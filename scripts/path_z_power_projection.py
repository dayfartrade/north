"""Statistical power projection for Path Z forward accumulation.

Question: given Path Z's in-sample profile (n=85, mean=+$462, std ~= $1442
per trade, expected rate ~2 trades/week), how many months until we can
statistically accept or reject the strategy at 95% confidence?

Methodology:
  - Assume in-sample mean + std hold in forward data
  - Compute standard error of mean at various n: SE = std/sqrt(n)
  - 95% CI half-width = 1.96 * SE
  - We can "detect" a true mean of $X vs $0 when 1.96*SE < X

Also does adverse-case projection: if true mean is only HALF the in-sample
mean, how long does it take to still detect?
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PATH_Z_LOG = ROOT / "data" / "shadow_equity_path_z.jsonl"


def load_pnls() -> list[float]:
    rows = []
    with open(PATH_Z_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            outcome = r.get("outcome", {})
            if outcome.get("net_pnl") is not None:
                rows.append(float(outcome["net_pnl"]))
    return rows


def main() -> None:
    pnls = load_pnls()
    n_sample = len(pnls)
    mean_sample = float(np.mean(pnls))
    std_sample = float(np.std(pnls, ddof=1))
    win_rate = sum(1 for p in pnls if p > 0) / n_sample

    print(f"=== Path Z in-sample profile ===")
    print(f"n_sample:    {n_sample}")
    print(f"mean:        ${mean_sample:+,.2f}/trade")
    print(f"std:         ${std_sample:+,.2f}")
    print(f"win_rate:    {100*win_rate:.1f}%")
    print(f"Sharpe/trade: {mean_sample/std_sample:+.3f}")
    print()

    # 2.5 years in-sample, n=85 --> ~34 trades/year --> ~2.8 trades/month
    years_in_sample = 2.5
    rate_per_year = n_sample / years_in_sample
    rate_per_month = rate_per_year / 12
    rate_per_week = rate_per_year / 52
    print(f"=== Rate estimates ===")
    print(f"trades/year:  {rate_per_year:.1f}")
    print(f"trades/month: {rate_per_month:.2f}")
    print(f"trades/week:  {rate_per_week:.2f}")
    print()

    # SE and CI at various forward n
    print(f"=== Confidence interval width by forward n (95% CI, in-sample std=${std_sample:,.0f}) ===")
    print(f"  {'n':>4s}  {'~months':>8s}  {'SE':>10s}  {'95% CI half':>13s}  {'Cleared at true mean:':>22s}")
    for n in [10, 20, 30, 50, 75, 100, 150, 200, 300]:
        se = std_sample / math.sqrt(n)
        half = 1.96 * se
        months = n / rate_per_month
        # At what true mean would CI just clear zero?
        # true_mean - 1.96*SE > 0 => true_mean > 1.96*SE = half
        print(f"  {n:>4d}  {months:>8.1f}  ${se:>+9,.0f}  ${half:>+12,.0f}  ${half:>+,.0f}")

    print()
    print("Interpretation: to statistically confirm mean > 0 at 95% confidence,")
    print("the observed mean at forward n must exceed the 'CI half' value.")
    print(f"In-sample mean was ${mean_sample:+,.0f}. If forward keeps that:")
    print()
    for n in [30, 50, 75, 100, 150]:
        se = std_sample / math.sqrt(n)
        half = 1.96 * se
        months = n / rate_per_month
        detectable = half < mean_sample
        print(f"  n={n:>3d}  ({months:>4.1f} mo)  CI half=${half:>+7,.0f}  "
              f"--> {'DETECTABLE' if detectable else 'NOT yet detectable'}")

    print()
    print("Adverse case — if true forward mean is HALF the in-sample:")
    reduced_mean = mean_sample / 2
    print(f"  true_mean = ${reduced_mean:+,.0f}/trade")
    for n in [50, 100, 200, 500]:
        se = std_sample / math.sqrt(n)
        half = 1.96 * se
        months = n / rate_per_month
        detectable = half < reduced_mean
        print(f"  n={n:>4d}  ({months:>5.1f} mo)  CI half=${half:>+7,.0f}  "
              f"--> {'DETECTABLE' if detectable else 'NOT yet detectable'}")

    print()
    print("Worst case — if true forward mean is ZERO (null true):")
    print(f"  We won't ever 'reject as zero' — we can only fail to reject.")
    print(f"  Reject-null gate triggers when observed mean < 0 with CI < 0.")
    print()
    for n in [30, 50, 100]:
        se = std_sample / math.sqrt(n)
        half = 1.96 * se
        months = n / rate_per_month
        p_null_pass = 1 - _normal_cdf(half / std_sample * math.sqrt(n))
        print(f"  n={n:>3d}  ({months:>4.1f} mo)  P(false-positive at true=0) = {p_null_pass*2:.1%}")


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


if __name__ == "__main__":
    main()
