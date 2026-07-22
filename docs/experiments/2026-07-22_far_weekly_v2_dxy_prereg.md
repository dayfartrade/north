# Pre-registration: FAR Weekly Gold Read v2 (DXY conditioning)

**Registered UTC:** 2026-07-22T13:00:00Z
**Owner:** Knox (autonomous under user product-design delegation)
**Trial id:** `far_weekly_gold_read_v2`
**Predecessor:** `far_weekly_gold_read_v1` (shipped 2026-07-22, live BETA)
**Reserved by:** v1 pre-reg § "Signal definition" — "DXY_chg is computed but
NOT used in the entry gate. Reserved as diagnostic for possible v2."

## Motivation

v1 uses only real yield conditioning (RY_chg). DXY (dollar index) is a
complementary macro variable — a rising dollar historically pressures
gold and vice versa. Adding DXY as an AND-gate could reduce false signals
during periods where real yields moved but the dollar didn't confirm.

**Hypothesis:** Requiring both RY_chg AND DXY_chg to point in the
signal-supportive direction produces higher-quality signals (higher
Sharpe, fewer trades) than v1's RY-only gate.

**Cost expected:** fewer trades (both filters must agree), so fewer
signals per year → longer time to reach any given n forward.
**Benefit expected:** cleaner directional bias, tighter drawdowns,
smoother equity curve.

## v2 signal definition (v1 + DXY constraint)

All v1 rules unchanged. Add ONE new AND-condition to entry:

- LONG requires ALL v1 LONG conditions PLUS: **DXY_chg < 0** (dollar falling)
- SHORT requires ALL v1 SHORT conditions PLUS: **DXY_chg > 0** (dollar rising)
- FLAT otherwise (expected to be MORE common than v1)

DXY_chg computed identically to RY_chg: 20-day change in DXY level.
Source: `data/macro/dxy_proxy__DTWEXBGS.csv` (FRED DTWEXBGS index).

## Position management (identical to v1)

- Entry: Monday 13:00 UTC open
- Stop: 2 × ATR(20 daily)
- Target: Friday 21:00 UTC close (time exit)
- Sizing: 1 contract fixed
- Cost model: $5 RT

## Sample split (fixed BEFORE any v2 backtest)

**Critical honesty note:** The 2010-2026 XAU/USD Dukascopy sample was fully
used by v1 (training + OOS + hold-out + supplementary OOS amendment). There
is no true out-of-sample gold data for v2 at this moment.

Therefore v2 gates are structured as:

- **Design comparison (2010-2026):** v2 backtest run on same 16-year sample
  as v1, PURELY as head-to-head comparison. This is NOT a ship gate — no
  claim of statistical significance from this run.
- **Forward validation (2026-07-22 onward):** v2 must produce at least 26
  weeks of forward paper-tracked results (~6 months) before any ship decision.
- **v2 live gate (when forward n ≥ 26):** v2 forward mean weekly return >
  v1 forward mean weekly return, AND both individually > 0.

## v2 comparison metrics (design-time, NOT ship gates)

Same v1 pre-reg gates applied to v2 for informational comparison:

| Metric | v1 (16yr) | v2 target |
|--------|-----------|-----------|
| Bootstrap 95% CI on mean weekly return | [+0.013%, +0.447%] | should tighten around a higher mean |
| PSR vs SR=0 | 0.9785 | ≥ 0.9785 (equal or better) |
| Win rate | 55.9% | ≥ 55% |
| Sharpe (ann) | 0.767 | ≥ 0.767 (should improve if DXY adds signal) |
| Positive years | 13 of 17 | ≥ 13 of 17 (equal or better) |
| Total trades | 363 | expected fewer (~200-300 with stricter filter) |

If v2 UNDERPERFORMS v1 on 16-year sample, do NOT ship v2 — the DXY
constraint doesn't add value and creates a smaller signal for no gain.
If v2 OUTPERFORMS on retrospective sample but by small margin, defer
ship decision to forward validation.

## Reject gates

- v2 win rate < 50% on 16yr sample → retire, do not proceed to forward
- v2 total P&L < 50% of v1's total → retire (too much signal lost)
- v2 Sharpe < 0.5 on 16yr sample → retire
- v2 has fewer than 100 trades on 16yr sample → retire (over-filtered)

## Interaction with v1

- v1 continues running on VPS timer as the shipped BETA product.
- v2 runs as a SHADOW candidate in parallel — computes signal but does
  NOT publish publicly during forward validation.
- After 6 months forward: if v2 forward > v1 forward AND both > 0, propose
  v2 as v1.1 upgrade with public announcement and clear track-record split.
- If v1 fails 12-month retirement gate, v2 can be evaluated as replacement
  candidate with fresh disclosure.

## Compliance with framework

- **Pre-registration:** ✅ this doc (before any v2 backtest)
- **No parameter tuning:** DXY_chg lag = 20 (identical to RY_chg lag)
- **Sample honesty:** design-time 16yr comparison is NOT a ship gate
- **Forward validation required:** 26 weeks minimum before any ship decision
- **Bonferroni-N:** registry increments; DSR/PSR recomputed as needed

## Registry update

Added to `data/experiments/registry.json` as `far_weekly_gold_read_v2` trial
entry with verdict `pre_registered`.

## Live effect

**None during pre-reg + design phase.** v2 will run only as a shadow
comparison until forward validation completes (~2027-01-22). v1 remains
the sole public product.
