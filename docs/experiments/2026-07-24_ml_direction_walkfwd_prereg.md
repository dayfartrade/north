# Pre-registration: FAR Weekly Gold ML Direction (walk-forward CV) v1

**Registered UTC:** 2026-07-24T11:45:00Z
**Owner:** Knox (autonomous under user product-design delegation)
**Trial id:** `far_weekly_gold_ml_direction_v1`
**Related:** meta-labeling (rejected 2026-07-22, different setup)
**Enabled by:** all D-track data (COT + GVZ + FOMC) now available

## Motivation

Options-selling rejected. Cross-asset transfer rejected. Contrarian positioning rejected. Seasonality rejected. Remaining mechanism family from user's original brief: **ML with strict CV.**

Prior meta-labeling (`far_weekly_meta_labeling_v1`, rejected 2026-07-22) used features to predict WHICH FAR Weekly v1 signals to skip. This is different: **predict raw next-week direction from features**, no dependency on v1's momentum+macro rule.

**Hypothesis:** A simple linear model over a fixed feature set with strict walk-forward CV can predict gold weekly direction better than random.

## Feature set (fixed pre-reg — no additions)

Computed at Sunday close, used to predict next week's LONG/SHORT/FLAT:

1. **M20**: 20-day return on gold daily close
2. **M60**: 60-day return on gold daily close
3. **ATR_pct**: 20-day ATR / current price
4. **MA_ratio**: MA10 / MA40 (short/long moving average ratio)
5. **RY_chg**: 20-business-day change in 10y real yield
6. **DXY_chg**: 20-business-day change in DXY
7. **GVZ_z**: 30-day z-score of GVZ (implied vol regime)
8. **nc_z**: 52-week z-score of COT nc_net (positioning)

All features are known on Sunday (COT publishes Friday for Tuesday snapshot).

## Model (fixed pre-reg — no changes)

- **Model class:** Logistic Regression (scikit-learn default with L2)
- **Target:** binary label `1 if next_week_return > 0 else 0`
- **Preprocessing:** StandardScaler (fit only on training fold, applied to test)
- **Threshold:**
  - LONG if predicted P(up) > 0.55
  - SHORT if predicted P(up) < 0.45
  - FLAT otherwise

## Walk-forward CV protocol

- **Initial training window:** 2011-01-01 to 2018-12-31 (~8 years, ~416 weeks)
- **Test folds:** 26-week rolling test windows from 2019-01-01 to 2026-06-30 (15 folds)
- **Re-fit cadence:** every 26 weeks, model re-trained on ALL data up to fold start (expanding window)
- **No look-ahead:** feature at week t uses only data available Sunday of week t

## Position management (identical to FAR Weekly v1)

- Entry: Monday 13:00 UTC open
- Stop: 2 × ATR(20 daily)
- Target: Friday 21:00 UTC close (time exit)
- Sizing: 1 GC contract (100 oz)
- Cost: $5 RT

## Sample split (fixed BEFORE any backtest)

- **Training (walk-forward expanding):** 2011-2018 initial, extended each fold
- **OOS (15 folds × 26 weeks):** 2019-01-01 to 2026-06-30 (~7.5 years)
- **Hold-out:** live from 2026-07-24 (min 26 weeks before ship)

**Honesty note:** Gold price + all features are on the same "seen" 2010-2026 window. But this specific ML model + walk-forward protocol has never been fit or evaluated. First-time evaluation.

## Ship gates (all must pass on OOS 2019-2026)

| # | Gate | Threshold | Rationale |
|---|------|-----------|-----------|
| 1 | OOS Sharpe (ann) | ≥ 0.60 | Match FAR Weekly v1 |
| 2 | OOS win rate | ≥ 55% | Directional edge |
| 3 | OOS total P&L | > 0 | Profitability |
| 4 | OOS PSR vs SR=0 | ≥ 0.90 | Statistical significance |
| 5 | OOS n | ≥ 100 | Statistical power |
| 6 | Positive-Sharpe folds | ≥ 8 of 15 | Regime robustness |
| 7 | Fold Sharpe worst-case | ≥ -1.0 | No catastrophic fold |

## Reject gates

- OOS Sharpe negative → REJECTED
- ANY fold Sharpe < -1.5 → REJECTED (extreme regime breakdown)
- FLAT rate > 80% → REJECTED (over-conservative model)
- FLAT rate < 20% → REJECTED (over-aggressive, no calibration)

## Live effect

**None during backtest.** If ship gates pass:
- Register `shadow_beta`
- Add ML-direction card to weekly.html (parallel to FAR Weekly v1)
- Weekly publisher runs ML inference at Sunday 22:00 UTC
- Disclose model class, feature set, walk-forward metrics, non-obvious risks

If rejected:
- Verdict `rejected_ship_gates`
- Add rejection memory
- Do NOT rescue with hyperparameter tuning (curve fit)
- Do NOT try non-linear model (that would be a fresh pre-reg)

## Bonferroni-adjusted DSR

Registry N post-registration: 41 trials.

## Compliance

- **Pre-registration:** ✅ this doc, before backtest
- **Model class fixed:** logistic regression only, no XGBoost/RF/NN tuning
- **Features fixed:** 8 specified above, no additions/removals
- **Thresholds fixed:** 0.55 / 0.45 (not tunable post-hoc)
- **CV protocol fixed:** 26-week walk-forward, expanding window
- **Registry:** entry created before backtest
