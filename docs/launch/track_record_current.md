# NORTH - live track record

*Auto-generated from `data/far_weekly_calls.jsonl` on 2026-10-12 11:07 UTC*

## Current call

- **Week:** 2026-10-12 to 2026-10-16
- **Direction:** FLAT
- **Reference price at publish:** $4190.15
- **Note:** No trade this week. Signal did not clear all four conditions. Sitting out is the correct action, not a missed opportunity.

## Cumulative record

- **Weeks published:** 11
- **Directional calls (LONG/SHORT):** 2
- **FLAT weeks:** 9
- **Directional calls resolved:** 2
- **Wins:** 0/2 (0% hit rate)
- **Cumulative return (net of costs):** -4.03%

## Recent resolves

| Week | Direction | Entry | Exit | Reason | Net % |
|---|---|---|---|---|---|
| 2026-07-27 | SHORT | $4014.24 | $4043.24 | friday_close | -0.72% |
| 2026-08-24 | LONG | $4602.06 | $4450.06 | friday_close | -3.30% |

## Honesty statement

This is a small sample. NORTH v1 has been live since 2026-07-22. Any conclusion drawn from fewer than ~25 resolved directional trades is noise. The 16-year historical backtest is our best current estimate of expected behavior, and it showed 55.9% win rate on directional weeks with +0.23% mean return per trade after costs. Live results should converge toward that over quarters and years, not weeks.

## Mechanical halt check (SPRT)

- **Verdict:** CONTINUE. Log-LR +0.776, halt boundary +2.773. Needs 6 more consecutive losses to halt.
- **Rule:** pre-registered sequential test on win rate. Halt fires automatically if evidence crosses the pre-set boundary. No subjective call. Published alongside every weekly dispatch so you can audit it.

## What we are doing about it

Current research pipeline (public, same discipline as the shipped product):

- **v2 shadow** (DXY-filtered v1): tracking since 2026-07-22. Forward window closes 2027-01-22. If v2 forward beats v1 forward on Sharpe and mean weekly return, v2 becomes the ship candidate.
- **v3-m20 pre-reg** (`far_weekly_gold_read_v3_m20`, drafted 2026-10-12): v2 plus a filter that would skip LONG signals in the historically bad high-momentum-exhaustion bucket (M20 above 7%). Four converging analyses identified this zone as v1's structural weak point; the one resolved live LONG loss sat in it. Pre-reg is drafted but blocked by a cooling-off requirement before the backtest can run. See `docs/experiments/2026-10-12_far_weekly_v3_m20_extremity_prereg.md`.
- **No live rule change** while pre-reg windows are open. v1 continues to run as published. If and when v2 or v3-m20 earns promotion, the transition is documented with full before/after track records.

What we are NOT doing: panic-shipping an unvalidated filter, retiring the engine on a two-trade sample, adding instruments or signals mid-drawdown. Every one of those is a documented failure mode in `docs/development_story.md`.
