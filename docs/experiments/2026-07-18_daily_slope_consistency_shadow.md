# Daily-slope-consistency shadow filter — pre-registration

**Registered UTC:** 2026-07-18T07:15:00Z
**Resolved UTC:** 2026-07-20T14:15:00Z
**Filter name:** `filter_daily_slope_consistency` (v8 strategy_engine)
**Trial id:** `daily_slope_consistency_shadow`
**Owner:** Knox
**Final verdict:** **REJECTED** at n=329 (see § Rejection verdict — 2026-07-20)

## Motivation — post-halt review

The pre-registered SPRT halt (`sprt_v72_1_launch`, then re-based `sprt_v72_1_launch_path_y`) fired at n=18. Halt monitor reads: log-LR=3.83 ≥ +2.94 halt boundary, 4W/18 (22.2%), realized DD −$9,440. Kill switch has been ON since 2026-07-13T14:30 UTC.

Splitting the 18 trades from 2026-07-01 → 2026-07-17 by direction alignment with the 20-day daily slope of GC:

| Direction vs 20d daily slope | n | Wins | WR | Total P&L | Mean/trade |
|---|---|---|---|---|---|
| COUNTER-trend | 6 | 0 | **0%** | **−$9,804** | −$1,634 |
| ALIGNED | 12 | 4 | 33% | +$1,067 | +$89 |

Every LONG entry (n=6) fired on a day where the 20d daily slope was already negative (range −$17 to −$7 per day). Zero wins. All 12 SHORT entries fired on days where 20d daily slope was negative — direction-aligned — and produced 4 wins, positive expectancy.

Root cause hypothesis: `edge_session_orb.py:59-66` `fetch_higher_tf_trend` computes a 1h-EMA-50 slope over 5 hours. That's a short-horizon momentum measure — a bounce lasting a few hours inside a multi-week down-trend flips it positive. The strategy dutifully goes LONG on those signals and gets whipsawed by the dominant tape.

The 07-13 memory (`session_2026_07_13_regime.md`) already concluded losses were **intraday microstructure, not macro-directional** — 3 of 4 launch LONG losses closed UP intraday but breakout got stopped. This filter is the microstructure governor implied by that finding: skip breakouts that fight the persistent daily direction.

## Hypothesis

For any session, if the intraday-slope-derived breakout direction opposes the sign of the 20-day daily slope of GC closes, skipping the trade improves risk-adjusted P&L relative to taking it.

**H0** (null): P(win | COUNTER-aligned) = P(win | ALIGNED) = 0.52 (Path Y baseline).
**H1** (alt): P(win | COUNTER-aligned) < P(win | ALIGNED).

## Filter specification

```python
# strategy_engine.filter_daily_slope_consistency
if not cfg.require_daily_slope_alignment:  # no-op until flag flipped
    return None
if regime.daily_20d_slope is None:  # data unavailable
    return None
if ctx.slope_at_close == 0:  # flat handled by filter_trend
    return None
intraday_sign = sign(ctx.slope_at_close)
daily_sign = sign(regime.daily_20d_slope)
if daily_sign == 0:
    return None  # ambiguous daily trend, don't gate
if intraday_sign != daily_sign:
    return "daily_slope_consistency: intraday_dir=X opposes daily_20d_slope=Y"
return None
```

**Feature computation** (`regime_context._daily_20d_slope`):
- Linear-regression slope over last 20 daily GC closes strictly before session date
- Uses `data/gc/GC_1d.csv` (already cached by `_load_gc_daily`)
- Returns None if fewer than 20 prior closes available

## In-sample effect size

### Live+shadow since 2026-07-01 launch (n=18)

| Metric | Value |
|---|---|
| Actual net P&L (no filter) | −$8,737 |
| Skips | 6 (all LONG, all counter-trend) |
| Trades kept | 12 |
| P&L on kept trades | +$1,067 |
| P&L lift | +$9,804 |
| Skip-rate | 33% of all PLANs |
| Precision on skipped losers | 6/6 = **100%** |
| p(0/6 wins | H0=0.52) | 0.0122 |
| p(0/6 wins | H0=0.33) | 0.0904 |

### Full forward log (n=32, pre-launch shadow + post-launch live)

Ran `python scripts/shadow_replay.py` after adding `daily_slope_consistency` as a fifth candidate:

