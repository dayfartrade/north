# Pre-registration: FAR Weekly Gold Seed 2 — Countertrend Fade v1

**Registered UTC:** 2026-07-29T05:55:00Z
**Trial id:** `far_weekly_gold_seed2_countertrend_fade_v1`
**Author:** Knox
**Source of idea:** Davey Appendices A/B/C (Euro Day) — mean-reversion countertrend fade of short-term extreme, filtered by opposite medium-term trend. Filed as Seed #2 in `davey_pre_reg_seeds.md`, ranked #1 of 3.

## Motivation

We currently ship one mechanism family (v1 momentum + macro). Every candidate discovered in the 2026-07-24 session died at OOS or shadow gates. To open a genuinely uncorrelated second product line, we need a **different mechanism family** — not a filter or a filter-of-filter of v1.

Countertrend fade of a 4-week extreme + medium-term trend agreement is:
- **Not correlated with v1** (v1 = momentum-continuation; this = fade of local extreme when the medium term still supports the fade direction)
- **Fires when v1 is FLAT** (55% of weeks in backtest) — potential ensemble complement
- **Purely price-based** — no macro dependency (v1 uses RY; failure of RY series would not kill Seed 2)
- **Two-timeframe check (4w + 8w)** matches Davey's robustness pattern

If Seed 2 clears the ship gates below, and its daily returns show R² correlation < 0.5 with v1's daily returns (Davey Ch 15 diversification test), it becomes the second product family candidate.

## Signal definition (FROZEN BEFORE BACKTEST)

Weekly cycle. Signal computed on Sunday's most-recent close (aligned with v1 publisher).

**LONG entry when BOTH:**
1. This week's low ≤ 4-week rolling low (weekly bars, 4 completed weeks)
2. Close > close[8 weeks ago] (medium-term uptrend still in force)

**SHORT entry when BOTH:**
1. This week's high ≥ 4-week rolling high (weekly bars, 4 completed weeks)
2. Close < close[8 weeks ago] (medium-term downtrend still in force)

**Else:** FLAT (no position).

## Position management (FROZEN)

- **Entry:** next Monday open (approximated as Sunday close in backtest, matching v1)
- **Stop:** entry ± 2 × ATR(20) — same as v1
- **Target:** Friday close (time exit) OR stop hit
- **Size:** 1 contract equivalent
- **Cost:** $5 round-trip (match v1 convention)
- **No macro filter** (deliberate — this mechanism must stand alone)

## Ship gates (all must pass on OOS 2019-2026)

| # | Gate | Threshold | Rationale |
|---|------|-----------|-----------|
| 1 | OOS Sharpe (annualized) | ≥ 0.60 | Davey Table 7.1 floor; matches our template |
| 2 | OOS Profit Factor | > 1.5 | Davey Table 7.1 |
| 3 | OOS Return / MaxDD | > 2.0 | Davey Table 7.1 |
| 4 | OOS n | ≥ 50 | Countertrend fires less often; 50 tolerable |
| 5 | Positive Sharpe on ≥ 5 of 8 OOS years (2019-2026) | — | Regime robustness |
| 6 | **NEW — Monkey test**: entry beats random entry (same exit) by ≥ +$50/trade | +$50 lift | Davey Ch 18 addition |
| 7 | **NEW — Diversification**: daily return R² with v1 < 0.30 | < 0.30 | Davey Ch 15 requirement to justify second product |

