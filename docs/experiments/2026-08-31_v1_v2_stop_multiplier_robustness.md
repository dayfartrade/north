# v1 + v2 stop-multiplier robustness

**Date:** 2026-08-31
**Author:** Knox
**Status:** Robustness audit.
**Trigger:** v1 uses 2xATR stop, picked pre-reg. Is that the peak, average, or arbitrary?

## Results

**v1:**

| stop | n | WR | stop-hit% | Sharpe | cum $ | max DD |
|---|---|---|---|---|---|---|
| 1.0xATR | 363 | 48.2% | 42.4% | 0.92 | $202,014 | $25,487 |
| 1.5xATR | 363 | 54.0% | 25.9% | 0.84 | $189,808 | $39,057 |
| **2.0xATR** (shipped) | 363 | 55.9% | 16.3% | 0.77 | $181,598 | $56,043 |
| 2.5xATR | 363 | 56.7% | 9.9% | **0.89** | **$249,469** | $30,136 |
| 3.0xATR | 363 | 56.7% | 6.3% | 0.82 | $239,425 | $33,573 |

**v2:**

| stop | n | WR | stop-hit% | Sharpe | cum $ | max DD |
|---|---|---|---|---|---|---|
| 1.0xATR | 270 | 51.5% | 40.4% | 1.23 | $211,356 | **$19,762** |
| 1.5xATR | 270 | 56.7% | 23.3% | **1.27** | $216,841 | $33,332 |
| **2.0xATR** (shipped) | 270 | 58.5% | 15.9% | 1.04 | $187,570 | $50,318 |
| 2.5xATR | 270 | 59.3% | 9.6% | 1.23 | **$256,749** | $24,292 |
| 3.0xATR | 270 | 59.3% | 5.2% | 1.21 | $256,324 | $25,174 |

## Findings

**1. The 2.0xATR shipped stop is NOT the peak.** For both v1 and v2, both 1.0xATR (tighter) and 2.5xATR (wider) beat 2.0xATR on Sharpe. 2.0x actually has the WORST Sharpe of the five tested multipliers for both variants. Also worst on cumulative P&L for v1, and worst max drawdown for both.

**2. The distribution is U-shaped.** Peak Sharpe at 1.0xATR (v1 0.92, v2 1.23) OR at 2.5xATR (v1 0.89, v2 1.23) with a dip at 2.0x. Two different mechanisms:
- Tighter stops (1.0x): higher stop-hit rate but each stop is a smaller loss. Cuts losers fast. Lower WR but tight risk control.
- Wider stops (2.5x-3.0x): lower stop-hit rate, more time-exits, higher WR. Lets winners run.
- Middle (2.0x) is the worst of both worlds: takes intermediate losses without the risk control of tight OR the run-let of wide.

**3. Pre-reg discipline is what it is.** 2xATR was locked before backtest. The pre-reg document explicitly reserves the right to test stop-multiplier variants in future v-something-else candidates. We're not modifying v1 or v2 - the shipped stops stay.

**4. This is a "would have shipped differently in retrospect" honesty asset.** The pre-reg picked 2xATR because "2 standard deviations" is a natural default. Post-hoc it's suboptimal. Publishing the sweep transparently is the honest move.

## Why is 2.0xATR bad?

Speculation: 2xATR sits right where a lot of typical weekly gold moves cluster. Enough noise hits the stop that we lose (16% stop-hit), but the stop is far enough that the loss is meaningful ($200 average per stop). Either tighter (cut faster) or wider (let it breathe) avoids this specific bad zone.

Not a proven mechanism, just a hypothesis. Would need more analysis to confirm.

## What this does NOT motivate

- Do NOT change v1's or v2's stop mid-window. Pre-reg is locked. Changing would invalidate the forward comparison.
- Do NOT ship a "v1 with tighter stop" candidate without a fresh pre-reg. The 1.0x or 2.5x findings are post-hoc; any candidate needs to pre-register the stop multiplier BEFORE re-running the backtest.
- Do NOT claim 2.5xATR is "the right stop." N=363 with one specific rule set is not enough evidence to declare a universal optimum. Different signal shape, different stop optimum.

## What this DOES motivate

- **A future v3 or v4 candidate could pre-register a different stop.** If we ever design a fresh candidate (say, v1 with a tighter macro filter), it's fair game to also pre-register 1.5xATR or 2.5xATR stops from the start.
- **Honesty disclosure for a future methodology page.** "Our shipped stop is 2xATR, picked pre-reg. In hindsight, 1.0x or 2.5x would have produced higher Sharpe on the same signal. We honor the pre-registered choice."

## Files touched

- Script: `scripts/v1_v2_stop_multiplier_robustness.py` (new)
- Doc: `docs/experiments/2026-08-31_v1_v2_stop_multiplier_robustness.md` (this file)
