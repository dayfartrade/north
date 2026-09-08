# v1 signal-component ablation study

**Date:** 2026-09-08
**Author:** Knox
**Status:** Robustness audit.
**Trigger:** v1's directional signal is a 4-way AND: `M20 sign × M60 sign × MA10/MA40 cross × RY_chg direction`. Never tested which components carry the alpha. Methodology-critical question.

## What was tested

Twelve variants of v1's directional rule, run through the same backtest engine (2xATR fixed stop, Monday-open / Friday-close, $5 RT cost) on the full 2010-01-01 → 2026-07-01 window.

**Baseline:** full v1 (all 4 components required).

**Drop-one:** remove one component from the AND, keep other 3. (4 variants)

**Only-one:** keep one component, drop other 3. (4 variants)

**Extra:** drop_both_momentum (only MA + RY), only_momentum_M20_M60.

## Results

| variant | trades | #L | #S | WR | Sharpe | cum $ | maxDD |
|---|---|---|---|---|---|---|---|
| baseline_v1_all4 | 360 | 223 | 137 | 55.8% | 0.77 | $179,537 | -$56,043 |
| **drop_M20** | 401 | 245 | 156 | 55.4% | **0.83** | **$218,400** | -$56,043 |
| drop_M60 | 453 | 260 | 194 | 53.0% | 0.46 | $124,659 | -$85,532 |
| drop_MA | 389 | 240 | 149 | 55.0% | 0.71 | $185,333 | -$56,043 |
| drop_RY | 534 | 324 | 210 | 52.2% | 0.29 | $146,655 | -$85,230 |
| only_M20 | 829 | 456 | 381 | 49.8% | 0.03 | $60,065 | -$98,451 |
| only_M60 | 829 | 501 | 328 | 51.5% | 0.23 | $203,539 | -$103,026 |
| only_MA | 829 | 459 | 374 | 51.6% | 0.32 | $179,373 | -$131,285 |
| **only_RY** | 804 | 431 | 381 | 51.6% | **0.43** | $156,188 | -$123,766 |
| only_momentum_M20_M60 | 582 | 353 | 229 | 51.2% | 0.18 | $127,832 | -$85,230 |
| drop_both_momentum | 511 | 290 | 223 | 53.2% | 0.68 | $206,408 | -$85,532 |

## Load-bearing rank (drop-one)

| component | removal costs Sharpe | interpretation |
|---|---|---|
| **RY_chg** | +0.48 (0.77 → 0.29) | Single most important. Removing it collapses the signal. |
| **M60** | +0.31 (0.77 → 0.46) | Second most important. Long-term momentum matters. |
| MA10/40 | +0.06 (0.77 → 0.71) | Mildly load-bearing. Redundant with M60 (both are trend). |
| **M20** | -0.07 (0.77 → 0.83) | **Removing it IMPROVES Sharpe.** Anti-informative in the conjunction. |

## Findings

**1. M20 is dead weight in v1's conjunction, possibly worse than dead weight.** Removing M20 from the AND requirement raises Sharpe from 0.77 to 0.83 AND cumulative P&L from $180k to $218k. This isn't noise: M20's inclusion filters out 41 additional trades that on aggregate would have been net positive. The mechanism is likely that M20 (20-day momentum) is too noisy at the weekly signal timeframe. It vetoes trades where M60 and MA already agree, and those vetoed trades are on average winners.

**2. RY_chg is the single most load-bearing component.** Alone it produces the best single-component Sharpe (0.43). Removing it from the full conjunction drops Sharpe by 0.48, the largest gap of any single removal. This confirms the intuition that real-yield momentum drives gold direction.

**3. M60 is the second most load-bearing component.** Removing it drops Sharpe by 0.31. The momentum term at 60-day timeframe carries most of what people usually attribute to "momentum" in gold.

