"""Adaptive-stop probe on v1 + v2 signal sets.

Queued as iteration 9 from the 2026-08-31 session but never ran. Prior
stop-multiplier robustness (2026-08-31) showed the shipped 2.0xATR stop
is U-shaped-worst among fixed multipliers. The natural follow-up is: do
non-fixed exit rules beat any of the fixed variants?

Variants tested (both variants get the same set applied to their signal set):
  1. fixed_2x         : baseline (shipped). Fixed 2xATR stop, Friday time exit.
  2. fixed_1x         : tight. Fixed 1xATR stop.
  3. fixed_2p5x       : wide. Fixed 2.5xATR stop.
  4. trailing_2x      : trailing 2xATR behind highest-close (LONG) / lowest-close (SHORT).
  5. be_at_1x         : fixed 2xATR stop, moved to entry after close hits +1xATR.
  6. target_2x        : fixed 2xATR stop, exit at 2xATR profit (checked via daily high/low).
  7. trailing_be_2x   : trailing 2xATR AND breakeven move at +1xATR profit.

Exit-timing convention: daily OHLC only, so intra-day sequencing is unknown.
Conservative rule: on any daily bar, if BOTH stop and target could have been
hit (low<=stop AND high>=target for LONG), assume stop hit first (worst case
for the trade). This is the standard conservative backtest convention.

Usage:
  python scripts/v1_v2_adaptive_stop_probe.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util
spec = importlib.util.spec_from_file_location("far_backtest",
                                                str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far_backtest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far_backtest)

CONTRACT_SIZE = far_backtest.CONTRACT_SIZE
RT_COST = far_backtest.RT_COST


@dataclass
class ExitRule:
    name: str
    stop_mult: float
    trailing_mult: float | None = None
    be_trigger_mult: float | None = None
    target_mult: float | None = None


VARIANTS = [
    ExitRule("fixed_2x",       stop_mult=2.0),
    ExitRule("fixed_1x",       stop_mult=1.0),
    ExitRule("fixed_2p5x",     stop_mult=2.5),
    ExitRule("trailing_2x",    stop_mult=2.0, trailing_mult=2.0),
    ExitRule("be_at_1x",       stop_mult=2.0, be_trigger_mult=1.0),
    ExitRule("target_2x",      stop_mult=2.0, target_mult=2.0),
    ExitRule("trailing_be_2x", stop_mult=2.0, trailing_mult=2.0, be_trigger_mult=1.0),
]


def simulate_week(week_bars: pd.DataFrame, direction: str, entry_price: float,
                    atr: float, rule: ExitRule) -> dict:
    if len(week_bars) == 0:
        return None
    dir_sign = 1 if direction == "LONG" else -1

    if direction == "LONG":
        stop = entry_price - rule.stop_mult * atr
        target = entry_price + rule.target_mult * atr if rule.target_mult else None
        be_trigger = entry_price + rule.be_trigger_mult * atr if rule.be_trigger_mult else None
    else:
        stop = entry_price + rule.stop_mult * atr
        target = entry_price - rule.target_mult * atr if rule.target_mult else None
        be_trigger = entry_price - rule.be_trigger_mult * atr if rule.be_trigger_mult else None

    be_triggered = False
    exit_price = None
    exit_reason = None

    for _, row in week_bars.iterrows():
        hi = float(row["high"]); lo = float(row["low"]); cl = float(row["close"])

        # Conservative: stop check FIRST (worst case for trade)
        if direction == "LONG":
            hit_stop = lo <= stop
        else:
            hit_stop = hi >= stop
        if hit_stop:
            exit_price = stop
            exit_reason = "stop" if not be_triggered else "be_stop"
            break

        # Target check (only if target is set)
        if target is not None:
            if direction == "LONG":
                hit_target = hi >= target
            else:
                hit_target = lo <= target
            if hit_target:
                exit_price = target
                exit_reason = "target"
                break

        # End-of-day updates
        # 1. Breakeven trigger check (uses close, so applies for next day)
        if be_trigger is not None and not be_triggered:
            if direction == "LONG" and cl >= be_trigger:
                stop = max(stop, entry_price)
                be_triggered = True
            elif direction == "SHORT" and cl <= be_trigger:
                stop = min(stop, entry_price)
                be_triggered = True

        # 2. Trailing stop update (based on close)
        if rule.trailing_mult is not None:
            if direction == "LONG":
                new_stop = cl - rule.trailing_mult * atr
                stop = max(stop, new_stop)
            else:
                new_stop = cl + rule.trailing_mult * atr
                stop = min(stop, new_stop)

    if exit_price is None:
        exit_price = float(week_bars.iloc[-1]["close"])
        exit_reason = "time"

    gross = (exit_price - entry_price) * dir_sign * CONTRACT_SIZE
    net = gross - RT_COST
    return {
        "direction": direction, "entry": entry_price, "exit": exit_price,
        "atr": atr, "exit_reason": exit_reason,
        "gross": gross, "net": net,
    }


def backtest_variant(daily: pd.DataFrame, df: pd.DataFrame, weeks: list,
                       rule: ExitRule, v2_filter: pd.Series | None = None) -> list[dict]:
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index:
            continue
        sig_row = df.loc[signal_date]
        direction = sig_row["direction"]
        if direction == "FLAT":
            continue
        if v2_filter is not None:
            if signal_date not in v2_filter.index or not bool(v2_filter.loc[signal_date]):
                continue
        if pd.isna(sig_row["ATR"]) or pd.isna(sig_row["M60"]):
            continue
        if mon not in df.index:
            continue
        entry_price = float(df.loc[mon]["open"])
        atr = float(sig_row["ATR"])
        if atr <= 0:
            continue
        week_slice = df.loc[mon:fri]
        result = simulate_week(week_slice, direction, entry_price, atr, rule)
        if result:
            result["signal_date"] = signal_date
            trades.append(result)
    return trades


def summarize(trades: list[dict], label: str) -> dict:
    if not trades:
        return {"label": label, "n": 0}
    n = len(trades)
    pnls = np.array([t["net"] for t in trades])
    wins = int((pnls > 0).sum())
    losses = int((pnls < 0).sum())
    wr = wins / n

    reasons = pd.Series([t["exit_reason"] for t in trades]).value_counts()

    returns = np.array([t["net"] / (t["entry"] * CONTRACT_SIZE) for t in trades])
    mean_r = returns.mean(); std_r = returns.std(ddof=1)
    sharpe_weekly = mean_r / std_r if std_r > 0 else 0
    sharpe_ann = sharpe_weekly * np.sqrt(52)

    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd = float(dd.min())
    cum_final = float(cum[-1])

    return {
        "label": label, "n": n, "wr": wr,
        "stop_pct": reasons.get("stop", 0) / n,
        "be_stop_pct": reasons.get("be_stop", 0) / n,
        "target_pct": reasons.get("target", 0) / n,
        "time_pct": reasons.get("time", 0) / n,
        "sharpe": sharpe_ann, "cum": cum_final, "max_dd": max_dd,
    }


def print_table(summaries: list[dict], header: str):
    print(f"\n=== {header} ===")
    cols = ["variant", "n", "WR", "stop%", "BE%", "tgt%", "time%", "Sharpe", "cum $", "maxDD"]
    print(f"  {cols[0]:<18} {cols[1]:>4}  {cols[2]:>6}  {cols[3]:>6}  {cols[4]:>5}  {cols[5]:>5}  {cols[6]:>6}  {cols[7]:>7}  {cols[8]:>10}  {cols[9]:>10}")
    for s in summaries:
        if s["n"] == 0:
            print(f"  {s['label']:<18} (no trades)"); continue
        print(f"  {s['label']:<18} {s['n']:>4}  {s['wr']*100:>5.1f}%  "
              f"{s['stop_pct']*100:>5.1f}%  {s['be_stop_pct']*100:>4.1f}%  "
              f"{s['target_pct']*100:>4.1f}%  {s['time_pct']*100:>5.1f}%  "
              f"{s['sharpe']:>7.2f}  ${s['cum']:>9,.0f}  ${s['max_dd']:>9,.0f}")


def load_v2_filter(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Compute v2 (DXY-conditioned) filter, same rule as far_weekly_v2_backtest."""
    dxy_path = far_backtest.ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"
    dxy = far_backtest.load_macro_series(dxy_path, "dxy")
    dxy_daily = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                              method="ffill")
    dxy_daily.index = df.index
    dxy_20d_chg = dxy_daily.pct_change(20) * 100
    long_ok  = (df["direction"] == "LONG") & (dxy_20d_chg < 0)
    short_ok = (df["direction"] == "SHORT") & (dxy_20d_chg > 0)
    return long_ok | short_ok


