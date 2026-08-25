"""Refresh site JSON payloads for the active week.

Emits two files consumed by the NORTH site (Rook):

  1. site/data/far_weekly_current.json - adds `live_pnl_pct` +
     `live_updated_utc` fields on non-FLAT weeks. `live_pnl_pct` is
     trade P&L (positive = winning for the current direction), so a
     SHORT with falling gold reads positive. On FLAT weeks the fields
     are absent (client keys off their absence to hide live strip).

  2. site/data/far_weekly_price_series.json - hourly OHLC for the
     active week window (week_of Monday 00:00 UTC through week_end
     Friday 21:00 UTC), resampled from Dukascopy XAUUSD 5m. Format:
       [{ "time_utc": <int epoch seconds>, "open": float,
          "high": float, "low": float, "close": float }, ...]
     Time is Unix epoch seconds so lightweight-charts consumes it
     directly.

Runs both from the weekly publisher (Sunday 22 UTC - seeds an empty
series before the week starts) and from the daily-brief workflow
(Mon-Fri 12 UTC - refreshes intraweek).

Usage:
    python scripts/north_site_refresh.py
    python scripts/north_site_refresh.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"
SITE_CURRENT = ROOT / "site" / "data" / "far_weekly_current.json"
SITE_PRICE_SERIES = ROOT / "site" / "data" / "far_weekly_price_series.json"
XAUUSD_5M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"


def load_active_call() -> dict | None:
    if not CALLS_LOG.exists():
        return None
    with open(CALLS_LOG) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    for row in reversed(rows):
        if row.get("type") == "call" and row.get("outcome") is None:
            return row
    return None


def load_week_bars(week_of: str, week_end: str) -> pd.DataFrame:
    if not XAUUSD_5M.exists():
        return pd.DataFrame()
    start = pd.Timestamp(week_of, tz="UTC")
    end = pd.Timestamp(week_end, tz="UTC") + pd.Timedelta(hours=21)
    df = pd.read_csv(XAUUSD_5M, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df[(df["ts"] >= start) & (df["ts"] <= end)].sort_values("ts")
    return df.reset_index(drop=True)


def resample_hourly(bars: pd.DataFrame) -> list[dict]:
    if bars.empty:
        return []
    idx = bars.set_index("ts")
    agg = idx.resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna(how="all")
    out = []
    for ts, row in agg.iterrows():
        if pd.isna(row["close"]):
            continue
        out.append({
            "time_utc": int(ts.timestamp()),
            "open": round(float(row["open"]), 3),
            "high": round(float(row["high"]), 3),
            "low": round(float(row["low"]), 3),
            "close": round(float(row["close"]), 3),
        })
    return out


def compute_live_pnl_pct(call: dict, bars: pd.DataFrame) -> float | None:
    if bars.empty:
        return None
    entry = call.get("entry_approx")
    direction = call.get("direction")
    if entry is None or direction not in ("LONG", "SHORT"):
        return None
    now_price = float(bars["close"].iloc[-1])
    if direction == "LONG":
        return round((now_price - float(entry)) / float(entry) * 100, 3)
    return round((float(entry) - now_price) / float(entry) * 100, 3)


def refresh(dry_run: bool = False) -> None:
    call = load_active_call()
    if call is None:
        print("[skip] no active call in far_weekly_calls.jsonl")
        return
    week_of = call.get("week_of")
    week_end = call.get("week_end")
    if not week_of or not week_end or week_of == "unknown":
        print(f"[skip] active call missing week_of/week_end: {call}")
        return
    direction = call.get("direction")
    print(f"[active] week {week_of} -> {week_end}, direction={direction}")

    bars = load_week_bars(week_of, week_end)
    series = resample_hourly(bars)
    print(f"[bars] {len(bars)} 5m bars -> {len(series)} hourly points")

    live_pnl = compute_live_pnl_pct(call, bars) if direction != "FLAT" else None
    now_utc = datetime.now(timezone.utc).isoformat()

    if not SITE_CURRENT.exists():
        print(f"[warn] {SITE_CURRENT} missing - not writing live fields")
    else:
        current = json.loads(SITE_CURRENT.read_text(encoding="utf-8"))
        if direction == "FLAT":
            current.pop("live_pnl_pct", None)
            current.pop("live_updated_utc", None)
        elif live_pnl is not None:
            current["live_pnl_pct"] = live_pnl
            current["live_updated_utc"] = now_utc
        if not dry_run:
            SITE_CURRENT.write_text(
                json.dumps(current, indent=2, default=str), encoding="utf-8")
            print(f"[wrote] {SITE_CURRENT.name} live_pnl_pct={live_pnl}")
        else:
            print(f"[dry-run] would write live_pnl_pct={live_pnl}")

    if not dry_run:
        SITE_PRICE_SERIES.parent.mkdir(parents=True, exist_ok=True)
        SITE_PRICE_SERIES.write_text(
            json.dumps(series, separators=(",", ":")), encoding="utf-8")
        print(f"[wrote] {SITE_PRICE_SERIES.name} ({len(series)} points)")
    else:
        print(f"[dry-run] would write {SITE_PRICE_SERIES.name} "
              f"({len(series)} points)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(f"[north_site_refresh] {datetime.now(timezone.utc).isoformat()}")
    refresh(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
