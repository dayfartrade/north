# Live vs backtest signal-component distribution audit

**Date:** 2026-09-08
**Author:** Knox
**Status:** Diagnostic snapshot. Most consequential finding of the day.
**Trigger:** N=6 live calls now on the board. Question: are the market conditions v1 is firing (or not firing) in live actually in-distribution with the 2010-2026 backtest sample, or are we in a regime the backtest didn't sample well?

## Distributions side-by-side

Every published call from `data/far_weekly_calls.jsonl` (n=6 to date), compared to the backtest signal-date sample (n=829 weekly signal rows over 2010-2026):

| variable | backtest N | backtest mean | backtest std | backtest p05/p50/p95 | live N | live mean | live min | live max |
|---|---|---|---|---|---|---|---|---|
| M20_pct | 829 | 0.75 | 4.32 | -6.05 / 0.55 / 7.99 | 6 | **5.99** | -4.14 | **13.66** |
| M60_pct | 829 | 2.29 | 7.59 | -8.86 / 1.81 / 15.88 | 6 | -2.08 | -14.44 | 5.04 |
| RY_chg_bps | 829 | 0.16 | 20.09 | -28.6 / -1.0 / 35.6 | 6 | 4.00 | -2.0 | 10.0 |
| ATR | 829 | 27.01 | 24.91 | 11.51 / 20.87 / 62.57 | 6 | **99.19** | 90.78 | **106.98** |
| price | 829 | 1,760 | 771 | 1,172 / 1,562 / 3,441 | 6 | **4,369** | 4,014 | **4,602** |

## Per-call percentile lookup

Where each live signal-component value sits in the 16-year backtest distribution:

| signal_date | dir | M20 | %ile | M60 | %ile | RY_bps | %ile | ATR | %ile |
|---|---|---|---|---|---|---|---|---|---|
| 2026-07-20 | SHORT | -4.14% | 12 | **-14.44%** | **1** | 7.0 | 69 | 98.52 | **97** |
| 2026-08-07 | FLAT | 5.33% | 85 | -4.37% | 19 | 9.0 | 72 | 92.62 | **97** |
| 2026-08-14 | FLAT | 8.97% | **96** | -2.98% | 25 | 10.0 | 74 | 90.78 | **97** |
| 2026-08-21 | LONG | **13.66%** | **100** | 1.42% | 48 | -2.0 | 49 | 100.53 | **98** |
| 2026-08-28 | FLAT | 10.06% | **98** | 2.85% | 55 | 0.0 | 52 | 105.73 | **98** |
| 2026-09-04 | FLAT | 2.08% | 65 | 5.04% | 67 | 0.0 | 52 | 106.98 | **98** |

## ATR regime check

| slice | ATR min | ATR max | ATR mean |
|---|---|---|---|
| live (last 6 weeks) | 90.78 | 106.98 | 99.19 |
| backtest recent 52 weeks | 36.25 | 244.75 | **97.48** |
| backtest full 16 years | 9.19 | 244.75 | 27.01 |

The live sample's mean ATR (99.19) is within 2% of the backtest RECENT-52-WEEK mean (97.48). But it's 3.7x the full-history backtest mean (27.01). The ATR regime is only well-represented by the last year of backtest.

## Findings

**1. Live is deep off-distribution vs the full 16-year backtest sample. Only in-distribution with the recent 52 weeks.** Every live ATR reading is at the 97-98th percentile of the full-history distribution. Every live price is far outside the historical price range ($4k+ vs backtest median $1,562).

This isn't a bug. It's a factual observation: gold went through a structural repricing in 2024-2026. Every subsequent live call is in a regime the majority of the backtest sample doesn't cover.

**2. Signal-component percentiles for the 6 live calls skew high on M20.** Four of six signals have M20 above the 85th percentile (85, 96, 98, 100). Two are below (12, 65). Historically, v1 fires across the full M20 distribution. Live so far has clustered at the extremes.

The 2026-08-21 LONG (which stopped out at -3.30%) had M20 at the 100th percentile of the entire backtest sample. Highest 20-day momentum ever recorded in v1's training data. That's a genuine outlier trade. It was v2-skipped (per prior fire-rate analysis) and it lost. Consistent with "extreme momentum equals mean-reversion setup" folklore, but N=1 doesn't prove that.

