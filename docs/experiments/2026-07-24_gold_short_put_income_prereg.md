# Pre-registration: FAR Weekly Gold Short-Put Income v1

**Registered UTC:** 2026-07-24T11:15:00Z
**Owner:** Knox (autonomous under user product-design delegation)
**Trial id:** `far_weekly_gold_short_put_income_v1`
**Predecessor:** none (genuinely different mechanism family — income vs directional)
**Enabled by:** D3 data fetch (GVZ Gold IV 2008-2026, 4732 rows)

## Motivation

FAR Weekly v1/v2 is directional (LONG or SHORT gold). Cross-asset transfer failed 2026-07-24. Contrarian positioning failed. Seasonality failed. Fresh mechanism family needed.

**Options-selling** is a fundamentally different mechanism:
- Return profile: income (premium collection) vs directional (price change)
- Correlation to price momentum: neutral (works in flat/rising regimes)
- Risk shape: capped upside (premium), unlimited downside on assignment (if uncovered)
- Retail-friendly: many gold investors already trade GLD options

**Hypothesis:** Selling short-dated OTM puts on gold generates positive risk-adjusted returns via volatility risk premium (option buyers overpay for insurance). GVZ implied vol > realized vol on average.

## Signal definition (mechanical, no discretion)

- **Instrument proxy:** short 1-week 5-delta put on gold spot (XAU/USD)
- **Pricing:** Black-Scholes with GVZ as implied vol input
  - IV = GVZ / 100 (GVZ is annualized %)
  - T = 5/365 (1 week to expiration)
  - r = 0 (short-dated, minimal impact)
  - K derived from delta -0.05 (deep OTM put)
- **Entry:** Every Monday 13:00 UTC (gold spot open)
- **Exit:** Friday 21:00 UTC (gold spot close). Assess:
  - If gold close ≥ strike → keep full premium, no assignment
  - If gold close < strike → premium minus (strike - close) loss
- **Sizing:** 1 contract = 100 oz nominal exposure (~$5000 assigned value at K=$3000)
- **Cost:** $2 RT (commissions + slippage on options)

## Position management

- No stop loss (assignment risk is baked into the position; capped by structure)
- No early close (accept full assignment or premium)
- Position resets weekly

## Sample split (fixed BEFORE any backtest)

**Honesty note:** Gold price 2010-2026 has been used for FAR Weekly v1 discovery + rejections. GVZ IV data is FRESH (not previously used for any test). Split is designed to leverage GVZ novelty:

- **Training (~432 weeks):** 2010-01-01 to 2018-12-31
- **OOS (~416 weeks):** 2019-01-01 to 2026-06-30
- **Hold-out:** live from 2026-07-24 onward (min 26 weeks before ship)

## Ship gates (all must pass on OOS 2019-2026)

| # | Gate | Threshold | Rationale |
|---|------|-----------|-----------|
| 1 | OOS Sharpe (ann) | ≥ 0.60 | Comparable to v1's 0.767 |
| 2 | OOS win rate | ≥ 75% | Short puts should win most weeks (OTM) |
| 3 | OOS total P&L | > 0 | Absolute profitability |
| 4 | OOS max weekly loss / annualized income | ≤ 3× | Assignment tail must be tolerable |
| 5 | OOS n | ≥ 100 | Statistical power |
| 6 | Left-tail skewness | > -3.0 | Not catastrophically left-tailed |
| 7 | OOS Sharpe > 0 in EACH year | ≥ 5 of 8 years | Regime robustness |

## Reject gates (kill switches)

- OOS Sharpe negative → REJECTED
- Any single week loss > 10× annualized median income → REJECTED (blowup risk)
- OOS assignment rate > 30% (too many losses) → REJECTED

## Implementation caveats (disclosed with product if shipped)

- **Modeled option prices, not real chain data**: Black-Scholes with GVZ IV is an approximation. Real GLD/GC options have skew (OTM puts trade above BSM). Actual premium collected in live trading may be LOWER than backtest suggests (BSM under-prices tail risk premium; short-put earned income likely higher in reality) OR HIGHER (BSM assumes constant vol; realized skew means real 5-delta puts are more expensive).
- **Sensitivity analysis required**: run at delta -0.05, -0.10, -0.15 to check sensitivity to strike selection
- **Assignment mechanics simplified**: real GLD options have physical settlement, tax implications, early exercise possible. Model assumes European-style cash settlement.

## Live effect

**None during backtest.** If ship gates pass:
- Register `far_weekly_gold_short_put_income_v1` verdict `shadow_beta`
- Add dedicated page: `weekly-put-income.html` (parallel to weekly.html)
- Do NOT publish real trade instructions — this is educational (readers execute their own)
- Weekly publish: strike price, expected premium %, risk disclosure
- Distinct from FAR Weekly v1 (different mechanism, different risk profile)

If ship gates fail:
- Register `rejected_ship_gates`
- Publish rejection notes
- Do NOT rescue with delta tuning (that would be curve fit)

## Bonferroni-adjusted DSR

Registry N post-registration: 40 trials. DSR computed with N=40.

## Compliance

- **Pre-registration:** ✅ this doc, before any backtest
- **No parameter tuning:** delta=0.05, T=5d, IV=GVZ, all fixed pre-backtest
- **Sample honesty:** gold price is not virgin OOS but GVZ IV signal is truly new
- **Sensitivity plan:** delta=0.10 and 0.15 runs as informational, not ship gates
- **Ship gates:** 7 explicit thresholds
- **Registry:** entry created before backtest
