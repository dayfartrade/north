"""Monte Carlo permutation analysis of Path Z equity curve.

Davey Ch 14/19-style Monte Carlo — permute the ORDER of the n=85
Path Z trades 5000 times, recompute equity curve, and report the
distribution of:
  (a) terminal wealth
  (b) max drawdown
  (c) longest losing streak
  (d) probability of ruin at $10k/$25k/$50k starting capital

Purpose: sequence-independent stress test. If Path Z's +$39k total is
driven by structural edge, MOST permutations should be net-positive with
manageable drawdown. If it's driven by lucky sequence (e.g., winners
early), MC will reveal a wide distribution with many terrible paths.

Also computes non-shuffled diagnostics:
  - actual max DD on the historical trade sequence
  - actual longest losing streak
"""
from __future__ import annotations

import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH_Z_LOG = ROOT / "data" / "shadow_equity_path_z.jsonl"

N_BOOT = 5000
STARTING_CAPITAL = [10_000, 25_000, 50_000, 100_000]


def load_pnls() -> list[float]:
    pnls = []
    with open(PATH_Z_LOG) as f:
        for line in f:
            if line.strip():
                pnls.append(float(json.loads(line)["outcome"]["net_pnl"]))
    return pnls


def max_drawdown(equity: list[float]) -> float:
    """Return max peak-to-trough drawdown (negative number, or 0 if none)."""
    peak = equity[0]
    max_dd = 0.0
    for eq in equity:
        if eq > peak:
            peak = eq
        dd = eq - peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def longest_losing_streak(pnls: list[float]) -> int:
    longest = 0; current = 0
    for p in pnls:
        if p < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def equity_curve(pnls: list[float], start: float = 0.0) -> list[float]:
    eq = [start]
    for p in pnls:
        eq.append(eq[-1] + p)
    return eq


def path_would_be_ruined(pnls: list[float], starting_capital: float) -> bool:
    """Return True if cumulative equity at any point drops below 0 starting from starting_capital."""
    eq = starting_capital
    for p in pnls:
        eq += p
        if eq <= 0:
            return True
    return False


def pct(rank: float, sorted_vals: list[float]) -> float:
    n = len(sorted_vals)
    return sorted_vals[max(0, min(n - 1, int(rank * n)))]