**3. M60 has more range.** From 1st percentile (2026-07-20 SHORT, -14.44%) to 67th percentile (2026-09-04 FLAT, +5.04%). This is more like normal backtest variation.

**4. RY_chg range is very compressed live.** Backtest std is 20 bps, live range is -2 to +10 bps. Real yields have been essentially flat for the entire live period. The RY_chg filter (< 0 for LONG, > 0 for SHORT) is being triggered by very small changes.

**5. Direction distribution: v1 fires LONG less often live than backtest (17% vs 27%).** Not enough sample to matter, but worth watching. If the LONG rate stays below backtest for another dozen weeks, it might indicate the LONG-firing conditions are becoming rarer in the new regime.

**6. The current 2026-09-07 call:** M20 65th percentile, M60 67th percentile, RY_chg 52nd percentile, ATR 98th percentile. Firing conditions are moderate on momentum, extreme on volatility. FLAT this week because MA10 > MA40 is true but RY_chg is 0 (not < 0), so LONG conjunction fails.

## What this replicates or extends

- **Gold seasonality memory (gold_metadata_seasonality):** Sep -1.2% historically. Current price action loosely fits.
- **ATR-based sizing was designed for exactly this:** the shipped 2xATR stop scales with volatility, so in dollar terms our stops today ($200) are proportionally the same risk-per-trade as our stops in 2015 ($40). The rule adapts. This is a design win.
- **v2 fire-rate finding (2026-08-31):** v1 fires trades that v2 filters out, and those filtered trades lose money. Live data so far (both losses were v2-skipped) is consistent. This distribution audit doesn't add evidence, but it's a compatible frame.

## What this does NOT motivate

- Do NOT halt v1. Halt check still says CONTINUE. Off-distribution alone is not a rejection criterion. The pre-reg picked halt logic based on trade-outcome statistics, not on market-regime characterization.
- Do NOT retune v1 or v2 for the new regime. Same discipline as always. Pre-reg is locked.
- Do NOT panic about ATR being at 97th percentile. The rule adapts. Position sizing (in the operator's execution) scales the risk down naturally.

## What this DOES motivate

- **Add a distribution snapshot to the weekly report.** Show operators where the current signal components sit in the backtest percentile distribution. Not for a trading decision but for regime awareness. Something like "This week's ATR is at the 98th percentile of 16-year history. Position size accordingly."
- **The recent-52-week comparison is the more informative one right now.** Consider building a rolling "recent regime" benchmark and reporting live values against that, not just against the full-history sample.
- **The M20-extreme observation deserves more analysis.** Historical v1 trades in the 95th+ M20 percentile: what's the win rate? What's the expected return? If it's systematically worse, that's a v3-class candidate: "v1 minus extreme-M20 trades." Post-hoc caveat as always.
- **The v3-class candidate design space just got more concrete.** Two related directions:
  1. **v1 minus extreme-M20** (from this audit + from the M20 ablation finding earlier today)
  2. **v1 + M6 regime overlay** (from today's M12 aggregator work: M6 flipped SHORT ~30d ago)

  Both need fresh pre-regs. Both are more grounded than the RY_level filter that was rejected last session.

## Open follow-ups

1. **Historical backtest performance by M20 percentile bucket.** Sub-analysis: split v1's 360 trades by M20 percentile (quintiles). If top-quintile M20 trades are systematically worse, that's evidence for a v3 candidate.
2. **Regime-conditioned OOS test:** rerun v1 backtest on 2024-2026 only (the ATR regime we're actually in). If v1 backtest Sharpe in that sub-window is much lower than full-window, we should be less confident in live continuation.
3. **Live ATR trajectory tracking.** Are we entering a new higher-volatility regime that will persist, or is this a temporary spike? Would inform stop-scaling expectations.

## Files touched

- Script: `scripts/live_vs_backtest_signal_dist.py` (new)
- Doc: `docs/experiments/2026-09-08_live_vs_backtest_distribution.md` (this file)
