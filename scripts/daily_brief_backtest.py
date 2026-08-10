"""QA replay: what would the daily brief have said on prior directional weeks?

Picks the Monday of each recent weekly directional call, reconstructs the
call (entry / stop / atr from that Monday's close and ATR20), and generates
the brief for Tue/Wed/Thu using real XAU/USD 5m bars from that week.

Prints a verdict trajectory per week: does ON TRACK / DRIFTING / AT RISK
line up with the actual Friday-close outcome?

Usage:
    python scripts/daily_brief_backtest.py                (last 12 weeks)
    python scripts/daily_brief_backtest.py --weeks 20
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.far_weekly_gold_read import load_daily_bars, load_macro_series, build_signals, RY

# Import brief functions
spec = importlib.util.spec_from_file_location("ndb", str(ROOT / "scripts" / "north_daily_brief.py"))
ndb = importlib.util.module_from_spec(spec); spec.loader.exec_module(ndb)


def find_directional_mondays(end: pd.Timestamp, n_weeks: int) -> list[dict]:
    """Return list of {monday, direction, entry, stop, atr, week_end} for the
    last n_weeks worth of directional calls."""
    start = end - pd.Timedelta(days=n_weeks * 7 + 90)
    daily = load_daily_bars(start, end)
    ry = load_macro_series(RY, "real_yield_10y")
    df = build_signals(daily, ry)
    # Take only Mondays
    mondays = df[df.index.weekday == 0]
    mondays = mondays[mondays["direction"].isin(["LONG", "SHORT"])]
    mondays = mondays.tail(n_weeks)
    calls = []
    for ts, row in mondays.iterrows():
        entry = float(row["close"])
        atr = float(row["ATR"])
        direction = str(row["direction"])
        if direction == "LONG":
            stop = entry - 2 * atr
        else:
            stop = entry + 2 * atr
        calls.append({
            "monday": ts,
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "atr": atr,
            "week_end": ts + pd.Timedelta(days=4),
        })
    return calls


def load_week_bars(monday: pd.Timestamp) -> pd.DataFrame:
    """Load XAU/USD 5m bars for the given trading week (Mon 00:00 to Fri 21:00 UTC)."""
    from research.tools.data_loader import load_gold_5m
    start = monday.strftime("%Y-%m-%d")
    end = (monday + pd.Timedelta(days=6)).strftime("%Y-%m-%d")
    bars = load_gold_5m(start=start, end=end)
    rows = [{"ts": pd.Timestamp(b.timestamp, unit="ms", tz="UTC"),
             "open": b.open, "high": b.high, "low": b.low, "close": b.close}
            for b in bars]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    week_end = monday + pd.Timedelta(days=4, hours=21)  # Friday 21 UTC
    return df[(df["ts"] >= monday) & (df["ts"] <= week_end)].reset_index(drop=True)


def brief_at(call: dict, week_bars: pd.DataFrame, snap: pd.Timestamp) -> tuple[str, dict]:
    """Return (verdict_badge, metrics) at the given snapshot time."""
    sub = week_bars[week_bars["ts"] <= snap].reset_index(drop=True)
    if sub.empty:
        return ("NO_DATA", {})
    synth_call = {
        "type": "call", "direction": call["direction"],
        "week_of": call["monday"].strftime("%Y-%m-%d"),
        "week_end": call["week_end"].strftime("%Y-%m-%d"),
        "entry_approx": call["entry"],
        "stop_price": call["stop"],
        "atr_20d": call["atr"],
    }
    m = ndb.compute_position_metrics(synth_call, sub)
    badge, _ = ndb.health_verdict(m)
    return (badge, m)


def compute_final_outcome(call: dict, week_bars: pd.DataFrame) -> tuple[str, float]:
    """Simulate the final v1 outcome: stop-hit or Friday close."""
    if week_bars.empty:
        return ("NO_DATA", 0.0)
    entry = call["entry"]
    stop = call["stop"]
    direction = call["direction"]
    for _, bar in week_bars.iterrows():
        if direction == "LONG" and bar["low"] <= stop:
            return ("stop", (stop - entry) / entry * 100)
        if direction == "SHORT" and bar["high"] >= stop:
            return ("stop", (entry - stop) / entry * 100)
    exit_price = float(week_bars["close"].iloc[-1])
    if direction == "LONG":
        return ("friday_close", (exit_price - entry) / entry * 100)
    else:
        return ("friday_close", (entry - exit_price) / entry * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=12,
                    help="how many recent directional weeks to replay")
    ap.add_argument("--end", default=None,
                    help="end date YYYY-MM-DD (default: today)")
    args = ap.parse_args()

    end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC")
    calls = find_directional_mondays(end, args.weeks)
    print(f"Replaying {len(calls)} directional weekly calls\n")

    header = ("week_of      dir   entry     stop      | Tue_12  Wed_12  Thu_12  Fri_20 | "
              "exit_reason  pnl%   consistent?")
    print(header)
    print("-" * len(header))

    for c in calls:
        wb = load_week_bars(c["monday"])
        if wb.empty:
            print(f"  {c['monday'].strftime('%Y-%m-%d')} {c['direction']:5s} — no bars, skip")
            continue

        snapshots = {
            "tue": c["monday"] + pd.Timedelta(days=1, hours=12),
            "wed": c["monday"] + pd.Timedelta(days=2, hours=12),
            "thu": c["monday"] + pd.Timedelta(days=3, hours=12),
            "fri_close": c["monday"] + pd.Timedelta(days=4, hours=21),
        }
        badges = {}
        for name, snap in snapshots.items():
            badge, _ = brief_at(c, wb, snap)
            badges[name] = badge.split(" ", 1)[1] if " " in badge else badge

        reason, pnl = compute_final_outcome(c, wb)

        # Consistency check
        final_positive = pnl > 0
        thu_track = "ON" in badges.get("thu", "")
        thu_drift = "DRIFT" in badges.get("thu", "") or "RISK" in badges.get("thu", "")
        thu_chop = "CHOPP" in badges.get("thu", "")
        if final_positive and thu_track:
            consistency = "✓"
        elif not final_positive and (thu_drift or reason == "stop"):
            consistency = "✓"
        elif thu_chop:
            consistency = "~"
        else:
            consistency = "MISS"

        print(f"  {c['monday'].strftime('%Y-%m-%d')} {c['direction']:5s} "
              f"${c['entry']:8.2f} ${c['stop']:8.2f} | "
              f"{badges.get('tue','?')[:6]:6s} {badges.get('wed','?')[:6]:6s} "
              f"{badges.get('thu','?')[:6]:6s} {badges.get('fri_close','?')[:6]:6s} | "
              f"{reason:12s} {pnl:+6.2f}%  {consistency}")


if __name__ == "__main__":
    main()
