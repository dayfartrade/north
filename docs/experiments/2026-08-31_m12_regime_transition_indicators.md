# M12 regime-transition leading indicators

**Date:** 2026-08-31
**Author:** Knox
**Status:** Exploratory analysis. Follow-up #1 from `2026-08-31_m12_regime_persistence.md`.
**Trigger:** Question - do any macro features predict M12 sign flips in the 30-60 days BEFORE they happen? If yes, we could add an early-warning signal.

## Method

`scripts/m12_transition_indicators.py`. For each M12 flip in the 16-year sample, snapshot macro state 30 and 60 trading days before the flip. Compare to a control sample of 200 mid-regime dates (where M12 direction was stable for 30 days on either side).

Features: DXY level and 20d change, real-yield level and 20d change, gold's own M20 (near-term momentum), gold ATR%, gold M12 magnitude (how close to zero already).

Filter to "meaningful" flips: only count if the streak that ended was >= 20 days. Otherwise we're measuring single-day whipsaws which are noise.

## Results

**100 total M12 flips detected in the sample.** After filtering to streaks >= 20 days: **26 meaningful flips** (11 LONG->SHORT bull endings, 15 SHORT->LONG bull starts).

### 60 trading days BEFORE any meaningful flip vs steady-state

| feature | pre-flip median (n=26) | steady median (n=200) | diff |
|---|---|---|---|
| DXY_chg_20d | +0.50 | -0.04 | **+0.54** |
| RY level | 0.41% | 0.60% | -0.19% |
| RY_chg_20d | -0.010 | +0.010 | -0.020 |
| gold_M20 | +0.55% | +0.58% | ~0 |
| gold_ATR_pct | 1.25% | 1.42% | -0.17 |
| gold_M12_abs | 6.9% | 18.6% | **-11.7pp** |

### 60 days BEFORE bull-ending (LONG->SHORT) flips only (n=11)

| feature | pre-flip median | steady median | diff |
|---|---|---|---|
| DXY_chg_20d | -0.25 | -0.04 | -0.21 |
| **RY level** | **-0.08%** | **+0.60%** | **-0.68pp** |
| RY_chg_20d | -0.06 | +0.01 | -0.07 |
| gold_ATR_pct | 1.26% | 1.42% | -0.16 |

## Findings

**1. Gold's own M12 magnitude is close to zero 60 days before a flip.** This is mechanical, not a leading signal - M12 has to approach zero to cross. Discount as informative.

**2. Real-yield LEVEL is different in pre-flip vs steady-state windows.** Across all meaningful flips (n=26), RY level 60d before is 0.41% vs 0.60% in steady state. In LONG-ending flips specifically, RY level is **NEGATIVE** (-0.08%) 60 days before the bull ends, vs +0.60% in steady state. Interpretation: gold bulls tend to end when real yields have already dropped into negative territory (macro tailwind exhausted; nothing left to fuel further rally).

**3. DXY momentum (20d change) is elevated pre-flip overall (+0.50 vs -0.04) but NEGATIVE pre-flip in LONG-ending subset (-0.25).** This is muddled by the direction of flip. In LONG->SHORT flips (bull ending), the dollar is still weakening (as it typically is late in a gold bull). In SHORT->LONG flips (bear ending), the dollar has been strengthening for weeks and is topping out. Aggregating both loses signal.

**4. Sample is tiny.** 11 LONG-ending flips and 15 SHORT-ending flips over 16 years. Any single flip can shift medians materially. Findings are directional, not statistical.

## Convergence with today's other findings

Two independent analyses today surfaced the same feature:

- **v2-skipped predictor probe** found that v2-skipped v1 losers cluster at low absolute real-yield levels (median 0.12%).
- **This analysis** found that gold LONG regimes tend to end when real yields are at or below zero (median -0.08% at 60d pre-flip in LONG->SHORT flips).

Both point to: **the absolute LEVEL of the US 10-year real yield conveys signal about when gold's macro backdrop is exhausted.** This is a coherent finding, not an artifact of one analysis.

## What this seeds (already drafted)

The v3 pre-reg (`docs/experiments/2026-08-31_far_weekly_v3_ry_level_prereg.md`) adds an RY_level floor to v2's rule. Thresholds locked BEFORE any v3 backtest. Split-sample train/OOS, then forward validation. No live effect until v2's shadow window closes in early 2027.

## What NOT to do

- Do not use these numbers to time regime flips live. n=11 to 26 is very small; the medians could shift materially with new data.
- Do not build a regime-detector product on top of these findings. Not enough sample, not enough independent validation.
- Do not modify v1, v2, or the ensemble based on this. All three are on pre-registered paths; changing rules mid-window invalidates the comparison.

## Files touched

- Script: `scripts/m12_transition_indicators.py` (new)
- Doc: `docs/experiments/2026-08-31_m12_regime_transition_indicators.md` (this file)
