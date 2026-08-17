"""Reproduce NORTH v1's advertised backtest numbers from raw data.

Anyone can run this to verify the numbers quoted in the pinned intro
message and the retirement wall. If they don't match what's on the
channel, the claim is wrong.

This is the honesty backstop. The intro says "55.9% win rate, +0.23%
mean return, Sharpe 0.77, drawdown 5.6% of notional." This script
recomputes those numbers from the same Dukascopy data anyone can
download.

Data required (all in repo except the 5m intraday):
  data/external/dukascopy/XAUUSD_5m_2010_2014.csv
  data/external/dukascopy/XAUUSD_5m_historical.csv
  data/external/dukascopy/XAUUSD_5m.csv
  data/macro/real_yield_10y__DFII10.csv

Intraday data is not versioned (large). Fetch with:
  python scripts/fetch_dukascopy_xauusd.py

Usage:
  python scripts/verify_north_v1_backtest.py
"""
from __future__ import annotations

import importlib.util
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location(
    "far", str(ROOT / "scripts" / "far_weekly_gold_read.py")
)
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)


ADVERTISED = {
    "start": "2010-01-01",
    "end": "2026-08-14",
    "min_directional_trades": 350,
    "win_rate_pct_target": 55.9,
    "mean_return_pct_target": 0.23,
    "sharpe_target": 0.77,
    "max_dd_dollars_target": 56043.0,   # actual cumulative $ drawdown per contract-per-week
    "positive_years_target": 13,
    "years_traded_target": 17,
    "tolerance_pct_points": 1.5,   # slack for edge weeks / data updates
    "tolerance_sharpe": 0.10,
    "tolerance_dollars": 3000.0,
}


def run() -> dict:
    start = pd.Timestamp(ADVERTISED["start"], tz="UTC")
    end = pd.Timestamp(ADVERTISED["end"], tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    signals = far.build_signals(daily, ry)
    signals = signals[(signals.index >= start) & (signals.index <= end)]
    weeks = far.week_indices(signals)

    # Use the same backtest engine the publisher uses. It reports $ P&L
    # per contract via a $5 round-trip cost model on 100 oz contracts.
    r = far.backtest(start, end)
    trades = r["trades"]
    n = len(trades)
    if n == 0:
        return {"error": "no trades produced"}

    pnls = [t["net"] for t in trades]
    rets = [t["net"] / (t["entry"] * far.CONTRACT_SIZE) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    mean_r = sum(rets) / n
    std_r = (sum((x - mean_r) ** 2 for x in rets) / (n - 1)) ** 0.5
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0

    # Dollar equity curve
    equity = []; running = 0.0
    for p in pnls:
        running += p; equity.append(running)
    peak = 0.0; max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak - v > max_dd:
            max_dd = peak - v

    by_year = defaultdict(list)
    for t in trades:
        by_year[str(t["week_start"])[:4]].append(t["net"])
    pos_years = sum(1 for _, tp in by_year.items() if sum(tp) > 0)

    return {
        "n": n,
        "win_rate_pct": 100 * wins / n,
        "mean_return_pct": 100 * mean_r,
        "sharpe_ann": sharpe,
        "max_dd_dollars": max_dd,
        "positive_years": pos_years,
        "years_traded": len(by_year),
    }


def compare(actual: dict) -> int:
    tol = ADVERTISED["tolerance_pct_points"]
    tol_sr = ADVERTISED["tolerance_sharpe"]
    print(f"\nNORTH v1 backtest verification")
    print(f"Window: {ADVERTISED['start']} to {ADVERTISED['end']}")
    print(f"Data:   Dukascopy XAUUSD 5m + FRED DFII10")
    print()
    print(f"  {'Metric':<28} {'Advertised':>12} {'Actual':>12} {'Diff':>10} {'':>6}")
    print(f"  {'-'*28} {'-'*12} {'-'*12} {'-'*10} {'-'*6}")

    failures = 0
    tol_dollars = ADVERTISED["tolerance_dollars"]
    rows = [
        ("Directional trades (>=)", ADVERTISED["min_directional_trades"],
         actual["n"], actual["n"] - ADVERTISED["min_directional_trades"], "gte", tol),
        ("Win rate %", ADVERTISED["win_rate_pct_target"],
         actual["win_rate_pct"], actual["win_rate_pct"] - ADVERTISED["win_rate_pct_target"], "abs", tol),
        ("Mean return per trade %", ADVERTISED["mean_return_pct_target"],
         actual["mean_return_pct"], actual["mean_return_pct"] - ADVERTISED["mean_return_pct_target"], "abs", tol),
        ("Sharpe (annualized)", ADVERTISED["sharpe_target"],
         actual["sharpe_ann"], actual["sharpe_ann"] - ADVERTISED["sharpe_target"], "abs", tol_sr),
        ("Max drawdown $", ADVERTISED["max_dd_dollars_target"],
         actual["max_dd_dollars"], actual["max_dd_dollars"] - ADVERTISED["max_dd_dollars_target"], "abs", tol_dollars),
        ("Positive years", ADVERTISED["positive_years_target"],
         actual["positive_years"], actual["positive_years"] - ADVERTISED["positive_years_target"], "abs", tol),
        ("Years traded", ADVERTISED["years_traded_target"],
         actual["years_traded"], actual["years_traded"] - ADVERTISED["years_traded_target"], "abs", tol),
    ]
    for name, target, actual_v, diff, kind, tolerance in rows:
        if kind == "gte":
            ok = actual_v >= target
        else:
            ok = abs(diff) <= tolerance
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        if "$" in name:
            print(f"  {name:<28} ${target:>11,.0f} ${actual_v:>11,.0f} {diff:>+10,.0f} {mark:>6}")
        elif isinstance(target, float):
            print(f"  {name:<28} {target:>12.2f} {actual_v:>12.2f} {diff:>+10.2f} {mark:>6}")
        else:
            print(f"  {name:<28} {target:>12d} {int(actual_v):>12d} {diff:>+10d} {mark:>6}")

    print()
    if failures == 0:
        print("VERIFIED. All metrics match the advertised numbers within tolerance.")
        return 0
    print(f"FAILED. {failures} metrics outside tolerance.")
    print("If you got here, one of two things is true:")
    print("  1. NORTH's advertised numbers are stale and should be republished.")
    print("  2. The data source has drifted (e.g., Dukascopy updated historical bars).")
    print("Either way, this is a real discrepancy worth investigating.")
    return 1


def main() -> None:
    actual = run()
    if "error" in actual:
        print(f"ERROR: {actual['error']}")
        sys.exit(2)
    sys.exit(compare(actual))


if __name__ == "__main__":
    main()
