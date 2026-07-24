# Pre-registration: FAR Weekly Gold Put-Spread Income v1

**Registered UTC:** 2026-07-24T13:00:00Z
**Owner:** Knox (autonomous under user product-design delegation)
**Trial id:** `far_weekly_gold_put_spread_income_v1`
**Predecessor:** `far_weekly_gold_short_put_income_v1` (rejected 2026-07-24 12:00Z)

## Motivation

Naked short-put v1 was rejected today with catastrophic left-tail (skew -6 to -8, max weekly loss $22-31k across delta variants). The problem was unbounded tail risk when gold gaps below the short strike. A **bull put spread** (short OTM put + long further-OTM put) caps the maximum loss to (strike diff × 100 oz) minus net premium collected.

**Hypothesis:** A short 5-delta put + long 2-delta put spread on gold weekly:
- Reduces premium collected (long leg costs some of the short leg's premium)
- BUT caps maximum weekly loss to a bounded amount
- Should have less-negative skew than naked puts
- Might survive the same ship gates that killed naked puts

This is a fresh mechanism (defined-risk options) with a specific hypothesis (cap the tail).

## Signal definition

Every Monday 13:00 UTC:
- SHORT 1-week put with target delta = -0.05, priced BSM with GVZ as IV
- LONG 1-week put with target delta = -0.02, priced BSM with GVZ as IV
- Net premium = short_premium - long_premium (net credit)
- Position: 1 contract each leg (100 oz)

Friday 21:00 UTC exit:
- If gold close ≥ short strike: keep full net premium (best case)
- If long_strike < gold close < short strike: net premium − (short_strike − close) (partial assignment)
- If gold close ≤ long strike: net premium − (short_strike − long_strike) (max loss, capped)

## Ship gates (all must pass on OOS 2019-2026)

| # | Gate | Threshold | Rationale |
|---|------|-----------|-----------|
| 1 | OOS Sharpe (ann) | ≥ 0.60 | Match FAR Weekly v1 |
| 2 | OOS win rate | ≥ 75% | OTM structure, most weeks credit |
| 3 | OOS total P&L | > 0 | Profitability |
| 4 | max weekly loss / ann median income | ≤ 3× | Meaningful cap improvement over naked put |
| 5 | OOS n | ≥ 100 | Statistical power |
| 6 | Skewness | > -3.0 | The whole point: fix the tail |
| 7 | Positive-Sharpe years | ≥ 5 of 8 | Regime robustness |

## Reject gates (kill switches)

- OOS Sharpe negative → REJECTED
- Skewness < -4 → REJECTED (the tail wasn't fixed)
- Max weekly loss > 8× ann median income → REJECTED (cap didn't help)

## Position management

- Entry: Monday 13:00 UTC open, both legs simultaneously
- Exit: Friday 21:00 UTC close, both legs simultaneously
- No management, no adjustments
- Cost: $4 RT (double the naked put — 2 option legs, but same $2 per RT)

## Sample split (fixed BEFORE any backtest)

- **Training:** 2010-2018 (~450 weeks)
- **OOS:** 2019-2026 (~380 weeks)

Note: gold price + GVZ data already extensively used, but this specific
structure (5×2 put spread) has never been tested.

## Live effect

**None during backtest.** If ship gates pass:
- Register as `shadow_beta`
- Add put-spread card to weekly.html
- Educational disclosure with real assignment mechanics discussion

If rejected:
- Register `rejected_ship_gates`
- Options mechanism family definitively closed for gold weekly

## Compliance

- Pre-registration: ✅ this doc, before backtest
- No parameter tuning: deltas 0.05/0.02 fixed
- Ship gates: 7 explicit, kill switches: 3
- Registry: entry created before backtest
