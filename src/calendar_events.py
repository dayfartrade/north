"""Construct a unified macro event calendar with release timestamps in UTC.

Each event has:
  ts_utc          : approximate release timestamp (UTC)
  event           : event type (FOMC, NFP, CPI, ...)
  value           : released figure
  prior           : prior period figure
  delta           : value - prior (for level series) or value (for rate series)
  trailing_mean   : trailing-N mean of `delta` (or `value` for rate series)
  trailing_std    : trailing-N std (same)
  surprise_z      : (delta - trailing_mean) / trailing_std
  expected_dir    : +1 / 0 / -1 — sign of expected GC reaction (literature-based)
                    Convention: bad-econ news → +1 (gold up); good-econ → -1.

NOTE: Release timestamps are computed from documented schedules; they may be off
by a day for occasional reschedules. Good enough for V1 backtest; refine later
with vintage data if needed.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone, time
from typing import Optional

import pandas as pd
import pytz

from data_fred import load as fred_load

ROOT = Path(__file__).resolve().parent.parent
CAL_DIR = ROOT / "data" / "calendar"
CAL_DIR.mkdir(parents=True, exist_ok=True)

ET = pytz.timezone("America/New_York")

# Authoritative FOMC announcement dates (2pm ET)
FOMC_DATES = [
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

TRAILING_N = 12  # months for monthly series, weeks for weekly


def et_to_utc(d: pd.Timestamp, hh: int, mm: int) -> pd.Timestamp:
    """Build an Eastern-time timestamp on date `d` then convert to UTC."""
    naive = datetime(d.year, d.month, d.day, hh, mm)
    aware = ET.localize(naive)
    return pd.Timestamp(aware.astimezone(timezone.utc))


def first_friday(year: int, month: int) -> pd.Timestamp:
    d = datetime(year, month, 1)
    while d.weekday() != 4:  # Mon=0..Fri=4
        d += timedelta(days=1)
    return pd.Timestamp(d)


def nth_business_day(year: int, month: int, n: int) -> pd.Timestamp:
    """Approximate Nth business day of month (skipping Sat/Sun, no holidays)."""
    d = datetime(year, month, 1)
    count = 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count == n:
                return pd.Timestamp(d)
        d += timedelta(days=1)


def _trail(series: pd.Series, n: int) -> tuple[pd.Series, pd.Series]:
    return series.rolling(n).mean().shift(1), series.rolling(n).std().shift(1)


def _safe_z(x: pd.Series, mean: pd.Series, std: pd.Series) -> pd.Series:
    z = (x - mean) / std
    return z.replace([float("inf"), float("-inf")], pd.NA)


# ---- builders for each event type ------------------------------------------

def build_fomc() -> pd.DataFrame:
    rows = []
    for d in FOMC_DATES:
        ts = pd.Timestamp(d)
        rows.append({
            "ts_utc": et_to_utc(ts, 14, 0),
            "event": "FOMC",
            "value": pd.NA, "prior": pd.NA, "delta": pd.NA,
            "trailing_mean": pd.NA, "trailing_std": pd.NA, "surprise_z": pd.NA,
            "expected_dir": 0,  # direction depends on hawkish/dovish; treat as vol event
        })
    return pd.DataFrame(rows)


def build_nfp() -> pd.DataFrame:
    """NFP: first Friday of month M+1 for observation month M, 8:30 ET."""
    df = fred_load("nfp").copy()
    df["delta"] = df["value"].diff()
    mean, std = _trail(df["delta"], TRAILING_N)
    df["trailing_mean"] = mean
    df["trailing_std"] = std
    df["surprise_z"] = _safe_z(df["delta"], mean, std)
    rows = []
    for _, r in df.iterrows():
        obs = r["date"]
        rel_month_year, rel_month = (obs.year + (1 if obs.month == 12 else 0),
                                      1 if obs.month == 12 else obs.month + 1)
        rel = first_friday(rel_month_year, rel_month)
        rows.append({
            "ts_utc": et_to_utc(rel, 8, 30),
            "event": "NFP",
            "value": r["value"], "prior": r["value"] - r["delta"],
            "delta": r["delta"],
            "trailing_mean": r["trailing_mean"], "trailing_std": r["trailing_std"],
            "surprise_z": r["surprise_z"],
            # strong NFP delta → gold down (good econ news)
            "expected_dir": -1 if pd.notna(r["surprise_z"]) and r["surprise_z"] > 0 else
                            (1 if pd.notna(r["surprise_z"]) and r["surprise_z"] < 0 else 0),
        })
    return pd.DataFrame(rows)


def build_unrate() -> pd.DataFrame:
    """UNRATE released same morning as NFP."""
    df = fred_load("unrate").copy()
    df["delta"] = df["value"].diff()
    mean, std = _trail(df["delta"], TRAILING_N)
    df["trailing_mean"] = mean
    df["trailing_std"] = std
    df["surprise_z"] = _safe_z(df["delta"], mean, std)
    rows = []
    for _, r in df.iterrows():
        obs = r["date"]
        rel_month_year, rel_month = (obs.year + (1 if obs.month == 12 else 0),
                                      1 if obs.month == 12 else obs.month + 1)
        rel = first_friday(rel_month_year, rel_month)
        rows.append({
            "ts_utc": et_to_utc(rel, 8, 30),
            "event": "UNRATE",
            "value": r["value"], "prior": r["value"] - r["delta"],
            "delta": r["delta"],
            "trailing_mean": r["trailing_mean"], "trailing_std": r["trailing_std"],
            "surprise_z": r["surprise_z"],
            # rising unemployment → gold up (bad econ news)
            "expected_dir": 1 if pd.notna(r["surprise_z"]) and r["surprise_z"] > 0 else
                            (-1 if pd.notna(r["surprise_z"]) and r["surprise_z"] < 0 else 0),
        })
    return pd.DataFrame(rows)


def _monthly_release(name: str, event: str, day_of_month_business: int,
                      direction_high: int) -> pd.DataFrame:
    """Generic builder for a monthly release at approximately the Nth business day."""
    df = fred_load(name).copy()
    df["delta"] = df["value"].diff()
    mean, std = _trail(df["delta"], TRAILING_N)
    df["trailing_mean"] = mean
    df["trailing_std"] = std
    df["surprise_z"] = _safe_z(df["delta"], mean, std)
    rows = []
    for _, r in df.iterrows():
        obs = r["date"]
        rel_y = obs.year + (1 if obs.month == 12 else 0)
        rel_m = 1 if obs.month == 12 else obs.month + 1
        rel = nth_business_day(rel_y, rel_m, day_of_month_business)
        rows.append({
            "ts_utc": et_to_utc(rel, 8, 30),
            "event": event,
            "value": r["value"], "prior": r["value"] - r["delta"],
            "delta": r["delta"],
            "trailing_mean": r["trailing_mean"], "trailing_std": r["trailing_std"],
            "surprise_z": r["surprise_z"],
            "expected_dir": direction_high if pd.notna(r["surprise_z"]) and r["surprise_z"] > 0
                            else (-direction_high if pd.notna(r["surprise_z"]) and r["surprise_z"] < 0 else 0),
        })
    return pd.DataFrame(rows)


def build_cpi() -> pd.DataFrame:
    """CPI YoY surprise direction is regime-dependent. We mark vol-only by default."""
    df = fred_load("cpi_yoy_proxy").copy()
    df["yoy"] = df["value"].pct_change(12) * 100
    mean, std = _trail(df["yoy"], TRAILING_N)
    df["trailing_mean"] = mean
    df["trailing_std"] = std
    df["surprise_z"] = _safe_z(df["yoy"], mean, std)
    rows = []
    for _, r in df.iterrows():
        obs = r["date"]
        rel_y = obs.year + (1 if obs.month == 12 else 0)
        rel_m = 1 if obs.month == 12 else obs.month + 1
        rel = nth_business_day(rel_y, rel_m, 9)  # CPI ~8th-13th business day, use 9
        rows.append({
            "ts_utc": et_to_utc(rel, 8, 30),
            "event": "CPI",
            "value": r["yoy"], "prior": pd.NA,
            "delta": r["yoy"] - mean.loc[r.name] if pd.notna(mean.loc[r.name]) else pd.NA,
            "trailing_mean": r["trailing_mean"], "trailing_std": r["trailing_std"],
            "surprise_z": r["surprise_z"],
            # In current rate-cycle regime, hot CPI → hawkish → gold DOWN.
            # Cold CPI → dovish → gold UP. We code this; backtest will validate.
            "expected_dir": -1 if pd.notna(r["surprise_z"]) and r["surprise_z"] > 0.5
                            else (1 if pd.notna(r["surprise_z"]) and r["surprise_z"] < -0.5 else 0),
        })
    return pd.DataFrame(rows)


def build_claims() -> pd.DataFrame:
    """Initial Claims: weekly, released Thursday after the Saturday-ending week."""
    df = fred_load("claims").copy()
    df["delta"] = df["value"].diff()
    n_weekly = 8
    mean, std = _trail(df["delta"], n_weekly)
    df["trailing_mean"] = mean
    df["trailing_std"] = std
    df["surprise_z"] = _safe_z(df["delta"], mean, std)
    rows = []
    for _, r in df.iterrows():
        # Observation date is the Saturday week-end; release is the following Thursday.
        rel = r["date"] + pd.Timedelta(days=5)
        rows.append({
            "ts_utc": et_to_utc(rel, 8, 30),
            "event": "CLAIMS",
            "value": r["value"], "prior": r["value"] - r["delta"],
            "delta": r["delta"],
            "trailing_mean": r["trailing_mean"], "trailing_std": r["trailing_std"],
            "surprise_z": r["surprise_z"],
            # rising claims → bad econ → gold UP
            "expected_dir": 1 if pd.notna(r["surprise_z"]) and r["surprise_z"] > 0 else
                            (-1 if pd.notna(r["surprise_z"]) and r["surprise_z"] < 0 else 0),
        })
    return pd.DataFrame(rows)


def build_forward(months_ahead: int = 6) -> pd.DataFrame:
    """Generate placeholder events for releases not yet published.

    Forward events have ts_utc populated by schedule rules but value/surprise/
    expected_dir are NaN. The PEB strategy (v4) does not need surprise_z or
    expected_dir — only the event timestamp. So these are usable live.
    """
    today = pd.Timestamp.now(tz="UTC").normalize().tz_convert(None)
    rows = []
    for n in range(months_ahead + 1):
        y = today.year + (today.month - 1 + n) // 12
        m = (today.month - 1 + n) % 12 + 1

        # NFP & UNRATE: first Friday of m for observation month m-1
        rel = first_friday(y, m)
        if rel >= today - pd.Timedelta(days=1):
            for ev in ("NFP", "UNRATE"):
                rows.append({
                    "ts_utc": et_to_utc(rel, 8, 30),
                    "event": ev, "value": pd.NA, "prior": pd.NA, "delta": pd.NA,
                    "trailing_mean": pd.NA, "trailing_std": pd.NA, "surprise_z": pd.NA,
                    "expected_dir": 0,
                })

        # CPI ~9th business day, PPI ~8th, Retail ~11th
        for ev, biz_day in (("PPI", 8), ("CPI", 9), ("RETAIL", 11)):
            rel = nth_business_day(y, m, biz_day)
            if rel >= today - pd.Timedelta(days=1):
                rows.append({
                    "ts_utc": et_to_utc(rel, 8, 30),
                    "event": ev, "value": pd.NA, "prior": pd.NA, "delta": pd.NA,
                    "trailing_mean": pd.NA, "trailing_std": pd.NA, "surprise_z": pd.NA,
                    "expected_dir": 0,
                })

        # Initial Claims: every Thursday in month m of year y
        d = datetime(y, m, 1)
        while d.month == m:
            if d.weekday() == 3 and pd.Timestamp(d) >= today - pd.Timedelta(days=1):  # Thursday
                rows.append({
                    "ts_utc": et_to_utc(pd.Timestamp(d), 8, 30),
                    "event": "CLAIMS", "value": pd.NA, "prior": pd.NA, "delta": pd.NA,
                    "trailing_mean": pd.NA, "trailing_std": pd.NA, "surprise_z": pd.NA,
                    "expected_dir": 0,
                })
            d += timedelta(days=1)

    return pd.DataFrame(rows)


def build_all(start: str = "2020-01-01", include_forward: bool = True,
              forward_months: int = 6) -> pd.DataFrame:
    parts = [
        build_fomc(),
        build_nfp(),
        build_unrate(),
        build_cpi(),
        build_claims(),
        _monthly_release("ppi", "PPI", 8, -1),          # PPI typically ~8th biz day, before CPI
        _monthly_release("retail_sales", "RETAIL", 11, -1),  # Retail Sales ~11th-12th biz day
    ]
    if include_forward:
        parts.append(build_forward(months_ahead=forward_months))
    cal = pd.concat(parts, ignore_index=True)
    cal["ts_utc"] = pd.to_datetime(cal["ts_utc"], utc=True)
    cal = cal[cal["ts_utc"] >= pd.Timestamp(start, tz="UTC")].sort_values("ts_utc").reset_index(drop=True)
    # Dedupe: same event-type at same timestamp keeps the one with data (non-NaN surprise_z)
    cal["has_data"] = cal["surprise_z"].notna().astype(int)
    cal = cal.sort_values(["ts_utc", "event", "has_data"], ascending=[True, True, False])
    cal = cal.drop_duplicates(subset=["ts_utc", "event"], keep="first").drop(columns=["has_data"])
    cal = cal.sort_values("ts_utc").reset_index(drop=True)
    return cal


def save(cal: pd.DataFrame) -> Path:
    path = CAL_DIR / "events.csv"
    cal.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    cal = build_all()
    path = save(cal)
    print(f"Saved {len(cal)} events to {path}")
    print("\nEvent counts:")
    print(cal["event"].value_counts())
    print("\nMost recent 15 events:")
    print(cal.tail(15)[["ts_utc", "event", "value", "surprise_z", "expected_dir"]].to_string(index=False))
