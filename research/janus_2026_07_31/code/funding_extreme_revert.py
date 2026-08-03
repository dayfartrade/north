"""funding_extreme_revert — fade crowded perpetual positioning.

Thesis (well-documented in crypto microstructure papers):
  When perpetual funding rate is at a 90-day extreme (95th percentile
  positive or 5th percentile negative), one side of the book is paying
  the other for the privilege of being levered. Extreme funding is a
  marker of crowding; crowded positioning unwinds. Fade the direction.

Mechanism synthesis 2026-06-25: per "Perpetual Futures + Market Quality"
paper, funding fee is a structural information aggregator. The
2026-06-25 multi-exchange funding aggregator wires Binance + Bybit +
OKX (+ Bitget) into a cross-exchange composite rate, behind the
MULTI_EXCHANGE_FUNDING_ENABLED env flag. The paper used Coinglass-
aggregated cross-exchange data; we approximate with simple-mean
aggregation across the 4 majors.

Trigger:
  current_funding >= p95(90d)  AND  current_funding > 0  ->  SHORT
  current_funding <= p5(90d)   AND  current_funding < 0  ->  LONG

Geometry:
  Entry: last 1H close
  SL/TP: delegated to src/setups/level_picker.py — TA-aware using 4H
         swing structure + order-book walls when available; falls back
         to fixed 1.5% / 1.5R / 2.5R when 4H/depth aren't passed in.
  Hold: resolver handles 48h expiry
"""
from __future__ import annotations
import os
from typing import Optional

from ..data.bitget_depth import DepthSnapshot
from ..data.types import Candle
from ..indicators import atr, best_atr_estimate
from . import level_picker
from .types import SetupCandidate

_MIN_FUNDING_HIST = 50


# Funding-phase 6-8h post-pay BOOST — pre-reg 2026-07-20
# (research/library/funding_phase_6_8h_boost_prereg_2026_07_20.md).
# 6-8h post-pay bucket showed +0.315R at n=218 Bonferroni-clean POSITIVE
# in the 2026-07-20 perf read. Two-flag SHADOW/LIVE pattern matches
# dynamic_threshold + funding_trend.
#   FUNDING_PHASE_BOOST_SHADOW_ENABLED=true → log-only in confidence_reasons
#   FUNDING_PHASE_BOOST_LIVE_ENABLED=true   → also apply tier bump (later)
# Both default OFF. LIVE path is a follow-up commit after SHADOW eval;
# this file only implements the SHADOW logging.
_PHASE_BOOST_WINDOW_LOW = 6.0
_PHASE_BOOST_WINDOW_HIGH = 8.0


def _phase_boost_shadow_enabled() -> bool:
    return os.environ.get(
        "FUNDING_PHASE_BOOST_SHADOW_ENABLED", "",
    ).strip().lower() == "true"


def _phase_boost_live_enabled() -> bool:
    return os.environ.get(
        "FUNDING_PHASE_BOOST_LIVE_ENABLED", "",
    ).strip().lower() == "true"


def _hours_since_last_funding_pay(ts_ms: int) -> float:
    """Hours since the most recent 8h funding payment (Bitget V2:
    pays at 00:00, 08:00, 16:00 UTC).

    Returns float in [0, 8). Result 6.0-8.0 = in the pre-reg BOOST
    window (with 8.0 excluded since that IS the next pay).
    """
    hours_since_epoch = ts_ms / 3_600_000.0
    return hours_since_epoch % 8.0


def _in_phase_boost_window(ts_ms: int) -> bool:
    """True when timestamp falls in 6-8h post-pay (pre-reg locked)."""
    h = _hours_since_last_funding_pay(ts_ms)
    return _PHASE_BOOST_WINDOW_LOW <= h < _PHASE_BOOST_WINDOW_HIGH


