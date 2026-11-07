"""Fail loudly when a live NORTH input goes stale.

Exists because continue-on-error hid two outages in 2026: FRED timing out
from CI (real_yield_10y frozen at 2026-07-30, forcing every v1 call FLAT)
and dukascopy_python 5.0.0 breaking imports (price cache frozen ~10-27).

Usage: python scripts/assert_data_fresh.py [--max-days N]
Exit 1 if any checked series' last date is older than N calendar days.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# (label, path, timestamp column). Daily FRED series publish with a 1-2
# business day lag, so 5 calendar days covers a long weekend.
CHECKS = [
    ("real_yield_10y (v1 live input)", "data/macro/real_yield_10y__DFII10.csv", "date"),
    ("dxy_proxy (v2 shadow input)",    "data/macro/dxy_proxy__DTWEXBGS.csv",    "date"),
    ("tnx_10y (regime context)",        "data/macro/tnx_10y__DGS10.csv",         "date"),
    ("XAUUSD 5m (Dukascopy cache)",     "data/external/dukascopy/XAUUSD_5m.csv", "ts"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-days", type=int, default=5)
    args = ap.parse_args()
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    stale = []
    for label, rel, col in CHECKS:
        p = ROOT / rel
        if not p.exists():
            print(f"[fresh] MISSING {label}: {rel}")
            stale.append(label)
            continue
        last = pd.to_datetime(pd.read_csv(p, usecols=[col])[col], utc=True).max()
        age = (now - last.tz_localize(None)).days
        flag = "STALE" if age > args.max_days else "ok"
        print(f"[fresh] {flag:5s} {label}: last={last.date()} age={age}d")
        if age > args.max_days:
            stale.append(label)
    if stale:
        print(f"[fresh] FAIL: {len(stale)} stale input(s): {', '.join(stale)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
