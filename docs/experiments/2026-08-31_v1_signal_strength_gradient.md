# v1 signal-strength gradient probe

**Date:** 2026-08-31
**Author:** Knox
**Status:** Robustness audit. Confirms v1's 4-of-4 gate is well-calibrated.
**Trigger:** v1 uses a binary gate (all 4 conditions align OR FLAT). Question: is that gate too strict, too permissive, or right?

## Method

`scripts/v1_signal_strength_gradient.py`. For each week, compute:

- `long_score = sum(M20>0, M60>0, MA10>MA40, RY_chg<0)` (0-4)
- `short_score` = inverted

Simulate trades at:
- `min_score >= 4`: v1's baseline rule
- `min_score >= 3`: 3-of-4 counts (relaxed)
- `min_score >= 2`: 2-of-4 counts (very relaxed)

Then partition by exact score to isolate what each level contributes.

Direction: whichever side has the higher score and clears min.

## Results

**Cumulative "at least this score" tests:**

| threshold | n | WR | mean %/trade | Sharpe | cum $ |
|---|---|---|---|---|---|
| **score >= 4 (v1)** | **363** | **55.9%** | **+0.227** | **0.767** | **+$181,598** |
| score >= 3 | 700 | 50.6% | +0.060 | 0.206 | +$138,498 |
| score >= 2 | 710 | 50.6% | +0.061 | 0.212 | +$141,728 |

**Exact-score partitions:**

| level | n | WR | mean %/trade | Sharpe | cum $ |
|---|---|---|---|---|---|
| score == 4 (v1) | 363 | 55.9% | +0.227 | +0.767 | **+$181,598** |
| **score == 3** | **337** | **44.8%** | **-0.120** | **-0.425** | **-$43,099** |
| score == 2 | 10 | 50.0% | +0.161 | +0.862 | +$3,229 |

## The finding

**v1's 4-of-4 gate is exactly the right place.**

The 3-of-4 subset (337 trades where exactly 3 conditions align) has:
- Win rate 44.8% (below 50%)
- Mean -0.12% per trade
- Sharpe -0.42
- Cumulative **-$43,099** over 16 years

The 4-of-4 subset (363 trades where all 4 align):
- Win rate 55.9%
- Mean +0.23% per trade
- Sharpe +0.77
- Cumulative +$181,598

**The gap between "all 4 align" and "3 of 4 align" is night and day.** Same underlying signal set. Removing one condition's requirement turns a winning strategy into a losing one.

## Why this matters

Three implications:

**1. v1's rule structure is not arbitrary.** The 4 conditions (M20, M60, MA cross, RY change) have meaningful interaction effects. They're not noisy indicators averaging out - each one is doing real work, and requiring all 4 to align is the filter that captures the interaction.

**2. Relaxing the gate would materially damage the product.** If a future well-meaning modification tried "score >= 3 for higher fire rate," it would double the sample (700 vs 363 trades) but the extra trades would be net-losers. Fire more, make less.

**3. The 4-of-4 gate is exactly what "high conviction" looks like in this rule shape.** Same principle we saw earlier today with `ensemble_unanimous` (all 3 signals must agree): stricter filters catch better trades. Binary conviction gates work when the underlying conditions have real interaction.

## What this does NOT mean

- Does NOT mean the gate could be tighter and still work. Score = 5 doesn't exist (only 4 conditions). We're at the maximum strictness this rule shape allows.
- Does NOT mean 3-of-4 is worthless as INFORMATION. A 3-of-4 signal that DIDN'T fire could still be informative for a discretionary trader; but as a mechanical rule it's net-negative.
- Does NOT motivate any change. v1 rule stays 4-of-4. This audit confirms the calibration.
- Does NOT count as a rejected trial. This is a robustness audit on v1's existing rule, not a new candidate.

## Public disclosure implications

This is a strong honesty asset. Candidate line for a future methodology page:

> "The 4-condition-must-agree rule looks strict. It's calibrated: relaxing to 3-of-4 doubles the trade count but the added trades lose money in aggregate (-$43,099 over 16 years). Our binary gate is where the edge lives."

Not touching public copy today. Note for later.

## Also confirms today's ensemble-unanimous finding

The `ensemble_unanimous` variant (`docs/experiments/2026-08-31_ensemble_aggregator_variants.md`) showed the same pattern at a higher level: requiring all 3 signals (v1, v2, monthly M12) to agree produced a Sharpe 1.09 subset in the M12 LONG regime, at the cost of very low fire rate. Same mechanism: binary conviction gates catch better trades.

Not proposing a "score >= 5" variant (impossible; only 4 conditions). But this pair of findings suggests: **v1's rule shape rewards strictness. If we ever design a v-something-else, the design principle "all conditions must align" is well-supported.**

## Files touched

- Script: `scripts/v1_signal_strength_gradient.py` (new)
- Doc: `docs/experiments/2026-08-31_v1_signal_strength_gradient.md` (this file)
