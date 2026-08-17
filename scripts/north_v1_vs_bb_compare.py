"""Side-by-side v1 vs NORTH-BB comparison.

Runs the v1 backtest (fixed Monday open / Friday close) and the BB
backtest (4H BB entry/exit) on the same signal weeks and reports
matched metrics.

Ship trigger (per docs/experiments/2026-07-31_north_v2_design.md):
    BB mean R per trade >= 0.5%
    AND BB mean R > v1 mean R on the same window

Usage:
    python scripts/north_v1_vs_bb_compare.py --start 2015-01-01 --end 2023-12-31
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
sys.path.insert(0, str(ROOT / "research"))

spec = importlib.util.spec_from_file_location(
    "far", str(ROOT / "scripts" / "far_weekly_gold_read.py")
)
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

spec2 = importlib.util.spec_from_file_location(
    "bb", str(ROOT / "scripts" / "north_bb_backtest.py")
)
bb_mod = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(bb_mod)

CONTRACT_SIZE = 100
SHIP_R_THRESHOLD = 0.005


def run_v1(start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    signals = far.build_signals(daily, ry)
    signals = signals[(signals.index >= start) & (signals.index <= end)]
    weeks = far.week_indices(signals)

    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in signals.index:
            continue
        sig_row = signals.loc[signal_date]
        direction = sig_row["direction"]
        if direction == "FLAT":
            continue
        if pd.isna(sig_row["ATR"]) or pd.isna(sig_row["M60"]):
            continue
        if mon not in signals.index:
            continue
        entry = float(signals.loc[mon, "open"])
        atr = float(sig_row["ATR"])
        if atr <= 0:
            continue
        stop = entry - far.STOP_ATR_MULT * atr if direction == "LONG" else entry + far.STOP_ATR_MULT * atr
        r = far.simulate_week(signals.loc[mon:fri], mon, fri, direction, entry, stop)
        if r:
            r["signal_date"] = signal_date
            r["entry_price"] = entry
            trades.append(r)
    return trades


def summarize(trades: list[dict], label: str) -> dict:
    if not trades:
        return {"label": label, "n": 0}
    n = len(trades)
    pnls = [t["net"] for t in trades]
    returns_pct = [t["net"] / (t["entry_price"] * CONTRACT_SIZE) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    mean_pnl = total / n
    mean_r = sum(returns_pct) / n
    if n > 1:
        std_r = (sum((r - mean_r) ** 2 for r in returns_pct) / (n - 1)) ** 0.5
    else:
        std_r = 0.0
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0
    equity = []
    running = 0.0
    for p in pnls:
        running += p
        equity.append(running)
    peak = 0.0
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    by_year = defaultdict(list)
    for t in trades:
        by_year[str(t["week_start"])[:4]].append(t["net"])
    positive_years = sum(1 for _, tp in by_year.items() if sum(tp) > 0)
    return {
        "label": label,
        "n": n,
        "wins": wins,
        "win_rate": wins / n,
        "total_pnl": total,
        "mean_pnl_per_trade": mean_pnl,
        "mean_return_pct": mean_r,
        "sharpe_ann": sharpe,
        "max_drawdown_dollars": max_dd,
        "years_traded": len(by_year),
        "positive_years": positive_years,
    }


def print_side_by_side(v1_s: dict, bb_s: dict, subset: str) -> None:
    print(f"\n{'='*68}\n {subset.upper()}\n{'='*68}")
    if v1_s.get("n", 0) == 0 or bb_s.get("n", 0) == 0:
        print("  Not enough trades to compare.")
        return
    rows = [
        ("Trades", f"{v1_s['n']}", f"{bb_s['n']}"),
        ("Win rate", f"{100*v1_s['win_rate']:.1f}%", f"{100*bb_s['win_rate']:.1f}%"),
        ("Total P&L", f"${v1_s['total_pnl']:+,.0f}", f"${bb_s['total_pnl']:+,.0f}"),
        ("Mean $/trade", f"${v1_s['mean_pnl_per_trade']:+,.0f}", f"${bb_s['mean_pnl_per_trade']:+,.0f}"),
        ("Mean R (return %)", f"{100*v1_s['mean_return_pct']:+.3f}%", f"{100*bb_s['mean_return_pct']:+.3f}%"),
        ("Sharpe (ann)", f"{v1_s['sharpe_ann']:+.3f}", f"{bb_s['sharpe_ann']:+.3f}"),
        ("Max drawdown", f"${v1_s['max_drawdown_dollars']:,.0f}", f"${bb_s['max_drawdown_dollars']:,.0f}"),
        ("Positive years", f"{v1_s['positive_years']}/{v1_s['years_traded']}",
                            f"{bb_s['positive_years']}/{bb_s['years_traded']}"),
    ]
    col_w = 22
    print(f"  {'metric':<22} {'v1':>{col_w}} {'BB':>{col_w}}")
    print(f"  {'-'*22} {'-'*col_w} {'-'*col_w}")
    for name, a, b in rows:
        print(f"  {name:<22} {a:>{col_w}} {b:>{col_w}}")


def ship_verdict(v1_s: dict, bb_s: dict) -> None:
    print(f"\n{'='*68}\n SHIP VERDICT\n{'='*68}")
    if bb_s.get("n", 0) == 0 or v1_s.get("n", 0) == 0:
        print("  Not enough trades on one side.")
        return
    bb_r = bb_s["mean_return_pct"]
    v1_r = v1_s["mean_return_pct"]
    condition_a = bb_r >= SHIP_R_THRESHOLD
    condition_b = bb_r > v1_r
    print(f"  BB mean R:  {100*bb_r:+.3f}%     v1 mean R: {100*v1_r:+.3f}%")
    print(f"  A. BB mean R >= 0.5%:      {'PASS' if condition_a else 'FAIL'}")
    print(f"  B. BB mean R > v1 mean R:  {'PASS' if condition_b else 'FAIL'}")
    if condition_a and condition_b:
        print("\n  VERDICT: SHIP")
    else:
        print("\n  VERDICT: DO NOT SHIP")
        if not condition_a:
            print(f"    Reason: mean R {100*bb_r:+.3f}% is below the 0.5% floor.")
        if not condition_b:
            print(f"    Reason: BB does not beat v1 mean R.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-07-20")
    args = ap.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    print(f"NORTH v1 vs BB comparison: {args.start} to {args.end}")

    print("\nRunning v1 backtest...")
    v1_trades = run_v1(start, end)

    print("Running BB backtest...")
    bb_result = bb_mod.backtest(start, end)
    bb_trades = bb_result["trades"]

    # Restrict both sides to weeks where BB was able to fill a trade,
    # so this is a truly apples-to-apples comparison.
    bb_weeks = {t["signal_date"] for t in bb_trades}
    v1_matched = [t for t in v1_trades if t.get("signal_date") in bb_weeks]

    print(f"\nSignal weeks covered: v1={len(v1_trades)}  BB={len(bb_trades)}  matched={len(v1_matched)}")

    v1_all = summarize(v1_matched, "v1")
    bb_all = summarize(bb_trades, "BB")
    print_side_by_side(v1_all, bb_all, "ALL DIRECTIONS (matched weeks)")

    v1_long = summarize([t for t in v1_matched if t["direction"] == "LONG"], "v1")
    bb_long = summarize([t for t in bb_trades if t["direction"] == "LONG"], "BB")
    print_side_by_side(v1_long, bb_long, "LONG only")

    v1_short = summarize([t for t in v1_matched if t["direction"] == "SHORT"], "v1")
    bb_short = summarize([t for t in bb_trades if t["direction"] == "SHORT"], "BB")
    print_side_by_side(v1_short, bb_short, "SHORT only")

    ship_verdict(v1_all, bb_all)

    print("\nBB exit reason breakdown:")
    exit_counts = defaultdict(int)
    for t in bb_trades:
        exit_counts[t["exit_reason"]] += 1
    for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count / len(bb_trades)
        print(f"  {reason}: {count} ({pct:.1f}%)")

    print("\nBB entry reason breakdown:")
    entry_counts = defaultdict(int)
    for t in bb_trades:
        entry_counts[t["entry_reason"]] += 1
    for reason, count in sorted(entry_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count / len(bb_trades)
        print(f"  {reason}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
