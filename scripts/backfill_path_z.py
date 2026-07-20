"""Backfill candidate_shadows.path_z into an existing shadow_equity JSONL.

Uses the XAU/USD 5m historical file to compute ER for each row, checks all
four Path Z conditions, and writes the decision back into candidate_shadows.

Idempotent — rows that already have path_z are skipped.

Usage:
  python scripts/backfill_path_z.py [--input path.jsonl] [--src-csv path.csv]

Defaults: input = data/shadow_equity_xauusd_backfill_full.jsonl
          src-csv = data/external/dukascopy/XAUUSD_5m.csv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from regime_context import _efficiency_ratio


def load_bars(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df


def load_rows(jsonl_path: Path) -> list[dict]:
    rows: list[dict] = []
    if not jsonl_path.exists():
        return rows
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def path_z_decision(row: dict, bars: pd.DataFrame) -> dict | None:
    """Compute path_z decision for one shadow row. Returns dict to store in candidate_shadows."""
    session = row.get("session")
    direction = row.get("direction_bias")
    or_open_str = row.get("or_open_utc", "")
    or_close_str = row.get("or_close_utc", "") or or_open_str
    if not or_open_str:
        return None

    try:
        or_open_ts = pd.Timestamp(or_open_str)
        if or_open_ts.tz is None:
            or_open_ts = or_open_ts.tz_localize("UTC")
    except Exception:
        return None

    try:
        or_close_ts = pd.Timestamp(or_close_str)
        if or_close_ts.tz is None:
            or_close_ts = or_close_ts.tz_localize("UTC")
    except Exception:
        or_close_ts = or_open_ts + pd.Timedelta(minutes=25)

    # Get 21 5m closes ending at or_close_ts (inclusive)
    mask = bars.index <= or_close_ts
    if not mask.any():
        return None
    end_idx = bars.index[mask][-1]
    end_pos = bars.index.get_loc(end_idx)
    start_pos = max(0, end_pos - 20)
    closes = bars.iloc[start_pos: end_pos + 1]["close"].tolist()
    er = _efficiency_ratio(closes, n=20)

    dow = or_open_ts.weekday()
    dow_name = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[dow]

    reasons = []
    if session != "NY":
        reasons.append(f"session {session} != NY")
    if direction != "SHORT":
        reasons.append(f"direction {direction} != SHORT")
    if er is None:
        reasons.append("ER unavailable")
    elif er >= 0.30:
        reasons.append(f"ER {er:.3f} >= 0.30")
    if dow not in (0, 1, 2):
        reasons.append(f"dow {dow_name} not Mon-Wed")

    would_skip = bool(reasons)
    return {
        "would_skip": would_skip,
        "would_take": not would_skip,
        "skip_reason": " | ".join(reasons) if reasons else None,
        "er_5m_20": er,
        "dow": dow_name,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="data/shadow_equity_xauusd_backfill_full.jsonl")
    p.add_argument("--src-csv", default="data/external/dukascopy/XAUUSD_5m.csv")
    args = p.parse_args()

    jsonl = ROOT / args.input
    csv_path = ROOT / args.src_csv

    print(f"Loading bars from {csv_path.name} ...")
    bars = load_bars(csv_path)
    print(f"  {len(bars):,} bars {bars.index[0].date()} -> {bars.index[-1].date()}")

    print(f"Loading shadow rows from {jsonl.name} ...")
    rows = load_rows(jsonl)
    if not rows:
        print("no rows loaded")
        return
    print(f"  {len(rows)} rows")

    updated = 0
    already = 0
    no_data = 0
    would_take = 0
    for row in rows:
        cs = row.setdefault("candidate_shadows", {})
        if "path_z" in cs:
            already += 1
            continue
        decision = path_z_decision(row, bars)
        if decision is None:
            no_data += 1
            continue
        cs["path_z"] = decision
        updated += 1
        if decision.get("would_take"):
            would_take += 1

    # Write atomically
    tmp = jsonl.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    os.replace(tmp, jsonl)

    print(f"\nUpdated: {updated}  already: {already}  no-data: {no_data}")
    print(f"Path Z would_take=True count: {would_take}")


if __name__ == "__main__":
    main()
