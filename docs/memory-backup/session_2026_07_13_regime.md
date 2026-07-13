---
name: Session 2026-07-13 — regime analysis + OOS rejection of real_yield filter
description: Discovered live is in tail regime (100% ry>=2.2); Bonferroni-passed real_yield_gt_2_2 candidate later REJECTED by OOS test. 3-of-4 losses are intraday microstructure on up-days.
type: project
originSessionId: current
---

**Session start:** 2026-07-13 ~09:10 UTC (right after "gm"). Loop-monitored dispatch through morning; CPI at 12:30 UTC.

## What happened

### Confirmed system state on gm
- Dispatch outage 07-11 19:30 → 07-13 09:03 (~36h dark). S4U band-aid holding this morning (ticks 09:03, 09:33, 10:03 all on schedule).
- Live model: 1W/6L since 07-01 launch, ~-$8,432 net at 7 taken trades.
- New taken trade since 07-08 handoff: 07-09 NY LONG @ 4139.60 → stopped @ 4127.60 = -$1,224.

### 3-loss post-mortem (initial hypothesis)
- Common signatures: 3/3 LONG, all in real_yield >= 2.25 regime, each with idiosyncratic setup (whipsaw day / vertical slope top-buy / dead-cat bounce).
- Joint probability of 0/3 AND all-LONG under H0=57%: ~1%. Real signal, not variance.
- 4 filter candidates proposed: `real_yield_gt_2_2`, `slope_gt_8`, `prior_day_range_gt_80`, `gap_after_down_day`.

### Regime shift confirmed
- Backtest window (2026-04-10 → 2026-07-02): mean ry 2.07, only 19% of days >= 2.2.
- Live since launch: mean ry 2.28, **100% of days >= 2.2**.
- Historical baseline: 2003-2007 had 35% of days >= 2.2 (comparable). 2008-2022 had 0-4% (QE era). 2023+ has ~10%. Current 100% is a tail regime.

### Bonferroni-6 WGC test
- On 24 forward-log trades: p(0/7 LONG wins in high-ry | H0=57%) = 0.0027 raw.
- Bonferroni × 6 (WGC canonical vars: real yield, DXY, CB purchases, CFTC MM net, GLD delta, Shanghai-COMEX premium): **p_adj = 0.0163**. Still significant.

### OOS test on 20+ years — REJECTED the hypothesis
- Ran `scripts/oos_real_yield_regime.py` across 5,883 days of real yield + 6,492 days of GC.
- **20d forward GC return at ry >= 2.2 is +2.28%** vs +0.81% at ry < 2.2 (higher, not lower).
- Even 2003-2007 OOS (35% high-ry days): +2.06% 20d fwd at ry >= 2.2.
- Effect only inverts at ry >= 2.5 (n=110, weak).
- **Filter would suppress correct-direction days.**

### Refined understanding — failure mode is INTRADAY
- 3 of 4 launch LONG losses (07-01, 07-02, 07-09) closed UP intraday +1.1% to +1.6%.
- Daily direction was CORRECT. Intraday breakout failed and got stopped.
- 3 of 4 losses never reached target within 24h (from 15m bar replay).
- **Root cause: OR breakout mechanic gets whipsawed in trending-but-choppy regime.** Not a macro-directional problem.
- Real research direction: intraday microstructure filters (entry-vs-prior-close chase, OR range vs daily range, timing within OR window).

## Artifacts shipped

- `scripts/shadow_replay.py` — evaluate candidate filters on forward log
- `scripts/halt_and_bonferroni.py` — halt-threshold + Bonferroni-6 test
- `scripts/oos_real_yield_regime.py` — 20-year OOS regime test
- `scripts/halt_monitor.py` — automated 2x-DD watch (verdict GREEN at 0.63x ratio)
- `src/shadow_log.py` — added `slope_gt_8` candidate
- `docs/experiments/2026-07-13_slope_gt_8_shadow.md` — pre-reg
- `docs/experiments/2026-07-13_shadow_candidates_batch.md` — 3-candidate design (real_yield REJECTED pre-apply)
- `docs/ops/vps_migration_checklist.md` — full Hetzner CX22 + systemd + healthchecks.io playbook
- `data/experiments/registry.json` — 4 new trial entries (Bonferroni-N updated to 21)
- `data/halt_state.json` — current verdict GREEN, ratio 0.63x

## Verdicts

