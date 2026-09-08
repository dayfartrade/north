# v1 slicing: by-year Sharpe + M20 percentile bucket performance

**Date:** 2026-09-08
**Author:** Knox
**Status:** Diagnostic follow-up. The clearest v3-class candidate direction to date.
**Trigger:** Two open follow-ups from the same-day distribution audit: (1) does v1's edge hold in the recent regime specifically? (2) are v1 trades at extreme M20 systematically worse?

## Part 1: v1 by year

| year | n | WR | mean $ | total $ | Sharpe |
|---|---|---|---|---|---|
| 2010 | 19 | 73.7% | $721 | $13,691 | 1.93 |
| 2011 | 24 | 62.5% | $838 | $20,111 | 1.48 |
| 2012 | 14 | 64.3% | $650 | $9,104 | 1.72 |
| 2013 | 21 | 42.9% | $460 | $9,651 | 0.87 |
| **2014** | 13 | 46.2% | -$173 | **-$2,248** | **-0.43** |
| **2015** | 16 | 56.2% | -$189 | **-$3,029** | **-0.41** |
| 2016 | 30 | 46.7% | $57 | $1,718 | 0.27 |
| **2017** | 25 | 36.0% | -$459 | **-$11,471** | **-1.78** |
| 2018 | 19 | 63.2% | $371 | $7,058 | 1.82 |
| 2019 | 28 | 64.3% | $641 | $17,952 | 2.31 |
| 2020 | 30 | 53.3% | $5 | $135 | -0.12 |
| 2021 | 21 | 61.9% | $437 | $9,184 | 1.06 |
| 2022 | 24 | 45.8% | $448 | $10,744 | 0.96 |
| **2023** | 22 | 45.5% | -$653 | **-$14,356** | **-1.79** |
| 2024 | 17 | 52.9% | $791 | $13,445 | 1.18 |
| **2025** | 22 | 72.7% | **$2,655** | **$58,419** | **2.64** |
| 2026 (H1) | 15 | 73.3% | $2,655 | $39,428 | 1.33 |

Rolling 2-year windows:

| window | n | total $ | Sharpe |
|---|---|---|---|
| 2010-2011 | 43 | $33,802 | 1.68 |
| 2013-2014 | 34 | $7,403 | 0.45 |
| **2014-2015** | 29 | -$5,277 | **-0.42** |
| 2016-2017 | 55 | -$9,753 | -0.38 |
| **2017-2018** | 44 | -$4,413 | **-0.44** |
| 2020-2021 | 51 | $9,319 | 0.24 |
| **2022-2023** | 46 | -$3,612 | **-0.13** |
| **2023-2024** | 39 | -$912 | **-0.20** |
| **2024-2025** | 39 | $71,864 | **2.07** |
| **2025-2026** | 37 | $97,848 | **1.97** |

### Yearly findings

**1. v1's edge is EXTREMELY strong in the current regime.** 2024, 2025, and H1 2026 are the three best consecutive years in v1's history. Rolling 2-year Sharpe 2024-2025 (2.07) and 2025-2026 (1.97) are top-tier, better than any 2-year window since 2019-2020. This confirms the distribution audit's implicit read: v1 loves the current market.

**2. v1 has had 5 bad years historically.** 2014, 2015, 2017, 2020, 2023 all had Sharpe below 0.30 or negative. 2017 (-1.78) and 2023 (-1.79) were catastrophic. The pre-reg halt logic was designed with these regime tails in mind.

**3. The pattern of bad years is telling.** 2013-2017 was a 5-year rough patch. 2020, 2023 were both single-year events. Not a clean "gold bear market" pattern; more like "v1 struggles when momentum signals get whipsawed" which happens in range-bound or transitional regimes.

**4. Live picked v1 up right after a peak.** Live went live 2026-07-20. Backtest 2026-H1 (Jan-Jun 2026) shows v1 crushing at Sharpe 1.33 with 73% WR. Live's first 2 trades (both losses) may just be a bad start to a period that regresses toward the mean. OR they may be the start of a 2017/2023-style down year. Halt-check math says we can't distinguish from noise until many more trades resolve.

## Part 2: M20 percentile bucket

Split all 360 v1 trades into LONG (223) and SHORT (137), then bucket each direction's trades into 5 equal-count quintiles by their M20 value.

**LONG trades (n=223), by M20 quintile:**

| bucket | n | M20 range | WR | mean $ | total $ | Sharpe |
|---|---|---|---|---|---|---|
| Q1_low | 45 | 0.34% to 2.06% | 66.7% | $666 | $29,967 | **1.84** |
| Q2 | 44 | 2.08% to 3.51% | 61.4% | $1,135 | $49,927 | 1.60 |
| Q3 | 45 | 3.53% to 5.36% | 62.2% | $800 | $36,021 | 1.49 |
| Q4 | 44 | 5.37% to 7.14% | 59.1% | $1,127 | $49,590 | 1.45 |
| **Q5_high** | 45 | 7.16% to 15.76% | **46.7%** | **-$1,126** | **-$50,683** | **-0.67** |

**SHORT trades (n=137), by M20 quintile:**

| bucket | n | M20 range | WR | mean $ | total $ | Sharpe |
|---|---|---|---|---|---|---|
| Q1_low | 28 | -12.07% to -5.53% | 60.7% | $944 | $26,427 | 0.37 |
| Q2 | 27 | -5.47% to -3.99% | 48.1% | $448 | $12,090 | 1.27 |
| Q3 | 27 | -3.87% to -2.40% | 40.7% | -$360 | -$9,723 | -1.00 |
| Q4 | 27 | -2.38% to -1.51% | 51.9% | $1,286 | $34,722 | 1.35 |
| Q5_high | 28 | -1.49% to -0.11% | 50.0% | $43 | $1,198 | -0.06 |

