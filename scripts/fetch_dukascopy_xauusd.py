"""Fetch XAU/USD 5m bars from Dukascopy for 2024-01-01 → today.

XAU/USD is spot gold — ~95% correlated with GC futures, useful as extended
directional proxy for shadow ship-gate analysis when yfinance 5m rolling
window (60 days) is the bottleneck.

Output: data/external/dukascopy/XAUUSD_5m.csv in canonical GC_5m schema.
Idempotent — resumes from last date in existing CSV.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import dukascopy_python as d

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "external" / "dukascopy"
OUT_CSV = OUT_DIR / "XAUUSD_5m.csv"

SYMBOL = "XAU/USD"
CHUNK_DAYS = 30  # fetch in monthly chunks


def load_existing() -> pd.DataFrame | None:
    if not OUT_CSV.exists():
        return None
    df = pd.read_csv(OUT_CSV, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    # dukascopy returns index=timestamp, cols=[open, high, low, close, volume]
    out = df.reset_index().rename(columns={"index": "ts", "timestamp": "ts"})
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    out["adj close"] = out["close"]  # match yfinance schema
    return out[["ts", "open", "high", "low", "close", "adj close", "volume"]]


def fetch_chunk(start: datetime, end: datetime) -> pd.DataFrame | None:
    try:
        df = d.fetch(
            instrument=SYMBOL,
            interval=d.INTERVAL_MIN_5,
            offer_side=d.OFFER_SIDE_BID,
            start=start,
            end=end,
        )
        if df is None or df.empty:
            return None
        return normalize(df)
    except Exception as e:
        print(f"  ERROR fetching {start.date()} -> {end.date()}: {type(e).__name__}: {str(e)[:120]}",
              file=sys.stderr)
        return None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_existing()

    if existing is not None and not existing.empty:
        cursor = existing["ts"].max().to_pydatetime()
        # Resume from last timestamp + 5m to avoid dup
        cursor = cursor + timedelta(minutes=5)
        print(f"resuming from {cursor.isoformat()}  ({len(existing)} rows already)")
    else:
        cursor = datetime(2024, 1, 1, tzinfo=timezone.utc)
        print(f"fresh pull from {cursor.isoformat()}")

    end_of_history = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if cursor >= end_of_history:
        print("already up to date")
        return

    all_new: list[pd.DataFrame] = []
    total_rows = 0
    while cursor < end_of_history:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end_of_history)
        print(f"fetching {cursor.date()} -> {chunk_end.date()} ... ", end="", flush=True)
        chunk = fetch_chunk(cursor, chunk_end)
        if chunk is None or chunk.empty:
            print("empty")
        else:
            print(f"{len(chunk)} bars")
            all_new.append(chunk)
            total_rows += len(chunk)
        cursor = chunk_end

    if not all_new:
        print("no new data")
        return

    new_df = pd.concat(all_new, ignore_index=True)
    if existing is not None:
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    # Dedupe on ts, keep first (existing values win on conflict)
    combined = combined.drop_duplicates(subset=["ts"], keep="first").sort_values("ts")
    combined.to_csv(OUT_CSV, index=False)
    print(f"\ntotal rows in {OUT_CSV.name}: {len(combined)}  (added {total_rows} new)")


if __name__ == "__main__":
    main()
