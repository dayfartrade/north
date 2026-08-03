# Tier=medium routing expansion pre-reg — 2026-07-18

**Author:** Janus 2026-07-18
**Trigger origin:** post-fix perf re-read Priority 1 (`project_2026_07_18_perf_reread.md`) surfaced tier=medium POSITIVE EDGE at n=49 clean. Full re-audit (`project_2026_07_18_perf_reread.md` + follow-up relay) confirmed 30d contamination-diluted picture is INDIST but post-fix subset is POSITIVE. Small-n regression risk requires locked evaluation gate.
**Status:** PARKED, not shipping. This doc locks the decision rule; a separate operator go-ahead is required at gate to act on any verdict.

## Background

Auto-trader currently routes only `funding_extreme_revert` tier=low per
`AUTO_TRADER_FUNDING_REVERT_ALLOWED_TIERS=['low']`. This routing was
established by the 2026-07-07 audit (n=558) which showed:

- tier=low     n=316  WR 67.1%  meanR +0.439R  POSITIVE EDGE
- tier=medium  n=237  WR 45.6%  meanR -0.033R  INDIST (flat)
- tier=high    n=  5  WR  0.0%  meanR -0.800R  NEGATIVE (small n)

Today (2026-07-18) re-audit at n=850 30d full + n=50 post-fix clean shows:

| Cut | tier=low | tier=medium |
|---|---|---|
| 30d FULL (contains bug contamination) | n=329, +0.425R, CI [+0.313, +0.537], **POSITIVE** | n=506, +0.053R, CI [-0.020, +0.127], INDIST |
| POST-FIX 3d clean | n=1 INSUFFICIENT | n=49, +0.518R, CI [+0.226, +0.810], **POSITIVE** |

The 30d cut confirms tier=low routing is still validated (same finding
as 07-07). The post-fix medium finding is the new signal — but n=49
is well below the pre-reg n≥200 discipline we applied to Path B today.

## Hypothesis being tested

**H0:** tier=medium mean R = 0 (or negative) at n≥200 clean data
**H1:** tier=medium mean R > 0 with CI95 lower bound ≥ +0.15R at n≥200 clean data

If H1 holds at gate, tier=medium routing is safe to expand into. If H0
holds, current tier=low-only routing is preserved.

## LOCKED evaluation criteria

**Sample:** funding_extreme_revert setups with `confidence_tier='medium'`
resolved (`status IN ('tp1_hit','tp2_hit','sl_hit','expired')`) with
`created_at >= 2026-07-15 14:00:00+00`. Post-fix window only — NO
mixing with contaminated pre-fix data.

**Decision rule (ALL must hold to expand routing):**

1. **n_medium_clean ≥ 200** — matches Path B pre-reg's sample floor
2. **CI95 lower bound ≥ +0.15R** — meaningful-edge threshold, matches
   Path B pre-reg's directional-significance floor
3. **Mean R ≥ +0.15R** — sanity check on the point estimate
4. **Per-symbol drill-down** — no single symbol contributes > 40% of
   the positive edge (guards against one-symbol dominance masking a
   generally-negative slice)

**Verdict outcomes:**

- **PASS all 4:** SHIP recommendation. Env change:
  `AUTO_TRADER_FUNDING_REVERT_ALLOWED_TIERS=low,medium`. Still gated
  on operator explicit go-ahead (same as auto-trader re-enable was).
- **FAIL sample floor (n < 200):** INSUFFICIENT-SAMPLE. Continue
  observation. Next gate: 2026-08-15 calendar OR n=200 whichever
  first.
- **PASS sample floor, FAIL edge criterion:** PARK. Document. Do
  NOT re-tune the +0.15R threshold. Reconsider at next major perf
  cut (~2026-09-01) if regime changes.

## Calendar trigger

**Whichever fires first:**

- **Calendar:** 2026-07-28 (10 days out; ~16 medium/day post-fix cadence
  puts n=200 in the same neighborhood)
- **Data:** n_medium_clean ≥ 200

## What NOT to do

- **Do NOT expand routing on the current n=49 read.** The CI is wide
  ([+0.226, +0.810]); at n=200 the mean could regress toward the 30d
  full picture (which was flat). This is exactly the small-sample
  fishing hazard the pre-reg exists to prevent.
- **Do NOT expand to tier=high.** 30d n=15 too small, WR 6.7%
  actively bad. High-tier is out of scope for any expansion decision
  under this pre-reg.
- **Do NOT re-tune the +0.15R meaningful-edge threshold** if data at
  gate shows CI lower bound of e.g. +0.10R. Same discipline as Path B
  pre-reg: locked = locked.
- **Do NOT rely on the 30d full cut for the expansion decision.** The
  bug window dilutes mean_r for both tiers uniformly, but the
  contamination is not clean-random — it's concentrated in one 4-day
  span. Only post-fix data can honestly answer the question.
- **Do NOT drop tier=low routing** even if tier=medium expands. Both
  tiers route; low remains the higher-confidence slice.

## Kill switch

If tier=medium is expanded and then underperforms live:
- Env-only revert: `AUTO_TRADER_FUNDING_REVERT_ALLOWED_TIERS=low`
- Next scanner cadence picks up (~5-15min)
- Auto-trader integration falls back to tier=low-only routing
- Zero code change, zero deploy

## Query to run at gate

Same as today's follow-up relay, just with `created_at >= '2026-07-15
14:00:00+00'` cutoff. Report:
- n, mean_r, CI95, WR per tier
- Per-symbol breakdown for tier=medium (drill-down for criterion #4)

## Cross-references

- Prior tier audit: `per_symbol_edge_tier_low_audit_2026_07_07.md`
- Today's re-audit context: `project_2026_07_18_perf_reread.md` +
  `project_2026_07_18_auto_trader_reenabled.md` (Janus memory)
- Path B pre-reg (analogous discipline pattern):
  `path_b_07_18_verdict_execution_notes_2026_07_13.md`
- Auto-trader config surface: `src/auto_trader/config.py::funding_revert_allowed_tiers`

## Pre-reg discipline note

This pre-reg was written BEFORE the gate fires. If the 2026-07-28
data shows POSITIVE tier=medium at n≥200 with CI clearing +0.15R,
that's a locked SHIP recommendation — no re-review of the criteria.
If it FAILS any criterion, that's a locked PARK — no fishing for a
different threshold that would make it pass. The "no fishing" rule
applies here identically to Path B.
