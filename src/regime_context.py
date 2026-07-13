"""RegimeContext builder — fetches macro data and constructs the immutable
RegimeContext snapshot passed to every v8 strategy call.

Single source for regime data lookup. Any filter that conditions on macro
imports its input from here, not from ad-hoc CSV reads.

Design:
  - Cache by (variable_name) — hot CSVs stay in memory across calls
  - Never fail; missing data returns None on that field
  - as_of_utc drives all lookups (last-value-on-or-before)
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

import pandas as pd

from strategy_engine import RegimeContext

ROOT = Path(__file__).resolve().parent.parent
_CACHE: dict[str, dict[str, float]] = {}


def _load_series(rel_path: str, value_col: str = "value", date_col: str = "date") -> dict[str, float]:
    """Load a daily FRED-style CSV into date-string → float dict. Cached."""
    if rel_path in _CACHE:
        return _CACHE[rel_path]
    fp = ROOT / rel_path
    out: dict[str, float] = {}
    if not fp.exists():
        _CACHE[rel_path] = out
        return out
    try:
        with open(fp, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    out[row[date_col][:10]] = float(row[value_col])
                except (ValueError, KeyError):
                    continue
    except Exception:
        pass
    _CACHE[rel_path] = out
    return out


def _lookup_le(series: dict[str, float], date_str: str) -> Optional[float]:
    """Last value on or before date_str. Returns None if no such value."""
    best = None
    for k in series:
        if k <= date_str and (best is None or k > best):
            best = k
    return series.get(best) if best else None


def _load_gc_daily() -> dict[str, tuple[float, float, float, float]]:
    """(open, high, low, close) by date."""
    key = "data/gc/GC_1d.csv"
    if key in _CACHE:
        return _CACHE[key]  # type: ignore
    fp = ROOT / key
    out: dict[str, tuple[float, float, float, float]] = {}
    if not fp.exists():
        _CACHE[key] = out  # type: ignore
        return out
    try:
        with open(fp, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    d = row["ts"][:10]
                    out[d] = (float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
                except (ValueError, KeyError):
                    continue
    except Exception:
        pass
    _CACHE[key] = out  # type: ignore
    return out


def _prior_day_stats(date_str: str) -> tuple[Optional[float], Optional[float]]:
    """Return (prior_day_range, prior_day_close_change)."""
    gc = _load_gc_daily()
    if not gc:
        return (None, None)
    prev_key = None
    for k in sorted(gc.keys()):
        if k < date_str:
            prev_key = k
        else:
            break
    if prev_key is None:
        return (None, None)
    _, hi, lo, prev_close = gc[prev_key]
    prev_range = hi - lo
    # Prior day close change: prev close vs 2-days-ago close
    prev_prev_key = None
    for k in sorted(gc.keys()):
        if k < prev_key:
            prev_prev_key = k
        else:
            break
    prev_change = None
    if prev_prev_key is not None:
        _, _, _, prev_prev_close = gc[prev_prev_key]
        prev_change = prev_close - prev_prev_close
    return (prev_range, prev_change)


def build_regime_context(as_of_utc: pd.Timestamp,
                          or_atr_ratio: Optional[float] = None,
                          or_win_vol_ratio: Optional[float] = None,
                          trend_slope: Optional[float] = None,
                          funding_annualized_pct: Optional[float] = None,
                          basis_pct: Optional[float] = None,
                          cot_mm_net_long: Optional[float] = None,
                          cot_pct_52w: Optional[float] = None) -> RegimeContext:
    """Construct a RegimeContext for the given timestamp.

    Bar-level context (or_atr_ratio, or_win_vol_ratio, trend_slope) and side
    channels (funding, basis, cot) are computed by the caller (dispatcher or
    backtest engine) and passed in. Macro fields (real yield, DXY, TNX) and
    prior-day GC stats are looked up here from local CSVs.
    """
    if as_of_utc.tz is None:
        as_of_utc = as_of_utc.tz_localize("UTC")
    date_str = as_of_utc.strftime("%Y-%m-%d")

    real_yield_10y = _lookup_le(_load_series("data/macro/real_yield_10y__DFII10.csv"), date_str)
    dxy = _lookup_le(_load_series("data/macro/dxy_proxy__DTWEXBGS.csv"), date_str)
    tnx = _lookup_le(_load_series("data/macro/tnx_10y__DGS10.csv"), date_str)

    prior_range, prior_close_change = _prior_day_stats(date_str)

    return RegimeContext(
        as_of_utc=as_of_utc,
        real_yield_10y=real_yield_10y,
        dxy=dxy,
        tnx=tnx,
        cot_mm_net_long=cot_mm_net_long,
        cot_pct_52w=cot_pct_52w,
        prior_day_range=prior_range,
        prior_day_close_change=prior_close_change,
        or_atr_ratio=or_atr_ratio,
        or_win_vol_ratio=or_win_vol_ratio,
        trend_slope=trend_slope,
        funding_annualized_pct=funding_annualized_pct,
        basis_pct=basis_pct,
    )


if __name__ == "__main__":
    # Quick sanity check
    now = pd.Timestamp.now(tz="UTC")
    ctx = build_regime_context(now)
    print(f"as_of: {ctx.as_of_utc}")
    print(f"real_yield_10y: {ctx.real_yield_10y}")
    print(f"dxy: {ctx.dxy}")
    print(f"tnx: {ctx.tnx}")
    print(f"prior_day_range: {ctx.prior_day_range}")
    print(f"prior_day_close_change: {ctx.prior_day_close_change}")
