"""Live vs backtest distribution audit for v1 signal components.

Pulls signal component values (M20_pct, M60_pct, RY_chg, ATR) from every
published call in data/far_weekly_calls.jsonl and compares distributions
to the backtest sample (2010-2026 daily bars at each Friday signal date).

Goal: are the market conditions we're firing (or not firing) in live
in-distribution with the backtest, or are we in a regime the backtest
didn't sample well?

N=live is small (~8 published calls to date). KS test won't be powerful.
This is a diagnostic snapshot, not a formal test.

Usage:
  python scripts/live_vs_backtest_signal_dist.py
"""
from __future__ import annotations

import json
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

CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"


def load_live_signals() -> pd.DataFrame:
    if not CALLS_LOG.exists():
        return pd.DataFrame()
    rows = []
    with open(CALLS_LOG) as f:
        for line in f:
            if not line.strip(): continue
            c = json.loads(line)
            sc = c.get("signal_components", {})
            rows.append({
                "signal_date": pd.Timestamp(c["signal_date_utc"]),
                "direction": c["direction"],
                "M20_pct": sc.get("M20_pct"),
                "M60_pct": sc.get("M60_pct"),
                "MA_above": sc.get("MA10_above_MA40"),
                "RY_chg_bps": sc.get("RY_chg_20d_bps"),
                "ATR": c.get("atr_20d"),
                "price": c.get("current_price"),
            })
    return pd.DataFrame(rows).sort_values("signal_date").reset_index(drop=True)


def load_backtest_signals() -> pd.DataFrame:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-07-01", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    df = far.build_signals(daily, ry)
    df = df[(df.index >= start) & (df.index <= end)].dropna(subset=["M20", "M60", "RY_chg"])
    weeks = far.week_indices(df)
    signal_dates = [sd for sd, _, _ in weeks if sd in df.index]
    bt = df.loc[signal_dates].copy()
    bt["M20_pct"] = bt["M20"] * 100
    bt["M60_pct"] = bt["M60"] * 100
    bt["MA_above"] = bt["MA10"] > bt["MA40"]
    bt["RY_chg_bps"] = bt["RY_chg"] * 100  # RY is in pct points, chg in pp, *100 = bps
    bt["ATR"] = bt["ATR"]
    bt["price"] = bt["close"]
    return bt[["direction", "M20_pct", "M60_pct", "MA_above", "RY_chg_bps", "ATR", "price"]]


def percentile_of(value: float, sample: pd.Series) -> float:
    if pd.isna(value) or sample.dropna().empty:
        return float("nan")
    s = sample.dropna().values
    return float((s < value).mean() * 100)


def summarize_column(bt: pd.Series, live: pd.Series, name: str) -> dict:
    bt_c = bt.dropna(); live_c = live.dropna()
    if bt_c.empty:
        return {"col": name}
    d = {
        "col": name,
        "bt_n": int(bt_c.count()), "live_n": int(live_c.count()),
        "bt_mean": float(bt_c.mean()), "bt_std": float(bt_c.std(ddof=1)),
        "bt_p05": float(bt_c.quantile(0.05)),
        "bt_p50": float(bt_c.median()),
        "bt_p95": float(bt_c.quantile(0.95)),
    }
    if not live_c.empty:
        d.update({
            "live_mean": float(live_c.mean()), "live_std": float(live_c.std(ddof=1)) if len(live_c) > 1 else float("nan"),
            "live_min": float(live_c.min()), "live_max": float(live_c.max()),
        })
    return d


def print_col_summary(s: dict):
    print(f"\n  === {s['col']} ===")
    print(f"    backtest N={s['bt_n']:,}  mean={s['bt_mean']:.3f}  std={s['bt_std']:.3f}")
    print(f"                  p05={s['bt_p05']:.3f}  p50={s['bt_p50']:.3f}  p95={s['bt_p95']:.3f}")
    if "live_mean" in s:
        print(f"    live     N={s['live_n']}    mean={s['live_mean']:.3f}  "
              f"std={s['live_std']:.3f}  min={s['live_min']:.3f}  max={s['live_max']:.3f}")


def main():
    print("Loading live published-calls...")
    live = load_live_signals()
    print(f"  {len(live)} published calls")

    print("Loading backtest daily signal-date sample...")
    bt = load_backtest_signals()
    print(f"  {len(bt)} weekly signal rows")

    print("\n=== Distribution comparison ===")
    for col in ["M20_pct", "M60_pct", "RY_chg_bps", "ATR", "price"]:
        s = summarize_column(bt[col], live[col], col)
        print_col_summary(s)

    print("\n=== Per-call percentile lookup (each live call vs backtest history) ===")
    print(f"  {'signal_date':<12} {'dir':<6} {'M20':>7} {'p%':>4}  {'M60':>7} {'p%':>4}  {'RY_bps':>7} {'p%':>4}  {'ATR':>7} {'p%':>4}")
    for _, r in live.iterrows():
        d = r["signal_date"].date()
        m20 = r["M20_pct"]; m60 = r["M60_pct"]; ry = r["RY_chg_bps"]; atr = r["ATR"]
        print(f"  {str(d):<12} {r['direction']:<6} "
              f"{m20:>6.2f}% {percentile_of(m20, bt['M20_pct']):>3.0f}  "
              f"{m60:>6.2f}% {percentile_of(m60, bt['M60_pct']):>3.0f}  "
              f"{ry:>6.1f}  {percentile_of(ry, bt['RY_chg_bps']):>3.0f}  "
              f"{atr:>6.2f}  {percentile_of(atr, bt['ATR']):>3.0f}")

    print("\n=== Live call direction distribution vs backtest ===")
    live_dir = live["direction"].value_counts()
    bt_dir = bt["direction"].value_counts()
    print(f"  {'direction':<8} {'backtest':>12} {'live':>8}")
    for d in ["LONG", "SHORT", "FLAT"]:
        bt_n = int(bt_dir.get(d, 0)); bt_p = 100 * bt_n / len(bt)
        live_n = int(live_dir.get(d, 0)); live_p = 100 * live_n / len(live) if len(live) else 0
        print(f"  {d:<8} {bt_n:>6}  {bt_p:>4.1f}%   {live_n:>3}  {live_p:>4.1f}%")

    print("\n=== ATR regime check (are we in a high-volatility regime?) ===")
    live_atr = live["ATR"].dropna()
    bt_atr = bt["ATR"].dropna()
    if not live_atr.empty:
        recent_bt_atr = bt_atr.tail(52)
        print(f"  live ATR range      : {live_atr.min():.2f} - {live_atr.max():.2f} (mean {live_atr.mean():.2f})")
        print(f"  backtest recent 52w : {recent_bt_atr.min():.2f} - {recent_bt_atr.max():.2f} (mean {recent_bt_atr.mean():.2f})")
        print(f"  backtest full 16y   : {bt_atr.min():.2f} - {bt_atr.max():.2f} (mean {bt_atr.mean():.2f})")


if __name__ == "__main__":
    main()
