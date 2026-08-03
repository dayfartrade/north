"""Load Dukascopy CSV price data into Bar lists for the backtest harness.

Dukascopy 5m CSV format (verified 2026-07-31 against XAUUSD_5m.csv):
    ts,open,high,low,close,adj close,volume
    2024-01-01 23:00:00+00:00,2062.598,2066.595,2062.405,2065.214,...

- ts: ISO 8601 with timezone (always +00:00 for UTC)
- We use `close`, not `adj close`, since these are spot instruments
  (no dividends or splits, adj close should equal close)
- volume: base-currency volume from Dukascopy aggregator

Supports:
- Single file load
- Multi-file concatenation (for XAUUSD 2010-2014 + historical + live)
- Resampling from 5m to 1H / 4H / 1D
- Date range filtering
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .backtest import Bar


def load_dukascopy_csv(
    path: str | Path,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> list[Bar]:
    """Load a single Dukascopy CSV into a Bar list, ascending by timestamp.

    start / end: optional YYYY-MM-DD strings to filter the range (inclusive).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    start_ms = _iso_date_to_ms(start) if start else None
    end_ms = _iso_date_to_ms(end) if end else None

    bars: list[Bar] = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts_ms = _parse_dukascopy_timestamp(row["ts"])
            except (ValueError, KeyError):
                continue
            if start_ms is not None and ts_ms < start_ms:
                continue
            if end_ms is not None and ts_ms > end_ms:
                continue
            try:
                bars.append(Bar(
                    timestamp=ts_ms,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0) or 0.0),
                ))
            except (ValueError, KeyError):
                continue

    bars.sort(key=lambda b: b.timestamp)
    return bars


def load_dukascopy_multi(
    paths: Iterable[str | Path],
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> list[Bar]:
    """Concatenate multiple Dukascopy CSVs (for spanning history + live files).

    Deduplicates on timestamp (keeping the first occurrence, which is
    typically the earlier-loaded file). Sorted ascending.
    """
    all_bars: list[Bar] = []
    for p in paths:
        try:
            all_bars.extend(load_dukascopy_csv(p, start=start, end=end))
        except FileNotFoundError:
            continue
    seen: set[int] = set()
    deduped: list[Bar] = []
    for b in sorted(all_bars, key=lambda x: x.timestamp):
        if b.timestamp in seen:
            continue
        seen.add(b.timestamp)
        deduped.append(b)
    return deduped


def resample(bars: list[Bar], target_minutes: int) -> list[Bar]:
    """Resample a list of bars to a coarser timeframe.

    target_minutes: 60 for 1H, 240 for 4H, 1440 for 1D.

    Aggregation: open = first bar's open, high = max, low = min,
    close = last bar's close, volume = sum. Timestamp of the resampled
    bar is the timestamp of its FIRST source bar (open time).

    Assumes source bars are contiguous in time. Gaps in source data
    produce partial resampled bars (fewer source bars aggregated) rather
    than skipping the window entirely. This is defensive against
    weekend gaps in gold data.
    """
    if not bars:
        return []
    if target_minutes < 1:
        raise ValueError("target_minutes must be positive")

    bucket_ms = target_minutes * 60_000
    result: list[Bar] = []
    current_bucket: list[Bar] = []
    current_bucket_start: Optional[int] = None

    for b in bars:
        bucket_start = (b.timestamp // bucket_ms) * bucket_ms
        if current_bucket_start is None:
            current_bucket_start = bucket_start
            current_bucket = [b]
        elif bucket_start == current_bucket_start:
            current_bucket.append(b)
        else:
            result.append(_aggregate_bucket(current_bucket, current_bucket_start))
            current_bucket = [b]
            current_bucket_start = bucket_start

    if current_bucket:
        result.append(_aggregate_bucket(current_bucket, current_bucket_start))

    return result


def _aggregate_bucket(bars: list[Bar], bucket_start_ms: int) -> Bar:
    """Aggregate a list of bars into a single OHLCV bar."""
    return Bar(
        timestamp=bucket_start_ms,
        open=bars[0].open,
        high=max(b.high for b in bars),
        low=min(b.low for b in bars),
        close=bars[-1].close,
        volume=sum(b.volume for b in bars),
    )


def _parse_dukascopy_timestamp(s: str) -> int:
    """Parse Dukascopy ISO 8601 timestamp string to unix milliseconds."""
    # e.g. "2024-01-01 23:00:00+00:00"
    dt = datetime.fromisoformat(s.strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _iso_date_to_ms(s: str) -> int:
    """Parse a YYYY-MM-DD date string to unix milliseconds at midnight UTC."""
    dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


# ------------------------------ CONVENIENCE ------------------------------

# Known Dukascopy file paths for major assets. Callers can override.
DUKASCOPY_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "external" / "dukascopy"

GOLD_5M_FILES = [
    DUKASCOPY_ROOT / "XAUUSD_5m_2010_2014.csv",
    DUKASCOPY_ROOT / "XAUUSD_5m_historical.csv",
    DUKASCOPY_ROOT / "XAUUSD_5m.csv",
]

SILVER_5M_FILES = [
    DUKASCOPY_ROOT / "XAGUSD_5m_historical.csv",
    DUKASCOPY_ROOT / "XAGUSD_5m.csv",
]


def load_gold_5m(start: Optional[str] = None, end: Optional[str] = None) -> list[Bar]:
    """Load full gold 5m history from Dukascopy files."""
    return load_dukascopy_multi(GOLD_5M_FILES, start=start, end=end)


def load_silver_5m(start: Optional[str] = None, end: Optional[str] = None) -> list[Bar]:
    """Load full silver 5m history from Dukascopy files."""
    return load_dukascopy_multi(SILVER_5M_FILES, start=start, end=end)