# Dynamic-threshold gate — Path B per backtest verdict 2026-07-04
# (research/library/dynamic_funding_threshold_backtest_2026_07_04.md):
# additional filter `current >= REL_MULT * median(recent_short_window)`
# catches degenerate-distribution symbols (WIF/KAS/UNI class) at
# emission time, sparing them the reactive per-symbol SUPPRESS pattern.
#
# Two flags, matching funding_trend's SHADOW/LIVE pattern:
#   FUNDING_REVERT_DYNAMIC_THRESHOLD_ENABLED=true
#     → SHADOW-log the counterfactual in confidence_reasons; still fire.
#   FUNDING_REVERT_DYNAMIC_THRESHOLD_LIVE_ENABLED=true
#     → also gate: if current < REL_MULT * median, DO NOT fire.
# Both default OFF → zero behavior change. SHADOW is the pre-LIVE
# verification path; operator flips LIVE after reviewing SHADOW data.
_DYNAMIC_MEDIAN_WINDOW = 21  # ~7 days at 8h cadence — matches backtest
_DEFAULT_REL_MULT = 1.3      # empirically tuned in the 2026-07-04 verdict


def _dynamic_threshold_enabled() -> bool:
    return os.environ.get(
        "FUNDING_REVERT_DYNAMIC_THRESHOLD_ENABLED", "",
    ).strip().lower() == "true"


def _dynamic_threshold_live_enabled() -> bool:
    return os.environ.get(
        "FUNDING_REVERT_DYNAMIC_THRESHOLD_LIVE_ENABLED", "",
    ).strip().lower() == "true"


def read_dynamic_live_symbols() -> set[str]:
    """FUNDING_REVERT_DYNAMIC_LIVE_SYMBOLS — CSV of symbols where the
    Path B LIVE gate is applied. Default empty → LIVE gate applies to
    NO symbols even when FUNDING_REVERT_DYNAMIC_THRESHOLD_LIVE_ENABLED
    is true. Case-insensitive; whitespace stripped.

    Per pre-reg (per_symbol_path_b_live_design_2026_07_03.md):
    Qualifying criteria are (a) base_n ≥ 50, (b) pass_mR - fail_mR
    ≥ +0.15R, (c) pass_mR > 0, (d) fail_n ≥ 15. Locked candidate set
    at 2026-07-03: NEARUSDT, ICPUSDT, ATOMUSDT.

    Empty set semantics matter: an operator running the LIVE flag ON
    but the SYMBOLS list empty gets NO LIVE gating anywhere — pure
    SHADOW behavior. This is the intended safe default while the
    operator picks which symbols to activate."""
    raw = os.environ.get("FUNDING_REVERT_DYNAMIC_LIVE_SYMBOLS", "").strip()
    if not raw:
        return set()
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def _dynamic_rel_mult() -> float:
    raw = os.environ.get("FUNDING_REVERT_REL_MULT", "").strip()
    if not raw:
        return _DEFAULT_REL_MULT
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_REL_MULT
    # Guardrail: nothing below 1.0 (would degenerate to pass-all),
    # nothing above 3.0 (would silence everything).
    return max(1.0, min(val, 3.0))


