# Bonferroni-N accounting reconciliation

**Date:** 2026-10-12
**Author:** Knox
**Status:** Reference doc. Governs any future v3-class pre-reg against the gold weekly sample.
**Trigger:** v3_ry_level pre-reg claimed N=6 at drafting. v3_m20 pre-reg claimed N=9. v3_m20 was then voided for discipline violation. Need an explicit accounting for any future candidate.

## Why this matters even after v3_m20 voided

The purpose of Bonferroni-N is to adjust the acceptable false-positive rate for the number of hypotheses tested against the same data. The relevant data pool is the 2010-01-01 to 2026-07-20 XAU/USD Dukascopy sample. Every analysis that probed this sample for a candidate filter contributes to N, regardless of whether the specific candidate was pre-registered or shipped.

A future pre-reg targeting the same extreme-M20-LONG hypothesis (or any adjacent filter design) must use the correct N. Under-counting N inflates the apparent significance of any future finding.

## Discovery pool, chronological

| # | Discovery / probe | Date | Doc |
|---|---|---|---|
| 1 | v1 fire-rate split by v2 | 2026-08-31 | docs/experiments/2026-08-31_v1_fire_rate_by_v2.md |
| 2 | v2-skipped predictor probe (6 features probed: M20 mag, M60 mag, MA spread, ATR%, RY_chg mag, RY_level) | 2026-08-31 | docs/experiments/2026-08-31_v2_skipped_predictor_probe.md |
| 3 | M12 regime transition indicators | 2026-08-31 | docs/experiments/2026-08-31_m12_regime_transition_indicators.md |
| 4 | Adaptive stop probe (daily) | 2026-09-08 | docs/experiments/2026-09-08_v1_v2_adaptive_stop_probe.md |
| 5 | Intraday 5m trailing probe | 2026-09-08 | docs/experiments/2026-09-08_v1_v2_intraday_trailing_probe.md |
| 6 | v1 signal-component ablation | 2026-09-08 | docs/experiments/2026-09-08_v1_signal_component_ablation.md |
| 7 | M12 aggregator alternatives | 2026-09-08 | docs/experiments/2026-09-08_m12_aggregator_alternatives.md |
| 8 | Live vs backtest distribution | 2026-09-08 | docs/experiments/2026-09-08_live_vs_backtest_distribution.md |
| 9 | v1 M20 percentile buckets | 2026-09-08 | docs/experiments/2026-09-08_v1_regime_and_m20_slices.md |
| 10 | v2 M20 bucket replication | 2026-09-08 | docs/experiments/2026-09-08_v2_m20_bucket_replication.md |
| 11 | Regime-disagreement trade analysis | 2026-10-12 | docs/experiments/2026-10-12_regime_disagreement_trade_analysis.md |
| 12 | Rolling 52w percentile comparator | 2026-10-12 | docs/experiments/2026-10-12_rolling_52w_percentile_comparator.md |

## Reconciliation vs prior pre-reg N claims

**v3_ry_level pre-reg (2026-08-31) claimed N=6.** It counted the 6 features probed in the v2-skipped predictor analysis (row 2 above). Honest accounting at that moment: should have also counted rows 1 and 3 (which contributed to the RY_level hypothesis specifically). True N at that moment was closer to **8** (6 features + 2 adjacent analyses). The pre-reg under-counted. Did not affect the outcome because v3_ry_level was rejected on effect-size gates, not p-value gates.

**v3_m20 pre-reg (2026-10-12) claimed N=9.** It counted the 9 analyses from 2026-09-08 onward (rows 4-12). Did NOT count rows 1-3 from the 2026-08-31 session, on the implicit assumption that the extreme-M20 hypothesis emerged from the 09-08 analyses specifically. Honest accounting: rows 1-3 contributed to the broader exploration of v1's structural weaknesses, so they should count. True N at that moment was **12**. The pre-reg under-counted.

**Current (as of 2026-10-12 end-of-day) honest N for the full discovery pool: 12.**

## Rule for future pre-regs against this sample

Any pre-reg that proposes a filter on top of v1 or v2 using features derived from the 2010-01-01 to 2026-07-20 Dukascopy sample must use **N ≥ 12** in its Bonferroni accounting. Additionally:

- If the pre-reg targets a hypothesis the author has previously tested (even informally, even voided like v3_m20), add +1 per prior exposure.
- If the pre-reg adds new feature exploration beyond what is in the table above, add +1 per new feature probed.
- Bonferroni-adjusted α on any permutation p-value gate: 0.05 / N.

## Specific impact on any future "extreme-M20-LONG" pre-reg

The author has seen the v3_m20 retrospective result (ship gates 1-4 PASS, matched-pair perm FAIL, TRAIN/OOS Sharpe-gap reject). Any future pre-reg testing the same hypothesis must declare this exposure.

Starting Bonferroni-N for such a future pre-reg: **13** (N=12 from the discovery pool, +1 for prior exposure to the voided retrospective).

Adjusted α on permutation p-value: 0.05 / 13 = **0.00385**.

If the future pre-reg also probes new features (e.g., different M20 window, rolling percentile instead of fixed threshold, SHORT-side variants), each adds +1 to N and tightens α further.

## Practical implication

The v3_m20 result (viewed under violation) had a matched-pair perm p-value of 0.346. That is nowhere near 0.00385. Even granting the viewing, there is no realistic path by which a future pre-reg against the same data could pass the matched-pair gate at the correct N. **Future v3-class work on this hypothesis must wait for new data.**

The Dukascopy pull running in the background today failed with SSL errors. New data unlock timing: unknown, pending data source recovery. Live resolves accumulate at the rate of maybe 10-20 per year given current fire rate.

## Files

- This doc: `docs/experiments/2026-10-12_bonferroni_accounting_reconciliation.md`
- Referenced pre-regs: `docs/experiments/2026-08-31_far_weekly_v3_ry_level_prereg.md`, `docs/experiments/2026-10-12_far_weekly_v3_m20_extremity_prereg.md`
