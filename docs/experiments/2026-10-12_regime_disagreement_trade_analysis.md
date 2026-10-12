# Regime-disagreement trade analysis

**Date:** 2026-10-12
**Author:** Knox
**Status:** Diagnostic analysis, no live rule change.
**Trigger:** Queue item #4 from the 2026-09-08 end-of-day agenda: "Are historical trades in regime-disagreement periods systematically worse? If yes, 'sit out disagreement' is a legitimate v3 design element on its own."

## Design (locked before running)

For each v1/v2 weekly signal in 2010-01-01 to 2026-07-01, classify the price-trend regime at the signal date using three horizons:

- M12 = 252-day close pct_change
- M6  = 126-day close pct_change
- M3  =  63-day close pct_change

Classify the (sign(M12), sign(M6), sign(M3)) triple:

- `FULL_AGREE` - all three same sign, all non-zero
- `M3_FLIP` - M12=M6, M3 opposite
- `M6_FLIP` - M12=M3, M6 opposite (mid-horizon flip)
- `M12_FLIP` - M6=M3, M12 opposite (classic recent reversal - did not occur in sample)
- `SPLIT_LONG` - M12=LONG, M6=M3=SHORT (fading extended uptrend)
- `SPLIT_SHORT` - M12=SHORT, M6=M3=LONG (fading extended downtrend)
- `ZERO` - missing data on any horizon

Then stratify realized trade returns by (regime × direction) for v1, and separately for v2 (DXY-filtered). Also run a 2×2 cross-tab of {Q5 extreme-M20} × {FULL_AGREE vs disagree} to check whether regime disagreement is the hidden cause of the known extreme-M20-LONG pathology.

No new discovery, no bucket boundaries chosen post-hoc, no re-tuning. Pre-existing M20 bucket boundaries are from the 2026-09-08 analysis.

## Regime count distribution (across all 360 v1 trades)

| regime | n | share |
|---|---:|---:|
| FULL_AGREE | 211 | 58.6% |
| M3_FLIP | 57 | 15.8% |
| M6_FLIP | 30 | 8.3% |
| SPLIT_SHORT | 22 | 6.1% |
| SPLIT_LONG | 21 | 5.8% |
| ZERO | 19 | 5.3% |

Most signals (58.6%) fire in a full-agreement regime; the "classic reversal" `M12_FLIP` state never occurred inside a v1 signal in-sample (makes sense: v1 requires MA10>MA40 or MA10<MA40, which structurally aligns with M12 direction).

## Results - v1 trades × regime × direction

| regime | dir | n | WR | mean $ | total $ | Sharpe |
|---|---|---:|---:|---:|---:|---:|
| FULL_AGREE | LONG | 152 | 59.2% | $535 | $81,273 | 0.87 |
| FULL_AGREE | SHORT | 59 | 49.2% | $102 | $5,997 | 0.26 |
| M3_FLIP | LONG | 18 | 50.0% | $276 | $4,976 | −0.32 |
| M3_FLIP | SHORT | 39 | 51.3% | $1,199 | $46,748 | 1.24 |
| M6_FLIP | LONG | 14 | 57.1% | $46 | $648 | 0.74 |
| **M6_FLIP** | **SHORT** | **16** | **25.0%** | **−$1,190** | **−$19,038** | **−2.95** |
| SPLIT_LONG | SHORT | 21 | 71.4% | $1,512 | $31,759 | 2.34 |
| SPLIT_SHORT | LONG | 21 | 52.4% | $529 | $11,117 | 1.58 |
| ZERO | LONG | 18 | 77.8% | $934 | $16,809 | 2.67 |

## Results - v2 (DXY-filtered) trades × regime × direction

| regime | dir | n | WR | mean $ | total $ | Sharpe |
|---|---|---:|---:|---:|---:|---:|
| FULL_AGREE | LONG | 107 | 63.6% | $796 | $85,158 | 1.24 |
| FULL_AGREE | SHORT | 51 | 47.1% | $141 | $7,208 | 0.30 |
| M3_FLIP | LONG | 14 | 57.1% | $605 | $8,476 | 0.72 |
| M3_FLIP | SHORT | 27 | 59.3% | $1,688 | $45,571 | 1.81 |
| M6_FLIP | LONG | 10 | 60.0% | $40 | $402 | 0.53 |
| **M6_FLIP** | **SHORT** | **9** | **22.2%** | **−$1,646** | **−$14,813** | **−3.37** |
| SPLIT_LONG | SHORT | 19 | 68.4% | $1,533 | $29,128 | 2.14 |
| SPLIT_SHORT | LONG | 18 | 55.6% | $736 | $13,255 | 2.10 |

## Results - binary "agree vs disagree" by direction

| bucket | n | WR | mean $ | total $ | Sharpe |
|---|---:|---:|---:|---:|---:|
| v1 LONG FULL_AGREE | 152 | 59.2% | $535 | $81,273 | 0.87 |
| v1 LONG disagree | 71 | 59.2% | $473 | $33,549 | **1.25** |
| v1 SHORT FULL_AGREE | 59 | 49.2% | $102 | $5,997 | 0.26 |
| v1 SHORT disagree | 78 | 51.3% | $753 | $58,718 | **0.52** |
| v2 LONG FULL_AGREE | 107 | 63.6% | $796 | $85,158 | 1.24 |
| v2 LONG disagree | 54 | 61.1% | $616 | $33,258 | **1.64** |
| v2 SHORT FULL_AGREE | 51 | 47.1% | $141 | $7,208 | 0.30 |
| v2 SHORT disagree | 55 | 56.4% | $1,089 | $59,886 | **0.85** |

