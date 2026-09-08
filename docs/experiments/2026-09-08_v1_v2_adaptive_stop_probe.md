# v1 + v2 adaptive-stop probe

**Date:** 2026-09-08
**Author:** Knox
**Status:** Robustness audit (post-hoc, no pre-reg).
**Trigger:** Queued as iteration 9 from the 2026-08-31 session but the session wrapped before running. The prior stop-multiplier sweep found 2.0xATR is U-shaped-worst among fixed multipliers. Natural follow-up: do any non-fixed exit rules beat the best fixed choice?

## What was tested

Seven exit rules applied to both v1 and v2 signal sets on the full 2010-01-01 → 2026-07-01 backtest window (841 weeks total; 360 v1 trades, 267 v2 trades).

| # | variant | rule |
|---|---|---|
| 1 | `fixed_2x` | Shipped baseline. Fixed 2xATR stop, Friday time exit. |
| 2 | `fixed_1x` | Fixed 1xATR stop. |
| 3 | `fixed_2p5x` | Fixed 2.5xATR stop. |
| 4 | `trailing_2x` | Stop starts at 2xATR, trails 2xATR behind highest close (LONG) / lowest close (SHORT). |
| 5 | `be_at_1x` | Fixed 2xATR stop, moves to entry after close hits +1xATR. |
| 6 | `target_2x` | Fixed 2xATR stop, exits at +2xATR profit (checked via daily high/low). |
| 7 | `trailing_be_2x` | Trailing 2xATR AND breakeven move at +1xATR profit. |

Exit-timing convention: daily OHLC only, so intra-day sequencing is unknown. Conservative rule when a bar could have hit both stop and target: assume stop first (worst case for the trade). Standard backtest convention.

## Results

**v1 (all directional signals, n=360):**

| variant | WR | stop% | BE% | tgt% | time% | Sharpe | cum $ | maxDD |
|---|---|---|---|---|---|---|---|---|
| fixed_2x (shipped) | 55.8% | 16.4% | 0.0% | 0.0% | 83.6% | 0.77 | $179,537 | -$56,043 |
| **fixed_1x** | 48.1% | 42.5% | 0.0% | 0.0% | 57.5% | **0.92** | $200,363 | **-$25,487** |
| **fixed_2p5x** | 56.7% | 10.0% | 0.0% | 0.0% | 90.0% | **0.90** | **$247,408** | -$30,136 |
| trailing_2x | 56.1% | 19.2% | 0.0% | 0.0% | 80.8% | 0.84 | $191,626 | -$56,043 |
| be_at_1x | 51.1% | 15.3% | 6.7% | 0.0% | 78.1% | 0.74 | $170,198 | -$56,043 |
| target_2x | 56.9% | 16.1% | 0.0% | 21.9% | 61.9% | 0.82 | $208,311 | -$53,244 |
| trailing_be_2x | 52.2% | 16.1% | 6.9% | 0.0% | 76.9% | 0.79 | $179,270 | -$56,043 |

**v2 (DXY-confirmed subset, n=267):**

| variant | WR | stop% | BE% | tgt% | time% | Sharpe | cum $ | maxDD |
|---|---|---|---|---|---|---|---|---|
| fixed_2x (shipped) | 58.4% | 16.1% | 0.0% | 0.0% | 83.9% | 1.05 | $185,509 | -$50,318 |
| **fixed_1x** | 51.3% | 40.4% | 0.0% | 0.0% | 59.6% | **1.24** | $209,705 | **-$19,762** |
| **fixed_2p5x** | 59.2% | 9.7% | 0.0% | 0.0% | 90.3% | **1.23** | **$254,688** | -$24,292 |
| trailing_2x | 58.8% | 18.7% | 0.0% | 0.0% | 81.3% | 1.12 | $192,989 | -$50,318 |
| be_at_1x | 53.6% | 15.0% | 6.7% | 0.0% | 78.3% | 1.00 | $173,542 | -$50,318 |
| target_2x | 59.6% | 15.7% | 0.0% | 24.0% | 60.3% | 1.16 | $219,725 | -$47,519 |
| trailing_be_2x | 55.1% | 15.7% | 6.7% | 0.0% | 77.5% | 1.06 | $181,223 | -$50,318 |

