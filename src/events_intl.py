"""International central bank rate decisions for MERS testing.

These dates are public, scheduled in advance. Times converted to UTC.
"""
from __future__ import annotations
from datetime import datetime, timedelta
import pandas as pd
import pytz

UTC = pytz.UTC
CET = pytz.timezone("Europe/Berlin")
LON = pytz.timezone("Europe/London")


def _to_utc(date_str: str, tz, hh: int, mm: int) -> pd.Timestamp:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    naive = datetime(d.year, d.month, d.day, hh, mm)
    aware = tz.localize(naive)
    return pd.Timestamp(aware.astimezone(UTC))


# ECB monetary policy decisions, 14:15 CET (press conference 14:45)
ECB_DATES = [
    # 2024
    "2024-01-25", "2024-03-07", "2024-04-11", "2024-06-06",
    "2024-07-18", "2024-09-12", "2024-10-17", "2024-12-12",
    # 2025
    "2025-01-30", "2025-03-06", "2025-04-17", "2025-06-05",
    "2025-07-24", "2025-09-11", "2025-10-30", "2025-12-18",
    # 2026 (Day 2 of meeting)
    "2026-01-29", "2026-03-12", "2026-04-23", "2026-06-04",
    "2026-07-23", "2026-09-10", "2026-10-29", "2026-12-17",
]

# BoE MPC rate decisions, 12:00 UK time
BOE_DATES = [
    # 2024
    "2024-02-01", "2024-03-21", "2024-05-09", "2024-06-20",
    "2024-08-01", "2024-09-19", "2024-11-07", "2024-12-19",
    # 2025
    "2025-02-06", "2025-03-20", "2025-05-08", "2025-06-19",
    "2025-08-07", "2025-09-18", "2025-11-06", "2025-12-18",
    # 2026
    "2026-02-05", "2026-03-19", "2026-04-30", "2026-06-18",
    "2026-07-30", "2026-09-17", "2026-11-05", "2026-12-17",
]


def build_ecb() -> pd.DataFrame:
    return pd.DataFrame([
        {"ts_utc": _to_utc(d, CET, 14, 15), "event": "ECB",
         "value": pd.NA, "prior": pd.NA, "delta": pd.NA,
         "trailing_mean": pd.NA, "trailing_std": pd.NA, "surprise_z": pd.NA,
         "expected_dir": 0}
        for d in ECB_DATES
    ])


def build_boe() -> pd.DataFrame:
    return pd.DataFrame([
        {"ts_utc": _to_utc(d, LON, 12, 0), "event": "BOE",
         "value": pd.NA, "prior": pd.NA, "delta": pd.NA,
         "trailing_mean": pd.NA, "trailing_std": pd.NA, "surprise_z": pd.NA,
         "expected_dir": 0}
        for d in BOE_DATES
    ])


def build_intl_all() -> pd.DataFrame:
    df = pd.concat([build_ecb(), build_boe()], ignore_index=True)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    return df.sort_values("ts_utc").reset_index(drop=True)


if __name__ == "__main__":
    df = build_intl_all()
    print(df)
