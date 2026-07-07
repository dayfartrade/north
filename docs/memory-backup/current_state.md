---
name: Current operational state (2026-07-07 ~13:45 UTC)
description: Where the system is at session end. Read this FIRST in the next session.
type: project
originSessionId: bb75b257-d83d-4c28-b913-c3fc4a842a01
---
**Session active:** 2026-07-07 ~13:45 UTC. Post-launch audit + hardening sprint underway. Website launch target: **2026-07-30 (23 days)**, code-freeze **2026-07-27**.

## What live performance looks like as of 2026-07-07

**Since v7 launch 2026-07-01:** 2 trades taken, 0 wins, 2 losses, cumulative **−$3,818** net (n=2, statistically meaningless but painful).
- 07-01 NY LONG @ 4122.60 → stopped @ 4090.60 = −$3,219
- 07-02 ASIA LONG @ 4142.70 → stopped @ 4136.90 = −$599

**Full v7 forward (2026-06-21+):** 16 trades, 8W/8L (50%), −$5,319 net. Backtest promised 58% + $524/trade — live paid off ratio collapsed.

**Alert dispatch since launch:** 9 total alerts (4 preview, 2 pre, 2 plan, 1 daily brief). 8 SENT[public] all silently fell back to private chat because `GOLDTRADER_TG_CHAT_PUBLIC` was never provisioned — subscribers received nothing for 7 days.

**Critical outage:** Dispatch went silent 2026-07-03 13:30 UTC → 2026-07-07 11:48 UTC (~66 hours). Root cause: yfinance bar-lag defer path in `dispatch_orb.py:290` re-deferred every tick without escalation. Watchdog only detects scheduler gaps, not data-staleness.

## Deep audit + patch sprint (this session — 2026-07-07)

Ran Explore agent audit → 15 findings. **Independently verified each** before patching (per user preference — saved us from a phantom "B1 entry-direction" fix that would have broken the strategy).

### Applied fixes (working tree, NOT COMMITTED)

| Fix | File | Change |
|---|---|---|
| **B2** — data-lag escalation | `dispatch_orb.py:290`, `health.py` | New `record_orb_lag_defer()` — 2nd consecutive defer for same (session, or_close_ts) sends private alert. Prevents repeat NFP-style silent outages. |
| **B3** — atomic state writes | `dispatch.py`, `dispatch_orb.py`, `health.py` | All `save_state`/`save_health` now write tmp + `os.replace()`. Crash-safe on Windows. |
| **B4** — cost model honesty | `backtest.py:31`, `position_sizing.py:107` | `RT_COST_PER_OZ` 0.19 → **0.24** (matches docstring; realistic GC round-trip). Re-ran validation: still PASSES. Full n=72, 56.9% win, +$466/trade, CI lo=+$74. |
| **H1** — public channel fail-fast | `telegram_bot.py` | New env `GOLDTRADER_STRICT_PUBLIC=1` → refuses to send when public unset. Default behavior: LOUD banner "FALLBACK: public channel not configured" prefixed to every fallback message so the operator can't miss it. |
| **H2** — atomic basis CSV | `basis_tracker.py` | Single write() call for row append; POSIX/NTFS atomic for small rows. |
| **H3** — validation kill-switch | `weekly_validation.py`, `dispatch_orb.py:194` | Validation now writes `data/validation_state.json` with verdict. Dispatch loads it every tick — if verdict=NOT READY, suppress all dispatches + private alert (once per day). Bootstrap grace if file missing. |
| **M3** — basis silent unmonitoring | `dispatch_orb.py:_basis_context` | Now logs failures to `dispatch.log` (was: silent). Alert content still quiet (design). |

### Verified as NOT bugs (audit was wrong)

- **B1** (entry direction break) — commit-to-first-direction ORB pattern is intentional. Skipping SHORT after failed LONG on same bar is impossible (both-hit case handled by `continue` at line 111). **Do not touch.**
- **H4** (DST session windows) — ran verification script for both US and UK DST transitions in 2026. All session times shift correctly (LON summer 07:00 UTC / winter 08:00; NY DST 13:30 / standard 14:30; ASIA fixed 23:00). `pytz.localize()` is doing its job.
- **M1** (data-staleness watchdog) — redundant with B2 fix.
- **M2** (COT timeout) — `requests.get(timeout=30)` already exists.
- **L1-L4** (perf/cache nits) — all phantom on inspection.

## Current backtest number (with honest cost model)

```
Window: 2026-04-10 → 2026-07-02 (83 days)
FULL:    n=72  win=41/72 (56.9%)  total=+$33,557  mean=+$466/trade  CI [+$74, +$870]
TRAIN:   n=57  win=30/57 (52.6%)  mean=+$448/trade
HOLDOUT: n=15  win=11/15 (73.3%)  mean=+$536/trade
VERDICT: DEPLOY-READY (WEAK tier, n<100)
```

Compare to old $19 cost: mean +$524 → +$466 (haircut of ~$58/trade). Edge survives. Weekly Sun 22:00 UTC revalidation still armed.

## Working-tree diff summary (not committed)

```
src/backtest.py         cost 0.19→0.24
src/basis_tracker.py    atomic single-write append
src/dispatch.py         atomic state write
src/dispatch_orb.py     lag escalation + validation kill-switch + basis logging
src/health.py           lag-defer tracker + atomic health write
src/position_sizing.py  GC cost 19→24
src/telegram_bot.py     STRICT_PUBLIC mode + loud fallback banner
src/weekly_validation.py  persists verdict → validation_state.json
.gitignore              baseline file exclusion (earlier fix)
data/validation_state.json  NEW — H3 kill-switch state (DEPLOY-READY as of run)
```

## What still needs to happen before 2026-07-30

- [ ] Provision public Telegram channel + set `GOLDTRADER_TG_CHAT_PUBLIC` env
- [ ] Day 10 chaos test: kill dispatch mid-tick; corrupt state; verify recovery
- [ ] Define website API contract (alert stream, live P&L feed, subscription state)
- [ ] Build website endpoints
- [ ] End-to-end dry-run of subscriber journey
- [ ] Code freeze 2026-07-27
- [ ] Website integration 07-28 → 07-29
- [ ] Public launch 2026-07-30

## Sprint schedule (from 2026-07-07)

| Days | Milestone |
|---|---|
| 1 (today) | ✅ Audit + B2/B3/B4/H1/H2/H3/M3 patches |
| 2-4 (07-08 → 07-10) | Chaos test + website API contract |
| 5-9 (07-11 → 07-15) | Website integration |
| 10 (07-13) | 🎯 CPI 12:30 UTC — first macro test of patched system |
| 15-17 (07-21 → 07-23) | Final integration + docs |
| 18-20 (07-24 → 07-26) | Code freeze + observe |
| 21-22 (07-28 → 07-29) | Website connect + bug hunt |
| 23 (07-30) | 🚀 PUBLIC LAUNCH |

Stretch goal: freeze by 07-24.

## Files to trust (post-patch)

Everything modified this session is in working tree. Dispatch scheduler will pick up new code on next tick (fresh Python process). Existing `data/dispatch_state.json` and `data/health.json` are compatible — new schema keys are additive.

## Next event timeline

- **2026-07-07 14:00 UTC** — NY PLAN (first live test of patched code; watch dispatch.log for "SENT[public] orb_plan NY")
- **2026-07-13 12:30 UTC** — CPI (first macro since v7 patches)
- 2026-07-29 18:00 UTC — FOMC (post-launch)
