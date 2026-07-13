# Phase 8.1 — v7 filter inventory + KEEP/DROP/REVISE marks

**Written UTC:** 2026-07-13 15:25
**Purpose:** Enumerate every gate/filter/decision in v7 codebase so v8 can port them into `strategy_engine.py` with clear intent.

## Legend

- **KEEP:** verbatim port to strategy_engine.py
- **REVISE:** port but change semantics (spelled out per row)
- **DROP:** filter is either dead code, wrong, or superseded by a better v8 primitive
- **INVESTIGATE:** unclear what it does; needs a spike before v8 decides

## Filters (all currently in v7)

### Box 1 — OR/ATR filter

| Location | Session | Rule | KEEP/DROP/REVISE |
|---|---|---|---|
| dispatch_orb.py:528 | all | skip if or_range > 2.0 * ATR (from default) | **REVISE** — make per-session explicit; no defaults |
| edge_session_orb_v7_final.py (LON) | LON | skip if or_range > 2.0 * ATR | KEEP |
| edge_session_orb_v7_final.py (NY) | NY | skip if or_range < 2.5 * ATR (v7.1, never live) | INVESTIGATE — Path Y results say drop; but backtest shows +75% mean/trade lift. Needs OOS shadow to decide. |
| edge_session_orb_v7_final.py (ASIA) | ASIA | skip if 2.0 <= ratio <= 2.5 (v7.1, never live) | INVESTIGATE — same as NY |

**v8 target:** one filter per session; explicit config; unit-tested; identical behavior in backtest and live.

### Box 2 — News stand-down

| Location | Rule | KEEP/DROP/REVISE |
|---|---|---|
| stand_down.py:MAJOR_NEWS | {FOMC, CPI, NFP, UNRATE, PPI, RETAIL} | KEEP — well-tested, canonical macro list |
| stand_down.py:NEWS_BUFFER_MINUTES | ±15min | KEEP |
| dispatch_orb.py:468 | Skip if OR bars overlap MAJOR_NEWS ± buffer | KEEP |
| stand_down_for_entry | Skip individual entries within buffer | KEEP |

### London fix stand-down

| Location | Rule | KEEP/DROP/REVISE |
|---|---|---|
| stand_down.py:is_london_fix_window | 15:00 UTC ± 10min | **REVISE** — memory says "London 15:00 fix is THE NY leak; skip-and-retest adds +$10k" — check the retest logic is preserved |

### Box 3 — Trend filter

| Location | Rule | KEEP/DROP/REVISE |
|---|---|---|
| edge_session_orb_v7_final.py (all) | require_trend=True: skip if slope==0 (FLAT) | KEEP — sensible default |
| dispatch_orb.py inline | LONG only if slope > 0; SHORT only if slope < 0 | KEEP — direction commit |

### Box 4/5/6 — Audit context (soft signals)

| Location | Rule | KEEP/DROP/REVISE |
|---|---|---|
| dispatch_orb.py:_basis_context | Basis divergence context | KEEP as observation, NOT gate |
| dispatch_orb.py funding | Bitget funding context | KEEP as observation |
| dispatch_orb.py cot | CFTC net long context | KEEP as observation |
| dispatch_orb.py volume | OR-window volume ratio | KEEP as observation + shadow candidate |

These are context blocks written to alerts and shadow log. Not gates. Should be part of RegimeContext in v8.

### Trade geometry

| Location | Rule | KEEP/DROP/REVISE |
|---|---|---|
| SESSION_CONFIG stop_mode | or_range | fixed | KEEP |
| SESSION_CONFIG fixed_stop_price | LON: $13 | KEEP |
| SESSION_CONFIG target_mode | or_range | stop_x_tp | KEEP |
| SESSION_CONFIG tp_mult | 1.5 (Path Y all) | KEEP |
| dispatch_orb.py commit-to-first-direction | Long stop and short stop set at OR high/low; whichever hits first commits | KEEP — audited safe (07-07 audit) |

### v7.2 accuracy sweep (memory notes)

| Item | KEEP/DROP/REVISE |
|---|---|
| v7.2 NY tp_mult 1.0 (from Path Y revert) | DROP — v7.1 rationale invalidated by divergence discovery |
| v7.2 extend max_hold 120 → 180 (commit ad3f332) | KEEP — orthogonal to filter divergence |
| v7.2 accuracy sweep (3 ships, 8 rejects per memory) | INVESTIGATE — audit each ship for live/backtest divergence pattern |

### Shadow candidates (registered 2026-07-13, none shipped)

| Candidate | KEEP as v8 shadow? |
|---|---|
| `vol_ratio_ge_1_0` | KEEP — pre-registered, still in flight |
| `slope_gt_8` | KEEP — pre-registered |
| `real_yield_gt_2_2` | DROP — REJECTED by 20-year OOS regime test |
| `prior_day_range_gt_80` | KEEP — pre-registered, awaiting apply |
| `gap_after_down_day` | KEEP — pre-registered, awaiting apply |

### Position sizing

| Location | Rule | KEEP/DROP/REVISE |
|---|---|---|
| position_sizing.py | Fixed / risk_pct / fixed_dollars modes | KEEP — separate concern from strategy engine |
| RT_COST_PER_OZ=0.24 | Round-trip cost | KEEP (fixed 2026-07-07 audit) |

### Health / operational gates

| Location | Rule | KEEP/DROP/REVISE |
|---|---|---|
| H3 kill switch (validation_state.json verdict) | Suppress all dispatch on NOT READY | KEEP — genuinely useful, saved us today |
| Bar-lag defer (H2 escalation) | Defer dispatch if bars stale | KEEP — canonical operational gate |
| Stale-data gate | Refuse alerts on >4h-old bars | KEEP — fixed today (UnboundLocalError) |
| Halt monitor (halt_monitor.py) | DD + SPRT verdict | KEEP — post-CPI wire-up TODO |
| Session-aware daemon | Skip COMEX close / weekends | KEEP — designed today, apply post-v8 |

## Summary

- **12 items KEEP** verbatim
- **3 REVISE** (per-session OR/ATR explicit; London fix retest verify; v7.2 sweep audit)
- **2 DROP** (real_yield_gt_2_2, v7.2 NY tp_mult 1.0)
- **4 INVESTIGATE** (NY min gate, ASIA deadzone gate, v7.2 sweep audit, others)

The INVESTIGATE items get answered by Path Q's shadow tracker — over 30 days we'll have OOS data on whether NY min gate and ASIA deadzone add real edge.
