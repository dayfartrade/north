"""v8 strategy engine — single source of truth for filter and decision logic.

**Status: SKETCH (Phase 8.1). No production callers yet.**

Design principles (see docs/experiments/2026-07-13_v8_scope.md):
  P1 One module owns all filter logic; backtest + live + shadow import from here.
  P2 Filters are pure functions, unit-testable in isolation.
  P3 RegimeContext is a first-class input to every decision.
  P4 Dispatcher is a thin runner; strategy semantics live here.
  P5 Every decision is logged before any side effect.
  P6 One version per registry entry; ship = new VERSION constant.

This file will REPLACE:
  - edge_session_orb_v7_final.py (backtest strategy)
  - Most of dispatch_orb.py (dispatch's strategy calls)
  - The shadow candidate logic in shadow_log.py

Not touched yet — Phase 8.3 does the port.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Callable, Optional

import pandas as pd


VERSION = "v8.0.0-sketch"
"""Bump this on every strategy behavior change. Registry entries link to it."""


# ---------------------------------------------------------------------------
# Regime context (P3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegimeContext:
    """Snapshot of macro/market state at decision time.

    Populated by the caller BEFORE calling any filter or decision function.
    All fields optional — filters handle None gracefully (skip conditioning
    on that variable). Never mutated after construction.
    """
    as_of_utc: pd.Timestamp

    # Macro (daily FRED-style, updated at market close)
    real_yield_10y: Optional[float] = None      # 10y TIPS, %
    dxy: Optional[float] = None                 # Trade-weighted USD index
    tnx: Optional[float] = None                 # 10y Treasury yield, %

    # Positioning (weekly)
    cot_mm_net_long: Optional[float] = None     # Managed money net long, contracts
    cot_pct_52w: Optional[float] = None         # Percentile of 52w range

    # Prior-session context
    prior_day_range: Optional[float] = None     # Prior UTC-day GC range, pts
    prior_day_close_change: Optional[float] = None  # Δ vs 2 days ago

    # Bar-level context at decision time
    or_atr_ratio: Optional[float] = None
    or_win_vol_ratio: Optional[float] = None
    trend_slope: Optional[float] = None

    # Crypto/perpetual side channels
    funding_annualized_pct: Optional[float] = None
    basis_pct: Optional[float] = None

    # Crabel Ch 28 features (2026-07-13 shadow candidates)
    # Range class of prior day: "NR7","NR4","NR","CONTROL","WS","WS4","WS7"
    prior_day_range_class: Optional[str] = None
    # 3-day directional pattern: "---" through "+++"; direction of prev-2 close,
    # prev-1 close, today open compared pairwise (see docs/experiments/
    # 2026-07-13_crabel_findings.md)
    three_day_pattern: Optional[str] = None


# ---------------------------------------------------------------------------
# Decision protocol (P5)
# ---------------------------------------------------------------------------

class Direction(Enum):
    LONG = 1
    SHORT = -1
    FLAT = 0


@dataclass(frozen=True)
class SessionConfig:
    """Per-session strategy config. Immutable after ship."""
    name: str                    # "LON" | "NY" | "ASIA"
    or_bars: int = 6             # 30-min OR on 5m bars
    watch_bars: int = 12         # 60-min breakout window
    max_hold_bars: int = 36      # 3-hour max hold (v7.2 extended)

    # OR/ATR gate (per-session semantics — Phase 8.3 decides ranges)
    or_atr_max: Optional[float] = None   # skip if or_range > or_atr_max * ATR
    or_atr_min: Optional[float] = None   # skip if or_range < or_atr_min * ATR
    or_atr_deadzone: Optional[tuple[float, float]] = None  # skip if in range

    # Trend gate
    require_trend: bool = True    # skip if slope == 0 (FLAT)

    # Geometry
    stop_mode: str = "or_range"   # "or_range" | "fixed"
    fixed_stop_dollars: Optional[float] = None
    target_mode: str = "or_range" # "or_range" | "stop_x_tp"
    tp_mult: float = 1.5

    # Session UTC open time (DST-aware, computed per-date by caller)
    utc_open_local: time = time(0, 0)


@dataclass(frozen=True)
class Decision:
    """The output of `evaluate_session()`. Log this BEFORE any side effect."""
    ts_recorded_utc: pd.Timestamp
    version: str
    session: str
    or_open_utc: pd.Timestamp
    or_close_utc: pd.Timestamp
    or_high: float
    or_low: float
    or_range: float
    atr: float

    would_take: bool
    would_skip_reasons: tuple[str, ...] = ()  # empty if would_take

    direction: Direction = Direction.FLAT
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_price: Optional[float] = None

    # Retained for audit + regression testing
    regime: Optional[RegimeContext] = None
    session_config_hash: str = ""


# ---------------------------------------------------------------------------
# Filter registry (P1, P2)
# ---------------------------------------------------------------------------

FilterFn = Callable[[SessionConfig, "OrContext", RegimeContext], Optional[str]]
"""A filter is a pure function returning None (pass) or a string reason (skip).

