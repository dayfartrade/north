# NORTH - the retirement wall

*Auto-generated from `data/experiments/registry.json` on 2026-08-30. 34 rejected trials on record.*

Why this exists: NORTH publishes signals. Signals fail. We show every failure here so subscribers can judge the discipline honestly. If it isn't on this list, we haven't tested it. If it is, here's what happened and why we killed it.

- **Trials ever run:** 52
- **Rejected / retired:** 34
- **Currently live:** NORTH v1 weekly gold read (5 historical shipping entries in registry, most are pre-NORTH engines that have since been retired)

---

## Rejected trials, newest first

### `universe_palladium_long_v1_signal`

- **Verdict:** rejected_gate1_gate3_underpowered
- **Resolved:** 2026-08-17T06:15:00Z
- **Observations:** 65
- **SR per period:** 0.181
- **Why:** Universe expansion probe: applied gold v1 rule (M20/M60/MA10-40/RY_chg, weekly cycle, 2xATR stop) to platinum, palladium, GDX, GDXJ

### `north_bb_v1_replacement_test`

- **Verdict:** rejected_below_ship_threshold_and_below_v1
- **Resolved:** 2026-08-17T05:30:00Z
- **Observations:** 363
- **SR per period:** 0.109
- **Why:** BB(20,2) entry/exit on 4H XAUUSD, same v1 signal (M20/M60/MA10-40/RY_chg)

### `silver_gsr_oos_revisit_v1`

