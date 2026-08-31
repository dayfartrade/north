# Pre-registration: FAR Weekly Gold Read v3 (v2 + real-yield-level floor)

**Registered UTC:** 2026-08-31T18:00:00Z
**Owner:** Knox (autonomous under user product-design delegation)
**Trial id:** `far_weekly_gold_read_v3`
**Predecessor:** `far_weekly_gold_read_v2` (shadow, pre-reg 2026-07-22, forward window ends 2027-01-22)
**Status:** DRAFT - pre-registered but NOT yet backtested. All thresholds specified BEFORE any v3 backtest run to prevent post-hoc fitting.

## Motivation

Today's fire-rate analysis (`docs/experiments/2026-08-31_v1_fire_rate_by_v2.md`) established that v1's entire alpha lives in the v2-confirmed subset, and the v2-skipped subset loses money in aggregate (Sharpe -0.14, cum -$8,538 over 16 years). v2's DXY filter is doing exactly one job: dropping the low-quality quarter of v1 firings.

The follow-on predictor probe (`docs/experiments/2026-08-31_v2_skipped_predictor_probe.md`) found that within the v2-skipped subset, the losers cluster at LOW absolute real-yield levels (median 0.12% vs 0.32% for winners; 60% lower than v2-confirmed trades overall).

The regime-transition indicator analysis (`docs/experiments/2026-08-31_m12_regime_transition_indicators.md`) independently found that gold LONG regimes tend to end at negative real yields (median -0.08% at flip points vs +0.60% steady state).

Two independent analyses point to the same feature: **the absolute LEVEL of the US 10-year real yield conveys signal about when v1 firings are lower quality.** v3 tests whether adding a real-yield-level floor to v2 improves the strategy.

**Hypothesis:** Requiring v2's DXY-aligned signal AND the real-yield level to be above a threshold produces higher-quality signals than v2 alone.

## v3 signal definition (v2 + RY_level floor)

All v2 rules unchanged. Add ONE new AND-condition to entry:

- LONG requires ALL v2 LONG conditions PLUS: **RY_level >= 0.25%** (real yield not deeply negative)
- SHORT requires ALL v2 SHORT conditions PLUS: **RY_level <= 1.50%** (not in a hostile-to-gold rate regime for a short; this is a symmetric filter, but the SHORT case is where the level should NOT be excessive on the other side)
- FLAT otherwise

**Threshold rationale (LOCKED before any v3 backtest):**

- **0.25% LONG floor:** halfway between the v2-skipped losers' median (0.12%) and the v2-skipped winners' median (0.32%). Not at the winners' median (would drop too many valid LONGs), not at zero (wouldn't filter enough).
- **1.50% SHORT ceiling:** roughly 3x the v2-confirmed median level (0.58%). A wide ceiling that would rarely bind but exists for symmetry. Rationale: gold SHORTs work best when rates are moving up FROM a moderate level, not when rates are already extreme.

Both thresholds specified NOW, BEFORE any v3 backtest. No sweep, no optimization. If they don't work, v3 rejects and we go back to v2.

`RY_level` = `data/macro/real_yield_10y__DFII10.csv` value on signal_date (last available bar, same as RY_chg uses).

## Position management (identical to v1 and v2)

- Entry: Monday 13:00 UTC open
- Stop: 2 x ATR(20 daily)
- Target: Friday 21:00 UTC close (time exit)
- Sizing: 1 contract fixed
- Cost model: $5 RT

## Sample split (fixed BEFORE any v3 backtest)

**Critical honesty note:** The 2010-2026 XAU/USD Dukascopy sample has been used extensively by both v1 and v2 pre-regs. There is no true out-of-sample gold data for v3 at this moment. The features used (RY_level) were surfaced by post-hoc analysis of the 2010-2026 sample today.

Therefore v3 gates are structured as:

- **Split-sample validation (retrospective):** TRAIN 2010-2018 vs OOS 2019-2026. Compute Sharpe/WR/cum on each split. OOS must clear the gates below without any threshold adjustment from the TRAIN.
- **Forward validation (2027-01-22 onward):** v3 requires 26 weeks of forward paper-tracked results BEFORE any ship decision. Starts once the v2 forward window closes to avoid conflating decisions.
- **v3 live gate (when forward n >= 26):** v3 forward mean weekly return > v2 forward mean weekly return, AND v3 forward Sharpe > v2 forward Sharpe.

