# v2 M20 percentile bucket replication check

**Date:** 2026-09-08
**Author:** Knox
**Status:** Replication check. Direct extension of `2026-09-08_v1_regime_and_m20_slices.md` to the v2 subset.
**Trigger:** The v1 M20 bucket analysis found the top-quintile M20 LONGs have Sharpe -0.67. Question for the v3 pre-reg case: does the pattern hold on v2's DXY-confirmed subset, or does v2's filter already remove the bad trades?

## Design (fixed, no re-tuning)

Same 5-quintile M20 bucketing as the v1 version. Same directional split. Same backtest window (2010-01-01 to 2026-07-01). Only difference: apply v2's DXY filter first (v1 LONG AND DXY_chg_20d < 0, or v1 SHORT AND DXY_chg_20d > 0), then bucket the surviving trades by M20 quintile within each direction.

Not a new discovery. Not new bucket boundaries chosen post-hoc. Direct replication.

## Results

**v2 LONG trades (n=161, DXY-confirmed):**

| bucket | n | M20 range | WR | mean $ | total $ | Sharpe |
|---|---|---|---|---|---|---|
| Q1_low | 33 | 0.34% to 2.30% | 66.7% | $122 | $4,040 | 0.85 |
| Q2 | 32 | 2.41% to 3.68% | 65.6% | $1,671 | $53,480 | 2.21 |
| Q3 | 32 | 3.77% to 5.35% | 62.5% | $1,185 | $37,923 | 2.05 |
| Q4 | 32 | 5.36% to 7.07% | 65.6% | $1,874 | $59,975 | 2.40 |
| **Q5_high** | 32 | 7.07% to 14.32% | 53.1% | -$1,156 | **-$37,002** | **-0.29** |

**v2 SHORT trades (n=106, DXY-confirmed):**

| bucket | n | M20 range | WR | mean $ | total $ | Sharpe |
|---|---|---|---|---|---|---|
| Q1_low | 22 | -12.07% to -6.01% | 59.1% | $1,083 | $23,823 | 0.23 |
| Q2 | 21 | -5.80% to -4.46% | 52.4% | $363 | $7,628 | 1.58 |
| **Q3** | 21 | -4.41% to -3.17% | 42.9% | -$241 | **-$5,051** | **-1.43** |
| Q4 | 21 | -3.11% to -1.92% | 52.4% | $888 | $18,655 | 1.76 |
| Q5_high | 21 | -1.91% to -0.17% | 52.4% | $1,049 | $22,039 | 0.65 |

**Extreme M20 (top 10% LONG / bottom 10% SHORT):**

| slice | n | WR | total $ | Sharpe |
|---|---|---|---|---|
| v2 LONG extreme (M20 >= 9.22%) | 17 | 52.9% | -$1,181 | 0.58 |
| v2 LONG non-extreme | 144 | 63.9% | $119,597 | 1.48 |
| v2 SHORT extreme (M20 <= -7.54%) | 11 | 45.5% | -$1,738 | -1.63 |
| v2 SHORT non-extreme | 95 | 52.6% | $68,832 | 0.97 |

## v1 vs v2 side-by-side

Q5_high LONG bucket (the finding under replication):

| variant | n | WR | Sharpe | cum $ | cliff from Q4 |
|---|---|---|---|---|---|
| v1 | 45 | 46.7% | -0.67 | -$50,683 | Q4 Sharpe 1.45 → Q5 -0.67 (2.12 gap) |
| v2 (DXY-filtered) | 32 | 53.1% | -0.29 | -$37,002 | Q4 Sharpe 2.40 → Q5 -0.29 (2.69 gap) |

## Findings

