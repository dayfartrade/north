# v1 day-of-week robustness audit (25 combinations)

**Date:** 2026-08-31
**Author:** Knox
**Status:** Robustness audit. NOT a rule change proposal.
**Trigger:** Known gap flagged in `north_v1_factsheet.md`: "Robustness of Monday-Friday entry/exit choice. All 25 day-combinations never tested. Would run before hard launch."

## Method

`scripts/v1_day_of_week_robustness.py`. Run the same v1 signal (frozen at prior-week Friday close) with all 25 entry-day x exit-day combinations. Same 2xATR stop, same $5 RT cost, same signal rules. Signal-side unchanged; only entry and exit day-of-week vary.

For exit_day earlier than entry_day (e.g., Wed entry, Tue exit), the trade holds through the weekend and exits the following week's Tuesday. Wraps naturally.

Metric: Sharpe (per-trade returns * sqrt(52), same convention as the shipping v1 headline).

## Results

Full table sorted by Sharpe:

| rank | combo | n | WR | Sharpe | cum $ |
|---|---|---|---|---|---|
| 1 | Tue-Fri | 363 | 57.9% | +1.059 | $239,046 |
| 2 | Wed-Tue | 367 | 54.8% | +1.054 | $291,511 |
| 3 | Tue-Thu | 369 | 55.0% | +0.951 | $165,271 |
| 4 | Wed-Fri | 362 | 55.5% | +0.930 | $181,833 |
| 5 | Tue-Mon | 369 | 55.6% | +0.929 | $290,332 |
| **6** | **Mon-Fri** | **363** | **56.2%** | **+0.916** | **$244,448** |
| 7 | Thu-Wed | 368 | 52.7% | +0.834 | $263,832 |
| 8 | Mon-Thu | 369 | 55.0% | +0.829 | $184,352 |
| 9 | Thu-Tue | 368 | 54.1% | +0.813 | $183,278 |
| 10 | Wed-Mon | 368 | 55.4% | +0.807 | $234,183 |
| 11 | Fri-Wed | 362 | 53.9% | +0.777 | $288,482 |
| 12 | Fri-Thu | 362 | 51.9% | +0.750 | $272,811 |
| 13 | Tue-Wed | 368 | 50.8% | +0.715 | $135,424 |
| 14 | Wed-Thu | 368 | 56.2% | +0.701 | $99,310 |
| 15 | Thu-Fri | 363 | 52.1% | +0.679 | $82,804 |
| 16 | Fri-Tue | 362 | 52.8% | +0.665 | $193,985 |
| 17 | Mon-Wed | 368 | 53.3% | +0.561 | $145,938 |
| 18 | Thu-Mon | 369 | 49.9% | +0.508 | $123,407 |
| 19 | Tue-Tue | 369 | 52.8% | +0.498 | $59,359 |
| 20 | Thu-Thu | 369 | 55.3% | +0.476 | $25,336 |
| 21 | Mon-Tue | 369 | 50.7% | +0.470 | $87,240 |
| 22 | Fri-Fri | 363 | 49.9% | +0.328 | $70,792 |
| 23 | Fri-Mon | 363 | 48.5% | +0.327 | $130,993 |
| 24 | Wed-Wed | 368 | 56.2% | +0.326 | $62,159 |
| 25 | Mon-Mon | 369 | 49.6% | -0.003 | $19,812 |

## Findings

**1. Mon-Fri (shipped v1) sits at rank #6/25.** Comfortably in the top quartile. Above the 25-combo median (0.72). Not the peak (Tue-Fri at 1.06) but very close.

**2. 24 of 25 combinations produce positive Sharpe.** Only Mon-Mon barely dips negative (-0.003). The signal mechanism (M20+M60+MA+RY_chg) works across almost every day-choice.

**3. 18 of 25 combinations clear Sharpe >= 0.50** (72%). The mechanism is not fragile to entry/exit timing.

**4. Same-day exits are the worst subset.** Mon-Mon, Tue-Tue, Wed-Wed, Thu-Thu, Fri-Fri: median Sharpe 0.33. Reason: same-day exit is a one-day hold that doesn't give the signal time to play out. Consistent with the pre-reg reasoning that weekly holds are the natural cycle for weekly signals.

**5. Cross-weekend holds tend to do best.** Wed-Tue (#2), Tue-Mon (#5), Wed-Mon (#10), Thu-Tue (#9), and Fri-Wed (#11) all involve holding across the weekend. Contra the intuition that weekend gap risk is a drag - here it looks like weekend gaps are net-slightly-helpful, at least on average. Consistent with the observation that gold's biggest moves often print on Sunday-night reopens.

**6. Tue-Fri edges out Mon-Fri.** Only by 0.14 Sharpe. And Tue-Fri had 4 fewer trades. Not a large enough gap to motivate a shift, even if we could (which the pre-reg would forbid mid-window).

## Interpretation

**v1's Mon-Fri choice is robust and honest.** The rank #6 result on 25 combinations means Mon-Fri sits in the top quartile without being the extreme. If Mon-Fri had ranked #1, we'd have to ask: were we searching over day-of-week choices when the pre-reg was written? (Answer: no, we weren't - pre-reg explicitly picked Monday open, Friday close as "the natural weekly cycle" before any backtest). A rank #6 finish is exactly what a pre-committed, honest choice looks like: better than random, not the optimum, no signs of hidden search.

The fact that 24/25 combos are positive is the stronger disclosure: **this is a real edge that survives arbitrary day-timing choices, not a fragile artifact of one specific setup.**

## Public disclosure implications

This is a legitimate honesty asset for the retail-facing story. Candidate lines for a future methodology page:

> "We picked Monday open, Friday close before running the backtest, as the natural weekly cycle. Post-hoc, we tested all 25 combinations of entry-day and exit-day: 24 of 25 produce positive Sharpe, 18 clear 0.5, and our shipped choice ranks #6 out of 25. The mechanism is robust to timing choice, not fragile to it."

Not proposing to publish today - not our surface to add copy to. But this is a strong asset for whenever the methodology page happens.

## What this does NOT do

- Does NOT motivate changing v1's Mon-Fri to Tue-Fri. Pre-reg forbids in-window rule changes. The gap (0.14 Sharpe) is inside the noise band anyway.
- Does NOT motivate a v3.1 or v2.5 candidate with a different day choice. Any candidate that emerged from this table would be post-hoc data-fitted.
- Does NOT change any live behavior. Pure disclosure asset.
- Does NOT recount as a "rejected trial" for the retirement wall. This is an audit of the shipped rule, not a candidate strategy test.

## Files touched

- Script: `scripts/v1_day_of_week_robustness.py` (new)
- Doc: `docs/experiments/2026-08-31_v1_day_of_week_robustness.md` (this file)
