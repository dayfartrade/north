---
name: Next gm agenda (as of 2026-07-13 ~17:15 UTC session end)
description: What Knox should dump immediately on the next "gm" trigger. Read this before agenda so the dump is current.
type: project
originSessionId: 8c5c29bc-8414-4021-bbca-1894ba8135a7
---
**Session ended:** 2026-07-13 ~17:15 UTC. Massive day: **27 commits pushed**. Dispatched bug fix saved CPI, divergence discovery led to Path Y honest DSR (FAIL), Q+Z shipped, v8 phases 8.1-8.5 all done, Crabel research + LON edge cross-tab, 3 wrap-up polish tasks.

## Open on next gm with this format

Lead with the halt state and shadow-log accumulation (this is the ONLY real signal accumulating overnight). Then queue.

### 1) Overnight status — read (in order):

1. `data/dispatch.log` — 30-min ticks continuing during ASIA (23:00 UTC) and LON (07:00 UTC)? Each will now say `DISPATCH SUPPRESSED: NOT READY` because kill switch is ON.
2. `data/shadow_equity_since_halt.jsonl` — first FORWARD shadow entries expected at ASIA 23:00 UTC (07-13) and LON 07:00 UTC (07-14). Verify tracker + resolver fired.
3. `data/halt_state.json` — should stay GREEN unless something dramatic happened.
4. Any private Telegram alerts overnight — halt monitor sends on GREEN↔AMBER↔HALT transitions.
5. The 22:00 UTC daily brief should include a new "SHADOW-EQUITY DIGEST" private message.

**If shadow tracker did NOT populate new entries overnight:** tracker wire is broken. Check `src/dispatch.py:249-278` and `scripts/shadow_orb_tracker.py`.

### 2) System state at handoff

- **Kill switch: ON.** `data/validation_state.json` verdict=NOT READY. All ORB dispatches suppressed. DO NOT flip this without a strategic decision.
- **Halt monitor: GREEN, SPRT CONTINUE.** log-LR +1.92 < halt +2.94. 9 live trades since launch (deduped), 2 wins (22%). DD ratio 0.69× reference.
- **v8 strategy_engine: single source of truth.** Backtest + dispatcher + shadow tracker all import from `src/strategy_engine.py`. 9 filters registered, 3 active, 6 shadow-gated on cfg thresholds.
- **73 tests passing.** Property tests + golden fixtures + market-hours + strategy-engine.
- **Path Y honest DSR: NOT READY.** n=25, 52% win, CI [-$112, +$954]. LON 75% edge, ASIA marginal, NY negative.
- **Regime finding: LON is BIMODAL** — edge at ry<2.0 AND ry≥2.2, failure in 2.0-2.2 transition. Not "regime-conditional" as first thought.

### 3) Queue for next session (ordered)

**a) Check first-forward-shadow entries.** ASIA 23:00 UTC and LON 07:00 UTC should have populated `shadow_equity_since_halt.jsonl` with `strategy_version=v7-actual-path-y` (not `-backfill`). If they did: system works end-to-end.

**b) Delete old GitHub token on GitHub side.** Kept 07-07 token still valid, but the newest (2026-10-11 expiry) is the one in `.github-token`. Cleanup only, low priority.

**c) VPS migration.** Still owed. Checklist at `docs/ops/vps_migration_checklist.md`. ~2h user execution. Public launch (07-30 → realistic 08-15+) depends on it.

**d) Public channel pinned message.** Drafted 07-08, still not pinned. In prior session transcript.

**e) Regime cross-check with 20yr history.** The "LON bimodal" finding at n=8 is suggestive; if we run the same analysis on 20 years of GC we could validate.

**f) Kaufman Ch 24 (Adaptive Techniques)** — deferred research; would inform v9+ regime-conditioning design.

**g) Backtest historical Crabel "crucible" regimes** (2011-13 bear, 2020 pandemic, 2022 shock) per quant framework.

### 4) DO NOT

- **Do NOT flip the kill switch off** without deciding Path X/Y/Z. DSR fails at honest metrics.
- **Do NOT ship any Crabel shadow candidate** without n≥100 shadow evidence. All are pre-registered but no-op via SessionConfig thresholds=None.
- **Do NOT re-run SPRT with new hypothesis pair** — that's discipline breach. Current pre-reg is `sprt_v72_1_launch_path_y` with H0=0.52, H1=0.35.
- **Do NOT touch orb_forward_log.csv again** — deduped 07-13, tracker bug fixed at source (`src/track_orb.py` rejects Sunday gaps >30min).

### 5) What shipped 07-13 (27 commits)

Pre-CPI:
- `6ffcef0` **Critical dispatch UnboundLocalError fix** — saved CPI T-1h alert
- `a953975` SPRT halt research + halt monitor
- `39578bb` Live/backtest divergence + kill switch
- `a309f93` Path Y honest DSR audit
- `b7e362a` Path Q + Z scoped

v8 rebuild:
- `f4f3226` Phase 8.1 sketch + tests
- `28f01d6` Phase 8.2 filters + regime + golden fixtures
- `689902f` + `562e1e8` Phase 8.3 backtest + dispatcher port
- `378969e` Phase 8.4 re-audit + filter refinement
- `13b3846` Phase 8.5 shadow candidates

Post-v8:
- `9410043` Shadow outcome resolver
- `c9d2edd` Halt monitor wired + Telegram transitions
- `6603469` Dedupe defense in halt_monitor
- `f176173` Session-aware daemon (COMEX close)
- `84acadd` Tracker session-attribution bug fix
- `62fd769` Property-based tests
- `4b79a6a` Regime-stratified DSR (LON bimodal finding)
- `0c8493e` Shadow-equity dashboard + backfill (58 rows seed)
- `34fb3db` Crabel research + LON edge cross-tab
- `e15dcd2` 3 Crabel shadow filters wired as no-ops
- `8b32d92` Nightly shadow-equity Telegram digest (22:00 UTC)
- `1593866` Dedupe orb_forward_log.csv in-place

### 6) Files that will matter next session

- `data/shadow_equity_since_halt.jsonl` — where forward shadow accumulates
- `data/halt_state.json` — verdict + SPRT reading each tick
- `data/dispatch.log` — should show SUPPRESSED every tick
- `data/validation_state.json` — kill switch state (verdict=NOT READY)
- `src/strategy_engine.py` — single source of truth
- `docs/experiments/2026-07-13_*.md` — full record of today's decisions

**Amazing session per user. Genuine rest earned until data accumulates.**
