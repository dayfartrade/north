---
name: v6 added Session ORB edge — day-trader frequency
description: Second edge added to push to ~1.5 trades/day; cost model dropped to $0.05 spread
type: project
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
**v6 = MERS v5 (events) + Session ORB (sessions).**

**Session ORB params (frozen, validated):**
- Opening range = first 6 × 5m bars = 30 min after each session open
- Sessions: London 07:00 UTC, NY 13:30 UTC, Asia 23:00 UTC
- Watch 12 bars (60 min) for breakout above OR.high or below OR.low
- Trend filter: 1h-resampled EMA50 slope-5; only with-trend breakouts taken
- Stop = 1.0 × OR range against entry. Target = 1.5 × OR range. Time exit 24 bars (2h).

**Backtest (60-day 5m window):**
- 82 trades = ~1.4/day  · 51.2% wins  · mean +$278  · total +$22,812  · Sharpe 2.54
- Per session: LON Sharpe 3.83 (strongest), ASIA 5.59 (small n but strong), NY 0.59 (weakest)
- Random-timestamp null p = 0.035 (significant on total $)
- Inverse trend filter: $4,345 vs real $22,812 (filter is real)

**Cost model:**
- User said spread is $0.05/oz per side
- RT cost = 2×0.05 (spread RT) + 0.05 (slippage RT) + $0.04/oz (commission) = $0.19/oz = $19 per GC contract
- Down from $24. Applied in src/backtest.py.

**Why these params (not the in-sample max):**
- Best-of-sweep config (OR=12, w=12, h=24, tp=1.0) showed Sharpe 11+ but that's clearly curve-fit
- OR=6, w=12, h=24, tp=1.5 is a "median" config — robust across the sweep neighborhood
- Walk-forward on 60-day window not viable (sample too small); rely on forward-test to refine

**Caveats:**
- 60-day 5m window is the data limit. v5 had 2 years; ORB has 2 months. Smaller sample = wider uncertainty.
- NY session is weak (Sharpe 0.59) but included since it's not negative. Watch in forward test.
- Forward tracker: data/tracker/orb_forward_log.csv via src/track_orb.py

**How to apply:**
- Treat ORB and MERS as ORTHOGONAL signals (event-driven vs session-driven, different timeframes)
- Combined target: ~1.5 trades/day
- If a forward week shows ORB win rate <40% or mean <$0, suspect regime change (see dashboard drift check)
