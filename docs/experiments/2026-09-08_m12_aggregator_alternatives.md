# Alternative M12 regime aggregators

**Date:** 2026-09-08
**Author:** Knox
**Status:** Research audit. Two significant findings.
**Trigger:** Prior finding (2026-08-31, m12_regime_bias memory) established that the current ensemble is behaving as "v1 minus SHORT signals" because M12 has been LONG-stuck since 2023-03-17. Question: is there a better monthly-regime aggregator that would make the ensemble a real 3-way vote? And if we tried a more-responsive variant, would it show a regime change we're currently blind to?

## What was tested

Six aggregator variants characterized on daily data 2010-2026, then each substituted into the 3-way ensemble backtest (v1 + v2 + monthly majority).

| variant | lookback | rule |
|---|---|---|
| M3 | 63 trading days (~3mo) | sign of 3-month price momentum |
| M6 | 126 td (~6mo) | sign of 6-month price momentum |
| M12 | 252 td (~12mo, baseline) | sign of 12-month price momentum |
| M24 | 504 td (~24mo) | sign of 24-month price momentum |
| M12_rw | EWM half-life 63d | recency-weighted 12-month, exponential decay |
| multi_consensus | 3+6+12 majority | majority sign vote of M3, M6, M12 |

## Phase 1: aggregator behavior

Direction on every daily bar (excluding FLATs from missing lookback):

| variant | %LONG | flips | median streak | max streak | current dir | current streak |
|---|---|---|---|---|---|---|
| M3 | 57.2% | 162 | 5 days | 183 | SHORT | **65 days** |
| M6 | 62.1% | 103 | 5 days | 665 | SHORT | **30 days** |
| M12 (baseline) | 60.8% | 100 | 5 days | 868 | LONG | **868 days** |
| M24 | 70.7% | 20 | 45 days | 807 | LONG | 630 days |
| M12_rw | 61.3% | 131 | 6 days | 687 | SHORT | **32 days** |
| multi_consensus | 60.0% | 147 | 4 days | 685 | SHORT | **30 days** |

**Four out of six aggregators currently say SHORT.** Only M12 (current baseline, 868 days) and M24 (630 days) still say LONG. The signals are diverging RIGHT NOW.

M6, M12_rw, and multi_consensus all flipped SHORT within the last 30-32 days. M3 flipped SHORT 65 days ago.

## Phase 2: ensemble backtest under each aggregator

Same 844-week window, same 2xATR fixed stop, same signal machinery. Only the monthly-regime vote changes.

| variant | trades | #L | #S | WR | Sharpe | cum $ | maxDD |
|---|---|---|---|---|---|---|---|
| v1 baseline (no monthly) | 363 | 223 | 140 | 55.9% | 0.77 | $181,598 | -$56,043 |
| v2 baseline (no monthly) | 270 | 161 | 109 | 58.5% | 1.04 | $187,570 | -$50,318 |
| **ensemble[M6]** | 331 | 213 | 118 | 57.7% | **0.92** | $193,446 | -$56,043 |
| ensemble[multi_consensus] | 344 | 219 | 125 | 57.0% | 0.81 | $181,888 | -$56,043 |
| ensemble[M12] (current) | 334 | 210 | 124 | 56.6% | 0.80 | $178,078 | -$56,043 |
| ensemble[M24] | 322 | 205 | 117 | 56.8% | 0.80 | $170,057 | -$56,043 |
| ensemble[M12_rw] | 341 | 215 | 126 | 56.3% | 0.73 | $169,374 | -$56,043 |
| ensemble[M3] | 358 | 221 | 137 | 55.6% | 0.72 | $172,216 | -$56,043 |

## Findings

**1. Multiple monthly aggregators currently disagree with M12.** The single most important operational observation from this experiment. M12 (baseline) says LONG for the 868th consecutive day. Four other aggregators (M3, M6, M12_rw, multi_consensus) say SHORT and have been saying SHORT for 30-65 days.

Practically: if we had shipped the ensemble with M6 instead of M12, the current live behavior would be different. This week (2026-09-07) is v1 FLAT, so the ensemble is FLAT regardless of monthly aggregator. But the next time v1 or v2 fires SHORT, ensemble[M6] would go SHORT (majority) while ensemble[M12] would go FLAT (1 v 1 v 1 no majority) or LONG-outvoted.

