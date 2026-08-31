# v1 + v2 cost sensitivity audit

**Date:** 2026-08-31
**Author:** Knox
**Status:** Robustness audit. Disclosure asset.
**Trigger:** Retail subscribers pay wider spreads and higher commissions than the $5 IBKR round-trip baseline. Does v1/v2 edge survive?

## Method

`scripts/v1_v2_cost_sensitivity.py`. Rerun the full v1 and v2 backtest at RT costs of $5 (baseline), $10, $15, $25, and $50 per trade. Everything else identical.

## Results

**v1:**

| RT cost | n | WR | mean %/trade | Sharpe | cum $ |
|---|---|---|---|---|---|
| $5 (baseline) | 363 | 55.9% | +0.227 | 0.767 | $181,598 |
| $10 | 363 | 55.9% | +0.223 | 0.757 | $179,783 |
| $15 | 363 | 55.9% | +0.220 | 0.746 | $177,968 |
| $25 | 363 | 55.9% | +0.214 | 0.724 | $174,338 |
| $50 | 363 | 55.1% | +0.198 | 0.671 | $165,263 |

**v2:**

| RT cost | n | WR | mean %/trade | Sharpe | cum $ |
|---|---|---|---|---|---|
| $5 (baseline) | 270 | 58.5% | +0.310 | 1.042 | $187,570 |
| $10 | 270 | 58.5% | +0.307 | 1.032 | $186,220 |
| $15 | 270 | 58.5% | +0.303 | 1.021 | $184,870 |
| $25 | 270 | 58.5% | +0.297 | 1.000 | $182,170 |
| $50 | 270 | 57.4% | +0.282 | 0.947 | $175,420 |

**Gross mean P&L per trade (before cost):**

- v1: $505 gross per trade
- v2: $700 gross per trade

## Findings

**1. Edge is extremely cost-robust.** At $50 RT (10x baseline), v1 loses only 13% of its Sharpe (0.77 → 0.67), v2 loses only 9% (1.04 → 0.95). Cumulative P&L drops 9-13%. WR is unchanged (only $50 case slightly perturbs it because a few marginal winners become losers).

**2. Breakeven cost is far above any realistic retail level.** v1's gross mean P&L per trade is $505, v2's is $700. RT cost would have to exceed $505 for v1 or $700 for v2 to eliminate the mean edge. Retail futures commissions are typically $2-8 per side ($4-16 RT). Even at IBKR retail (~$4 RT) or extreme retail (~$15-20 RT), the edge is preserved.

**3. v2 is more cost-resilient than v1 in relative terms.** v2's higher mean P&L per trade means the fixed-dollar cost is a smaller fraction of the trade's expected value. v2 stays above Sharpe 1.0 all the way through $25 RT.

**4. GLD equivalent cost check.** For a subscriber using GLD ETF instead of GC futures, roughly $10-15 RT per 100 shares (varies by broker). v1 at $15 RT: Sharpe 0.75, cum $177,968. v2 at $15 RT: Sharpe 1.02, cum $184,870. Both survive comfortably.

## Public disclosure implications

Candidate honesty statement for a future methodology page or subscriber FAQ:

> "The backtest headline uses $5 round-trip cost (realistic IBKR institutional). At $25 RT (well above any retail broker), v1 Sharpe drops from 0.77 to 0.72 and cumulative P&L drops 4%. The edge does not depend on institutional cost structure. Even $50 RT preserves 87% of the Sharpe and 91% of the P&L."

Not touching public copy today. Disclosure asset for later.

## What this does NOT do

- Does NOT motivate a rule change. Cost is not a signal.
- Does NOT change any live behavior. v1's cost model stays $5 in the shipped backtest.
- Does NOT change the retirement wall count.
- Does NOT count against Bonferroni-N. Robustness audit, not candidate search.

## Files touched

- Script: `scripts/v1_v2_cost_sensitivity.py` (new)
- Doc: `docs/experiments/2026-08-31_v1_v2_cost_sensitivity.md` (this file)