| Metric | Value |
|---|---|
| Actual net P&L (no filter) | −$10,238 |
| Skips | 8 |
| Skipped W / L | 1 / 7 |
| P&L on kept trades | −$736 |
| P&L lift | +$9,502 |
| Skip-rate | 25% of all PLANs |
| Precision on skipped losers | 7/8 = **87.5%** |

Small-sample warning: precision regressed from 100% (n=6 in-sample) to 87.5% (n=8 wider-sample), consistent with mean-reversion. Still comfortably above the 60% ship gate and the 55% reject gate. Extrapolating linearly is dangerous; the ship gate requires n≥100 shadow decisions before the numbers count.

## Ship gates (ALL required)

1. **n ≥ 100 shadow decisions** across live+shadow tracker
2. **Precision on skipped losers ≥ 60%** (matches Crabel-batch ship gate)
3. **Expected P&L lift > 0** with 95% CI clearing zero (bootstrap)
4. **Skip-rate ≤ 40%** of PLANs (avoid over-filtering) unless P&L improvement is decisive
5. **No regime confound** — check that skip precision holds when partitioned by ry-bucket, so we're not just re-labeling the "ry≥2.2 regime" signal already rejected as `real_yield_gt_2_2` on 07-13.

## Rejection gates (any triggers REJECT)

- Precision on skipped losers < 55% at n=100 → REJECT
- Skip-rate > 40% at n=100 without decisive P&L improvement → REJECT
- Not cleared by **2026-10-13** (aligned with `sprt_v72_1_reentry_prereg` hard-stop) → REJECT
- Filter effect vanishes when trades are partitioned by ry-bucket (i.e., only "works" because it correlates with ry≥2.2 regime already known to underperform intraday) → REJECT

## Compliance with quant framework (memory: `quant_framework_gold.md`)

- **Pre-registration:** ✅ this doc
- **Bonferroni-N:** ✅ increments trial count in registry.json; contributes to WGC-6 adjustment
- **OOS on pre-launch data:** ✅ done via `scripts/shadow_replay.py` — n=32 forward-log replay (pre+post-launch), 87.5% skip precision, +$9,502 lift (documented above)
- **3-months-ago test:** ❌ FAILS. This filter would not have been named 3 months ago; discovered post-halt from live data. Weakens candidate strength (matches `slope_gt_8_shadow` weakness). Documented weakness accepted for shadow-only status; ship gate #5 (regime confound check) is the disciplining safeguard.
- **20-year OOS test on the underlying regime signal:** ✅ done via `scripts/oos_lon_bimodal_3bucket.py` + `scripts/crabel_crucible_regimes_daily.py`. See "Supporting OOS evidence" below.

## Supporting OOS evidence (added 2026-07-18)

Two complementary long-horizon analyses run today:

### 20yr regime-bucketed daily returns

`scripts/oos_lon_bimodal_3bucket.py` bucketed 20+ years of daily GC returns into `ry<2.0`, `2.0-2.2`, `≥2.2` at 1d/5d/20d forward horizons.

- The "MID underperforms LOW and HIGH" bimodal signature the 07-13 memory recorded at LON n=8 does NOT survive on 20yr daily data. In the 2003-2007 era (n=278 MID days), MID was strongest at 5d/20d, not weakest.
- Implication for THIS filter: the daily-slope-consistency filter is NOT the same signal as the ry-bucket claim. It skips based on 20d daily slope sign vs. intraday slope sign — orthogonal to the ry regime dimension. The 20yr null on the ry-bimodal claim does not invalidate this filter; it invalidates a different candidate.

### 60m-bar directional-hypothesis test (n=14,143, 2.5 years)

`scripts/oos_daily_slope_consistency_60m.py` — the production filter runs on 5m bars with 30-min OR; we only have 3mo of 5m. This script reformulates the CORE hypothesis at 60m resolution over 2.5 years of GC data:

> At any 60m bar, if the 5-bar EMA-50 slope on 60m closes matches the sign of the prior-20d daily GC slope, the *next-3h* signed return (signed by intraday slope direction) is systematically higher than when signs disagree.

Result:

| Bucket | n | Mean signed fwd (bps) | Pos% | t-stat |
|---|---|---|---|---|
| **ALIGNED** | 7,826 | **+1.39** | 51.5% | **+2.49** |
| COUNTER | 6,317 | −0.12 | 47.9% | −0.19 |

