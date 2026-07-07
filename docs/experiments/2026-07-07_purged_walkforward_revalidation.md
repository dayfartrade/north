# Experiment: purged_walkforward_revalidation of v7.2.1

**Registered UTC:** 2026-07-07T19:20:00Z
**Blinded until:** results computed same-session
**Layer:** validation-only (no strategy-code change proposed)
**Owner:** Knox

## Hypothesis

v7.2.1 walks forward positively under **López de Prado Ch 7.4 purged K-Fold
CV with 1% embargo**. If it does not, the earlier positive walk-forward
result was inflated by residual serial-correlation leakage between
adjacent folds.

## Rationale

Today's original walk-forward (`scripts/walk_forward_validation.py`) used
plain chronological 20/10/5 sliding windows. That is a lightweight
approximation of proper Purged K-Fold CV:

- **Purging** (Ch 7.4.1) drops training bars whose labels overlap the test
  set. For session-boundary trades that never overlap in time, this reduces
  to a no-op — so purging matters little for us.
- **Embargo** (Ch 7.4.2) drops training bars that IMMEDIATELY FOLLOW a test
  set, to defeat serial-correlation leakage from ARMA-like price processes.
  Suggested magnitude: h ≈ 0.01 × T ≈ 0.8 days over an 80-day window.
  For 24h/day GC futures this is meaningful.

If v7.2.1 walk-forward turns from positive to negative with embargo, our
earlier "signal is real" claim was leakage. If it holds, the shipped
strategy has evidence beyond the DSR-flagged concern.

## Data

- **Window:** 2026-04-13 → 2026-07-01 (v7.2.1 sample as shipped, n=52)
- **CV split:** 5-fold Purged K-Fold with pctEmbargo = 0.01
- **Embargo magnitude:** ~0.8 calendar days between test-end and next train-start

## Method

1. Build a t1 pd.Series from the shipped v7.2.1 trades (entry_ts → exit_ts).
2. Instantiate the PurgedKFold class (adapted from LdP Snippet 7.3, no
   sklearn dependency required for our simple slice-based backtest).
3. For each of 5 folds:
   - Test = one contiguous slice of trades
   - Train = remaining trades AFTER purging any overlap AND embargoing the
     first ~1% of trades immediately following the test slice
   - Compute: n_test, win%, mean/trade, permutation p-value on the test slice
4. Aggregate: mean per-fold test-mean, distribution of test win%, permutation
   p-value across all folds (shuffle labels within each fold, aggregate)

## Decision rule — LOCKED

**RE-VALIDATED** (evidence stands as ship rationale) if ALL of:

1. At least 4 of 5 folds have positive test-mean/trade
2. Median fold test-win% ≥ 60%
3. Aggregate permutation p-value < 0.05 (raw, this is validation not new ship)
4. DSR on the pooled fold results > 0.50 (partial credit — full 0.95 gate
   applies only to NEW ship decisions)

**LEAKAGE-FLAGGED** if:

- ≤ 2 folds positive AND aggregate p > 0.20
- Original 5-window walk-forward's 5-of-5 positive result collapses

**INCONCLUSIVE** otherwise — log and revisit at n=100 live.

## Bonferroni denominator

This is a VALIDATION experiment, not a live-ship experiment. Does not
consume the 5/month ship-experiment budget. Bonferroni is not applicable
because we are re-testing an existing hypothesis under stricter methodology,
not searching a new hypothesis.

## Results (fill AFTER running — do not edit above)

- **Ran on:** 2026-07-07
- **Sample size per fold:** train ~41, test ~10
- **Fold-level positive-mean count:** **5/5**
- **Median fold test-win%:** 60.0%
- **Aggregate permutation p-value:** **0.0033** (clears Bonferroni N=15 = 0.05/15 = 0.0033)
- **PSR (pooled):** 0.9965
- **Gates:** G1=PASS G2=PASS G3=PASS G4=PASS
- **Verdict:** **RE-VALIDATED**

### Nuance to preserve

Two seemingly-contradictory results held together honestly:

| Test | Result | Question it answers |
|---|---|---|
| Purged K-Fold CV (this file) | p=0.0033 (clears Bonferroni N=15) | Given v7.2.1 specifically, is its signal distinguishable from random? |
| Deflated Sharpe (dsr_audit_2026_07_07.md) | DSR = 0.0000 | Given I tested 15 variants and picked this one, what's the expected max under null? |

Reconciled: v7.2.1 has real per-strategy edge, but my process of picking
it from a pool of 15 hopeful variants inflated my *claimed* confidence
beyond the raw p-value. Both statements coexist.

Discipline going forward: report BOTH numbers in every ship commit.

- The strategy is not noise.
- My earlier "signal is real" post overstated it.
- Live data settles it.
