# GDX-as-vehicle probe: gold v1 signal, miner ETF trade

**Date:** 2026-08-17 (session extension)
**Author:** Knox
**Status:** Research finding. Does NOT change ship stance. Pre-registered follow-up needed if pursued.

## Purpose

Different question than the universe probe. The universe probe asked "does GDX have its own tradeable momentum" (answer: no, actively negative). This asks "if we use GOLD'S signal but trade GDX as the vehicle, do miners' operational leverage give us amplified returns?"

Mechanism: gold miners typically have operational leverage on gold's move because their profit is a lever on the gold-vs-mining-cost spread. On a good gold signal, GDX might return 2-3x what gold returns.

## Test

Script: `scripts/gdx_vehicle_probe.py`. For each week 2010-2026 where gold v1 fires directional, compute:
- The gold trade (Monday open to Friday close, 2xATR stop)
- The GDX trade (same window, GDX prices, GDX-specific ATR stop)

## Results

### All directional trades (n=363)

| metric | gold (native) | gdx (via gold v1) |
|---|---|---|
| Win rate | 55.9% | 53.7% |
| Mean R per trade | +0.230% | +0.303% |
| Std R per trade | 2.13% | 4.52% |
| Sharpe (ann) | 0.778 | 0.482 |
| Cum R | +83.4% | +109.9% |
| Max DD | 22.3% | 49.8% |

GDX returns more per trade but with double the variance. Sharpe drops. The extra return does not compensate for the extra risk.

### LONG only (n=223) - the interesting finding

| metric | gold LONG | gdx LONG |
|---|---|---|
| Win rate | 59.2% | 57.4% |
| Mean R per trade | +0.301% | +0.657% |
| Sharpe (ann) | 0.989 | 1.062 |
| Cum R | +67.0% | +146.6% |
| Max DD | 12.4% | 24.8% |

**GDX genuinely amplifies gold's LONG signal.** Higher mean R, higher cum R, and slightly higher Sharpe despite double the drawdown. The operational leverage story holds up on the LONG side.

### SHORT only (n=140) - the killer

| metric | gold SHORT | gdx SHORT |
|---|---|---|
| Win rate | 50.7% | 47.9% |
| Mean R per trade | +0.117% | -0.262% |
| Sharpe (ann) | +0.415 | -0.413 |
| Cum R | +16.3% | -36.7% |
| Max DD | 20.7% | 67.0% |

**GDX destroys the gold SHORT signal.** Miners do not cooperate on down-moves. When gold falls, miners often fall less (hedging, sticky costs, alternative revenue streams). The asymmetry kills the strategy.

### Empirical GDX beta to gold on these trades: 1.38

Lower than the naive 2.0 that miners are often quoted as. In weekly windows with the specific gold v1 filter, miners are only 1.4x leveraged.

## The honest read

There is a legitimate signal here: **gold v1 LONG traded via GDX outperforms gold v1 LONG traded via gold**, at the cost of double the drawdown. If a subscriber is comfortable with 25% drawdown for 2x expected return, this is a reasonable vehicle swap.

But: this is a full-sample number. No pre-registration, no OOS split, no ship-gate test. Same discipline problem as the universe probe: an interesting pattern on the full sample is not proof of a live edge.

And: the SHORT side actively destroys, so any product would have to be LONG-only, which loses about 40% of the total signal count.

## Legitimate follow-up (would need its own pre-reg)

- Formal OOS test on gold v1 LONG traded via GDX (train 2010-2017, OOS 2018-2026, Bonferroni for having probed this).
- Consider GLD (gold ETF) as an intermediate vehicle: 1x gold, tax-advantaged for retail, no options-implied cost.
- If OOS holds: consider offering GDX as a "higher-conviction vehicle" note in the weekly card when the LONG signal fires. Not a new signal, a note about vehicle choice.

## What NOT to do

- Do not add GDX as an automatic secondary signal. Would violate pre-reg discipline (this was probed after gold v1 was already known to work).
- Do not use these numbers in any subscriber-facing marketing. Full-sample, unvalidated.
- Do not test other miner vehicles (GDXJ, individual miners) post-hoc. Would compound the multiple-testing problem.