def main():
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-07-01", tz="UTC")

    print(f"Loading data {start.date()} -> {end.date()}...")
    daily = far_backtest.load_daily_bars(start, end)
    ry = far_backtest.load_macro_series(far_backtest.RY, "real_yield_10y")
    df = far_backtest.build_signals(daily, ry)
    df = df[(df.index >= start) & (df.index <= end)]
    weeks = far_backtest.week_indices(df)
    print(f"  loaded {len(df)} daily bars, {len(weeks)} weeks")

    print(f"\nComputing v2 (DXY) filter...")
    v2_filter = load_v2_filter(df, start, end)

    print(f"\nRunning {len(VARIANTS)} variants on v1 signal set...")
    v1_summaries = []
    for rule in VARIANTS:
        trades = backtest_variant(daily, df, weeks, rule, v2_filter=None)
        v1_summaries.append(summarize(trades, rule.name))

    print(f"\nRunning {len(VARIANTS)} variants on v2 signal set...")
    v2_summaries = []
    for rule in VARIANTS:
        trades = backtest_variant(daily, df, weeks, rule, v2_filter=v2_filter)
        v2_summaries.append(summarize(trades, rule.name))

    print_table(v1_summaries, "v1 signal set (all directional)")
    print_table(v2_summaries, "v2 signal set (DXY-confirmed)")

    print("\n=== Ranking by Sharpe ===")
    for label, sums in [("v1", v1_summaries), ("v2", v2_summaries)]:
        ranked = sorted([s for s in sums if s["n"] > 0], key=lambda s: -s["sharpe"])
        print(f"\n  {label}:")
        for i, s in enumerate(ranked, 1):
            print(f"    {i}. {s['label']:<18} Sharpe {s['sharpe']:.2f}  cum ${s['cum']:>9,.0f}  DD ${s['max_dd']:>9,.0f}")


if __name__ == "__main__":
    main()
