# Deep-analysis findings — 2026-07-20 (interim, NOT a ship candidate)

**Written UTC:** 2026-07-20T15:15:00Z
**Status:** Interim findings from n=1018 XAU/USD ORB analysis + n=985 XAG/USD cross-check. NOT a shippable candidate. Requires further validation before any pre-reg or live decision.

## What was run

`scripts/deep_analysis_orb.py` on Dukascopy XAU/USD 5m (2024-01-01 → 2026-07-20). For each of 1,018 Path-Y-taken entries, simulated outcome under both FORWARD (buy breakout) and FADE (invert direction). Then partitioned across session × direction × ER band × or_atr ratio × day-of-week × hour.

`scripts/ny_short_deep_dive.py` on the NY-SHORT subset — the only quadrant with positive edge — computed bootstrap CI, temporal stability, concentration risk, and tighter filter combos.

`scripts/deep_analysis_orb.py` re-run on XAG/USD 5m for cross-market comparison.

## Key finding: NY SHORT sub-edge in gold

Path Y overall on n=1018 XAU/USD:
```
FORWARD: -$24.80/trade, -$25,249 total, 50% win
FADE:    -$29.91/trade, -$30,451 total, 48.7% win
```

Both directions lose overall. Fade does NOT rescue Path Y.

But session × direction breakdown reveals:
```
                LONG                    SHORT
ASIA    n=120  -$22/trade         n=81   -$197/trade
LON     n=226  -$7/trade          n=149  -$154/trade
NY      n=256  -$47/trade         n=186  +$161/trade  ← ONLY winning quadrant
```

Tightening filters on the NY-SHORT subset:
```
NY SHORT (all)                  n=186  mean +$161  total +$29,874  CI includes 0
NY SHORT + not-Fri              n=149  mean +$227  total +$33,755
NY SHORT + Low ER (<0.30)       n=139  mean +$270  total +$37,558
NY SHORT + Low ER + not-Fri     n=112  mean +$320  total +$35,827
NY SHORT + Low ER + Mon-Wed     n= 91  mean +$409  total +$37,258  CI [+$45, +$760]
```

**The tightest filter (NY SHORT + Low ER + Mon-Wed) is the only combination whose bootstrap 95% CI clears zero.** 36 trades/year at +$409/trade. Win rate 62.6%.

## Concentration risk — READ THIS BEFORE ANY DECISION

Top 5 trades in the n=91 subset = +$23,847 (**64% of total P&L**)
Top 10 trades = +$33,132 (**89% of total**)
Excluding top 5% (5 trades): mean drops from +$409 to +$156/trade — still positive but 3× smaller

This is a **positive fat-tail** strategy. The edge exists in a small number of outlier winners. This has three consequences:

1. **Fragile to filter drift.** Any additional filter that would exclude even 2-3 of the top winners kills most of the edge.
2. **Slippage/execution risk is asymmetric.** If our fills on winners are 10% worse than modeled (missed target by a tick, etc.), we lose disproportionately. If fills on losers are 10% worse, negligible impact.
3. **Live-forward evidence collection is slow.** At 36 trades/year, hitting n=100 live takes ~2.8 years. Small-sample volatility will be extreme.

## Temporal trajectory (n=91 NY-SHORT+LowER+Mon-Wed)

```
2024 H1: -$2,443 at n=21   ← losing period
2025 H1: +$1,000 at n=41   ← turned positive
2025 H2: +$6,224 at n=61
2026 H1: +$27,916 at n=71  ← 2026 Q1 = +$21k in 10 trades ← concentrated
2026 H2: +$37,258 at n=91  ← recent gain +$9k in 20 trades
```

The edge STRENGTHENED in 2025-2026. This is concerning because:
- Could be regime-favorable pattern that will reverse
- Could be data-mining artifact (we selected filters using this data — look-ahead bias in the filter design itself)
- Could be genuine edge that emerged as gold's volatility regime shifted (2024 low-vol → 2026 high-vol correction phase)

