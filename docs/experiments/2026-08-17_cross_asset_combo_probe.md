# Cross-asset combo probe: gold v1 + palladium LONG-only

**Date:** 2026-08-17 (session extension)
**Author:** Knox
**Status:** Research finding, does NOT change ship stance.

## Purpose

Follow-up from `docs/experiments/2026-08-17_universe_probe.md`. Palladium LONG-only failed OOS discipline standalone. Question: do the two signals fire on complementary weeks such that combining them into a portfolio gives diversification benefit? If yes, that is a real research result even if palladium never ships alone.

## Test

Script: `scripts/cross_asset_combo_probe.py`. Window 2010-01-01 to 2026-08-14. For each week, compute both gold v1 direction (LONG/SHORT/FLAT) and palladium v1 LONG signal. Report:
- Overlap between weeks
- Correlation of same-week returns when both fire
- Portfolio metrics (50/50 blend when both fire, full weight when only one fires)

## Results

### Week overlap (n=833)

| category | count | % |
|---|---|---|
| Both fire directional | 89 | 10.7% |
| Only gold fires | 274 | 32.9% |
| Only palladium fires | 61 | 7.3% |
| Neither fires | 409 | 49.1% |

Signals are complementary. Only about 11% of weeks see both fire. Palladium fires directional 150 times over 16 years, and 60 of those weeks (40%) are weeks where gold is FLAT. The two rules identify different market conditions.

### Same-week correlation

**+0.149** on 89 both-fire weeks. Very low. Two mostly-uncorrelated signals.

### Standalone performance (directional weeks only)

| metric | gold v1 (LONG+SHORT) | palladium LONG-only |
|---|---|---|
| n | 363 | 150 |
| Win rate | 55.9% | 57.3% |
| Mean R | +0.230% | +0.635% |
| Sharpe (ann) | +0.778 | +1.302 |
| Cum R | +83.4% | +95.3% |
| Max DD | 22.3% | 30.3% |

### 50/50 blend (either leg fires)

| metric | value |
|---|---|
| n | 424 |
| Win rate | 55.2% |
| Mean R | +0.307% |
| Sharpe (ann) | +0.974 |
| Cum R | +130.2% |
| Max DD | 21.3% |

Portfolio Sharpe (0.97) sits between the two legs. Cumulative return is highest of the three (more weeks with signal = more opportunities). Max drawdown is lower than palladium alone.

## The honest read

The diversification benefit IS real. Two low-correlation signals fire on mostly-different weeks. A portfolio captures more of the total opportunity set with variance reduction.

But this does NOT validate palladium. The blend's Sharpe (0.97) is a weighted average of the two Sharpes; combining an underpowered signal with a proven one produces something in between, not something new. Palladium's individual OOS test still failed (mean R 0.475%, CI includes zero). If we shipped the blend to subscribers, we would be dressing up an unvalidated signal with a validated one and calling the average "proof."

The pattern to remember: **diversification is a variance transformation, not an alpha generator**. If palladium has no real edge (which is the honest reading of its OOS test), then over enough live trades the blend converges to gold alone, minus the operational overhead of running two signals.

## What this means for NORTH

Nothing changes for the immediate soft launch. NORTH publishes gold v1. Full stop.

If palladium's shadow log (not yet running - we did not add it after the OOS rejection) were to accrue 50+ forward signals AND continue to show +0.5%+ mean R AND positive-year pattern held, then re-running this combo probe with fresh data would be the right way to consider shipping a two-asset product.

## Files

- Script: `scripts/cross_asset_combo_probe.py`
- Registry entry: (not added - this is a research probe, not a pre-registered candidate)
- Related: `docs/experiments/2026-08-17_universe_probe.md`

## What NOT to do based on this

- Do not ship the 50/50 blend to subscribers. Palladium leg is unvalidated.
- Do not add palladium to the public weekly card as a "companion signal." Would violate the same discipline that has kept 34 dead strategies dead.
- Do not re-run this test with tuned weights or with additional assets in the blend. That is post-hoc portfolio optimization, well-documented as a way to over-fit history.
