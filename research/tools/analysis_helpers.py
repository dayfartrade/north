"""Shared pure helpers for signal analysis and backtest post-processing.

Adapted from Janus's bluechipsignal analysis_helpers.py (2026-07-31).
Pure functions, no I/O, no exchange-specific state. Defensive by design:
callers pass raw values; bad inputs degrade gracefully rather than raise.

Do NOT add I/O dependencies here. This module is for pure math and
categorization utilities used across backtest and reporting code.
"""
from __future__ import annotations


def entry_slippage_bps(
    side: str | None,
    intended: float | None,
    actual: float | None,
) -> float | None:
    """Signed basis points of adverse entry slippage.

    Positive = adverse (worse fill than intended).
    Negative = favorable (better fill than intended).

    For SHORT: adverse means actual < intended (sold cheaper).
    For LONG: adverse means actual > intended (bought pricier).

    Returns None when inputs are incomplete or intended <= 0.
    """
    if not intended or not actual or side not in ("long", "short"):
        return None
    if intended <= 0:
        return None
    if side == "short":
        return -(actual - intended) / intended * 10_000.0
    return (actual - intended) / intended * 10_000.0


def session_bucket(hour_utc: int) -> str:
    """4-bucket UTC session tag for per-session analytics.

    Boundaries inclusive-left:
        [0, 6):   asia
        [6, 12):  eu_am
        [12, 18): us_am
        [18, 24): us_pm

    Useful for identifying which trading session produced a signal or
    trade outcome. Same convention across gold, silver, crypto.
    """
    if 0 <= hour_utc < 6:
        return "asia"
    if 6 <= hour_utc < 12:
        return "eu_am"
    if 12 <= hour_utc < 18:
        return "us_am"
    return "us_pm"


def percentile(sorted_values: list[float], p: float) -> float:
    """Linear-interpolation percentile on a pre-sorted list.

    Arguments:
        sorted_values: list already sorted ascending
        p: percentile as a fraction in [0.0, 1.0]

    Returns:
        The interpolated percentile value.

    Edge cases:
        Empty list returns 0.0 (caller decides interpretation)
        Singleton returns its own value regardless of p

    Matches numpy.percentile with method='linear'. Inlined here to
    avoid numpy dependency in code that runs during signal generation.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def rolling_z_score(
    series: list[float],
    lookback: int,
) -> list[float | None]:
    """Rolling z-score of a value series.

    For each index i, computes (series[i] - mean(series[i-lookback+1:i+1]))
    divided by stdev of the same window. Returns None for indices with
    insufficient history.

    Useful for extreme-detection signals such as gold-silver ratio
    z-score, funding rate z-score, or any percentile-adjacent measure.
    """
    if lookback <= 1:
        raise ValueError("lookback must be > 1 for z-score computation")
    n = len(series)
    if n == 0:
        return []
    result: list[float | None] = []
    for i in range(n):
        if i + 1 < lookback:
            result.append(None)
            continue
        window = series[i + 1 - lookback : i + 1]
        m = sum(window) / lookback
        var = sum((x - m) ** 2 for x in window) / lookback
        if var <= 0:
            result.append(None)
            continue
        stdev = var ** 0.5
        result.append((series[i] - m) / stdev)
    return result


def bollinger_bands(
    series: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Bollinger Bands (upper, middle, lower).

    Middle = simple moving average over `period`.
    Upper = middle + num_std * rolling stdev.
    Lower = middle - num_std * rolling stdev.

    Returns three parallel lists, each with None for indices with
    insufficient history.

    Standard parameters (period=20, num_std=2.0) are typical for daily
    or 4H charts. Adjust for other timeframes.
    """
    if period < 2:
        raise ValueError("period must be >= 2 for Bollinger Bands")
    n = len(series)
    upper: list[float | None] = []
    middle: list[float | None] = []
    lower: list[float | None] = []
    for i in range(n):
        if i + 1 < period:
            upper.append(None)
            middle.append(None)
            lower.append(None)
            continue
        window = series[i + 1 - period : i + 1]
        mid = sum(window) / period
        var = sum((x - mid) ** 2 for x in window) / period
        stdev = var ** 0.5
        middle.append(mid)
        upper.append(mid + num_std * stdev)
        lower.append(mid - num_std * stdev)
    return upper, middle, lower
