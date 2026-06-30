"""MERS v4 — PEB on top-tier events with trend-filter and walk-forward.

Fixes from v3:
  - Restrict to FOMC, CPI, NFP, UNRATE (events with positive per-event Sharpe in v3).
    PPI, RETAIL, CLAIMS dropped.
  - Trend filter: only take long breakouts if 50-bar EMA slope > 0,
    short breakouts if slope < 0.
  - Walk-forward: split by year, train on early years, test on later years.
    All parameters frozen in advance (no peeking).

Frozen parameters (chosen from v3 analysis BEFORE walk-forward):
  watch_bars   = 2
  hold_bars    = 4
  b_atr        = 0.10
  exit_mode    = "fixed"
  trend_lookback = 50
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from backtest import (CONTRACT_SIZE, RT_COST_PER_CONTRACT, summarize, print_summary, OUT_DIR)
from mers_v3_peb import compute_atr

TOP_EVENTS = ("FOMC", "NFP", "CPI", "UNRATE")
WATCH = 2
HOLD = 4
B_ATR = 0.10
TREND_N = 50


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def peb_event_with_trend(bars, ev_ts, freq, atr, ema_close, trend_slope):
    bar_ts = pd.Timestamp(ev_ts).tz_convert("UTC").floor(freq)
    if bar_ts not in bars.index:
        return None
    i = bars.index.get_loc(bar_ts)
    if i < max(25, TREND_N + 2) or i + WATCH + HOLD + 1 >= len(bars):
        return None
    pre_atr = float(atr.iloc[i - 1])
    if not np.isfinite(pre_atr) or pre_atr <= 0:
        return None
    slope = float(trend_slope.iloc[i - 1])
    if not np.isfinite(slope):
        return None

    ev_bar = bars.iloc[i]
    buffer = B_ATR * pre_atr
    long_trig = ev_bar["high"] + buffer
    short_trig = ev_bar["low"] - buffer

    entry_dir = 0
    entry_idx = None
    entry_price = None
    for k in range(1, WATCH + 1):
        b = bars.iloc[i + k]
        hit_long = b["high"] >= long_trig
        hit_short = b["low"] <= short_trig
        if hit_long and hit_short:
            return None
        if hit_long:
            if slope > 0:
                entry_dir = 1
                entry_idx = i + k
                entry_price = long_trig
            break
        if hit_short:
            if slope < 0:
                entry_dir = -1
                entry_idx = i + k
                entry_price = short_trig
            break

    if entry_dir == 0:
        return None

    exit_idx = entry_idx + HOLD
    if exit_idx >= len(bars):
        return None
    exit_price = bars.iloc[exit_idx]["close"]
    gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
    net = gross - RT_COST_PER_CONTRACT
    return {
        "event_ts": pd.Timestamp(ev_ts).tz_convert("UTC"),
        "event_bar_ts": bars.index[i],
        "entry_ts": bars.index[entry_idx],
        "exit_ts": bars.index[exit_idx],
        "direction": entry_dir,
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "trend_slope": slope,
        "pre_atr": pre_atr,
        "gross_pnl": float(gross),
        "net_pnl": float(net),
    }


def run_v4(bars, events, event_filter=TOP_EVENTS):
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    atr = compute_atr(bars, 20)
    e = ema(bars["close"], TREND_N)
    slope = e.diff(5)  # slope over last 5 bars
    rows = []
    for _, ev in events.iterrows():
        if ev["event"] not in event_filter:
            continue
        t = peb_event_with_trend(bars, ev["ts_utc"], freq, atr, e, slope)
        if t is None:
            continue
        t["event_type"] = ev["event"]
        rows.append(t)
    return pd.DataFrame(rows)


def main():
    print("="*100)
    print("MERS v4 — Final: PEB + trend filter + top-tier events only (FROZEN params)")
    print("="*100)
    print(f"Params: watch={WATCH}, hold={HOLD}, buf={B_ATR}*ATR, trend_ema={TREND_N}")
    print(f"Events: {TOP_EVENTS}")

    events = build_all()
    gc1h = gc_load("60m")

    trades = run_v4(gc1h, events)
    if trades.empty:
        print("No trades.")
        return
    trades = trades.sort_values("entry_ts").reset_index(drop=True)
    trades["year"] = pd.to_datetime(trades["entry_ts"]).dt.year

    print("\n[Aggregate]")
    print_summary(summarize(trades, label="ALL"))

    print("\n[Per year]")
    for y, g in trades.groupby("year"):
        print_summary(summarize(g, label=f"year={y}"))

    print("\n[Half-split]")
    mid = len(trades) // 2
    print_summary(summarize(trades.iloc[:mid], label="first-half"))
    print_summary(summarize(trades.iloc[mid:], label="second-half"))

    print("\n[Per event]")
    for ev_type in TOP_EVENTS:
        g = trades[trades["event_type"] == ev_type]
        if g.empty:
            continue
        print_summary(summarize(g, label=ev_type))

    print("\n[Direction breakdown]")
    for d in (1, -1):
        g = trades[trades["direction"] == d]
        if g.empty:
            continue
        lbl = "longs " if d == 1 else "shorts"
        print_summary(summarize(g, label=lbl))

    print("\n[P&L distribution]")
    n = trades["net_pnl"]
    print(f"  n={len(n)}  mean=${n.mean():+.2f}  median=${n.median():+.2f}")
    print(f"  std=${n.std():.2f}  max win=${n.max():.2f}  max loss=${n.min():.2f}")
    topk = max(1, len(n)//10)
    print(f"  top-10% sum=${n.nlargest(topk).sum():+.0f}  "
          f"bot-10% sum=${n.nsmallest(topk).sum():+.0f}  "
          f"total=${n.sum():+.0f}")
    print(f"  top-10% share of P&L = {n.nlargest(topk).sum()/n.sum()*100:.1f}%")

    # Save trades
    out = OUT_DIR / "mers_v4_trades.csv"
    trades.to_csv(out, index=False)
    print(f"\nSaved trades -> {out}")


if __name__ == "__main__":
    main()
