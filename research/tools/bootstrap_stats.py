"""Bootstrap CI + Bonferroni-corrected p-values for signal edge testing.

Adapted from Janus's bluechipsignal perf_bootstrap.py (2026-07-31).
Pure Python stdlib, no numpy dependency. Works on any list of trade
returns from any asset.

Why bootstrap instead of t-distribution CI:
- t-distribution CI assumes IID returns plus approximate normality.
  Neither holds for trade returns (heavy tails, sampling clustering).
- Bootstrap makes no distributional assumption. Right tool for small
  samples with fat tails.

Why Bonferroni correction:
- When you test N signals and pick the best, "the best of N random
  outputs" has an inflated apparent significance.
- Bonferroni correction (multiply p-value by N tests) is the simplest
  defense against that data-mining bias.
- Use `p_adjusted` when judging "is this signal actually predictive
  after accounting for the fact I tested several candidates."

Reasonable defaults:
- n_resamples: 10000 (statistically stable, still fast for n<10k trades)
- alpha: 0.05 (standard 95% CI)
- seed: 42 (reproducibility)
"""
from __future__ import annotations
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BootstrapResult:
    """Per-signal bootstrap output.

    p_raw is the uncorrected p-value against H0: mean = 0.
    p_adjusted is the Bonferroni-corrected p-value.
    verdict is a text label such as 'positive', 'negative', 'indist'.
    """
    label: str
    n: int
    mean: float
    ci_low: float
    ci_high: float
    p_raw: float
    p_adjusted: float
    verdict: str


def bootstrap_ci(
    returns: list[float],
    *,
    n_resamples: int = 10000,
    alpha: float = 0.05,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Percentile-bootstrap CI for the mean of a return series.

    Returns (mean, ci_low, ci_high) at (1 - alpha) * 100% confidence.

    Bootstrap discipline: resample WITH REPLACEMENT n_resamples times,
    compute the mean of each resample, take the alpha/2 and 1-alpha/2
    percentiles of the bootstrap distribution as CI bounds.

    Edge cases:
        n=0: returns (0.0, 0.0, 0.0)
        n=1: returns (value, value, value), no uncertainty quantification
    """
    n = len(returns)
    if n == 0:
        return 0.0, 0.0, 0.0
    if n == 1:
        v = float(returns[0])
        return v, v, v
    mean = sum(returns) / n
    rng = random.Random(seed)
    boot_means: list[float] = []
    for _ in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += returns[rng.randrange(n)]
        boot_means.append(s / n)
    boot_means.sort()
    lo_idx = max(0, int(alpha / 2 * n_resamples))
    hi_idx = min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))
    return mean, boot_means[lo_idx], boot_means[hi_idx]


def bootstrap_p_value(
    returns: list[float],
    *,
    n_resamples: int = 10000,
    seed: int = 42,
) -> float:
    """Two-sided bootstrap p-value against H0: mean = 0.

    Method: center the returns on zero (subtract observed mean),
    bootstrap the centered sample n_resamples times, count fraction
    of resample means with absolute value >= observed absolute mean.
    """
    n = len(returns)
    if n == 0:
        return 1.0
    observed_mean = sum(returns) / n
    if observed_mean == 0.0:
        return 1.0
    centered = [r - observed_mean for r in returns]
    rng = random.Random(seed)
    extreme_count = 0
    obs_abs = abs(observed_mean)
    for _ in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += centered[rng.randrange(n)]
        if abs(s / n) >= obs_abs:
            extreme_count += 1
    return extreme_count / n_resamples


def evaluate_signal(
    label: str,
    returns: list[float],
    *,
    n_hypotheses_in_batch: int = 1,
    alpha: float = 0.05,
    ci_lower_threshold: float = 0.0,
) -> BootstrapResult:
    """One-shot signal evaluation with CI, p-value, Bonferroni correction, verdict.

    n_hypotheses_in_batch: how many signals were tested in the same run
    (used for Bonferroni correction). If you tested 3 candidate signals
    and want to judge each, pass n_hypotheses_in_batch=3.

    ci_lower_threshold: verdict is 'positive' if ci_low >= this value.
    Default 0.0 = "CI clears zero". Pass 0.005 for the 0.5% ship
    threshold (assuming returns are in per-trade fraction units).

    Verdicts:
        'positive'  : ci_low >= ci_lower_threshold AND p_adjusted < alpha
        'negative'  : ci_high <= -ci_lower_threshold AND p_adjusted < alpha
        'indist'    : otherwise
    """
    if not returns:
        return BootstrapResult(
            label=label, n=0, mean=0.0, ci_low=0.0, ci_high=0.0,
            p_raw=1.0, p_adjusted=1.0, verdict="empty",
        )
    n = len(returns)
    mean, ci_low, ci_high = bootstrap_ci(returns, alpha=alpha)
    p_raw = bootstrap_p_value(returns)
    p_adjusted = min(1.0, p_raw * n_hypotheses_in_batch)
    if ci_low >= ci_lower_threshold and p_adjusted < alpha:
        verdict = "positive"
    elif ci_high <= -ci_lower_threshold and p_adjusted < alpha:
        verdict = "negative"
    else:
        verdict = "indist"
    return BootstrapResult(
        label=label, n=n, mean=mean, ci_low=ci_low, ci_high=ci_high,
        p_raw=p_raw, p_adjusted=p_adjusted, verdict=verdict,
    )