## Real GC 5m confirmation (60-day yfinance) — SIGN MATCHES

Ran `scripts/deep_analysis_orb.py` on `data/gc/GC_5m.csv` (real GC futures, yfinance 60-day rolling window, n=117 entries). Small sample but authentic gold FUTURES data, not spot proxy.

Session × Direction cross-tab:
```
              LONG                     SHORT
ASIA    n=13  -$4/trade         n=22  -$161/trade  ← loses
LON     n=12  -$340/trade       n=22  -$498/trade  ← loses  
NY      n=17  -$99/trade        n=31  +$36/trade   ← positive (only quadrant)
```

n=31 NY-SHORT on real GC = +$36/trade, +$1,116 total, 54.8% win rate.

**Directional sign matches XAU/USD n=1018 finding.** Same quadrant (NY + SHORT) is the only winner on both datasets. Different sample sizes (31 vs 186), different data sources (yfinance GC futures vs Dukascopy XAU spot), same finding.

This is meaningful non-trivial confirmation that the edge is NOT a spot-vs-futures data artifact. Increases confidence in the finding from ~40% to ~55-65%.

## Knapp v9 reproduction study — REJECTED

Ran `scripts/oos_knapp_paired.py` on EUR/USD, GBP/USD, USD/JPY (all Dukascopy, n≈1,200 each):

```
EUR/USD  n=1216  paired lift +/-$0.00/trade  CI spans zero
GBP/USD  n=1203  paired lift +/-$0.00/trade  CI spans zero
USD/JPY  n=1226  paired lift +$0.20/trade    CI [-$0.12, +$0.51], spans zero
```

(FX P&L values are per unit under CONTRACT_SIZE=100; scale up 100x for realistic dollar terms → still under +$50/trade ship gate.)

Combined with gold's +$2.35/trade lift, **Knapp v9 candidate FAILS the reproduction gate.** Registry entry `knapp_er_stops_v9` should be updated from `pre_registered_draft` → `rejected_pre_apply` reason "reproduction study failed on 3 markets + gold below ship gate."

## Silver cross-check — INCONCLUSIVE

`data/external/dukascopy/XAGUSD_5m.csv` (180,510 rows, same 2024-2026 window)

```
SILVER: n=985  forward -$24/trade  fade -$24/trade  win rate 13%
```

**13% win rate on silver is anomalous.** Investigation shows this is likely a simulator artifact — silver's smaller per-oz point value (~$0.20 5m OR-range vs gold's ~$5) causes most 5m bars to have BOTH the stop AND target level within their intra-bar high-low range. The paired simulation resolves these ambiguities conservatively (both-hit = stop), producing artificial losses.

To do a clean silver cross-check, outcome simulation would need to drop to 1m or tick resolution. Deferred.

**Consequence:** silver comparison neither confirms nor refutes gold's NY-SHORT edge. Cross-market validation remains an open question. This weakens the confidence bound on the finding.

## Fade at ER≥0.60 (n=37)

Small-sample but striking:
```
FADE (invert) at ER>=0.60:  n=37  mean +$587/trade  total +$21,745
```

37 trades over 2.5 years = ~15/year. Too rare to be a standalone strategy. But: shorting confirmed-uptrend breakouts (LONG signal in strong-trend ER) at the OR level is essentially a "fade-into-resistance" contrarian play. Interesting hypothesis but not enough n to pre-register.

## What this does NOT change

- Engine A halt stays ON. n=91 filtered NY-SHORT is NOT a Path Y rescue; it's a NEW candidate that must go through fresh pre-reg, DSR, SPRT gates.
- Bonferroni-N in registry has grown significantly with today's analysis (session partition + direction partition + ER band partition + day-of-week partition + or_atr partition + concentration test + silver cross-check ≈ 8+ additional trials that must count toward N for any candidate we pre-register from this session).
- `knapp_er_stops_v9` draft still relevant but likely-to-fail per the +$2.35/trade result on gold.

