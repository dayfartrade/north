# Fire-rate analysis: v1 trades split by whether v2 confirmed

**Date:** 2026-08-31
**Author:** Knox
**Status:** Analytical follow-up. Third and final follow-up from the M12 regime-split analysis.
**Trigger:** Follow-up #3 from `2026-08-31_m12_regime_split_ensemble.md` - v2 fires on 33% of weeks vs v1's 43%, so ~10% of weeks v1 fires but v2 doesn't. What do those v2-skipped v1 trades look like?

## Method

`scripts/v1_fire_rate_split_by_v2.py`. Run the full backtest, collect every v1 directional trade, and for each one tag whether v2 also confirmed the same direction (`v2_confirmed`) or v2 said FLAT because DXY wasn't aligned (`v2_skipped`). By construction v2 can never disagree in direction with v1 - it only fires when v1 fires AND DXY aligns.

Then compute WR, mean %/trade, Sharpe, and cumulative $ P&L per subset. Also split by direction (LONG vs SHORT) and by M12 regime.

## Results

```
=== ALL v1 TRADES ===
  v1 all                    n=344  WR= 54.9%  mean= +0.207%  Sharpe= +0.701  cum=$  167,906
  v1 + v2 confirmed         n=258  WR= 57.8%  mean= +0.289%  Sharpe= +0.972  cum=$  176,445
  v1 - v2 skipped           n= 86  WR= 46.5%  mean= -0.040%  Sharpe= -0.138  cum=$   -8,538

=== v1 LONG TRADES ===
  v1 LONG all               n=205  WR= 57.6%  mean= +0.256%  Sharpe= +0.839  cum=$   98,013
  v1 LONG + v2 confirmed    n=149  WR= 61.7%  mean= +0.379%  Sharpe= +1.258  cum=$  107,290
  v1 LONG - v2 skipped      n= 56  WR= 46.4%  mean= -0.070%  Sharpe= -0.224  cum=$   -9,277

=== v1 SHORT TRADES ===
  v1 SHORT all              n=139  WR= 51.1%  mean= +0.134%  Sharpe= +0.479  cum=$   69,893
  v1 SHORT + v2 confirmed   n=109  WR= 52.3%  mean= +0.166%  Sharpe= +0.568  cum=$   69,154
  v1 SHORT - v2 skipped     n= 30  WR= 46.7%  mean= +0.018%  Sharpe= +0.075  cum=$      739

=== v2-SKIPPED v1 TRADES BY M12 REGIME ===
  v2-skipped, M12 LONG      n= 64  WR= 48.4%  mean= +0.004%  Sharpe= +0.012  cum=$     -855
  v2-skipped, M12 SHORT     n= 22  WR= 40.9%  mean= -0.165%  Sharpe= -0.627  cum=$   -7,684

=== v2-CONFIRMED v1 TRADES BY M12 REGIME ===
  v2-confirmed, M12 LONG    n=169  WR= 60.9%  mean= +0.280%  Sharpe= +0.914  cum=$  135,945
  v2-confirmed, M12 SHORT   n= 89  WR= 51.7%  mean= +0.307%  Sharpe= +1.088  cum=$   40,500
```

## The finding

**v1's entire alpha lives in the v2-confirmed subset. The v2-skipped subset loses money in aggregate.**

Not "slightly worse." Not "lower quality." **Negative Sharpe, cumulative loss over 16 years.**

- 258 v2-confirmed v1 trades: cum **+$176,445**, Sharpe 0.97
- 86 v2-skipped v1 trades: cum **-$8,538**, Sharpe -0.14

Every $1 of v1's headline +$167,906 profit is more than accounted for by the v2-confirmed subset. The v2-skipped trades are net negative and drag the composite down.

## Direction breakdown makes it starker

**LONG side is where the v2 filter earns its keep most clearly:**

- v1 LONG + v2 confirmed: **Sharpe 1.26**, WR 61.7%, mean +0.38%
- v1 LONG - v2 skipped: **Sharpe -0.22**, WR 46.4%, mean -0.07%

v2 skips 27% of v1 LONGs (56 of 205). Those 56 trades are collectively unprofitable. The remaining 149 v2-confirmed LONGs run at a 1.26 Sharpe, which is the strongest metric anywhere in the NORTH backtest.

