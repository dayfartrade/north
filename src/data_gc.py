"""Fetch and store GC=F (gold futures continuous) data from yfinance.

Strategy: snapshot all intervals to per-interval CSV. On re-run, merge new bars
into existing store so the minute-level archive grows past yfinance's 7-day cap.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

TICKER = "GC=F"
ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "gc"
STORE.mkdir(parents=True, exist_ok=True)

# (interval, max_period) supported by yfinance for free intraday
INTERVALS = [
    ("1m",  "7d"),
    ("2m",  "60d"),
    ("5m",  "60d"),
    ("15m", "60d"),
    ("30m", "60d"),
    ("60m", "730d"),
    ("1d",  "max"),
]


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    keep = [c for c in ("open", "high", "low", "close", "adj close", "volume") if c in df.columns]
    df = df[keep].copy()
    df.index.name = "ts"
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def _path(interval: str) -> Path:
    return STORE / f"GC_{interval}.csv"


def fetch_interval(interval: str, period: str) -> pd.DataFrame:
    df = yf.download(TICKER, period=period, interval=interval,
                     progress=False, auto_adjust=False)
    if df.empty:
        return df
    return _flatten(df)


def merge_and_save(interval: str, fresh: pd.DataFrame) -> tuple[int, int]:
    """Merge fresh bars into the stored CSV. Returns (rows_before, rows_after)."""
    path = _path(interval)
    if path.exists():
        old = pd.read_csv(path, index_col="ts", parse_dates=["ts"])
        if old.index.tz is None:
            old.index = old.index.tz_localize("UTC")
        before = len(old)
        combined = pd.concat([old, fresh])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        before = 0
        combined = fresh.sort_index()
    combined.to_csv(path)
    return before, len(combined)


def snapshot_all(verbose: bool = True) -> dict:
    """Pull every interval and merge into store. Returns per-interval stats."""
    stats = {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for interval, period in INTERVALS:
        try:
            fresh = fetch_interval(interval, period)
            if fresh.empty:
                stats[interval] = {"status": "empty"}
                if verbose:
                    print(f"[{now}] {interval:4s} -> empty")
                continue
            before, after = merge_and_save(interval, fresh)
            stats[interval] = {
                "status": "ok",
                "fresh_rows": len(fresh),
                "stored_before": before,
                "stored_after": after,
                "added": after - before,
                "first": str(fresh.index.min()),
                "last": str(fresh.index.max()),
            }
            if verbose:
                print(f"[{now}] {interval:4s} fresh={len(fresh):>6d} "
                      f"stored {before}->{after} (+{after-before})  "
                      f"range {fresh.index.min()} .. {fresh.index.max()}")
        except Exception as e:
            stats[interval] = {"status": "error", "error": str(e)}
            if verbose:
                print(f"[{now}] {interval:4s} ERROR: {e}")
    return stats


def load(interval: str) -> pd.DataFrame:
    """Load stored bars for a given interval."""
    path = _path(interval)
    if not path.exists():
        raise FileNotFoundError(f"No stored data for interval {interval}; run snapshot first.")
    df = pd.read_csv(path, index_col="ts", parse_dates=["ts"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


if __name__ == "__main__":
    snapshot_all()
