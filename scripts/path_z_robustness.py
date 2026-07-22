"""Path Z robustness — temporal + subsample stability of the n=85 in-sample.

Given 4 rejections around Path Z in the 2026-07-22 session (multi-market,
partial-take, FX fade, Meyers HR-ORB), stress-test whether the n=85
in-sample edge is temporally concentrated or evenly distributed.

Splits tested:
  A. Per year: 2024 vs 2025 vs 2026 partial
  B. First half vs second half by trade count
  C. Rolling window (25-trade window)
  D. Halving-random-half stability (bootstrap variance of two halves)

If the +$461/trade in-sample edge is real, it should show up across most
temporal splits. If it's concentrated in one window, the 35-month forward
timeline becomes very risky.
"""
from __future__ import annotations

import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH_Z_LOG = ROOT / "data" / "shadow_equity_path_z.jsonl"


def load_trades() -> list[dict]:
    with open(PATH_Z_LOG) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def summarize(label: str, pnls: list[float]) -> None:
    n = len(pnls)
    if n == 0:
        print(f"  {label:<28s}  NO TRADES")
        return
    total = sum(pnls)
    mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    med = statistics.median(pnls)
    if n > 1:
        stdev = statistics.stdev(pnls)
        se = stdev / (n ** 0.5)
    else:
        stdev = 0.0; se = 0.0
    print(f"  {label:<28s}  n={n:>3d}  "
          f"total=${total:>+9,.0f}  mean=${mean:>+7,.2f}  "
          f"WR={100*wins/n:>4.1f}%  med=${med:>+6,.0f}  "
          f"SE=${se:>6,.0f}")


def bootstrap_ci(pnls: list[float], n_boot: int = 5000, seed: int = 42) -> tuple[float, float]:
    rng = random.Random(seed)
    means = []
    n = len(pnls)
    for _ in range(n_boot):
        s = [pnls[rng.randrange(n)] for _ in range(n)]
        means.append(sum(s) / n)
    means.sort()
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]


def main() -> None:
    trades = load_trades()
    trades.sort(key=lambda t: t["or_open_utc"])
    pnls = [float(t["outcome"]["net_pnl"]) for t in trades]
    dates = [t["or_open_utc"][:10] for t in trades]
    print(f"Loaded {len(trades)} Path Z in-sample trades from "
          f"{dates[0]} to {dates[-1]}\n")

    # Full sample baseline
    print("=== Full sample ===")
    summarize("all trades", pnls)
    lo, hi = bootstrap_ci(pnls)
    print(f"    bootstrap 95% CI on mean: [${lo:+,.0f}, ${hi:+,.0f}]")

    # A. Per year
    print("\n=== Split A: per calendar year ===")
    from collections import defaultdict
    by_year: dict[str, list[float]] = defaultdict(list)
    for p, d in zip(pnls, dates):
        year = d[:4]
        by_year[year].append(p)
    for year in sorted(by_year):
        summarize(f"year {year}", by_year[year])

    # B. First half vs second half by trade count
    print("\n=== Split B: first half vs second half (by trade sequence) ===")
    half = len(pnls) // 2
    summarize(f"first  {half} trades", pnls[:half])
    summarize(f"second {len(pnls)-half} trades", pnls[half:])

    # C. Rolling 25-trade window mean
    print("\n=== Split C: rolling 25-trade window mean ===")
    W = 25
    print(f"  {'window ending trade #':<28s} {'date':<12s} {'mean/trade':<12s}")
    for i in range(W - 1, len(pnls)):
        w_pnls = pnls[i - W + 1: i + 1]
        m = sum(w_pnls) / W
        # Only print every 10 windows to keep output brief
        if (i - W + 1) % 10 == 0 or i == len(pnls) - 1:
            print(f"  window ending #{i+1:>3d}          "
                  f"{dates[i]:<12s} ${m:+7,.0f}")
    # Also report min/max of rolling mean
    rolling_means = [sum(pnls[i - W + 1: i + 1]) / W for i in range(W - 1, len(pnls))]
    print(f"  Rolling {W}-trade mean range: min=${min(rolling_means):+,.0f}  "
          f"max=${max(rolling_means):+,.0f}")

    # D. Random-split stability: 100 random 50/50 splits, report mean of each half
    print("\n=== Split D: 100 random 50/50 splits (stability check) ===")
    rng = random.Random(1)
    diffs = []
    for _ in range(100):
        idx = list(range(len(pnls)))
        rng.shuffle(idx)
        h = len(idx) // 2
        m1 = sum(pnls[i] for i in idx[:h]) / h
        m2 = sum(pnls[i] for i in idx[h:]) / (len(idx) - h)
        diffs.append(m1 - m2)
    print(f"  Mean absolute half-split diff: ${statistics.mean(abs(d) for d in diffs):+,.0f}")
    print(f"  Max abs diff (any split):      ${max(abs(d) for d in diffs):+,.0f}")

    # E. Contribution: what fraction of P&L comes from top-k trades?
    print("\n=== Split E: contribution concentration ===")
    total = sum(pnls)
    sorted_desc = sorted(pnls, reverse=True)
    for k in [1, 3, 5, 10, 20]:
        top_k_pnl = sum(sorted_desc[:k])
        print(f"  Top {k:>2d} trades:  ${top_k_pnl:>+9,.0f}  "
              f"({100*top_k_pnl/total:>5.1f}% of total)")


if __name__ == "__main__":
    main()