Registered filters are applied in a fixed order by evaluate_session().
Adding a filter = one new function + one registry entry. That's it.
"""


@dataclass(frozen=True)
class OrContext:
    """The OR bars + ATR + slope, packaged for filters."""
    session_open_utc: pd.Timestamp
    or_close_utc: pd.Timestamp
    or_high: float
    or_low: float
    or_range: float
    atr_at_close: float
    slope_at_close: float
    or_bars_df: pd.DataFrame  # for filters that need bar-level detail


def filter_or_atr(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Optional[str]:
    """Per-session OR/ATR gates. Explicit — no cross-session default fallback.

    This replaces v7's dispatch_orb.py:528 (which fell through to default 2.0
    for NY/ASIA — the source of today's divergence bug).
    """
    ratio = ctx.or_range / ctx.atr_at_close if ctx.atr_at_close > 0 else 0

    if cfg.or_atr_max is not None and ratio > cfg.or_atr_max:
        return f"OR/ATR {ratio:.2f} > max {cfg.or_atr_max}"

    if cfg.or_atr_min is not None and ratio < cfg.or_atr_min:
        return f"OR/ATR {ratio:.2f} < min {cfg.or_atr_min}"

    if cfg.or_atr_deadzone is not None:
        lo, hi = cfg.or_atr_deadzone
        if lo <= ratio <= hi:
            return f"OR/ATR {ratio:.2f} in dead zone [{lo}, {hi}]"

    return None


def filter_trend(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Optional[str]:
    """Skip on flat trend if config requires trend."""
    if cfg.require_trend and ctx.slope_at_close == 0:
        return "trend flat"
    return None


def filter_news_stand_down(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Optional[str]:
    """Skip session if OR bars overlap a MAJOR_NEWS release window ONLY.

    London fix windows do NOT invalidate an OR — they're handled at entry
    time (per v7 dispatch behavior). This filter is session-level.

    v7 parity: matches dispatch_orb.py:468 (Box 2 news gate). Fix
    stand-down happens in the breakout-watch loop, not here.
    """
    try:
        from stand_down import _load_calendar, MAJOR_NEWS, NEWS_BUFFER_MINUTES
    except ImportError:
        return None  # graceful in isolation tests

    import pandas as pd
    cal = _load_calendar()
    if cal.empty:
        return None
    relevant = cal[cal["event"].isin(MAJOR_NEWS)]
    buf = pd.Timedelta(minutes=NEWS_BUFFER_MINUTES)
    for _, ev in relevant.iterrows():
        ev_ts = pd.Timestamp(ev["ts_utc"])
        if ev_ts.tz is None:
            ev_ts = ev_ts.tz_localize("UTC")
        if (ev_ts + buf >= ctx.session_open_utc) and (ev_ts - buf <= ctx.or_close_utc):
            return f"news:{ev['event']}@{ev_ts.strftime('%H:%M')}"
    return None


def filter_vol_ratio(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Optional[str]:
    """Skip PLAN if OR-window volume ratio below threshold (shadow candidate).

    Currently in shadow (vol_ratio_ge_1_0). Ships as v8 filter only if
    n>=100 shadow decisions confirm edge. Meanwhile, keeps returning None
    if threshold unset in cfg.
    """
    threshold = getattr(cfg, "min_or_win_vol_ratio", None)
    if threshold is None:
        return None
    if regime.or_win_vol_ratio is None:
        return None  # data unavailable, don't apply
    if regime.or_win_vol_ratio < threshold:
        return f"or_win_vol_ratio {regime.or_win_vol_ratio:.2f} < {threshold}"
    return None


def filter_prior_day_range(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Optional[str]:
    """Skip PLAN if prior-day GC range exceeded threshold (whipsaw filter).

    Shadow candidate registered 2026-07-13 in shadow_candidates_batch.md.
    Ships as v8 filter only after n>=100 shadow evidence.
    Ratio for eventual ship gate is per SessionConfig.max_prior_day_range.
    """
    threshold = getattr(cfg, "max_prior_day_range", None)
    if threshold is None:
        return None
    if regime.prior_day_range is None:
        return None
    if regime.prior_day_range > threshold:
        return f"prior_day_range {regime.prior_day_range:.1f} > max {threshold}"
    return None


def filter_prior_day_nr7_lon(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Optional[str]:
    """Crabel Ch 28 canonical: LON only when prior day was narrowest of last 7.
    Pre-registered 2026-07-13T16:00 as v8 shadow candidate. No-op until
    cfg.require_prior_nr7=True flipped.
    """
    if not getattr(cfg, "require_prior_nr7", False):
        return None
    if cfg.name != "LON":
        return None  # LON-only per pre-reg
    if regime.prior_day_range_class is None:
        return None
    if regime.prior_day_range_class != "NR7":
        return f"prior_day_range_class={regime.prior_day_range_class} != NR7 (Crabel LON gate)"
    return None


def filter_lon_short_only(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Optional[str]:
    """Task 7 finding: 7 of 8 LON backtest trades were SHORT. Skip LONG entries.
    Pre-registered 2026-07-13T16:00. No-op until cfg.lon_short_only=True.
    """
    if not getattr(cfg, "lon_short_only", False):
        return None
    if cfg.name != "LON":
        return None
    if ctx.slope_at_close > 0:  # LONG bias
        return f"lon_short_only: slope {ctx.slope_at_close:.2f} > 0"
    return None


def filter_crabel_3day_pattern(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Optional[str]:
    """Crabel Ch 28: allowlist the high-probability 3-day patterns for gold ORB.
    Pre-registered 2026-07-13T16:00. No-op until cfg.crabel_3day_whitelist set.
    Suggested whitelist per findings doc: {"+--", "-++", "+-+", "++-", "--+"}.
    """
    whitelist = getattr(cfg, "crabel_3day_whitelist", None)
    if not whitelist:
        return None
    if regime.three_day_pattern is None:
        return None
    if regime.three_day_pattern not in whitelist:
        return f"3day_pattern {regime.three_day_pattern} not in Crabel whitelist"
    return None


def filter_gap_after_down_day(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Optional[str]:
    """Skip LONG PLAN if prior day closed sharply lower (dead-cat bounce filter).

    Shadow candidate registered 2026-07-13 in shadow_candidates_batch.md.
    Applies only to LONG direction bias (checked via slope sign).
    """
    threshold = getattr(cfg, "gap_after_down_day_threshold", None)
    if threshold is None:
        return None
    if regime.prior_day_close_change is None:
        return None
    # Only relevant when we'd take LONG (slope > 0)
    if ctx.slope_at_close <= 0:
        return None
    if regime.prior_day_close_change <= threshold:
        return f"prior_day_close_change {regime.prior_day_close_change:.1f} <= {threshold}"
    return None


REGISTERED_FILTERS: tuple[FilterFn, ...] = (
    filter_or_atr,
    filter_trend,
    filter_news_stand_down,
    filter_vol_ratio,
    filter_prior_day_range,
    filter_gap_after_down_day,
    # Crabel Ch 28 candidates (all no-op until SessionConfig flag flipped):
    filter_prior_day_nr7_lon,
    filter_lon_short_only,
    filter_crabel_3day_pattern,
    # London fix filter is entry-level (per breakout), not session-level;
    # handled in dispatch/backtest execution layer.
    # Break-even-stop-at-60min (Crabel Ch 2) is execution-level,
    # requires trajectory tracker; deferred.
)


# ---------------------------------------------------------------------------
# Main entry point (P1, P4)
# ---------------------------------------------------------------------------

def evaluate_session(cfg: SessionConfig, ctx: OrContext, regime: RegimeContext) -> Decision:
    """Compute the strategy's decision for one session's OR.

    Called by:
      - Backtest engine (v8 replacement for edge_session_orb_v7_final.run_orb_v7)
      - Dispatcher (v8 replacement for dispatch_orb.dispatch_orb_alerts's inner loop)
      - Shadow tracker (v8 replacement for scripts/shadow_orb_tracker.py)

    All three call the SAME code. Divergence impossible.
    """
    reasons = tuple(r for f in REGISTERED_FILTERS if (r := f(cfg, ctx, regime)) is not None)

    # Direction from slope
    if ctx.slope_at_close > 0:
        direction = Direction.LONG
    elif ctx.slope_at_close < 0:
        direction = Direction.SHORT
    else:
        direction = Direction.FLAT

    # Geometry — only relevant if we'd take
    if not reasons:
        if cfg.stop_mode == "fixed":
            stop_dist = cfg.fixed_stop_dollars or 0.0
        else:
            stop_dist = ctx.or_range
        if cfg.target_mode == "stop_x_tp":
            target_dist = cfg.tp_mult * stop_dist
        else:
            target_dist = cfg.tp_mult * ctx.or_range

        if direction == Direction.LONG:
            entry = ctx.or_high
            target = entry + target_dist
            stop = entry - stop_dist
        elif direction == Direction.SHORT:
            entry = ctx.or_low
            target = entry - target_dist
            stop = entry + stop_dist
        else:
            entry = target = stop = None
    else:
        entry = target = stop = None

    return Decision(
        ts_recorded_utc=pd.Timestamp.now(tz="UTC"),
        version=VERSION,
        session=cfg.name,
        or_open_utc=ctx.session_open_utc,
        or_close_utc=ctx.or_close_utc,
        or_high=ctx.or_high,
        or_low=ctx.or_low,
        or_range=ctx.or_range,
        atr=ctx.atr_at_close,
        would_take=(not reasons and direction != Direction.FLAT),
        would_skip_reasons=reasons,
        direction=direction,
        entry_price=entry,
        target_price=target,
        stop_price=stop,
        regime=regime,
        session_config_hash="TODO-hash-cfg-here",
    )


# ---------------------------------------------------------------------------
# Session configs — Phase 8.3 ports these from v7 with explicit intent
# ---------------------------------------------------------------------------

# Path Y config (matches current live behavior). Ships when Phase 8.3 completes.
SESSION_CONFIGS_V8_INITIAL = {
    "LON": SessionConfig(
        name="LON",
        or_atr_max=2.0,
        stop_mode="fixed",
        fixed_stop_dollars=13.0,
        target_mode="stop_x_tp",
        tp_mult=1.5,
    ),
    "NY": SessionConfig(
        name="NY",
        or_atr_max=2.0,  # Path Y: matches live's actual behavior (no min gate)
        stop_mode="or_range",
        target_mode="or_range",
        tp_mult=1.5,
    ),
    "ASIA": SessionConfig(
        name="ASIA",
        or_atr_max=2.0,  # Path Y: matches live (no deadzone)
        stop_mode="or_range",
        target_mode="or_range",
        tp_mult=1.5,
    ),
}
