"""v1 signal-component ablation study.

v1 fires LONG when ALL of:
  M20 > 0, M60 > 0, MA10 > MA40, RY_chg_20d < 0
And symmetrically SHORT.

This script measures which of the four components carry v1's alpha:
  - Baseline (full v1, all 4 required)
  - Drop-one: remove one component, keep other 3. (4 variants)
  - Only-one: keep one component, drop other 3. (4 variants)

Each variant runs the same backtest engine, same 2xATR stop, same
Monday-open / Friday-close exit, same $5 RT cost. Directions computed
independently for each variant. Ranking by Sharpe.

Usage:
  python scripts/v1_signal_ablation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util
spec = importlib.util.spec_from_file_location("far_backtest",
                                                str(ROOT / "scripts" / "far_weekly_gold_read.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)

CONTRACT_SIZE = fb.CONTRACT_SIZE
RT_COST = fb.RT_COST
STOP_ATR_MULT = fb.STOP_ATR_MULT


def apply_variant(df: pd.DataFrame, use_M20: bool, use_M60: bool,
                    use_MA: bool, use_RY: bool) -> pd.DataFrame:
    """Return df with 'direction' column computed from selected components only."""
    d = df.copy()
    if use_M20:
        long_M20 = d["M20"] > 0; short_M20 = d["M20"] < 0
    else:
        long_M20 = True; short_M20 = True
    if use_M60:
        long_M60 = d["M60"] > 0; short_M60 = d["M60"] < 0
    else:
        long_M60 = True; short_M60 = True
    if use_MA:
        long_MA = d["MA10"] > d["MA40"]; short_MA = d["MA10"] < d["MA40"]
    else:
        long_MA = True; short_MA = True
    if use_RY:
        long_RY = d["RY_chg"] < 0; short_RY = d["RY_chg"] > 0
    else:
        long_RY = True; short_RY = True

    long_cond = long_M20 & long_M60 & long_MA & long_RY
    short_cond = short_M20 & short_M60 & short_MA & short_RY
    d["direction"] = np.where(long_cond, "LONG",
                                np.where(short_cond, "SHORT", "FLAT"))
    return d


def backtest(df: pd.DataFrame, weeks: list) -> list[dict]:
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index:
            continue
        sig_row = df.loc[signal_date]
        direction = sig_row["direction"]
        if direction == "FLAT":
            continue
        if pd.isna(sig_row["ATR"]) or pd.isna(sig_row["M60"]) or pd.isna(sig_row["RY_chg"]):
            continue
        if mon not in df.index:
            continue
        entry_price = float(df.loc[mon]["open"])
        atr = float(sig_row["ATR"])
        if atr <= 0:
            continue
        if direction == "LONG":
            stop = entry_price - STOP_ATR_MULT * atr
        else:
            stop = entry_price + STOP_ATR_MULT * atr
        week_slice = df.loc[mon:fri]
        result = fb.simulate_week(week_slice, mon, fri, direction, entry_price, stop)
        if result:
            trades.append(result)
    return trades


def summarize(trades: list[dict], label: str, direction_counts: dict) -> dict:
    if not trades:
        return {"label": label, "n": 0, **direction_counts}
    n = len(trades)
    pnls = np.array([t["net"] for t in trades])
    wins = int((pnls > 0).sum())
    wr = wins / n
    returns = np.array([t["net"] / (t["entry"] * CONTRACT_SIZE) for t in trades])
    sharpe_ann = (returns.mean() / returns.std(ddof=1)) * np.sqrt(52) if returns.std(ddof=1) > 0 else 0
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    max_dd = float((cum - peak).min())
    return {
        "label": label, "n": n, "wr": wr, "sharpe": sharpe_ann,
        "cum": float(cum[-1]), "max_dd": max_dd,
        **direction_counts,
    }


def count_directions(df: pd.DataFrame) -> dict:
    dc = df["direction"].value_counts().to_dict()
    return {
        "n_long": int(dc.get("LONG", 0)),
        "n_short": int(dc.get("SHORT", 0)),
        "n_flat": int(dc.get("FLAT", 0)),
    }


def print_table(rows: list[dict], header: str):
    print(f"\n=== {header} ===")
    print(f"  {'variant':<24} {'trades':>6}  {'#L':>4}  {'#S':>4}  {'WR':>6}  {'Sharpe':>7}  {'cum $':>10}  {'maxDD':>10}")
    for r in rows:
        if r["n"] == 0:
            print(f"  {r['label']:<24} (no trades)"); continue
        print(f"  {r['label']:<24} {r['n']:>6}  "
              f"{r.get('n_long',0):>4}  {r.get('n_short',0):>4}  "
              f"{r['wr']*100:>5.1f}%  {r['sharpe']:>7.2f}  "
              f"${r['cum']:>9,.0f}  ${r['max_dd']:>9,.0f}")


VARIANTS = [
    # (label, use_M20, use_M60, use_MA, use_RY)
    ("baseline_v1_all4",   True,  True,  True,  True),
    # Drop-one
    ("drop_M20",           False, True,  True,  True),
    ("drop_M60",           True,  False, True,  True),
    ("drop_MA",            True,  True,  False, True),
    ("drop_RY",            True,  True,  True,  False),
    # Only-one
    ("only_M20",           True,  False, False, False),
    ("only_M60",           False, True,  False, False),
    ("only_MA",            False, False, True,  False),
    ("only_RY",            False, False, False, True),
    # Drop-two combinations (useful for pairs analysis)
    ("only_momentum_M20_M60", True,  True,  False, False),
    ("only_trend_MA_only",    False, False, True,  False),  # dup w/ only_MA, keep for grouping
    ("drop_both_momentum", False, False, True,  True),
]


def main():
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-07-01", tz="UTC")

    print(f"Loading data {start.date()} -> {end.date()}...")
    daily = fb.load_daily_bars(start, end)
    ry = fb.load_macro_series(fb.RY, "real_yield_10y")
    base = fb.build_signals(daily, ry)
    base = base[(base.index >= start) & (base.index <= end)]
    weeks = fb.week_indices(base)
    print(f"  {len(base)} daily bars, {len(weeks)} weeks")

    results = []
    for label, uM20, uM60, uMA, uRY in VARIANTS:
        df_v = apply_variant(base, uM20, uM60, uMA, uRY)
        # Direction counts on weeks (signal_date only, not every daily bar)
        weekly_dir = pd.Series([df_v.loc[sd]["direction"] if sd in df_v.index else "MISSING"
                                  for sd, _, _ in weeks])
        dc = {
            "n_long": int((weekly_dir == "LONG").sum()),
            "n_short": int((weekly_dir == "SHORT").sum()),
            "n_flat": int((weekly_dir == "FLAT").sum()),
        }
        trades = backtest(df_v, weeks)
        results.append(summarize(trades, label, dc))
        print(f"  {label}: {len(trades)} trades ({dc['n_long']}L, {dc['n_short']}S)")

    print_table(results, "v1 signal-component ablation")

    print("\n=== Ranking by Sharpe (drop-one variants) ===")
    drops = [r for r in results if r["label"].startswith("drop_") or r["label"] == "baseline_v1_all4"]
    for r in sorted(drops, key=lambda x: -x["sharpe"]):
        delta = r["sharpe"] - next(x["sharpe"] for x in results if x["label"] == "baseline_v1_all4")
        print(f"  {r['label']:<24} Sharpe {r['sharpe']:.2f}  (delta vs baseline: {delta:+.2f})  n={r['n']}")

    print("\n=== Ranking by Sharpe (only-one variants) ===")
    onlys = [r for r in results if r["label"].startswith("only_") and r["n"] > 0]
    for r in sorted(onlys, key=lambda x: -x["sharpe"]):
        print(f"  {r['label']:<24} Sharpe {r['sharpe']:.2f}  cum ${r['cum']:>9,.0f}  n={r['n']}")

    print("\n=== Load-bearing rank (drop-one damage) ===")
    baseline_sharpe = next(x["sharpe"] for x in results if x["label"] == "baseline_v1_all4")
    drops_only = [r for r in results if r["label"].startswith("drop_")]
    # Most load-bearing = largest Sharpe drop when removed = biggest gap or "removal helps"
    # Actually the load-bearing question is: which component when REMOVED hurts the most?
    # If removing a component RAISES Sharpe, that component is anti-informative.
    for r in sorted(drops_only, key=lambda x: baseline_sharpe - x["sharpe"], reverse=True):
        component = r["label"].replace("drop_", "")
        gap = baseline_sharpe - r["sharpe"]
        print(f"  {component:<6} removal costs Sharpe {gap:+.2f}  (baseline {baseline_sharpe:.2f}, drop_{component} {r['sharpe']:.2f})")


if __name__ == "__main__":
    main()
