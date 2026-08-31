# v2 accelerated-ship-gate amendment: consideration and rejection

**Date:** 2026-08-31
**Author:** Knox
**Status:** Consideration doc. Recommendation: DO NOT file the amendment.
**Trigger:** Today produced four independent lines of evidence that v2 is stronger than the original 2026-07-22 pre-reg anticipated. Question: does that justify amending the pre-reg to add an earlier ship gate?

## The temptation

The original v2 pre-reg (`docs/experiments/2026-07-22_far_weekly_v2_dxy_prereg.md`) specifies:
- 26-week forward window through 2027-01-22
- Single ship gate: v2 forward mean weekly return > v1 forward mean weekly return, AND both > 0

Since ship, four independent analyses have surfaced stronger evidence for v2:

1. **Fire-rate finding** (`docs/experiments/2026-08-31_v1_fire_rate_by_v2.md`): v1's entire alpha lives in the v2-confirmed subset. The v2-skipped subset cumulative $-8,538 over 16 years, negative Sharpe. v2 is not "a better v1" - it's "v1 minus the losing quarter."

2. **Cross-regime validation** (`docs/experiments/2026-08-31_m12_regime_split_ensemble.md`): v2 wins in both M12 regimes (LONG Sharpe 0.91 vs v1's 0.67; SHORT Sharpe 1.09 vs v1's 0.77). Not regime-conditional.

3. **Cross-asset validation** (`docs/experiments/2026-08-31_dxy_filter_cross_asset.md`): DXY-alignment mechanism improves Sharpe on silver (+90%) and SPX (+33%), not just gold. Portable macro filter.

4. **Vol-target compounding** (`docs/experiments/2026-08-31_vol_scaled_sizing_probe.md`): v2 with vol-target sizing reads Sharpe 1.24, cum/DD ratio 4.68x. Very strong tactical strategy.

Plus the live-check bonus: both live losers (2026-07-27 SHORT, 2026-08-24 LONG) were v2-skipped v1 trades. If v2 had shipped, live P&L would be 0% instead of -4.02%.

Given all this, a natural thought: **should we amend the pre-reg to allow earlier v2 ship?**

## The amendment we could write

Something like:

> **Amendment (proposed 2026-08-31):** In addition to the 26-week ship gate, v2 may ship EARLY if:
> - At least 8 directional v1 trades have resolved forward AND
> - v2 forward cumulative return exceeds v1 forward cumulative return by >2% AND
> - v2 forward Sharpe (annualized) exceeds v1 forward Sharpe by >0.20 AND
> - Bootstrap 95% CI on the v2-v1 forward difference clears zero

## Why we should NOT file this amendment

**Reason 1: All four supporting analyses are in-sample.**

The 2010-2026 Dukascopy sample was already used in:
- v1 pre-reg (training + OOS + hold-out + supplementary amendments)
- v2 pre-reg (design comparison, explicitly called "NOT a ship gate")
- Ensemble pre-reg (2019-2026 OOS)

Today's four analyses use the SAME 16-year sample:
- Fire-rate split: post-hoc partition of the 16yr sample
- Regime split: post-hoc partition of the 16yr sample
- Cross-asset: silver 2014-2026, SPX 2015-2023 - overlapping windows, same DXY series
- Vol-target: reweight of the 16yr sample

**Every single "stronger v2 case" argument comes from further slicing data v2 already had access to when its rule was designed.** The pre-reg's whole purpose is to guard against "we see something new, want to move fast." The evidence isn't new information from independent data; it's re-cuts of existing data.

**Reason 2: Live data (N=2) is directionally consistent but not informative.**

Both live losses were v2-skipped. That's suggestive. But N=2 has essentially zero statistical power. The probability of 2 out of 2 v1 losses being v2-skipped, if v2's skip rate is 25% and skips are random with respect to outcome, is 0.25^2 = 6.25%. Meaningful, but far from significance. Any statistical inference from N=2 is theater.

