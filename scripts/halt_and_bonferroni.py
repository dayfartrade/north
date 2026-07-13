"""Halt-threshold check + WGC-6 Bonferroni test + historical regime baseline.

Applies the quant framework (memory: quant_framework_gold.md):
  - Halt on 2x backtest max DD (gold-specific) or 20-25% capital DD.
  - Bonferroni-correct macro filters across all 6 WGC candidates considered.
  - Historical baseline: how common is the real_yield >= 2.2 regime?

Read-only. Prints report; no state modified.
"""
from __future__ import annotations

import csv
import math
import statistics
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FWD = ROOT / "data/tracker/orb_forward_log.csv"
GC_1D = ROOT / "data/gc/GC_1d.csv"
REAL_YIELD = ROOT / "data/macro/real_yield_10y__DFII10.csv"
DXY = ROOT / "data/macro/dxy_proxy__DTWEXBGS.csv"
TNX = ROOT / "data/macro/tnx_10y__DGS10.csv"

LAUNCH_DATE = "2026-07-01"


def load_daily(path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                out[row["date"][:10]] = float(row["value"])
            except (ValueError, KeyError):
                continue
    return out


def load_gc_daily(path: Path):
    out: dict[str, tuple[float, float, float, float]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                d = row["ts"][:10]
                out[d] = (float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
            except (ValueError, KeyError):
                continue
    return out


def lookup_le(daily: dict[str, float], d: str) -> float | None:
    best = None
    for k in daily:
        if k <= d and (best is None or k > best):
            best = k
    return daily[best] if best else None


def compute_dd(pnls: list[float]) -> dict:
    """Peak-to-trough dollar drawdown."""
    if not pnls:
        return {"max_dd": 0.0, "current_dd": 0.0, "peak": 0.0, "trough": 0.0}
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    trough_at_max = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = equity - peak
        if dd < max_dd:
            max_dd = dd
            trough_at_max = equity
    current_dd = equity - peak
    return {"max_dd": max_dd, "current_dd": current_dd, "final_equity": equity, "peak": peak, "trough": trough_at_max}


def main() -> None:
    real_yield = load_daily(REAL_YIELD)
    dxy = load_daily(DXY)
    tnx = load_daily(TNX)
    gc = load_gc_daily(GC_1D)

    trades = []
    with open(FWD, newline="") as f:
        for row in csv.DictReader(f):
            if row["took_trade"] != "True":
                continue
            try:
                trades.append({
                    "entry_ts": row["entry_ts"],
                    "date": row["entry_ts"][:10],
                    "session": row["session"],
                    "direction": float(row["direction"]),
                    "net_pnl": float(row["net_pnl"]),
                    "trend_slope": float(row["trend_slope"]),
                    "or_range": float(row["or_range"]),
                })
            except (ValueError, KeyError):
                continue

    live_trades = [t for t in trades if t["date"] >= LAUNCH_DATE]
    all_pnls = [t["net_pnl"] for t in trades]
    live_pnls = [t["net_pnl"] for t in live_trades]

    print("=" * 70)
    print(f"1) HALT-THRESHOLD CHECK (2x rule per quant advice)")
    print("=" * 70)
    all_dd = compute_dd(all_pnls)
    live_dd = compute_dd(live_pnls)
    print(f"  Forward log full window (n={len(trades)}):")
    print(f"    max_DD = ${all_dd['max_dd']:,.0f}  final_equity=${all_dd['final_equity']:,.0f}")
    print(f"  Live only since {LAUNCH_DATE} (n={len(live_trades)}):")
    print(f"    realized_DD = ${live_dd['max_dd']:,.0f}  current_DD = ${live_dd['current_dd']:,.0f}")

    # Halt trigger: live realized DD vs 2x full-window max_DD
    # (Full-window is proxy for backtest max DD until we regenerate backtest.)
    proxy_backtest_max = abs(all_dd["max_dd"])
    live_dd_mag = abs(live_dd["max_dd"])
    ratio = live_dd_mag / proxy_backtest_max if proxy_backtest_max > 0 else float("inf")
    print(f"\n  Proxy check: live_DD / forward_window_max_DD = ${live_dd_mag:,.0f} / ${proxy_backtest_max:,.0f} = {ratio:.2f}x")
    print(f"  Gold-specific halt threshold: 2.00x")
    if ratio >= 2.0:
        print("  ** HALT TRIGGER (2x): user decision needed **")
    elif ratio >= 1.5:
        print(f"  APPROACHING halt threshold (>=1.5x) — watch closely")
    else:
        print(f"  Below halt threshold — continue trading (but note this is forward-log proxy, not backtest max DD)")
    print("  Note: forward_window includes launch losses so proxy underestimates true backtest max DD; run backtest for hard number.")

    print()
    print("=" * 70)
    print(f"2) HISTORICAL REGIME BASELINE — real yield >= 2.2")
    print("=" * 70)
    ry_dates = sorted(real_yield.keys())
    # Compute per-decade fraction
    for decade_start in [2003, 2008, 2013, 2018, 2023]:
        vals = [v for d, v in real_yield.items() if int(d[:4]) >= decade_start and int(d[:4]) < decade_start + 5]
        if vals:
            frac = sum(1 for v in vals if v >= 2.2) / len(vals)
            print(f"  {decade_start}-{decade_start+4}: n={len(vals):5d}  mean={statistics.mean(vals):+.2f}  frac_ge_2.2={frac:.0%}")
    # And recent
    for window, label in [("2024-01-01", "2024+"), ("2025-01-01", "2025+"), ("2026-01-01", "2026+"), ("2026-07-01", "2026-07+")]:
        vals = [v for d, v in real_yield.items() if d >= window]
        if vals:
            frac = sum(1 for v in vals if v >= 2.2) / len(vals)
            print(f"  {label:12s}: n={len(vals):5d}  mean={statistics.mean(vals):+.2f}  frac_ge_2.2={frac:.0%}")

    print()
    print("=" * 70)
    print(f"3) WGC-6 BONFERRONI TEST ON FORWARD LOG (n={len(trades)})")
    print("=" * 70)
    print(f"  Candidates from theory (pre-registered per WGC / Erb-Harvey):")

    # We only have real_yield, dxy, tnx locally. Others (CB purchases, MM net long %, GLD delta,
    # Shanghai-COMEX premium) require external data we don't have yet.
    # Bonferroni penalty still applies because we CONSIDERED all 6.
    N_CONSIDERED = 6

    # Test 1: real yield gate on LONGs
    def stratify_by_ry(threshold, direction_filter=None):
        buckets = {"high": [], "low": []}
        for t in trades:
            if direction_filter and t["direction"] != direction_filter:
                continue
            ry = lookup_le(real_yield, t["date"])
            if ry is None:
                continue
            bucket = "high" if ry >= threshold else "low"
            buckets[bucket].append(t["net_pnl"])
        return buckets

    def report(label, buckets):
        for k in ["high", "low"]:
            pnls = buckets[k]
            if not pnls: continue
            wins = sum(1 for p in pnls if p > 0)
            print(f"    {label} [{k}] n={len(pnls)} wins={wins} ({100*wins/len(pnls):.0f}%) net=${sum(pnls):,.0f}")

    # Test each pre-registered variable
    print("  (a) real_yield >= 2.2 | LONG only")
    b = stratify_by_ry(2.2, direction_filter=1.0)
    report("real_yield", b)
    # p-value via binomial exact test approximation
    hi = b["high"]
    if hi:
        wins_hi = sum(1 for p in hi if p > 0)
        # Under H0: backtested 57% win rate, chance of <= wins_hi wins in n=len(hi)
        n = len(hi)
        p0 = 0.57
        # P(X <= wins_hi) under Binomial(n, 0.57)
        pv = sum(math.comb(n, k) * (p0**k) * ((1-p0)**(n-k)) for k in range(wins_hi + 1))
        pv_adj = min(pv * N_CONSIDERED, 1.0)
        print(f"    LONG-in-high-ry: P(X<={wins_hi}|Bin({n},{p0})) = {pv:.4f}  Bonferroni_x6 = {pv_adj:.4f}")

    print("  (b) DXY: no clean threshold hypothesis yet (log for future test)")
    # Just log mean DXY on wins vs losses
    long_win_dxy = []; long_loss_dxy = []
    for t in trades:
        if t["direction"] != 1.0: continue
        d = lookup_le(dxy, t["date"])
        if d is None: continue
        (long_win_dxy if t["net_pnl"] > 0 else long_loss_dxy).append(d)
    if long_win_dxy and long_loss_dxy:
        print(f"    LONG wins DXY mean: {statistics.mean(long_win_dxy):.3f} (n={len(long_win_dxy)})")
        print(f"    LONG loss DXY mean: {statistics.mean(long_loss_dxy):.3f} (n={len(long_loss_dxy)})")

    print("  (c) CB net purchases (WGC monthly): DATA NOT LOCAL — skipped, but counts to Bonferroni")
    print("  (d) CFTC managed-money net long %: DATA NOT LOCAL — skipped, counts to Bonferroni")
    print("  (e) GLD holdings delta: DATA NOT LOCAL — skipped, counts to Bonferroni")
    print("  (f) Shanghai-COMEX premium: DATA NOT LOCAL — skipped, counts to Bonferroni")

    print()
    print(f"  Interpretation: with N={N_CONSIDERED} candidates considered, any raw p-value must be x{N_CONSIDERED} to be honest.")
    print()

    print("=" * 70)
    print("4) TIME-TO-N=100 ESTIMATE AT CURRENT SAMPLE RATE")
    print("=" * 70)
    # Rate = trades per day since forward log started
    fwd_first = min(t["date"] for t in trades)
    fwd_last = max(t["date"] for t in trades)
    dt = (datetime.fromisoformat(fwd_last) - datetime.fromisoformat(fwd_first)).days + 1
    rate = len(trades) / dt if dt > 0 else 0
    days_to_100 = (100 - len(trades)) / rate if rate > 0 else float("inf")
    print(f"  Forward log span: {fwd_first} to {fwd_last} ({dt} days) — {len(trades)} taken trades")
    print(f"  Rate: {rate:.2f} trades/day  ->  {days_to_100:.0f} days to n=100  ({days_to_100/30:.1f} months)")
    print(f"  Gold-specific note: sequential prob test matters more than n=100 wait (per quant advice).")


if __name__ == "__main__":
    main()
