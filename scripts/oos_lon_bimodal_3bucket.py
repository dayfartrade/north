"""OOS 3-bucket test of the LON bimodal claim (2026-07-13 finding).

The 07-13 memory recorded a `LON is BIMODAL` finding at n=8: edge at ry<2.0
AND ry>=2.2, failure in the 2.0-2.2 transition. This script cross-checks
the same 3-bucket regime split against 20+ years of daily gold data.

Data limits (documented honestly):
  - We do NOT have 20 years of 5m intraday bars — the LON ORB itself cannot
    be replayed. This script tests the DAILY-return proxy of the bimodal
    hypothesis, which is a weaker but feasible check.
  - GC_1d covers 2000-08-30 -> today. DFII10 covers ~2003-01 -> today.
  - Overlap sample = ~5,880 days.

Read-only. No live impact. Companion to `oos_real_yield_regime.py`.
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_YIELD = ROOT / "data/macro/real_yield_10y__DFII10.csv"
GC_1D = ROOT / "data/gc/GC_1d.csv"


def load_ry() -> dict[str, float]:
    out: dict[str, float] = {}
    with open(REAL_YIELD, newline="") as f:
        for row in csv.DictReader(f):
            try:
                out[row["date"][:10]] = float(row["value"])
            except (ValueError, KeyError):
                continue
    return out


def load_gc() -> dict[str, float]:
    out: dict[str, float] = {}
    with open(GC_1D, newline="") as f:
        for row in csv.DictReader(f):
            try:
                out[row["ts"][:10]] = float(row["close"])
            except (ValueError, KeyError):
                continue
    return out


def bucket_of(ry_val: float) -> str:
    if ry_val < 2.0:
        return "LOW (<2.0)"
    if ry_val < 2.2:
        return "MID (2.0-2.2)"
    return "HIGH (>=2.2)"


def stats(rets: list[float]) -> dict:
    if not rets:
        return {"n": 0}
    m = statistics.mean(rets)
    sd = statistics.stdev(rets) if len(rets) > 1 else 0.0
    pos = sum(1 for r in rets if r > 0)
    t = m / (sd / (len(rets) ** 0.5)) if sd > 0 else 0
    return {
        "n": len(rets),
        "mean_pct": 100 * m,
        "sd_pct": 100 * sd,
        "pos_pct": 100 * pos / len(rets),
        "t": t,
        "sharpe_ann": (m / sd) * (252 ** 0.5) if sd > 0 else 0,
    }


def run_window(label: str, start: str, end: str, ry: dict, gc: dict,
                dates_sorted: list[str], horizon: int = 1) -> None:
    print(f"\n{'=' * 78}")
    print(f"Window: {label}   ({start} -> {end})   horizon={horizon}d fwd return")
    print("=" * 78)
    buckets: dict[str, list[float]] = {
        "LOW (<2.0)": [],
        "MID (2.0-2.2)": [],
        "HIGH (>=2.2)": [],
    }
    for d in dates_sorted:
        if d < start or d >= end:
            continue
        if d not in ry:
            continue
        idx = dates_sorted.index(d)
        fwd_idx = idx + horizon
        if fwd_idx >= len(dates_sorted):
            continue
        fwd = dates_sorted[fwd_idx]
        if d not in gc or fwd not in gc:
            continue
        r = (gc[fwd] - gc[d]) / gc[d]
        buckets[bucket_of(ry[d])].append(r)

    print(f"{'bucket':16s} {'n':>5s} {'mean%':>8s} {'sd%':>7s} {'pos%':>6s} {'t':>7s} {'sharpe_ann':>10s}")
    for name in ("LOW (<2.0)", "MID (2.0-2.2)", "HIGH (>=2.2)"):
        s = stats(buckets[name])
        if s["n"] == 0:
            print(f"{name:16s} {'0':>5s}")
            continue
        print(f"{name:16s} {s['n']:>5d} {s['mean_pct']:>+7.3f} {s['sd_pct']:>6.3f} "
              f"{s['pos_pct']:>5.1f} {s['t']:>+7.2f} {s['sharpe_ann']:>+9.2f}")

    # Bimodal signature check: MID underperforms both LOW and HIGH
    if all(buckets[b] for b in buckets):
        m_low = statistics.mean(buckets["LOW (<2.0)"])
        m_mid = statistics.mean(buckets["MID (2.0-2.2)"])
        m_high = statistics.mean(buckets["HIGH (>=2.2)"])
        bimodal = (m_mid < m_low) and (m_mid < m_high)
        margin_low = m_low - m_mid
        margin_high = m_high - m_mid
        print(f"\nBimodal signature (MID worse than LOW AND HIGH): {'YES' if bimodal else 'NO'}")
        print(f"  MID vs LOW:  {100*margin_low:+.3f}%   MID vs HIGH: {100*margin_high:+.3f}%")


def main() -> None:
    ry = load_ry()
    gc = load_gc()
    dates_sorted = sorted(gc.keys())

    print(f"real yield: {len(ry)} days, {min(ry) if ry else '?'} -> {max(ry) if ry else '?'}")
    print(f"GC daily:   {len(gc)} days, {min(gc) if gc else '?'} -> {max(gc) if gc else '?'}")

    for horizon in (1, 5, 20):
        run_window("FULL sample", "2003-01-01", "2100-01-01", ry, gc, dates_sorted, horizon=horizon)
        run_window("2003-2007 (rate-hike cycle, ~35% HIGH days)",
                    "2003-01-01", "2008-01-01", ry, gc, dates_sorted, horizon=horizon)
        run_window("2008-2021 (QE / real-yield floor era)",
                    "2008-01-01", "2022-01-01", ry, gc, dates_sorted, horizon=horizon)
        run_window("2022-current (real-yield rebuild)",
                    "2022-01-01", "2100-01-01", ry, gc, dates_sorted, horizon=horizon)

    print()
    print("=" * 78)
    print("HONEST LIMITATION")
    print("=" * 78)
    print(
        "This tests the DAILY-return proxy. The LON ORB claim is intraday and\n"
        "cannot be validated against 20yr data without historical 5m bars.\n"
        "Interpret bimodal signature 'YES' as directional evidence at best; a\n"
        "'NO' does not falsify the LON ORB claim, just fails to confirm it via\n"
        "this weaker proxy.\n"
    )


if __name__ == "__main__":
    main()