Disagreement is uniformly BETTER than agreement on both v1 and v2, for both LONG and SHORT. Any "sit out disagreement" filter would strip profitable trades.

## Cross-tab - M20 extremity × regime agreement (v2 LONG, the known pathology)

M20 Q5 threshold: ≥ 7.07% (same as the 2026-09-08 v2 bucket analysis)

| cell | n | WR | mean $ | total $ | Sharpe |
|---|---:|---:|---:|---:|---:|
| Q5 extreme × AGREE | 28 | 53.6% | −$1,300 | −$36,388 | −0.30 |
| Q5 extreme × DISAGREE | 5 | 60.0% | −$116 | −$578 | −0.18 |
| Q1-Q4 norm × AGREE | 79 | 67.1% | $1,539 | $121,545 | 1.93 |
| Q1-Q4 norm × DISAGREE | 49 | 61.2% | $691 | $33,836 | 1.85 |

The Q5-extreme pathology is driven almost entirely by the AGREE cell (n=28, cum −$36k). The DISAGREE cell is too small (n=5) to say the pattern holds there, but it does NOT look dramatically different. Importantly, regime disagreement is NOT the hidden driver of the Q5 pathology; the cell structure shows M20 extremity dominates regardless of regime state.

## Findings

**1. The naive hypothesis is REJECTED.** Trades in regime-disagreement periods are NOT systematically worse than trades in full-agreement periods. On the contrary, both v1 and v2 show disagreement = better Sharpe on both the LONG and SHORT side. A blanket "sit out disagreement" filter would reject this.

**2. One specific disagreement cell is strongly negative: M6_FLIP SHORT.**
- v1: n=16, Sharpe **−2.95**, cum −$19,038, WR 25.0%
- v2: n=9, Sharpe **−3.37**, cum −$14,813, WR 22.2%

This is the "SHORTing while the 6-month trend disagrees with the 3-month and 12-month trends" state. Economically: you're trying to short gold during a mid-horizon rally against the longer-term direction. The sample is small (n=16 and n=9) but the signal is directionally striking in both v1 and v2.

**3. SPLIT_LONG SHORT is strongly positive.**
- v1: n=21, Sharpe 2.34
- v2: n=19, Sharpe 2.14

Shorting an uptrend that is topping (M12 LONG, M6=M3=SHORT) is a durable high-quality setup in the sample. This is the pattern Russell & Howard describe as "selling into a topped-out run." A disagreement filter would reject this, destroying value.

**4. The extreme-M20-LONG pathology is independent of regime agreement.** The Q5×AGREE cell carries the −$36k loss on its own (28 of 33 trades). Regime disagreement does not explain the Q5 problem.

## Implications for the v3 pre-reg

- **DO NOT add a blanket regime-disagreement filter.** The data rejects it.
- **Candidate micro-filter: "do not SHORT when M6_FLIP."** Removes ~16 v1 trades, ~9 v2 trades, saves ~$19k / ~$15k, moves Sharpe up measurably. BUT the sample size is small (n=9 on v2), and this would be a *second* post-hoc filter stacked on top of the extreme-M20 filter.
- **Bonferroni cost:** This analysis adds +1 to the discovery count regardless of whether it informs the pre-reg. If the M6_FLIP finding is incorporated, that's a second decision from the same session and compounds the multiple-testing cost.

Recommendation: keep the v3 pre-reg scoped to **"v2 minus extreme-M20-LONG"** (one lever, one hypothesis, one discovery to pre-register against). Do NOT bundle in the M6_FLIP filter. Treat M6_FLIP as a flagged future candidate requiring its own replication on new data, and track it in the memory system as "research debt."

## Bonferroni accounting update

Session-level discovery count across the 2026-09-08 + 2026-10-12 research:
1. Adaptive stop probe
2. Intraday 5m trailing probe
3. v1 component ablation
4. M12 aggregator alternatives
5. Live vs backtest distribution
6. v1 M20 percentile buckets
7. v2 M20 bucket replication
8. Regime-disagreement analysis (this doc)

N = 8. Any v3 pre-reg permutation p-value gate should use Bonferroni-adjusted α = 0.05 / 8 = **0.00625**. This is tighter than the previous estimate of α = 0.05 / 6 = 0.0083.

## Files touched

- Script: `scripts/regime_disagreement_trade_analysis.py` (new)
- Data: `data/experiments/regime_disagreement_trades.csv` (trade-level dump)
- Doc: `docs/experiments/2026-10-12_regime_disagreement_trade_analysis.md` (this file)

## What this does NOT change

- No live rule change.
- v1 and v2 pre-reg stays locked through 2027-01-22.
- Does not change the main v3 candidate ("v2 minus extreme-M20-LONG").

## What this DOES change

- Rejects a candidate filter design (blanket regime-disagreement).
- Elevates one specific sub-cell (M6_FLIP SHORT) to "research debt" status with explicit sample-size caveat.
- Confirms extreme-M20 is an independent problem, strengthening the main v3 case.
- Raises the Bonferroni N for the pre-reg to 8.