## Provisional next candidate: Path Z (NY-SHORT + Low-ER + Mon-Wed)

If we choose to pre-register this, the design would be:

- **Entry:** NY session ORB (13:00 UTC breakout of 30-min OR) with slope-derived direction = SHORT (i.e., prior 5h EMA-50 slope negative on 1h bars)
- **Filter 1:** Efficiency Ratio on 20 bars of 5m closes ending at OR close is < 0.30
- **Filter 2:** Day of week ∈ {Monday, Tuesday, Wednesday}
- **Stop / Target:** Path Y default (stop_dist = or_range, target = or_range × 1.0)
- **Contract size:** 1 GC contract initially (50% ramp per Path B discipline)

**Expected characteristics (in-sample):**
- ~36 trades / year
- Mean +$409/trade in-sample (severe overfit risk — filters selected using same data)
- Bootstrap 95% CI [+$45, +$760] (clears zero but wide)
- 62% win rate
- Median trade +$486
- Fat right tail — 64% of P&L in top 5 trades

**Requirements before pre-reg:**
1. **Adjust for Bonferroni-N** — count today's segmentation multiplicity
2. **DSR compute** with the wider trial count
3. **Live-forward validation** — accumulate n≥50 fresh NY-SHORT+LowER+Mon-Wed decisions before real capital
4. **Concentration robustness test** — Sharpe / rolling drawdown / max-consecutive-loss analysis
5. **Kaufman gold-caution acknowledged** — this candidate IS a gold-specific pattern (silver cross-check failed for microstructure reasons; if we can fix that and silver ALSO shows it, confidence rises)

**Estimated confidence level right now: ~40-55%** this is a real edge vs data-mining. That's higher than most rejected candidates (dsc was ~25% at n=17) but lower than the ship threshold (~85% for live capital deployment).

## Recommendation

**Do NOT pre-register Path Z today.** Do:

1. Continue live forward on VPS (Engine A halted, so no new Path Y trades accumulate — but VPS is documenting shadow decisions)
2. Rewrite `scripts/backfill_shadow_log.py` with a NY-SHORT-restricted config variant
3. Wait 4-6 weeks for fresh forward decisions to accumulate in the tight-filter subset (~4-6 trades organically)
4. If the fresh forward maintains the +$400/trade signature, THEN pre-register Path Z with proper Bonferroni-adjusted DSR
5. Concurrently: try to fix silver simulator (drop to 1m outcome resolution) for a clean cross-market validation

## Files produced today

- `scripts/deep_analysis_orb.py` — market-agnostic ORB deep analysis (forward + fade, all partitions)
- `scripts/ny_short_deep_dive.py` — sub-analysis of the NY-SHORT quadrant
- `scripts/fetch_dukascopy_symbols.py` — multi-symbol fetcher, extends earlier XAU/USD-only script
- `data/external/dukascopy/XAUUSD_5m.csv` — 180,700 bars (already committed)
- `data/external/dukascopy/XAGUSD_5m.csv` — 180,510 bars silver
- `data/external/dukascopy/EURUSD_5m.csv` — for Knapp reproduction study (unused so far)
- `data/external/dukascopy/GBPUSD_5m.csv` — for Knapp reproduction study
- `data/external/dukascopy/USDJPY_5m.csv` — for Knapp reproduction study
- `data/analysis_gold_trades.csv` — n=1018 raw paired-outcome table
- `data/analysis_silver_trades.csv` — n=985 raw paired-outcome table

## Bonus: Hetzner utilization monitoring live

`ops/vps/system_stats.sh` + `ops/systemd/gdt-sysstats.{service,timer}` deployed to VPS. Logs CPU/RAM/disk every 15 min to `/home/gdt/system_stats.csv`. End-of-week report will include capacity utilization for second-project sizing.
