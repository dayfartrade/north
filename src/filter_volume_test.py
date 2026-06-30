"""Filter-improvement test: does event-bar VOLUME confirm signal quality?

Hypothesis: breakouts on high-volume event bars are more likely to continue.

Test: condition on event-bar volume >= K * trailing_median_volume for various K.
If the edge improves only with very strict K, it's likely fitting; if it improves
robustly across K thresholds, it's a real refinement.
"""
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v5 import run_v5, peb_event_v5, dedupe_co_released, TOP_EVENTS_V5, TREND_N
from mers_v3_peb import compute_atr
from backtest import summarize, print_summary


def run_v5_with_volume(bars, events, vol_mult=1.0, lookback=24*5):
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=TREND_N, adjust=False).mean()
    slope = ema.diff(5)
    vol_med = bars["volume"].rolling(lookback, min_periods=10).median()

    events = dedupe_co_released(events)
    rows = []
    for _, ev in events.iterrows():
        if ev["event"] not in TOP_EVENTS_V5:
            continue
        ts = pd.Timestamp(ev["ts_utc"]).tz_convert("UTC").floor(freq)
        if ts not in bars.index:
            continue
        i = bars.index.get_loc(ts)
        ev_vol = bars.iloc[i]["volume"]
        ref_vol = vol_med.iloc[i - 1] if i > 0 else np.nan
        if pd.isna(ref_vol) or ref_vol == 0:
            continue
        if ev_vol < vol_mult * ref_vol:
            continue  # filter out low-volume event bars
        t = peb_event_v5(bars, ev["ts_utc"], freq, atr, slope)
        if t is None:
            continue
        t["event_type"] = ev["event"]
        t["ev_vol"] = float(ev_vol)
        t["ref_vol"] = float(ref_vol)
        t["vol_ratio"] = float(ev_vol / ref_vol)
        rows.append(t)
    return pd.DataFrame(rows)


def main():
    bars = gc_load("60m")
    events = build_all()

    # Check that GC volume is present
    if "volume" not in bars.columns or bars["volume"].sum() == 0:
        print("No volume data on GC bars — skipping volume filter.")
        return

    print("Sweep over event-bar volume filter multiplier:")
    print(f"{'vol_mult':>9s} {'n':>4s} {'win%':>6s} {'mean_$':>10s} {'total_$':>10s} {'sharpe':>7s} {'PF':>5s}")
    base = run_v5_with_volume(bars, events, vol_mult=0.0)
    s = summarize(base, label="baseline (no filter)")
    print(f"{0.0:9.2f} {s['n']:4d} {s['win_rate']*100:6.1f} {s['mean_net_pnl']:+10.2f} "
          f"{s['total_net_pnl']:+10.0f} {s['sharpe_per_trade']:+7.2f} {s['profit_factor']:5.2f}")
    for k in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
        trades = run_v5_with_volume(bars, events, vol_mult=k)
        s = summarize(trades, label=f"vol>={k}*med")
        if s["n"] == 0:
            print(f"{k:9.2f}   0  --     --        --       --     --")
            continue
        print(f"{k:9.2f} {s['n']:4d} {s['win_rate']*100:6.1f} {s['mean_net_pnl']:+10.2f} "
              f"{s['total_net_pnl']:+10.0f} {s['sharpe_per_trade']:+7.2f} {s['profit_factor']:5.2f}")


if __name__ == "__main__":
    main()
