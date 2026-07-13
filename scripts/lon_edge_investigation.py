"""Task 7: Is LON's 75% edge structural or artifact of small-n?

Cross-tabs LON's 8 backtest trades by day-of-week, prior-day range
category (Crabel NR/WS classification), and 3-day directional pattern.
Small n so mostly descriptive; flags patterns to shadow-log for OOS
validation.
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_gc import load as gc_load
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on
from edge_session_orb_v7_final import SESSION_CONFIG, run_orb_v7


def _classify_prior_day_range(prior_ranges: list[float]) -> str:
    """Crabel's classification. prior_ranges[0] is yesterday, [1] is 2days-ago, etc."""
    if len(prior_ranges) < 7:
        return "unknown"
    y = prior_ranges[0]
    if y == min(prior_ranges[:7]):
        return "NR7"
    if y == min(prior_ranges[:4]):
        return "NR4"
    if y < prior_ranges[1]:  # narrower than 2-days-ago
        return "NR"
    if y == max(prior_ranges[:7]):
        return "WS7"
    if y == max(prior_ranges[:4]):
        return "WS4"
    if y > prior_ranges[1]:
        return "WS"
    return "CONTROL"


def _three_day_pattern(closes: list[float], today_open: float) -> str:
    """Crabel's 3-day pattern: prev-2 close vs prev-3, prev-1 vs prev-2, today open vs prev-1."""
    if len(closes) < 3:
        return "?"
    c1, c2, c3 = closes[0], closes[1], closes[2]  # yesterday, 2ago, 3ago
    d1 = "+" if c2 > c3 else "-"
    d2 = "+" if c1 > c2 else "-"
    d3 = "+" if today_open > c1 else "-"
    return d1 + d2 + d3


def main() -> None:
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    daily = pd.read_csv(ROOT / "data/gc/GC_1d.csv", parse_dates=["ts"]).set_index("ts").sort_index()
    if daily.index.tz is None:
        daily.index = daily.index.tz_localize("UTC")

    df = run_orb_v7(bars, session_utc_time_on(datetime.now(pytz.UTC).date(), "LON"), "LON")
    df = df[df["took_trade"] == True]
    if df.empty:
        print("no LON takes")
        return

    print("=" * 70)
    print("TASK 7 — LON edge investigation (n=%d taken trades)" % len(df))
    print("=" * 70)

    # Attach features
    features = []
    for _, r in df.iterrows():
        d = pd.Timestamp(r["entry_ts"]).date()
        # Prior daily bars
        prior_daily = daily[daily.index.date < d].tail(7)
        if len(prior_daily) < 3:
            continue
        prior_ranges = [(row["high"] - row["low"]) for _, row in prior_daily.iloc[::-1].iterrows()]
        prior_closes = [row["close"] for _, row in prior_daily.iloc[::-1].iterrows()]
        # Today's open
        today_row = daily[daily.index.date == d]
        if today_row.empty:
            continue
        today_open = float(today_row.iloc[0]["open"])

        dow = pd.Timestamp(r["entry_ts"]).weekday()
        dow_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dow]
        prior_range_class = _classify_prior_day_range(prior_ranges)
        three_day = _three_day_pattern(prior_closes, today_open)
        features.append({
            "date": str(d),
            "dow": dow_name,
            "prior_class": prior_range_class,
            "three_day": three_day,
            "direction": "LONG" if r["direction"] == 1 else "SHORT",
            "net_pnl": r["net_pnl"],
            "won": r["net_pnl"] > 0,
        })

    print("\n[FEATURE-ANNOTATED TRADES]")
    print(f"{'date':11s} {'dow':4s} {'prior':8s} {'3day':5s} {'dir':6s} {'net':>8s} {'W?':>3s}")
    for f in features:
        w = "W" if f["won"] else "L"
        print(f"{f['date']:11s} {f['dow']:4s} {f['prior_class']:8s} {f['three_day']:5s} {f['direction']:6s} ${f['net_pnl']:+7.0f} {w:>3s}")

    print("\n[BY DAY OF WEEK]")
    for dow in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
        sub = [f for f in features if f["dow"] == dow]
        if sub:
            w = sum(1 for f in sub if f["won"])
            p = sum(f["net_pnl"] for f in sub)
            print(f"  {dow}: n={len(sub)}  wins={w}/{len(sub)} ({100*w/len(sub):.0f}%)  net=${p:+,.0f}")

    print("\n[BY PRIOR-DAY RANGE CLASS (Crabel)]")
    classes = sorted(set(f["prior_class"] for f in features))
    for c in classes:
        sub = [f for f in features if f["prior_class"] == c]
        w = sum(1 for f in sub if f["won"])
        p = sum(f["net_pnl"] for f in sub)
        print(f"  {c:8s}: n={len(sub)}  wins={w}/{len(sub)} ({100*w/len(sub):.0f}%)  net=${p:+,.0f}")

    print("\n[BY 3-DAY PATTERN]")
    patterns = sorted(set(f["three_day"] for f in features))
    for pat in patterns:
        sub = [f for f in features if f["three_day"] == pat]
        w = sum(1 for f in sub if f["won"])
        p = sum(f["net_pnl"] for f in sub)
        print(f"  {pat}: n={len(sub)}  wins={w}/{len(sub)} ({100*w/len(sub):.0f}%)  net=${p:+,.0f}")


if __name__ == "__main__":
    main()
