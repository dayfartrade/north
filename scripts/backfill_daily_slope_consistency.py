"""Backfill `candidate_shadows.daily_slope_consistency` into existing
shadow_equity_since_halt.jsonl rows. Idempotent — skips rows that already
have the field.

Adds the field to rows where direction_bias is LONG or SHORT (FLAT is
handled by filter_trend upstream). For LONG/SHORT rows, computes
20d daily GC slope as-of session date and records:

  candidate_shadows.daily_slope_consistency = {
    "would_skip": bool | None,
    "daily_20d_slope": float | None,
  }

Read-modifies-writes atomically. Never touches actual `would_skip` or
`outcome` — additive fields only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
SHADOW_LOG = ROOT / "data/shadow_equity_since_halt.jsonl"

from regime_context import _daily_20d_slope


def load_rows() -> list[dict]:
    if not SHADOW_LOG.exists():
        return []
    rows: list[dict] = []
    with open(SHADOW_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def write_atomic(rows: list[dict]) -> None:
    tmp = SHADOW_LOG.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    os.replace(tmp, SHADOW_LOG)


def compute_dsc(row: dict) -> dict | None:
    direction = row.get("direction_bias")
    if direction not in ("LONG", "SHORT"):
        return None
    date_str = row.get("or_open_utc", "")[:10]
    if not date_str:
        return None
    dsl = _daily_20d_slope(date_str)
    if dsl is None or dsl == 0:
        return {"would_skip": None, "daily_20d_slope": dsl}
    intra_slope = row.get("trend_slope")
    if intra_slope is None or intra_slope == 0:
        return {"would_skip": None, "daily_20d_slope": dsl}
    intra_sign = 1 if intra_slope > 0 else -1
    daily_sign = 1 if dsl > 0 else -1
    return {
        "would_skip": bool(intra_sign != daily_sign),
        "daily_20d_slope": dsl,
    }


def main() -> None:
    rows = load_rows()
    if not rows:
        print(f"no rows in {SHADOW_LOG}")
        return

    updated = 0
    skipped_already = 0
    skipped_no_direction = 0
    for row in rows:
        cs = row.setdefault("candidate_shadows", {})
        if "daily_slope_consistency" in cs:
            skipped_already += 1
            continue
        dsc = compute_dsc(row)
        if dsc is None:
            skipped_no_direction += 1
            continue
        cs["daily_slope_consistency"] = dsc
        updated += 1

    write_atomic(rows)
    print(f"backfill: {updated} updated, {skipped_already} already had field, "
          f"{skipped_no_direction} skipped (no direction / no date)")

    # Quick summary of what got added
    taken_with_dsc = [
        r for r in rows
        if not r.get("would_skip")
        and r.get("candidate_shadows", {}).get("daily_slope_consistency", {}).get("would_skip") is not None
    ]
    dsc_skips = [r for r in taken_with_dsc if r["candidate_shadows"]["daily_slope_consistency"]["would_skip"]]
    print(f"  taken shadow entries with valid dsc: {len(taken_with_dsc)}")
    print(f"  of those, dsc would skip:            {len(dsc_skips)}")


if __name__ == "__main__":
    main()
