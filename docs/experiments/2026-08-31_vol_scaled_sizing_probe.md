# Volatility-scaled position sizing probe

**Date:** 2026-08-31
**Author:** Knox
**Status:** Exploratory sizing analysis. Not a pre-reg for a rule change.
**Trigger:** Current v1 uses 1 fixed contract per trade. ATR ranges from ~$5 in 2015 low-vol to ~$100 in 2026 high-vol. Fixed sizing means 20x more dollar risk on high-ATR trades than low-ATR trades. Question: does vol-target (constant dollar risk per trade) improve risk-adjusted returns?

## Method

`scripts/vol_scaled_sizing_probe.py`. For v1 and v2, run three sizing regimes:

1. **Fixed 1 contract** (shipping baseline)
2. **Vol-target $2,500 risk per trade** (contracts = $2,500 / (2 x ATR x 100 oz))
3. **Vol-target with 5-contract cap** (retail-realistic ceiling)

Same signal rules, same 2xATR stop, same $5 RT cost. Only position size changes per trade.

The $2,500 risk target is roughly what 1 contract at avg ATR $12 represented in the earlier sample; picked deliberately below 1 contract at current ATR so the median trade sizes DOWN under this scheme.

## Results

**v1:**

| sizing | n | WR | med contracts | Sharpe ($) | cum $ | max DD |
|---|---|---|---|---|---|---|
| Fixed 1c (shipping) | 363 | 55.9% | 1.00 | 0.717 | $181,598 | $56,043 |
| Vol-target | 363 | 55.9% | 0.59 | **0.936** | $88,906 | **$26,440** |
| Vol-target 5c cap | 363 | 55.9% | 0.59 | 0.936 | $88,906 | $26,440 |

**v2:**

| sizing | n | WR | med contracts | Sharpe ($) | cum $ | max DD |
|---|---|---|---|---|---|---|
| Fixed 1c (shipping) | 270 | 58.5% | 1.00 | 0.920 | $187,570 | $50,318 |
| Vol-target | 270 | 58.5% | 0.60 | **1.243** | $88,762 | **$18,956** |
| Vol-target 5c cap | 270 | 58.5% | 0.60 | 1.243 | $88,762 | $18,956 |

**Return/max-DD ratios (Calmar-like):**

| variant | fixed | vol-target |
|---|---|---|
| v1 | 3.24x | 3.36x (+4%) |
| v2 | 3.73x | **4.68x (+25%)** |

## Findings

**1. Vol-target improves Sharpe by 31-35%.** v1: 0.72 -> 0.94. v2: 0.92 -> 1.24. Fixed sizing gives too much weight to high-vol regime trades, which drove most of the equity curve variance.

**2. Max drawdown roughly halves.** v1: $56k -> $26k. v2: $50k -> $19k. High-ATR losses in 2011-2013 and 2026 were the dominant drawdown contributors; vol-target smooths them.

**3. Cumulative P&L is proportional to the risk target.** Vol-target at $2,500/trade produces about half the cum P&L of fixed 1c because median contracts is 0.59 (positions are smaller). To match fixed's cum $181k, risk target would need to be about $4,200/trade - and Sharpe/DD ratios stay identical (sizing multiplier is scale-invariant to those metrics).

**4. The 5-contract cap doesn't bind.** Median contracts is 0.59; the cap would only activate for very-low-ATR weeks (2015 range, ATR ~$5), which are historical. Not relevant in current regime.

**5. Cum/DD ratio improves 25% on v2** (3.73x -> 4.68x). This is the Calmar analog and the most defensible headline for a sizing improvement: "same P&L per unit drawdown, meaningfully improved."

## The fractional-contract problem

Median position is 0.59 contracts. Half the trades want less than 1 GC contract. Retail can't do this on futures. Solutions:

1. **Round to integer, floor at 1.** Loses vol-target benefit on low-ATR weeks (position stuck at 1 when strategy wants 0.5). Would need re-simulation to quantify.
2. **Use MGC micro-gold contracts.** MGC = 10 oz vs GC's 100 oz. Median 0.59 GC contracts = 5.9 MGC, roundable to 5 or 6. Preserves vol-target benefit.
3. **Use GLD ETF.** GLD ~ 10 oz gold equivalent per 100 shares. Very fine granularity. Slightly wider spreads/higher costs (see cost sensitivity audit - edge survives $50 RT).
4. **Recommend a account-scaled sizing rule** ("size for 1% account drawdown on a full stop-out") without prescribing contracts. Puts sizing choice on the subscriber.

Not a decision to make today. Documentation asset.

## Public disclosure implications

Vol-target is not v1 or v2's shipped sizing convention. But it's a legitimate optional enhancement the subscriber can implement. Candidate copy for a future methodology page:

> "The backtest uses 1 GC contract per trade for simplicity. Vol-target sizing (constant dollar risk per trade, sized by 1/ATR) improves Sharpe by 30-35% and cuts max drawdown roughly in half. Any subscriber implementing NORTH is free to use vol-target sizing; the signal rules are identical."

Not touching public copy today. Note for later.

## What this does NOT do

- Does NOT change v1's or v2's pre-registered sizing rule. Pre-reg specified "1 contract fixed." That stays.
- Does NOT propose a v3 or new candidate. Sizing is not a signal.
- Does NOT change any live behavior. NORTH continues publishing entry, stop, and exit rules; sizing is subscriber's call.
- Does NOT change the retirement wall.

## What it DOES do

- Documents the sizing-improvement opportunity for future v2-ship discussions.
- Provides an evidence-based recommendation the subscriber can pick up on their own.
- Materially strengthens the v2 case: with vol-target, v2's Sharpe reads as 1.24 with 4.68x return/DD, which is a very strong tactical strategy by any conventional measure.

## Files touched

- Script: `scripts/vol_scaled_sizing_probe.py` (new)
- Doc: `docs/experiments/2026-08-31_vol_scaled_sizing_probe.md` (this file)
