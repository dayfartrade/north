"""Fetch multiple symbols from Dukascopy in canonical schema.

Runs on VPS (Windows may block freeserv.dukascopy.com). Idempotent per symbol.
Output: data/external/dukascopy/{SLUG}_5m.csv per symbol.

Usage:
  python scripts/fetch_dukascopy_symbols.py "EUR/USD" "GBP/USD" "USD/JPY"
"""
from __future__ import annotations

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


def load_existing(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


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


def fetch_symbol(symbol: str) -> None:
    out_csv = OUT_DIR / f"{slug(symbol)}_5m.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_existing(out_csv)
    if existing is not None and not existing.empty:
        cursor = existing["ts"].max().to_pydatetime() + timedelta(minutes=5)
        print(f"[{symbol}] resuming from {cursor.isoformat()} ({len(existing)} rows)")
    else:
        cursor = datetime(2024, 1, 1, tzinfo=timezone.utc)
        print(f"[{symbol}] fresh pull from {cursor.isoformat()}")

    end_of_history = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if cursor >= end_of_history:
        print(f"[{symbol}] already up to date")
        return

    all_new = []
    total = 0
    while cursor < end_of_history:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end_of_history)
        print(f"[{symbol}] fetch {cursor.date()} -> {chunk_end.date()} ... ", end="", flush=True)
        chunk = fetch_chunk(symbol, cursor, chunk_end)
        if chunk is None or chunk.empty:
            print("empty")
        else:
            print(f"{len(chunk)} bars")
            all_new.append(chunk)
            total += len(chunk)
        cursor = chunk_end

    if not all_new:
        return
    new_df = pd.concat(all_new, ignore_index=True)
    combined = pd.concat([existing, new_df], ignore_index=True) if existing is not None else new_df
    combined = combined.drop_duplicates(subset=["ts"], keep="first").sort_values("ts")
    combined.to_csv(out_csv, index=False)
    print(f"[{symbol}] wrote {len(combined)} rows total (added {total})")


def main() -> None:
    symbols = sys.argv[1:] if len(sys.argv) > 1 else ["EUR/USD", "GBP/USD", "USD/JPY"]
    for sym in symbols:
        fetch_symbol(sym)


if __name__ == "__main__":
    main()
