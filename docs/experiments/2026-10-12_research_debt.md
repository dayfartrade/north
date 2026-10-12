# Research debt - deferred findings that need fresh data to progress

**Date:** 2026-10-12
**Author:** Knox
**Status:** Living document. Updated when new items appear or existing items resolve.
**Purpose:** Record findings that are real-looking but under-sampled or compromised, with explicit replication conditions. Prevents loss between sessions.

## Why this doc exists

Several analyses during the 2026-09-08 and 2026-10-12 sessions surfaced effects that look striking but have one of two problems:

1. Sample size too small for a pre-reg (n less than ~20 is the rough cutoff).
2. The author has prior exposure (as with the voided v3-m20 pre-reg), making a fresh pre-reg against the same data impossible.

These findings cannot be acted on now but should not be forgotten. This doc names them with explicit replication conditions so a future session can pick them up correctly.

## Debt item 1: M6_FLIP SHORT

**Finding:** When the 6-month trend disagrees with the 3-month and 12-month trends (M6 opposite sign, M3 and M12 same sign), SHORT trades perform strikingly badly.

- v1 M6_FLIP SHORT: n=16, WR 25.0%, mean −$1,190, cum −$19,038, Sharpe −2.95
- v2 (DXY-filtered) M6_FLIP SHORT: n=9, WR 22.2%, mean −$1,646, cum −$14,813, Sharpe −3.37

**Why not actionable now:**

- Sample size too small. n=9 on v2 is below the rough threshold for pre-reg confidence.
- No independent replication sample. The 2010-2026 Dukascopy data was used to discover this.

**Replication conditions required:**

- At least 10 additional M6_FLIP SHORT occurrences in a sample the author has not seen.
- Fresh pre-reg declaring the finding as a prior hypothesis under test.
- Appropriate Bonferroni-N inclusion (contributes +1 to N for any pre-reg testing related SHORT-side filters).

**How to detect eligibility:** when Dukascopy data extends past 2026-07-20 and includes at least 3 months of SHORT regime, run `scripts/regime_disagreement_trade_analysis.py` restricted to the new data only. Count M6_FLIP SHORT occurrences. If ≥ 10, consider drafting a pre-reg.

**Doc trail:** `docs/experiments/2026-10-12_regime_disagreement_trade_analysis.md`.

## Debt item 2: Rolling 52w percentile M20 threshold

**Finding:** A rolling-percentile formulation of the M20 extremity filter would scope differently than a fixed-threshold formulation. For 2026 LONG signals: 3 of 8 qualify under rolling top-20%, vs 6 of 8 under fixed-threshold ≥ 7%.

**Why not actionable now:**

- The underlying extreme-M20-LONG hypothesis itself is in the compromised zone (author saw the voided v3-m20 retrospective; see Bonferroni reconciliation doc).
- Pursuing the rolling-percentile variant now would be hypothesis-slide: the author would be adjusting the threshold formulation based on knowledge of what the fixed-threshold version produced.

**Replication conditions required:**

- Fresh data where the author has NOT seen either fixed-threshold or rolling-percentile retrospective results.
- Pre-reg declares the rolling-percentile formulation up front with locked window (252 trading days) and locked threshold (top 20% of trailing-window M20 for LONG signals).

**Doc trail:** `docs/experiments/2026-10-12_rolling_52w_percentile_comparator.md`.

## Debt item 3: SHORT-side M20 extremity

**Finding:** v2 SHORT trades with M20 ≤ −7.54% (bottom-10% M20): n=11, Sharpe −1.63. Looks pathological but tiny sample.

**Why not actionable now:**

- n=11 is too small for a pre-reg.
- The pattern was discovered in the same v2 bucket replication analysis that discovered the LONG-side pathology, so Bonferroni cost compounds if both are included in a future pre-reg.

**Replication conditions required:**

- Doubled sample size in a dataset the author has not seen.
- Pre-reg must explicitly declare whether SHORT-side extremity is being tested standalone or jointly with LONG-side extremity (joint test needs tighter α).

**Doc trail:** `docs/experiments/2026-09-08_v2_m20_bucket_replication.md`.

## Debt item 4: Q3 SHORT anomaly (v1 and v2)

**Finding:** Moderate-negative-M20 SHORTs (M20 between −4.4% and −3.2%) underperform both adjacent buckets on both v1 (Sharpe −1.00) and v2 (Sharpe −1.43). Not an extremity story; a middle-bucket dip.

**Why not actionable now:**

- No credible mechanism proposed. The pattern is empirical only.
- Any filter would be ad-hoc post-hoc bucket-boundary fitting.

**Replication conditions required:**

- A plausible mechanism (what economic reason would these M20 values behave differently?). Without a mechanism, this is just a bucket artifact.
- Replication in a dataset the author has not seen.

**Doc trail:** `docs/experiments/2026-09-08_v2_m20_bucket_replication.md`.

## Not research debt - already resolved or rejected

For completeness, items that LOOK like they should be here but have been actively rejected:

- **Blanket regime-disagreement filter.** Tested and REJECTED on 2026-10-12. Disagreement is actually BETTER on both v1 and v2. Not debt; moved to development story.
- **v3-m20 (fixed-threshold extreme-M20-LONG filter).** Pre-reg VOIDED on 2026-10-12 due to author discipline violation. Not debt; moved to retirement wall. Future work on this specific hypothesis is Debt item 2 above (rolling-percentile variant on fresh data) or requires an entirely new approach.
- **Any universe expansion (silver, GDX, GDXJ, palladium, platinum, BB(20,2), seasonality).** All rejected on their own pre-regs through August 2026. Not revisit candidates without a reason.

## Review cadence

This doc should be reviewed at the start of any session that proposes a v3-class candidate against the gold weekly sample. The purpose is to prevent the author from accidentally testing an "already-flagged-as-debt" hypothesis without honoring its replication conditions.

Next review trigger: whichever comes first of (a) Dukascopy data available past 2026-07-20, (b) 10+ new live weekly resolves, or (c) explicit user request to revisit v3-class work.
