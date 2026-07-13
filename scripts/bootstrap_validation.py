"""Non-parametric validation of the SPRT halt call + bootstrapped reference max DD.

Two independent checks:
  (A) SPRT sensitivity: how robust is the halt verdict to the choice of p0?
      Compute P(wins <= observed | Binomial(n, p)) across p in [0.40, 0.60].
      If halt-signal holds across a wide p range, verdict is robust.

  (B) Bootstrapped max DD reference: shuffle the pre-launch forward-log trades
      M times, compute max DD per shuffle, take 95th percentile.
      Replaces the $20k placeholder in halt_monitor.py with a data-driven number.

Read-only. Prints report.
"""
from __future__ import annotations

import csv
import math
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FWD = ROOT / "data/tracker/orb_forward_log.csv"
LAUNCH_DATE = "2026-07-01"


def load_pnls_by_window() -> tuple[list[float], list[float]]:
    """Return (pre_launch_pnls, live_pnls)."""
    pre, live = [], []
    with open(FWD, newline="") as f:
        for row in csv.DictReader(f):
            if row["took_trade"] != "True":
                continue
            try:
                d = row["entry_ts"][:10]
                pnl = float(row["net_pnl"])
            except (ValueError, KeyError):
                continue
            (live if d >= LAUNCH_DATE else pre).append(pnl)
    return pre, live


def binomial_pmf(n: int, k: int, p: float) -> float:
    return math.comb(n, k) * (p ** k) * ((1 - p) ** (n - k))


def binomial_cdf_le(n: int, k: int, p: float) -> float:
    return sum(binomial_pmf(n, i, p) for i in range(k + 1))


