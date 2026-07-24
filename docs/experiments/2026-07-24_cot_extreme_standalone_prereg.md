# Pre-registration: FAR Weekly Gold COT Extreme Read v1

**Registered UTC:** 2026-07-24T09:40:00Z
**Owner:** Knox (autonomous under user product-design delegation)
**Trial id:** `far_weekly_gold_cot_extreme_v1`
**Predecessor:** none (different mechanism family from FAR Weekly v1)
**Related:** COT filter test 2026-07-22 (rejected as v1 filter; commit 7edee7d)

## Motivation

FAR Weekly v1/v2 (momentum + macro) is one mechanism family — shipped BETA.
Cross-asset transfer failed (BTC v1, WTI v1 both rejected 2026-07-24).
Need genuinely different mechanism on gold: **contrarian mean-reversion
on speculator positioning extremes.**

CFTC Commitments of Traders (COT) reports show non-commercial (speculator)
net long/short positions weekly. Extreme positioning is historically a
mean-reversion signal — when speculators are heavily long, price often
tops; when heavily short, price often bottoms.

Fresh mechanism (NOT momentum, NOT macro): pure positioning-based
contrarian signal. Uses COT data alone; ignores price momentum entirely.

**Hypothesis:** When non-commercial net position z-score (52-week rolling)
exceeds ±2σ, the next-week gold return is significantly biased against
the extreme (mean reversion).

## Signal definition (from theory, pre-registered)

- **Data:** `data/macro/cot_gold_simplified.csv` (COMEX gold code 088691,
  Tuesday snapshot published Friday)
- **nc_z:** 52-week rolling z-score of `nc_net` (non-commercial net position)
- **Direction:**
  - SHORT gold if nc_z > +2 (specs crowded long, mean-revert down)
  - LONG gold if nc_z < -2 (specs crowded short, mean-revert up)
  - FLAT otherwise
- **Timing:** COT release Friday → signal computed Sunday → entry Monday
  open → exit Friday close (identical timing to FAR Weekly v1)

## Position management (identical to v1)

- Entry: Monday 13:00 UTC open (gold spot)
- Stop: 2 × ATR(20 daily)
- Target: Friday 21:00 UTC close
- Sizing: 1 GC contract (100 oz)
- Cost: $5 RT

## Sample split (fixed BEFORE any backtest)

**Honesty note:** Gold price 2010-2023 has been used extensively for
FAR Weekly v1 discovery, v2 shadow, COT filter test. This is not virgin
OOS data. However, this specific rule (contrarian standalone on COT
z-score) has not been tested.

- **Training (~468 weeks):** 2010-01-05 to 2018-12-31
- **In-sample-only test (~260 weeks):** 2019-01-01 to 2023-12-31
- **True forward validation:** starts 2026-07-24 if ship gates pass;
  requires 26 weeks minimum before any ship decision

## Ship gates (all must pass on full 2010-2023 sample AND on 2019-2023 tail)

Because true OOS is unavailable, gates are dual-window:

| # | Gate | Threshold | Rationale |
|---|------|-----------|-----------|
| 1 | Sharpe (ann) full sample | ≥ 0.60 | Comparable to v1's 0.767 |
| 2 | Sharpe 2019-2023 tail | ≥ 0.40 | Lower bar for smaller sample |
| 3 | Win rate full sample | ≥ 55% | Signal has directional edge |
| 4 | PSR vs SR=0 (full) | ≥ 0.90 | Statistical significance |
| 5 | Total P&L full sample | > 0 | Absolute profitability |
| 6 | Trade count (full) | ≥ 30 | z > ±2 is rare; need power |
| 7 | Trade count (tail) | ≥ 10 | Tail-window minimum |

## Reject gates (kill switches)

- Sharpe negative in EITHER window → REJECTED
- Both training + tail windows negative P&L → REJECTED
- n < 20 in full sample (over-restrictive) → REJECTED

## Live effect

**None during backtest.** If ship gates pass:
- Register `far_weekly_gold_cot_extreme_v1` verdict `shadow_beta`
- Add COT Extreme card to weekly.html (parallel to FAR Weekly cards)
- Fetch 2024-2026 COT data for live signal computation
- Public disclosure includes: this pre-reg, backtest metrics, "in-sample-only
  disclosure" (no true OOS gold data available)

If ship gates fail:
- Register `rejected_ship_gates`
- Add rejection memory
- No further COT-standalone work until fresh theory

## Bonferroni-adjusted DSR

Registry N post-registration: 38 trials. DSR computed with N=38 for
familywise-error correction.

## Compliance

- **Pre-registration:** ✅ this doc, before backtest
- **No parameter tuning:** z-threshold=2, rolling=52 weeks (standard),
  stop=2×ATR (inherited from v1)
- **Sample honesty:** explicit note that gold 2010-2023 is not virgin OOS
- **Ship gates:** 7 explicit thresholds, dual-window
- **Registry:** entry created before backtest
