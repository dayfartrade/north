"""MERS v5 on 5-minute bars.

Why: events happen at minute precision (8:30:00 ET, 14:00:00 ET). The 1h bar
spans 60 min, so it captures the move but mixes pre- and post-event price.
On 5m bars we can:
  - Define "event bar" as the 5-minute bar containing the release timestamp
  - Get a cleaner directional signal in the immediate post-release minutes
  - Validate the edge survives at finer resolution

Trade-off: only ~60 days of 5m data available from yfinance (vs 2y of 1h).

Adapted v5 parameters for 5m bars:
  watch_bars   = 4   (~20 min watching for breakout)
  max_hold     = 24  (~2 hr max hold)
  b_atr        = 0.10
  stop_mult    = 1.0
  tp_mult      = 2.0
  trend_n      = 50  (now 50 × 5min = 4 hr trend)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v5 import peb_event_v5, dedupe_co_released, TOP_EVENTS_V5
from mers_v3_peb import compute_atr
from backtest import summarize, print_summary, CONTRACT_SIZE


def run_v5_5m(bars, events,
              watch_bars=4, max_hold=24, b_atr=0.10,
              stop_mult=1.0, tp_mult=2.0, trend_n=50):
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=trend_n, adjust=False).mean()
    slope = ema.diff(5)

    events = dedupe_co_released(events)
    rows = []
    for _, ev in events.iterrows():
        if ev["event"] not in TOP_EVENTS_V5:
            continue
        t = peb_event_v5(bars, ev["ts_utc"], freq, atr, slope,
                         watch=watch_bars, max_hold=max_hold, b_atr=b_atr,
                         stop_mult=stop_mult, tp_mult=tp_mult)
        if t is None:
            continue
        t["event_type"] = ev["event"]
        rows.append(t)
    return pd.DataFrame(rows)


def main():
    print("="*100)
    print("MERS v5 on 5-minute bars (60-day window)")
    print("="*100)
    events = build_all()
    bars5 = gc_load("5m")

    # Default sweep
    print("\nSweep over watch/max_hold (5m units):")
    print(f"{'watch':>5s} {'hold':>4s} {'n':>3s} {'win%':>6s} {'mean_$':>10s} {'total_$':>10s} {'sharpe':>7s}")
    best = None
    for watch in (2, 4, 6, 12):
        for hold in (6, 12, 18, 24, 36, 48):
            trades = run_v5_5m(bars5, events, watch_bars=watch, max_hold=hold)
            s = summarize(trades, label=f"w={watch}|h={hold}")
            if s["n"] >= 3:
                print(f"{watch:5d} {hold:4d} {s['n']:3d} {s['win_rate']*100:6.1f} "
                      f"{s['mean_net_pnl']:+10.2f} {s['total_net_pnl']:+10.0f} {s['sharpe_per_trade']:+7.2f}")
                if best is None or s["total_net_pnl"] > best["total_net_pnl"]:
                    best = s

    # Detail on default config
    print("\nDefault config detail (watch=4, hold=24):")
    trades = run_v5_5m(bars5, events)
    if not trades.empty:
        print_summary(summarize(trades, label="ALL"))
        for ev_type in TOP_EVENTS_V5:
            sub = trades[trades["event_type"] == ev_type]
            if sub.empty: continue
            print_summary(summarize(sub, label=ev_type))


if __name__ == "__main__":
    main()