- **Verdict:** rejected_gate1_underpowered
- **Resolved:** 2026-08-03T11:23:20Z
- **Observations:** 131
- **SR per period:** 0.113
- **Why:** Fresh pre-reg of Silver GSR z-score reversion, single-config (lookback=180, |z|>=1

### `gold_basis_long_only_oos_v1`

- **Verdict:** rejected_gate1_underpowered
- **Resolved:** 2026-08-03T11:09:02Z
- **Observations:** 54
- **SR per period:** 0.229
- **Why:** Fresh pre-reg of LONG-only gold basis mechanism (post-hoc finding from gold_basis_janus_transplant_v1)

### `gold_basis_janus_transplant_v1`

- **Verdict:** rejected_baseline_positive_direction
- **Resolved:** 2026-08-03T11:07:12Z
- **Observations:** 255
- **SR per period:** 0.077
- **Why:** Janus funding-extreme transplant to gold via futures basis (GC=F minus XAUUSD spot)

### `silver_candidate_1_native_momentum_v1`

- **Verdict:** rejected
- **Resolved:** 2026-08-03T11:01:49Z
- **Why:** Silver-native momentum + industrial macro (copper/silver ratio, oil, ISM)

### `silver_candidate_2_gsr_zscore_reversion_v1`

- **Verdict:** rejected
- **Resolved:** 2026-08-03T11:01:49Z
- **Why:** Gold-silver ratio z-score extreme reversion

### `silver_candidate_3_vol_regime_v1`

- **Verdict:** rejected
- **Resolved:** 2026-08-03T11:01:49Z
- **Observations:** 192
- **SR per period:** -0.044
- **Why:** Silver volatility regime signal

### `far_weekly_gold_seed2_countertrend_fade_v1`

- **Verdict:** rejected
- **Resolved:** 2026-07-29T06:06:12Z
- **Observations:** 29
- **SR per period:** 0.006
- **Why:** Davey Seed 2 countertrend fade: SHORT if 4w-high AND close < close[8w ago]; LONG mirror

### `far_weekly_gold_put_spread_income_v1`

- **Verdict:** rejected_ship_gates
- **Resolved:** 2026-07-24T13:15:00Z
- **Observations:** 379
- **SR per period:** 0.0114
- **Why:** Put-spread variant of C1 (short 5-delta + long 2-delta)

### `far_weekly_gold_ml_direction_v1`

- **Verdict:** rejected_ship_gates
- **Resolved:** 2026-07-24T12:00:00Z
- **Observations:** 175
- **SR per period:** 0.0111
- **Why:** LogReg on 8 features (M20, M60, MA_ratio, ATR_pct, RY_chg, DXY_chg, GVZ_z, nc_z)

### `far_weekly_gold_short_put_income_v1`

- **Verdict:** rejected_ship_gates
- **Resolved:** 2026-07-24T11:35:00Z
- **Observations:** 379
- **SR per period:** -0.0419
- **Why:** Options-selling income (BSM 5-delta puts on gold weekly, GVZ as IV)

### `gold_seasonality_v1`

- **Verdict:** rejected_ship_gates
- **Resolved:** 2026-07-24T10:25:00Z
- **Observations:** 169
- **SR per period:** -0.0132
- **Why:** Seasonality signal: LONG in top-3 months by mean return (Aug, Jan, Feb from 2010-2019 discovery), SHORT in bottom-3 (Sep, Nov, May)

### `far_weekly_gold_cot_extreme_v1`

- **Verdict:** rejected_ship_gates
- **Resolved:** 2026-07-24T09:55:00Z
- **Observations:** 80
- **SR per period:** 0.0628
- **Why:** Contrarian standalone signal on nc_net 52wk z-score (|z|>2)

### `far_weekly_wti_read_v1`

- **Verdict:** rejected_ship_gates
- **Resolved:** 2026-07-24T06:25:00Z
- **Observations:** 96
- **SR per period:** -0.0169
- **Why:** FAR Weekly WTI v1 (M60 + DXY on WTI)

### `far_weekly_bitcoin_read_v1`

- **Verdict:** rejected_ship_gates
- **Resolved:** 2026-07-24T06:10:00Z
- **Observations:** 89
- **SR per period:** -0.0708
- **Why:** FAR Weekly BTC v1 (M60 + DXY on BTC)

### `far_weekly_meta_labeling_v1`

- **Verdict:** rejected_ship_gates
- **Resolved:** 2026-07-22T14:45:00Z
- **Observations:** 252
- **SR per period:** 0.138
- **Why:** Prado AFML Ch 3

### `path_z_ny_short_shadow`

- **Verdict:** rejected_oos_test
- **Resolved:** 2026-07-22T09:38:33.577744+00:00
- **Observations:** 91
- **Why:** SHADOW pre-reg (v9 candidate #2): filter_path_z

### `knapp_er_stops_v9`

- **Verdict:** rejected_pre_apply
- **Resolved:** 2026-07-20T16:45:00Z
- **Observations:** 1018
- **Why:** REJECTED pre-apply on 2026-07-20 (same-day resolution): reproduction study failed on 3 non-gold markets + gold below ship gate

### `daily_slope_consistency_shadow`

- **Verdict:** rejected
- **Resolved:** 2026-07-20T14:15:00Z
- **Observations:** 329
- **Why:** REJECTED at n=329 per pre-reg rejection gate #2 (skip-rate 41

### `real_yield_gt_2_2_shadow`

- **Verdict:** rejected_pre_apply
- **Resolved:** ?
- **Observations:** 24
- **Why:** REJECTED before apply (2026-07-13 11:00 UTC): OOS regime test on 20+ years fails

### `backfill_2026_07_07_rejected_01`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_02`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_03`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_04`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_05`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_06`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_07`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_08`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_09`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_10`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_11`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `backfill_2026_07_07_rejected_12`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** Backfilled from 2026-07-07 sweep — 12 hypotheses tested and rejected without per-variant SR recording

### `janus_q4_trailing_stop`

- **Verdict:** rejected
- **Resolved:** ?
- **Why:** REJECTED per pre-reg (docs/experiments/2026-07-07_janus_q4_trailing_stop

---

## What is currently live

**NORTH v1** - weekly gold direction call. Published every Sunday 22:00 UTC on the public Telegram channel. Signal is a 4-condition momentum + macro filter (M20, M60, MA10 vs MA40, 20-day change in US 10y real yield). The call publishes for the following Monday-Friday window with a defined entry, stop, and time-based exit. If any condition disagrees, the call is FLAT and no trade is taken that week.

Everything else in this repo is either a retired engine, a shadow-log candidate accruing forward evidence, or an internal research artifact.
