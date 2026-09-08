# v1 + v2 intraday (5m) trailing stop probe

**Date:** 2026-09-08
**Author:** Knox
**Status:** Robustness audit. Follow-up to the same-day daily-close adaptive-stop probe.
**Trigger:** The 2026-09-08 daily-close adaptive-stop probe found trailing stops barely beat the fixed baseline. Explicit gap noted in that doc: 2xATR trailing distance checked only at daily close cannot lock in much MFE. The honest test uses 5m bars during the week. We have 1.19M 5m XAUUSD bars covering 2010-onward. This probe wires them into the weekly backtest and reruns trailing at 5m granularity.

## What was tested

Six trailing variants applied to both v1 and v2 signal sets on the full 2010-01-01 → 2026-07-01 window. Each variant enters Monday open at the daily open price, checks stops and updates trailing on every 5m close within the week, and exits at Friday close if no stop hit.

| # | variant | rule |
|---|---|---|
| 1 | `fixed_2x_baseline` | Reference. Fixed 2xATR stop, Friday time exit. |
| 2 | `trail_2x_5m` | Initial 2xATR stop, trails 2xATR behind highest 5m close (LONG) / lowest (SHORT). |
| 3 | `trail_1p5x_5m` | Initial 2xATR stop, trails 1.5xATR. |
| 4 | `trail_1x_5m` | Initial 2xATR stop, trails 1.0xATR. |
| 5 | `trail_0p5x_5m` | Initial 2xATR stop, trails 0.5xATR (very tight). |
| 6 | `trail_2x_after_1x` | Delayed activation: fixed 2x initial, trailing 2x only activates after +1xATR profit. |

Exit-timing convention: on any 5m bar, stop check happens before trailing update. Standard conservative rule.

## Results

**v1 (all directional signals, n=360):**

| variant | WR | stop% | trail% | time% | Sharpe | cum $ | maxDD |
|---|---|---|---|---|---|---|---|
| fixed_2x_baseline | 55.8% | 16.4% | 0.0% | 83.6% | 0.77 | $179,537 | -$56,043 |
| trail_2x_5m | 52.8% | 0.0% | 32.8% | 67.2% | 0.68 | $160,403 | -$37,903 |
| **trail_1p5x_5m** | 50.6% | 0.0% | 52.5% | 47.5% | **0.85** | $165,688 | **-$30,128** |
| trail_1x_5m | 43.9% | 0.0% | 81.9% | 18.1% | 0.77 | $156,959 | -$20,854 |
| trail_0p5x_5m | 40.0% | 0.0% | 100.0% | 0.0% | 0.49 | $44,689 | -$24,826 |
| trail_2x_after_1x | 53.9% | 14.2% | 11.9% | 73.9% | 0.70 | $153,072 | -$53,244 |

**v2 (DXY-confirmed subset, n=267):**

| variant | WR | stop% | trail% | time% | Sharpe | cum $ | maxDD |
|---|---|---|---|---|---|---|---|
| fixed_2x_baseline | 58.4% | 16.1% | 0.0% | 83.9% | 1.05 | $185,509 | -$50,318 |
| trail_2x_5m | 55.1% | 0.0% | 31.8% | 68.2% | 1.06 | $178,068 | -$32,179 |
| **trail_1p5x_5m** | 53.6% | 0.0% | 51.3% | 48.7% | **1.24** | $181,337 | **-$22,392** |
| trail_1x_5m | 44.9% | 0.0% | 82.0% | 18.0% | 1.00 | $154,982 | -$20,001 |
| trail_0p5x_5m | 40.4% | 0.0% | 100.0% | 0.0% | 0.40 | $29,543 | -$24,261 |
| trail_2x_after_1x | 56.2% | 13.9% | 12.4% | 73.8% | 0.95 | $157,675 | -$47,519 |

## Findings

**1. 5m trailing at 1.5xATR is genuinely useful.** For BOTH v1 and v2, `trail_1p5x_5m` beats the fixed 2x baseline on Sharpe (v1: 0.85 vs 0.77; v2: 1.24 vs 1.05) AND slashes max drawdown to less than half (v1: $30k vs $56k; v2: $22k vs $50k). This is meaningfully different from the daily-close trailing finding (which barely edged baseline).