def compute_max_dd(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = equity - peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def bootstrap_max_dd(pnls: list[float], target_n: int, M: int = 10000, seed: int = 42) -> dict:
    """Bootstrap resample pnls to make M sequences of target_n, compute max DD per sequence."""
    rng = random.Random(seed)
    max_dds = []
    for _ in range(M):
        sample = [rng.choice(pnls) for _ in range(target_n)]
        max_dds.append(compute_max_dd(sample))
    max_dds_mag = sorted([abs(d) for d in max_dds])
    return {
        "M": M,
        "target_n": target_n,
        "mean_max_dd_mag": statistics.mean(max_dds_mag),
        "median_max_dd_mag": statistics.median(max_dds_mag),
        "p50": max_dds_mag[int(0.50 * M)],
        "p75": max_dds_mag[int(0.75 * M)],
        "p90": max_dds_mag[int(0.90 * M)],
        "p95": max_dds_mag[int(0.95 * M)],
        "p99": max_dds_mag[int(0.99 * M)],
    }


def bootstrap_win_rate(pnls: list[float], target_n: int, M: int = 10000, seed: int = 42) -> dict:
    """Bootstrap: how often do we get <=1 win in target_n draws from pnls?"""
    rng = random.Random(seed)
    wins_dist = []
    for _ in range(M):
        sample = [rng.choice(pnls) for _ in range(target_n)]
        wins_dist.append(sum(1 for p in sample if p > 0))
    return {
        "M": M,
        "target_n": target_n,
        "mean_wins": statistics.mean(wins_dist),
        "median_wins": statistics.median(wins_dist),
        "prob_wins_le_1": sum(1 for w in wins_dist if w <= 1) / M,
        "prob_wins_le_2": sum(1 for w in wins_dist if w <= 2) / M,
        "prob_wins_le_3": sum(1 for w in wins_dist if w <= 3) / M,
    }


def main() -> None:
    pre, live = load_pnls_by_window()

    print("=" * 70)
    print("(A) SPRT SENSITIVITY — is HALT verdict robust to p0 choice?")
    print("=" * 70)
    live_wins = sum(1 for p in live if p > 0)
    live_n = len(live)
    print(f"  Observed: {live_wins}/{live_n} wins ({100*live_wins/live_n:.0f}%)")
    print(f"  Parametric P(X <= {live_wins} | Binomial({live_n}, p)) across p:")
    print(f"    {'p':>6s}  {'P(X<={live_wins})':>15s}  {'2xBonferroni':>13s}  {'flag':>6s}")
    for p in [0.40, 0.45, 0.50, 0.52, 0.55, 0.57, 0.60]:
        pv = binomial_cdf_le(live_n, live_wins, p)
        bonf2 = min(pv * 2, 1.0)  # Bonferroni for a two-tail hypothesis
        flag = "**" if pv < 0.05 else "  "
        print(f"    {p:6.2f}  {pv:15.4f}  {bonf2:13.4f}  {flag:>6s}")
    print(f"  Read: if P(X<={live_wins}) < 0.05 across a wide p range (say 0.45+),")
    print(f"        HALT verdict is robust to hypothesis choice.")

    print()
    print("=" * 70)
    print("(B) BOOTSTRAP WIN-RATE DIST — using pre-launch forward log as null")
    print("=" * 70)
    print(f"  Null sample: {len(pre)} pre-launch trades, {sum(1 for p in pre if p > 0)} wins ({100*sum(1 for p in pre if p > 0)/len(pre):.0f}%)")
    print(f"  Bootstrap {10000} draws of n={live_n} from null:")
    br = bootstrap_win_rate(pre, live_n)
    print(f"    mean_wins  = {br['mean_wins']:.2f}")
    print(f"    P(wins<=1) = {br['prob_wins_le_1']:.4f}")
    print(f"    P(wins<=2) = {br['prob_wins_le_2']:.4f}")
    print(f"    P(wins<=3) = {br['prob_wins_le_3']:.4f}")
    print(f"  Read: our 1/10 outcome under pre-launch null has empirical p = {br['prob_wins_le_1']:.4f}")

    print()
    print("=" * 70)
    print("(C) BOOTSTRAP MAX DD — replaces halt_monitor.py placeholder")
    print("=" * 70)
    # Bootstrap max DD for a sample of size = live_n from pre-launch (null)
    md_short = bootstrap_max_dd(pre, live_n)
    print(f"  Pre-launch null, target n={live_n}, M={md_short['M']}:")
    print(f"    mean max_DD_mag   = ${md_short['mean_max_dd_mag']:>7,.0f}")
    print(f"    median            = ${md_short['p50']:>7,.0f}")
    print(f"    p75               = ${md_short['p75']:>7,.0f}")
    print(f"    p90               = ${md_short['p90']:>7,.0f}")
    print(f"    p95               = ${md_short['p95']:>7,.0f}   <-- suggested REFERENCE_MAX_DD")
    print(f"    p99               = ${md_short['p99']:>7,.0f}")

    # Also for larger n (n=72 backtest-equivalent) as a longer-horizon reference
    md_long = bootstrap_max_dd(pre, 72)
    print(f"  Pre-launch null, target n=72 (backtest-equiv horizon):")
    print(f"    p95               = ${md_long['p95']:>7,.0f}   <-- alternate REFERENCE_MAX_DD (longer horizon)")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Live realized max DD (from halt_monitor): $12,548")
    print(f"  Bootstrap p95 max DD (n={live_n}):        ${md_short['p95']:,.0f}")
    print(f"  Bootstrap p95 max DD (n=72 horizon):    ${md_long['p95']:,.0f}")
    print(f"  Ratio live_DD / bootstrap p95 (n={live_n}):  {12548/md_short['p95']:.2f}x")
    print(f"  Empirical P(1 win in 10) under null:    {br['prob_wins_le_1']:.4f}")
    print()
    print(f"  Verdict robustness: SPRT halt call ", end="")
    if br['prob_wins_le_1'] < 0.05:
        print("HOLDS (non-parametric p < 0.05)")
    else:
        print("does NOT hold (non-parametric p >= 0.05)")


if __name__ == "__main__":
    main()
