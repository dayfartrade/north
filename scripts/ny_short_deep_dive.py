"""Deep dive on the NY SHORT edge found in gold n=1018 deep_analysis_orb.

Questions:
  1. Is +$29,874 concentrated in a few outlier days, or evenly distributed?
  2. What does the trade-by-trade P&L distribution look like?
  3. Any temporal pattern — is edge growing, shrinking, stable?
  4. Cross-tab with day-of-week, ER band, OR/ATR ratio
  5. Bootstrap CI on the NY-SHORT mean
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TRADES = ROOT / "data" / "analysis_gold_trades.csv"


def bootstrap_ci(vals: list[float], n: int = 5000) -> tuple[float, float]:
    rng = random.Random(20260720)
    N = len(vals)
    means = []
    for _ in range(n):
        s = [vals[rng.randrange(N)] for _ in range(N)]
        means.append(sum(s) / N)
    means.sort()
    return means[int(0.025 * n)], means[int(0.975 * n)]


def main() -> None:
    df = pd.read_csv(TRADES)
    df["date"] = pd.to_datetime(df["date"])

    ny_short = df[(df["session"] == "NY") & (df["direction_fwd"] == "SHORT")].copy()
    print(f"=== NY-SHORT subset: n={len(ny_short)} ===")
    print(f"Date range: {ny_short['date'].min().date()} -> {ny_short['date'].max().date()}")
    print()

    # Distribution
    pnls = ny_short["pnl_forward"].values
    print(f"Total P&L         = ${pnls.sum():+,.0f}")
    print(f"Mean/trade        = ${pnls.mean():+,.2f}")
    print(f"Median/trade      = ${np.median(pnls):+,.2f}")
    print(f"Std dev           = ${pnls.std():,.2f}")
    print(f"Win rate          = {100*(pnls>0).mean():.1f}%")
    print()

    # Percentiles
    print("P&L percentiles:")
    for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        print(f"  p{p:2d}  = ${np.percentile(pnls, p):+,.2f}")
    print()

    # Top 10 winners + losers — how concentrated?
    sorted_pnl = np.sort(pnls)[::-1]
    top10 = sorted_pnl[:10]
    top20 = sorted_pnl[:20]
    print(f"Top 10 trades P&L  = ${top10.sum():+,.0f}  ({100*top10.sum()/pnls.sum():.1f}% of total)")
    print(f"Top 20 trades P&L  = ${top20.sum():+,.0f}  ({100*top20.sum()/pnls.sum():.1f}% of total)")
    print(f"Bot 10 trades P&L  = ${sorted_pnl[-10:].sum():+,.0f}")
    print()

    # Excluding top 10 — is there still edge?
    truncated_top = pnls[pnls < np.percentile(pnls, 99)]
    print(f"Excluding top 1%:  n={len(truncated_top)}  total=${truncated_top.sum():+,.0f}  mean=${truncated_top.mean():+,.2f}")
    truncated_5 = pnls[pnls < np.percentile(pnls, 95)]
    print(f"Excluding top 5%:  n={len(truncated_5)}  total=${truncated_5.sum():+,.0f}  mean=${truncated_5.mean():+,.2f}")
    print()

    # Bootstrap CI on the mean
    ci_lo, ci_hi = bootstrap_ci(pnls.tolist())
    print(f"Bootstrap 95% CI on mean = [${ci_lo:+,.2f}, ${ci_hi:+,.2f}]  clears zero: {ci_lo > 0}")
    print()

    # Temporal stability — quarterly buckets
    print("Quarterly P&L:")
    ny_short["quarter"] = ny_short["date"].dt.to_period("Q")
    q_stats = ny_short.groupby("quarter")["pnl_forward"].agg(["count", "sum", "mean"])
    for q, row in q_stats.iterrows():
        print(f"  {q}  n={int(row['count']):>3d}  total=${row['sum']:>+8,.0f}  mean=${row['mean']:>+7.2f}")
    print()

    # By day-of-week within NY SHORT
    print("NY-SHORT by day of week:")
    dow_stats = ny_short.groupby("dow")["pnl_forward"].agg(["count", "sum", "mean", lambda x: (x>0).mean()])
    dow_stats.columns = ["n", "total", "mean", "win_rate"]
    for dow in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
        if dow in dow_stats.index:
            r = dow_stats.loc[dow]
            print(f"  {dow}  n={int(r['n']):>3d}  total=${r['total']:>+8,.0f}  mean=${r['mean']:>+7.2f}  win={100*r['win_rate']:>4.1f}%")
    print()

    # By ER band
    print("NY-SHORT by ER band:")
    er_stats = ny_short.groupby("er_band")["pnl_forward"].agg(["count", "sum", "mean", lambda x: (x>0).mean()])
    er_stats.columns = ["n", "total", "mean", "win_rate"]
    for band in ["low", "mid", "high"]:
        if band in er_stats.index:
            r = er_stats.loc[band]
            print(f"  {band:6s}  n={int(r['n']):>3d}  total=${r['total']:>+8,.0f}  mean=${r['mean']:>+7.2f}  win={100*r['win_rate']:>4.1f}%")
    print()

    # Hour of day (all NY SHORT is roughly 13-20 UTC)
    print("NY-SHORT by hour UTC:")
    hr_stats = ny_short.groupby("hour_utc")["pnl_forward"].agg(["count", "sum", "mean"])
    hr_stats.columns = ["n", "total", "mean"]
    for h, r in hr_stats.iterrows():
        print(f"  {h:02d}:00  n={int(r['n']):>3d}  total=${r['total']:>+8,.0f}  mean=${r['mean']:>+7.2f}")
    print()

    # Cumulative equity curve — flat or growing?
    ny_short_sorted = ny_short.sort_values("date").copy()
    ny_short_sorted["cum_pnl"] = ny_short_sorted["pnl_forward"].cumsum()
    print(f"Cumulative P&L trajectory (every 20 trades):")
    for i in range(0, len(ny_short_sorted), 20):
        row = ny_short_sorted.iloc[i]
        print(f"  n={i+1:>3d} {row['date'].date()}  cum=${row['cum_pnl']:>+8,.0f}")
    print(f"  n={len(ny_short_sorted):>3d} {ny_short_sorted['date'].iloc[-1].date()}  cum=${ny_short_sorted['cum_pnl'].iloc[-1]:>+8,.0f}  FINAL")


if __name__ == "__main__":
    main()
