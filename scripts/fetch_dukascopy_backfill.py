"""Backfill Dukascopy 5m data with explicit start/end dates.

Runs on VPS (Windows may block freeserv.dukascopy.com). Idempotent per
output file. Chunks 30 days at a time. Writes canonical schema.

Purpose: extend XAUUSD 5m sample back to 2015 for OOS testing of Path Z
discovered on 2024-2026 data. Also usable for silver + FX pairs.

Usage:
  python fetch_dukascopy_backfill.py --symbol "XAU/USD" --start 2015-01-01 --end 2023-12-31
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import dukascopy_python as d

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "external" / "dukascopy"
CHUNK_DAYS = 30


def slug(symbol: str) -> str:
    return symbol.replace("/", "")


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index().rename(columns={"index": "ts", "timestamp": "ts"})
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    out["adj close"] = out["close"]
    return out[["ts", "open", "high", "low", "close", "adj close", "volume"]]


def fetch_chunk(symbol: str, start: datetime, end: datetime):
    try:
        df = d.fetch(
            instrument=symbol,
            interval=d.INTERVAL_MIN_5,
            offer_side=d.OFFER_SIDE_BID,
            start=start,
            end=end,
        )
        if df is None or df.empty:
            return None
        return normalize(df)
    except Exception as e:
        print(f"  ERROR {symbol} {start.date()}: {type(e).__name__}: {str(e)[:100]}",
              file=sys.stderr)
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True, help="e.g. XAU/USD")
    ap.add_argument("--start", required=True, help="ISO date YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="ISO date YYYY-MM-DD")
    ap.add_argument("--out-suffix", default="_5m_historical",
                    help="Filename suffix; default: _5m_historical")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / f"{slug(args.symbol)}{args.out_suffix}.csv"

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    # Resume if file exists
    existing = None
    if out_csv.exists():
        existing = pd.read_csv(out_csv, parse_dates=["ts"])
        existing["ts"] = pd.to_datetime(existing["ts"], utc=True)
        if len(existing):
            last_ts = existing["ts"].max().to_pydatetime()
            print(f"Resuming from {last_ts.isoformat()} ({len(existing)} rows exist)")
            start = max(start, last_ts + timedelta(minutes=5))

    print(f"[{args.symbol}] backfill {start.date()} -> {end.date()} to {out_csv.name}")

    cursor = start
    all_new = []
    total = 0
    chunk_count = 0
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
        chunk_count += 1
        print(f"[{chunk_count}] {cursor.date()} -> {chunk_end.date()} ... ",
              end="", flush=True)
        chunk = fetch_chunk(args.symbol, cursor, chunk_end)
        if chunk is None or chunk.empty:
            print("empty")
        else:
            print(f"{len(chunk)} bars")
            all_new.append(chunk)
            total += len(chunk)
            # Incremental write every 10 chunks so we don't lose progress
            if len(all_new) >= 10:
                merged = existing
                if all_new:
                    new_df = pd.concat(all_new, ignore_index=True)
                    merged = pd.concat([existing, new_df], ignore_index=True) \
                        if existing is not None else new_df
                    merged = merged.drop_duplicates(subset=["ts"], keep="first") \
                        .sort_values("ts")
                    merged.to_csv(out_csv, index=False)
                    print(f"    [checkpoint saved: {len(merged)} rows]")
                    existing = merged
                    all_new = []
        cursor = chunk_end

    # Final write
    if all_new:
        new_df = pd.concat(all_new, ignore_index=True)
        merged = pd.concat([existing, new_df], ignore_index=True) \
            if existing is not None else new_df
        merged = merged.drop_duplicates(subset=["ts"], keep="first").sort_values("ts")
        merged.to_csv(out_csv, index=False)

    final = pd.read_csv(out_csv, parse_dates=["ts"]) if out_csv.exists() else pd.DataFrame()
    print(f"\n[done] {out_csv.name} = {len(final)} rows total ({total} added this run)")


if __name__ == "__main__":
    main()
