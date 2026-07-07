---
name: Full logic audit findings (2026-06-19)
description: Bugs found and fixed during pre-deploy audit; clean items confirmed
type: project
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
**Audit performed 2026-06-19 after ORB deployment.** All criticals fixed before Task Scheduler installation.

## Critical (FIXED):

**C1 — DST-aware session times.** SESSIONS dict in `edge_session_orb.py` was using fixed UTC times (NY=13:30 UTC). Correct only during US DST (Mar-Nov). In winter, NY open shifts to 14:30 UTC and the strategy would miss session starts.

Fix: refactored to `SESSIONS_LOCAL` storing `(tz, local_time)` pairs; added `session_utc_time_on(date, sess)` that returns the correct per-date UTC time. `find_session_starts()` and `dispatch_orb.py` both use this. Backtest results unchanged (60-day window is entirely within DST).

**A8 — Weekend guard on dispatch_orb.** `dispatch_orb_alerts()` had no check for market-closed periods. Could send misleading "London ORB forming" alerts on Saturdays when GC is closed.

Fix: `dispatch_orb_alerts` now `return` early if `market_likely_open()` is False (uses `health.market_likely_open` which knows the Fri 17:00 ET → Sun 18:00 ET maintenance gap).

**A3 — Dispatch plan-alert timing window widened.** Was 30 min wide ([bar_close-20m, bar_close+10m]); risk of missing alerts if Task Scheduler tick lands just outside. Widened to ±30 min around `bar_close`. State file prevents duplicates.

## Confirmed clean (no lookahead, no bugs):

- ATR computation uses past bars only (`atr.iloc[i-1]` before event bar).
- `surprise_z` uses `rolling(N).mean().shift(1)` — excludes current observation.
- Exit logic tie-breaking is conservative (assumes stop hit first if both touched in same bar).
- Trend filter slope evaluated at decision bar — no future data leak.
- Cost model: $0.05 spread × 2 (RT) + $0.05 slippage RT + $0.04/oz commission = $0.19/oz = $19/contract RT. Correct.
- Position sizing math (per-vehicle units, GLD share-cap, Reg-T margin allowance) is consistent.
- Random-timestamp null, inverse-strategy null, walk-forward by quarter, deflated Sharpe all methodologically sound.

## Known limitations (not bugs, documented):

- yfinance free GC=F intraday has ~15h lag → STALE_BAR_HOURS set to 24.
- ORB validated on only 60-day 5m window. Forward-test will refine.
- CPI direction rule in `calendar_events.py` is regime-dependent and hardcoded — but v5 PEB ignores `expected_dir`, so this dead code path doesn't affect deployment.
- dispatch.py and dispatch_orb.py share `dispatch_state.json`. Works because dispatch.py calls dispatch_orb.py sequentially, but architecture is fragile under concurrency. Task Scheduler `IgnoreNew` policy prevents concurrent invocations.

## Deployment status:

Task Scheduler entries installed 2026-06-19/20:
- `\GoldDayTrader\Dispatch` — every 30 min, runs `src/dispatch.py`
- `\GoldDayTrader\DailyRefresh` — daily 6 PM, runs `src/run_daily.py`

Both verified `Last Result: 0` after manual trigger. (`267011` on a never-run task is `SCHED_S_TASK_HAS_NOT_RUN`, not an error.)

## Round-2 audit (deeper pass, also 2026-06-19) — additional fixes:

**D1 (CRITICAL):** `track_results.py` was importing from `mers_v4_final` (fixed-hold, no stops), but the deployed strategy is `mers_v5` (event-bar-range stops + 2× targets, JOBS merged from NFP+UNRATE). Forward log would have recorded the wrong P&L. Fix: switched to `from mers_v5 import …` and added `dedupe_co_released` step.

**D2 (HIGH):** `track_orb.py` used the static `SESSIONS` snapshot (today's UTC times) — same DST bug we fixed for live dispatch was not propagated. Fix: now uses `SESSIONS_LOCAL` + `session_utc_time_on(date, sess)` per-date, also skips Saturdays explicitly.

**D10 (MEDIUM):** `position_sizing.py` futures cost was $24 RT — stale from before user-specified $0.05 spread. Fix: GC=$19, MGC=$4 to match `RT_COST_PER_OZ = 0.19` in backtest.py.

**Lesson:** when changing a deployed parameter (cost model, strategy version, session times), check ALL downstream files for the same constant. We had stale copies in trackers and position_sizing.
