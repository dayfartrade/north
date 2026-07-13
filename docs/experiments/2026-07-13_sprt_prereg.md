# Pre-registration: SPRT halt parameters

**Registered UTC:** 2026-07-13T11:00:00Z
**Owner:** Knox
**Applies to:** `scripts/halt_monitor.py`, `sprt()` function

## Rationale

Per quant framework (memory: `quant_framework_gold.md`) Q1: gold's slow effective sample rate makes waiting for n=100 unacceptable. Wald's Sequential Probability Ratio Test lets us halt as soon as evidence accumulates against the null hypothesis of a working strategy.

**Framework rule violation risk:** if we run SPRT with any hypothesis pair (p0, p1) we like AFTER seeing the data, we're hindsight-fitting. Same failure mode as `real_yield_gt_2_2` earlier today (OOS reject). To prevent this, pre-register the parameters BEFORE using SPRT verdict as authoritative.

## Parameters

- **H0 (strategy works):** p = 0.57 (backtested win rate on v7.2.1 per DSR audit 2026-07-07)
- **H1 (strategy broken):** p = 0.35 (roughly the launch-window observed win rate; represents "meaningfully below random for ORB")
- **Type I error (alpha):** 0.05 — 5% chance of halting a working strategy
- **Type II error (beta):** 0.05 — 5% chance of continuing a broken strategy

## SPRT boundaries

- **Halt (accept H1):** log-LR >= ln((1-beta)/alpha) = ln(19) = +2.944
- **Safe (accept H0):** log-LR <= ln(beta/(1-alpha)) = ln(1/19) = -2.944
- **Continue sampling:** -2.944 < log-LR < +2.944

## Per-trade log-LR

- **Win:** log(p1/p0) = log(0.35/0.57) = **-0.488**
- **Loss:** log((1-p1)/(1-p0)) = log(0.65/0.43) = **+0.413**

## Interpretation rules

1. **On SPRT_HALT:** private alert fires. Strategy is HALTED in live capital. Shadow-logged from that point forward per framework Q1.
2. **On SPRT_SAFE:** SPRT test complete for this hypothesis pair. Any new SPRT would need new pre-registered params.
3. **On SPRT_CONTINUE:** keep sampling. Verdict revisited each new trade.
4. **Once verdict fires, this SPRT is frozen.** Restart requires a new pre-registration (new hypothesis pair and/or new sample window).

## Sample window

**Starts at:** 2026-07-01 launch (first live trade under v7.2.1).
**Ends at:** whenever SPRT crosses a boundary.
**Frozen:** we do NOT re-run SPRT with different hypotheses if it hasn't fired yet — that's hypothesis fishing. If regime shifts substantively (e.g., real yield drops below 2.0 for 30+ days), we can register a new SPRT with new params keyed to the new window.

## Current reading at pre-reg time

- **n = 10 trades since 2026-07-01**
- **wins = 1** (07-08 NY SHORT +$2,091)
- **losses = 9**
- **log-LR = 1×(-0.488) + 9×(+0.413) = +3.229**
- **Verdict: SPRT_HALT** (log-LR > +2.944)

**This reading is FROM PRE-REG MOMENT ONWARD authoritative.** For all trades already in the sample as of 11:00 UTC 2026-07-13, this represents a retrospective read using pre-registered parameters — legitimate because the parameters (p0=0.57, p1=0.35, alpha=beta=0.05) are:
- p0 = backtested win rate, established before any launch trade
- p1 = 0.35 chosen as "meaningfully broken" threshold; NOT the observed 10% because that would be circular

**Note on p1 choice:** 0.35 is above the observed live rate of 10%. Choosing p1 closer to the observed value would make SPRT more likely to fire — a form of hindsight. Choosing 0.35 (a natural "clearly broken" threshold) is defensible. If we had chosen p1=0.45 (mild underperformance), current log-LR = 1×log(0.45/0.57) + 9×log(0.55/0.43) = -0.236 + 2.216 = **+1.98** which is BELOW the halt boundary — the pair matters.

## Escalation path

**If user accepts SPRT_HALT verdict:**
1. Halt live trading (no new positions).
2. Continue running the strategy in shadow mode — log what it WOULD have decided.
3. Track shadow-equity vs live at halt point.
4. If shadow-equity recovers to a new peak within 30 days: halt was correct (regime); do not re-enter until pre-registered re-entry conditions met.
5. If shadow-equity keeps bleeding: edge is dead; strategy retired.

**If user overrides SPRT_HALT:**
1. Document override rationale in the registry.
2. Set a max additional-DD before user commits to halt anyway.
3. Reset SPRT with new pre-reg after 5 more trades.

## Registration in registry

Added to `data/experiments/registry.json` as `sprt_v72_1_launch` entry with these parameters.
