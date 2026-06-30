"""News + London-fix stand-down windows.

Notes' guidance:
  - ±15 min around FOMC/CPI/NFP/PPI/UNRATE releases — gold reacts violently,
    ORB strategies get chopped on event candles.
  - ±10 min around London fix windows (10:30 LT and 15:00 LT) —
    scheduled vol events, known whipsaw zone.

This module returns whether a given timestamp falls inside any stand-down.
Used by ORB dispatch and backtest to pre-register skips before improvising.

Calendar source: data/calendar/events.csv (built by calendar_events.py).
"""
from __future__ import annotations
from pathlib import Path
from datetime import time
import pandas as pd
import pytz

ROOT = Path(__file__).resolve().parent.parent
CAL_PATH = ROOT / "data" / "calendar" / "events.csv"

# News events that materially move gold (the heavy-hitters)
MAJOR_NEWS = {"FOMC", "CPI", "NFP", "UNRATE", "PPI", "RETAIL"}
NEWS_BUFFER_MINUTES = 15

# London fix times in LOCAL London time
LON_FIX_TIMES_LOCAL = [time(10, 30), time(15, 0)]
FIX_BUFFER_MINUTES = 10

_LON_TZ = pytz.timezone("Europe/London")


def _load_calendar() -> pd.DataFrame:
    if not CAL_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(CAL_PATH)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"])
    if df["ts_utc"].dt.tz is None:
        df["ts_utc"] = df["ts_utc"].dt.tz_localize("UTC")
    return df


def is_news_window(ts: pd.Timestamp, calendar: pd.DataFrame | None = None,
                    buffer_minutes: int = NEWS_BUFFER_MINUTES) -> tuple[bool, str]:
    """True if ts is within ±buffer minutes of a MAJOR_NEWS event."""
    if calendar is None:
        calendar = _load_calendar()
    if calendar.empty:
        return False, ""
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    relevant = calendar[calendar["event"].isin(MAJOR_NEWS)]
    delta = (relevant["ts_utc"] - ts).abs()
    hits = relevant[delta <= pd.Timedelta(minutes=buffer_minutes)]
    if hits.empty:
        return False, ""
    # Closest one
    closest = hits.iloc[(hits["ts_utc"] - ts).abs().argmin()]
    return True, f"news:{closest['event']}@{closest['ts_utc'].strftime('%H:%M')}"


def is_london_fix_window(ts: pd.Timestamp,
                          buffer_minutes: int = FIX_BUFFER_MINUTES) -> tuple[bool, str]:
    """True if ts is within ±buffer minutes of a London fix (10:30 or 15:00 LT, DST-aware)."""
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    ts_lon = ts.astimezone(_LON_TZ)
    for fix_t in LON_FIX_TIMES_LOCAL:
        fix_dt = ts_lon.normalize() + pd.Timedelta(hours=fix_t.hour, minutes=fix_t.minute)
        if abs((ts_lon - fix_dt).total_seconds()) <= buffer_minutes * 60:
            return True, f"lon_fix@{fix_t.strftime('%H:%M')}LT"
    return False, ""


def should_stand_down(ts: pd.Timestamp, calendar: pd.DataFrame | None = None) -> tuple[bool, str]:
    """Combined stand-down check. Returns (bool, reason)."""
    nw, nr = is_news_window(ts, calendar)
    if nw:
        return True, nr
    fw, fr = is_london_fix_window(ts)
    if fw:
        return True, fr
    return False, ""


def stand_down_for_or_window(session_open_utc: pd.Timestamp,
                              or_bars: int = 6, bar_minutes: int = 5,
                              calendar: pd.DataFrame | None = None) -> tuple[bool, str]:
    """Skip the entire session ONLY if the OR-defining window itself hits a stand-down.

    If the OR bars (used to compute or_high/or_low) overlap a news release, the
    OR itself is unreliable. Otherwise we keep the session and just stand-down
    individual entries that fall inside a fix or news buffer.
    """
    if calendar is None:
        calendar = _load_calendar()
    or_end = session_open_utc + pd.Timedelta(minutes=or_bars * bar_minutes)
    t = session_open_utc
    while t < or_end:
        sd, r = should_stand_down(t, calendar)
        if sd:
            return True, r
        t += pd.Timedelta(minutes=bar_minutes)
    return False, ""


def stand_down_for_entry(entry_ts: pd.Timestamp,
                          calendar: pd.DataFrame | None = None) -> tuple[bool, str]:
    """Per-entry check: is this specific entry timestamp inside a stand-down?

    Use this for ORB breakout entries — skip individual entries that fire
    within ±15min of news or ±10min of a London fix, but keep watching for
    breakouts at other times during the watch window.
    """
    return should_stand_down(entry_ts, calendar)


if __name__ == "__main__":
    cal = _load_calendar()
    print(f"Calendar rows: {len(cal)}")
    print(f"Major news events: {(cal['event'].isin(MAJOR_NEWS)).sum()}")
    print()

    # Test on the upcoming NFP
    nfp_ts = pd.Timestamp("2026-07-03 12:30:00", tz="UTC")
    for offset in (-30, -16, -15, -10, 0, 10, 15, 16, 30):
        t = nfp_ts + pd.Timedelta(minutes=offset)
        sd, r = should_stand_down(t)
        print(f"  NFP ts+{offset:+3d}min: stand_down={sd}  reason={r}")
    print()

    # Test London fix windows
    print("=== London fix detection ===")
    today = pd.Timestamp.now(tz="UTC").normalize()
    for lt_hour, lt_min in [(10, 30), (15, 0)]:
        # Compute UTC for this LT (today)
        lon_dt = _LON_TZ.localize(today.tz_localize(None) + pd.Timedelta(hours=lt_hour, minutes=lt_min))
        utc_dt = lon_dt.astimezone(pytz.UTC)
        for offset in (-15, -10, -5, 0, 5, 10, 15):
            t = utc_dt + pd.Timedelta(minutes=offset)
            sd, r = is_london_fix_window(t)
            print(f"  fix {lt_hour:02d}:{lt_min:02d}LT (UTC={utc_dt.strftime('%H:%M')}) +{offset:+3d}min: lon_fix={sd}  reason={r}")
    print()

    # OR-window skip rate (full session skips — should be RARE)
    print("=== OR-window skip rate over backtest (last 60d) ===")
    from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on
    from data_gc import load as gc_load
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    for sess_name in SESSIONS_LOCAL:
        skipped = 0; total = 0; reasons = {}
        for d in pd.date_range(bars.index.min().date(), bars.index.max().date(), freq="D"):
            sess_t = session_utc_time_on(d.date(), sess_name)
            open_ts = pd.Timestamp.combine(d.date(), sess_t).tz_localize("UTC")
            sd, r = stand_down_for_or_window(open_ts, calendar=cal)
            total += 1
            if sd:
                skipped += 1
                reasons[r] = reasons.get(r, 0) + 1
        print(f"  {sess_name:5s}: {skipped:3d}/{total:3d} ({skipped/total*100:.0f}%) OR-skip  reasons: {reasons}")
