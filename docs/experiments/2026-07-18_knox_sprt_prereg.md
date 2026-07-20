# Knox SPRT pre-registration — activates at shadow n=50

**Registered UTC:** 2026-07-18T09:00:00Z
**Trial id:** `knox_sprt_prereg` (to be added to `data/experiments/registry.json` on activation)
**Owner:** Knox
**Status:** PRE-REGISTERED (dormant until Knox shadow n reaches 50)

## Purpose

Engine A's SPRT (`sprt_v72_1_launch_path_y`, H0=0.52 vs H1=0.35) tested v7 Path Y. Engine B (Knox) is a different strategy — same OR mechanic but with `daily_slope_consistency` filter that skips counter-trend breakouts. Its win rate has different priors and different failure modes.

Knox needs its OWN halt discipline. This doc pre-registers Knox's SPRT parameters BEFORE seeing enough data to fit them to a preferred narrative. The activation trigger (n=50 shadow) is chosen so we have some evidence for H0 calibration but not so much that the choice is retrospective.

## Activation protocol

When `scripts/shadow_ship_gate_report.py` reports Knox shadow n ≥ 50:

1. Run `scripts/knox_sprt_activate.py` (to be written on activation, not now).
2. Script computes Knox's observed shadow win rate on the first 50 decisions.
3. H0 = observed shadow win rate, clamped to [0.45, 0.60].
4. H1 = H0 − 0.15, floored at 0.30.
5. alpha = beta = 0.05 (matches Engine A convention).
6. Boundaries: A_halt = +ln((1-beta)/alpha) ≈ +2.944, B_safe = ln(beta/(1-alpha)) ≈ −2.944.
7. Trial added to `registry.json` with `id="knox_sprt_launch"`, `verdict="pre_registered"`.
8. SPRT reading computed on Knox's live-published research alerts (NOT shadow decisions — only what actually got sent to `GOLDTRADER_TG_CHAT_RESEARCH`).
9. Halt fires when log-LR crosses either boundary.

## What Knox SPRT tests

**Not** the same hypothesis as Engine A's SPRT. Specifically:
- Sample: Knox alerts that were dispatched to the research channel (post-2026-07-18).
- Not the full shadow log — only what was actually published.
- This ensures Knox is tested on decisions users actually saw.

## Halt actions

If Knox SPRT halts (log-LR ≥ +2.944):
1. `scripts/knox_kill.py off "SPRT halt log-LR=X.XX at n=Y"` — flips state file.
2. Auto-post to research channel: "🛑 Knox SPRT halted at n=X. Pausing signals. Re-entry conditions in next-session review."
3. Weekly report continues, showing halted state.
4. Halt is not automatically reversible. Requires:
   - Explicit user go-ahead AFTER analysis of the halt cause
   - New pre-registration if hypothesis needs changing (must be new trial id, cannot re-run same pre-reg)

## Safe-side (log-LR ≤ −2.944)

If Knox SPRT crosses SAFE boundary (accept H0, reject H1):
1. This is NOT auto-promotion to public. It's just "Knox is not decisively broken."
2. Public-promotion still requires: shadow n=100, precision≥60%, CI clears zero, VPS stable 30d, explicit user go-ahead.
3. SAFE side is a green light to KEEP running research alerts, not to launch commercially.

## Interaction with ship gates

Knox has three independent gate systems:

| System | What it does | Trigger to promote | Trigger to kill |
|---|---|---|---|
| Shadow ship gate | Statistical filter validation | n=100 + precision + CI + skip-rate | precision<55% at n=100, skip>40%, hard-stop |
| Knox SPRT | Live-alert halt monitor | SAFE crossing at n=? | HALT crossing |
| Hard stop | Backstop | — | 2026-10-13 |

All three must remain green. Any single gate saying "kill" pauses Knox. Only ship-gate + SPRT-SAFE + user go-ahead promotes.

## Why n=50 and not n=100

The shadow ship gate is at n=100 (validation). SPRT operates on ACTUAL dispatched alerts (a subset of shadow decisions — only those where both engines agreed to take). At current rates, n=50 dispatched alerts ≈ n=75-100 shadow decisions. SPRT is running SLIGHTLY ahead of the ship gate so we can halt bad live behavior before waiting for the full validation cycle.

## What could invalidate this pre-reg

1. If shadow accumulation shows Knox win rate is well outside [0.45, 0.60] range, the clamp will make H0/H1 artificial. Mitigation: at activation, if raw observed rate is <0.40, publish a note ("Knox shadow shows sub-40% raw rate; SPRT calibration used clamped H0=0.45 — treat SPRT continuation as weak evidence") and proceed anyway. Never adjust the clamp AFTER seeing the data.
2. If Engine B's dispatch rate is very low (<5 alerts/month), SPRT will take too long to be actionable. Mitigation: at n=50 dispatched alerts, if elapsed >12 weeks, re-evaluate whether SPRT is the right monitor vs. a simpler bootstrap-CI approach. Document decision either way.
3. If the daily-slope-consistency filter's regime conditions change (e.g., ry drops below 2.0 for 30+ days), Knox may behave differently than it did in the pre-reg-era shadow. This is expected and does NOT invalidate SPRT — just document the regime shift alongside the SPRT reading.

## Compliance with quant framework

- **Pre-registration:** ✅ this doc, before seeing n=50 data
- **Bonferroni-N:** ✅ trial entry will be added on activation
- **Reproducibility:** activation script is deterministic given the shadow log; H0/H1 are functions of observed data with pre-specified clamps
- **No adjustment of gates AFTER seeing data:** enforced by "cannot re-run same pre-reg" rule
