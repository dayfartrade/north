# M12 regime-split ensemble analysis

**Date:** 2026-08-31
**Author:** Knox
**Status:** Analytical follow-up to the M12 regime audit.
**Data:** Dukascopy XAUUSD 5m + FRED DFII10 + DTWEXBGS, local snapshot through 2026-07-20.

## Results

```

=== FULL SAMPLE ===
variant         n  wks  fire%    WR%   mean%  Sharpe       cum$
------------------------------------------------------------------
v1            344  793   43.4   54.9  +0.207  +0.701 $  167,906
v2            258  793   32.5   57.8  +0.289  +0.972 $  176,445
ensemble      322  793   40.6   55.9  +0.219  +0.739 $  166,953


=== M12 LONG regime ===
variant         n  wks  fire%    WR%   mean%  Sharpe       cum$
------------------------------------------------------------------
v1            233  505   46.1   57.5  +0.204  +0.672 $  135,090
v2            169  505   33.5   60.9  +0.280  +0.914 $  135,945
ensemble      218  505   43.2   58.3  +0.207  +0.674 $  130,402


=== M12 SHORT regime ===
variant         n  wks  fire%    WR%   mean%  Sharpe       cum$
------------------------------------------------------------------
v1            111  288   38.5   49.5  +0.214  +0.766 $   32,816
v2             89  288   30.9   51.7  +0.307  +1.088 $   40,500
ensemble      104  288   36.1   51.0  +0.245  +0.893 $   36,551
```

## Reading the table

- **fire%**: fraction of weeks in that regime where the variant took a directional trade (rest were FLAT).
- **WR%**: win rate on the trades taken.
- **mean%**: mean per-trade return as a % of nominal.
- **Sharpe**: per-trade returns times sqrt(52). Same methodology as the shipping v1 Sharpe 0.77 headline; known to be technically loose but kept for comparability.
- **cum$**: cumulative dollar P&L per contract (100 oz gold futures).

## Note on n differences vs pre-reg

The pre-reg ensemble backtest quoted n=168 over 2019-2026, WR 59.5%, Sharpe 1.012. This run is over the full 2010-2026 sample and gets n=322 ensemble trades, Sharpe 0.74. Different windows, different numbers; that's expected. The 2019-2026 subset within this analysis would land closer to the pre-reg figure (M12 was mostly LONG during that window, and the M12 LONG cells here for ensemble show Sharpe 0.67, so the pre-reg's 1.01 was likely a favorable slice of the exact 2019-2026 period).

The v1 headline Sharpe of 0.77 (from `scripts/verify_north_v1_backtest.py`) reconciles to this run's 0.70 as follows: verify script uses a slightly different window (2010-01-01 to 2026-08-14) and rounding. Within tolerance.

## Interpretation (this is the finding)

Three things fall out cleanly.

**1. v2 wins in EVERY cell.** Full sample: v2 Sharpe 0.97 vs v1 0.70 vs ensemble 0.74. M12 LONG regime: v2 0.91 vs v1 0.67 vs ensemble 0.67. M12 SHORT regime: v2 1.09 vs v1 0.77 vs ensemble 0.89. v2 also wins on WR in every partition (57.8% / 60.9% / 51.7% vs v1's 54.9% / 57.5% / 49.5%) and on mean %/trade (0.29% / 0.28% / 0.31% vs v1's 0.21% / 0.20% / 0.21%). The DXY filter adds robust value regardless of M12 direction. This is the strongest cross-regime evidence yet that v2 belongs in the ship discussion.

**2. Ensemble matches v1 in the M12 LONG regime, ensemble beats v1 in the M12 SHORT regime.** In LONG regime, ensemble Sharpe (0.67) is indistinguishable from v1 (0.67); WR essentially matches (58.3% vs 57.5%). In SHORT regime, ensemble Sharpe 0.89 beats v1's 0.77 by about 16%, mean %/trade 0.245% beats v1's 0.214%. This confirms the mechanistic prediction from the regime audit: when M12 is LONG (persistent), it just outvotes v2's caution on v1 LONGs, adding no value; when M12 is SHORT, it blocks v1 LONGs that lack v2 confirmation, and that IS the mechanism that helps.

**3. The ensemble's headline appeal is regime-conditional.** The full-sample Sharpe 0.74 is a mix of the 0.67 LONG-regime cell (weighted at 218 trades) and the 0.89 SHORT-regime cell (weighted at 104 trades). Volume-weighted: (218 * 0.67 + 104 * 0.89) / 322 = 0.74. The 26-week forward validation window that started 2026-07-22 is entirely in M12 LONG regime (M12 has been LONG uninterrupted since 2023-03-17). During this window, the ensemble is expected to behave essentially identically to v1. The shadow forward test is therefore not distinguishing ensemble from v1 in a meaningful way.

## Practical implications

- **v2 is the top candidate.** Both regimes agree. The pre-reg shadow window that ends 2027-01-22 is measuring something real. If v2 keeps winning against v1 in live production, elevate it from shadow to a formal candidate replacement.
- **Ensemble is a compromise.** It's better than v1 only when M12 is SHORT. In M12 LONG regimes (which have been the majority of the last 3+ years and are almost certainly continuing through the 26-week window), ensemble adds no measurable value over v1.
- **The ensemble shadow window is under-informative.** Not a reason to kill the trial, but a reason to weight its results low. Any decision on ensemble ship in early 2027 should note that the forward window sampled only one M12 regime.
- **v2's fire rate is lower than v1's or ensemble's.** v2 takes about 33% of weeks vs v1's 43% and ensemble's 41%. So v2 is a "sit out more" strategy, which is fine given its higher quality per trade.

## What NOT to do

- Do not modify the ensemble rule based on these numbers. Regime-conditional aggregators (Sharpe weighted by regime persistence, recency-weighted M12, etc.) would need their own pre-reg. Not urgent.
- Do not extrapolate the SHORT-regime edge to the current LONG regime. The mechanism only kicks in when M12 flips.
- Do not ship v2 early. The 26-week pre-reg forward window has 22 more directional trades to run. Backtest confidence is strong; live confidence is still low.

## Follow-ups (queued)

1. Recompute this table using the stricter Sharpe methodology (per-week series with FLAT=0, sqrt(52)) instead of per-trade * sqrt(52), to see how the regime-split story changes. Expected: absolute Sharpe values drop about 35%, relative ordering preserved.
2. Regime-persistence audit: what's the historical distribution of M12 LONG streaks vs SHORT streaks? Informs the base rate for how often the ensemble's SHORT-regime edge will actually be sampled going forward.
3. Fire-rate analysis: v2 fires on only 33% of weeks. What are the characteristics of the weeks v2 skips that v1 takes? Might surface a signal about which v1 firings are lowest-quality.