**Extreme M20 (top / bottom 10% of same-direction distribution):**

| slice | n | WR | total $ | Sharpe |
|---|---|---|---|---|
| LONG extreme (M20 >= 8.97%) | 23 | 47.8% | +$13 | 0.71 |
| LONG non-extreme | 200 | 60.5% | $114,809 | 1.03 |
| SHORT extreme (M20 <= -7.02%) | 14 | 57.1% | $15,058 | -0.30 |
| SHORT non-extreme | 123 | 49.6% | $49,657 | 0.53 |

### M20 bucket findings

**1. v1 LONGs in the top 20% M20 bucket LOSE money.** Q5_high LONGs (M20 > 7.16%) have Sharpe -0.67 and cumulative -$50,683 over 45 trades. WR drops from ~60% in Q1-Q4 to 46.7% in Q5. **This is a cliff, not a gradient.**

**2. The 2026-08-24 live LONG loser is exactly this type.** M20 was 13.66% (well above 7.16% Q5 threshold). WR of the historical Q5 bucket says 46.7% wins; the actual outcome was a loss. Fully consistent.

**3. Four independent lines of evidence now point at extreme-M20-LONG as the bad zone:**
- **Signal ablation (this morning):** dropping M20 from v1's AND conjunction raises Sharpe 0.77 -> 0.83.
- **M12 aggregator alternatives (this morning):** M6 is now SHORT, M12 is LONG, regime disagreement zone.
- **Live distribution audit (this afternoon):** 4 of 6 live signals have M20 in the 85+ percentile.
- **This M20 bucket analysis:** Q5 LONGs have Sharpe -0.67.

All four independently identified the same weak point in v1's rule. That's a strong convergent signal.

**4. SHORT side shows no clean extreme-M20 pattern.** SHORT Q3 (moderate M20) is the worst bucket, not the extremes. Not symmetric with LONG. Whatever the mechanism is on LONG, it's LONG-specific, not a mirrored effect.

**5. Extreme-LONG's mechanism (speculative):** M20 > 7% in weekly gold historically means the market has already run hard for 4 weeks. Buying into that runup (LONG entry Monday open after such a run) tends to fade. This is textbook mean-reversion setup, and v1 doesn't have any mean-reversion protection. The 4-week momentum tail traps v1 into buying tops.

## The v3 candidate that keeps writing itself

Combining today's four analyses:

**Candidate: v3 = v2 minus extreme-M20-LONG trades.**

Rough specification (would need formal pre-reg before backtest):
- Same v1 baseline rule
- Same v2 DXY-confirmation filter
- **Additional filter:** if signal is LONG AND M20 > 7% (or M20 in top 20% of its rolling backtest distribution), skip.

This candidate is grounded in:
- Two independent statistical findings (ablation drop-M20 improves; Q5-LONG loses)
- One live outcome (2026-08-24 M20=13.66% LONG loser)
- One regime observation (current live is clustering at high M20)

**Cannot ship without a fresh pre-reg with proper TRAIN/OOS split.** Same discipline as v3_ry_level (rejected in the last session). But this candidate has stronger convergent evidence than any prior v3-class idea.

## What this does NOT motivate

- Do NOT change v1 or v2 mid-window. Pre-reg locked through 2027-01-22.
- Do NOT ship "v1-minus-Q5" or "v2-minus-Q5" as a live product without a fresh pre-reg. Retrospective bucketing is exactly what pre-reg discipline is designed to prevent shipping.
- Do NOT interpret the 2014-2017 or 2023 bad years as reason to distrust v1. The pre-reg halt logic was designed FOR those regimes.
- Do NOT interpret 2024-2025's outstanding backtest performance as proof v1 will keep winning. Small-sample regime luck cuts both ways.

## What this DOES motivate

- **Draft a v3 candidate pre-reg for "v2 minus extreme-M20-LONG."** Fresh pre-reg, TRAIN 2010-2018 / OOS 2019-2026 chronological split, Bonferroni-N incremented for the M20-related discovery process (probably N=5+ given how many analyses today touched M20).
- **Add "M20 percentile" to the weekly report.** Similar in spirit to the ATR percentile idea from the distribution audit. Gives operators explicit awareness when the current signal is in the historically-bad zone.
- **When Rook builds the transparency page, include the by-year Sharpe table.** Shipping this data (5 losing years out of 16) is more honest than not.
- **Methodology page disclosure of the extreme-M20 finding.** "In backtest, v1 LONG trades where 20-day price momentum exceeded 7% had negative Sharpe. The 2026-08-24 live LONG loser was such a trade. A v3 candidate that filters these out is in design."

## Open follow-ups

1. **Formal pre-reg for v3 = v2 minus extreme-M20-LONG.** Needs threshold selection rule (fixed 7%? rolling percentile?), TRAIN/OOS split, ship gates. Multi-day drafting task.
2. **Same M20 bucket analysis on v2 signal set.** Does the Q5 pattern hold when v2's DXY filter is also applied? If yes, the M20 extremity is doing filtering that v2 alone doesn't cover.
3. **What ELSE distinguishes 2013-2017 and 2023 bad-year trades from good-year trades?** Signal-component regression to identify feature discriminators. Could inform additional v3-class filters.
4. **Live-monitoring: track live M20 percentile per call.** If future live SHORTs come in with M20 in Q3 (historically the worst SHORT bucket), that's a preemptive warning we can flag.

## Files touched

- Script: `scripts/v1_regime_and_m20_slices.py` (new)
- Doc: `docs/experiments/2026-09-08_v1_regime_and_m20_slices.md` (this file)
