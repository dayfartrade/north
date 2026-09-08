"""5m-granularity trailing stop probe on v1 + v2 signal sets.

Closes the gap flagged in the 2026-09-08 adaptive-stop probe: daily-close
trailing barely beat the fixed baseline, but a 2xATR trailing distance
checked only at daily close cannot lock in much MFE. The honest test uses
5m bars during the week.

Variants:
  1. fixed_2x_baseline (reference, daily-simulated stop check)
  2. trail_2x_5m
  3. trail_1p5x_5m
  4. trail_1x_5m
  5. trail_0p5x_5m (very tight)
  6. trail_2x_5m_after_1x_profit (only start trailing after +1x ATR gain)

Exit-timing convention on 5m bars: order-of-touch within a 5m bar is
still ambiguous but far less than daily. Conservative: on any 5m bar,
stop check happens FIRST before trailing update.

Usage:
  python scripts/v1_v2_intraday_trailing_probe.py
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
class TrailRule:
    name: str
    initial_stop_mult: float
    trailing_mult: float | None = None
    activation_mult: float | None = None


VARIANTS = [
    TrailRule("fixed_2x_baseline",   initial_stop_mult=2.0),
    TrailRule("trail_2x_5m",         initial_stop_mult=2.0, trailing_mult=2.0),
    TrailRule("trail_1p5x_5m",       initial_stop_mult=2.0, trailing_mult=1.5),
    TrailRule("trail_1x_5m",         initial_stop_mult=2.0, trailing_mult=1.0),
    TrailRule("trail_0p5x_5m",       initial_stop_mult=2.0, trailing_mult=0.5),
    TrailRule("trail_2x_after_1x",   initial_stop_mult=2.0, trailing_mult=2.0, activation_mult=1.0),
]


def load_5m_bars() -> pd.DataFrame:
    """Load combined 5m XAUUSD data (2010-onward)."""
    dfs = []
    for path in [far_backtest.EARLY_5M, far_backtest.HISTORICAL_5M, far_backtest.LIVE_5M]:
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["ts"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        dfs.append(df[["ts", "open", "high", "low", "close"]])
    combined = pd.concat(dfs, ignore_index=True) \
        .drop_duplicates(subset=["ts"], keep="first") \
        .sort_values("ts") \
        .set_index("ts")
    return combined


def simulate_week_5m(week_5m: pd.DataFrame, direction: str, entry_price: float,
                       atr: float, rule: TrailRule) -> dict:
    """Simulate one week's trade using 5m bars for stop and trailing."""
    if len(week_5m) == 0:
        return None
    dir_sign = 1 if direction == "LONG" else -1

    if direction == "LONG":
        stop = entry_price - rule.initial_stop_mult * atr
        activation_level = entry_price + rule.activation_mult * atr if rule.activation_mult else None
    else:
        stop = entry_price + rule.initial_stop_mult * atr
        activation_level = entry_price - rule.activation_mult * atr if rule.activation_mult else None

    trailing_active = rule.activation_mult is None  # active from start if no activation
    exit_price = None
    exit_reason = None

    for _, row in week_5m.iterrows():
        hi = float(row["high"]); lo = float(row["low"]); cl = float(row["close"])

        # 1. Stop check FIRST (conservative)
        if direction == "LONG":
            hit_stop = lo <= stop
        else:
            hit_stop = hi >= stop
        if hit_stop:
            exit_price = stop
            exit_reason = "trail_stop" if trailing_active and rule.trailing_mult else "stop"
            break

        # 2. Activation check
        if activation_level is not None and not trailing_active:
            if direction == "LONG" and hi >= activation_level:
                trailing_active = True
            elif direction == "SHORT" and lo <= activation_level:
                trailing_active = True

        # 3. Trailing update (if active)
        if trailing_active and rule.trailing_mult is not None:
            if direction == "LONG":
                new_stop = cl - rule.trailing_mult * atr
                stop = max(stop, new_stop)
            else:
                new_stop = cl + rule.trailing_mult * atr
                stop = min(stop, new_stop)

    if exit_price is None:
        exit_price = float(week_5m.iloc[-1]["close"])
        exit_reason = "time"

    gross = (exit_price - entry_price) * dir_sign * CONTRACT_SIZE
    net = gross - RT_COST
    return {
        "direction": direction, "entry": entry_price, "exit": exit_price,
        "atr": atr, "exit_reason": exit_reason,
        "gross": gross, "net": net,
    }


