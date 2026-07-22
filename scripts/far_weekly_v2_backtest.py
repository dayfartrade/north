"""FAR Weekly v2 backtest with DXY conditioning.

Pre-reg: docs/experiments/2026-07-22_far_weekly_v2_dxy_prereg.md
Signal: v1 signal AND DXY_chg agrees with direction.

This is design-time comparison ONLY — NOT a ship gate. See pre-reg
for forward validation requirements.

Usage: python scripts/far_weekly_v2_backtest.py --start 2010-01-01 --end 2026-07-20
"""
from __future__ import annotations

import argparse
import sys
import math
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

import importlib.util
spec = importlib.util.spec_from_file_location("far",
                                                str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

DXY = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"


def build_v2_signals(daily: pd.DataFrame, ry: pd.Series, dxy: pd.Series) -> pd.DataFrame:
    """v1 signals + DXY AND-condition."""
    df = far.build_signals(daily, ry)

    # Add DXY column
    dxy_daily = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                             method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(far.RY_LAG)

    # Direction: v1 direction AND DXY_chg agrees
    v1_dir = df["direction"]
    long_ok = (v1_dir == "LONG") & (df["DXY_chg"] < 0)
    short_ok = (v1_dir == "SHORT") & (df["DXY_chg"] > 0)
    df["direction"] = np.where(long_ok, "LONG",
                                 np.where(short_ok, "SHORT", "FLAT"))
    return df


def backtest_v2(start: pd.Timestamp, end: pd.Timestamp) -> dict:
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    dxy = far.load_macro_series(DXY, "dxy")
    df = build_v2_signals(daily, ry, dxy)

    df = df[(df.index >= start) & (df.index <= end)]
    weeks = far.week_indices(df)

    trades = []
    flat = 0
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index:
            continue
        sig_row = df.loc[signal_date]
        direction = sig_row["direction"]
        if direction == "FLAT":
            flat += 1
            continue
        if pd.isna(sig_row["ATR"]) or pd.isna(sig_row["M60"]) or pd.isna(sig_row["DXY_chg"]):
            continue
        entry_row = df.loc[mon] if mon in df.index else None
        if entry_row is None:
            continue
        entry_price = float(entry_row["open"])
        atr = float(sig_row["ATR"])
        if atr <= 0:
            continue
        if direction == "LONG":
            stop_price = entry_price - 2.0 * atr
        else:
            stop_price = entry_price + 2.0 * atr

        week_bars = df.loc[mon:fri]
        if len(week_bars) == 0:
            continue
        dir_sign = 1 if direction == "LONG" else -1
        exit_price = None; exit_reason = None
        for _, row in week_bars.iterrows():
            if direction == "LONG":
                hit_stop = float(row["low"]) <= stop_price
            else:
                hit_stop = float(row["high"]) >= stop_price
            if hit_stop:
                exit_price = stop_price; exit_reason = "stop"; break
        if exit_price is None:
            exit_price = float(week_bars.iloc[-1]["close"])
            exit_reason = "time"
        gross = (exit_price - entry_price) * dir_sign * 100
        net = gross - 5.0
        trades.append({
            "week_start": mon, "direction": direction,
            "entry": entry_price, "exit": exit_price,
            "exit_reason": exit_reason, "net": net,
        })
    return {"trades": trades, "flat": flat, "total_weeks": len(weeks)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-07-20")
    args = ap.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    r = backtest_v2(start, end)
    trades = r["trades"]
    n = len(trades)
    if n == 0:
        print("No trades. v2 filter too restrictive.")
        return

    pnls = [t["net"] for t in trades]
    returns = [t["net"] / (t["entry"] * 100) for t in trades]
    total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    mean_r = sum(returns) / n
    std_r = (sum((r - mean_r) ** 2 for r in returns) / (n - 1)) ** 0.5
    sharpe = mean_r / std_r * math.sqrt(52) if std_r > 0 else 0

    # PSR
    sys.path.insert(0, str(ROOT / "src"))
    from deflated_sharpe import sr_stats, probabilistic_sharpe
    s = sr_stats(returns)
    psr = probabilistic_sharpe(s, benchmark_sr=0.0)

    # Bootstrap CI
    import random
    rng = random.Random(42)
    means = []
    for _ in range(10000):
        smp = [returns[rng.randrange(n)] for _ in range(n)]
        means.append(sum(smp)/n)
    means.sort()
    lo95 = means[250]; hi95 = means[9750]

    print(f"\n=== FAR Weekly v2 (DXY-conditioned) — {args.start} to {args.end} ===")
    print(f"  Total weeks: {r['total_weeks']}  FLAT: {r['flat']} "
          f"({100*r['flat']/r['total_weeks']:.0f}%)")
    print(f"  Traded weeks: {n}")
    print(f"  Win rate: {100*wins/n:.1f}%")
    print(f"  Total P&L: ${total:+,.0f}")
    print(f"  Mean $/week: ${mean:+,.0f}")
    print(f"  Sharpe (ann): {sharpe:.3f}")
    print(f"  Skewness: {s.skewness:+.3f}")
    print(f"  Bootstrap 95% CI on mean weekly return: "
          f"[{100*lo95:+.4f}%, {100*hi95:+.4f}%]")
    print(f"  PSR vs SR=0: {psr:.4f}")

    # Year-by-year
    by_year = defaultdict(list)
    for t in trades:
        by_year[str(t["week_start"])[:4]].append(t)
    print(f"\n  Year-by-year:")
    for y in sorted(by_year):
        tr = by_year[y]
        pl = [t["net"] for t in tr]
        n_y = len(pl); w = sum(1 for p in pl if p > 0)
        print(f"    {y}: n={n_y:>3d}  mean=${sum(pl)/n_y:>+6,.0f}  "
              f"WR={100*w/n_y:>4.1f}%  total=${sum(pl):>+8,.0f}")


if __name__ == "__main__":
    main()
