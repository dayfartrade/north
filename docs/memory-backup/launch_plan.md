---
name: Launch plan & timeline
description: 12-day plan to ship the gold day-trader as a PRODUCT by July 1, 2026
type: project
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
**Target launch: 2026-07-01.** This is a PRODUCT, not personal-use only — the user is connecting it to a website for shipment.

**Timeline:**
- 2026-06-19 → 2026-06-20: Live forward test of v6 (ORB). Catch bugs, validate alert UX. No macro events fire in this window (next is NFP Jul 3 = after launch).
- 2026-06-20 → 2026-06-21: User shares their prior failures, data, books, observations. I absorb, update memory, draft v7 revision plan.
- 2026-06-21 → 2026-06-23: v7 build — integrate priors, add edges if warranted, re-run full null-test battery (random-timestamp, inverse, walk-forward, GLD cross-asset, DSR).
- 2026-06-23 → 2026-06-25: Production hardening — REST API endpoints, JSON data export, web-dashboard data feeds, multi-user config support, audit log, risk disclaimers.
- 2026-06-25 → 2026-06-27: Polish, documentation for the website team, deployment checklist. **Code freeze June 27.**
- 2026-06-28 → 2026-06-30: Standby. Bug-fixes only during website integration.
- **2026-07-01: LAUNCH.**

**Critical hard truth to surface in any marketing:** the product is defensible by *backtest rigor + null tests + integrated priors*, NOT by long live track record. We will have <2 weeks of live data at launch. Any pre-launch claim ("Sharpe X.XX") must be the honest annualized number (~0.59 for MERS, ~2.54 for ORB in-sample), with sample-size caveat.

**Open questions to resolve early:**
1. What's the actual delivery mode? Telegram alerts to subscribers? Web dashboard? Paid signal service? — affects what API surface to build days 5-7.
2. Multi-tenant or single-config? — affects position-sizing and config architecture.

**How to apply:**
- Treat post-Jun 27 as code-frozen. New edges / strategy changes after that date go in a v7.1 backlog, not into the launch build.
- Reserve days 5-7 specifically for API/data-export surface — that's the website team's interface, can't ship without it.
- If user-shared priors are large, prioritize the highest-value 1-2 ideas; defer rest to post-launch backlog.