def backtest_variant(bars_5m: pd.DataFrame, df: pd.DataFrame, weeks: list,
                       rule: TrailRule, v2_filter: pd.Series | None = None) -> list[dict]:
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

        # Slice 5m bars for this week (mon 00:00 to fri 23:59)
        week_start = mon
        week_end = fri + pd.Timedelta(hours=23, minutes=59)
        week_5m = bars_5m.loc[week_start:week_end]
        if len(week_5m) == 0:
            continue

        result = simulate_week_5m(week_5m, direction, entry_price, atr, rule)
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
        "trail_pct": reasons.get("trail_stop", 0) / n,
        "time_pct": reasons.get("time", 0) / n,
        "sharpe": sharpe_ann, "cum": cum_final, "max_dd": max_dd,
    }


def print_table(summaries: list[dict], header: str):
    print(f"\n=== {header} ===")
    print(f"  {'variant':<24} {'n':>4}  {'WR':>6}  {'stop%':>6}  {'trail%':>6}  {'time%':>6}  {'Sharpe':>7}  {'cum $':>10}  {'maxDD':>10}")
    for s in summaries:
        if s["n"] == 0:
            print(f"  {s['label']:<24} (no trades)"); continue
        print(f"  {s['label']:<24} {s['n']:>4}  {s['wr']*100:>5.1f}%  "
              f"{s['stop_pct']*100:>5.1f}%  {s['trail_pct']*100:>5.1f}%  "
              f"{s['time_pct']*100:>5.1f}%  {s['sharpe']:>7.2f}  "
              f"${s['cum']:>9,.0f}  ${s['max_dd']:>9,.0f}")


def load_v2_filter(df: pd.DataFrame) -> pd.Series:
    dxy_path = far_backtest.ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"
    dxy = far_backtest.load_macro_series(dxy_path, "dxy")
    dxy_daily = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                              method="ffill")
    dxy_daily.index = df.index
    dxy_20d_chg = dxy_daily.pct_change(20) * 100
    long_ok = (df["direction"] == "LONG") & (dxy_20d_chg < 0)
    short_ok = (df["direction"] == "SHORT") & (dxy_20d_chg > 0)
    return long_ok | short_ok


def main():
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-07-01", tz="UTC")

    print(f"Loading daily bars for signal computation...")
    daily = far_backtest.load_daily_bars(start, end)
    ry = far_backtest.load_macro_series(far_backtest.RY, "real_yield_10y")
    df = far_backtest.build_signals(daily, ry)
    df = df[(df.index >= start) & (df.index <= end)]
    weeks = far_backtest.week_indices(df)
    print(f"  {len(df)} daily bars, {len(weeks)} weeks")

    print(f"Loading 5m XAUUSD bars (this takes ~10s)...")
    bars_5m = load_5m_bars()
    print(f"  {len(bars_5m):,} 5m bars from {bars_5m.index.min()} to {bars_5m.index.max()}")

    v2_filter = load_v2_filter(df)

    print(f"\nRunning {len(VARIANTS)} variants on v1 signal set...")
    v1_summaries = []
    for rule in VARIANTS:
        trades = backtest_variant(bars_5m, df, weeks, rule, v2_filter=None)
        v1_summaries.append(summarize(trades, rule.name))
        print(f"  {rule.name}: n={len(trades)}")

    print(f"\nRunning {len(VARIANTS)} variants on v2 signal set...")
    v2_summaries = []
    for rule in VARIANTS:
        trades = backtest_variant(bars_5m, df, weeks, rule, v2_filter=v2_filter)
        v2_summaries.append(summarize(trades, rule.name))
        print(f"  {rule.name}: n={len(trades)}")

    print_table(v1_summaries, "v1 signal set (all directional)")
    print_table(v2_summaries, "v2 signal set (DXY-confirmed)")

    print("\n=== Ranking by Sharpe ===")
    for label, sums in [("v1", v1_summaries), ("v2", v2_summaries)]:
        ranked = sorted([s for s in sums if s["n"] > 0], key=lambda s: -s["sharpe"])
        print(f"\n  {label}:")
        for i, s in enumerate(ranked, 1):
            print(f"    {i}. {s['label']:<24} Sharpe {s['sharpe']:.2f}  cum ${s['cum']:>9,.0f}  DD ${s['max_dd']:>9,.0f}")


if __name__ == "__main__":
    main()
