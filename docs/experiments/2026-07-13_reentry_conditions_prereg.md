# Pre-registration: SPRT halt re-entry conditions

**Registered UTC:** 2026-07-13T11:05:00Z
**Applies to:** `sprt_v72_1_launch` halt decision (see `2026-07-13_sprt_prereg.md`)
**Owner:** Knox
**Purpose:** Define un-halt criteria BEFORE the halt-vs-override decision, so the choice to re-enter live capital isn't influenced by emotional shadow-recovery observation.

## Why pre-register re-entry

The quant framework's containment doctrine (memory: `quant_framework_gold.md` Q1) says: keep signal in shadow when halted; if shadow-equity recovers, re-enter mechanically. "Mechanically" means the re-entry trigger is defined in advance, not decided in the moment. Otherwise we drift into "hopeful" re-entries after 2 shadow wins and get chopped up again.

## Framework — three re-entry paths

### Path A: SHADOW-RECOVERY re-entry (default)

**Applies when:** halt was triggered by SPRT (edge-broken evidence). Re-enter when shadow-equity independently signals edge recovery.

**Trigger:** shadow-equity accumulates ≥ **+2× reference max DD** ($27,390 at current bootstrap) in profits since halt point, AND that recovery includes ≥ **5 consecutive shadow "would-take" outcomes with ≥ 60% win rate**.

**Rationale:** we need both magnitude proof (that shadow shows the edge is back, not tail luck) AND rate proof (≥60% win rate over 5+ trades) before committing capital. The +2× reference DD magnitude is symmetric with the halt trigger.

### Path B: REGIME-CHANGE re-entry

**Applies when:** the regime that broke the strategy has demonstrably shifted.

**Trigger:** 10y TIPS real yield drops below 2.0 for **30 consecutive trading days**, AND shadow-equity is positive since halt.

**Rationale:** if today's failure mode is intraday chop in high-real-yield regime (per 07-13 finding), a regime shift back to <2.0 real yield removes the environmental trigger. 30-day window is chosen to avoid regime-flip head-fakes.

**Note:** even under regime-change re-entry, the first 5 live trades run at **50% position size** until shadow-continuous-recovery is also confirmed.

### Path C: STRATEGY-VERSION re-entry

**Applies when:** we ship v7.3 (or later) with a change addressing the identified failure mode.

**Trigger:** new strategy version passes full DSR gate (SR > 0.95 after Bonferroni on N-considered) AND a new SPRT pre-reg is registered against the new version. Old halt is closed; new SPRT begins.

**Rationale:** if we fix the strategy, the old halt is no longer relevant to the new one. But we still start a new SPRT to catch the case where our "fix" doesn't work either.

## What COUNTS as shadow-equity for Path A

- **Shadow-equity trade:** an ORB PLAN that fires under v7.2.1 in the halt window, with entry/exit price backfilled from historical bars (per `scripts/shadow_replay.py` pattern).
- **Cost model:** same $24/contract round-trip as live.
- **P&L:** computed as if we took the trade with same position sizing.

Shadow-equity is tallied in `data/shadow_equity_since_halt.jsonl` (new file, created on halt).

## What DOES NOT count

- Manual "what if" analyses done outside the shadow logger.
- Cherry-picked hindsight winners.
- Trades under new strategy versions (those trigger Path C, not Path A).

## Escalation to user

Halt monitor's state file (`data/halt_state.json`) surfaces re-entry candidacy each tick. Private Telegram alert fires when:
- Path A magnitude threshold crossed (≥ +$27,390 shadow-equity since halt)
- Path B regime threshold crossed (real_yield < 2.0 for 30 days)
- Path C: user manually ships a new strategy version

**Final re-entry decision remains a manual user action.** The pre-reg defines when the SYSTEM will FLAG, not when the user MUST re-enter. But rejecting a flagged re-entry requires explicit rationale in the registry (same standard as overriding a halt).

## Hard stop

If NONE of Paths A/B/C fires by **2026-10-13** (3 months from halt), the strategy is retired. Un-retirement requires a full new preregistration.

## Registry entry

Added to `data/experiments/registry.json` as `sprt_v72_1_reentry_prereg`.
