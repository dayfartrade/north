# Experiment: vol_ratio_ge_1_0 (shadow-mode)

**Registered UTC:** 2026-07-07T18:35:00Z
**Blinded until:** n=100 cumulative shadow decisions accumulated
**Layer:** session_config (would become a `min_or_vol_ratio` gate in SESSION_CONFIG if promoted)
**Owner:** Knox

## Hypothesis

Skipping PLANs where OR-window volume ratio (OR-avg-volume / prior-20-bar-avg)
is below 1.0 preserves or improves win rate. Sampled today at n=52 the full-
sample lift was directional (69.2% → 75.0%) but total P&L dropped 28% and
holdout CI included zero, so it did not clear the ship gate. Shadow-log for
30 days to see if the signal holds with more data.

## Rationale

Volume analysis on v7.2.1 sample showed:
- Winners avg OR-window vol ratio 1.66×
- Losers avg OR-window vol ratio 1.28×
- OOS test-set win rate lift 81% → 87% at vol ≥ 1.0 threshold

Signal is directional. Sample too small to ship (Janus's Q2 rule: n ≥ 100
minimum for capital-gating filters). Shadow-mode is the proper containment.

## Data collection

`src/shadow_log.py` records `would_skip = or_win_vol_ratio < 1.0` in
`data/shadow_decisions.jsonl` for every real PLAN that fires. No live impact.
The candidate does NOT gate any actual dispatch.

## Decision rule — LOCKED

Analyze at n ≥ 100 shadow decisions cumulative (real live PLANs post-2026-07-07,
plus historical backfill from alerts_stream.jsonl).

**Promote to live gate** if ALL of:

1. Would-have-skipped events show win rate < baseline by ≥ 10pp
2. Would-have-skipped events show mean/trade < baseline by ≥ $200
3. Would-have-kept events show mean/trade ≥ baseline
4. Bootstrap 95% CI on (kept − skipped) mean-per-trade is entirely negative
   (skipped events reliably worse)

**Continue shadow** if any gate 1-4 fails but signal is directionally right.

**Reject and remove from registry** if:

- After n=200 shadow decisions, would-have-skipped events show ≥ baseline win rate
  (filter is picking out random subset, no real signal)

## Bonferroni denominator

Shadow-mode candidates do NOT consume live-ship hypothesis budget until they
are promoted. Recorded here for tracking.

## Results (fill during rolling analysis)

- **First shadow row:** <ts>
- **Cumulative n at n=50 check:** <fill>
- **Cumulative n at n=100 check:** <fill>
- **Interim analyses:** <link to notebook / script output>
- **Final verdict:** PROMOTE | CONTINUE | REJECT