**2. Ensemble[M6] genuinely improves on ensemble[M12].** Sharpe 0.92 vs 0.80. Not massive but real: ~15% Sharpe improvement, and cum P&L up from $178k to $193k. M6 hits the sweet spot: responsive enough to flip on real regime changes but not so noisy that it triggers on 3-month whipsaws (162 flips for M3 vs 103 flips for M6 vs 100 for M12).

**3. Recency-weighted M12 (M12_rw) is WORSE than plain M12.** Sharpe 0.73 vs 0.80. Counter-intuitive: giving recent months more weight should make the aggregator more responsive to regime changes. It does (131 flips vs 100 for plain M12), but the extra flips are on average wrong. The exponential decay picks up noise faster than signal at this horizon.

**4. Multi-consensus is marginally worse than plain M12.** Sharpe 0.81 vs 0.80. Basically identical. Adding M3 and M6 as extra voters alongside M12 gives you nothing over M12 alone. The signal is in one of the three components, not the consensus.

**5. v2 baseline still beats every ensemble variant.** Sharpe 1.04 vs best ensemble (M6) 0.92. **The ensemble as a structural approach is fundamentally worse than v2 alone.** No monthly aggregator changes this. What ensemble does is add a monthly filter on top of v2, but the monthly filter (in any variant tested) subtracts alpha rather than adds it.

**6. The M6 finding is genuinely interesting but partly a lookup-window effect.** M6 is the closest analog to "recent 6-month price action," which is a natural macro-regime timeframe. The reason M12 fails right now is precisely that gold's 12-month lookback captures the 2025 bull run, but the 6-month lookback is starting to reflect the summer 2026 pullback. That's a genuine regime shift M12 is blind to.

## Cross-check: what does this imply about current market state?

The v1 signal for the week of 2026-09-07 is FLAT: M20 +2.1%, M60 +5.0%, MA10>MA40 true, RY_chg 0bps. Momentum still positive on the 20-60 day timeframes, but weakening.

M6 flipping SHORT ~30 days ago says the medium-term (6-month) price trend is now negative. Consistent with the 2026-07 gold pullback and the -3.30% v1 LONG loss on 2026-08-24 (which was v2-skipped and part of the M12/M6 disagreement zone).

This is not a live-rule change trigger. But it IS worth noting: the market may be in a transition regime that our shipped v1 (which doesn't use any monthly filter) and the shadow ensemble (which uses M12) are both slow to detect.

## What this does NOT motivate

- Do NOT change the shadow ensemble mid-window. It's on the pre-registered forward window through 2027-01-22. Changing it invalidates the comparison.
- Do NOT ship "ensemble with M6" as a live product based on this backtest. Post-hoc, needs a fresh pre-reg with OOS split.
- Do NOT interpret the "4-of-6 aggregators say SHORT" as a trading signal. This is characterization, not a firing rule.

## What this DOES motivate

- **Add a "regime disagreement" indicator to the weekly report.** Something like "Monthly regime: M12 LONG (868d), M6 SHORT (30d), consensus SHORT." Gives operators and readers explicit awareness of the regime uncertainty. Doesn't drive a trade decision but improves transparency.
- **If a future ensemble candidate is designed, use M6 not M12 as the monthly vote.** Pre-registered, of course. Fresh candidate with OOS split.
- **The v2 vs ensemble finding is a real result:** ensemble as an approach is worse than v2 alone regardless of aggregator. This narrows the "candidate space" for future v3-class work: focus on refining v2's filter rather than adding a monthly vote layer.
- **Methodology page disclosure:** "We tested six monthly-regime aggregators. Four out of six currently disagree with M12, our baseline. If our shadow ensemble were built on M6 instead, current live behavior would differ. We disclose this rather than hide it."

## Open follow-ups

1. **Regime disagreement history:** how often across 2010-2026 does M12 disagree with M6? What's the base rate for a regime-transition period like the current one?
2. **Trades made during regime-disagreement periods:** are these systematically worse than trades made during regime-agreement periods? If so, a "sit out disagreement" filter would be a legitimate v3 candidate design element.
3. **DXY and real-yield decomposition:** which macro factor is driving the M6/M12 divergence right now? Real yields have been range-bound (from live signal component values). DXY has been the more volatile variable.

## Files touched

- Script: `scripts/m12_aggregator_alternatives.py` (new)
- Doc: `docs/experiments/2026-09-08_m12_aggregator_alternatives.md` (this file)