def main() -> None:
    pnls = load_pnls()
    n = len(pnls)
    total = sum(pnls)
    mean = total / n
    print(f"Loaded {n} Path Z trades. Total P&L = ${total:+,.0f}, mean = ${mean:+,.2f}\n")

    # === Actual historical sequence ===
    hist_eq = equity_curve(pnls)
    hist_dd = max_drawdown(hist_eq)
    hist_streak = longest_losing_streak(pnls)
    print("=== Actual historical sequence ===")
    print(f"  Max drawdown:            ${hist_dd:>+9,.0f}")
    print(f"  Longest losing streak:   {hist_streak} trades")
    print(f"  Terminal equity:         ${hist_eq[-1]:>+9,.0f}")

    # Historical ruin check
    print(f"\n  Historical ruin (starting from ...):")
    for cap in STARTING_CAPITAL:
        ruined = path_would_be_ruined(pnls, cap)
        print(f"    ${cap:>7,}: {'RUINED' if ruined else 'survived'}")

    # === Monte Carlo permutation ===
    print(f"\n=== Monte Carlo: {N_BOOT} permutations of trade order ===")
    rng = random.Random(42)
    terminals = []
    max_dds = []
    streaks = []
    ruin_counts = {cap: 0 for cap in STARTING_CAPITAL}

    for _ in range(N_BOOT):
        perm = pnls[:]  # copy
        rng.shuffle(perm)
        eq = equity_curve(perm)
        terminals.append(eq[-1])
        max_dds.append(max_drawdown(eq))
        streaks.append(longest_losing_streak(perm))
        for cap in STARTING_CAPITAL:
            if path_would_be_ruined(perm, cap):
                ruin_counts[cap] += 1

    terminals.sort()
    max_dds.sort()
    streaks.sort()

    print(f"\n  Terminal equity distribution:")
    print(f"    5%ile:   ${pct(0.05, terminals):>+9,.0f}")
    print(f"    25%ile:  ${pct(0.25, terminals):>+9,.0f}")
    print(f"    50%ile:  ${pct(0.50, terminals):>+9,.0f}")
    print(f"    75%ile:  ${pct(0.75, terminals):>+9,.0f}")
    print(f"    95%ile:  ${pct(0.95, terminals):>+9,.0f}")
    prob_positive = sum(1 for t in terminals if t > 0) / N_BOOT
    print(f"    P(terminal > 0):  {100*prob_positive:.1f}%")

    print(f"\n  Max drawdown distribution:")
    print(f"    5%ile (best):    ${pct(0.05, max_dds):>+9,.0f}")
    print(f"    25%ile:          ${pct(0.25, max_dds):>+9,.0f}")
    print(f"    50%ile (median): ${pct(0.50, max_dds):>+9,.0f}")
    print(f"    75%ile:          ${pct(0.75, max_dds):>+9,.0f}")
    print(f"    95%ile (worst):  ${pct(0.95, max_dds):>+9,.0f}")

    print(f"\n  Longest losing streak distribution:")
    print(f"    5%ile:  {pct(0.05, [float(s) for s in streaks]):.0f} trades")
    print(f"    50%ile: {pct(0.50, [float(s) for s in streaks]):.0f} trades")
    print(f"    95%ile: {pct(0.95, [float(s) for s in streaks]):.0f} trades")
    print(f"    max:    {max(streaks)} trades")

    print(f"\n  Probability of ruin (starting from ...):")
    for cap in STARTING_CAPITAL:
        p = ruin_counts[cap] / N_BOOT
        print(f"    ${cap:>7,}: {100*p:>5.1f}%")

    # NOTE: terminal equity is order-invariant — permutation preserves it by
    # construction. Above is a sequence-only analysis (drawdown/streak). The
    # "does edge exist" question is answered by BOOTSTRAP-WITH-REPLACEMENT below.

    # === Bootstrap resampling (WITH replacement) — tests sampling risk ===
    print(f"\n=== Bootstrap: {N_BOOT} resamples WITH replacement (n={n} each) ===")
    boot_terminals = []
    boot_max_dds = []
    boot_means = []
    boot_ruin = {cap: 0 for cap in STARTING_CAPITAL}

    for _ in range(N_BOOT):
        sample = [pnls[rng.randrange(n)] for _ in range(n)]
        eq = equity_curve(sample)
        boot_terminals.append(eq[-1])
        boot_max_dds.append(max_drawdown(eq))
        boot_means.append(sum(sample) / n)
        for cap in STARTING_CAPITAL:
            if path_would_be_ruined(sample, cap):
                boot_ruin[cap] += 1

    boot_terminals.sort()
    boot_max_dds.sort()
    boot_means.sort()

    prob_positive = sum(1 for t in boot_terminals if t > 0) / N_BOOT
    print(f"\n  Terminal equity distribution:")
    print(f"    5%ile:   ${pct(0.05, boot_terminals):>+9,.0f}")
    print(f"    25%ile:  ${pct(0.25, boot_terminals):>+9,.0f}")
    print(f"    50%ile:  ${pct(0.50, boot_terminals):>+9,.0f}")
    print(f"    75%ile:  ${pct(0.75, boot_terminals):>+9,.0f}")
    print(f"    95%ile:  ${pct(0.95, boot_terminals):>+9,.0f}")
    print(f"    P(terminal > 0):  {100*prob_positive:.1f}%  (MEANINGFUL - real edge test)")

    print(f"\n  Mean per trade distribution (95% CI):")
    print(f"    [${pct(0.025, boot_means):+,.0f}, ${pct(0.975, boot_means):+,.0f}]")

    print(f"\n  Max DD distribution (with resample noise):")
    print(f"    5%ile (best):    ${pct(0.05, boot_max_dds):>+9,.0f}")
    print(f"    50%ile (median): ${pct(0.50, boot_max_dds):>+9,.0f}")
    print(f"    95%ile (worst):  ${pct(0.95, boot_max_dds):>+9,.0f}")

    print(f"\n  Ruin probability (starting from ..., BOOTSTRAP samples):")
    for cap in STARTING_CAPITAL:
        p = boot_ruin[cap] / N_BOOT
        print(f"    ${cap:>7,}: {100*p:>5.1f}%")

    # === Interpretation ===
    print(f"\n=== Interpretation ===")
    print(f"  Historical sequence: max DD -${abs(hist_dd):,.0f} ({100*abs(hist_dd)/hist_eq[-1]:.0f}% of terminal equity)")
    print(f"  Bootstrap P(terminal > 0): {100*prob_positive:.1f}%")
    if prob_positive > 0.95:
        print(f"  =>Edge highly likely to survive resampling")
    elif prob_positive > 0.80:
        print(f"  =>Moderate confidence edge is real; noticeable tail risk")
    elif prob_positive > 0.60:
        print(f"  =>Weak edge, high sample-size dependence")
    else:
        print(f"  =>No reliable edge under sampling variance")


if __name__ == "__main__":
    main()
