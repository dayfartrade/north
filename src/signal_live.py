"""Live signal generator for MERS v4.

Given:
  - The upcoming event calendar (from calendar_events.build_all())
  - Latest GC bars (via data_gc.snapshot_all() then load())

For each upcoming high-impact event in the next N hours, this prints
the trade plan a human would execute:

  Event:        FOMC at 2026-07-29 18:00 UTC (14:00 ET)
  Pre-event:
    - Compute ATR(20) on the most recent closed 1h bar
    - Compute EMA(50) slope (last 5-bar diff)
  At event bar close (1 hour after release for hourly cadence):
    - Note event-bar HIGH and LOW
    - Place buy-stop at HIGH + 0.10*ATR
    - Place sell-stop at LOW  - 0.10*ATR
    - Only take long if EMA slope > 0; only short if EMA slope < 0
  Exit: at the close of the 4th bar after entry (4-hour hold).
  Stop suggestion: ATR-based protective stop equal to event-bar range.

Usage:
  python src/signal_live.py            # show upcoming-event plans
  python src/signal_live.py --refresh  # snapshot fresh data first
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

from data_gc import load as gc_load, snapshot_all as gc_snapshot
from data_fred import snapshot_all as fred_snapshot
from calendar_events import build_all
from mers_v3_peb import compute_atr
from mers_v4_final import TOP_EVENTS, WATCH, HOLD, B_ATR, TREND_N

ROOT = Path(__file__).resolve().parent.parent
ALERTS_DIR = ROOT / "data" / "alerts"
ALERTS_DIR.mkdir(parents=True, exist_ok=True)


def fmt_et(ts_utc: pd.Timestamp) -> str:
    import pytz
    ET = pytz.timezone("America/New_York")
    return pd.Timestamp(ts_utc).tz_convert(ET).strftime("%Y-%m-%d %H:%M %Z")


def upcoming(events: pd.DataFrame, horizon_hours: int = 240) -> pd.DataFrame:
    now = pd.Timestamp.now(tz="UTC")
    horizon = now + pd.Timedelta(hours=horizon_hours)
    mask = (events["ts_utc"] >= now) & (events["ts_utc"] <= horizon) & (events["event"].isin(TOP_EVENTS))
    return events.loc[mask].sort_values("ts_utc").reset_index(drop=True)


def plan_for_event(bars: pd.DataFrame, atr: pd.Series, ema50: pd.Series,
                    slope: pd.Series, ev: pd.Series) -> dict:
    ev_ts = pd.Timestamp(ev["ts_utc"]).tz_convert("UTC")
    bar_ts = ev_ts.floor(pd.Timedelta(hours=1))

    # Find the most recent closed bar BEFORE the event for ATR/slope context
    closed = bars[bars.index < ev_ts]
    if closed.empty:
        return {"event": ev["event"], "ts_utc": ev_ts,
                "error": "no closed bars before event"}
    latest_idx = bars.index.get_loc(closed.index[-1])
    a = float(atr.iloc[latest_idx]) if latest_idx < len(atr) else float("nan")
    s = float(slope.iloc[latest_idx]) if latest_idx < len(slope) else float("nan")
    last_close = float(bars.iloc[latest_idx]["close"])

    plan = {
        "event": ev["event"],
        "ts_utc": ev_ts,
        "ts_et": fmt_et(ev_ts),
        "bar_ts_utc": bar_ts,
        "last_close": last_close,
        "atr_20": a,
        "ema_slope_5": s,
        "trend_dir": "UP" if s > 0 else "DOWN" if s < 0 else "FLAT",
        "buffer": B_ATR * a if a == a else float("nan"),
        "instructions": [
            f"At {fmt_et(bar_ts + pd.Timedelta(hours=1))} (close of event bar):",
            f"  - Note event-bar HIGH (H) and LOW (L).",
            f"  - Buffer = {B_ATR}*ATR = ${B_ATR * a:.2f}" if a == a else "  - Buffer N/A",
            f"  - Long trigger:  buy-stop @ H + ${B_ATR * a:.2f}" if a == a else "",
            f"  - Short trigger: sell-stop @ L - ${B_ATR * a:.2f}" if a == a else "",
            (f"  - Trend filter (EMA{TREND_N} slope = {s:+.2f}): "
             f"ONLY take LONG breakout (trend up)" if s > 0
             else (f"  - Trend filter (EMA{TREND_N} slope = {s:+.2f}): "
                   f"ONLY take SHORT breakout (trend down)" if s < 0
                   else f"  - Trend filter (EMA{TREND_N} slope ≈ 0): SKIP this event")),
            f"  - Watch {WATCH} bars after event bar; cancel both if neither triggers.",
            f"  - Exit at close of bar #{HOLD} after entry ({HOLD}-hour hold).",
            f"  - Suggested stop: opposite side of event-bar range (e.g. long -> stop below L).",
        ],
    }
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="Snapshot fresh data before printing.")
    ap.add_argument("--horizon-hours", type=int, default=240,
                    help="How many hours ahead to look (default 240 = 10 days).")
    args = ap.parse_args()

    if args.refresh:
        print("[refresh] pulling fresh GC + FRED data...")
        gc_snapshot(verbose=False)
        fred_snapshot(verbose=False)

    bars = gc_load("60m")
    bars = bars.sort_index()
    atr = compute_atr(bars, 20)
    ema50 = bars["close"].ewm(span=TREND_N, adjust=False).mean()
    slope = ema50.diff(5)

    events = build_all()
    upc = upcoming(events, horizon_hours=args.horizon_hours)

    print("="*80)
    print(f"MERS v4 LIVE PLAN  — generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print(f"Looking ahead {args.horizon_hours}h. Events: {TOP_EVENTS}")
    print(f"Bars last={bars.index[-1]}  ATR(20)={float(atr.iloc[-1]):.2f}  "
          f"EMA{TREND_N} slope(5)={float(slope.iloc[-1]):+.3f}  "
          f"close={float(bars['close'].iloc[-1]):.2f}")
    print("="*80)

    if upc.empty:
        print("\nNo top-tier events in the lookahead window.")
        return

    plans = []
    for _, ev in upc.iterrows():
        p = plan_for_event(bars, atr, ema50, slope, ev)
        plans.append(p)
        print(f"\n--- {p['event']} @ {p['ts_et']} (UTC: {p['ts_utc']}) ---")
        if "error" in p:
            print(f"  ERROR: {p['error']}")
            continue
        print(f"  Pre-event context: last_close=${p['last_close']:.2f}  "
              f"ATR(20)=${p['atr_20']:.2f}  trend={p['trend_dir']}")
        for line in p["instructions"]:
            if line:
                print(line)

    # Persist alert log
    out = ALERTS_DIR / f"alerts_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    pd.DataFrame(plans).to_csv(out, index=False)
    print(f"\nSaved alert log -> {out}")


if __name__ == "__main__":
    main()
