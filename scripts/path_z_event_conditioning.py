"""Cross-tabulate Path Z trades against the macro event calendar.

Bucket each of the n=85 Path Z trades by macro-event proximity:
  - EVENT_DAY_NEAR_OPEN: an event released between 12:00-14:00 UTC same day
    (during OR-build window or watch window immediately after)
  - EVENT_DAY_OTHER:     event released same day but outside 12-14 UTC
  - DAY_AFTER_EVENT:     T-1 had at least one event
  - PRE_EVENT_DAY:       T+1 has scheduled event (Wednesday before Thursday CPI, etc.)
  - QUIET:               none of the above

Report mean/trade, WR, n per bucket. Also split by event type
(FOMC/NFP/CPI/UNRATE/CLAIMS separately) for the same-day bucket.

If event conditioning materially changes Path Z's edge, this suggests
a v10 filter (either "only take Path Z on QUIET days" or "only take on
EVENT_DAY_NEAR_OPEN days"). If not, macro is orthogonal on this timeframe.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CAL = ROOT / "data" / "calendar" / "events.csv"
PATH_Z_LOG = ROOT / "data" / "shadow_equity_path_z.jsonl"

# NY session opens at 13:00 UTC; Path Z entries fall in the 12-bar watch window
# starting at 13:30 UTC (after 6x5m OR build). So macro events released between
# 12:00-14:00 UTC land during the OR-build or right when Path Z considers entry.
NEAR_OPEN_START_UTC = pd.Timestamp("12:00").time()
NEAR_OPEN_END_UTC = pd.Timestamp("14:00").time()


def load_trades() -> list[dict]:
    with open(PATH_Z_LOG) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def load_events() -> pd.DataFrame:
    df = pd.read_csv(CAL, parse_dates=["ts_utc"])
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    df["date"] = df["ts_utc"].dt.date
    return df


def classify_trade(trade_ts_utc: pd.Timestamp, events: pd.DataFrame) -> tuple[str, list[str]]:
    """Return (bucket, event_types_matched)."""
    trade_date = trade_ts_utc.date()
    prev_date = trade_date - pd.Timedelta(days=1)
    next_date = trade_date + pd.Timedelta(days=1)

    same_day = events[events["date"] == trade_date]
    prev_day = events[events["date"] == prev_date]
    next_day = events[events["date"] == next_date]

    if len(same_day):
        near_open = same_day[same_day["ts_utc"].dt.time.between(
            NEAR_OPEN_START_UTC, NEAR_OPEN_END_UTC)]
        if len(near_open):
            return "EVENT_DAY_NEAR_OPEN", sorted(set(near_open["event"]))
        return "EVENT_DAY_OTHER", sorted(set(same_day["event"]))
    if len(prev_day):
        return "DAY_AFTER_EVENT", sorted(set(prev_day["event"]))
    if len(next_day):
        return "PRE_EVENT_DAY", sorted(set(next_day["event"]))
    return "QUIET", []


def summarize(label: str, pnls: list[float], indent: int = 0) -> None:
    n = len(pnls)
    if n == 0:
        print(f"{' '*indent}{label:<32s}  NO TRADES")
        return
    total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    print(f"{' '*indent}{label:<32s}  n={n:>3d}  mean=${mean:>+7,.0f}  "
          f"WR={100*wins/n:>4.1f}%  total=${total:>+8,.0f}")


def main() -> None:
    trades = load_trades()
    trades.sort(key=lambda t: t["or_open_utc"])
    events = load_events()
    print(f"Path Z trades: {len(trades)}  |  events: {len(events)}  "
          f"({events['date'].min()} - {events['date'].max()})\n")

    by_bucket: dict[str, list[float]] = defaultdict(list)
    by_event_type_near_open: dict[str, list[float]] = defaultdict(list)
    by_event_type_prev_day: dict[str, list[float]] = defaultdict(list)

    for t in trades:
        ts = pd.Timestamp(t["or_open_utc"])
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        pnl = float(t["outcome"]["net_pnl"])
        bucket, evs = classify_trade(ts, events)
        by_bucket[bucket].append(pnl)
        if bucket == "EVENT_DAY_NEAR_OPEN":
            for ev in evs:
                by_event_type_near_open[ev].append(pnl)
        if bucket == "DAY_AFTER_EVENT":
            for ev in evs:
                by_event_type_prev_day[ev].append(pnl)

    print("=== Bucket breakdown ===\n")
    for bucket in ["QUIET", "PRE_EVENT_DAY", "EVENT_DAY_NEAR_OPEN",
                   "EVENT_DAY_OTHER", "DAY_AFTER_EVENT"]:
        summarize(bucket, by_bucket.get(bucket, []))

    print("\n=== Baseline (all Path Z) ===")
    all_pnls = [p for pnls in by_bucket.values() for p in pnls]
    summarize("all trades", all_pnls)

    print("\n=== EVENT_DAY_NEAR_OPEN split by event type ===")
    for ev, pnls in sorted(by_event_type_near_open.items(),
                            key=lambda kv: -len(kv[1])):
        summarize(f"  {ev}", pnls, indent=2)

    print("\n=== DAY_AFTER_EVENT split by event type ===")
    for ev, pnls in sorted(by_event_type_prev_day.items(),
                            key=lambda kv: -len(kv[1])):
        summarize(f"  {ev}", pnls, indent=2)

    # Simple v10 candidate filters — test both directions
    print("\n=== v10 filter simulations ===")
    quiet = by_bucket.get("QUIET", [])
    non_quiet = [p for b, pnls in by_bucket.items() if b != "QUIET" for p in pnls]
    print(f"  Filter A: 'only trade QUIET days'")
    summarize("    QUIET-only", quiet, indent=2)
    print(f"  Filter B: 'skip QUIET days (only event-adjacent)'")
    summarize("    non-QUIET", non_quiet, indent=2)


if __name__ == "__main__":
    main()