**4. MA10/40 is close to redundant with M60.** Removing MA only costs 0.06 Sharpe, because MA10 vs MA40 crossover is a slower-moving proxy for something already captured by M60 sign. The trend condition is doing very similar work twice.

**5. No single component reproduces v1 alone.** Best single component (RY, Sharpe 0.43) is far below v1's 0.77. The conjunction is doing real work, just not equally across the four components. RY + M60 + MA together carry the alpha; M20 is a drag.

**6. Drop-both-momentum (only MA + RY) preserves most of v1's alpha.** Sharpe 0.68 vs baseline 0.77. Small drop for a much simpler rule. Would fire on 511 trades vs baseline's 360, so it trades more but at slightly lower per-trade quality.

## The M20 anomaly deserves scrutiny

The M20-removal result is the standout. Let me be precise about what it does and does NOT imply.

**Does imply:** in the exact window 2010-2026 with the exact other components as specified, requiring `M20 sign` in the conjunction filters out 41 trades that were on aggregate positive. This is empirically true on this data.

**Does NOT imply:** M20 sign is "wrong" as a filter in general. Or that v1 should be re-shipped without M20 based on this finding. Or that any similar signal set would benefit from dropping M20.

**Cautions:**
- Post-hoc. Same discipline: cannot ship a "v1 minus M20" candidate without a fresh pre-reg and Bonferroni bump.
- Multiplicity: I tested 4 drop-one variants. The one that gave the best result may be the extreme of noise across 4 tests. A single-test Bonferroni correction would demand very strong evidence to conclude "drop M20 is real."
- No OOS split. Full-window backtest. If M20's failure is a 2020s regime effect (real yields dominating direction, momentum noise on short timeframe), the drop-M20 variant might not generalize forward.

## What this replicates or extends

- **Sensitivity analysis (data/experiments/registry.json baseline sensitivity):** Prior 11-parameter perturbation found baseline is robust. This is consistent: none of the drop-ones catastrophically fail (worst is drop_RY at Sharpe 0.29, still positive). But the sensitivity analysis didn't test structural removal, only parameter perturbation.
- **v2 finding (2026-08-31):** DXY confirmation filters out v1's losing quarter. This ablation shows that WITHIN v1's own conjunction, M20 is doing similar filtering wrong.

## What this does NOT motivate

- Do NOT ship "v1 minus M20." Post-hoc finding, needs pre-reg + OOS split for a fresh candidate.
- Do NOT remove M20 from any live rule mid-window.
- Do NOT claim RY_chg is "the" gold signal. Alone it runs at Sharpe 0.43. It needs at least one other component to reach the shipped v1's level.

## What this DOES motivate

- **v3-class candidate design:** A pre-registered variant that drops M20 (or replaces it with a different short-timeframe filter) is a legitimate research direction. Would need TRAIN/OOS split, fresh pre-reg, and Bonferroni discipline.
- **Test M20-removal on v2 too.** Open follow-up: does the DXY-confirmed subset also improve when M20 is dropped? If yes, both signals share the same weak link.
- **Methodology page disclosure:** v1's 4-component conjunction is unequally load-bearing. Publishing this table gives readers accurate weight on which parts of the signal are doing the work.
- **Simpler-is-viable observation:** Drop-both-momentum (MA + RY only) runs at Sharpe 0.68 with fewer moving parts. For a hypothetical simpler-story product, this is worth remembering.

## Files touched

- Script: `scripts/v1_signal_ablation.py` (new)
- Doc: `docs/experiments/2026-09-08_v1_signal_component_ablation.md` (this file)

## Open follow-ups

1. Repeat ablation on v2 signal set (add DXY filter over each ablated variant). Does M20 stay anti-informative there?
2. Regime-split the ablation: is M20 anti-informative in both M12 LONG and M12 SHORT regimes, or only one?
3. Chronological split-sample: does drop-M20 hold in TRAIN 2010-2018 AND OOS 2019-2026, or is it OOS-only?