**Auto-reject:**
- Negative OOS total P&L → REJECTED
- OOS Sharpe < 0.30 → REJECTED
- Any of gates 1-5 fail → REJECTED
- Gates 6-7 fail → still eligible for shadow (would be v1's shadow-complement, not standalone product)

## Sample split

- **Training (in-sample, seen):** 2010-2018 (~9 years, ~470 weekly bars)
- **OOS (blind):** 2019-2026-07 (~7.5 years, ~390 weekly bars)
- Expected weekly signals: roughly 15-25% fire rate (countertrend fades are rarer than momentum). Expected n_OOS ≈ 60-100 trades.

## No-tune rules

- **DO NOT tune** any of: 4-week lookback, 8-week medium-term lookback, 2×ATR stop, exit-timing rule
- If Seed 2 fails as configured: file rejection. Do not adjust params to save it.
- If Seed 2 passes: ship as `pre_registered_shadow` (26-week forward validation required before public), matching Ensemble discipline.
- Reserve ONE variant retest right (Seed 2b) if a mechanism failure is clearly identified (e.g. sample too small n<30). No parameter tweaking allowed.

## Data source

- Primary: `data/external/dukascopy/XAUUSD_5m.csv` (2015+), `XAUUSD_5m_2010_2014.csv`, `XAUUSD_5m_historical.csv`. Resample to weekly.
- Same infrastructure as `scripts/far_weekly_gold_read.py`.

## Registry entry (to be added on backtest execution)

```json
{
  "trial_id": "far_weekly_gold_seed2_countertrend_fade_v1",
  "family": "weekly_countertrend_fade",
  "status": "pre_registered",
  "hypothesis": "Countertrend fade of 4w extreme with 8w-trend confirmation on gold has positive OOS Sharpe uncorrelated with v1",
  "pre_reg_ref": "docs/experiments/2026-07-29_seed2_countertrend_fade_prereg.md",
  "registered_utc": "2026-07-29T05:55:00Z"
}
```

## Expected outcomes (prior beliefs, NOT tunable)

- P(Sharpe ≥ 0.60 on OOS): ~35%. Countertrend on gold has historically been fragile (2019-2026 was a strong bull → SHORTs on 4w-high extremes likely got run over).
- P(Diversification R² < 0.30 vs v1): ~65%. Different mechanism family should naturally decorrelate.
- Most likely failure mode: SHORT signals get killed by 2019-2026 gold bull rally. Bimodal by year risk.

## Notes on discipline

- No walk-forward optimization at any stage. Fixed params from Davey seed doc.
- If ship gates pass: register as shadow, DO NOT ship publicly. 26-week forward log required.
- If ship gates fail: register as REJECTED with reason, add to `cot_extreme_standalone_rejected.md`-style memory note.
- Compare with buy-and-hold on same OOS window as sanity check (v1 lesson from 2026-07-24).

---

## VERDICT — REJECTED (2026-07-29)

Backtest executed 2026-07-29 as pre-registered. No parameter adjustments.

### In-sample (2010-2018)

| Metric | Value |
|---|---|
| n | 57 |
| Total P&L | +$5,465 |
| Win rate | 54.4% |
| Sharpe (ann) | 0.474 |
| Profit Factor | 1.096 |
| Return/MaxDD | 0.261 |
| Max DD | $20,948 |
| Positive-Sharpe years | 6 of 9 |

In-sample already fails 3 of 5 core gates (Sharpe, PF, R/DD). Only years-positive and n pass.

### Out-of-sample (2019-2026)

| Metric | Value |
|---|---|
| n | 29 |
| Total P&L | **-$8,170** (auto-reject) |
| Win rate | 48.3% |
| Sharpe (ann) | 0.043 |
| Profit Factor | 0.838 |
| Return/MaxDD | -0.381 |
| Max DD | $21,448 |
| Positive-Sharpe years | 3 of 8 |
| Diversification R² vs v1 | **0.0005** (PASS, spectacular) |

### Gate results

| # | Gate | Threshold | OOS | Result |
|---|---|---|---|---|
| 1 | OOS Sharpe (ann) | ≥ 0.60 | 0.043 | ❌ FAIL |
| 2 | OOS Profit Factor | > 1.5 | 0.838 | ❌ FAIL |
| 3 | OOS Return/MaxDD | > 2.0 | -0.381 | ❌ FAIL |
| 4 | OOS n | ≥ 50 | 29 | ❌ FAIL |
| 5 | Positive Sharpe ≥ 5/8 years | — | 3/8 | ❌ FAIL |
| 6 | Monkey test | +$50/trade | not run | — |
| 7 | Diversification R² | < 0.30 | 0.0005 | ✅ PASS |

**Auto-reject triggered:** negative OOS P&L (-$8,170).

### Diagnosis

Prior belief was 35% probability of Sharpe ≥ 0.60. Actual outcome consistent with expectations: countertrend on gold during 2019-2026 got crushed by the sustained bull market. Bimodal by year:
- **Wins:** 2020 (+$12.7k, gold rally exhaustion), 2022 (+$8.3k, hedge fund selloff), 2025 (+$7.2k)
- **Losses:** 2019 (-$6.4k), 2021 (-$1.4k), 2023 (-$4.9k), 2024 (-$3.8k), 2026 (-$20.0k single trade wipeout)

The 2026 single-trade catastrophic loss (-$19,952) reflects gold's break to new all-time highs — the very move the strategy is designed to fade. Same failure mode as the Path Z gold ORB family (`gold_orb_family_dead.md`): countertrend mechanisms cannot survive the modern gold regime.

### Silver lining

The diversification gate (R² = 0.0005) PASSED spectacularly. This confirms: countertrend mechanisms ARE structurally uncorrelated with v1 momentum. If we ever find a countertrend mechanism that clears core gates (unlikely on gold given regime evidence), it would be a genuine second product family.

### No re-tune

Per pre-reg discipline. Not saving Seed 2 with param tweaks. Filing REJECTED. Seed 1 (mean-reversion limit) remains in queue; Seed 3 (time-of-week) is a v3-of-v1 tweak, not a fresh mechanism family — deprioritized.
