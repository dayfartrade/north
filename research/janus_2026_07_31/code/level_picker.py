"""TA-aware SL/TP level picker.

The fixed-percentage SL/TP defaults (1.50% / 2.25% / 3.75%) used by
funding_extreme_revert and pm_consensus_shift ignored all structural
information. This module produces TA-driven levels using:

  - 4H swing highs / lows  → structural support / resistance
  - Order-book walls       → current liquidity barriers
  - ATR(14) on 4H          → noise-tolerance buffer

Algorithm (SHORT; LONG mirrors):

  SL (above entry):
    structural    = nearest 4H swing high > entry, + 0.30 * ATR_4H
    wall          = nearest ask wall > entry,      + 0.20 * ATR_4H
    SL = max(structural, wall, entry * (1 + 0.5%))   # max = furthest, safest
    cap SL at entry * (1 + 3.0%)                     # never risk > 3%

  TP1 (below entry, RR ≥ 1.0):
    structural    = nearest 4H swing low < entry, + 0.20 * ATR_4H   (exit BEFORE structure)
    wall          = nearest bid wall < entry,     + 0.20 * ATR_4H   (exit BEFORE wall)
    TP1 = max(structural, wall)                     # max = closer to entry (more achievable)
    if RR < 1.0, promote TP1 to entry - 1.0 * risk

  TP2 (below entry, RR ≥ 2.0):
    deeper_struct = 2nd-nearest 4H swing low < entry, + 0.20 * ATR_4H
    floor         = entry - 2.5 * risk
    TP2 = min(deeper_struct, floor)                  # min = further from entry (more reward)
    if RR < 2.0, promote TP2 to entry - 2.0 * risk

Fallback: if four_h is empty / lacks swings AND depth is None,
returns the legacy fixed-percentage (1.5% SL, 1.5R TP1, 2.5R TP2)
levels so calling sites that don't have TA inputs still work.

Stop-tightening (2026-06-25): if STOP_TIGHTEN_F env var is a numeric
value in (0, 1), the SL distance shrinks to original * (1 - F) AFTER
all structural placement, AFTER caps, AFTER fallback. The 0.5% floor
re-applies after tightening so a degenerate F=0.99 still keeps a
sane SL. TP prices are UNCHANGED — R-multiples mechanically increase.
Pre-reg: research/library/stop_tighten_live_promotion_prereg_2026_06_25.md
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

from ..data.bitget_depth import DepthSnapshot
from ..data.types import Candle
from ..indicators import swing_highs, swing_lows
from ..sl_obfuscation import obfuscate_price

_SL_MIN_PCT = 0.005      # 0.5% floor — never risk less than this
_SL_MAX_PCT = 0.030      # 3.0% cap   — never risk more than this
_SL_STRUCT_BUFFER_ATR = 0.30
_SL_WALL_BUFFER_ATR = 0.20
_TP_STRUCT_BUFFER_ATR = 0.20   # exit BEFORE structure / wall
_TP_WALL_BUFFER_ATR = 0.20
_MIN_RR_TP1 = 1.0
_MIN_RR_TP2 = 2.0
_TP2_FLOOR_R = 2.5
_FALLBACK_SL_PCT = 0.015
_FALLBACK_TP1_R = 1.5
_FALLBACK_TP2_R = 2.5

# suggest_entry tuning
_ENTRY_STRUCT_BUFFER_ATR = 0.30   # how far above support / below resistance to limit
_ENTRY_MAX_DISTANCE_PCT = 0.015   # don't chase more than 1.5% from trigger price
_ENTRY_MIN_DISCOUNT_PCT = 0.001   # ignore <0.1% improvements (fee noise — just market)


@dataclass(frozen=True)
class LevelPickerResult:
    sl: float
    tp1: float
    tp2: float
    rr1: float
    rr2: float
    sl_reason: str
    tp1_reason: str
    tp2_reason: str
    method: str       # 'ta_aware' or 'fallback'


@dataclass(frozen=True)
class EntryResult:
    entry: float
    reason: str
    discount_pct: float   # positive = better than trigger; 0.0 = no discount
    method: str           # 'structural', 'bounded', 'no_discount'


def _fallback(side: str, entry: float) -> LevelPickerResult:
    if side == "short":
        sl = entry * (1 + _FALLBACK_SL_PCT)
        risk = sl - entry
        tp1 = entry - risk * _FALLBACK_TP1_R
        tp2 = entry - risk * _FALLBACK_TP2_R
    else:
        sl = entry * (1 - _FALLBACK_SL_PCT)
        risk = entry - sl
        tp1 = entry + risk * _FALLBACK_TP1_R
        tp2 = entry + risk * _FALLBACK_TP2_R
    # D2 obfuscation — apply consistently across all SL return paths.
    sl = obfuscate_price(sl, seed_key=f"{side}|{entry}|{sl}|fallback")
    return LevelPickerResult(
        sl=sl, tp1=tp1, tp2=tp2,
        rr1=_FALLBACK_TP1_R, rr2=_FALLBACK_TP2_R,
        sl_reason=f"fallback {_FALLBACK_SL_PCT*100:.1f}% (no 4H structure)",
        tp1_reason=f"fallback {_FALLBACK_TP1_R}R",
        tp2_reason=f"fallback {_FALLBACK_TP2_R}R",
        method="fallback",
    )


def _read_stop_tighten_f() -> float:
    """Read STOP_TIGHTEN_F env var. Returns 0.0 (no tightening) when
    unset / invalid / out of (0, 1) range. Pre-reg-locked at F=0.5 per
    backtest verdict 2026-06-25 — only that exact value is currently
    SHIPPED behind this flag; any other value is a research override.

    NOTE: returning > 0.0 means "F is configured" — not "tightening is
    live." Live emission requires STOP_TIGHTEN_LIVE_ENABLED=true also
    (checked by _stop_tighten_live_enabled). The two flags split the
    SHADOW phase (F set, LIVE off → log only) from LIVE phase (both on).
    """
    raw = os.environ.get("STOP_TIGHTEN_F", "").strip()
    if not raw:
        return 0.0
    try:
        f = float(raw)
    except ValueError:
        return 0.0
    if not (0.0 < f < 1.0):
        return 0.0
    return f


def _stop_tighten_live_enabled() -> bool:
    """Whether the tightened SL should be EMITTED ON THE CARD.

    Default off. When false but STOP_TIGHTEN_F is set, scanner logs the
    tightened SL to setup_sl_shadow but the card still carries the
    original SL — that's the SHADOW phase.
    """
    val = os.environ.get("STOP_TIGHTEN_LIVE_ENABLED", "").strip().lower()
    return val in ("true", "1", "yes", "on")


def compute_tightened_sl(side: str, entry: float, sl: float, f: float) -> float:
    """Pure helper — given an original SL price and an F in (0, 1),
    return the tightened SL price (closer to entry).

    Re-applies the 0.5% floor after tightening so a degenerate F doesn't
    produce a sub-noise SL. Used by the scanner during SHADOW phase to
    log what the tightened SL WOULD have been.
    """
    if f <= 0.0 or f >= 1.0:
        return sl
    if side == "short":
        orig_distance = sl - entry
        new_distance = orig_distance * (1.0 - f)
        new_sl = entry + new_distance
        floor_sl = entry * (1.0 + _SL_MIN_PCT)
        if new_sl < floor_sl:
            new_sl = floor_sl
        return new_sl
    orig_distance = entry - sl
    new_distance = orig_distance * (1.0 - f)
    new_sl = entry - new_distance
    floor_sl = entry * (1.0 - _SL_MIN_PCT)
    if new_sl > floor_sl:
        new_sl = floor_sl
    return new_sl


def _apply_stop_tighten(
    side: str, entry: float, sl: float,
) -> tuple[float, Optional[str]]:
    """Apply F-multiplier tightening to the SL distance ONLY when LIVE
    flag is true. Returns (new_sl, reason_suffix). reason_suffix is
    None when no tightening applied (either F unset OR LIVE off — the
    SHADOW phase keeps the original SL on the card).
    """
    f = _read_stop_tighten_f()
    if f == 0.0 or not _stop_tighten_live_enabled():
        return sl, None
    new_sl = compute_tightened_sl(side, entry, sl, f)
    suffix = f" · tightened F={f:.2f}"
    return new_sl, suffix


def suggest_levels(
    *,
    side: str,
    entry: float,
    atr_4h: float,
    four_h: Optional[list[Candle]] = None,
    depth: Optional[DepthSnapshot] = None,
) -> Optional[LevelPickerResult]:
    """Return TA-aware (sl, tp1, tp2) for a setup.

    Falls back to fixed-percentage levels when 4H structure is missing.
    Returns None only on pathological input (entry <= 0).
    """
    if entry <= 0:
        return None
    if side not in ("short", "long"):
        return None

    # If 4H or ATR is unavailable, fall back to fixed-percentage levels.
    if not four_h or len(four_h) < 5 or atr_4h <= 0:
        result = _fallback(side, entry)
    elif side == "short":
        result = _short(entry, atr_4h, four_h, depth)
    else:
        result = _long(entry, atr_4h, four_h, depth)

    # Apply STOP_TIGHTEN_F multiplier AFTER all structural placement
    # (incl floor/cap inside _short/_long, incl fallback path).
    # Floor re-applied inside _apply_stop_tighten so a too-tight SL
    # still respects the 0.5% minimum.
    new_sl, suffix = _apply_stop_tighten(side, entry, result.sl)
    if suffix is None:
        return result
    # Re-derive risk + RR with tightened SL. TP1/TP2 prices unchanged.
    new_risk = abs(new_sl - entry)
    if new_risk <= 0:
        return result   # degenerate; keep original
    new_rr1 = abs(result.tp1 - entry) / new_risk
    new_rr2 = abs(result.tp2 - entry) / new_risk
    return LevelPickerResult(
        sl=new_sl,
        tp1=result.tp1, tp2=result.tp2,
        rr1=new_rr1, rr2=new_rr2,
        sl_reason=result.sl_reason + suffix,
        tp1_reason=result.tp1_reason, tp2_reason=result.tp2_reason,
        method=result.method,
    )


def _short(
    entry: float, atr_4h: float,
    four_h: list[Candle], depth: Optional[DepthSnapshot],
) -> LevelPickerResult:
    swing_high_idxs = swing_highs(four_h, k=2)
    highs_above = sorted(
        [four_h[i].high for i in swing_high_idxs if four_h[i].high > entry]
    )
    nearest_high = highs_above[0] if highs_above else None

    swing_low_idxs = swing_lows(four_h, k=2)
    lows_below = sorted(
        [four_h[i].low for i in swing_low_idxs if four_h[i].low < entry],
        reverse=True,  # nearest (highest, closest to entry) first
    )
    nearest_low = lows_below[0] if lows_below else None
    second_low = lows_below[1] if len(lows_below) > 1 else None

    ask_wall = (
        depth.nearest_ask_wall[0]
        if depth and depth.nearest_ask_wall and depth.nearest_ask_wall[0] > entry
        else None
    )
    bid_wall = (
        depth.nearest_bid_wall[0]
        if depth and depth.nearest_bid_wall and depth.nearest_bid_wall[0] < entry
        else None
    )

    # ── SL: above entry, max of structural+wall+floor, capped at MAX_PCT ──
    sl_floor = entry * (1 + _SL_MIN_PCT)
    sl_cap = entry * (1 + _SL_MAX_PCT)
    sl_candidates: list[tuple[str, float]] = [("min_floor", sl_floor)]
    if nearest_high is not None:
        sl_candidates.append(("swing_high", nearest_high + _SL_STRUCT_BUFFER_ATR * atr_4h))
    if ask_wall is not None:
        sl_candidates.append(("ask_wall", ask_wall + _SL_WALL_BUFFER_ATR * atr_4h))
    sl_pick = max(sl_candidates, key=lambda x: x[1])
    sl_capped = False
    if sl_pick[1] > sl_cap:
        sl = sl_cap
        sl_capped = True
        sl_reason = f"capped at +{_SL_MAX_PCT*100:.1f}% (struct {sl_pick[0]} too far)"
    else:
        sl = sl_pick[1]
        sl_reason = f"{sl_pick[0]} {sl:.6f}"

    risk = sl - entry
    # ── TP1: below entry, closer of struct+wall, RR ≥ 1.0 ──
    tp1_candidates: list[tuple[str, float]] = []
    if nearest_low is not None:
        tp1_candidates.append((
            "swing_low", nearest_low + _TP_STRUCT_BUFFER_ATR * atr_4h,
        ))
    if bid_wall is not None:
        tp1_candidates.append((
            "bid_wall", bid_wall + _TP_WALL_BUFFER_ATR * atr_4h,
        ))
    if tp1_candidates:
        # pick max (closer to entry → more achievable)
        tp1_pick = max(tp1_candidates, key=lambda x: x[1])
        tp1 = tp1_pick[1]
        tp1_reason = f"{tp1_pick[0]} {tp1:.6f}"
        # Must be below entry
        if tp1 >= entry:
            tp1 = entry - _MIN_RR_TP1 * risk
            tp1_reason = f"structural above entry — promoted to {_MIN_RR_TP1}R"
    else:
        tp1 = entry - _FALLBACK_TP1_R * risk
        tp1_reason = f"no struct or wall — {_FALLBACK_TP1_R}R"
    rr1 = (entry - tp1) / risk
    if rr1 < _MIN_RR_TP1:
        tp1 = entry - _MIN_RR_TP1 * risk
        tp1_reason = f"struct RR {rr1:.2f}R < {_MIN_RR_TP1} — promoted to {_MIN_RR_TP1}R"
        rr1 = _MIN_RR_TP1

    # ── TP2: deeper, min of 2nd-swing+floor, RR ≥ 2.0 ──
    tp2_candidates: list[tuple[str, float]] = [("floor", entry - _TP2_FLOOR_R * risk)]
    if second_low is not None:
        tp2_candidates.append((
            "swing_low_2", second_low + _TP_STRUCT_BUFFER_ATR * atr_4h,
        ))
    # pick min (further from entry → more reward) but must be < tp1
    tp2_pick = min(tp2_candidates, key=lambda x: x[1])
    tp2 = tp2_pick[1]
    tp2_reason = f"{tp2_pick[0]} {tp2:.6f}"
    if tp2 >= tp1:
        tp2 = entry - _MIN_RR_TP2 * risk
        tp2_reason = f"deeper struct above tp1 — promoted to {_MIN_RR_TP2}R"
    rr2 = (entry - tp2) / risk
    if rr2 < _MIN_RR_TP2:
        tp2 = entry - _MIN_RR_TP2 * risk
        tp2_reason = f"struct RR {rr2:.2f}R < {_MIN_RR_TP2} — promoted to {_MIN_RR_TP2}R"
        rr2 = _MIN_RR_TP2

    # D2 obfuscation (predator defense) — apply BEFORE returning so the
    # obfuscated SL is what's stored, displayed, and tracked. No-op when
    # SL_OBFUSCATION_ENABLED is unset. Seed_key uses entry + raw sl so
    # the offset is deterministic per-setup and stable across recomputes.
    sl = obfuscate_price(sl, seed_key=f"short|{entry}|{sl}")

    return LevelPickerResult(
        sl=sl, tp1=tp1, tp2=tp2,
        rr1=round(rr1, 3), rr2=round(rr2, 3),
        sl_reason=sl_reason, tp1_reason=tp1_reason, tp2_reason=tp2_reason,
        method="ta_aware",
    )


def entry_discount_enabled() -> bool:
    """ENTRY_DISCOUNT_ENABLED master flag for catalyst specialists.
    Default off → existing trigger-price behavior preserved. Operator
    flips on to start placing structurally-aware limit entries on
    funding_extreme_revert, cme_gap_fill, pm_consensus_shift cards.

    grimes_pullback already uses suggest_entry with a real structural
    anchor and is unaffected by this flag.
    """
    v = os.environ.get("ENTRY_DISCOUNT_ENABLED", "").strip().lower()
    return v in ("true", "1", "yes", "on")


def suggest_entry_atr_buffered(
    *,
    side: str,
    trigger_price: float,
    atr: float,
    atr_multiple: float = 0.3,
) -> EntryResult:
    """ATR-buffered limit entry for catalyst specialists (no natural
    structural anchor).

    For SHORT, entry = trigger + atr_multiple * ATR (better fill on a
    small post-trigger bounce). For LONG, mirror.

    Same caps as `suggest_entry`:
      * MIN_DISCOUNT (0.1%) — if the proposed improvement is below fee
        noise, return trigger_price (market order behavior)
      * MAX_DISTANCE (1.5%) — if the buffer exceeds 1.5% from trigger,
        clamp to that bound

    Pathological inputs collapse to trigger_price.
    """
    if trigger_price <= 0 or side not in ("short", "long"):
        return EntryResult(
            entry=trigger_price, reason="invalid input",
            discount_pct=0.0, method="no_discount",
        )
    if atr <= 0:
        return EntryResult(
            entry=trigger_price, reason="no ATR — fall back to market",
            discount_pct=0.0, method="no_discount",
        )

    buffer = atr_multiple * atr
    if side == "short":
        # Entry ABOVE trigger (better fill on a small upward bounce)
        ideal = trigger_price + buffer
        # If buffer is too small (< MIN_DISCOUNT), market entry
        if (ideal - trigger_price) / trigger_price < _ENTRY_MIN_DISCOUNT_PCT:
            return EntryResult(
                entry=trigger_price,
                reason=f"buffer {buffer:.6f} below min discount — market",
                discount_pct=0.0, method="no_discount",
            )
        # Cap at MAX_DISTANCE
        ceiling = trigger_price * (1 + _ENTRY_MAX_DISTANCE_PCT)
        if ideal > ceiling:
            entry = ceiling
            method = "bounded"
            reason = (
                f"clamped at +{_ENTRY_MAX_DISTANCE_PCT*100:.1f}% — "
                f"ATR buffer {buffer:.6f} too aggressive"
            )
        else:
            entry = ideal
            method = "atr_buffered"
            reason = f"+{atr_multiple:.1f}*ATR buffer above trigger"
        discount_pct = (entry - trigger_price) / trigger_price
    else:  # long
        ideal = trigger_price - buffer
        if (trigger_price - ideal) / trigger_price < _ENTRY_MIN_DISCOUNT_PCT:
            return EntryResult(
                entry=trigger_price,
                reason=f"buffer {buffer:.6f} below min discount — market",
                discount_pct=0.0, method="no_discount",
            )
        floor = trigger_price * (1 - _ENTRY_MAX_DISTANCE_PCT)
        if ideal < floor:
            entry = floor
            method = "bounded"
            reason = (
                f"clamped at -{_ENTRY_MAX_DISTANCE_PCT*100:.1f}% — "
                f"ATR buffer {buffer:.6f} too aggressive"
            )
        else:
            entry = ideal
            method = "atr_buffered"
            reason = f"-{atr_multiple:.1f}*ATR buffer below trigger"
        discount_pct = (trigger_price - entry) / trigger_price
    return EntryResult(
        entry=entry, reason=reason,
        discount_pct=discount_pct, method=method,
    )


def suggest_entry(
    *,
    side: str,
    trigger_price: float,
    structural_level: float,
    atr_4h: float,
) -> EntryResult:
    """Pick a TA-aware limit entry, anchored to an S/R level.

    For longs, the caller passes the structural support the setup is
    leaning on (e.g. pullback_low). We propose a limit *above* that
    support — `structural_level + 0.30 * ATR_4H` — so the trade fills on
    a retest rather than chasing the post-signal close. Symmetric for
    shorts.

    Two bounds keep this honest:

      - `_ENTRY_MAX_DISTANCE_PCT` (1.5%): if the structural level is
        further than 1.5% from `trigger_price`, we clamp to that bound.
        Going deeper than 1.5% has too low a fill probability for the
        marginal price improvement to pay back.
      - `_ENTRY_MIN_DISCOUNT_PCT` (0.1%): if the improvement vs
        `trigger_price` is below 0.1% (i.e. inside fee noise), we fall
        back to `trigger_price`. No point placing a limit that's
        functionally a market order.

    Pathological inputs (entry ≤ 0, missing ATR) collapse to
    `trigger_price` rather than returning None — entries are required
    for every setup and the upstream specialist can still emit at market.
    """
    if trigger_price <= 0 or side not in ("short", "long"):
        return EntryResult(
            entry=trigger_price, reason="invalid input",
            discount_pct=0.0, method="no_discount",
        )
    if atr_4h <= 0 or structural_level <= 0:
        return EntryResult(
            entry=trigger_price, reason="no ATR / structure available",
            discount_pct=0.0, method="no_discount",
        )

    buffer = _ENTRY_STRUCT_BUFFER_ATR * atr_4h

    if side == "long":
        # Want entry BELOW trigger, above structural support.
        ideal = structural_level + buffer
        # If ideal ≥ trigger (structure isn't actually a discount), bail.
        if ideal >= trigger_price * (1 - _ENTRY_MIN_DISCOUNT_PCT):
            return EntryResult(
                entry=trigger_price,
                reason=f"structure {structural_level:.6f}+buf above trigger {trigger_price:.6f} — market",
                discount_pct=0.0, method="no_discount",
            )
        floor = trigger_price * (1 - _ENTRY_MAX_DISTANCE_PCT)
        if ideal < floor:
            # structural is deeper than we'll chase — clamp.
            entry = floor
            method = "bounded"
            reason = (
                f"clamped at -{_ENTRY_MAX_DISTANCE_PCT*100:.1f}% "
                f"(structure {structural_level:.6f}+buf={ideal:.6f} too deep)"
            )
        else:
            entry = ideal
            method = "structural"
            reason = (
                f"limit at structural support {structural_level:.6f}"
                f" + {_ENTRY_STRUCT_BUFFER_ATR}*ATR = {entry:.6f}"
            )
        discount_pct = (trigger_price - entry) / trigger_price
        return EntryResult(entry=entry, reason=reason,
                           discount_pct=round(discount_pct, 5), method=method)

    # short — mirror
    ideal = structural_level - buffer
    if ideal <= trigger_price * (1 + _ENTRY_MIN_DISCOUNT_PCT):
        return EntryResult(
            entry=trigger_price,
            reason=f"structure {structural_level:.6f}-buf below trigger {trigger_price:.6f} — market",
            discount_pct=0.0, method="no_discount",
        )
    ceiling = trigger_price * (1 + _ENTRY_MAX_DISTANCE_PCT)
    if ideal > ceiling:
        entry = ceiling
        method = "bounded"
        reason = (
            f"clamped at +{_ENTRY_MAX_DISTANCE_PCT*100:.1f}% "
            f"(structure {structural_level:.6f}-buf={ideal:.6f} too far)"
        )
    else:
        entry = ideal
        method = "structural"
        reason = (
            f"limit at structural resistance {structural_level:.6f}"
            f" - {_ENTRY_STRUCT_BUFFER_ATR}*ATR = {entry:.6f}"
        )
    discount_pct = (entry - trigger_price) / trigger_price
    return EntryResult(entry=entry, reason=reason,
                       discount_pct=round(discount_pct, 5), method=method)


def _long(
    entry: float, atr_4h: float,
    four_h: list[Candle], depth: Optional[DepthSnapshot],
) -> LevelPickerResult:
    # Mirror of _short with above/below swapped.
    swing_low_idxs = swing_lows(four_h, k=2)
    lows_below = sorted(
        [four_h[i].low for i in swing_low_idxs if four_h[i].low < entry],
        reverse=True,
    )
    nearest_low = lows_below[0] if lows_below else None

    swing_high_idxs = swing_highs(four_h, k=2)
    highs_above = sorted(
        [four_h[i].high for i in swing_high_idxs if four_h[i].high > entry]
    )
    nearest_high = highs_above[0] if highs_above else None
    second_high = highs_above[1] if len(highs_above) > 1 else None

    bid_wall = (
        depth.nearest_bid_wall[0]
        if depth and depth.nearest_bid_wall and depth.nearest_bid_wall[0] < entry
        else None
    )
    ask_wall = (
        depth.nearest_ask_wall[0]
        if depth and depth.nearest_ask_wall and depth.nearest_ask_wall[0] > entry
        else None
    )

    # SL: below entry, min of structural+wall (further from entry = safer), floored at -0.5%, capped at -3%
    sl_floor = entry * (1 - _SL_MIN_PCT)
    sl_cap = entry * (1 - _SL_MAX_PCT)
    sl_candidates: list[tuple[str, float]] = [("min_floor", sl_floor)]
    if nearest_low is not None:
        sl_candidates.append(("swing_low", nearest_low - _SL_STRUCT_BUFFER_ATR * atr_4h))
    if bid_wall is not None:
        sl_candidates.append(("bid_wall", bid_wall - _SL_WALL_BUFFER_ATR * atr_4h))
    sl_pick = min(sl_candidates, key=lambda x: x[1])
    if sl_pick[1] < sl_cap:
        sl = sl_cap
        sl_reason = f"capped at -{_SL_MAX_PCT*100:.1f}% (struct {sl_pick[0]} too far)"
    else:
        sl = sl_pick[1]
        sl_reason = f"{sl_pick[0]} {sl:.6f}"

    risk = entry - sl
    # TP1: above entry, closer of structural+wall (min = closer for long)
    tp1_candidates: list[tuple[str, float]] = []
    if nearest_high is not None:
        tp1_candidates.append((
            "swing_high", nearest_high - _TP_STRUCT_BUFFER_ATR * atr_4h,
        ))
    if ask_wall is not None:
        tp1_candidates.append((
            "ask_wall", ask_wall - _TP_WALL_BUFFER_ATR * atr_4h,
        ))
    if tp1_candidates:
        tp1_pick = min(tp1_candidates, key=lambda x: x[1])  # closer to entry = lower for long
        tp1 = tp1_pick[1]
        tp1_reason = f"{tp1_pick[0]} {tp1:.6f}"
        if tp1 <= entry:
            tp1 = entry + _MIN_RR_TP1 * risk
            tp1_reason = f"struct below entry — promoted to {_MIN_RR_TP1}R"
    else:
        tp1 = entry + _FALLBACK_TP1_R * risk
        tp1_reason = f"no struct or wall — {_FALLBACK_TP1_R}R"
    rr1 = (tp1 - entry) / risk
    if rr1 < _MIN_RR_TP1:
        tp1 = entry + _MIN_RR_TP1 * risk
        tp1_reason = f"struct RR {rr1:.2f}R < {_MIN_RR_TP1} — promoted to {_MIN_RR_TP1}R"
        rr1 = _MIN_RR_TP1

    # TP2: deeper, max of 2nd-swing+floor (max = further from entry = more reward for long)
    tp2_candidates: list[tuple[str, float]] = [("floor", entry + _TP2_FLOOR_R * risk)]
    if second_high is not None:
        tp2_candidates.append((
            "swing_high_2", second_high - _TP_STRUCT_BUFFER_ATR * atr_4h,
        ))
    tp2_pick = max(tp2_candidates, key=lambda x: x[1])
    tp2 = tp2_pick[1]
    tp2_reason = f"{tp2_pick[0]} {tp2:.6f}"
    if tp2 <= tp1:
        tp2 = entry + _MIN_RR_TP2 * risk
        tp2_reason = f"deeper struct below tp1 — promoted to {_MIN_RR_TP2}R"
    rr2 = (tp2 - entry) / risk
    if rr2 < _MIN_RR_TP2:
        tp2 = entry + _MIN_RR_TP2 * risk
        tp2_reason = f"struct RR {rr2:.2f}R < {_MIN_RR_TP2} — promoted to {_MIN_RR_TP2}R"
        rr2 = _MIN_RR_TP2

    # D2 obfuscation (predator defense) — apply BEFORE returning. See
    # the matching note in _short. No-op when SL_OBFUSCATION_ENABLED unset.
    sl = obfuscate_price(sl, seed_key=f"long|{entry}|{sl}")

    return LevelPickerResult(
        sl=sl, tp1=tp1, tp2=tp2,
        rr1=round(rr1, 3), rr2=round(rr2, 3),
        sl_reason=sl_reason, tp1_reason=tp1_reason, tp2_reason=tp2_reason,
        method="ta_aware",
    )
