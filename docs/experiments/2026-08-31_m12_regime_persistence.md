# M12 regime-persistence audit

**Date:** 2026-08-31
**Author:** Knox
**Status:** Analytical follow-up. Extends the M12 regime-split ensemble analysis.
**Trigger:** Follow-up #2 from `2026-08-31_m12_regime_split_ensemble.md` - how often does M12 flip, and what's the base rate for a flip in the next 26 weeks?

## Method

`scripts/m12_regime_persistence.py`. Compute sign of trailing 252-day gold return (M12) per weekday from 2010-01-01 through 2026-07-20 (local Dukascopy). Group consecutive same-sign days into streaks. Report length distribution.

## Results

### M12 LONG streaks

- n = 51 streaks
- Total LONG days: 2,559 (about 63% of the sample)
- Median streak length: **3 days**
- Mean: 50.2 days (heavily right-skewed)
- p25 / p50 / p75 / p90: 1 / 3 / 12 / 64 days
- Top 5 longest:

| length (days) | start | end |
|---|---|---|
| **868** | 2023-03-17 | 2026-07-20 (OPEN) |
| 531 | 2019-05-31 | 2021-06-17 |
| 397 | 2010-12-21 | 2012-06-27 |
| 245 | 2016-02-17 | 2017-01-25 |
| 182 | 2017-10-27 | 2018-07-10 |

### M12 SHORT streaks

- n = 50 streaks
- Total SHORT days: 1,486 (about 37% of the sample)
- Median streak length: **6 days**
- Mean: 29.7 days
- p25 / p50 / p75 / p90: 1 / 6 / 22 / 80 days
- Top 5 longest:

| length (days) | start | end |
|---|---|---|
| 369 | 2013-01-11 | 2014-06-16 |
| 189 | 2015-01-29 | 2015-10-21 |
| 145 | 2018-07-11 | 2019-01-29 |
| 94 | 2014-07-30 | 2014-12-08 |
| 91 | 2021-07-09 | 2021-11-12 |

## Two things that jump out

**1. The distribution is bimodal, not smooth.** Median LONG streak is 3 days, median SHORT streak is 6 days - most sign flips are single-day whipsaws around a level. But a small number of streaks last 100+ days, and those account for almost all the total time-in-regime. Right-skew: most streaks are noise; a few are structural regimes.

**2. The current LONG streak is unprecedented.** 868 days as of 2026-07-20 (still open). Longer than any prior LONG streak in the 16-year sample by 337 days. The prior maximum was 531 days (2019-05-31 to 2021-06-17, the COVID-era gold rally).

## Base rate for a flip in the next 26 weeks

There is no comparable prior streak. Every LONG streak in the sample was shorter than the current one. This means any base-rate estimate from historical distribution is extrapolation.

What we CAN say:
- Every prior streak eventually flipped. The current one will too, eventually.
- The prior longest streak (531 days) took a 2011-2013 gold peak-and-crash to break.
- Gold's structural setup (real yields, dollar, central bank buying) would need to shift materially for the current M12 to flip SHORT within 26 weeks. Currently no sign of that.

Rough qualitative estimate: **less than 20% probability of an M12 flip in the pre-reg forward window (through 2027-01-22).** Not zero, but this is a single regime being sampled.

## Implications for the ensemble

Combining this with the regime-split analysis (`2026-08-31_m12_regime_split_ensemble.md`):

1. Ensemble adds value over v1 only in M12 SHORT regime. The current LONG regime shows no ensemble edge.
2. The 26-week pre-reg forward window is almost certainly going to stay entirely in M12 LONG. Ensemble's shadow performance during that window will look nearly identical to v1's live performance.
3. When the ensemble shadow window closes in early 2027, the numbers will be measuring "ensemble in a persistent LONG regime" - which the backtest already showed is indistinguishable from v1.
4. To meaningfully test the ensemble's SHORT-regime edge live, we'd need a gold bear cycle. Those happen once every 4-6 years based on this sample; the last one ended 2015.

**Practical:** treat the ensemble's pre-reg forward window as measuring how well the ensemble tracks v1 (a smoke test), not whether the ensemble is a better product than v1 (untestable in the current regime).

## Implications for v2

The regime-split analysis showed v2 wins in BOTH regimes. So the current LONG regime is fully informative for v2's forward test: any edge v2 shows over v1 in the shadow window is representative, not regime-conditional.

**v2 shadow window remains a real test.** Ensemble shadow window is not.

## Follow-ups (queued, not urgent)

1. Regime-transition analysis: what typically triggers an M12 flip? Any leading indicators from macro (real yields cracking, dollar strengthening, TLT rally) that would give early warning?
2. Look at M12 flip frequency vs gold volatility regime. Are chop years (like 2021-2022 with 24 flips in 12 months) predictable?
3. Consider a "regime-conditional" variant where the aggregator weights v2 heavier during M12-persistent regimes and equal-weights during M12-choppy regimes. Would need its own pre-reg.

## Files touched

- Script: `scripts/m12_regime_persistence.py` (new)
- Doc: `docs/experiments/2026-08-31_m12_regime_persistence.md` (this file)
