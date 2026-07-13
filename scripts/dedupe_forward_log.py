"""Clean duplicate trades from data/tracker/orb_forward_log.csv in-place.

Root cause fixed in src/track_orb.py (Sunday session-attribution bug).
This is a one-shot cleanup for historical duplicates already in the CSV.

Dedupe key: (entry_ts, entry_price, exit_price) tuple. Keeps first
occurrence's row. Writes to tmp + atomic rename.

Dry-run by default. Pass --apply to write.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data/tracker/orb_forward_log.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write dedupe result to file")
    args = parser.parse_args()

    if not LOG.exists():
        print(f"[dedupe] {LOG.relative_to(ROOT)} not found")
        return

    with open(LOG, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not fieldnames:
        print("[dedupe] no fieldnames")
        return

    seen = {}
    dupes = []
    kept = []
    for row in rows:
        if row.get("took_trade") != "True":
            # Keep no-take rows as-is (dedupe key doesn't apply)
            kept.append(row)
            continue
        key = (row.get("entry_ts"), row.get("entry_price"), row.get("exit_price"))
        if any(v is None or v == "" for v in key):
            kept.append(row)  # incomplete keys keep
            continue
        if key in seen:
            dupes.append(row)
        else:
            seen[key] = row
            kept.append(row)

    print(f"Total rows:      {len(rows)}")
    print(f"Unique kept:     {len(kept)}")
    print(f"Duplicates:      {len(dupes)}")

    if dupes:
        print("\nDuplicate examples (first 5):")
        for d in dupes[:5]:
            print(f"  {d['entry_ts']}  session={d['session']}  net_pnl={d['net_pnl']}")

    if not args.apply:
        print("\n[dry-run] No changes written. Pass --apply to save.")
        return

    if not dupes:
        print("[dedupe] No dupes to remove.")
        return

    tmp = LOG.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in kept:
            w.writerow(row)
    os.replace(tmp, LOG)
    print(f"[dedupe] Wrote {len(kept)} rows to {LOG.relative_to(ROOT)} ({len(dupes)} removed)")


if __name__ == "__main__":
    main()