## Findings

**1. No adaptive-stop variant beats the best fixed multiplier.** For both v1 and v2, `fixed_1x` and `fixed_2p5x` occupy the top two Sharpe slots. All four adaptive variants rank third or lower.

**2. Adaptive variants DO beat the shipped 2xATR baseline** (except breakeven, which degrades). But that just reflects the prior finding: 2.0xATR is U-shaped-worst. Moving away from it in any direction is an improvement. Not a new insight, and not a reason to change anything.

**3. Breakeven-move degrades performance on both variants.** `be_at_1x` is dead-last on Sharpe. Mechanism: the 1xATR trigger cuts trades to flat that would have recovered to full target. 6.7% of trades exit at breakeven, and those trades are net winners on the un-modified rule.

  This is the same pattern the 2026-07-07 `janus_q4_trailing_stop` experiment found on the ORB engine: MFE-locking cuts would-be winners on transient pullbacks. Different signal, same mechanism. The finding replicates.

**4. Target-take improves win rate but flatlines Sharpe.** `target_2x` wins ~22-24% of trades early at the 2xATR target, boosting WR by ~1pp. But the cum P&L is roughly equal to trailing_2x, meaning it captures roughly the same total dollars while cutting some winner tail. Sharpe is above fixed_2x but below both fixed_1x and fixed_2p5x.

**5. Trailing stops don't help at daily-close granularity.** `trailing_2x` barely edges the fixed baseline. A 2xATR trailing distance is too wide to lock in much MFE when only checked at daily close. Would need 5m bars during the week to give trailing stops a fair test, which we have but haven't wired into the weekly backtest.

**6. Max DD ranking is different from Sharpe ranking.** `fixed_1x` is BY FAR the best on max DD ($25k vs $56k baseline for v1; $20k vs $50k for v2). If drawdown is the constraint, 1xATR wins decisively. If Sharpe alone, fixed_2p5x edges it by a hair.

## What this replicates

- **Stop-multiplier robustness (2026-08-31):** fixed 1xATR and 2.5xATR both beat the shipped 2.0xATR. Confirmed on the same data.
- **janus_q4_trailing_stop (2026-07-07):** MFE-locking / breakeven rules systematically cut would-be winners. Cross-engine replication.

## What this does NOT motivate

- Do NOT change v1's or v2's stop mid-window. Pre-reg is locked. Same discipline as the stop-multiplier finding.
- Do NOT ship a "v1 with trailing stop" candidate. It doesn't help.
- Do NOT ship a "v1 with breakeven move" candidate. It actively hurts.
- Do NOT re-tune adaptive parameters on the same data (trailing at 1x or 3x, breakeven at 0.5x, etc). Textbook p-hacking. If a future candidate wants adaptive exits, it needs a fresh pre-reg and Bonferroni bump.

## What this DOES motivate

- **A future candidate pre-registering fixed 1xATR or 2.5xATR is the natural exit-rule improvement path.** Not adaptive.
- **The 5m-granularity trailing question is still open.** We have 5m XAUUSD data. If we ever want to give trailing stops a fair test, checking every 5-minute close instead of daily would be the honest way to do it. Not urgent, but a real gap.
- **Honesty disclosure for methodology page:** "We tested trailing, breakeven-move, target-take, and combined variants. None beat the best fixed multiplier on Sharpe. Adaptive complexity added zero edge on this signal."

## Files touched

- Script: `scripts/v1_v2_adaptive_stop_probe.py` (new)
- Doc: `docs/experiments/2026-09-08_v1_v2_adaptive_stop_probe.md` (this file)
