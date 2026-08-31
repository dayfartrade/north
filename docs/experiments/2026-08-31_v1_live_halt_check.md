# v1 live-record SPRT halt check

**Date:** 2026-08-31
**Author:** Knox
**Status:** Diagnostic. Answers "should we be worried about 0-2?"
**Trigger:** v1 is at 0W-2L live. Engine A was halted at 4/18 wins by SPRT log-LR crossing 2.944. Applying the same SPRT math to v1's current record tells us formally whether we're in the halt zone, safe zone, or inconclusive.

## SPRT parameters (matching Engine A's halt formulation)

- H0 baseline: WR = 0.559 (v1 backtest)
- H1 degraded: WR = 0.35 (same p1 as Engine A)
- Alpha = 0.05, Beta = 0.20
- Halt boundary (accept H1): log-LR >= **2.944**
- Safe boundary (accept H0): log-LR <= **-2.944**
- Per-win increment: **-0.468** (drives LR toward safe)
- Per-loss increment: **+0.388** (drives LR toward halt)

## Current state

- 0W-2L on 2 resolved directional trades:
  - `[L] 2026-07-27 SHORT -0.72%`
  - `[L] 2026-08-24 LONG -3.30%`
- Log-LR = **+0.776**
- Verdict: **CONTINUE (not enough evidence yet)**

## Loss-only trajectory

If every future trade also loses, halt fires at:

| additional losses | total record | log-LR | verdict |
|---|---|---|---|
| +0 | 0W-2L | +0.776 | CONTINUE |
| +1 | 0W-3L | +1.164 | CONTINUE |
| +2 | 0W-4L | +1.552 | CONTINUE |
| +3 | 0W-5L | +1.940 | CONTINUE |
| +4 | 0W-6L | +2.328 | CONTINUE |
| +5 | 0W-7L | +2.715 | CONTINUE |
| **+6** | **0W-8L** | **+3.103** | **HALT** |

So we would need **6 more consecutive losses** (0-8 total) before the formal halt triggers.

Given v1's 55.9% backtest WR, the probability of 6 consecutive losses is 0.441^6 = 0.73% (about 1 in 137).

## Full SPRT grid

Verdict at every (n, wins) up to n=25:

```
  n\wins      0     1     2     3     4     5     6     7     8     9    10    11    12    13    14
  n= 0          .
  n= 1          .     .
  n= 2          .     .     .
  n= 3          .     .     .     .
  n= 4          .     .     .     .     S
  n= 5          .     .     .     .     .     S
  n= 6          .     .     .     .     .     S     S
  n= 7          .     .     .     .     .     S     S     S
  n= 8          H     .     .     .     .     .     S     S     S
  n=10          H     H     .     .     .     .     .     S     S     S     S
  n=12          H     H     H     .     .     .     .     .     S     S     S     S     S
  n=14          H     H     H     H     .     .     .     .     .     S     S     S     S     S     S
  n=18          H     H     H     H     H     .     .     .     .     .     S     S     S     S     S
  n=25          H     H     H     H     H     H     H     H     H     .     .     .     .     .     S
```

Legend: H=halt, S=safe (accept H0 baseline), . = continue

Observations from the grid:

- **Halt requires at least 8 trades** with all losses. Cannot halt before n=8 under this test formulation.
- **Safe requires at least 4 trades** with all wins. Can accept baseline as early as n=4 with 4W-0L.
- At the end of the pre-reg forward window (~n=26 for v1, though signal count depends on FLAT rate), halt requires 8W or fewer to have happened. Safe requires 14+ wins.

## Interpretation

**We are firmly in the "continue, insufficient evidence" zone.** The SPRT test cannot fire either halt or safe verdict at N=2 by construction (halt requires n>=8, safe requires n>=4 of wins). The two losses have moved the log-LR from 0 to +0.78, which is about 26% of the way to halt (2.94). Not zero, but not close.

**Two more losses in a row would still not halt.** 0-4 gives log-LR 1.55, still below halt.

**The math says: keep going as designed.** Any impulse to modify v1 based on 0-2 is running well ahead of what our own halt framework would justify. The pre-reg gate for evaluation is 26 weeks forward; the halt gate under this formulation is 8 losses (~10 directional weeks minimum). Both are far ahead of us.

## Comparison to Engine A halt

Engine A was halted at n=18, 4W-14L (WR 22.2%), log-LR 3.834. Very deep in the halt zone. Reference to remind ourselves what "actually broken" looks like:

- Engine A: n=18, 4 wins, log-LR 3.834 (halt threshold 2.944 -> HALT)
- v1 today: n=2, 0 wins, log-LR 0.776 (halt threshold 2.944 -> CONTINUE)

## What triggers a real concern

Based on this framework:

- **n=3-5 all losses (0-3, 0-4, 0-5):** still CONTINUE. Log-LR 1.16 to 1.94.
- **0-6 or 0-7:** CONTINUE but getting closer. Worth a diagnostic re-check.
- **0-8 or worse:** HALT. Time to stop publishing and figure out what changed.
- **Any streak of 4W-0L in the meantime:** SAFE, accept baseline. Continue confidently.

## What this does NOT change

- Does NOT modify the halt gate. The SPRT parameters used here match Engine A's for comparability, but v1 didn't ship with an explicit SPRT halt attached. If we ever add one, this analysis is the starting point.
- Does NOT change v1 rules. Pure diagnostic.
- Does NOT affect the pre-reg forward windows. Both v2 and ensemble shadow-window gates are separate from halt gates.
- Does NOT affect the retirement wall count.

## Practical output

**For the honesty page or a subscriber FAQ:** "Two losses in a row is not statistically alarming for a 55.9% WR strategy. A formal sequential test at the same 95%/20% error bounds used for the shipped Engine A halt would need to see six more consecutive losses before it would flag v1 as broken."

Not touching public copy today. Diagnostic asset for the record.

## Files touched

- Script: `scripts/v1_live_halt_check.py` (new)
- Doc: `docs/experiments/2026-08-31_v1_live_halt_check.md` (this file)
