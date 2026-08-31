"""M12 regime-persistence audit.

Follow-up #2 from docs/experiments/2026-08-31_m12_regime_split_ensemble.md.

Question: what's the historical distribution of M12 LONG streaks vs
SHORT streaks? Informs the base rate for how often the ensemble's
SHORT-regime edge will actually be sampled going forward.

Output: streak counts, length percentiles, top-5 longest each side,
plus base-rate estimate for a flip out of the current LONG streak
within the next 26 weeks.

Usage:
    python scripts/m12_regime_persistence.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location(
    "far", str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)


def compute_streaks(daily: pd.DataFrame) -> list[dict]:
    m12 = daily["close"].pct_change(252)
    dir_series = pd.Series(
        np.where(m12 > 0, "L", np.where(m12 < 0, "S", "F")),
        index=m12.index,
    ).dropna()

    streaks = []
    cur_dir = None
    cur_start = None
    cur_len = 0
    prev_ts = None
    for ts, d in dir_series.items():
        if d != cur_dir:
            if cur_dir in ("L", "S"):
                streaks.append({
                    "dir": cur_dir, "start": cur_start,
                    "end": prev_ts, "length_days": cur_len,
                })
            cur_dir = d
            cur_start = ts
            cur_len = 1
        else:
            cur_len += 1
        prev_ts = ts
    if cur_dir in ("L", "S"):
        streaks.append({
            "dir": cur_dir, "start": cur_start,
            "end": prev_ts, "length_days": cur_len, "open": True,
        })
    return streaks


def report(streaks: list[dict], label: str) -> None:
    lens = [s["length_days"] for s in streaks]
    print(f"\n=== {label} (n={len(streaks)}) ===")
    if not lens:
        return
    print(f"total days:     {sum(lens)}")
    print(f"min length:     {min(lens)}")
    print(f"max length:     {max(lens)}")
    print(f"mean length:    {np.mean(lens):.1f}")
    print(f"median length:  {int(np.median(lens))}")
    print(f"p25/50/75/90:   {np.percentile(lens, 25):.0f} / "
          f"{np.percentile(lens, 50):.0f} / "
          f"{np.percentile(lens, 75):.0f} / "
          f"{np.percentile(lens, 90):.0f}")
    top = sorted(streaks, key=lambda x: -x["length_days"])[:5]
    print("top 5 longest:")
    for s in top:
        open_flag = " (OPEN)" if s.get("open") else ""
        print(f"  {s['length_days']:>5} days   "
              f"{s['start'].date()} -> {s['end'].date()}{open_flag}")


def base_rate_flip(long_streaks: list[dict], horizon_days: int) -> None:
    if not long_streaks or not long_streaks[-1].get("open"):
        print("\n[no open LONG streak, skipping base-rate analysis]")
        return
    current = long_streaks[-1]
    days_so_far = current["length_days"]
    print(f"\n=== Base rate for M12 flip in the next {horizon_days} days ===")
    print(f"current LONG streak: {days_so_far} days, "
          f"started {current['start'].date()}")

    prior = [s["length_days"] for s in long_streaks[:-1]]
    if not prior:
        print("no prior LONG streaks to compare against")
        return
    reached = sum(1 for l in prior if l >= days_so_far)
    total = len(prior)
    print(f"prior LONG streaks that reached >= {days_so_far} days: "
          f"{reached}/{total}")

    if reached == 0:
        print("current LONG streak is longer than any prior; "
              "no comparable base rate")
        return

    ended_within = sum(1 for l in prior if days_so_far <= l < days_so_far + horizon_days)
    pct = 100 * ended_within / reached
    print(f"of those, ended within {horizon_days} more days: "
          f"{ended_within}/{reached} = {pct:.0f}%")
    extras = [l - days_so_far for l in prior if l >= days_so_far]
    if extras:
        print(f"median additional length once a streak reached {days_so_far}d: "
              f"{int(np.median(extras))} days")


def main() -> None:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-08-31", tz="UTC")
    daily = far.load_daily_bars(start, end)
    print(f"daily bars: {len(daily)}   "
          f"range: {daily.index.min().date()} -> {daily.index.max().date()}")

    streaks = compute_streaks(daily)
    long_streaks = [s for s in streaks if s["dir"] == "L"]
    short_streaks = [s for s in streaks if s["dir"] == "S"]

    report(long_streaks, "M12 LONG streaks")
    report(short_streaks, "M12 SHORT streaks")

    base_rate_flip(long_streaks, horizon_days=182)  # 26 weeks


if __name__ == "__main__":
    main()
