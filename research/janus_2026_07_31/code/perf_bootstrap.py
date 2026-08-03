"""Bootstrap statistics for per-specialist edge testing.

Pure helpers — no DB, no I/O. Lives in src/ so tests can import without
psycopg. The companion `scripts/specialist_edge_test.py` does the DB
load and calls into these functions.

Why bootstrap instead of the analytical CI in perf_report.py:
  - The t-distribution CI assumes IID returns + approximate normality.
    Neither holds for trade returns (heavy tails, sampling clustering).
  - Bootstrap makes no distributional assumption. It's the right tool for
    small samples and fat tails. See Aronson EBTA Ch 4-6 + LdP AFML Ch 7.
  - Per-specialist multiple-testing correction (Bonferroni-adjusted
    p-values) catches the data-mining bias when we look at "the best of
    N specialists." See Aronson Ch 6.

The functions are intentionally simple; no numpy dependency, just stdlib.
Speed is fine for our scale (n <= 10000 setups, 4-10 specialists).
"""
from __future__ import annotations
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BootstrapResult:
    """Per-rule bootstrap output.

    p_raw is the uncorrected p-value (H0: mean = 0).
    p_adjusted is the Bonferroni-corrected p-value (multiply by n_rules).
    Use p_adjusted when judging "is this specialist actually predictive
    after accounting for the fact we tested several specialists."
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
    """Percentile-bootstrap CI for the mean.

    Returns (mean, ci_low, ci_high) at (1 - alpha) * 100% confidence.
    For n=0 returns zeros; for n=1 returns the single value as point
    estimate AND CI bounds (no uncertainty quantification possible).

    Bootstrap discipline: resample WITH REPLACEMENT n_resamples times,
    compute the mean of each resample, take the alpha/2 and 1-alpha/2
    percentiles of the bootstrap distribution as the CI.
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
    """Two-sided bootstrap p-value for H0: population mean = 0.

    Method: center the observed returns to enforce H0 (mean = 0), then
    resample with replacement n_resamples times. p = fraction of
    bootstrap means as extreme as the observed mean. Add-one smoothing
    in the standard way so p > 0.

    Returns 1.0 when n < 2 (cannot test).
    """
    n = len(returns)
    if n < 2:
        return 1.0
    observed = sum(returns) / n
    abs_observed = abs(observed)
    centered = [r - observed for r in returns]
    rng = random.Random(seed)
    count_extreme = 0
    for _ in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += centered[rng.randrange(n)]
        m = s / n
        if abs(m) >= abs_observed:
            count_extreme += 1
    return (count_extreme + 1) / (n_resamples + 1)


def bootstrap_p_value_one_sided(
    returns: list[float],
    *,
    direction: str = "positive",
    n_resamples: int = 10000,
    seed: int = 42,
) -> float:
    """One-sided bootstrap p-value for H0: population mean = 0.

    Per Aronson EBTA Ch 5-6, TA rule testing is inherently directional
    (H1: rule mean > 0, not "different from 0"). The one-sided variant
    is the correct alignment for our ship / kill decisions, which are
    always directional.

    direction:
      "positive" — H1: mean > 0; p = fraction of resampled means ≥ observed
      "negative" — H1: mean < 0; p = fraction of resampled means ≤ observed

    Zero-centered under H0 per Aronson's methodology. Add-one smoothing.

    Returns 1.0 when n < 2 (cannot test).
    """
    n = len(returns)
    if n < 2:
        return 1.0
    if direction not in ("positive", "negative"):
        raise ValueError(f"direction must be 'positive' or 'negative', got {direction!r}")
    observed = sum(returns) / n
    centered = [r - observed for r in returns]
    rng = random.Random(seed)
    count_extreme = 0
    for _ in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += centered[rng.randrange(n)]
        m = s / n
        if direction == "positive":
            if m >= observed:
                count_extreme += 1
        else:
            if m <= observed:
                count_extreme += 1
    return (count_extreme + 1) / (n_resamples + 1)


def _verdict(mean: float, ci_low: float, ci_high: float, p_adj: float, n: int, min_n: int = 5) -> str:
    """Translate the (mean, CI, adjusted-p, n) tuple into a label.

    Verdict thresholds:
      - n < min_n               -> INSUFFICIENT
      - p_adjusted < 0.05 + ci entirely above zero -> EDGE (corrected)
      - ci_low > 0 (raw)        -> POSITIVE (raw — needs multiple-testing caveat)
      - ci_high < 0 (raw)       -> NEGATIVE (raw — same caveat)
      - otherwise               -> INDISTINGUISHABLE
    """
    if n < min_n:
        return f"INSUFFICIENT (n={n} < {min_n})"
    if p_adj < 0.05 and ci_low > 0:
        return "POSITIVE EDGE (multiple-testing-corrected)"
    if ci_low > 0:
        return "POSITIVE (raw — flagged by multiple testing)"
    if ci_high < 0:
        return "NEGATIVE (raw — flagged by multiple testing)"
    return "INDISTINGUISHABLE FROM ZERO"


def specialist_edge_test(
    returns_by_specialist: dict[str, list[float]],
    *,
    n_resamples: int = 10000,
    alpha: float = 0.05,
    min_n: int = 5,
    seed: int = 42,
) -> list[BootstrapResult]:
    """Test each specialist's edge with bootstrap CI + Bonferroni-adjusted
    p-value across the family of specialists tested.

    Bonferroni correction: count specialists with n >= min_n (we only
    test those), multiply each one's raw p by the count. Conservative
    but defensible — White's Reality Check would be the next step if we
    had aligned trade timestamps across specialists.

    Returns a list sorted by adjusted p-value ascending (most-significant
    first).
    """
    testable = [
        name for name, rs in returns_by_specialist.items() if len(rs) >= min_n
    ]
    n_tests = max(1, len(testable))
    out: list[BootstrapResult] = []
    for name, rs in returns_by_specialist.items():
        n = len(rs)
        if n == 0:
            out.append(BootstrapResult(
                label=name, n=0, mean=0.0, ci_low=0.0, ci_high=0.0,
                p_raw=1.0, p_adjusted=1.0, verdict="INSUFFICIENT (n=0)",
            ))
            continue
        mean, ci_low, ci_high = bootstrap_ci(
            rs, n_resamples=n_resamples, alpha=alpha, seed=seed,
        )
        p_raw = bootstrap_p_value(rs, n_resamples=n_resamples, seed=seed)
        p_adj = min(1.0, p_raw * n_tests) if n >= min_n else 1.0
        verdict = _verdict(mean, ci_low, ci_high, p_adj, n, min_n=min_n)
        out.append(BootstrapResult(
            label=name, n=n, mean=mean,
            ci_low=ci_low, ci_high=ci_high,
            p_raw=p_raw, p_adjusted=p_adj,
            verdict=verdict,
        ))
    out.sort(key=lambda r: r.p_adjusted)
    return out