**SHORT side is less dramatic but consistent:**

- v1 SHORT + v2 confirmed: Sharpe 0.57
- v1 SHORT - v2 skipped: Sharpe 0.08 (near-zero)

v2's SHORT-skip filter mostly avoids near-zero-EV trades rather than clear losers. Still additive.

## Regime interaction

**The worst v1 trades in the sample are v2-skipped SHORTs during M12 SHORT regime:**

- 22 trades, WR 40.9%, Sharpe -0.63, cum -$7,684

Small n (22), but this is the worst-performing subset by any measure. Interpretation: when v1 fires SHORT during a persistent SHORT regime and DXY doesn't confirm, the trade is fighting the aggregate signal from both dollar and long-run trend. Skip these.

**v2-confirmed trades are strong in BOTH regimes:**

- M12 LONG regime: n=169, Sharpe 0.91
- M12 SHORT regime: n=89, Sharpe 1.09

Confirms the finding from the regime-split analysis: v2's edge is not regime-conditional. It works everywhere.

## Live-trade check

The 2026-08-24 LONG loss (-3.30%) was v2-skipped (DXY_chg ~ 0, need <0 for LONG confirmation). It falls squarely in the "v1 LONG - v2 skipped" bucket which has historical mean -0.07% and Sharpe -0.22. The loss is right in the middle of what that bucket produces.

The 2026-07-27 SHORT loss (-0.72%) was also v2-skipped. Falls in the "v1 SHORT - v2 skipped" bucket which has historical mean +0.02% (basically flat).

Both live losers to date were v2-skipped v1 trades. If v2 had been the live product, both would have been avoided. Cumulative live P&L would be 0% instead of -4.02%.

**N=2 is not evidence.** But the direction is consistent with what a 344-trade backtest shows, which is a real signal even without the live confirmation.

## Practical implications

1. **v2 is not "a better v1"; v2 is "v1 minus the losing quarter."** The DXY filter is doing exactly one job - it drops the low-quality third of v1 firings, which happen to be net-negative in aggregate.
2. **The case for v2 elevation is now very strong from the backtest side.** Every partition (full sample, LONG, SHORT, both M12 regimes) shows v2 wins. The forward validation window is still the honest gate, but the prior on v2 winning is much higher than the pre-reg alone suggested.
3. **v1's Sharpe 0.77 headline is misleading in a specific way.** It averages a high-Sharpe subset (v2-confirmed, 1.26 for LONG) with a low-Sharpe subset (v2-skipped, -0.22 for LONG). The "product" is really two products in a trench coat, and one of them shouldn't ship.
4. **Ensemble does not capture this edge fully.** In the current M12 LONG regime, ensemble takes almost every v1 LONG signal including the v2-skipped ones (because monthly M12 outvotes v2's FLAT). This is why the regime-split analysis showed ensemble ~= v1 in M12 LONG. The fire-rate split confirms: ensemble's ~40% fire rate keeps too many v2-skipped losers in the mix.

## What NOT to do

- **Do not ship v2 early.** The 26-week pre-reg forward window has 22 more directional trades to run. Backtest evidence has always been strong; the pre-reg contract was about live validation, and we honor it.
- **Do not modify v1's rules based on this.** The finding is about a filter on top of v1, not about v1 itself.
- **Do not restart the shadow window.** Full 26 weeks was the pre-reg agreement.
- **Do not present these numbers publicly as "the case for v2" without the sample-window caveat.** All the strong numbers are in-sample; v2 was designed on this data. Live validation is what earns the promotion.

## Suggested next step (queued, not urgent)

After 8-10 more directional trades resolve live, revisit this analysis with the new live data included. If the pattern holds (v2-skipped v1 losers, v2-confirmed v1 winners), that's live confirmation and worth an accelerated pre-reg amendment to consider v2 elevation before the full 26-week window closes.

Right now the observed live pattern (2 out of 2 losers were v2-skipped) is consistent but n=2 doesn't move the prior meaningfully. Wait for more sample.

## Files touched

- Script: `scripts/v1_fire_rate_split_by_v2.py` (new)
- Doc: `docs/experiments/2026-08-31_v1_fire_rate_by_v2.md` (this file)
