# Experiment: meta_labeling_v72_1

**Registered UTC:** 2026-07-08T00:15:00Z
**Blinded until:** results computed same session
**Layer:** session_config (would gate PLAN dispatches if promoted)
**Owner:** Knox

## Hypothesis

A minimal-feature meta-labeler (López de Prado Ch 3.6-3.7) trained on the
v7.2.1 shipped trades (n=52) can act as a soft filter that:
1. Raises OOS win-rate by ≥ 5pp vs baseline (69.2% → 74.2%)
2. Preserves OOS mean/trade at baseline + ≥ $100
3. Keeps at least 60% of trades (else filter too aggressive to be viable)

If it clears all three, we have evidence a secondary classifier extracts
signal from the primary v7.2.1 PLAN. If it fails any, meta-labeling on
this sample is not viable.

## Rationale

v7.2.1 shipped with n=52 trades. Adding gate features by hand (v7.1's OR/ATR
dead-zone, v7.2's tp_mult adjustments) got us from ~57% to 69.2% win-rate.
The natural next step is a supervised classifier that learns non-linear
combinations of features, per LdP Ch 3.

n=52 is the ceiling for now. We CANNOT train more features than the sample
supports without gross overfitting. So the feature set is deliberately
capped at 3:

- session (categorical, 3 levels)
- or_atr_ratio (OR range / ATR at OR-close)
- trend_slope (EMA50 slope at OR-close, absolute value)

With one-hot encoding for session, that's 5 free parameters in a logistic
regression. n=52 gives ~10 samples per parameter — the minimum defensible
ratio at this sample size.

## Data

- **Window:** 2026-04-13 → 2026-07-01 (v7.2.1 sample as shipped, n=52)
- **CV split:** 5-fold Purged K-Fold with 1% embargo (matches the earlier
  purged_walkforward_revalidation methodology)
- **Model:** scikit-learn LogisticRegression, C=1.0 (default), no class balancing
- **Prediction threshold:** 0.5 (calibrated on train fold, applied to test fold)

## Method

1. Collect v7.2.1 trades via `run_orb_v7` per SESSION_CONFIG (same path as
   the DSR audit + purged K-fold revalidation used).
2. Build features: session (one-hot), or_atr_ratio, trend_slope (abs).
3. Label: 1 if net_pnl > 0, else 0.
4. Purged 5-fold CV: for each fold, fit logistic on train trades (n≈41),
   predict on test trades (n≈10). Aggregate predictions.
5. Compute on aggregated OOS predictions:
   - kept_win_rate = win% among trades where predict = 1
   - kept_mean_pnl = mean net_pnl among kept trades
   - keep_fraction = fraction of all trades where predict = 1
6. Compute DSR on kept-trade net_pnl series against N=17 (registry).

## Decision rule — LOCKED

**SHIPPABLE-SIGNAL** if ALL:
1. Aggregate OOS kept-trade win-rate ≥ **74.2%** (baseline 69.2% + 5pp)
2. Aggregate OOS kept-trade mean/trade ≥ **$912** (baseline $812 + $100)
3. Keep fraction ≥ **60%** (n≥31 of 52 kept)
4. DSR against N=17, V=0.5 > **0.50** (partial credit — NOT a ship gate)

If SHIPPABLE-SIGNAL, the next step is NOT auto-ship. It's:
  - Save the trained model artifact
  - Register as shadow-mode candidate (like vol_ratio_ge_1_0)
  - Collect n≥50 live shadow decisions before promoting to live gate
  - Full DSR>0.95 gate required for live promotion

**REJECT** if:
- Any of 1, 2, 3 fails AND kept_mean_pnl < baseline mean ($812)

**INCONCLUSIVE** otherwise (some gates pass, filter isn't clearly harmful
or clearly helpful).

## Bonferroni denominator

This IS a new-hypothesis experiment. Increments N: 16 → 17. Recorded in
`data/experiments/registry.json` regardless of outcome (Marcos's Third Law).

## Overfit-risk mitigation

- Feature count capped at 3 (5 parameters after one-hot).
- Logistic regression only (no non-linear model families tried).
- Purged K-fold with embargo (defeats serial-correlation leakage).
- Decision threshold FIXED at 0.5 — no per-fold threshold optimization.
- Pre-registration written and committed BEFORE any fit is run.
- DSR reported against honest N.

## Results (fill AFTER running — do not edit above)

- **Ran on:** 2026-07-08
- **Sample size:** n=52
- **Kept fraction:** _fill_ (need ≥ 60%)
- **Kept-trade OOS win-rate:** _fill_% (need ≥ 74.2%)
- **Kept-trade OOS mean/trade:** $_fill_ (need ≥ $912)
- **Baseline win-rate:** 69.2%
- **Baseline mean/trade:** $812
- **DSR against N=17, V=0.5:** _fill_ (partial gate: > 0.50)
- **Gates:** G1=_ G2=_ G3=_ G4=_
- **Verdict:** _fill_

### Notes to preserve honestly

_(fill during analysis — reasons if gates failed, feature coefficients,
anything the future me will want to see when re-reading this file)_
