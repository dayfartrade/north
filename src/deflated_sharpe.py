"""Deflated Sharpe Ratio (López de Prado, Ch 14.7.3, 2018) + Probabilistic SR.

Corrects the observed Sharpe ratio for:
  (a) non-Normal returns (skew + kurtosis)
  (b) finite sample length
  (c) MULTIPLE-TESTING SELECTION BIAS — the main reason to use DSR over PSR

Under H0: SR = 0, the expected maximum Sharpe across N independent trials is
positive due to selection bias. DSR estimates that expected-maximum-under-null
as SR* and asks: what is P(true SR > SR*) given the observed SR_hat + higher
moments + sample length T?

Rule of thumb: DSR > 0.95 means the strategy clears the 5% significance
bar AFTER accounting for how many trials were needed to find it.

This is the finance-specific version of Bonferroni / FDR that Janus flagged
in his 2026-07-07 reply on Q1 (multi-hypothesis correction).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence

import math
import numpy as np
from scipy import stats

EULER_MASCHERONI = 0.5772156649015329


@dataclass
class SRStats:
    """Everything DSR needs from a per-observation return series."""
    n_observations: int
    sr_per_period: float            # Sharpe ratio at the sampling frequency (not annualized)
    skewness: float
    kurtosis: float                 # non-excess (Gaussian = 3.0)


def sr_stats(returns: Sequence[float]) -> SRStats:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 2 or r.std(ddof=1) == 0:
        return SRStats(len(r), float("nan"), float("nan"), float("nan"))
    sr = r.mean() / r.std(ddof=1)
    # scipy skew/kurtosis default: bias-corrected skew, EXCESS kurtosis
    skew = float(stats.skew(r, bias=False))
    ex_kurt = float(stats.kurtosis(r, bias=False))
    return SRStats(len(r), float(sr), skew, ex_kurt + 3.0)


def probabilistic_sharpe(observed: SRStats, benchmark_sr: float) -> float:
    """PSR — probability that true SR > benchmark_sr, given observed sample.

    Corrects for skew, kurtosis, and sample size (finite-sample bias).
    Returns a probability in [0, 1]. Rule: PSR > 0.95 to reject SR=benchmark at 5%.
    """
    n = observed.n_observations
    if n < 2 or not math.isfinite(observed.sr_per_period):
        return float("nan")
    sr = observed.sr_per_period
    g3 = observed.skewness
    g4 = observed.kurtosis
    denom_sq = 1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * sr * sr
    if denom_sq <= 0:
        return float("nan")
    numerator = (sr - benchmark_sr) * math.sqrt(n - 1)
    z = numerator / math.sqrt(denom_sq)
    return float(stats.norm.cdf(z))


def expected_max_sr_under_null(n_trials: int, sr_variance_across_trials: float) -> float:
    """SR* — estimator of the expected maximum SR across N independent trials
    when the true SR is zero (López de Prado 14.7.3, Bailey & LdP 2014).

    SR* = sqrt(V) × ( (1 - γ) · Φ⁻¹[1 − 1/N]  +  γ · Φ⁻¹[1 − 1/(N·e)] )
    """
    if n_trials < 2 or sr_variance_across_trials <= 0:
        return 0.0
    g = EULER_MASCHERONI
    z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(sr_variance_across_trials) * ((1.0 - g) * z1 + g * z2)


def deflated_sharpe(observed: SRStats, n_trials: int,
                     sr_variance_across_trials: float) -> tuple[float, float]:
    """DSR — probability that observed SR beats the expected max SR under the
    null hypothesis, accounting for selection bias from `n_trials` trials.

    Returns (dsr, sr_star). DSR > 0.95 clears the 5% significance bar
    AFTER correcting for the number of hypotheses that were tested.
    """
    sr_star = expected_max_sr_under_null(n_trials, sr_variance_across_trials)
    dsr = probabilistic_sharpe(observed, sr_star)
    return dsr, sr_star