| Candidate | Verdict |
|---|---|
| `real_yield_gt_2_2` (LONG-only) | **REJECTED pre-apply** — OOS regime test fails. Would suppress correct-direction days. |
| `slope_gt_8` | SHADOW live — small n, in-sample overfit risk |
| `prior_day_range_gt_80` | SHADOW pending apply (post-CPI) — weakest of remaining 3 |
| `gap_after_down_day` (LONG-only) | SHADOW pending apply (post-CPI) — n=2 skips, high overfit |

## Halt monitor readings (at 10:56 UTC — updated with bootstrap + SPRT)

- Trades since launch: 10 (1W/9L, 10% win rate)
- Realized max DD: -$12,548 (~12.5% of $100k assumed capital)
- **Reference max DD: $13,695** (bootstrap p95 from pre-launch 14-trade null, M=10000, n=10 horizon). Replaced $20k placeholder.
- **DD ratio: 0.92× — approaching AMBER on capital-preservation lens**
- **SPRT: HALT** (pre-registered p0=0.57, p1=0.35, alpha=beta=0.05). log-LR = +3.23 > boundary +2.94.
- **Combined verdict: HALT** (SPRT authoritative; overrides DD-GREEN per framework)
- **Verdict transition: GREEN -> HALT at 10:56 UTC**
- Bootstrap non-parametric validation confirms halt is robust:
  - Empirical p(1 win in 10 | pre-launch null) = 0.31%
  - Parametric P(X<=1 | Bin(10,p)) < 0.05 for all p >= 0.45
  - Halt call not sensitive to hypothesis choice
- Note: user must confirm actual account capital; $100k is placeholder

## 🚨 CRITICAL FINDING (14:20 UTC): LIVE/BACKTEST STRATEGY DIVERGENCE

`src/dispatch_orb.py:528` — live only applies one OR/ATR filter:
```python
or_max = cfg.get("or_vs_atr_max", 2.0) * cur_atr
if or_range > or_max: skip
```

`src/edge_session_orb_v7_final.py` (backtest) applies per-session filters:
- LON: `or_vs_atr_max: 2.0` (skip if OR > 2×ATR) — **matches live** ✓
- NY: `or_vs_atr_min: 2.5` (skip if OR < 2.5×ATR) — **NOT in live** ❌
- ASIA: `or_atr_deadzone: (2.0, 2.5)` — **NOT in live** ❌

**Live effect:** NY and ASIA sessions fall through to the DEFAULT `or_vs_atr_max=2.0` — LON's filter is silently applied to them. Filter direction is INVERTED vs intent for NY.

**Verified:**
- 07-13 NY (today): OR 21.90, ATR 5.32 → LON-default filter said 21.90 > 10.64 → skip. Correct outcome, wrong filter.
- 07-09 NY: OR 12.00, small ATR (~4-5) → filter passed → LONG entered → -$1,224 loss.

**Implications:**
1. Live is running a DIFFERENT strategy than backtest.
2. DSR audit (2026-07-07) validated backtest — doesn't apply to live.
3. SPRT halt call (H0=57% backtested win rate) may be testing wrong hypothesis.
4. v7.1 accuracy claim (+75% mean/trade) never actually deployed as intended.
5. Today's regime analysis assumed live=backtest — needs re-framing.

**Decision paths:**
1. Fix live to match backtest (add per-session filters in dispatch_orb.py). ~30 LOC.
2. Fix backtest to match live (remove min/deadzone). Re-run backtest for honest live metrics.
3. Accept divergence, re-baseline SPRT to actual live.

**Do NOT ship any strategy change without deciding this first.** All other filter work is downstream of this.

## HALT DECISION PENDING FROM USER

**Impact if HALT accepted:**
- Skip NY session at 2026-07-13 13:30 UTC (post-CPI) and all subsequent ORB entries
- Shadow-log continues for what strategy WOULD have decided
- Re-entry per pre-registered conditions (docs/experiments/2026-07-13_reentry_conditions_prereg.md)

**Re-entry paths (pre-registered):**
- Path A (shadow recovery): shadow accumulates >= +$27,390 AND >=5 consecutive would-take at >=60% win
- Path B (regime): real_yield<2.0 for 30 consecutive days AND shadow>=0; first 5 live trades at 50% size
- Path C (new strategy): v7.3+ passes DSR AND new SPRT pre-reg
- Hard stop: retire if none fire by 2026-10-13

## Open questions

- Actual account capital (for 20% floor calibration)
- Should we ship shadow candidates for intraday-chop filters (OR range vs daily range, entry-vs-prior-close)?
- VPS migration: post-CPI window (14:00 UTC onward)
