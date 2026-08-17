# Universe expansion probe (platinum, palladium, GDX, GDXJ)

**Date:** 2026-08-17
**Author:** Knox
**Status:** Data probe complete. Palladium LONG surfaced as candidate; OOS discipline test **rejected** it. Underpowered.

## Purpose

The next-agenda item was "universe expansion" with a warning against naive gold-rule transfer. Before designing native signals per asset, I ran a data probe: apply gold v1's exact rule structure to each candidate's own price series and see what surfaces. This is a probe, not a ship gate.

## The probe

Script: `scripts/universe_v1_probe.py`

Rule (identical to gold v1): LONG if M20>0, M60>0, MA10>MA40, RY_chg<0. SHORT if inverted. Signal at Friday close, enter Monday open, exit Friday close, 2xATR stop from entry.

Assets: PL=F (platinum), PA=F (palladium), GDX (VanEck Gold Miners), GDXJ (Junior Miners). All from yfinance, 2010-2026, daily.

## Probe results (full sample, contains data snooping)

| asset | dir | n | WR | mean R | Sharpe | cum R | DD | +yrs |
|---|---|---|---|---|---|---|---|---|
| Platinum | all | 260 | 46.9% | +0.109% | 0.264 | +28% | 38% | 10/17 |
| Palladium | all | 252 | 52.0% | +0.184% | 0.348 | +46% | 67% | 10/17 |
| **Palladium** | **LONG** | **150** | **57.3%** | **+0.635%** | **1.302** | **+95%** | **30%** | **13/16** |
| Palladium | SHORT | 102 | 44.1% | -0.479% | -0.837 | -49% | 66% | 7/16 |
| GDX | all | 331 | 45.6% | -0.329% | -0.497 | -109% | 142% | 6/17 |
| GDXJ | all | 309 | 46.0% | -0.365% | -0.479 | -113% | 142% | 5/17 |

Platinum and both miner ETFs (GDX, GDXJ) are weak or actively negative. **Palladium LONG stood out** with 1.302 Sharpe and 13/16 positive years.

## Palladium LONG — OOS discipline test

Script: `scripts/universe_palladium_oos.py`

Split: TRAIN 2010-2017, OOS 2018-2026. Bonferroni n=8 (4 assets x 2 directions probed).

| window | n | WR | mean R | +yrs | CI | p_adj |
|---|---|---|---|---|---|---|
| TRAIN 2010-2017 | 85 | 58.8% | +0.757% | 8/8 | [+0.21%, +1.32%] | 0.060 |
| OOS 2018-2026 | 65 | 55.4% | +0.475% | 5/8 | [-0.58%, +1.59%] | 1.000 |

## Gate verdict

- Gate 1 (OOS CI clears 0 AND p_adj < 0.05): **FAIL** (CI includes zero, p_adj = 1.0)
- Gate 2 (OOS positive years >= 60%): PASS (62%)
- Gate 3 (OOS mean R > 0.5% per trade): **FAIL** (0.475% just below floor)

**Verdict: REJECT.**

## The recurring pattern

This is the third time we have seen this profile:

1. Silver GSR (2026-08-03): mean R +0.115%, ci_low fails, positive years pattern holds
2. Gold basis LONG-only (2026-08-03): same shape
3. Palladium LONG (2026-08-17): mean R +0.475%, ci_low fails, positive years pattern holds

The gold-momentum family produces *plausible* signals on adjacent assets. The pattern is real in the "annual P&L is positive most of the time" sense. But per-trade variance is high enough that CIs blow past zero and Bonferroni kills the p-value. All three are underpowered, not flat.

The honest read: **these are candidates for shadow-log forward tracking, not ship candidates.** If any of them accrues 100+ live signals with the same mean-R pattern intact, revisit for graduation.

## What I am NOT doing

- Not sweeping palladium parameters to find a passing configuration.
- Not adding palladium to a shadow log yet — three underpowered candidates already accruing (gold basis + silver GSR are live; adding a third would strain the operator surface without new information). Only add if we retire one of the current shadows.
- Not testing platinum or miners further. Both showed no edge and no interesting pattern.

## What I might do next

If the user wants to keep pushing universe expansion, the honest options are:
- **Cross-asset combos:** basket of (gold v1 + palladium v1 LONG). If they trigger on different weeks, uncorrelated variance might combine well. Requires backtest.
- **Miner leverage:** GDX with **gold's** signal (not miners' own signal). Miners often lead physical gold; a positive gold v1 might be amplified by trading GDX instead. Different test than what we ran here.
- **Structural signals:** Pt/Pd ratio mean reversion (industrial rotation), Au/USD DXY correlation break (tail-risk regime), etc. Each needs its own pre-reg and probably fails the same underpowered gate.