Delta: **+1.50 bps / 3h** aligned − counter. Aligned bucket t=+2.49 is significant at p≈0.01.

Sample size is **442× the shadow_replay n=32**. This is not conclusive proof of the full ORB filter (loses stop/target microstructure and 30-min OR window detail), but it IS direct evidence that the core directional premise ("aligning intraday slope with daily 20d slope helps") holds beyond the 18-trade launch cherry pick. The filter is capturing a real regularity, not an artifact.

Caveat: 60m/3h horizon still lives entirely in the 2024-2026 GC bull-then-correction era. A pre-2024 test would need historical 60m bars we don't have.

### Crabel crucible daily characterization

`scripts/crabel_crucible_regimes_daily.py` compared today's live regime to three historical crucibles:

| Window | Ann Sharpe | Lag-1 autocorr |
|---|---|---|
| **REFERENCE (2026-04→07 live)** | **−2.40** | +0.02 |
| Crucible 1 (2011-13 bear) | −0.95 | −0.06 |
| Crucible 2 (2020 pandemic) | +1.19 | +0.10 |
| Crucible 3 (2022 rate-hike) | −0.93 | −0.03 |

Reads-across:
- Current regime shows **worse annualized Sharpe than any historical crucible**, yet lag-1 return autocorr is **mildly positive** — trend persistence should favor breakout follow-through at the daily scale.
- The failure is NOT daily-scale mean reversion. It IS intraday microstructure, exactly what `filter_daily_slope_consistency` targets: aligning breakouts with the DAILY trend to avoid intraday bounces inside a persistent tape.
- Ship gate #5 (regime confound with `real_yield_gt_2_2`): the filter's signal is directional (daily slope sign vs intraday slope sign), not regime-bucketed. It fires equally in low-ry and high-ry environments so long as intraday and daily disagree. Partition test at n≥50 will still verify this empirically.

## Interaction with existing filters and re-entry paths

- **Does NOT flip kill switch.** Kill switch remains ON per `validation_state.json`.
- **Does NOT re-baseline SPRT.** Discipline breach per `sprt_v72_1_reentry_prereg`.
- **Does NOT enable filter in live.** `cfg.require_daily_slope_alignment` defaults to False in `SESSION_CONFIGS_V8_INITIAL`. Filter only records shadow decisions.
- **Does NOT change Path A / B / C re-entry gates.** Those remain: A (shadow ≥ +$27,390 & 5 consec ≥60%), B (ry<2.0 for 30d & shadow≥0), C (v7.3+ passes DSR + new SPRT).

## Files changed

- `src/strategy_engine.py` — added `daily_20d_slope` field to RegimeContext, added `filter_daily_slope_consistency`, registered in REGISTERED_FILTERS
- `src/regime_context.py` — added `_daily_20d_slope()` helper, wired into `build_regime_context()`
- `data/experiments/registry.json` — added `daily_slope_consistency_shadow` trial entry
- `scripts/shadow_replay.py` — added `daily_slope_consistency` to CANDIDATES + `daily_20d_slope()` feature computer for offline evaluation against the forward log
- `tests/test_strategy_engine.py` — added `TestFilterDailySlopeConsistency` (7 test cases)
- `docs/experiments/2026-07-18_daily_slope_consistency_shadow.md` — this file

## Immediate action

None. Filter registered as shadow-only. Kill switch stays ON. Shadow tracker will begin recording daily-slope-consistency decisions on the next ORB session tick after these changes deploy.

## Rejection verdict — 2026-07-20

**REJECTED at n=329 per pre-registered rejection gate #2: skip-rate above 40% ceiling without decisive P&L improvement.**

### Data source

`data/gc/GC_5m.csv` (yfinance) is capped at 60-day rolling window and gave only n=17 (in-sample launch) → n=41 (100-day yfinance backfill). Insufficient to trigger the n≥100 gate.

Substituted **XAU/USD 5m from Dukascopy** (2024-01-15 → 2026-07-20, 180,700 bars) as extended proxy. Pulled free (no account) via `dukascopy-python` package, script at `scripts/fetch_dukascopy_xauusd.py`. XAU/USD spot is ~95% correlated with GC futures — direction and skip-rate signals valid; P&L $ amounts approximate (spot vs futures basis, no roll gaps). Ran `scripts/backfill_shadow_log.py --start 2024-01-15` with GC_5m.csv temporarily swapped for XAUUSD_5m.csv, then `scripts/backfill_daily_slope_consistency.py`, then `scripts/shadow_ship_gate_report.py`. Original GC_5m.csv and pre-analysis shadow log restored after run; XAU/USD-backfilled shadow analysis preserved separately at `data/shadow_equity_xauusd_backfill_full.jsonl`.

