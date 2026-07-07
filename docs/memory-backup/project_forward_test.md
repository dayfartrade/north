---
name: Forward test schedule
description: When live tracking started and which events to watch for
type: project
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
**Forward test start:** 2026-06-19. Set in `src/track_results.py` (`FORWARD_START`). Any top-tier event resolving on or after this date is eligible to be added to the forward log.

**Next signals (top-tier, in order):**
- 2026-07-03 12:30 UTC → JOBS (NFP + UNRATE released together)
- 2026-07-13 12:30 UTC → CPI
- 2026-07-29 18:00 UTC → FOMC
- 2026-08-07 12:30 UTC → JOBS
- 2026-08-13 12:30 UTC → CPI

**Expected cadence:** ~3 trades per month (FOMC monthly-ish + 1 JOBS + 1 CPI). Forward sample reaches 10-15 trades after roughly 4 months — minimum useful sample to start updating expectations.

**Trigger for re-assessment:** if forward win rate is below 35% OR mean trade is negative after 10 trades, suspect regime change and pause. Use `src/dashboard.py` "Drift check" section — it watches for these and warns.

**Why:** User explicitly wants forward validation before scaling. Memory of v5 backtest stats lives in `data/tracker/forward_log.csv` (vs backtest in `data/backtests/`).

**How to apply:** When the user shares post-deployment data (live trade results, regime observations), update forward_log.csv via track_results.py and check the dashboard for drift signals before suggesting strategy changes.
