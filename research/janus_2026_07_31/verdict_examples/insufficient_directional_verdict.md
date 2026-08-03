# Path B dynamic-threshold verdict — 2026-07-27 (past-due gate exec)

**Pre-reg:** `research/library/dynamic_funding_threshold_design_2026_07_04.md`
**Execution notes:** `research/library/path_b_07_18_verdict_execution_notes_2026_07_13.md`
**Interim (n=79):** `research/library/path_b_shadow_interim_verdict_2026_07_08.md`
**Gate scheduled:** 2026-07-18 (executed 9 days late per past-due sweep)

## Verdict: INSUFFICIENT-DIRECTIONAL — continue SHADOW to 2026-08-01

No LIVE changes. `FUNDING_REVERT_DYNAMIC_THRESHOLD_LIVE_ENABLED` stays
whatever it currently is (unchanged). SHADOW annotation continues.

## Numbers vs locked decision tree

Aggregate over 2026-07-04 → 2026-07-27 (23 days):

| bucket | n | mean R | CI95 | win % |
|---|---|---|---|---|
| PASSED | 418 | +0.104R | [+0.027, +0.181] | 30.1% |
| filtered | 93 | +0.185R | [+0.009, +0.361] | 47.3% |

**PASSED − filtered = −0.081R**

Decision tree application:

- n_total = 511 ≥ 200 ✓ (sample floor met)
- \|PASSED − filtered\| = 0.081R < 0.15R → **INSUFFICIENT-DIRECTIONAL**

Neither SHIP-DIRECTION (delta ≥ +0.15R) nor REMOVE (delta ≤ −0.15R)
threshold met.

## Direction check

Inversion (filtered > PASSED) PERSISTS but is diminishing as sample grows:

- n=79 (07-08 interim): PASSED − filtered = **−0.400R**
- n=511 (today): PASSED − filtered = **−0.081R**

The interim doc's "sample noise" interpretation is winning against
"regime dependence." Direction is still wrong for the gate's intent,
but by less than the −0.15R kill threshold.

## Per-symbol LIVE additions (base_n ≥ 50, delta ≥ +0.15R, pass_mR > 0, fail_n ≥ 15)

No symbol qualifies:

- **PEPEUSDT** (pass_n=41, filt_n=16): delta = +0.624R ✓, direction ✓,
  but pass_n < 50 → FAIL sample floor.
- **WIFUSDT** (pass_n=23, filt_n=18): delta = −0.730R → wrong direction.
- **OPUSDT** (pass_n=5, filt_n=22): delta = −0.691R → wrong direction.
- All others: either pass_n < 50 OR fail_n < 15 OR wrong-direction delta.

Consistent with pre-reg's expectation: "no LIVE list changes" was the
predicted outcome.

## Action

- Continue SHADOW annotation (env unchanged)
- No LIVE list changes (no additions, no removals)
- Recheck 2026-08-01 (matches the extended Path A deadline —
  bundle both)
- If inversion persists at n≥800 or worsens back below −0.15R,
  REMOVE gate per pre-reg's kill-switch path

## Kill switch

Clear `FUNDING_REVERT_DYNAMIC_THRESHOLD_LIVE_ENABLED` in Atlas .env if
inversion strengthens materially before next scheduled check.
