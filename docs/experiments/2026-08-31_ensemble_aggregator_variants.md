# Ensemble aggregator variants

**Date:** 2026-08-31
**Author:** Knox
**Status:** Exploratory analysis. Not a pre-reg for a new candidate.
**Trigger:** Today's M12 regime-split analysis showed the current ensemble (2-of-3 majority) matches v1 in M12 LONG regime because monthly M12 vote is a constant tiebreaker. Question: is there a better aggregator? Does M12 add anything over v2 alone?

## Method

`scripts/ensemble_aggregator_variants.py`. Test three aggregators on the same v1 signal path:

1. **ensemble_current**: 2-of-3 majority of {v1, v2, monthly M12} (baseline, currently in shadow)
2. **ensemble_unanimous**: all three must agree (v1 == v2 == monthly, non-FLAT)
3. **v2 alone**: reference (equivalent to "v1 AND v2 must both fire")

Same v1 signal rule, same 2xATR stop, same $5 RT cost. Only the aggregator changes.

## Results

**Full sample 2010-2026:**

| variant | n | WR | mean %/trade | Sharpe | cum $ |
|---|---|---|---|---|---|
| v1 | 363 | 55.9% | +0.227 | 0.767 | $181,598 |
| **v2** | 270 | 58.5% | +0.310 | **1.042** | **$187,570** |
| ensemble_current (2-of-3) | 334 | 56.6% | +0.238 | 0.804 | $178,078 |
| ensemble_unanimous (all 3) | 172 | 58.1% | +0.292 | 0.946 | $94,863 |

**M12 LONG regime:**

| variant | n | WR | mean %/trade | Sharpe | cum $ |
|---|---|---|---|---|---|
| v1 | 233 | 57.5% | +0.204 | 0.672 | $135,090 |
| v2 | 169 | 60.9% | +0.280 | 0.914 | $135,945 |
| ensemble_current | 218 | 58.3% | +0.207 | 0.674 | $130,402 |
| **ensemble_unanimous** | 116 | 62.9% | +0.342 | **1.088** | $80,827 |

**M12 SHORT regime:**

| variant | n | WR | mean %/trade | Sharpe | cum $ |
|---|---|---|---|---|---|
| v1 | 130 | 53.1% | +0.267 | 0.949 | $46,507 |
| **v2** | 101 | 54.5% | +0.360 | **1.271** | $51,625 |
| ensemble_current | 116 | 53.4% | +0.297 | 1.077 | $47,676 |
| ensemble_unanimous | 56 | 48.2% | +0.188 | 0.630 | $14,036 |

## Findings

**1. v2 alone remains the best aggregator overall.** Sharpe 1.042 full-sample, dominates M12 SHORT regime (1.271). Not beaten by any 3-way variant on aggregate metrics.

**2. ensemble_unanimous has a very specific asymmetric profile.**
- Highest Sharpe of ANY variant in M12 LONG regime (1.09), driven by strict filtering to only fully-aligned setups.
- WORST Sharpe in M12 SHORT regime (0.63), because 3-way agreement is rare when M12 is choppy (shorter streaks, more disagreements).
- Fires on only 172 trades over 16 years (10.6 per year). Over-filtered for a public product; long stretches with no calls.
- Cumulative P&L only 51% of v2's ($94k vs $187k).

**3. ensemble_current (2-of-3) is a compromise that doesn't beat its components.** Sharpe 0.80 sits between v1 (0.77) and v2 (1.04). In M12 LONG regime it's essentially v1 (0.67 = 0.67). In M12 SHORT it's essentially v2 (1.08 close to 1.27). The 3-way vote is not additive - it just picks whichever component is dominating in the current regime.

**4. Monthly M12 as an aggregator vote is not adding value net.** In every regime cell, v2 alone beats ensemble_current in either Sharpe or cumulative P&L or both. If M12 were adding signal, we'd expect at least one cell where the ensemble strictly dominates v2. There isn't one.

## Interpretation

The current ensemble design is under-informative in a specific way: monthly M12 has been LONG for 1,221 days, which turns it into a constant vote that just favors whichever direction happens to align with LONG. In practice:

- On v1 LONG signals: v1 + M12 = 2 votes, ensemble = LONG regardless of v2 (which drops the DXY filter benefit)
- On v1 SHORT signals: M12 dissents, so ensemble = FLAT unless v2 also confirms SHORT (which blocks most v1 shorts)

Effectively the "3-way ensemble" is "v1 for LONGs, v2 for SHORTs." Not really an ensemble in the aggregator sense.

The unanimous variant is more honest as an ensemble - it truly requires 3-way agreement. But the cost is a very low fire rate (10.6/year vs v2's 16.9/year vs v1's 22.7/year) and half the cumulative P&L. That's not a productizable strategy in a "one call per week" format.

## Practical implication

**v2 remains the strongest ship candidate.** Nothing about the alternative-aggregator probe changes this. If anything, it further downgrades the current ensemble - the vote is not adding value net.

**No new pre-reg proposal.** The unanimous ensemble is interesting academically but not productizable in NORTH's format. The current ensemble was already downgraded by today's regime analyses; this probe seals it.

**No live behavior change.** All variants remain shadow. v1 stays as the shipped product.

## What NOT to do

- Do not modify the current ensemble rule. It's in a pre-reg forward window; changing it mid-window invalidates the comparison.
- Do not propose ensemble_unanimous as a new candidate. Its fire rate is too low for the product format, and cumulative P&L is half of v2's. Would need to run under a different framing (e.g., "high-conviction only" side product) with its own pre-reg.
- Do not increment the retirement wall. This is a variant probe on an existing candidate, not a new candidate rejection.

## Files touched

- Script: `scripts/ensemble_aggregator_variants.py` (new)
- Doc: `docs/experiments/2026-08-31_ensemble_aggregator_variants.md` (this file)
