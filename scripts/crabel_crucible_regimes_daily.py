"""Daily-behavior look at Crabel crucible regimes (per quant framework advice).

Windows:
  - 2011-2013 gold bear (post-2011-Sep peak $1900, drawdown to $1180)
  - 2020 pandemic shock (Feb-Apr 2020)
  - 2022 rate-hike shock (Apr-Sep 2022)

**What this script does NOT do:** replay Crabel ORB candidates (NR7, LON-short,
3-day pattern) — those are intraday filters and require 5m bars we do not
have for those windows.

**What this script DOES do:** characterize daily behavior — range, gap
frequency, drawdown, autocorrelation — so we can qualitatively judge whether
our current strategy (session ORB, breakout-follow) would face similar
microstructure stress. Read-only.
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GC_1D = ROOT / "data/gc/GC_1d.csv"


def load_gc_ohlc() -> list[dict]:
    rows: list[dict] = []
    with open(GC_1D, newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "date": r["ts"][:10],
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                })
            except (ValueError, KeyError):
                continue
    rows.sort(key=lambda r: r["date"])
    return rows


def slice_window(rows: list[dict], start: str, end: str) -> list[dict]:
    return [r for r in rows if start <= r["date"] < end]


def daily_returns(rows: list[dict]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(rows)):
        p0 = rows[i - 1]["close"]
        p1 = rows[i]["close"]
        if p0 > 0:
            out.append((p1 - p0) / p0)
    return out


def daily_range_pct(rows: list[dict]) -> list[float]:
    return [(r["high"] - r["low"]) / r["close"] for r in rows if r["close"] > 0]


def overnight_gap_pct(rows: list[dict]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(rows)):
        prev_close = rows[i - 1]["close"]
        today_open = rows[i]["open"]
        if prev_close > 0:
            out.append((today_open - prev_close) / prev_close)
    return out


def autocorr_lag1(vals: list[float]) -> float:
    if len(vals) < 3:
        return 0.0
    m = statistics.mean(vals)
    num = sum((vals[i] - m) * (vals[i + 1] - m) for i in range(len(vals) - 1))
    den = sum((v - m) ** 2 for v in vals)
    return num / den if den else 0.0


def max_drawdown(rows: list[dict]) -> tuple[float, str, str]:
    peak = float("-inf")
    peak_date = trough_date = rows[0]["date"] if rows else ""
    worst = 0.0
    worst_peak = worst_trough = rows[0]["date"] if rows else ""
    for r in rows:
        if r["close"] > peak:
            peak = r["close"]
            peak_date = r["date"]
        dd = (r["close"] - peak) / peak if peak > 0 else 0.0
        if dd < worst:
            worst = dd
            worst_peak = peak_date
            worst_trough = r["date"]
    return worst, worst_peak, worst_trough


def summarize(label: str, rows: list[dict]) -> None:
    if len(rows) < 5:
        print(f"\n== {label} ==\n  insufficient data (n={len(rows)})")
        return
    print(f"\n{'=' * 78}")
    print(f"{label}   ({rows[0]['date']} -> {rows[-1]['date']})   n={len(rows)}")
    print("=" * 78)
    rets = daily_returns(rows)
    ranges = daily_range_pct(rows)
    gaps = overnight_gap_pct(rows)
    dd, dd_peak, dd_trough = max_drawdown(rows)
    ret_mean = statistics.mean(rets) if rets else 0
    ret_sd = statistics.stdev(rets) if len(rets) > 1 else 0
    print(f"  price:            {rows[0]['close']:.0f} -> {rows[-1]['close']:.0f}   "
          f"({100 * (rows[-1]['close'] - rows[0]['close']) / rows[0]['close']:+.1f}%)")
    print(f"  max DD:           {100 * dd:+.1f}%   from {dd_peak} -> {dd_trough}")
    print(f"  daily return:     mean={100 * ret_mean:+.3f}%  sd={100 * ret_sd:.3f}%  "
          f"ann_sharpe={ret_mean / ret_sd * (252 ** 0.5) if ret_sd else 0:+.2f}")
    print(f"  daily range:      mean={100 * statistics.mean(ranges):.3f}%  "
          f"p90={100 * sorted(ranges)[int(0.9 * len(ranges))]:.3f}%")
    print(f"  overnight gap:    mean_abs={100 * statistics.mean([abs(g) for g in gaps]):.3f}%  "
          f"p90_abs={100 * sorted([abs(g) for g in gaps])[int(0.9 * len(gaps))]:.3f}%")
    print(f"  return autocorr:  lag-1={autocorr_lag1(rets):+.3f}  "
          f"(>0 means trend-persistence favors breakout follow-through)")


def main() -> None:
    rows = load_gc_ohlc()

    # Reference: the current era we're in
    summarize("REFERENCE: 2026-04 -> 2026-07 (current trading window)",
              slice_window(rows, "2026-04-01", "2026-08-01"))

    # Crucible windows
    summarize("CRUCIBLE 1: 2011-09 -> 2013-06 gold bear (from $1900 peak)",
              slice_window(rows, "2011-09-01", "2013-07-01"))
    summarize("CRUCIBLE 2: 2020-02 -> 2020-05 pandemic shock",
              slice_window(rows, "2020-02-01", "2020-06-01"))
    summarize("CRUCIBLE 3: 2022-04 -> 2022-11 rate-hike shock",
              slice_window(rows, "2022-04-01", "2022-12-01"))

    print("\n" + "=" * 78)
    print("HONEST LIMITATION")
    print("=" * 78)
    print(
        "This is a DAILY-scale characterization. The Crabel candidates in our\n"
        "v8 filter chain (NR7 LON gate, 3-day pattern whitelist, LON-short-only)\n"
        "are intraday filters. Testing them against these regimes requires\n"
        "historical 5m bars we do NOT have (GC_5m starts 2026-04-09).\n"
        "\n"
        "Read-across takeaway: if a crucible window shows very negative return\n"
        "autocorrelation (mean-reverting tape), a breakout-follow strategy like\n"
        "ORB tends to underperform there regardless of Crabel gates. Positive\n"
        "autocorr = trend persistence favors ORB. Compare vs REFERENCE to see\n"
        "how far the current regime is from each historical crucible.\n"
    )


if __name__ == "__main__":
    main()
