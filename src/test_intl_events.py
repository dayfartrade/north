"""Backtest MERS v5 PEB+trend logic on ECB and BoE events to see if edge transfers."""
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from mers_v5 import run_v5
from events_intl import build_ecb, build_boe, build_intl_all
from backtest import summarize, print_summary

# We need to make these events pass through the v5 filter, so set "TOP_EVENTS_V5"
# temporarily by patching the global. Cleaner: build a mini events df with these
# events and run a custom v5 invocation.

from mers_v5 import peb_event_v5, dedupe_co_released
from mers_v3_peb import compute_atr
TREND_N = 50


def run_v5_custom(bars, events, event_filter):
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=TREND_N, adjust=False).mean()
    slope = ema.diff(5)
    rows = []
    for _, ev in events.iterrows():
        if ev["event"] not in event_filter:
            continue
        t = peb_event_v5(bars, ev["ts_utc"], freq, atr, slope)
        if t is None:
            continue
        t["event_type"] = ev["event"]
        rows.append(t)
    return pd.DataFrame(rows)


def main():
    bars = gc_load("60m")
    ecb = build_ecb()
    boe = build_boe()

    print("ECB rate decisions:")
    trades = run_v5_custom(bars, ecb, event_filter=("ECB",))
    print_summary(summarize(trades, label="ECB all"))
    if not trades.empty:
        for d in (1, -1):
            sub = trades[trades["direction"] == d]
            if sub.empty: continue
            print_summary(summarize(sub, label=f"ECB {'long' if d==1 else 'short'}"))

    print("\nBoE rate decisions:")
    trades = run_v5_custom(bars, boe, event_filter=("BOE",))
    print_summary(summarize(trades, label="BOE all"))
    if not trades.empty:
        for d in (1, -1):
            sub = trades[trades["direction"] == d]
            if sub.empty: continue
            print_summary(summarize(sub, label=f"BOE {'long' if d==1 else 'short'}"))


if __name__ == "__main__":
    main()
