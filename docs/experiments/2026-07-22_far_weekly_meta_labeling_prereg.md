# Pre-registration: FAR Weekly meta-labeling filter (Prado AFML Ch 3.6)

**Registered UTC:** 2026-07-22T14:30:00Z
**Owner:** Knox
**Trial id:** `far_weekly_meta_labeling_v1`
**Predecessors:** `far_weekly_gold_read_v1` (live BETA), `far_weekly_gold_read_v2` (DXY, pre-reg shadow)
**Method source:** López de Prado, "Advances in Financial Machine Learning" (2018), Ch 3.6 "Meta-Labeling"

## Motivation

FAR Weekly failure analysis (2026-07-22) established that 4 of 17 backtest
years were losing, with 2017 (-$13k) and 2023 (-$14k) being the worst.
Mechanism: gold rallies but the signal takes LONGs at local peaks that pull
back and hit 2×ATR stops before mean-reverting. The direction is correct;
the entry timing pays for false starts.

Meta-labeling (Prado 3.6) directly addresses this. The primary model
(FAR Weekly signal) sets the SIDE (LONG/SHORT/FLAT). A secondary binary
ML classifier decides SIZE ({0, 1} — pass or take). Trained on features
that capture volatility regime, trend position, and cross-asset context.

**Hypothesis:** A meta-labeling filter on top of FAR Weekly non-FLAT signals
can identify high-confidence trades and pass on low-confidence ones,
improving win rate and Sharpe without changing the primary model.

## Structural advantage: FAR Weekly is IID-friendly

Weekly hold (Mon 13:00 UTC → Fri 21:00 UTC) means observations don't
temporally overlap (Prado Ch 4). The IID assumption that ML methods
require is closer to valid here than for higher-frequency signals.
No `mpNumCoEvents` uniqueness-weighting needed.

## Data setup (frozen)

- **Primary signals used:** v1 (RY-only) — 363 non-FLAT weeks over 2010-2026
- **Target definition:** binary, per Prado 3.6 getBins:
  - `y = 1` iff `net_pnl > 0` (winning week)
  - `y = 0` iff `net_pnl ≤ 0` (losing or flat week)
- **Sample split:**
  - TRAINING: 2010-2020 (11 years, ~200 signals)
  - HOLD-OUT: 2021-2026 (5.5 years, ~163 signals)
- Cross-validation for training set: standard 5-fold. Since weekly hold has
  no observation overlap, no purged-K-fold needed (verified by design).

## Features (pre-committed, no post-hoc addition)

All computed on data available AT the Friday close signal date (no lookahead):

**Signal-magnitude features (4):**
1. `abs_M20` — absolute value of 4-week momentum (strength of signal)
2. `abs_M60` — absolute value of 12-week momentum
3. `MA_dist_pct` — (MA10 − MA40) / MA40 (normalized MA gap)
4. `abs_RY_chg` — absolute 20-day change in real yield (bps)

**Volatility features (2):**
5. `ATR_pct` — ATR(20d) / close (normalized daily-vol)
6. `ATR_ratio` — ATR(20d) / ATR(60d) (recent vs long vol)

**Trend-position features (2):**
7. `close_vs_MA40` — (close / MA40) − 1
8. `pos_in_20d_range` — (close − min_20d) / (max_20d − min_20d)

**Macro features (3):**
9. `DXY_chg_20d` — 20-day DXY change (raw, signed)
10. `RY_level` — current 10y real yield level (not change)
11. `RY_chg_60d` — 60-day real yield change (longer memory than 20d signal)

**Cross-asset features (2):**
12. `gold_oil_ratio` — gold / WTI ratio (from Dukascopy WTI data)
13. `gold_oil_ratio_chg_20d` — 20-day change in that ratio

**Direction encoding (2):**
14. `primary_direction_long` — 1 if primary=LONG else 0
15. `primary_direction_short` — 1 if primary=SHORT else 0

Total: **15 features**. Fixed. Any feature that fails to compute for a signal
row causes that row to be dropped (documented).

## Model (fixed hyperparameters, no tuning)

- **Classifier:** RandomForestClassifier (scikit-learn)
- **n_estimators:** 100 (sklearn default)
- **max_depth:** None (default — grow to purity)
- **min_samples_leaf:** 3 (slight regularization to prevent memorization
  of individual trades)
- **class_weight:** "balanced" (base rate ~55% is close to balanced but
  we want the classifier to prioritize precision over recall)
- **random_state:** 42 (reproducibility)
- **Threshold:** default 0.5 for take/pass decision. NO threshold tuning.

## Decision rule

For each hold-out non-FLAT signal:
- Compute features
- Predict probability of profit p̂
- If p̂ > 0.5: **TAKE** the trade (identical position mgmt as v1)
- If p̂ ≤ 0.5: **SKIP** the trade (filter to FLAT)

## Comparison metrics (all reported on hold-out 2021-2026)

Primary comparison: **filtered strategy** vs **baseline v1**

| Metric | v1 baseline | Meta-labeled target |
|--------|-------------|---------------------|
| Win rate | actual | ≥ v1 |
| Mean weekly return | actual | ≥ v1 |
| Sharpe (ann) | actual | ≥ v1 (ideally +0.2 or more) |
| Number of trades | actual | ≤ v1 (should filter some) |

Also report: classifier precision/recall/F1 on hold-out.

## Ship gates (pre-reg discipline; do NOT weaken post-hoc)

For meta-labeling to be shipped as `v3` candidate:
1. Hold-out (2021-2026) filtered mean weekly return > baseline mean
2. Hold-out filtered win rate ≥ baseline WR
3. Hold-out filtered Sharpe ≥ baseline Sharpe + 0.2
4. Classifier precision on TAKE decisions ≥ 0.60 (60% of taken trades win)
5. At least 40 signals taken in hold-out (avoid over-filtering to noise)

## Reject gates

- Filtered mean weekly return ≤ 0 in hold-out
- Filtered Sharpe < baseline (meta-labeling makes things worse)
- Fewer than 20 trades taken (over-filter — signal too rare to be useful)
- Filtered win rate < baseline WR (classifier picking wrong signals)

## Live effect during pre-reg

**None.** Meta-labeling is a research candidate; no changes to live v1 or
shadow v2. If all ship gates pass on hold-out, formal v3 pre-reg follows
with fresh forward validation before any live promotion.

## Registry

Added to `data/experiments/registry.json` as `far_weekly_meta_labeling_v1`
trial, verdict `pre_registered_research`.