### Ship-gate report at n=329

| Metric | Value | Gate |
|---|---|---|
| n resolved (with candidate signal) | 329 | ≥100 ✅ |
| Skip rate | **41.6%** | ≤40% ❌ (gate #2 trip) |
| Precision on skipped losers | 58.4% | ≥60% ship / ≥55% reject (in ambiguous zone) |
| P&L (no filter) | -$5,495 | — |
| P&L (with filter applied) | -$9,191 | — |
| P&L lift (total) | **-$3,696** | positive required |
| P&L lift (mean/trade) | **-$11.23** | positive required |
| Bootstrap 95% CI on mean lift | **[-$77, +$49]** | must clear zero (does NOT) |

Skip counts: 137 skipped of 329 → 57 wins skipped + 80 losses skipped (precision 58.4%).

### Verdict logic

Per pre-reg § Rejection gates:
- ~~Precision < 55% at n=100 → REJECT~~ — 58.4% is above 55% floor, does not trip
- **Skip-rate > 40% at n=100 without decisive P&L improvement → REJECT** — 41.6% > 40% AND P&L lift is negative with CI spanning zero (not decisive improvement) → **TRIP**
- ~~Not cleared by 2026-10-13 → REJECT~~ — resolved earlier
- ~~Regime confound with ry-bucket → REJECT~~ — not the failure mode

Second consideration: the *direction* of the P&L result. Filter costs $11/trade on average; the trades it skips are, on net, *better* than the trades it keeps. This is not a "filter doesn't work" — this is a "filter has anti-signal."

### Bigger finding: Path Y itself

Unfiltered Path Y P&L on the same n=329 XAU/USD sample: **-$16.70/trade average** (-$5,495 over 2.5 years). The strategy without any additional filter shows negative expectancy at 329-trade sample size on XAU/USD proxy.

This retroactively **validates the `sprt_v72_1_launch_path_y` halt** at n=18 → the halt was not unlucky sequencing; it was correctly identifying a strategy without positive expectancy. The n=41 yfinance backfill showed unfiltered Path Y as +$78/trade over 100 days — that was small-sample optimism; at 3.3× the sample it flips negative.

### Caveats

1. **XAU/USD ≠ GC.** ~95% correlated. Direction and precision signals valid; contract math (P&L $ amounts) is approximate (spot vs futures basis, contract multiplier).
2. **Skip rate margin.** 41.6% is only 1.6pp above the 40% ceiling. The gate trips with a margin, not a landslide. But precision (58.4%) is also below the ship floor (60%), so both indicators point the same direction.
3. **Post-hoc filter selection.** Pre-reg noted dsc fails the 3-months-ago test (discovered post-halt from live data). Rejection at n=329 confirms the guarded-skepticism was warranted.

### Downstream actions taken

- Registry entry `daily_slope_consistency_shadow` updated to `verdict: rejected`, n=329
- Registry entry `knox_soft_launch_engine_b` updated to `verdict: deprecated_by_dependency` (Knox soft-launch config `SESSION_CONFIGS_V8_B` used `require_daily_slope_alignment=True`, now retired)
- Registry entry `knox_sprt_prereg` updated to `verdict: deprecated_never_activated` (Knox never accumulated n=50 needed to activate)
- `data/knox_state.json` disabled with reason "dsc_rejected_at_n329"
- VPS `.env.vps` `KNOX_RESEARCH_ENABLED=0` (was already 0 — Knox research channel never created)
- No live systems affected (Knox never dispatched; Engine A remains halted per prior pre-reg)

### Next candidate for Engine B (v9)

**Volker Knapp asymmetric ER-based stops** (Kaufman Ch 17 p.792, filed 2026-07-20 in `memory/kaufman_ch17_readnotes.md`). Directly addresses the LONG-stops failure mode that dsc failed to address. Requires new pre-reg doc + new registry entry; NOT auto-inherited from this experiment. Halt discipline for Engine A remains independent — Path A/B/C re-entry conditions unchanged.
