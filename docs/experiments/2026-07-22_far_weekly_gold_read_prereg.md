# Pre-registration: FAR Weekly Gold Read

**Registered UTC:** 2026-07-22T11:00:00Z
**Owner:** Knox (autonomous product design under user delegation 2026-07-22 chat)
**Trial id:** `far_weekly_gold_read_v1`
**Product name:** FAR Weekly Gold Read
**Timeframe:** weekly (Monday open → Friday close)

## Motivation

Session 2026-07-22 established via 12-year OOS testing that classical intraday ORB
mechanisms (Path Y, Path Z, Meyers HR, Crabel, gap-fade, event-conditioned) do NOT
carry persistent edges on gold. See `memory/gold_orb_family_dead.md`,
`memory/path_z_oos_result.md`, and `memory/alternative_mechanisms_result.md`.

Weekly momentum on gold, particularly combined with macro conditioning
(real yields, DXY), has a well-documented long-term academic literature (see
Asness/Moskowitz/Pedersen 2013 "Value and Momentum Everywhere"). This pre-reg
tests whether that established literature reproduces on a modern, defensible
gold intraday dataset with disciplined pre-registration.

User has delegated full product-design authority for this candidate. Result
will be published as recurring weekly calls on the FAR website.

## Hypothesis

Weekly gold direction (LONG / SHORT / FLAT) can be predicted from a combination
of price momentum + macro conditioning strong enough to produce a
positive-Sharpe systematic strategy after realistic costs on GC futures or GLD.

**H0 (null):** Weekly gold direction is unpredictable from momentum + macro
signals; strategy weekly returns have mean = 0.
**H1 (alt):** Combined momentum + macro filter produces positive-Sharpe
strategy on OOS, holds up under hold-out test.

## Signal definition (fixed pre-reg, no post-hoc tuning)

All computed on **daily closes** from XAU/USD spot (Dukascopy).

**Momentum:**
- M20 = (Close_t − Close_{t−20}) / Close_{t−20}   [4-week momentum]
- M60 = (Close_t − Close_{t−60}) / Close_{t−60}   [12-week momentum]
- MA10 = 10-day SMA of Close
- MA40 = 40-day SMA of Close

**Macro conditioning:**
- RY_chg = 10y Real Yield − 10y Real Yield lag-20   [4-week real yield change]
  Source: `data/macro/real_yield_10y__DFII10.csv` (FRED DFII10)
- DXY_chg = DXY − DXY lag-20   [4-week DXY change]
  Source: `data/macro/dxy_proxy__DTWEXBGS.csv` (FRED DTWEXBGS)

## Entry rules (fixed)

Evaluated at Friday close of week N to determine week N+1 direction:

**LONG** iff ALL:
- M20 > 0 AND M60 > 0
- MA10 > MA40
- RY_chg < 0 (real yields falling supports gold)

**SHORT** iff ALL:
- M20 < 0 AND M60 < 0
- MA10 < MA40
- RY_chg > 0 (real yields rising)

**FLAT** otherwise (majority of weeks expected to be FLAT — this is intentional; concentrated signal).

DXY_chg is computed but NOT used in the entry gate. Reserved as diagnostic for
possible v2. Committing to only-RY_chg as macro filter prevents kitchen-sinking.

## Position management (fixed)

- **Entry:** Monday 13:00 UTC open (NY session open, closest realistic execution time)
- **Stop:** 2 × ATR(20 daily) from entry
- **Target:** Friday 21:00 UTC close (time exit — 5 trading days)
- **Sizing:** 1 contract fixed (100 oz GC or GC-equivalent)
- **No intraweek adjustments** — mechanical hold

## Cost model (pre-reg for realism)

- **Instrument for backtest:** XAU/USD spot (Dukascopy)
- **Cost model reflects live execution:** GC futures on IBKR
  - Commission: $1.70 round-trip
  - Spread + slippage: $1-3 round-trip (1-2 ticks × $1/tick)
  - **Total RT cost: $5 per trade** (conservative for GC micro or full GC)
- On per-oz basis: $0.05/oz round-trip
- Contract multiplier: 100 oz per contract

## Sample split (fixed BEFORE any backtest)

- **TRAINING:** 2015-01-01 to 2020-12-31 (6 years) — used for design confirmation
- **OOS validation:** 2021-01-01 to 2023-12-31 (3 years) — used to check generalization
- **HOLD-OUT:** 2024-01-01 to 2026-07-20 (2.6 years) — NEVER touched until pre-reg is finalized post-OOS

The 12-year Dukascopy XAUUSD data was fetched today with the intention of
using it for this candidate. No look-ahead on hold-out is possible because
Path Z discovery happened before the hold-out data was consulted for this design.

## Ship gates (ALL required)

1. **Training Sharpe (annualized) ≥ 0.5** on 2015-2020 sample after costs
2. **OOS mean weekly return > 0** on 2021-2023 sample after costs
3. **OOS win rate ≥ 50%** on non-FLAT weeks
4. **Combined 2015-2023 bootstrap 95% CI on mean weekly return clears zero**
5. **Hold-out 2024-2026 mean weekly return > 0** (final gate)
6. **Bonferroni-adjusted N=33 (registry+1)** PSR > 0.95 on combined sample after costs

## Reject gates (any triggers REJECT)

- Training Sharpe < 0.3: retire before OOS
- OOS mean return ≤ 0: retire before hold-out
- OOS win rate < 45% (below coin flip): retire
- Hold-out mean return ≤ 0: retire even if training + OOS passed
- More than 10 FLAT-year outcomes in the combined sample (strategy too rare
  to be a viable weekly product): retire — need at least 3 non-FLAT signals/year
- Cumulative drawdown > 30% at any point in walk-forward: retire

## Compliance with framework

- **Pre-registration:** ✅ this doc (before any backtest)
- **Fixed parameters:** M20, M60, MA10, MA40, ATR20, RY_chg thresholds all fixed
- **No post-hoc parameter tuning:** if training fails, retire — do NOT re-parameterize
- **Bonferroni-N:** registry increments; DSR/PSR computed on combined sample
- **Sample split committed:** no data leak from hold-out during pre-reg design
- **Cost model realistic:** GC futures IBKR pricing

## Files that will be produced

- `scripts/far_weekly_gold_read.py` — backtest engine
- `scripts/far_weekly_gold_read_walkforward.py` — training + OOS + hold-out runner
- `data/experiments/registry.json` — `far_weekly_gold_read_v1` entry
- Live trigger (post-ship): systemd timer on VPS, Sunday evening publish

## Product design (post-ship)

- **Publish cadence:** Sunday 22:00 UTC (before Monday open)
- **Publish channel:** FAR website page dedicated to Knox (per user directive)
- **Content:** direction (LONG/SHORT/FLAT), entry price, stop price, expected exit price + timeframe
- **Track record:** every published call resolved by Friday close; accumulates on page
- **Format:** simple executable format for retail (GC futures or GLD ETF)

## Overall confidence at pre-reg time

Prior confidence based on academic literature + our own null findings on
intraday: **40-50%** this strategy will pass all gates. Weekly momentum
strategies on gold have decades of documented backing, but modern algo era
may have eroded the edge (as happened with intraday ORB).

If training fails, retire this specific parameterization. Any redesign requires
fresh pre-reg with different filter combination.
