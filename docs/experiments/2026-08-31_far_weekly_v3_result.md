# v3 backtest result: REJECTED per pre-reg

**Date:** 2026-08-31
**Author:** Knox
**Status:** REJECTED per pre-registered ship gates.
**Pre-reg:** `docs/experiments/2026-08-31_far_weekly_v3_ry_level_prereg.md`
**Backtest script:** `scripts/far_weekly_v3_backtest.py`

## What v3 was

v3 = v2 + real-yield-level filter:
- LONG requires v2 LONG + `RY_level >= 0.25%`
- SHORT requires v2 SHORT + `RY_level <= 1.50%`

Thresholds locked BEFORE any v3 backtest, informed by two independent probes (v2-skipped predictor probe, regime-transition indicators) that both surfaced RY_level as a candidate feature.

## The result

**Full sample 2010-2026:**

| variant | n | WR | mean %/trade | Sharpe | cum $ |
|---|---|---|---|---|---|
| v1 | 363 | 55.9% | +0.227 | 0.767 | $181,598 |
| v2 | 270 | 58.5% | +0.310 | **1.042** | $187,570 |
| v3 | 213 | 56.8% | +0.252 | 0.836 | $99,764 |

**OOS 2019-2026 (the ship-gate window):**

| variant | n | WR | mean %/trade | Sharpe | cum $ |
|---|---|---|---|---|---|
| v1 | 182 | 58.2% | +0.282 | 0.939 | $137,012 |
| v2 | 136 | 62.5% | +0.421 | **1.351** | $149,791 |
| v3 | 92 | 59.8% | +0.326 | 1.009 | $67,612 |

v3 has decent absolute numbers. Sharpe 1.009 OOS, WR 59.8% OOS, cum $67k. In a vacuum, this is a fine strategy.

But v2 is better on every metric. And the pre-reg gate was "v3 must beat v2 to add value." v3 doesn't.

## Ship gate results

| gate | detail | verdict |
|---|---|---|
| 1. v3 OOS Sharpe >= v2 OOS Sharpe | v3=1.009 vs v2=1.351 | **FAIL** |
| 2. v3 OOS P&L >= 80% of v2 OOS | v3=$67,612 vs v2=$149,791 (45.1%) | **FAIL** |
| 3. v3 total trades >= 100 | n=213 | PASS |
| 4. TRAIN vs OOS Sharpe within 50% | train=0.687, oos=1.009 (47% diff) | PASS (barely) |
| 5. v3 Sharpe >= v2 in both regime cells | LONG v3=0.70/v2=0.91, SHORT v3=1.04/v2=1.27 | **FAIL** |

3 of 5 fail. Per pre-reg reject gates: **v3 REJECTS**.

## Why v3 failed

The RY_level filter drops trades that v2 already captured well. Instead of removing only the losers, it removes winners too.

On the OOS window:
- v2: 136 trades, $149,791 cumulative
- v3: 92 trades, $67,612 cumulative
- v3 dropped 44 additional trades that were collectively worth **~$82k of P&L**.

The RY_level feature looked promising in single-feature probing because the LOSERS clustered at low RY. But that doesn't mean the low-RY WINNERS are safe to drop. In practice, the filter throws out both, and the winner-loss ratio is not favorable enough to justify the smaller sample.

Interpretation of the underlying signal:

- The predictor probe was correct that RY_level differs between v2-skipped winners and losers, but the effect size is smaller than the effect of losing sample count.
- The transition-indicator finding (bulls end at negative real yields) is still a real pattern, but "gold bulls end at low RY" doesn't mean "individual LONG trades at low RY lose money." Those are different scales of aggregation.
- Feature discovery from probing 6 features (Bonferroni-N = 6) with only ~90 losing trades to distinguish is under-powered. RY_level looked like the strongest signal but it wasn't strong enough to survive as a stand-alone filter.

## What this means for the discipline

**This is exactly what pre-registration is for.** The RY_level finding was seductive:
- Two independent analyses today surfaced it
- Economic story was coherent (low real yields = exhausted macro tailwind)
- Predictor probe showed clear separation between v2-skipped winners and losers on RY_level

If we had shipped v3 based on that enthusiasm without a locked-threshold pre-reg, we would have:
- Made v1 -> v3 the live product path
- Given up 55% of v2's OOS P&L for a marginal improvement over v1
- Increased the retail-facing "trades taken" from 136 to 92 (33% fewer signals) without corresponding quality gain

The pre-reg's `Reject` clause "Post-hoc threshold tweak needed to pass any gate -> HARD REJECT" also protects us here. It would be tempting to try RY_level >= 0.10% or RY_level >= 0.15% instead of 0.25% and see if the numbers improve. Doing so would be data-fitting. The pre-reg says: if the locked thresholds don't work, v3 is dead. Move on.

## What v3's failure does NOT mean

- Does NOT invalidate v2. v2 is still the strongest ship candidate by every backtest measure.
- Does NOT retire the RY_level idea forever. It just means "RY_level as an additional binary filter on top of v2" doesn't work. A different mechanism using RY_level (as an interaction term, or as a signal-strength scalar, or in combination with something else) could work. Any such candidate would need its own pre-reg.
- Does NOT change v1 or v2's forward-validation windows. Both continue on schedule.
- Does NOT change the retirement wall count meaningfully - v3 goes from `pre_registered` to `rejected_ship_gates`, incrementing the rejected count by 1.

## Registry update

Trial `far_weekly_gold_read_v3` verdict changed: `pre_registered` -> `rejected_ship_gates`.

Retirement wall count moves from 38 to 39 retired trials.

Bonferroni-N (for the multi-feature probe that surfaced this candidate) is 6; not applied to a p-value here because the ship gates are threshold-based, not p-value-based. Noted for the record.

## Files touched

- Backtest script: `scripts/far_weekly_v3_backtest.py` (new)
- Result doc: `docs/experiments/2026-08-31_far_weekly_v3_result.md` (this file)
- Registry: `data/experiments/registry.json` verdict updated
- Retirement wall regen: `docs/launch/retirement_wall.md` (auto)
