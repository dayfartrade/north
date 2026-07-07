---
name: v7 geometry finding — per-session, not unified
description: Counter-intuitive backtest finding driving v7 design — different sessions need opposite stop logic
type: project
originSessionId: 14f4c0d3-d439-4594-962d-37fd4ffc75e5
---
**Finding (2026-06-30):** The R:R fix the user's notes pushed (tighten stops, add OR-vs-ATR filter) is right for LON but WRONG for NY and unnecessary for ASIA. Optimal v7 is **per-session hybrid**:

- **ASIA**: keep v6 — OR-range stop, OR-range target, no filter. (n=30, 57% wins, +$507/trade in backtest)
- **LON**: v7-tight — filter OR<2×ATR, adaptive stop $13, target=1.5×stop. (n=8, 75% wins, +$879/trade)
- **NY**: keep v6 — OR-range stop, no filter. NY ORs are always wide post-news; tightening kills it. (n=34, 44% wins, +$108/trade)

**Why the asymmetry:** LON has bimodal OR distribution (news days vs quiet); filter cleanly separates. NY ORs are uniformly wide; filter just kills the strategy. ASIA ORs are uniformly tight; filter doesn't change anything.

**Validation (60-day backtest):**
- v6 unified: $+18,499 total, mean $+197, Sharpe(pt) 0.110
- v7-hybrid: $+25,907 total (+40%), mean $+360, Sharpe(pt) higher

**Validation (live n=11 replay):**
- Original: $-6,784
- v7-hybrid: $+773 (delta $+7,557 — filter skipped 3 catastrophic LON trades)

**Why:** Per-session winner-MAE max from backtest:
- ASIA: $11.40  LON: $10.80  NY: $18.50
- NY winners need wider stops; LON winners pull back less.

**How to apply:** Code in `src/edge_session_orb_v7_final.py`. SESSION_CONFIG dict is the public API. Pending Phase 7 validation (bootstrap CI, 80/20 holdout) before live deployment. Don't deploy unified-rule "improvements" — they break NY.