**Reason 3: The proposed amendment thresholds (8 trades, +2% return, +0.20 Sharpe) are eyeballed.**

I picked "n=8 for early ship" because it's roughly where a coin-flip test starts to have visible signal. That's a post-hoc threshold choice. Even the amendment itself has a data-fitting problem.

**Reason 4: The original pre-reg's 26-week window was chosen for a reason.**

The pre-reg document says: "v2 will run only as a shadow comparison until forward validation completes (~2027-01-22)." That "6 months" number wasn't picked to be maximally cautious - it was picked to give enough resolved directional trades (12-18 expected) that a t-test on the v1-v2 forward difference would have some power. Cutting to n=8 halves the sample and pushes the test into definitely-underpowered territory.

**Reason 5: The regime-persistence finding argues for MORE patience, not less.**

Today's analysis showed the current M12 LONG regime is unprecedented in the sample (868 days, longer than any prior by 337 days). Both v1 and v2 have been living inside one very stable regime. The pre-reg's 26 weeks all fall inside this regime. Shipping v2 early would mean shipping based on a single-regime forward test. Waiting to see the full window (or even longer, into a potential regime flip) gets us more informative data.

**Reason 6: The retirement wall counts on this discipline.**

NORTH's marketing story is "we show every failure. Every strategy pre-registered. Every ship gate honored." Amending an active pre-reg to add a permissive early-ship gate after the strategy has performed well in a shadow window is exactly the kind of move that erodes that story. Even if the amendment is defensible, it looks like "we found ways to ship v2 sooner because we like v2." That's a credibility cost that outweighs any speedup benefit.

**Reason 7: The cost of waiting is small.**

The 26-week window ends 2027-01-22. That's about 5 months away from today. During those 5 months:
- v1 continues to run and produce results
- v2 continues to shadow
- Both go into the same forward record
- Real-world data accumulates without any decision cost

The "cost of delayed ship" is theoretical (higher-Sharpe strategy could have made money in the interim). In practice, v1's own live record is fine and the intermediate months don't produce lost opportunity that matters.

## What we CAN do instead

Do everything short of amending the pre-reg:

1. **Track forward performance transparently.** After every resolved directional week, compute the forward v1 vs v2 delta and log it privately. Don't publish. Don't let it influence the shadow flow.
2. **Prepare the v2 elevation announcement in advance.** If v2 passes the 26-week gate, we can ship the same day the window closes because the ship-plan is already written. This has zero pre-reg cost.
3. **If v2 dominates dramatically before Jan 2027**, defer to Farhad. His call as product owner. Anything Knox does here is a recommendation, not a decision. But the recommendation is clear: honor the gate.
4. **Document today's four analyses as the "case for v2 elevation once the gate clears."** Not the case for accelerated ship - the case for ship at 2027-01-22.

## What triggers reconsideration

If at any point in the 26-week window:
- v2 goes to 0-6 forward while v1 is 3-3: v2 is broken, kill v2 shadow immediately (per its own reject gates)
- Live results diverge sharply from backtest for BOTH v1 and v2: something structural has changed, invalidate both pre-regs and start over
- Regime flips (M12 goes SHORT): informative event, worth a fresh regime-split analysis at that point

None of these are "ship v2 early" triggers. They're "kill or re-scope" triggers.

## Final recommendation

**Do not file the amendment.** Honor the original 2027-01-22 gate. Use the intervening 5 months to:
- Continue forward tracking (already happening)
- Prepare v2 elevation ship materials if the gate clears
- Continue independent research on other candidates (this loop's job)

Farhad can override this recommendation as product owner. But if asked, my professional recommendation is: the case for v2 is strong on backtest, live evidence is not yet informative, the pre-reg exists to protect us from exactly this pattern of reasoning, honor it.

## Files touched

- Consideration doc: `docs/experiments/2026-08-31_v2_accelerated_ship_gate_consideration.md` (this file)
- No pre-reg amendment filed.
- No registry update.
- No live change.
