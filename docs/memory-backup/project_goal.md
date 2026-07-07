---
name: Project goal & status
description: Single sentence purpose, vehicle, constraints, current deployment state
type: project
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
**Goal (locked-in):** generate profitable signals for day-trading gold futures (GC), manually executed by the user. Free data only for V1; budget tolerance can grow once edge is proven.

**Why:** User has already exhausted ML-on-price-history (30y FRED gold daily) with multiple prior AI attempts. They explicitly asked for a "fresh perspective" — i.e., NOT predicting price from price. So the chosen edge is structural: event-driven volatility expansion + trend filter.

**How to apply:** Every design choice should serve THIS goal — profitability after realistic costs. Reject improvements that don't survive walk-forward or null tests. When in doubt about adding a feature, ask: does it serve the only goal?

**Status as of 2026-06-19:** v5 deployed end-to-end; v6 added Session ORB edge (~1.5 trades/day combined). Telegram alerts wired. Forward test window started.

**This is a PRODUCT, not just personal use.** User is connecting it to a website. **Launch target: 2026-07-01.** Code-freeze 2026-06-27. See `launch_plan.md` for the 12-day timeline.

Next steps in priority order: (1) user shares prior failures/data — currently waiting on this; (2) v7 build integrating priors; (3) production hardening (API endpoints, data exports for website); (4) handoff to website team.

First real forward signal: NFP on 2026-07-03 12:30 UTC (post-launch).
