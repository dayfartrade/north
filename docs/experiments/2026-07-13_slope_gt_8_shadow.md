# Experiment: slope_gt_8 (shadow-mode)

**Registered UTC:** 2026-07-13T10:05:00Z
**Blinded until:** n=100 cumulative shadow decisions accumulated
**Layer:** session_config (would become a `max_trend_slope_long` gate if promoted)
**Owner:** Knox

## Hypothesis

Skipping LONG entries where 15m trend_slope > 8 preserves or improves LONG win rate. Steep positive slope at OR-close signals a vertical/parabolic move that ORB LONGs then fade into.

## Rationale

The 2026-07-13 3-loss post-mortem (07-01/02/09 launch losses) identified 07-02 ASIA (slope +11.78) as a "buying the top of a vertical move" archetype. When applied to the 24 forward-log trades:

- Skips 5 trades (all losses, 0 wins)
- Net_after_skip lift = +$8,145 vs baseline

**Overfit caveat:** filter was designed AFTER inspecting the 07-02 loss. In-sample-of-in-sample bias baked in. But the mechanism (top-of-vertical entry) is theoretically plausible independent of the dataset.

**Bonferroni note:** this candidate contributes to the N considered on 07-13 (currently 4 candidates evaluated on the same forward log). p-value on shipping decisions must be × 4 or larger to be honest.

## Data collection

`src/shadow_log.py` CANDIDATES entry records `would_skip = trend_slope > 8.0` in `data/shadow_decisions.jsonl` for every real PLAN. Analysis code applies the LONG-only cut at report time — SHORT PLANs record the flag but their would_skip is disregarded when scoring the LONG-only hypothesis.

## Ship gate

Same as `vol_ratio_ge_1_0`: n ≥ 100 shadow decisions AND ≥ 60% precision on skipped losers (loss dollars / total skipped dollars) AND expected P&L lift > 0 with holdout CI > 0.

## Rejection conditions

- Precision on skipped losers < 55% at n=100 → REJECT (small-sample overfit confirmed)
- Skip rate > 30% of PLANs → REJECT (too aggressive, sacrifices sample)
- Ship gate not cleared by 2026-09-15 → REJECT (candidate cannot beat n growth)

## Companion candidates

Registered same day (07-13) for parallel evaluation, pending dispatch_orb.py feature extension:
- `real_yield_gt_2_2` (LONG-only) — canonical macro filter (Erb & Harvey 2013)
- `prior_day_range_gt_80` — whipsaw filter
- `gap_after_down_day` (LONG-only) — dead-cat bounce filter
