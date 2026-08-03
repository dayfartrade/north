"""Shared pure-function helpers for read-only auto-trader analysis scripts.

Extracted 2026-07-31 after three scripts shipped the same helpers
independently:
  - scripts/trade_decomposition_2026_07_31.py
  - scripts/cost_model_calibration_2026_07_31.py
  - scripts/routed_vs_unrouted_2026_07_31.py

No I/O, no DB, no exceptions raised on bad input (defensive by design —
callers pass row dicts directly from psycopg fetches, so bad values must
degrade gracefully rather than crash the report).

Do NOT add live-trading dependencies here. This module is for the
analysis + reporting layer only; keep it importable from scripts/*
without dragging in auto_trader/, jobs/, or tg/ modules.
"""
from __future__ import annotations


def entry_slippage_bps(
    side: str | None,
    intended: float | None,
    actual: float | None,
) -> float | None:
    """Signed bps of adverse entry slippage.

    Positive = adverse (worse fill than intended).
    Negative = favorable (better fill than intended).

    - SHORT: adverse = actual < intended (sold cheaper). Return
      -(actual - intended) / intended * 10_000.
    - LONG:  adverse = actual > intended (bought pricier). Return
      (actual - intended) / intended * 10_000.
    - Returns None when inputs incomplete or intended <= 0.
    """
    if not intended or not actual or side not in ("long", "short"):
        return None
    if intended <= 0:
        return None
    if side == "short":
        return -(actual - intended) / intended * 10_000.0
    return (actual - intended) / intended * 10_000.0


def session_bucket(hour_utc: int) -> str:
    """4-bucket UTC session tag used across per-session analytics.

    Boundaries inclusive-left: [0,6)=asia, [6,12)=eu_am, [12,18)=us_am,
    [18,24)=us_pm. Matches perf_by_time_extended + auto_trader_leak_audit
    + trade_decomposition + cost_model_calibration conventions.
    """
    if 0 <= hour_utc < 6:
        return "asia"
    if 6 <= hour_utc < 12:
        return "eu_am"
    if 12 <= hour_utc < 18:
        return "us_am"
    return "us_pm"


def percentile(sorted_values: list[float], p: float) -> float:
    """Linear-interpolation percentile on a pre-sorted list.

    - Empty list returns 0.0 (caller decides interpretation)
    - Singleton returns its own value regardless of p
    - Otherwise: p in [0.0, 1.0]; standard interpolation between
      the two nearest data points.

    Matches numpy.percentile with method='linear'. Small enough to
    inline; extracted here to avoid re-implementing per-script.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)