## v3 comparison metrics (design-time, NOT ship gates)

Same v2 comparison structure. If v3 beats v2 on the split-sample retrospective, proceed to forward paper. If v3 UNDERPERFORMS v2 on either train or OOS, v3 rejects immediately (do not enter forward validation).

| Metric | v1 (16yr) | v2 (16yr, retrospective) | v3 target |
|---|---|---|---|
| Sharpe (per-trade x sqrt(52)) | 0.77 | 1.04 | >= 1.04 on OOS 2019-2026 |
| Win rate | 55.9% | 58.5% | >= 58% on OOS |
| Total P&L | +$181k | +$187k | >= v2's P&L on OOS |
| Trade count | 363 | 270 | expected 200-250 (further filter) |
| M12 LONG regime Sharpe | 0.67 | 0.91 | >= 0.91 |
| M12 SHORT regime Sharpe | 0.77 | 1.09 | >= 1.09 |

## Reject gates (any single fail retires v3)

- v3 OOS Sharpe < v2 OOS Sharpe -> reject (RY_level filter doesn't add value)
- v3 total P&L < 80% of v2's on OOS -> reject (too much signal lost for the filter cost)
- v3 has fewer than 100 trades on 16yr sample -> reject (over-filtered)
- v3 TRAIN and OOS Sharpes differ by more than 50% -> reject (filter looks train-specific)
- Post-hoc threshold tweak needed to pass any gate -> HARD REJECT (indicates the filter was fit, not discovered)

## Interaction with v1 and v2

- v1 continues running on the workflow timer as the shipped BETA product.
- v2 continues running as SHADOW through 2027-01-22 per its own pre-reg.
- v3 runs as SHADOW ONLY starting whenever v2's forward window closes. Does NOT compete with v2's shadow window (avoid conflating variables).
- After v3's 6-month forward window: if v3 forward beats v2 forward, propose v3 as v2.1 upgrade with public disclosure and clear track-record split.
- If v2 ships as the live product before v3's forward window opens (based on v2's own gates), v3's baseline moves from v2-shadow to v2-live for comparison.

## Compliance with framework

- **Pre-registration:** this doc (BEFORE any v3 backtest)
- **No parameter tuning:** RY_level thresholds (0.25% floor, 1.50% ceiling) fixed here.
- **Sample honesty:** design-time 16yr comparison used only after split-sample validation
- **Forward validation required:** 26 weeks minimum before any ship decision
- **Bonferroni-N:** registry increments. The RY_level feature was surfaced from probing 6 features (M20 magnitude, M60 magnitude, MA spread, ATR%, RY_chg magnitude, RY_level). Bonferroni-N is 6 for the v3 gate; adjust p-values accordingly on forward test if computed.
- **Data-snoop caveat noted:** the threshold values were informed by looking at the same 16-year sample that will be split for train/OOS. Split-sample validation is a partial defense but not perfect. The forward window is the honest gate.

## Registry update

Will add to `data/experiments/registry.json` as `far_weekly_gold_read_v3` with verdict `pre_registered`. NOT yet added; commit this pre-reg first, then update registry in the same session or later once the pre-reg is reviewed.

## Live effect

**None.** v3 is pre-registered only. No shadow logging until v2's forward window closes (2027-01-22) or v2 rejects earlier. No live effect on the shipped v1 product.

## What this pre-reg does NOT do

- Does not modify v1 or v2 rules. v1 and v2 continue on their pre-registered paths.
- Does not commit us to build v3. If the retrospective split-sample test fails, v3 rejects and we move on. The value of the pre-reg is protecting us from post-hoc reasoning if we ever DO run the backtest.
- Does not propose a shipping timeline. v3 is a 2027 conversation at earliest.

## Files

- Pre-reg: `docs/experiments/2026-08-31_far_weekly_v3_ry_level_prereg.md` (this file)
- Supporting analyses:
  - `docs/experiments/2026-08-31_v1_fire_rate_by_v2.md`
  - `docs/experiments/2026-08-31_v2_skipped_predictor_probe.md`
  - `docs/experiments/2026-08-31_m12_regime_transition_indicators.md`
- Backtest script (to be written when v3 is actually evaluated): would live at `scripts/far_weekly_gold_read_v3.py`, mirror `scripts/far_weekly_v2_backtest.py`
