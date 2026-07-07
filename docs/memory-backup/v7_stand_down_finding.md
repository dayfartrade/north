---
name: v7 stand-down finding — fix window is the biggest single lift
description: London 15:00 fix windows is THE accuracy leak for NY ORB; skip-and-retest converts losers into selective re-entries
type: project
originSessionId: 14f4c0d3-d439-4594-962d-37fd4ffc75e5
---
**Finding (2026-06-30):** 80% of NY ORB entries fall inside the London 15:00 LT fix window (= 14:00 UTC summer). Those entries are systematically worse:

- NY entries IN fix (n=27): 41% win, mean −$8, total −$203 (basically breakeven with full variance)
- NY entries OUTSIDE fix (n=7): 57% win, mean +$554, total +$3,877

**Fix is structurally co-timed with NY ORB by design** — NY equities open 09:30 ET = 14:30 BST in summer, fix at 15:00 BST. So the first 30 min of NY entries falls in the ±10 min fix buffer.

**Resolution:** Skip-and-retest — when a breakout fires inside fix/news window, skip and KEEP watching for a later breakout in the watch window. Many NY days produce a retest at 14:15-15:00 UTC. Retests perform much better than first-breakouts inside the fix.

**Backtest impact (60-day window):**
- v7-hybrid (no stand-down): n=72, total +$25,907, mean +$360
- v7-hybrid + stand-down: **n=69, total +$36,179, mean +$524 (+40% on top of v7)**

**Stand-down rules:**
- ±15 min around FOMC/CPI/NFP/PPI/UNRATE/RETAIL releases
- ±10 min around London 10:30 LT and 15:00 LT fix windows

**News filter rarely fires in current schedule** — releases at 12:30 UTC don't overlap any entry watch (LON 07:30-08:30, NY 14:00-15:00, ASIA 23:30-00:30). Acts as safety net for non-standard timing (FOMC at 18:00 — also safe).

**Code:** `src/stand_down.py` + wired into `src/edge_session_orb_v7_final.py` via `apply_stand_down=True` default.

**How to apply:** Always-on for v7 dispatch. Logged skipped entries should be tracked separately for retro QA — if skipped entries would have won more than retests, the rule needs revisiting.
