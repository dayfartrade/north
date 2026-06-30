"""Forward-result tracker.

For each top-tier event that has already passed AND we have GC bar coverage of
the event window, simulate the MERS v4 trade plan against actual bars and
record the outcome. This lets us measure the strategy's live performance over
time without any account.

Output: data/tracker/forward_log.csv  (one row per resolved event)
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v3_peb import compute_atr
# Use v5 (deployed strategy: event-bar-range stop + 2x target + 6-bar time exit, JOBS=NFP+UNRATE).
from mers_v5 import (TOP_EVENTS_V5 as TOP_EVENTS, WATCH, MAX_HOLD as HOLD,
                       B_ATR, TREND_N, peb_event_v5, dedupe_co_released)


ROOT = Path(__file__).resolve().parent.parent
TRACK = ROOT / "data" / "tracker"
TRACK.mkdir(parents=True, exist_ok=True)
LOG = TRACK / "forward_log.csv"

# Cutoff date: we only count "live" forward trades from this point on.
# Update once we have the system running.
FORWARD_START = pd.Timestamp("2026-06-19", tz="UTC")


def main():
    cal = dedupe_co_released(build_all())
    bars = gc_load("60m").sort_index()
    if bars.index.tz is None: bars.index = bars.index.tz_localize("UTC")
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=TREND_N, adjust=False).mean()
    slope = ema.diff(5)

    # Existing log
    if LOG.exists():
        existing = pd.read_csv(LOG, parse_dates=["event_ts", "entry_ts", "exit_ts"])
    else:
        existing = pd.DataFrame()

    now = pd.Timestamp.now(tz="UTC")
    rows = []
    for _, ev in cal.iterrows():
        if ev["event"] not in TOP_EVENTS:
            continue
        ev_ts = pd.Timestamp(ev["ts_utc"]).tz_convert("UTC")
        if ev_ts < FORWARD_START:
            continue
        # Need event + WATCH + HOLD bars to be resolved.
        resolve_by = ev_ts + pd.Timedelta(hours=(1 + WATCH + HOLD + 1))
        if now < resolve_by:
            continue
        # Skip if already in log
        if not existing.empty and (existing["event_ts"] == ev_ts).any():
            continue
        # v5 logic: PEB + event-bar-range stop/target + trend filter
        t = peb_event_v5(bars, ev_ts, freq, atr, slope)
        outcome = {
            "event_ts": ev_ts,
            "event_type": ev["event"],
            "took_trade": t is not None,
        }
        if t is not None:
            outcome.update({
                "entry_ts": t["entry_ts"],
                "exit_ts": t["exit_ts"],
                "direction": t["direction"],
                "entry_price": t["entry_price"],
                "exit_price": t["exit_price"],
                "trend_slope": t["trend_slope"],
                "pre_atr": t["pre_atr"],
                "gross_pnl": t["gross_pnl"],
                "net_pnl": t["net_pnl"],
            })
        else:
            outcome.update({
                "entry_ts": None, "exit_ts": None, "direction": 0,
                "entry_price": None, "exit_price": None,
                "trend_slope": None, "pre_atr": None,
                "gross_pnl": 0.0, "net_pnl": 0.0,
            })
        rows.append(outcome)

    if not rows:
        print(f"[track] no new resolvable events since FORWARD_START={FORWARD_START.date()}")
        return

    new_df = pd.DataFrame(rows)
    merged = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
    merged = merged.drop_duplicates(subset=["event_ts", "event_type"]).sort_values("event_ts")
    merged.to_csv(LOG, index=False)

    print(f"[track] resolved {len(rows)} new event(s). Total tracked: {len(merged)}")
    print("\nForward summary so far:")
    taken = merged[merged["took_trade"] == True].copy()
    if taken.empty:
        print("  (no trades taken yet)")
        return
    n = len(taken)
    wins = (taken["net_pnl"] > 0).sum()
    total = taken["net_pnl"].sum()
    mean = taken["net_pnl"].mean()
    print(f"  n={n}  wins={wins}/{n} ({wins/n*100:.1f}%)  total=${total:+.0f}  mean=${mean:+.2f}/trade")
    print("\nLast 10 forward trades:")
    cols = ["event_ts", "event_type", "direction", "entry_price", "exit_price", "net_pnl"]
    print(taken.tail(10)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
