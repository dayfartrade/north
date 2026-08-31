"""Build the daily-read history archive for the NORTH site.

Emits two file groups consumed by Rook's detail-page route:

  site/data/history/index.json
    Chronological listing of every published week (newest first). Each
    entry: week_of, week_end, direction, outcome, has_detail. Timeline
    UX gates its "click through" link on has_detail == true. FLAT weeks
    are included with has_detail: false so the timeline stays complete.

  site/data/history/<week_of>.json
    Per-week detail, only emitted when a directional week has resolved.
    Contains the full call payload as originally published (verbatim),
    the deduped Mon-Fri daily briefs (from data/north_daily_brief.jsonl),
    and optionally a hourly price_series (from Dukascopy XAUUSD 5m) if
    bars are available. Missing fields are honest: if the daily-brief
    workflow wasn't live for a historical week, daily_briefs is []
    plus a daily_briefs_note explaining the gap.

Idempotent: every run reads current calls history and rewrites all
detail files. Safe to re-run; new fresh data (Dukascopy bars, macro
refresh) picked up automatically on the next tick.

Run cadence:
  - As a step in .github/workflows/weekly-publish.yml after
    scripts/far_weekly_gold_read_publish.py so newly resolved weeks
    get their per-week file the same push.
  - Manually: python scripts/build_history_archive.py

Design notes for future maintainers:
  - Never synthesize a daily brief. If a day is missing from
    north_daily_brief.jsonl, omit it. The archive shows what was
    actually captured at the time, not what "should have been."
  - The per-week detail file's `call` object is the raw call as
    published. Do not massage or reformat; downstream consumers
    depend on it matching the same shape as far_weekly_current.json.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"
DAILY_BRIEF_LOG = ROOT / "data" / "north_daily_brief.jsonl"
SITE_HISTORY_DIR = ROOT / "site" / "data" / "history"
SITE_INDEX = SITE_HISTORY_DIR / "index.json"
XAUUSD_5M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"

# Cutoff date: earlier resolved directional weeks have no daily briefs
# captured because the workflow went live starting 2026-08-24.
DAILY_BRIEF_WORKFLOW_START = "2026-08-24"

SCHEMA_VERSION = 1


def load_calls() -> list[dict]:
    if not CALLS_LOG.exists():
        return []
    with open(CALLS_LOG, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def load_briefs() -> list[dict]:
    if not DAILY_BRIEF_LOG.exists():
        return []
    with open(DAILY_BRIEF_LOG, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def is_resolved_directional(call: dict) -> bool:
    return (
        call.get("direction") in ("LONG", "SHORT")
        and (call.get("outcome") or {}).get("result") == "resolved"
    )


def build_index(calls: list[dict]) -> dict:
    weeks = []
    for c in sorted(calls, key=lambda x: x.get("week_of", ""), reverse=True):
        entry = {
            "week_of": c.get("week_of"),
            "week_end": c.get("week_end"),
            "direction": c.get("direction"),
        }
        if is_resolved_directional(c):
            outcome = c.get("outcome") or {}
            entry["outcome"] = {
                "net_return_pct": outcome.get("net_return_pct"),
                "exit_reason": outcome.get("exit_reason"),
            }
            entry["has_detail"] = True
        else:
            entry["outcome"] = None
            entry["has_detail"] = False
        weeks.append(entry)
    return {"schema_version": SCHEMA_VERSION, "weeks": weeks}


def briefs_for_week(all_briefs: list[dict], week_of: str) -> list[dict]:
    """Dedupe brief entries by calendar date, last-write-wins.

    Prefers the `site_shape` field if the brief was captured after the
    2026-08-31 field-snapshot upgrade (gates/event/commentary all live).
    Falls back to the raw metrics block for older briefs, which lands
    nulls for the fields that weren't captured at the time.
    """
    week_briefs = [b for b in all_briefs if b.get("week_of") == week_of]
    by_day = {}
    for b in sorted(week_briefs, key=lambda x: x.get("brief_utc", "")):
        day = (b.get("brief_utc") or "")[:10]
        if day:
            by_day[day] = b
    out = []
    for day in sorted(by_day.keys()):
        rec = by_day[day]
        site_shape = rec.get("site_shape")
        if site_shape and isinstance(site_shape, dict):
            entry = dict(site_shape)
            # Enforce date consistency in case site_shape captured with
            # a different reference day than the brief_utc timestamp
            entry["date"] = day
            out.append(entry)
            continue
        m = rec.get("metrics") or {}
        out.append({
            "date": day,
            "openPnlPct": m.get("pnl_pct"),
            "distanceStopAtr": m.get("stop_dist_atr"),
            # gates/event/commentary not captured in the raw brief log
            # for pre-2026-08-31 weeks.
            "gates": None,
            "event": None,
            "commentary": None,
        })
    return out


def load_week_price_series(week_of: str, week_end: str) -> dict | None:
    """Hourly OHLC for the week window if Dukascopy bars are available."""
    if not XAUUSD_5M.exists():
        return None
    start = pd.Timestamp(week_of, tz="UTC")
    end = pd.Timestamp(week_end, tz="UTC") + pd.Timedelta(hours=21)
    df = pd.read_csv(XAUUSD_5M, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df[(df["ts"] >= start) & (df["ts"] <= end)].sort_values("ts")
    if df.empty:
        return None
    idx = df.set_index("ts")
    agg = idx.resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna(how="all")
    series = []
    for ts, row in agg.iterrows():
        if pd.isna(row["close"]):
            continue
        series.append({
            "time_utc": int(ts.timestamp()),
            "open": round(float(row["open"]), 3),
            "high": round(float(row["high"]), 3),
            "low": round(float(row["low"]), 3),
            "close": round(float(row["close"]), 3),
        })
    if not series:
        return None
    return {"week_of": week_of, "week_end": week_end, "series": series}


def build_week_detail(call: dict, all_briefs: list[dict]) -> dict:
    week_of = call.get("week_of")
    week_end = call.get("week_end")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "week_of": week_of,
        "week_end": week_end,
        "call": call,
        "daily_briefs": briefs_for_week(all_briefs, week_of),
    }
    if not payload["daily_briefs"]:
        if week_of and week_of < DAILY_BRIEF_WORKFLOW_START:
            payload["daily_briefs_note"] = (
                f"Daily brief automation went live {DAILY_BRIEF_WORKFLOW_START}; "
                "earlier weeks have call + resolve only."
            )
        else:
            payload["daily_briefs_note"] = (
                "No daily briefs captured for this week. Check "
                "data/north_daily_brief.jsonl and workflow logs."
            )
    series = load_week_price_series(week_of, week_end) if week_of and week_end else None
    if series is not None:
        payload["price_series"] = series
    return payload


def emit(dry_run: bool = False) -> None:
    calls = load_calls()
    briefs = load_briefs()

    SITE_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    index = build_index(calls)
    if not dry_run:
        SITE_INDEX.write_text(
            json.dumps(index, indent=2, default=str) + "\n",
            encoding="utf-8")
    print(f"[index] {len(index['weeks'])} weeks total, "
          f"{sum(1 for w in index['weeks'] if w['has_detail'])} with detail")

    for call in calls:
        if not is_resolved_directional(call):
            continue
        week_of = call.get("week_of")
        if not week_of:
            continue
        detail = build_week_detail(call, briefs)
        out_path = SITE_HISTORY_DIR / f"{week_of}.json"
        if not dry_run:
            out_path.write_text(
                json.dumps(detail, indent=2, default=str) + "\n",
                encoding="utf-8")
        n_briefs = len(detail["daily_briefs"])
        has_series = "price_series" in detail
        print(f"[detail] {week_of} {call.get('direction')} briefs={n_briefs} "
              f"price_series={'yes' if has_series else 'no'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    emit(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
