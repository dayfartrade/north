# Rolling 52-week percentile comparator for live signals

**Date:** 2026-10-12
**Author:** Knox
**Status:** Diagnostic tool, no live rule change.
**Trigger:** Queue item #3 from 2026-09-08 agenda: "live signals compared to trailing 52-week backtest distribution, not full 16-year. More informative given the ATR regime shift."

## Why this exists

The 2026-09-08 live-vs-backtest distribution audit showed that 4 of 6 recent live signals had M20 above the 85th percentile of the full-history (2010-2026) distribution. That full-history anchor is dominated by low-ATR, low-price regime years and is not representative of the regime any live signal fires in today. A rolling 52-week benchmark gives a regime-aware answer to the question "is this signal extreme for its current regime, or just extreme relative to 2015 gold?"

## Design (locked before run)

For each weekly signal date, compute percentile rank of each component (M20, M60, ATR, DXY_chg, RY_chg) against:
- (a) full historical distribution [2010-01-01, signal_date)
- (b) trailing 252-trading-day window ending at (but excluding) signal_date

Report both. Flag when the gap between (a) and (b) exceeds 20 percentile points - this is the "regime-shift tell."

Window scope: 2010-01-01 to data cutoff 2026-07-20 (Dukascopy 5m historical). Live calls between 2026-07-20 and 2026-10-12 are not covered by this analysis; they will be covered when Dukascopy data is next pulled.

## Signals in-sample (2026 directional, n=18)

### LONGs - M20 extremity by full vs trailing-52w

| date | M20 | full pctl | 52w pctl | full top20 | trail top20 |
|---|---:|---:|---:|---:|---:|
| 2026-01-09 | +4.89% | 84% | 56% | YES | |
| 2026-01-16 | +5.92% | 89% | 64% | YES | |
| 2026-01-30 | +13.01% | 99% | 96% | YES | YES |
| 2026-02-06 | +10.10% | 98% | 90% | YES | YES |
| 2026-02-13 | +9.68% | 98% | 86% | YES | YES |
| 2026-02-20 | +2.46% | 67% | 40% | | |
| 2026-02-27 | +7.81% | 94% | 74% | YES | |
| 2026-03-06 | +4.18% | 79% | 50% | | |

### SHORTs (through 2026-07-10, n=10)

| date | M20 | full pctl | 52w pctl |
|---|---:|---:|---:|
| 2026-03-20 | −12.07% | 0% | 0% |
| 2026-05-15 | −6.01% | 5% | 7% |
| 2026-05-22 | −4.24% | 11% | 10% |
| 2026-05-29 | −1.65% | 28% | 20% |
| 2026-06-05 | −8.19% | 1% | 4% |
| 2026-06-12 | −7.08% | 3% | 8% |
| 2026-06-19 | −7.85% | 2% | 6% |
| 2026-06-26 | −9.91% | 1% | 4% |
| 2026-07-03 | −3.50% | 15% | 21% |
| 2026-07-10 | −2.30% | 22% | 27% |

### Headline count

| metric | count | share |
|---|---:|---:|
| 2026 directional LONGs | 8 | - |
| LONG with M20 in full-history top 20% | 6 | 75% |
| LONG with M20 in trailing-52w top 20% | 3 | 38% |
| 2026 directional SHORTs | 10 | - |
| SHORT with M20 in full-history bottom 20% | 7 | 70% |
| SHORT with M20 in trailing-52w bottom 20% | 7 | 70% |

The LONG scoping differs by ~2× between the two benchmarks. The SHORT scoping does not change meaningfully.

## ATR regime shift - most visible decoupling

Recent ATR readings sit at the top of the full-history distribution but only in the middle-upper range of the trailing-52w distribution:

| date | ATR | full pctl | 52w pctl | gap |
|---|---:|---:|---:|---:|
| 2026-02-06 | 230.6 | 100% | 100% | 0 |
| 2026-06-05 | 100.7 | 98% | 64% | **−34** |
| 2026-06-12 | 109.8 | 98% | 68% | **−30** |
| 2026-06-26 | 116.8 | 98% | 71% | **−27** |
| 2026-07-03 | 120.0 | 98% | 72% | **−26** |
| 2026-07-10 | 105.2 | 98% | 57% | **−40** |

