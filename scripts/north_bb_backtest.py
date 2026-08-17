"""NORTH-BB backtest.

Same v1 signal (M20/M60/MA10-40/RY_chg) but replaces the fixed calendar
entry/exit with Bollinger Band based entry/exit on 4H XAUUSD.

Entry rule
----------
* Signal fires Friday close for the following Monday-Friday.
* LONG: after Monday 00:00 UTC, wait for first 4H bar whose low <= lower BB(20,2).
  Enter at that bar's close.
* SHORT: mirror on upper BB.
* Fallback: if no touch within 48 hours after Monday 00:00 UTC,
  enter at the close of the 48h-mark 4H bar (Wednesday ~00:00 UTC).

Exit rule
---------
* LONG exit: first 4H bar (after entry) whose high >= upper BB(20,2).
  Exit at that bar's close.
* SHORT exit: mirror on lower BB.
* Stop: 2x ATR(daily, 20) applied to actual entry price, checked
  intra-4H via bar high/low.
* Fallback exit: Friday 21:00 UTC close.

Cost model matches v1: $5 round trip per contract, 100 oz per contract.

Compare against v1 with `scripts/north_v1_vs_bb_compare.py`.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "far", str(ROOT / "scripts" / "far_weekly_gold_read.py")
)
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

from tools.analysis_helpers import bollinger_bands
from tools.bootstrap_stats import evaluate_signal

BB_PERIOD = 20
BB_STD = 2.0
ENTRY_WINDOW_HOURS = 48
WEEK_END_HOUR_UTC = 21
CONTRACT_SIZE = 100
RT_COST = 5.0
STOP_ATR_MULT = 2.0


def load_intraday_5m() -> pd.DataFrame:
    """Concatenate all Dukascopy XAUUSD 5m files, dedup, sort."""
    paths = [far.EARLY_5M, far.HISTORICAL_5M, far.LIVE_5M]
    dfs = []
    for path in paths:
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["ts"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        dfs.append(df)
    combined = (
        pd.concat(dfs, ignore_index=True)
        .drop_duplicates(subset=["ts"], keep="first")
        .sort_values("ts")
        .set_index("ts")
    )
    return combined


def resample_to_4h(bars_5m: pd.DataFrame) -> pd.DataFrame:
    """Resample 5m bars to 4H OHLC. Bars labeled by their start time."""
    agg = bars_5m.resample("4h", origin="epoch", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return agg.dropna(subset=["open", "high", "low", "close"])


def attach_bollinger(bars_4h: pd.DataFrame) -> pd.DataFrame:
    """Add lower/middle/upper BB columns computed on close."""
    closes = bars_4h["close"].tolist()
    upper, middle, lower = bollinger_bands(closes, BB_PERIOD, BB_STD)
    df = bars_4h.copy()
    df["bb_upper"] = upper
    df["bb_middle"] = middle
    df["bb_lower"] = lower
    return df


def simulate_bb_week(
    bars_4h: pd.DataFrame,
    mon: pd.Timestamp,
    fri: pd.Timestamp,
    direction: str,
    atr_daily: float,
) -> dict | None:
    """Simulate one BB-based trade for a given signal week.

    Returns a dict with entry/exit details, or None if we could not fill.
    """
    entry_start = mon.tz_convert("UTC").normalize()
    entry_deadline = entry_start + pd.Timedelta(hours=ENTRY_WINDOW_HOURS)
    week_end = fri.tz_convert("UTC").normalize() + pd.Timedelta(hours=WEEK_END_HOUR_UTC)

    entry_window = bars_4h[(bars_4h.index >= entry_start) & (bars_4h.index < entry_deadline)]
    if entry_window.empty:
        return None

    entry_bar = None
    entry_reason = None
    for ts, row in entry_window.iterrows():
        if pd.isna(row["bb_lower"]) or pd.isna(row["bb_upper"]):
            continue
        if direction == "LONG" and float(row["low"]) <= float(row["bb_lower"]):
            entry_bar = (ts, row)
            entry_reason = "bb_touch"
            break
        if direction == "SHORT" and float(row["high"]) >= float(row["bb_upper"]):
            entry_bar = (ts, row)
            entry_reason = "bb_touch"
            break

    if entry_bar is None:
        fallback_slice = entry_window[entry_window.index <= entry_deadline]
        if fallback_slice.empty:
            return None
        ts = fallback_slice.index[-1]
        row = fallback_slice.iloc[-1]
        if pd.isna(row["bb_lower"]) or pd.isna(row["bb_upper"]):
            return None
        entry_bar = (ts, row)
        entry_reason = "fallback_48h"

    entry_ts, entry_row = entry_bar
    entry_price = float(entry_row["close"])

    if direction == "LONG":
        stop_price = entry_price - STOP_ATR_MULT * atr_daily
    else:
        stop_price = entry_price + STOP_ATR_MULT * atr_daily

    exit_window = bars_4h[(bars_4h.index > entry_ts) & (bars_4h.index <= week_end)]
    exit_price = None
    exit_reason = None
    exit_ts = None
    for ts, row in exit_window.iterrows():
        if direction == "LONG":
            if float(row["low"]) <= stop_price:
                exit_price = stop_price
                exit_reason = "stop"
                exit_ts = ts
                break
            if not pd.isna(row["bb_upper"]) and float(row["high"]) >= float(row["bb_upper"]):
                exit_price = float(row["close"])
                exit_reason = "bb_target"
                exit_ts = ts
                break
        else:
            if float(row["high"]) >= stop_price:
                exit_price = stop_price
                exit_reason = "stop"
                exit_ts = ts
                break
            if not pd.isna(row["bb_lower"]) and float(row["low"]) <= float(row["bb_lower"]):
                exit_price = float(row["close"])
                exit_reason = "bb_target"
                exit_ts = ts
                break

    if exit_price is None:
        if exit_window.empty:
            return None
        exit_price = float(exit_window.iloc[-1]["close"])
        exit_reason = "time"
        exit_ts = exit_window.index[-1]

    dir_sign = 1 if direction == "LONG" else -1
    gross = (exit_price - entry_price) * dir_sign * CONTRACT_SIZE
    net = gross - RT_COST
    return {
        "week_start": mon,
        "week_end": fri,
        "direction": direction,
        "entry_ts": entry_ts,
        "entry_price": entry_price,
        "entry_reason": entry_reason,
        "exit_ts": exit_ts,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "stop_price": stop_price,
        "gross": gross,
        "net": net,
    }


def backtest(start: pd.Timestamp, end: pd.Timestamp) -> dict:
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    signals = far.build_signals(daily, ry)
    signals = signals[(signals.index >= start) & (signals.index <= end)]
    weeks = far.week_indices(signals)

    bars_5m = load_intraday_5m()
    bars_5m = bars_5m[(bars_5m.index >= start - pd.Timedelta(days=30)) & (bars_5m.index <= end + pd.Timedelta(days=7))]
    bars_4h = resample_to_4h(bars_5m)
    bars_4h = attach_bollinger(bars_4h)

    trades = []
    unfilled = 0
    flat_weeks = 0
    for signal_date, mon, fri in weeks:
        if signal_date not in signals.index:
            continue
        sig_row = signals.loc[signal_date]
        direction = sig_row["direction"]
        if direction == "FLAT":
            flat_weeks += 1
            continue
        if pd.isna(sig_row["ATR"]) or pd.isna(sig_row["M60"]):
            continue
        atr_daily = float(sig_row["ATR"])
        if atr_daily <= 0:
            continue
        result = simulate_bb_week(bars_4h, mon, fri, direction, atr_daily)
        if result is None:
            unfilled += 1
            continue
        result["signal_date"] = signal_date
        result["atr_daily"] = atr_daily
        trades.append(result)
    return {
        "trades": trades,
        "flat_weeks": flat_weeks,
        "unfilled": unfilled,
        "total_weeks": len(weeks),
    }


def summarize(trades: list[dict], label: str) -> dict:
    if not trades:
        return {"label": label, "n": 0}
    n = len(trades)
    pnls = [t["net"] for t in trades]
    returns_pct = [t["net"] / (t["entry_price"] * CONTRACT_SIZE) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    mean = total / n
    mean_r = sum(returns_pct) / n
    if n > 1:
        var_r = sum((r - mean_r) ** 2 for r in returns_pct) / (n - 1)
        std_r = var_r ** 0.5
    else:
        std_r = 0.0
    sharpe_ann = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0

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
    positive_years = sum(1 for y, tp in by_year.items() if sum(tp) > 0)

    boot = evaluate_signal(label, returns_pct, ci_lower_threshold=0.005)

    return {
        "label": label,
        "n": n,
        "wins": wins,
        "win_rate": wins / n,
        "total_pnl": total,
        "mean_pnl_per_trade": mean,
        "mean_return_pct": mean_r,
        "std_return_pct": std_r,
        "sharpe_ann": sharpe_ann,
        "max_drawdown_dollars": max_dd,
        "years_traded": len(by_year),
        "positive_years": positive_years,
        "bootstrap_ci_low_pct": boot.ci_low,
        "bootstrap_ci_high_pct": boot.ci_high,
        "bootstrap_verdict": boot.verdict,
        "p_raw": boot.p_raw,
    }


def print_summary(summary: dict) -> None:
    n = summary.get("n", 0)
    if n == 0:
        print(f"  {summary['label']}: no trades")
        return
    print(f"  {summary['label']}:  n={n}  WR={100*summary['win_rate']:.1f}%")
    print(f"    total P&L:        ${summary['total_pnl']:+,.0f}")
    print(f"    mean $/trade:     ${summary['mean_pnl_per_trade']:+,.0f}")
    print(f"    mean R:           {100*summary['mean_return_pct']:+.3f}%")
    print(f"    Sharpe (ann):     {summary['sharpe_ann']:+.3f}")
    print(f"    max DD:           ${summary['max_drawdown_dollars']:,.0f}")
    print(f"    positive years:   {summary['positive_years']}/{summary['years_traded']}")
    print(f"    bootstrap 95% CI: [{100*summary['bootstrap_ci_low_pct']:+.3f}%, "
          f"{100*summary['bootstrap_ci_high_pct']:+.3f}%]  verdict={summary['bootstrap_verdict']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-07-20")
    ap.add_argument("--json-out", help="Write trades and summary to this JSON path")
    args = ap.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    print(f"NORTH-BB backtest: {args.start} to {args.end}")
    print("Signal source: v1 (unchanged)")
    print(f"Entry/exit: BB({BB_PERIOD},{BB_STD}) on 4H XAUUSD")
    print(f"Entry fallback: {ENTRY_WINDOW_HOURS}h  Time fallback exit: Fri {WEEK_END_HOUR_UTC}:00 UTC")
    print()

    r = backtest(start, end)
    print(f"Signal weeks total: {r['total_weeks']}")
    print(f"FLAT weeks:         {r['flat_weeks']}  ({100*r['flat_weeks']/max(r['total_weeks'],1):.0f}%)")
    print(f"Directional weeks:  {r['total_weeks'] - r['flat_weeks']}")
    print(f"Unfilled (missing 4H data): {r['unfilled']}")
    print(f"Trades executed:    {len(r['trades'])}")
    print()

    all_summary = summarize(r["trades"], "all")
    long_summary = summarize([t for t in r["trades"] if t["direction"] == "LONG"], "long")
    short_summary = summarize([t for t in r["trades"] if t["direction"] == "SHORT"], "short")

    print_summary(all_summary)
    print()
    print_summary(long_summary)
    print()
    print_summary(short_summary)
    print()

    print("Exit reason breakdown:")
    reason_counts = defaultdict(int)
    for t in r["trades"]:
        reason_counts[t["exit_reason"]] += 1
    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")

    print("\nEntry reason breakdown:")
    entry_counts = defaultdict(int)
    for t in r["trades"]:
        entry_counts[t["entry_reason"]] += 1
    for reason, count in sorted(entry_counts.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")

    if args.json_out:
        payload = {
            "params": {
                "start": args.start,
                "end": args.end,
                "bb_period": BB_PERIOD,
                "bb_std": BB_STD,
                "entry_window_hours": ENTRY_WINDOW_HOURS,
                "stop_atr_mult": STOP_ATR_MULT,
                "rt_cost": RT_COST,
            },
            "summary_all": all_summary,
            "summary_long": long_summary,
            "summary_short": short_summary,
            "trades": [
                {
                    "week_start": str(t["week_start"]),
                    "signal_date": str(t["signal_date"]),
                    "direction": t["direction"],
                    "entry_ts": str(t["entry_ts"]),
                    "entry_price": t["entry_price"],
                    "entry_reason": t["entry_reason"],
                    "exit_ts": str(t["exit_ts"]),
                    "exit_price": t["exit_price"],
                    "exit_reason": t["exit_reason"],
                    "stop_price": t["stop_price"],
                    "net": t["net"],
                }
                for t in r["trades"]
            ],
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nWrote {args.json_out}")


if __name__ == "__main__":
    main()
