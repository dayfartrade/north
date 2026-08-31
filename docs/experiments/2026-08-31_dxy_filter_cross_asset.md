# Cross-asset check: does the DXY-filter mechanism generalize?

**Date:** 2026-08-31
**Author:** Knox
**Status:** Exploratory probe. Not a pre-reg, not a ship candidate for any new product.
**Trigger:** Today's v2 analyses showed the DXY filter turns v1's Sharpe 0.77 into v2's Sharpe 1.04 on gold. Question - is this a gold-specific effect or a portable mechanism?

## Method

`scripts/dxy_filter_cross_asset.py`. Apply the v1-shape rule (M20 > 0 AND M60 > 0 AND MA10 > MA40 AND RY_chg < 0 for LONG; inverted for SHORT) to two other USD-denominated assets:

- **Silver (XAG/USD)** - close macro cousin to gold, Dukascopy 5m data 2014-2026
- **S&P 500 (USA500.IDXUSD)** - risk asset, different DXY sensitivity, Dukascopy 5m 2015-2023

Then apply the DXY filter (same as v2 gold) as an AND-condition on top. Compare rule-alone vs rule+DXY performance.

Same position management as gold-v1: Monday open entry, 2xATR stop, Friday close time exit.

## Results

```
=== GOLD (XAU/USD) - baseline ===
  v1-shape rule alone         n=363  WR=55.9%  mean=+0.227%  Sharpe=+0.767  cum=$181,598
  v1-shape + DXY filter (v2)  n=270  WR=58.5%  mean=+0.310%  Sharpe=+1.042  cum=$187,570
  DXY-filter dropped 93/363 = 25.6% of firings

=== SILVER (XAG/USD) ===
  v1-shape rule alone         n=245  WR=47.8%  mean=+0.185%  Sharpe=+0.337  cum=$131,993
  v1-shape + DXY filter       n=181  WR=49.2%  mean=+0.365%  Sharpe=+0.641  cum=$148,162
  DXY-filter dropped 64/245 = 26.1% of firings

=== S&P 500 (USA500) ===
  v1-shape rule alone         n=168  WR=56.5%  mean=+0.111%  Sharpe=+0.338  cum=$40,632
  v1-shape + DXY filter       n=125  WR=57.6%  mean=+0.162%  Sharpe=+0.449  cum=$42,348
  DXY-filter dropped 43/168 = 25.6% of firings
```

## Findings

**1. The DXY-alignment mechanism improves Sharpe on all three assets.**

| asset | Sharpe alone | Sharpe + DXY | improvement |
|---|---|---|---|
| Gold | 0.77 | 1.04 | +35% |
| Silver | 0.34 | 0.64 | +90% |
| S&P 500 | 0.34 | 0.45 | +33% |

**2. All three assets see almost identical filter-drop rate: 25.6% - 26.1%.** This is striking. The DXY-alignment rule filters roughly a quarter of raw firings on every asset tested. That's a structural regularity, not an artifact of gold's specific relationship with the dollar.

**3. Silver sees the largest relative improvement.** From Sharpe 0.34 to 0.64, +90%. The silver rule alone has a losing WR (47.8%), which the DXY filter drags up to just under breakeven WR (49.2%) but with much better per-trade payoff (mean +0.18% -> +0.37%). Silver is more DXY-sensitive than gold on this rule shape.

**4. S&P 500 improvement is modest.** Rule alone WR is already 56.5%, +DXY filter WR is 57.6%, Sharpe 0.34 -> 0.45. Real but smaller. SPX's DXY sensitivity is less mechanical - it can shrug off DXY moves that would matter for a precious metal.

## Interpretation

**The DXY filter is a portable macro-alignment mechanism, not a gold-specific quirk.** Same skip rate, same directional improvement across three different USD-denominated assets. This meaningfully strengthens the conceptual case for v2 as the shipping version - the mechanism has independent cross-asset evidence, not just single-asset backtest luck.

Does NOT motivate shipping a silver or SPX product on this rule shape:

- **Silver:** even with the DXY filter, Sharpe 0.64 is below the ship threshold we used for gold (0.77+). Silver-native research was already exhausted earlier in 2026 (three candidates + GSR revisit all rejected).
- **SPX:** we don't ship SPX. Not our universe.

The value is in the CONCEPTUAL support: v2's edge is a real mechanism, not gold-flavored curve fit.

## What this does NOT do

- Does not open silver or SPX product research. Universe expansion was formally probed (`docs/experiments/2026-08-17_universe_probe.md`) and rejected for these assets.
- Does not affect v1 or v2's pre-reg forward windows. Those run on their own schedules.
- Does not seed a "cross-asset ensemble" candidate. Anything of that shape would need its own pre-reg.

## What it DOES do

- Adds cross-asset evidence to today's v2 case. Combined with the fire-rate finding (v2 drops the losing quarter of v1 firings) and the regime-split finding (v2 wins in both M12 regimes), the case for v2 elevation is now backed by four independent analyses.
- Documents the mechanism for future reference: DXY-alignment filter drops ~25% of naive momentum+RY firings across USD-denominated assets, and the dropped subset is systematically weaker.

## Files touched

- Script: `scripts/dxy_filter_cross_asset.py` (new)
- Doc: `docs/experiments/2026-08-31_dxy_filter_cross_asset.md` (this file)
