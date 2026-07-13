"""OOS validation of real_yield_gt_2_2 across 20+ years of GC + real yield data.

Per quant framework rule 3: "OOS test on pre-regime data. If real yield truly
conditions your edge, it should show signal in periods BEFORE it obviously
mattered." This script tests whether high-real-yield days systematically
produce lower forward gold returns across the full FRED history.

Read-only. No live impact.
"""
from __future__ import annotations

import csv
import statistics
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_YIELD = ROOT / "data/macro/real_yield_10y__DFII10.csv"
GC_1D = ROOT / "data/gc/GC_1d.csv"


def load_series(path: Path, key_col: str = "date", val_col: str = "value") -> dict[str, float]:
    out: dict[str, float] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                out[row[key_col][:10]] = float(row[val_col])
            except (ValueError, KeyError):
                continue
    return out


def load_gc_close() -> dict[str, float]:
    out: dict[str, float] = {}
    with open(GC_1D, newline="") as f:
        for row in csv.DictReader(f):
            try:
                out[row["ts"][:10]] = float(row["close"])
            except (ValueError, KeyError):
                continue
    return out


def business_days(sorted_dates: list[str], anchor: str, n: int) -> str | None:
    """Return the date n business days AFTER anchor (approx — uses whatever dates exist)."""
    try:
        idx = sorted_dates.index(anchor)
    except ValueError:
        return None
    if idx + n < len(sorted_dates):
        return sorted_dates[idx + n]
    return None


def forward_return(gc: dict[str, float], sorted_dates: list[str], d: str, horizon_days: int) -> float | None:
    fwd = business_days(sorted_dates, d, horizon_days)
    if fwd is None or d not in gc:
        return None
    return (gc[fwd] - gc[d]) / gc[d]


def bucket_stats(rets: list[float]) -> dict:
    if not rets:
        return {"n": 0}
    m = statistics.mean(rets)
    sd = statistics.stdev(rets) if len(rets) > 1 else 0.0
    positive = sum(1 for r in rets if r > 0)
    # t-stat approx for mean != 0
    t = m / (sd / (len(rets) ** 0.5)) if sd > 0 else 0
    return {"n": len(rets), "mean_pct": 100 * m, "sd_pct": 100 * sd, "pos_pct": 100 * positive / len(rets), "t": t}


def main() -> None:
    ry = load_series(REAL_YIELD)
    gc = load_gc_close()
    sorted_gc_dates = sorted(gc.keys())
    print(f"real yield series: {len(ry)} days ({min(ry) if ry else '?'} to {max(ry) if ry else '?'})")
    print(f"GC close series:   {len(gc)} days ({min(gc) if gc else '?'} to {max(gc) if gc else '?'})")

    # For each GC trading day where we have real yield, bucket by regime + measure fwd N-day return.
    HORIZONS = [1, 5, 10, 20]  # 1 day, 1 week, 2 weeks, 1 month
    THRESHOLDS = [1.5, 2.0, 2.2, 2.5]

    print()
    print("=" * 80)
    print("Forward GC LONG return conditional on real_yield regime (long-side hypothesis test)")
    print("=" * 80)

    for thresh in THRESHOLDS:
        print(f"\n  Threshold: real_yield >= {thresh}")
        print(f"    horizon      HIGH (ry>=t)                                LOW (ry<t)")
        for h in HORIZONS:
            high = []; low = []
            for d in sorted_gc_dates:
                if d not in ry: continue
                r = forward_return(gc, sorted_gc_dates, d, h)
                if r is None: continue
                (high if ry[d] >= thresh else low).append(r)
            hi_s = bucket_stats(high)
            lo_s = bucket_stats(low)
            hi_str = f"n={hi_s['n']:4d}  mean={hi_s.get('mean_pct',0):+.3f}%  pos={hi_s.get('pos_pct',0):.0f}%  t={hi_s.get('t',0):+.2f}" if hi_s['n'] else "n=0"
            lo_str = f"n={lo_s['n']:4d}  mean={lo_s.get('mean_pct',0):+.3f}%  pos={lo_s.get('pos_pct',0):.0f}%  t={lo_s.get('t',0):+.2f}" if lo_s['n'] else "n=0"
            print(f"    {h}d fwd:   {hi_str}   |   {lo_str}")

    # Focus: 2003-2007 (pre-regime era with lots of ry>=2.2 days) as pure OOS
    print()
    print("=" * 80)
    print("OOS regime era: 2003-2007 (35% ry>=2.2 days per prior analysis)")
    print("=" * 80)
    for h in HORIZONS:
        high = []; low = []
        for d in sorted_gc_dates:
            if d < "2003-01-01" or d >= "2008-01-01": continue
            if d not in ry: continue
            r = forward_return(gc, sorted_gc_dates, d, h)
            if r is None: continue
            (high if ry[d] >= 2.2 else low).append(r)
        hi_s = bucket_stats(high)
        lo_s = bucket_stats(low)
        print(f"  {h}d fwd:   ry>=2.2 n={hi_s['n']:4d} mean={hi_s.get('mean_pct',0):+.3f}% t={hi_s.get('t',0):+.2f}   |   ry<2.2 n={lo_s['n']:4d} mean={lo_s.get('mean_pct',0):+.3f}% t={lo_s.get('t',0):+.2f}")

    # 2022-2024 (post-QE, real yields rebuilt)
    print()
    print("=" * 80)
    print("Recent regime: 2022-2024 (real yields normalized after QE)")
    print("=" * 80)
    for h in HORIZONS:
        high = []; low = []
        for d in sorted_gc_dates:
            if d < "2022-01-01" or d >= "2025-01-01": continue
            if d not in ry: continue
            r = forward_return(gc, sorted_gc_dates, d, h)
            if r is None: continue
            (high if ry[d] >= 2.0 else low).append(r)  # lower threshold for this era
        hi_s = bucket_stats(high)
        lo_s = bucket_stats(low)
        print(f"  {h}d fwd:   ry>=2.0 n={hi_s['n']:4d} mean={hi_s.get('mean_pct',0):+.3f}% t={hi_s.get('t',0):+.2f}   |   ry<2.0 n={lo_s['n']:4d} mean={lo_s.get('mean_pct',0):+.3f}% t={lo_s.get('t',0):+.2f}")


if __name__ == "__main__":
    main()
