"""Analyze v2's DXY filter: does it drop winners or losers relative to v1?

For each week where v1 was directional but v2 filtered to FLAT (DXY not
confirming), look up what v1's actual outcome would have been. Aggregate:
mean P&L of filtered weeks, win rate, best/worst.

If filtered weeks have MEAN P&L > 0 → v2 is throwing away winners.
If filtered weeks have MEAN P&L < 0 → v2 is correctly filtering losers.

Usage: python scripts/v1_vs_v2_filter_analysis.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec_v1 = importlib.util.spec_from_file_location("far", str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec_v1); spec_v1.loader.exec_module(far)

spec_v2 = importlib.util.spec_from_file_location("v2", str(ROOT / "scripts" / "far_weekly_v2_backtest.py"))
v2 = importlib.util.module_from_spec(spec_v2); spec_v2.loader.exec_module(v2)


def analyze(label, start, end):
    print(f"\n{'#'*70}\n# {label}: {start.date()} to {end.date()}\n{'#'*70}")
    r1 = far.backtest(start, end)
    r2 = v2.backtest_v2(start, end)
    v1_by_week = {t["week_start"]: t for t in r1["trades"]}
    v2_weeks = {t["week_start"] for t in r2["trades"]}
    filtered = [t for wk, t in v1_by_week.items() if wk not in v2_weeks]
    kept = [t for wk, t in v1_by_week.items() if wk in v2_weeks]
    def stats(trades):
        if not trades: return "n=0"
        n = len(trades); pnl = sum(t["net"] for t in trades)
        w = sum(1 for t in trades if t["net"]>0)
        return f"n={n}  total=${pnl:+,.0f}  mean=${pnl/n:+,.0f}  WR={100*w/n:.1f}%"
    print(f"v1 all:      {stats(list(v1_by_week.values()))}")
    print(f"v2 kept:     {stats(kept)}")
    print(f"v2 filtered: {stats(filtered)}  "
          f"({100*len(filtered)/max(1,len(v1_by_week)):.1f}% of v1)")
    return v1_by_week, kept, filtered


def main():
    analyze("FULL SAMPLE",
            pd.Timestamp("2010-01-01", tz="UTC"),
            pd.Timestamp("2026-07-20", tz="UTC"))
    analyze("TRAIN (design window)",
            pd.Timestamp("2010-01-01", tz="UTC"),
            pd.Timestamp("2017-12-31", tz="UTC"))
    analyze("OOS (post-design)",
            pd.Timestamp("2018-01-01", tz="UTC"),
            pd.Timestamp("2026-07-20", tz="UTC"))
    # Re-do the FULL for detailed printout
    v1_by_week, kept, filtered = analyze("FULL SAMPLE — DETAIL",
            pd.Timestamp("2010-01-01", tz="UTC"),
            pd.Timestamp("2026-07-20", tz="UTC"))

    print()
    def summary(label, trades):
        if not trades:
            print(f"\n{label}: no trades")
            return
        pnls = [t["net"] for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        n = len(trades)
        print(f"\n{label} (n={n}):")
        print(f"  Total P&L:    ${sum(pnls):+,.0f}")
        print(f"  Mean per wk:  ${sum(pnls)/n:+,.0f}")
        print(f"  Win rate:     {100*wins/n:.1f}%")
        print(f"  Best:         ${max(pnls):+,.0f}")
        print(f"  Worst:        ${min(pnls):+,.0f}")

    summary("KEPT by v2 filter (v1 and v2 agree)", kept)
    summary("FILTERED out by v2 (v1 traded, v2 said FLAT)", filtered)

    if filtered:
        f_pnls = [t["net"] for t in filtered]
        f_mean = sum(f_pnls) / len(f_pnls)
        print(f"\n{'='*70}")
        print("VERDICT:")
        if f_mean > 0:
            print(f"  Filtered weeks averaged ${f_mean:+,.0f} — v2 is DROPPING WINNERS.")
            print("  The DXY filter costs money on the filtered subset.")
        else:
            print(f"  Filtered weeks averaged ${f_mean:+,.0f} — v2 is CATCHING LOSERS.")
            print("  The DXY filter is doing legitimate work.")

        # Split by direction
        long_filt = [t for t in filtered if t["direction"] == "LONG"]
        short_filt = [t for t in filtered if t["direction"] == "SHORT"]
        for lbl, sub in [("LONG filtered", long_filt), ("SHORT filtered", short_filt)]:
            if sub:
                m = sum(t["net"] for t in sub) / len(sub)
                w = sum(1 for t in sub if t["net"] > 0)
                print(f"  {lbl}: n={len(sub)}, mean=${m:+,.0f}, WR={100*w/len(sub):.1f}%")


if __name__ == "__main__":
    main()