def _dynamic_median(funding_history: list[tuple[int, float]]) -> Optional[float]:
    """Median of the last N funding readings (N = _DYNAMIC_MEDIAN_WINDOW).
    Returns None when insufficient history so caller can treat that
    case as "no counterfactual signal" rather than a bogus zero."""
    if len(funding_history) < _DYNAMIC_MEDIAN_WINDOW:
        return None
    window = [r for _, r in funding_history[-_DYNAMIC_MEDIAN_WINDOW:]]
    window.sort()
    n = len(window)
    if n % 2:
        return window[n // 2]
    return 0.5 * (window[n // 2 - 1] + window[n // 2])


def read_suppress_symbols() -> set[str]:
    """FUNDING_EXTREME_REVERT_SUPPRESS_SYMBOLS — CSV of symbols to emit
    as muted cards only (no setups-table insert). Default empty → zero
    behavior change. Case-insensitive; whitespace stripped.

    Locked action queue from pre-reg verdict 2026-06-30
    (research/library/per_symbol_edge_attribution_funding_extreme_revert_2026_06_29.md):
      KASUSDT (n=31, WR 45.2%, -0.097R) and BNBUSDT (n=13, WR 46.2%, +0.022R)
    were the only symbols meeting the SUPPRESS rule at that sample."""
    raw = os.environ.get("FUNDING_EXTREME_REVERT_SUPPRESS_SYMBOLS", "").strip()
    if not raw:
        return set()
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def read_suppress_exempt_low_symbols() -> set[str]:
    """FUNDING_EXTREME_REVERT_SUPPRESS_EXEMPT_LOW — CSV of symbols that
    are normally in the SUPPRESS list BUT get exempted when their
    confidence_tier resolves to 'low'.

    Motivation (per_symbol_edge_tier_low_audit_2026_07_07.md):
    the SUPPRESS list was originally built pre-tier-inversion-routing.
    Under tier=low routing, WIFUSDT (n=29, +0.276R) and UNIUSDT (n=16,
    +0.125R) show POSITIVE R at tier=low even though they're on the
    all-tier SUPPRESS list.

    Behavior:
      * Symbol in EXEMPT + tier=low → NORMAL insert path (auto-trader
        can route via G2b)
      * Symbol in EXEMPT + tier != low → apply SUPPRESS (muted only)
      * Symbol in SUPPRESS but NOT in EXEMPT → apply SUPPRESS (muted only)

    Default empty — zero behavior change until operator sets. The
    exemption ONLY applies to symbols ALSO listed in the SUPPRESS list;
    a symbol only in EXEMPT is a no-op."""
    raw = os.environ.get("FUNDING_EXTREME_REVERT_SUPPRESS_EXEMPT_LOW", "").strip()
    if not raw:
        return set()
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


# V2.0 backtest finding (scripts/backtest_funding_revert.py):
#   LONGS  n=46, mean -0.347R post-cost, CI95 [-0.675, -0.020]
#          -> STATISTICALLY NEGATIVE EDGE
#   SHORTS n=108, mean +0.180R post-cost, CI95 [-0.059, +0.420]
#          -> indistinguishable; barely positive
# Consistent with Grimes asymmetry. Window dominated by crypto downtrend.
# Until an uptrend backtest validates long branch, suppress.
_LONG_BRANCH_VALIDATED = False


def _percentile(sorted_values: list[float], p: float) -> float:
    """Linear-interp percentile. p in [0, 100]."""
    n = len(sorted_values)
    if n == 0:
        raise ValueError("empty input")
    if n == 1:
        return sorted_values[0]
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def detect(
    symbol: str,
    one_h: list[Candle],
    funding_history: list[tuple[int, float]],
    current_funding_rate: float,
    *,
    four_h: Optional[list[Candle]] = None,
    depth: Optional[DepthSnapshot] = None,
) -> list[SetupCandidate]:
    """Inputs:
      one_h            recent 1H candles; last close is the entry reference
      funding_history  ascending (ts_ms, rate) tuples from bitget.fetch_history_funding
      current_funding_rate  the just-now snapshot (could come from funding endpoint)
      four_h           OPTIONAL 4H candles — when present, level_picker uses
                       swing structure for SL/TP. Else falls back to fixed pct.
      depth            OPTIONAL order-book snapshot — when present, walls are
                       considered alongside swings.
    """
    if len(one_h) < 2 or len(funding_history) < _MIN_FUNDING_HIST:
        return []

    rates = sorted([r for _, r in funding_history])
    p95 = _percentile(rates, 95)
    p5 = _percentile(rates, 5)

    side: Optional[str] = None
    reason_extra = ""
    if current_funding_rate > 0 and current_funding_rate >= p95:
        side = "short"
        reason_extra = (
            f"current {current_funding_rate*100:.4f}%/8h >= 95th %ile "
            f"({p95*100:.4f}%) — longs over-paying, crowded"
        )
    elif current_funding_rate < 0 and current_funding_rate <= p5:
        if not _LONG_BRANCH_VALIDATED:
            return []  # backtest showed STATISTICALLY NEGATIVE; suppress
        side = "long"
        reason_extra = (
            f"current {current_funding_rate*100:.4f}%/8h <= 5th %ile "
            f"({p5*100:.4f}%) — shorts over-paying, crowded"
        )
    else:
        return []

    # Dynamic-threshold counterfactual — compute median(7d) and whether
    # the current rate passes the REL_MULT gate. Used for both SHADOW
    # logging AND (when LIVE flag is set) actual gating. Compute once
    # regardless of flags so the check is cheap to enable.
    dyn_median = _dynamic_median(funding_history)
    dyn_rel_mult = _dynamic_rel_mult()
    dyn_passes: Optional[bool] = None
    if dyn_median is not None and dyn_median > 0:
        dyn_passes = abs(current_funding_rate) >= dyn_rel_mult * abs(dyn_median)
    # LIVE gate — after operator promotes SHADOW → LIVE, this actually
    # blocks emission. Defensive: only gate when we have a real median
    # signal; when median is None (cold-start / short history) let the
    # baseline gate decide alone.
    #
    # Per-symbol filter added 2026-07-03 (AFK iter 3): only apply LIVE
    # gate when the symbol is in FUNDING_REVERT_DYNAMIC_LIVE_SYMBOLS.
    # Empty set → NO symbols gated (safe default). Universe-wide sweep
    # showed LIVE would hurt many symbols; only NEAR/ICP/ATOM currently
    # meet the pre-reg qualification criteria.
    if (_dynamic_threshold_live_enabled()
            and dyn_passes is False):
        live_syms = read_dynamic_live_symbols()
        if live_syms and symbol.upper() in live_syms:
            return []

    trigger_price = float(one_h[-1].close)
    if trigger_price <= 0:
        return []

    # ATR_4H — used as buffer in the picker. 0 means picker will fall back.
    # We pass 4H to the picker (it needs the real 4H value for SL/TP
    # placement) but ALSO compute a fallback estimate for atr_at_setup
    # storage. When 4H is missing or short, the storage uses 1H * 2 so
    # perf_by_regime has a usable value instead of NULL.
    atr_4h_val = 0.0
    if four_h and len(four_h) >= 15:
        atr_series = atr(four_h, 14)
        last_atr = next((x for x in reversed(atr_series) if x is not None), 0.0)
        atr_4h_val = float(last_atr or 0.0)
    atr_for_storage = best_atr_estimate(four_h=four_h, one_h=one_h)

    # Entry discount — gated behind ENTRY_DISCOUNT_ENABLED env flag.
    # When ON, places a limit entry slightly above (SHORT) or below
    # (LONG) the trigger price for better fill on the typical post-
    # trigger bounce. When OFF (default), entry == trigger price as
    # before. Uses ATR-buffered helper (catalyst specialists lack a
    # natural structural anchor for the standard suggest_entry).
    #
    # SHADOW mode (2026-07-09): also compute the ENTRY_DISCOUNT price
    # when atr is available, regardless of the LIVE flag. Persisted
    # to setups.entry_shadow_price for post-hoc analysis under the
    # entry_discount_prereg_2026_07_09.md middle path. Zero live
    # behavior change from computing shadow — actual entry uses the
    # flag path as before.
    entry_reason = ""
    shadow_entry: Optional[float] = None
    shadow_method: Optional[str] = None
    shadow_discount_pct: Optional[float] = None
    if atr_4h_val > 0:
        _shadow_ep = level_picker.suggest_entry_atr_buffered(
            side=side, trigger_price=trigger_price, atr=atr_4h_val,
        )
        if _shadow_ep.method != "no_discount":
            shadow_entry = _shadow_ep.entry
            shadow_method = _shadow_ep.method
            shadow_discount_pct = _shadow_ep.discount_pct
    if level_picker.entry_discount_enabled() and atr_4h_val > 0:
        ep = level_picker.suggest_entry_atr_buffered(
            side=side, trigger_price=trigger_price, atr=atr_4h_val,
        )
        entry = ep.entry
        if ep.method != "no_discount":
            entry_reason = (
                f"entry {ep.reason} "
                f"(discount {ep.discount_pct*100:.2f}% vs trigger {trigger_price:.6f})"
            )
    else:
        entry = trigger_price

    levels = level_picker.suggest_levels(
        side=side, entry=entry, atr_4h=atr_4h_val, four_h=four_h, depth=depth,
    )
    if levels is None:
        return []

    reasons = [
        f"funding_extreme_revert · n={len(funding_history)} ({len(funding_history)*8/24:.0f}d hist)",
        reason_extra,
        f"thesis: extreme positioning unwinds; fade {side} side",
    ]
    if entry_reason:
        reasons.append(entry_reason)
    reasons.extend([
        f"SL {levels.sl_reason}",
        f"TP1 {levels.tp1_reason}",
        f"TP2 {levels.tp2_reason}",
    ])
    # SHADOW counterfactual — record whether the dynamic-threshold gate
    # would have kept this fire. Enables post-hoc n=50 evaluation without
    # a schema change. Only rendered when the flag is on (or LIVE);
    # avoids polluting the reasons array for the default OFF path.
    if (_dynamic_threshold_enabled() or _dynamic_threshold_live_enabled()) \
            and dyn_median is not None:
        verdict = "PASSED" if dyn_passes else "filtered"
        reasons.append(
            f"SHADOW[dynamic_threshold={verdict}]: "
            f"current {current_funding_rate*100:.4f}% vs "
            f"{dyn_rel_mult:.2f}*median(7d) "
            f"= {dyn_rel_mult * dyn_median * 100:.4f}%"
        )

    # Funding-phase 6-8h post-pay SHADOW — pre-reg 2026-07-20
    # (funding_phase_6_8h_boost_prereg_2026_07_20.md). Logs whether
    # this setup falls in the pre-reg BOOST window. LIVE tier bump is
    # a separate flag + follow-up commit; this file only records the
    # counterfactual so post-hoc analysis can validate the effect.
    if _phase_boost_shadow_enabled() or _phase_boost_live_enabled():
        trigger_ts = int(one_h[-1].ts_ms)
        hours_since_pay = _hours_since_last_funding_pay(trigger_ts)
        in_window = _in_phase_boost_window(trigger_ts)
        reasons.append(
            f"SHADOW[phase_boost={'true' if in_window else 'false'}]: "
            f"hours_since_pay={hours_since_pay:.2f}"
        )

    # Funding extremity percentile — used by Option C component 1 scoring
    # (QUALITY_C1_ENABLED). Same logic as src/regime_direction._percentile_rank
    # but applied to the abs-funding-rate distribution so it works for both
    # positive (SHORT side) and negative (LONG side) funding triggers.
    abs_rates = sorted(abs(r) for r in rates)
    abs_current = abs(current_funding_rate)
    n_below = sum(1 for r in abs_rates if r < abs_current)
    funding_extremity_percentile = (n_below / len(abs_rates)) * 100.0 if abs_rates else 50.0

    return [SetupCandidate(
        symbol=symbol,
        side=side,
        source_phase="funding_extreme_revert",
        bias_tf="none",
        trigger_tf="1H",
        entry_price=entry,
        sl_price=levels.sl,
        tp1_price=levels.tp1,
        tp2_price=levels.tp2,
        atr_at_setup=atr_for_storage,
        bias_alignment="aligned",  # not really; placeholder for scoring
        volume_confirmed=False,
        reasons=reasons,
        funding_extremity_percentile=funding_extremity_percentile,
        entry_shadow_price=shadow_entry,
        entry_shadow_method=shadow_method,
        entry_shadow_discount_pct=shadow_discount_pct,
    )]
