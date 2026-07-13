---
name: Hosting is the pre-launch blocker (band-aided 2026-07-08, VPS still owed)
description: The trader depends on Windows Task Scheduler on Farhad's PC. Band-aided today to S4U + WakeToRun; VPS migration still open.
type: project
originSessionId: 4d2bb3d1-0d21-4109-92a6-5ebade22fdce
---
**On 2026-07-08 the dispatch pipeline went dark for ~12h** (07-07 23:30 UTC → 07-08 12:00 UTC) because `\GoldDayTrader\Dispatch` was set to `LogonType: InteractiveToken`. The screen locked overnight and Task Scheduler refused to fire an interactive-only task. LON preview/pre/plan for 07-08 were all permanently missed. Windows recorded `NumberOfMissedRuns: 24`.

**Band-aid applied 2026-07-08 17:34 UTC** via `scripts/apply_s4u.ps1` (elevated):
- `LogonType: InteractiveToken → S4U` (runs whether user logged in or not, no password)
- `WakeToRun: False → True` (wakes machine ~2 min before each 30-min tick)

**What this fixes:** screen locked, user logged off, PC in Modern Standby / Modern Sleep.

**What this does NOT fix:**
- Machine fully shut down
- Laptop unplugged and battery drained
- Windows Update reboot without auto-relogin
- Any OS-level failure

**Why:** For pre-launch (2026-07-30) we need the trader to be as reliable as a paid service. Home PC + Task Scheduler is not that. The user picked "defer VPS to another day" on 2026-07-08 during a session already loaded with polish work.

**How to apply:** When session returns to hosting/reliability topics, surface the still-open VPS migration. Options were:
- **Hetzner CX22** — €4.15/mo, Ubuntu 24.04, EU. Recommended.
- DigitalOcean $4/mo, Fly.io, Railway.

Migration plan (~1-2h): provision VPS, install Python 3.14, git-clone repo, scp state files (`dispatch_state.json`, `health.json`, `validation_state.json`, `data/tracker/*`, `data/gc/*`, `data/macro/*`, `.telegram`, `.github-token`), systemd oneshot timer every 30 min, verify one tick, cut over (disable Windows task → enable systemd).

**Do NOT declare "launch ready" without this migration or an equivalent hosting move.** The band-aid is enough for casual overnight testing, not for public subscribers.