The post-Feb-2026 ATRs look "99th-percentile extreme" by full-history standards and completely routine by trailing-52w standards. Any filter keyed on absolute ATR level would miscategorize current regime.

## Findings

**1. The "extreme M20 LONG" phenomenon has two very different population counts depending on the benchmark.** Using full-history top-20%: 6 of 8 LONGs qualify (75%). Using trailing-52w top-20%: 3 of 8 LONGs qualify (38%). This is a 2× difference. The v3 pre-reg threshold choice has to pick one before any backtest; the choice affects base rates substantially.

**2. SHORT side is roughly invariant to benchmark choice.** Both benchmarks flag ~70% of the 2026 SHORTs as "bottom-20% M20" extreme. This is because the M60/M20 negatives in 2026 are already outside normal 52w range too. For the SHORT side, benchmark choice is not pivotal.

**3. Three LONGs are "extreme both ways" - the strongest candidates for a v3 filter to catch:**
- 2026-01-30 LONG (M20=13.01%, full 99%, 52w 96%)
- 2026-02-06 LONG (M20=10.10%, full 98%, 52w 90%)
- 2026-02-13 LONG (M20=9.68%, full 98%, 52w 86%)

These are the ones a rolling-percentile v3 filter would catch. A fixed-threshold v3 filter (M20 ≥ 7%) would catch these PLUS 2026-01-16 (M20=5.92%, trail 64%) and 2026-02-27 (M20=7.81%, trail 74%) - potentially trading some good signals away.

**4. ATR regime shift is unambiguous.** Any live rule that uses ATR level in an absolute sense will mis-fire in the current regime. v1 uses ATR for stop sizing (2×ATR), which is adaptive and fine; this analysis would matter for any filter that said "trade only when ATR < X" or similar.

## Implications for the v3 pre-reg

**Threshold rule choice (locked before backtest):**

Two defensible options:

- **Option A - Fixed threshold.** `M20 > 7%` triggers "skip LONG." Simple, pre-reg-friendly, directly implements the 2026-09-08 Q5 finding. But fixed thresholds decay as regime shifts.
- **Option B - Rolling top-quintile.** `M20 > 80th percentile of trailing 252d M20 distribution` triggers "skip LONG." Adaptive, more selective in the recent regime (would miss 2 of 5 LONG-mode trades on 2026 live, including 2026-02-27 which the fixed rule catches).

**Decision principle for the pre-reg:** choose Option A for the first v3 candidate. Rationale:
1. The 2026-09-08 finding was explicitly keyed on M20 > 7% in full-history terms; using the rolling benchmark would be sliding to a different hypothesis.
2. Simpler rules are more robust to overfitting critiques.
3. Rolling-percentile is a legitimate second candidate but should be its own pre-reg if proposed later.

Lock the fixed-threshold rule for v3-candidate-A. Document rolling-percentile as a deferred second candidate.

## Operational use of this tool

The CSV output `data/experiments/rolling_52w_percentile_recent.csv` is suitable for weekly report augmentation - the "signal context" cell could show both the full-history and trailing-52w percentiles when a live signal is published. This is a reporting enhancement, not a trading rule change, and it directly addresses the product goal of "regime-aware transparency."

Candidate wording in weekly report:
> This week's M20 of +X% sits at the Nth percentile of the full backtest sample (2010-2026) and the Mth percentile of the trailing 12-month window.

No commitment to shipping this yet. Flag for Rook/Vega review when the pre-reg window ends.

## Files touched

- Script: `scripts/rolling_52w_percentile_comparator.py` (new)
- Data: `data/experiments/rolling_52w_percentile_recent.csv`
- Doc: `docs/experiments/2026-10-12_rolling_52w_percentile_comparator.md` (this file)

## What this does NOT change

- No live rule change.
- No pre-reg modification.
- Does not change the v3 threshold-choice recommendation (fixed-threshold v3-candidate-A stays the primary target).

## What this DOES change

- Quantifies regime-shift effect on scoping (2× LONG population difference).
- Confirms ATR regime shift (expected).
- Provides tooling for optional weekly-report augmentation (deferred).
- Adds +1 to Bonferroni discovery count. New total: **N=9**.