**1. The pattern REPLICATES.** Top-quintile M20 LONGs are still negative-Sharpe on v2 (Sharpe -0.29, cum -$37,002). The direction of the effect is preserved, and the "cliff" between Q4 and Q5 is even sharper on v2 (2.69 Sharpe gap vs v1's 2.12 gap). This is the key result and it validates the v3 direction.

**2. v2's DXY filter partially mitigates but does not eliminate the extreme-M20-LONG problem.** Of v1's 45 Q5 LONGs, v2 keeps 32 and drops 13. The 13 dropped trades were the "DXY-misaligned extreme-M20 LONGs" that v2 already correctly filters. But the remaining 32 still lose $37k cumulative and run at negative Sharpe. The DXY filter and the M20-extremity filter are picking up different bad-trade types; both would be needed for full coverage.

**3. On v2, the SHORT side ALSO shows an extreme-M20 bad zone, but in a very small sample.** SHORT with M20 <= -7.54% (n=11): Sharpe -1.63, cum -$1,738. Non-extreme SHORT (n=95): Sharpe 0.97. This didn't show as strongly on v1 (v1 extreme SHORT: Sharpe -0.30 but positive cum). Sample size is small enough (n=11) that I would not put weight on this as a standalone finding, but it's worth flagging for the pre-reg design decision (symmetric extremity filter vs LONG-only).

**4. The Q3 SHORT anomaly persists.** v1 SHORT Q3 Sharpe -1.00, v2 SHORT Q3 Sharpe -1.43. On both variants, moderate-negative-M20 SHORTs (M20 in the -4.4% to -3.2% range) underperform surrounding buckets. Not part of the M20-extremity story, but a real second-order feature.

**5. v2 LONG Q4 is the peak.** Sharpe 2.40, cum $60k on 32 trades. Combined with the Q1-Q4 average Sharpe of ~1.9, this makes v2 LONG (minus Q5) look extremely strong. The candidate "v2 minus extreme-M20-LONG" would be trading on precisely these good buckets.

## What this does NOT change

- Still no live rule changes. Pre-reg locked through 2027-01-22.
- Still requires a fresh pre-reg for the v3 candidate. This is a replication check, not a ship gate.
- The SHORT-side finding is too small a sample to inform pre-reg design yet.

## What this DOES change

The v3-candidate case is now stronger than it was this morning. To recap the evidence chain:

1. **v1 component ablation:** dropping M20 raises v1 Sharpe.
2. **v1 M20 bucketing:** top-quintile M20 LONGs have Sharpe -0.67.
3. **Live distribution audit:** 4 of 6 live signals sit at extreme high M20.
4. **v2 M20 bucketing (this doc):** top-quintile pattern replicates on v2 with a sharper Q4-vs-Q5 cliff.

The convergent evidence now spans TWO different signal sets (v1 and v2), not one. This is a materially stronger case for pre-reg drafting.

## Design decisions for the v3 pre-reg (informed but not decided)

- **Base rule:** should be v2 (DXY-filtered), since v2 is where the replication holds AND is the stronger baseline.
- **M20 threshold:** two options both defensible.
  - Fixed threshold (e.g., 7% for LONG). Simple, testable, arbitrary.
  - Rolling percentile (e.g., top 20% of trailing 3-year LONG signals). Adaptive, but adds a moving-part.
  - Pre-reg should lock one before backtest.
- **SHORT-side handling:** LONG-only filter, given the SHORT extreme-M20 sample is only n=11. Or a symmetric filter with a wider SHORT threshold. Or a threshold-based on the DIRECTIONAL bucket, not fixed at 10%. All defensible; needs to be locked pre-reg.
- **Ship gates:** should include cumulative P&L improvement (not just Sharpe), max DD improvement, AND matched-pair mean lift with permutation p-value. Same rigor as v3_ry_level's rejected pre-reg.
- **Bonferroni denominator:** N is now large-ish because of the 2026-09-08 discovery session. Conservative accounting: N=6 (adaptive daily probe, intraday probe, component ablation, M12 aggregators, live distribution, M20 buckets), or N=7 if the v2 replication counts.

## Files touched

- Script: `scripts/v2_m20_bucket_replication.py` (new)
- Doc: `docs/experiments/2026-09-08_v2_m20_bucket_replication.md` (this file)
