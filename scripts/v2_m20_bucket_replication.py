"""v2 M20 percentile bucket replication check.

Direct replication of 2026-09-08 v1 M20 bucket analysis, but on the v2
DXY-confirmed subset only. Question: does the "top-quintile M20 LONGs
have negative Sharpe" pattern hold when v2's DXY filter is also applied,
or does the DXY filter already remove the bad trades?

This is a replication check, not a new discovery. Design is fixed from
the v1 version (same 5-quintile bucketing, same directional split).

Usage:
  python scripts/v2_m20_bucket_replication.py
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

DXY_PATH = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"


def run_v2_backtest() -> list[dict]:
    """v2 = v1 with DXY-confirmation filter."""
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-07-01", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    df = far.build_signals(daily, ry)
    df = df[(df.index >= start) & (df.index <= end)]

    dxy = far.load_macro_series(DXY_PATH, "dxy")
    dxy_daily = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                              method="ffill")
    dxy_daily.index = df.index
    df["DXY_chg"] = dxy_daily.pct_change(far.RY_LAG) * 100

    weeks = far.week_indices(df)
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        v1_dir = sig["direction"]
        if v1_dir == "FLAT": continue
        if pd.isna(sig["ATR"]) or pd.isna(sig["M60"]) or pd.isna(sig["DXY_chg"]):
            continue

        dxy_chg = float(sig["DXY_chg"])
        if v1_dir == "LONG" and dxy_chg < 0: v2_dir = "LONG"
        elif v1_dir == "SHORT" and dxy_chg > 0: v2_dir = "SHORT"
        else: continue  # v2-skipped

        entry = float(df.loc[mon]["open"]); atr = float(sig["ATR"])
        if atr <= 0: continue
        stop = entry - far.STOP_ATR_MULT * atr if v2_dir == "LONG" else entry + far.STOP_ATR_MULT * atr
        r = far.simulate_week(df.loc[mon:fri], mon, fri, v2_dir, entry, stop)
        if not r: continue
        trades.append({
            "signal_date": signal_date,
            "direction": v2_dir,
            "M20_pct": float(sig["M20"]) * 100,
            "M60_pct": float(sig["M60"]) * 100,
            "DXY_chg_pct": dxy_chg,
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


def print_by_m20_bucket(trades: list[dict], variant: str):
    print(f"\n=== {variant} M20 percentile bucket ===")
    df = pd.DataFrame(trades)
    for direction, grp in df.groupby("direction"):
        print(f"\n  --- {direction} trades (n={len(grp)}) ---")
        grp = grp.copy()
        grp["m20_bucket"] = pd.qcut(grp["M20_pct"], 5,
                                      labels=["Q1_low", "Q2", "Q3", "Q4", "Q5_high"])
        print(f"  {'bucket':<10} {'n':>4}  {'M20 range':<20}  {'WR':>6}  {'mean$':>8}  {'total$':>10}  {'Sharpe':>7}")
        for b, sub in grp.groupby("m20_bucket", observed=True):
            n = len(sub); wr = (sub["net"] > 0).mean()
            m = sub["net"].mean(); t = sub["net"].sum()
            sh = sharpe(sub["ret"].values)
            m20_min = sub["M20_pct"].min(); m20_max = sub["M20_pct"].max()
            print(f"  {str(b):<10} {n:>4}  {m20_min:>7.2f}% to {m20_max:>7.2f}%  "
                  f"{wr*100:>5.1f}%  ${m:>7,.0f}  ${t:>9,.0f}  {sh:>7.2f}")


def print_extreme_m20(trades: list[dict], variant: str):
    print(f"\n=== {variant} extreme M20 (top 10% LONG / bottom 10% SHORT) ===")
    df = pd.DataFrame(trades)
    for direction, grp in df.groupby("direction"):
        if direction == "LONG":
            thr = grp["M20_pct"].quantile(0.90)
            extreme = grp[grp["M20_pct"] >= thr]
            label = f"LONG with M20 >= {thr:.2f}% (top 10% of LONG signals)"
        else:
            thr = grp["M20_pct"].quantile(0.10)
            extreme = grp[grp["M20_pct"] <= thr]
            label = f"SHORT with M20 <= {thr:.2f}% (bottom 10% of SHORT signals)"
        non_ex = grp.drop(extreme.index)
        print(f"\n  {label}")
        print(f"    extreme     : n={len(extreme)}  WR={(extreme['net']>0).mean()*100:>4.1f}%  "
              f"total=${extreme['net'].sum():>9,.0f}  Sharpe={sharpe(extreme['ret'].values):>5.2f}")
        print(f"    non-extreme : n={len(non_ex)}  WR={(non_ex['net']>0).mean()*100:>4.1f}%  "
              f"total=${non_ex['net'].sum():>9,.0f}  Sharpe={sharpe(non_ex['ret'].values):>5.2f}")


def main():
    trades = run_v2_backtest()
    print(f"v2 trades: n={len(trades)}")
    print_by_m20_bucket(trades, "v2 (DXY-confirmed)")
    print_extreme_m20(trades, "v2 (DXY-confirmed)")


if __name__ == "__main__":
    main()
