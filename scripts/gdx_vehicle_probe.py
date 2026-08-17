"""GDX vehicle with gold v1 signal.

Different question than the universe probe. Universe probe asked
"does GDX have its own tradeable momentum" (answer: no, actively
negative). This asks "if we use GOLD'S signal but trade GDX as the
vehicle, do we get amplified returns from miners' operational leverage?"

Mechanism: gold miners typically move 2-3x gold on directional days
because their profit is a lever on the gold-vs-mining-cost spread.
So a good gold signal traded through GDX could theoretically show
higher returns per trade with proportionally higher variance.

The test:
  For each week where gold v1 fires directional, compute:
    - What gold trade would have been (Monday open to Friday close)
    - What GDX trade would have been (same window, GDX prices)
  Report side-by-side.

Not a ship candidate. Just data.
"""
from __future__ import annotations

import argparse
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


def load_gdx() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "universe" / "gdx_daily.csv", parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df = df[df.index.weekday < 5]
    return df


def summarize(returns: list[float], label: str) -> None:
    n = len(returns)
    if n == 0:
        print(f"  {label}: no trades"); return
    wins = sum(1 for r in returns if r > 0)
    mean = sum(returns) / n
    if n > 1:
        std = (sum((r - mean) ** 2 for r in returns) / (n - 1)) ** 0.5
    else:
        std = 0.0
    sharpe = (mean / std) * math.sqrt(52) if std > 0 else 0.0
    total = sum(returns)
    equity = []; running = 0.0
    for r in returns:
        running += r; equity.append(running)
    peak = 0.0; max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak - v > max_dd:
            max_dd = peak - v
    print(f"  {label}:  n={n}  WR={100*wins/n:.1f}%")
    print(f"    mean R:       {100*mean:+.3f}%")
    print(f"    std R:        {100*std:.3f}%")
    print(f"    Sharpe (ann): {sharpe:+.3f}")
    print(f"    cum R:        {100*total:+.2f}%")
    print(f"    max DD:       {100*max_dd:.2f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-08-14")
    args = ap.parse_args()
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    print(f"GDX vehicle with gold v1 signal: {args.start} to {args.end}")
    print(f"Mechanism check: does miner operational leverage amplify gold v1?\n")

    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    sig = far.build_signals(daily, ry)
    sig = sig[(sig.index >= start) & (sig.index <= end)]
    weeks = far.week_indices(sig)
    gdx = load_gdx()

    gold_returns = []
    gdx_returns = []
    paired = []
    for signal_date, mon, fri in weeks:
        if signal_date not in sig.index: continue
        row = sig.loc[signal_date]
        direction = row["direction"]
        if direction == "FLAT": continue
        if pd.isna(row["ATR"]) or pd.isna(row["M60"]): continue
        if mon not in sig.index: continue

        # Gold trade
        gold_entry = float(sig.loc[mon, "open"])
        atr = float(row["ATR"])
        if atr <= 0: continue
        gold_stop = gold_entry - far.STOP_ATR_MULT * atr if direction == "LONG" else gold_entry + far.STOP_ATR_MULT * atr
        gold_week = sig.loc[mon:fri]
        gold_exit = None
        for _, r in gold_week.iterrows():
            if direction == "LONG" and float(r["low"]) <= gold_stop:
                gold_exit = gold_stop; break
            if direction == "SHORT" and float(r["high"]) >= gold_stop:
                gold_exit = gold_stop; break
        if gold_exit is None:
            gold_exit = float(gold_week.iloc[-1]["close"])
        dir_sign = 1 if direction == "LONG" else -1
        gold_r = (gold_exit - gold_entry) * dir_sign / gold_entry

        # GDX trade: same window, GDX prices, GDX-specific ATR-based stop.
        gdx_win = gdx[(gdx.index >= mon) & (gdx.index <= fri)]
        if len(gdx_win) == 0:
            continue
        # Approximate ATR for GDX using its own recent 20-day range
        gdx_hist = gdx[gdx.index < mon].tail(20)
        if len(gdx_hist) < 5:
            continue
        gdx_atr = (gdx_hist["high"] - gdx_hist["low"]).mean()
        gdx_entry = float(gdx_win.iloc[0]["open"])
        gdx_stop = gdx_entry - far.STOP_ATR_MULT * gdx_atr if direction == "LONG" else gdx_entry + far.STOP_ATR_MULT * gdx_atr
        gdx_exit = None
        for _, r in gdx_win.iterrows():
            if direction == "LONG" and float(r["low"]) <= gdx_stop:
                gdx_exit = gdx_stop; break
            if direction == "SHORT" and float(r["high"]) >= gdx_stop:
                gdx_exit = gdx_stop; break
        if gdx_exit is None:
            gdx_exit = float(gdx_win.iloc[-1]["close"])
        gdx_r = (gdx_exit - gdx_entry) * dir_sign / gdx_entry

        gold_returns.append(gold_r)
        gdx_returns.append(gdx_r)
        paired.append((gold_r, gdx_r, direction))

    print(f"Matched trades: {len(paired)}\n")

    print("=" * 60)
    print(" Gold (native vehicle)")
    print("=" * 60)
    summarize(gold_returns, "gold v1")

    print(f"\n{'='*60}\n GDX (miner vehicle, same signal)\n{'='*60}")
    summarize(gdx_returns, "gdx via gold v1")

    # Split by direction
    long_pairs = [(g, x) for g, x, d in paired if d == "LONG"]
    short_pairs = [(g, x) for g, x, d in paired if d == "SHORT"]
    if long_pairs:
        print(f"\n{'='*60}\n LONG only ({len(long_pairs)})\n{'='*60}")
        summarize([g for g, x in long_pairs], "gold LONG")
        summarize([x for g, x in long_pairs], "gdx LONG")
    if short_pairs:
        print(f"\n{'='*60}\n SHORT only ({len(short_pairs)})\n{'='*60}")
        summarize([g for g, x in short_pairs], "gold SHORT")
        summarize([x for g, x in short_pairs], "gdx SHORT")

    # Beta estimate
    if len(paired) >= 20:
        mg = sum(g for g, x, _ in paired) / len(paired)
        mx = sum(x for g, x, _ in paired) / len(paired)
        num = sum((g - mg) * (x - mx) for g, x, _ in paired)
        den = sum((g - mg) ** 2 for g, x, _ in paired)
        beta = num / den if den > 0 else float("nan")
        print(f"\nEmpirical GDX beta to gold on these trades: {beta:.2f}")
        print(f"  (a beta of 2.0 would mean GDX moves 2x gold on these weeks;")
        print(f"   check if gdx mean R / gold mean R matches this beta)")


if __name__ == "__main__":
    main()
