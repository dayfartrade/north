---
name: Next gm agenda (as of 2026-07-08 ~20:35 UTC session end)
description: What Knox should dump immediately on the next "gm" trigger. Read this before agenda so the dump is current.
type: project
originSessionId: 4d2bb3d1-0d21-4109-92a6-5ebade22fdce
---
**Session ended:** 2026-07-08 ~20:35 UTC. Live QA + reliability hardening
session. Ranged from diagnosing an overnight 12h dispatch outage to
shipping a Task Scheduler band-aid and drafting the public channel
pinned message.

## Open on next gm with this format

Lead with what happened overnight (ASIA + LON) — **this is the first
live overnight test of the S4U + WakeToRun fix**. Then the queue.

### 1) Overnight status — CRITICAL FIRST CHECK

Read (in order):
1. `data/dispatch.log` — did 30-min ticks continue through the night
   even while screen was locked? Look for gaps.
2. `data/tracker/orb_forward_log.csv` — any new trades since
   2026-07-07 07:00 UTC LON entry?
3. `data/alerts_stream.jsonl` — any new PLAN payloads since the
   first one at 2026-07-08 14:00:16 UTC?
4. `data/shadow_decisions.jsonl` — new shadow rows on top of the
   first n=1 recorded on 2026-07-08 14:00:17 UTC?
5. `NumberOfMissedRuns` on the task (should still be 0 if fix worked).

**If there's a gap ≥60 min in dispatch.log:** the S4U/WakeToRun fix
didn't hold. Escalate. Options:
- Deeper Windows sleep debugging (event log for hybrid sleep,
  Modern Standby wake denials)
- Emergency VPS migration (memory: `hosting_blocker.md`)

**If ticks fired all night:** the band-aid held. Note it in current_state.

### 2) v7.2.1 live performance since launch

As of session end (2026-07-08 20:35 UTC):
- 2 trades taken since launch 2026-07-01 (2L, −$3,818 net)
- 2026-07-08 NY: PLAN fired at 14:00:16 UTC (SHORT bias, entry 4075.80,
  target 4052.25, RR 1.5). Watch expired 15:00 UTC with no entry —
  **no-trade session**.
- No ASIA at 23:00 UTC captured yet (session ended before that fire).

### 3) Queue for the day (ordered by pre-launch value)

**a) VPS migration — still owed.** Band-aid is holding for now but
public launch (07-30) needs it. Hetzner CX22 recommended. Memory:
`hosting_blocker.md`. User deferred on 2026-07-08.

**b) Public channel pinned message — drafted, NOT yet pinned.** Text
is in the session transcript (2026-07-08). User needs to paste it
into Telegram channel `-1004427609443` and pin. If the transcript is
gone, ask user for text; alternative is to re-draft based on user's
preferences (leaner intro-only, no numbers block, EN only).

**c) Rook's website integration.** Untracked `site/` still in
`C:\golddaytrador\site\`. Endpoint mismatch was Rook's problem —
user's explicit direction: **don't touch.**

**d) Weekly validation Sunday 2026-07-12 22:00 UTC.** Runs
automatically. Now expected to include first shadow-analyzer output
(waiting for n≥100 shadow rows; only n=1 recorded).

**e) Code freeze 2026-07-27** — 19 days.

### 4) What NOT to do

- **Do NOT re-run meta-labeling on n=52.** Pre-reg REJECTED it
  2026-07-08. Revisit at n≥100 live per DSR discipline.
- **Do NOT add shadow candidates just to add them.** n=1 today.
  Each entry contributes to future N. Only add if there's a
  market-structure motivation.
- **Do NOT touch `site/`.** Rook's domain.
- **Do NOT declare "launch ready" without the VPS migration or
  equivalent hosting move.** The S4U band-aid is enough for QA,
  not for public subscribers who depend on us not going dark.

## What shipped today (2026-07-08)

- **12h outage 07-07 23:30 → 07-08 12:00 UTC diagnosed** —
  `LogonType: InteractiveToken` blocked task from firing when screen
  was locked overnight. LON preview/pre/plan for 07-08 permanently
  lost.
- **Band-aid applied 17:34 UTC:** `LogonType → S4U`,
  `WakeToRun → true` via `scripts/apply_s4u.ps1` (elevated).
  Committed as `1004b23`, pushed to origin/main.
- **First-ever populated JSONL rows:**
  - `alerts_stream.jsonl` — 2026-07-08 NY PLAN, full audit payload
    (basis, funding, COT, volume, stand-down window).
  - `shadow_decisions.jsonl` — n=1, `vol_ratio_ge_1_0` shadow
    filter recorded `would_skip=true` (ratio 0.781 < 1.0). This
    NY session was a no-trade, so no verdict on the shadow filter
    yet.
- **Public channel pinned message** drafted (EN only, leaner
  intro-only version), NOT yet pinned.

## Live state at handoff

- **Strategy version:** v7.2.1 (live)
- **Task Scheduler Dispatch task:** LogonType=S4U, WakeToRun=True,
  30-min repeat, StartWhenAvailable=true
- **NumberOfMissedRuns at handoff:** 0
- **Last dispatch tick before session end:** 2026-07-08 20:30 UTC
- **All 13 Telegram alert types** share one visual language
- **Post-mortem generator** live
- **Pre-fill checklist** live
- **Shadow log** wired AND now has n=1 real row

## Files that will matter next session

- `data/dispatch.log` — overnight coverage check
- `data/alerts_stream.jsonl` — polished alert payloads
- `data/shadow_decisions.jsonl` — shadow-filter feature capture
- `scripts/apply_s4u.ps1` — the fix, if it needs re-running
- `data/s4u_apply.log` — result of the last apply
- `src/alert_format_v2.py` — the polished formatter
- `data/experiments/registry.json` — N=17 trial history
- Memory: `hosting_blocker.md` (new) — VPS is the real fix
