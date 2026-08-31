# v2-skipped predictor probe

**Date:** 2026-08-31
**Author:** Knox
**Status:** Exploratory analysis. Not a pre-reg, not a ship candidate. Fact-finding on what distinguishes the v2-skipped losing subset.
**Trigger:** The fire-rate analysis showed the 93 v2-skipped v1 trades collectively lose money (Sharpe -0.14, cum -$8,538). DXY misalignment defines the group by construction. Question: is there a SECOND macro/technical feature that distinguishes them, which could seed a v3 candidate that layers another filter?

## Method

`scripts/v2_skipped_predictor_probe.py`. For each v1 directional trade in the 16-year backtest, capture:

- Momentum magnitudes: `abs_M20`, `abs_M60`
- Trend structure: `abs_MA_spread_pct` (10/40 MA distance as % of price)
- Volatility: `ATR_pct` (ATR20 as % of price)
- Macro: `abs_RY_chg` (magnitude of real-yield change), `RY_level` (real-yield absolute level)
- Seasonality: month of signal date

Then compare distributions between v2-confirmed and v2-skipped subsets, and within v2-skipped, between winners and losers.

## Results

**Distribution: v2-confirmed vs v2-skipped (medians)**

| feature | v2-confirmed (n=270) | v2-skipped (n=93) | median diff |
|---|---|---|---|
| `abs_M20` | 4.2% | 3.0% | **-28.6%** |
| `abs_M60` | 6.6% | 6.7% | +0.8% |
| `abs_RY_chg` | 0.14 pp | 0.13 pp | -7.1% |
| `abs_MA_spread_pct` | 2.53% | 2.09% | **-17.2%** |
| `ATR_pct` | 1.30% | 1.44% | +10.8% |
| **`RY_level`** | **0.58%** | **0.23%** | **-60.3%** |

**Within v2-skipped, winners (n=45) vs losers (n=48):**

| feature | skip winners | skip losers | win-lose diff |
|---|---|---|---|
| `abs_M20` | 3.0% | 3.1% | -5.7% |
| `abs_M60` | 5.5% | 7.5% | **-26.7%** |
| `abs_MA_spread_pct` | 1.94% | 2.45% | -20.7% |
| **`RY_level`** | **0.32%** | **0.12%** | **+166.7%** |

**Seasonality (v2-skipped rate by month):**

| month | v2-conf | v2-skip | skip% | skip WR |
|---|---|---|---|---|
| Jan | 18 | 11 | 38% | 55% |
| Feb | 22 | 8 | 27% | 50% |
| Mar | 22 | 6 | 21% | 33% |
| Apr | 17 | 5 | 23% | 0% |
| May | 26 | 8 | 24% | 50% |
| Jun | 24 | 9 | 27% | 89% |
| **Jul** | **22** | **15** | **41%** | 40% |
| **Aug** | **22** | **14** | **39%** | 71% |
| Sep | 30 | 6 | 17% | 33% |
| Oct | 19 | 2 | 10% | 0% |
| Nov | 22 | 5 | 19% | 20% |
| Dec | 26 | 4 | 13% | 50% |

## Findings

**1. Real yield LEVEL is the strongest secondary predictor.** v2-skipped trades fire when the absolute real yield level is 60% lower than v2-confirmed trades (median 0.23% vs 0.58%). Within the v2-skipped group, the losers fire at an even lower level (0.12%) vs the winners (0.32%). Economic intuition: at near-zero real yields, gold's macro tailwind is already priced in, so a signal firing without DXY confirmation is more likely to be chasing an exhausted move. Not proof, but the effect is large and consistent.

**2. M20 magnitude is a secondary distinguishing feature.** v2-skipped v1 firings happen on ~29% weaker 4-week momentum than v2-confirmed. So DXY-misaligned v1 firings tend to be the marginal ones. Same directional intuition: weaker momentum + no dollar confirmation = weaker overall setup.

**3. Trend-structure (MA spread) is a smaller but consistent factor.** v2-skipped trades happen when the 10-40 MA spread is narrower (17% narrower medians). Weaker trend structure.

**4. Seasonality: July and August are the "v2 disagrees with v1" months.** 41% and 39% skip rates respectively, vs a base rate of ~26%. Signal: gold summer trading is where v1 fires most often without DXY confirming. Small n but consistent with the general "summer chop" reputation.

**5. No strong effect from ATR level or RY_chg magnitude.** Volatility regime doesn't predict; the size of the real-yield move doesn't predict. Direction of the RY move does (that's already in v1). Absolute level of RY does (this finding).

## Seed for a v3 candidate

**Not proposing v3 today.** Just seeding the idea. A rule that would drop the WORST subset of v2-skipped trades:

```
v3 = v1 signal AND NOT (RY_level < 0.30% AND abs_M20 < 3%)
```

This would drop the "low real yield + weak momentum" subset regardless of DXY. In-sample this would be additive to v2 (already drops DXY-misaligned). But:

- The rule was designed AFTER seeing the data (data-snooping).
- A proper v3 pre-reg would need to specify the filter thresholds BEFORE re-running the backtest, then split-sample validation.
- The thresholds 0.30% RY / 3% M20 are eyeballed medians, not optimized.
- Bonferroni-N would increment for having probed multiple features (RY_level, M20, MA_spread, ATR_pct, RY_chg, seasonality = 6 features probed).

**Actionable follow-up:** if we ever design a v3 candidate, real-yield ABSOLUTE LEVEL is the strongest place to look. Not the change (already used), the level. Pre-reg would specify a fresh threshold and a fresh OOS split.

## What NOT to do

- Do not ship a v3 based on this probe. Every threshold is post-hoc.
- Do not modify v2 to include an RY_level filter. v2 is in a pre-reg shadow window; changing the rule mid-window invalidates the whole comparison.
- Do not present these findings as evidence that v1 needs modification. v1's rules were the pre-reg. This analysis is about what an ADDITIONAL filter could look like, not about what's wrong with v1.
- Do not chase the seasonality finding. n=15 in July is too small to inform a rule change; the effect could be regime-noise.

## Files touched

- Script: `scripts/v2_skipped_predictor_probe.py` (new)
- Doc: `docs/experiments/2026-08-31_v2_skipped_predictor_probe.md` (this file)
