"""MERS v3 — Post-Event Breakout (PEB).

Logic (per event):
  1. Wait for the event bar to close. event_bar = bar that contains the release ts.
  2. Record [ev_high, ev_low] of that bar.
  3. In the next K bars, monitor:
     - If price prints high > ev_high + buffer  -> enter LONG at that level
     - If price prints low  < ev_low  - buffer  -> enter SHORT at that level
     - If both, take whichever happened first in time order (we approximate with
       the bar where the break occurred; if same bar, skip).
  4. Exit logic (parameter):
     - "fixed":   hold for H bars after entry, exit at close
     - "atr_stop": stop = entry +/- stop_atr * ATR(20), target = entry +/- tp_atr * ATR
  5. Buffer = b_atr * ATR(20) of bars BEFORE the event (no look-ahead).

This exploits the documented vol expansion without requiring direction prediction.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from backtest import (CONTRACT_SIZE, RT_COST_PER_CONTRACT, OUT_DIR,
                       summarize, print_summary)

EVENTS_INC = ("FOMC", "NFP", "CPI", "PPI", "RETAIL", "UNRATE", "CLAIMS")


def compute_atr(bars: pd.DataFrame, n: int = 20) -> pd.Series:
    high = bars["high"]
    low = bars["low"]
    close = bars["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=5).mean()


def peb_trade_one(bars, ev_ts, freq, watch_bars, hold_bars,
                   b_atr, exit_mode, stop_atr, tp_atr, atr):
    """Simulate one event's PEB attempt. Returns trade dict or None."""
    bar_ts = pd.Timestamp(ev_ts).tz_convert("UTC").floor(freq)
    if bar_ts not in bars.index:
        return None
    i = bars.index.get_loc(bar_ts)
    if i < 25 or i + watch_bars + hold_bars + 1 >= len(bars):
        return None
    ev_bar = bars.iloc[i]
    pre_atr = float(atr.iloc[i - 1])
    if not np.isfinite(pre_atr) or pre_atr <= 0:
        return None
    buffer = b_atr * pre_atr
    long_trig = ev_bar["high"] + buffer
    short_trig = ev_bar["low"] - buffer

    # Look forward up to watch_bars for the first trigger
    entry_dir = 0
    entry_idx = None
    entry_price = None
    for k in range(1, watch_bars + 1):
        b = bars.iloc[i + k]
        hit_long = b["high"] >= long_trig
        hit_short = b["low"] <= short_trig
        if hit_long and hit_short:
            # both touched in same bar — assume worst-case: skip (can't tell order)
            return None
        if hit_long:
            entry_dir = 1
            entry_idx = i + k
            entry_price = long_trig
            break
        if hit_short:
            entry_dir = -1
            entry_idx = i + k
            entry_price = short_trig
            break
    if entry_dir == 0:
        return None

    # Exit logic
    if exit_mode == "fixed":
        exit_idx = entry_idx + hold_bars
        if exit_idx >= len(bars):
            return None
        exit_price = bars.iloc[exit_idx]["close"]
        exit_reason = "time"
    elif exit_mode == "atr_stop":
        stop = entry_price - stop_atr * pre_atr * entry_dir
        target = entry_price + tp_atr * pre_atr * entry_dir
        exit_price = None
        exit_idx = None
        for k in range(0, hold_bars + 1):
            if entry_idx + k >= len(bars):
                break
            b = bars.iloc[entry_idx + k]
            if entry_dir == 1:
                if b["low"] <= stop:
                    exit_price = stop
                    exit_idx = entry_idx + k
                    exit_reason = "stop"
                    break
                if b["high"] >= target:
                    exit_price = target
                    exit_idx = entry_idx + k
                    exit_reason = "target"
                    break
            else:
                if b["high"] >= stop:
                    exit_price = stop
                    exit_idx = entry_idx + k
                    exit_reason = "stop"
                    break
                if b["low"] <= target:
                    exit_price = target
                    exit_idx = entry_idx + k
                    exit_reason = "target"
                    break
        if exit_price is None:
            ix = min(entry_idx + hold_bars, len(bars) - 1)
            exit_price = bars.iloc[ix]["close"]
            exit_idx = ix
            exit_reason = "time"
    else:
        raise ValueError(exit_mode)

    gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
    net = gross - RT_COST_PER_CONTRACT
    return {
        "event_ts": ev_ts,
        "event_bar_ts": bars.index[i],
        "entry_ts": bars.index[entry_idx],
        "exit_ts": bars.index[exit_idx],
        "direction": entry_dir,
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "buffer": float(buffer),
        "pre_atr": pre_atr,
        "gross_pnl": float(gross),
        "net_pnl": float(net),
        "exit_reason": exit_reason,
    }


