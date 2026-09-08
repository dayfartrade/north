"""Two v1 slicing analyses following up on today's distribution audit.

1. v1 by year and rolling 2-year window.
   Does v1's edge hold in the recent (high-ATR, high-price) regime specifically?

2. v1 performance by M20 percentile bucket.
   The 2026-08-24 LONG loser had M20 at the 100th percentile of the backtest
   sample. 4 of 6 live signals have M20 above the 85th percentile. Is v1
   systematically worse at extreme M20 in the historical sample?

No pre-reg, post-hoc slicing. Diagnostic only.

Usage:
  python scripts/v1_regime_and_m20_slices.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util
spec = importlib.util.spec_from_file_location("far", str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)


def run_v1_backtest() -> list[dict]:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-07-01", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    df = far.build_signals(daily, ry)
    df = df[(df.index >= start) & (df.index <= end)]
    weeks = far.week_indices(df)

    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        if sig["direction"] == "FLAT": continue
        if pd.isna(sig["ATR"]) or pd.isna(sig["M60"]): continue
        entry = float(df.loc[mon]["open"]); atr = float(sig["ATR"])
        if atr <= 0: continue
        if sig["direction"] == "LONG":
            stop = entry - far.STOP_ATR_MULT * atr
        else:
            stop = entry + far.STOP_ATR_MULT * atr
        r = far.simulate_week(df.loc[mon:fri], mon, fri, sig["direction"], entry, stop)
        if not r: continue
        trades.append({
            "signal_date": signal_date,
            "year": signal_date.year,
            "direction": sig["direction"],
            "M20_pct": float(sig["M20"]) * 100,
            "M60_pct": float(sig["M60"]) * 100,
            "RY_chg": float(sig["RY_chg"]),
            "ATR": atr,
            "price": entry,
            "net": r["net"],
            "ret": r["net"] / (entry * far.CONTRACT_SIZE),
        })
    return trades


def sharpe(returns: np.ndarray) -> float:
    if len(returns) < 2: return float("nan")
    m = returns.mean(); s = returns.std(ddof=1)
    return (m / s) * np.sqrt(52) if s > 0 else 0.0


def print_by_year(trades: list[dict]):
    print("\n=== v1 performance by calendar year ===")
    print(f"  {'year':<6} {'n':>4}  {'WR':>6}  {'mean$':>8}  {'total$':>10}  {'Sharpe':>7}")
    df = pd.DataFrame(trades)
    for y, grp in df.groupby("year"):
        n = len(grp)
        wr = (grp["net"] > 0).mean()
        mean = grp["net"].mean(); total = grp["net"].sum()
        sh = sharpe(grp["ret"].values)
        print(f"  {y:<6} {n:>4}  {wr*100:>5.1f}%  ${mean:>7,.0f}  ${total:>9,.0f}  {sh:>7.2f}")

    print("\n=== v1 rolling 2-year window Sharpe ===")
    all_years = sorted(df["year"].unique())
    print(f"  {'window':<12} {'n':>4}  {'total$':>10}  {'Sharpe':>7}")
    for i in range(len(all_years) - 1):
        y_start, y_end = all_years[i], all_years[i+1]
        grp = df[(df["year"] >= y_start) & (df["year"] <= y_end)]
        if len(grp) == 0: continue
        n = len(grp); total = grp["net"].sum()
        sh = sharpe(grp["ret"].values)
        print(f"  {y_start}-{y_end}    {n:>4}  ${total:>9,.0f}  {sh:>7.2f}")


def print_by_m20_bucket(trades: list[dict]):
    print("\n=== v1 performance by M20 percentile bucket ===")
    df = pd.DataFrame(trades)
    # Split LONGs and SHORTs separately since M20 has opposite meaning
    for direction, grp in df.groupby("direction"):
        print(f"\n  --- {direction} trades (n={len(grp)}) ---")
        # For LONG, high M20 = strong recent up-momentum; for SHORT, low M20 = strong recent down
        if direction == "LONG":
            # bucket by M20 pct: low, mid-low, mid, mid-high, high
            grp = grp.copy()
            grp["m20_bucket"] = pd.qcut(grp["M20_pct"], 5, labels=["Q1_low", "Q2", "Q3", "Q4", "Q5_high"])
        else:
            grp = grp.copy()
            grp["m20_bucket"] = pd.qcut(grp["M20_pct"], 5, labels=["Q1_low", "Q2", "Q3", "Q4", "Q5_high"])
        print(f"  {'bucket':<10} {'n':>4}  {'M20 range':<20}  {'WR':>6}  {'mean$':>8}  {'total$':>10}  {'Sharpe':>7}")
        for b, sub in grp.groupby("m20_bucket", observed=True):
            n = len(sub)
            wr = (sub["net"] > 0).mean()
            m = sub["net"].mean(); t = sub["net"].sum()
            sh = sharpe(sub["ret"].values)
            m20_min = sub["M20_pct"].min(); m20_max = sub["M20_pct"].max()
            print(f"  {str(b):<10} {n:>4}  {m20_min:>7.2f}% to {m20_max:>7.2f}%  "
                  f"{wr*100:>5.1f}%  ${m:>7,.0f}  ${t:>9,.0f}  {sh:>7.2f}")


def print_extreme_m20(trades: list[dict]):
    print("\n=== v1 performance at EXTREME M20 (top/bottom 10% of same-direction distribution) ===")
    df = pd.DataFrame(trades)
    for direction, grp in df.groupby("direction"):
        n = len(grp)
        if direction == "LONG":
            threshold_hi = grp["M20_pct"].quantile(0.90)
            extreme = grp[grp["M20_pct"] >= threshold_hi]
            label = f"LONG with M20 >= {threshold_hi:.2f}% (top 10% of LONG signals)"
        else:
            threshold_lo = grp["M20_pct"].quantile(0.10)
            extreme = grp[grp["M20_pct"] <= threshold_lo]
            label = f"SHORT with M20 <= {threshold_lo:.2f}% (bottom 10% of SHORT signals)"
        n_ex = len(extreme)
        wr_ex = (extreme["net"] > 0).mean() if n_ex > 0 else float("nan")
        total_ex = extreme["net"].sum() if n_ex > 0 else 0
        sh_ex = sharpe(extreme["ret"].values) if n_ex > 1 else float("nan")

        # Compare to non-extreme same direction
        non_extreme = grp.drop(extreme.index)
        n_ne = len(non_extreme)
        wr_ne = (non_extreme["net"] > 0).mean() if n_ne > 0 else float("nan")
        total_ne = non_extreme["net"].sum() if n_ne > 0 else 0
        sh_ne = sharpe(non_extreme["ret"].values) if n_ne > 1 else float("nan")

        print(f"\n  {label}")
        print(f"    extreme     : n={n_ex}  WR={wr_ex*100:>4.1f}%  total=${total_ex:>9,.0f}  Sharpe={sh_ex:>5.2f}")
        print(f"    non-extreme : n={n_ne}  WR={wr_ne*100:>4.1f}%  total=${total_ne:>9,.0f}  Sharpe={sh_ne:>5.2f}")


def main():
    trades = run_v1_backtest()
    print(f"Loaded v1 trades: n={len(trades)}")
    print_by_year(trades)
    print_by_m20_bucket(trades)
    print_extreme_m20(trades)


if __name__ == "__main__":
    main()
