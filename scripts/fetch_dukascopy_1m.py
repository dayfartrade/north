"""Backfill Dukascopy 1m data — dedicated fetcher (5m version is separate).

For fast-scalping candidate testing (Path S). Chunks 15 days to keep
individual requests smaller since 1m has ~5x the data volume of 5m.

Usage:
  python fetch_dukascopy_1m.py --symbol XAU/USD --start 2018-01-01 --end 2023-12-31
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
CHUNK_DAYS = 15


def slug(symbol: str) -> str:
    return symbol.replace("/", "")


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index().rename(columns={"index": "ts", "timestamp": "ts"})
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    out["adj close"] = out["close"]
    return out[["ts", "open", "high", "low", "close", "adj close", "volume"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / f"{slug(args.symbol)}_1m_historical.csv"
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    existing = None
    if out_csv.exists():
        existing = pd.read_csv(out_csv, parse_dates=["ts"])
        existing["ts"] = pd.to_datetime(existing["ts"], utc=True)
        if len(existing):
            last_ts = existing["ts"].max().to_pydatetime()
            start = max(start, last_ts + timedelta(minutes=1))
            print(f"Resuming from {start.isoformat()} ({len(existing)} rows)")

    print(f"[{args.symbol}] 1m backfill {start.date()} -> {end.date()}")
    cursor = start
    all_new = []
    total = 0
    chunk_i = 0
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
        chunk_i += 1
        print(f"[{chunk_i}] {cursor.date()} -> {chunk_end.date()} ... ",
              end="", flush=True)
        try:
            df = d.fetch(instrument=args.symbol,
                          interval=d.INTERVAL_MIN_1,
                          offer_side=d.OFFER_SIDE_BID,
                          start=cursor, end=chunk_end)
            if df is None or df.empty:
                print("empty")
            else:
                chunk = normalize(df)
                print(f"{len(chunk)} bars")
                all_new.append(chunk)
                total += len(chunk)
        except Exception as e:
            print(f"ERR {type(e).__name__}: {str(e)[:60]}")
        cursor = chunk_end
        # Checkpoint every 5 chunks (1m is data-heavy)
        if len(all_new) >= 5:
            merged = pd.concat(all_new, ignore_index=True)
            if existing is not None:
                merged = pd.concat([existing, merged], ignore_index=True)
            merged = merged.drop_duplicates(subset=["ts"], keep="first") \
                .sort_values("ts")
            merged.to_csv(out_csv, index=False)
            print(f"    [checkpoint {len(merged)} rows total]")
            existing = merged
            all_new = []
    if all_new:
        merged = pd.concat(all_new, ignore_index=True)
        if existing is not None:
            merged = pd.concat([existing, merged], ignore_index=True)
        merged = merged.drop_duplicates(subset=["ts"], keep="first") \
            .sort_values("ts")
        merged.to_csv(out_csv, index=False)
    final = pd.read_csv(out_csv, parse_dates=["ts"])
    print(f"\n[done] {out_csv.name} = {len(final)} rows")


if __name__ == "__main__":
    main()
