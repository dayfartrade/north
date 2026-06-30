"""Sanity check: do the constructed event timestamps actually align with GC volatility?

We pick the recent FOMC dates and NFP dates, look at the 1h GC bars around them,
and compute the post-event hour's true-range vs the trailing 24h average.
If our timestamps are correct, the post-event hour should have outsized range.
"""
from __future__ import annotations
import pandas as pd
import numpy as np

from data_gc import load as gc_load
from calendar_events import build_all


def hour_floor(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.floor("1h")


def event_response(gc1h: pd.DataFrame, cal: pd.DataFrame, event: str, lookback_bars: int = 24):
    sub = cal[cal["event"] == event].copy()
    rows = []
    for _, ev in sub.iterrows():
        t = hour_floor(ev["ts_utc"])
        if t not in gc1h.index:
            continue
        idx = gc1h.index.get_loc(t)
        if idx < lookback_bars or idx + 1 >= len(gc1h):
            continue
        window_back = gc1h.iloc[idx - lookback_bars: idx]
        avg_tr = (window_back["high"] - window_back["low"]).mean()
        post_bar = gc1h.iloc[idx]
        next_bar = gc1h.iloc[idx + 1]
        # Move within event hour and the hour after
        ev_range = post_bar["high"] - post_bar["low"]
        post_range = next_bar["high"] - next_bar["low"]
        ev_return = (post_bar["close"] - post_bar["open"]) / post_bar["open"] * 100
        rows.append({
            "ts": t, "avg_tr": avg_tr,
            "event_range": ev_range, "next_range": post_range,
            "event_return_pct": ev_return,
            "vol_ratio_event": ev_range / avg_tr if avg_tr else np.nan,
            "vol_ratio_next": post_range / avg_tr if avg_tr else np.nan,
        })
    return pd.DataFrame(rows)


def main():
    gc1h = gc_load("60m")
    cal = build_all()
    cal_recent = cal[cal["ts_utc"] >= gc1h.index.min()].copy()

    for event in ["FOMC", "NFP", "CPI", "RETAIL", "PPI", "CLAIMS"]:
        resp = event_response(gc1h, cal_recent, event)
        if resp.empty:
            print(f"{event:8s} no matches in GC 1h window")
            continue
        baseline = gc1h["high"].subtract(gc1h["low"]).rolling(24).mean().mean()
        mean_event = resp["event_range"].mean()
        mean_ratio = resp["vol_ratio_event"].mean()
        # Estimate one-sided p-value via signed-rank style: % of events where vol_ratio_event > 1
        pct_over_baseline = (resp["vol_ratio_event"] > 1.0).mean() * 100
        print(f"{event:8s} n={len(resp):3d} | mean ev_range=${mean_event:6.2f} | "
              f"avg vol-ratio={mean_ratio:4.2f}x | "
              f"% bars above baseline={pct_over_baseline:5.1f}% | "
              f"mean signed return in event hour={resp['event_return_pct'].mean():+.3f}%")
    print(f"\nGlobal baseline 1h true-range: ${baseline:.2f}")


if __name__ == "__main__":
    main()