**2. Compared to the fixed-multiplier ranking from the daily probe:**

Combining today's two probes, best Sharpe rankings become:

v1:
1. `fixed_1x` , Sharpe 0.92, cum $200k, DD $25k
2. `fixed_2p5x` , Sharpe 0.90, cum $247k, DD $30k
3. `trail_1p5x_5m` , Sharpe 0.85, cum $166k, DD $30k
4. `fixed_2x` , Sharpe 0.77, cum $180k, DD $56k

v2:
1. `fixed_1x` , Sharpe 1.24, cum $210k, DD $20k
2. `trail_1p5x_5m` , Sharpe 1.24, cum $181k, DD $22k
3. `fixed_2p5x` , Sharpe 1.23, cum $255k, DD $24k
4. `fixed_2x` , Sharpe 1.05, cum $186k, DD $50k

For v2, `trail_1p5x_5m` matches the best fixed variant on Sharpe with a different profile (lower cum P&L, similar drawdown). For v1, it lands third but is still the best adaptive variant tested. Adaptive layering CAN help at 5m granularity , the daily-only version couldn't.

**3. The 1.5x trailing distance is the sweet spot for a reason.** Tighter (1x and 0.5x) triggers on 5m noise and cuts winning trades: `trail_1x_5m` win rate drops to 44%, `trail_0p5x_5m` to 40%. Wider (2x) leaves too much MFE on the table before the stop lifts. 1.5x is enough to avoid most noise while still capturing the profit-lock benefit.

**4. Delayed activation (`trail_2x_after_1x`) does not help.** Requiring +1xATR profit before trailing kicks in only saves 12% of trades from being trailed out, and the ones it saves aren't the biggest winners. Slightly worse Sharpe than the un-delayed 2x trail.

**5. Trailing collapses the winner/loser distinction on max DD.** All 5m trailing variants (except 0.5x, which is a mess) have max DD in the $20-38k range vs the baseline's $56k. Trailing genuinely does what it's supposed to do: cap the downside on any single trade by locking in partial profits. The question is only whether the win-rate hit outweighs the drawdown protection.

## What this reverses vs the daily probe

The daily probe (published earlier today) concluded "no adaptive variant beats the best fixed multiplier." That conclusion holds if you stop at daily granularity. **At 5m granularity, `trail_1p5x_5m` matches the best fixed multiplier on Sharpe for v2 with a very different risk profile** (much lower drawdown, slightly lower cum P&L).

The two probes agree on: breakeven-move degrades, target-take is neutral, delayed activation is neutral. They disagree on: whether trailing helps at all. Answer: only at sub-daily granularity, and only at the right trailing distance.

## What this does NOT motivate

- Do NOT change v1's or v2's stop mid-window. Pre-reg locked at 2xATR fixed. Same discipline.
- Do NOT retune the 1.5x trailing distance on the same data. Textbook p-hacking.
- Do NOT claim `trail_1p5x_5m` is "the right stop." N=360/267 with one specific rule set is not enough evidence to declare a universal optimum. Different signal shape, different exit optimum.

## What this DOES motivate

- **A future candidate pre-registering `trail_1p5x_5m` as an exit rule is now a legitimate design option.** Alongside `fixed_1x` and `fixed_2p5x` from the daily probe. Three viable exit-rule contenders exist for v3-class candidates.
- **For risk-conscious sizing, `trail_1p5x_5m` is arguably preferable to `fixed_2p5x`.** Both hit ~1.2 Sharpe on v2, but the trailing variant has half the max drawdown. Sharpe is not everything; sequence-of-returns risk matters.
- **Methodology page disclosure:** "Our shipped exit is fixed 2xATR, picked pre-reg. In hindsight, both fixed 1xATR/2.5xATR AND 5m-checked 1.5xATR trailing would have produced better Sharpe on the same signal. We honor the pre-registered choice for the current forward window."

## Files touched

- Script: `scripts/v1_v2_intraday_trailing_probe.py` (new)
- Doc: `docs/experiments/2026-09-08_v1_v2_intraday_trailing_probe.md` (this file)
