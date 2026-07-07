---
name: Strategy MERS v5 — what works and why
description: The deployed strategy and which validation tests it survived
type: project
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
**MERS v5 = Macro Event Reaction Strategy, Post-Event Breakout, trend-filtered.**

Per qualifying event (FOMC, JOBS=NFP+UNRATE merged, CPI):
1. Wait for the event-hour bar to close. Record H, L of that bar.
2. Place buy-stop at H + 0.1·ATR(20); sell-stop at L − 0.1·ATR(20).
3. **Trend filter**: only take LONG if EMA(50) slope(5) > 0; only take SHORT if slope < 0.
4. Watch 2 bars. If neither triggers, cancel.
5. Stop = 1.0× event-bar range against entry. Target = 2.0× range in favor. Time exit at bar 6.

**Why these events only:** FOMC (#1 vol expansion 3.85×), JOBS (2.55×), CPI (2.04×). PPI/Retail/Claims had positive edge in v3 but failed walk-forward; included would dilute. ECB tested → small sample (n=4) suspicious. BoE tested → clearly LOSES (-$25k, 29% wins, n=7). Dropped.

**Why these directions:** Direction-following with hardcoded rules failed walk-forward (lost in test half). Direction-LEARNED rules also failed. PEB + trend filter is what survived — trade WITH established trend, fade nothing.

**Why this exit logic:** Tight ATR stops (1.5×ATR) cut winners short — gold's post-event vol exceeds 1.5×ATR. Event-bar-range-based stops are naturally wider on high-vol days, tighter on low-vol — adaptive.

**What edges were tested and DROPPED:**
- Direction-following MERS (v1/v2) — failed walk-forward
- ECB/BoE/BoJ events — BoE clearly negative, ECB sample too small
- 5m precision — 60-day window only produces 3 trades
- DXY divergence as standalone edge — mostly negative Sharpe across the sweep
- Volume filter @ mult > 1.5 — too restrictive, no incremental edge

**What edges were KEPT as filters:**
- EMA(50) slope-5 trend filter — inverse loses $10k, real wins $17k ✓
- Volume filter @ mult ≥ 1.25 — marginal lift, included

**How to apply:** If extending v5, validate any new event/filter against the same battery: walk-forward by quarter, random-timestamp null, inverse-strategy null, GLD cross-asset.