def run_peb(bars, events, watch_bars=2, hold_bars=2, b_atr=0.25,
            exit_mode="fixed", stop_atr=1.5, tp_atr=2.0,
            event_filter=EVENTS_INC):
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    atr = compute_atr(bars, 20)
    rows = []
    for _, ev in events.iterrows():
        if ev["event"] not in event_filter:
            continue
        t = peb_trade_one(bars, ev["ts_utc"], freq, watch_bars, hold_bars,
                          b_atr, exit_mode, stop_atr, tp_atr, atr)
        if t is None:
            continue
        t["event_type"] = ev["event"]
        rows.append(t)
    return pd.DataFrame(rows)


def main():
    print("="*100)
    print("MERS v3 — Post-Event Breakout (direction-agnostic)")
    print("="*100)

    events = build_all()
    gc1h = gc_load("60m")

    print("\n--- Fixed-hold exit, parameter sweep ---")
    results = []
    for watch in (1, 2, 3):
        for hold in (1, 2, 3, 4):
            for b_atr in (0.10, 0.25, 0.50):
                trades = run_peb(gc1h, events, watch_bars=watch, hold_bars=hold,
                                 b_atr=b_atr, exit_mode="fixed")
                s = summarize(trades, label=f"watch={watch}|hold={hold}|buf={b_atr}")
                if s["n"] >= 20:
                    results.append(s)
    for s in sorted(results, key=lambda x: -x["total_net_pnl"])[:12]:
        print_summary(s)

    print("\n--- ATR stop/target exit, parameter sweep ---")
    results2 = []
    for watch in (1, 2, 3):
        for hold in (4, 6):
            for b_atr in (0.10, 0.25):
                for stop in (1.0, 1.5, 2.0):
                    for tp in (1.5, 2.0, 3.0):
                        trades = run_peb(gc1h, events, watch_bars=watch, hold_bars=hold,
                                         b_atr=b_atr, exit_mode="atr_stop",
                                         stop_atr=stop, tp_atr=tp)
                        s = summarize(trades, label=f"w={watch}|h={hold}|b={b_atr}|s={stop}|t={tp}")
                        if s["n"] >= 20:
                            results2.append(s)
    for s in sorted(results2, key=lambda x: -x["total_net_pnl"])[:12]:
        print_summary(s)

    # Best config: drill in
    print("\n--- Detail for the leader (split halves + per-event) ---")
    if results:
        best = max(results, key=lambda x: x["total_net_pnl"])
    else:
        return
    parts = best["label"].split("|")
    watch = int(parts[0].split("=")[1])
    hold = int(parts[1].split("=")[1])
    b_atr = float(parts[2].split("=")[1])
    trades = run_peb(gc1h, events, watch_bars=watch, hold_bars=hold,
                     b_atr=b_atr, exit_mode="fixed")
    trades = trades.sort_values("entry_ts").reset_index(drop=True)
    print(f"\nLeader: {best['label']}")
    print_summary(summarize(trades, label="ALL"))
    mid = len(trades) // 2
    print_summary(summarize(trades.iloc[:mid], label="first-half"))
    print_summary(summarize(trades.iloc[mid:], label="second-half"))
    trades["year"] = pd.to_datetime(trades["entry_ts"]).dt.year
    for y, g in trades.groupby("year"):
        print_summary(summarize(g, label=f"year={y}"))
    print("\nPer-event:")
    for ev_type in EVENTS_INC:
        g = trades[trades["event_type"] == ev_type]
        if g.empty:
            continue
        print_summary(summarize(g, label=ev_type))


if __name__ == "__main__":
    main()
