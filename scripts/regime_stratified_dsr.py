"""Regime-stratified DSR audit — is LON's 75% edge structural or regime-conditional?

Runs the Path Y backtest, stratifies each trade by real_yield_10y at OR-close,
computes per-stratum + per-session metrics. Answers:
  - Does LON win rate hold across ry regimes?
  - Does ASIA improve outside high-ry regime?
  - Are NY losses concentrated in a specific regime?

Read-only. Prints report; no state changes.
"""
from __future__ import annotations

import csv
import statistics
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_gc import load as gc_load
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on
from edge_session_orb_v7_final import SESSION_CONFIG, run_orb_v7

REAL_YIELD_CSV = ROOT / "data/macro/real_yield_10y__DFII10.csv"

REGIMES = [
    ("very_low", None, 1.5),
    ("low", 1.5, 2.0),
    ("mid", 2.0, 2.2),
    ("high", 2.2, None),
]


def _load_real_yield() -> dict[str, float]:
    out: dict[str, float] = {}
    with open(REAL_YIELD_CSV, newline="") as f:
        for row in csv.DictReader(f):
            try:
                out[row["date"][:10]] = float(row["value"])
            except (ValueError, KeyError):
                continue
    return out


def _lookup_le(series: dict[str, float], date_str: str) -> float | None:
    best = None
    for k in series:
        if k <= date_str and (best is None or k > best):
            best = k
    return series.get(best) if best else None


def _regime_label(ry: float | None) -> str:
    if ry is None:
        return "unknown"
    for label, lo, hi in REGIMES:
        if (lo is None or ry >= lo) and (hi is None or ry < hi):
            return label
    return "unknown"


def _fmt(rows: list[dict]) -> str:
    if not rows:
        return "n=0"
    n = len(rows)
    wins = sum(1 for r in rows if r["net_pnl"] > 0)
    total = sum(r["net_pnl"] for r in rows)
    mean = total / n
    if n > 1:
        sd = statistics.stdev(r["net_pnl"] for r in rows)
        se = sd / (n ** 0.5)
    else:
        se = 0
    return f"n={n:3d} win={wins}/{n} ({100*wins/n:3.0f}%) total=${total:+7,.0f} mean=${mean:+8,.0f} SE=${se:.0f}"


def main() -> None:
    ry_series = _load_real_yield()
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    all_taken = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        if df.empty:
            continue
        for _, row in df.iterrows():
            if not row.get("took_trade", False):
                continue
            d = str(row["entry_ts"])[:10]
            ry = _lookup_le(ry_series, d)
            all_taken.append({
                "date": d,
                "session": sess_name,
                "direction": int(row["direction"]),
                "net_pnl": float(row["net_pnl"]),
                "won": float(row["net_pnl"]) > 0,
                "real_yield": ry,
                "regime": _regime_label(ry),
                "or_range": float(row["or_range"]),
                "atr": float(row["atr"]),
            })

    if not all_taken:
        print("No taken trades under Path Y config.")
        return

    print("=" * 76)
    print(f"REGIME-STRATIFIED DSR (Path Y config, n={len(all_taken)} taken trades)")
    print("=" * 76)

    print("\n[FULL SAMPLE]")
    print(f"  {_fmt(all_taken)}")

    print("\n[BY SESSION]")
    for sess in ["LON", "NY", "ASIA"]:
        rows = [r for r in all_taken if r["session"] == sess]
        print(f"  {sess:4s} {_fmt(rows)}")

    print("\n[BY REGIME]")
    for label, lo, hi in REGIMES:
        rows = [r for r in all_taken if r["regime"] == label]
        bound = f"[{lo if lo is not None else '-inf'}, {hi if hi is not None else '+inf'})"
        print(f"  {label:9s} ry {bound:16s} {_fmt(rows)}")

    print("\n[BY SESSION x REGIME]")
    print(f"  {'session':7s} {'regime':10s} {'metrics':60s}")
    for sess in ["LON", "NY", "ASIA"]:
        for label, _, _ in REGIMES:
            rows = [r for r in all_taken if r["session"] == sess and r["regime"] == label]
            if rows:
                print(f"  {sess:7s} {label:10s} {_fmt(rows)}")

    # Key questions
    print("\n" + "=" * 76)
    print("KEY QUESTIONS")
    print("=" * 76)

    # Q1: LON edge across regimes
    lon_by_regime = {}
    for label, _, _ in REGIMES:
        rows = [r for r in all_taken if r["session"] == "LON" and r["regime"] == label]
        if rows:
            wins = sum(1 for r in rows if r["won"])
            lon_by_regime[label] = (len(rows), wins, sum(r["net_pnl"] for r in rows))
    print("\nQ1: Is LON's 75% edge structural or regime-conditional?")
    for label, (n, w, pnl) in lon_by_regime.items():
        wr = 100 * w / n if n > 0 else 0
        print(f"    LON in {label}: {w}/{n} ({wr:.0f}%) net=${pnl:+,.0f}")

    # Q2: NY across regimes
    print("\nQ2: Are NY losses concentrated in high-ry regime?")
    for label, _, _ in REGIMES:
        rows = [r for r in all_taken if r["session"] == "NY" and r["regime"] == label]
        if rows:
            wins = sum(1 for r in rows if r["won"])
            total = sum(r["net_pnl"] for r in rows)
            print(f"    NY in {label}: {wins}/{len(rows)} ({100*wins/len(rows):.0f}%) net=${total:+,.0f}")

    # Q3: ASIA
    print("\nQ3: Does ASIA improve in low-ry regime?")
    for label, _, _ in REGIMES:
        rows = [r for r in all_taken if r["session"] == "ASIA" and r["regime"] == label]
        if rows:
            wins = sum(1 for r in rows if r["won"])
            total = sum(r["net_pnl"] for r in rows)
            print(f"    ASIA in {label}: {wins}/{len(rows)} ({100*wins/len(rows):.0f}%) net=${total:+,.0f}")


if __name__ == "__main__":
    main()
