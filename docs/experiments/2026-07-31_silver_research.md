# Silver signal research

**Date:** 2026-07-31
**Author:** Knox
**Status:** RESEARCH / DESIGN. No backtests run yet.
**Related:** `soft_launch_decisions.md`, `research/janus_2026_07_31/INDEX.md`

---

## Why silver

User agreed to widen the tradable universe beyond gold. Silver is the first asset because:
- We already have 5m Dukascopy data 2010-2026
- Structurally adjacent to gold (both are precious metals)
- BUT different enough that lessons from gold don't naively transfer (higher volatility, industrial demand component, distinct positioning dynamics)

Copper is deferred to a later phase per user directive.

## Silver's characteristics (things gold doesn't have)

**Volatility profile:** silver's daily volatility is historically 1.8-2.2x gold's. What looks like a normal 1% move in gold is a 2% move in silver. Position sizing must respect this.

**Dual-demand structure:** silver is roughly 55% industrial demand (electronics, photovoltaics, medical) and 45% investment demand. Gold is >95% investment. This means silver responds to industrial cycles (PMI, semiconductor cycle, solar installations) in a way gold doesn't.

**Positioning:** silver is retail-heavy vs gold's central-bank-heavy structure. COT data shows different commercial-vs-speculator dynamics. Extreme readings in silver mean different things than in gold.

**Volatility clustering:** silver has more pronounced regime switching than gold. Long quiet periods punctuated by violent moves (e.g. Jan 2021 short squeeze).

## The naive-transfer trap

We already ran this experiment in July and it failed. Cross-asset transfer of NORTH v1's gold-tuned rules to BTC and WTI was rejected on OOS data. See registry entries and `docs/development_story.md`.

The lesson: apply gold's SPECIFIC parameter values to silver, expect them to fail. What might transfer is the STRUCTURE (momentum + macro filter), but weights, timeframes, and macro inputs need silver-native design.

## 3 candidate signal families for silver

Design 3 distinct mechanism families. Backtest each. Ship the winner if any clears 0.5% per trade.

### Candidate 1: Silver-native momentum plus industrial macro

Structural analog of NORTH v1 but tuned for silver's dual-demand nature.

**Conditions (to be finalized during design):**
- 4-week momentum on silver (M20 > 0 for LONG)
- 12-week momentum on silver (M60 > 0 for LONG)
- MA cross on silver, likely 10/40 daily like v1
- Instead of real yields (gold-specific driver), use an INDUSTRIAL macro filter: e.g. 20-day change in copper/silver ratio, or 20-day change in US ISM Manufacturing PMI, or 20-day change in oil prices
- OR keep real yields as one of two macro filters and add industrial as a second

**Why this could work:** silver's investment-demand component responds to similar macro forces as gold. The industrial-demand component adds a different signal that gold doesn't have.

**Why this could fail:** industrial macro data updates are much less frequent than daily prices. Signal might be too slow. Or industrial and monetary components move in opposite directions, canceling out.

**Data needed:** silver Dukascopy 5m (have it), plus one industrial macro series (copper, oil, PMI, or all three).

### Candidate 2: Gold-silver ratio z-score extreme reversion

Cross-asset relative-value signal. When the gold-silver ratio hits extremes, mean-reverts.

**Rules:**
- Compute gold price / silver price on daily bars
- Compute rolling z-score over lookback (candidate lookbacks: 60d, 90d, 180d)
- When z-score > +2 (silver way too cheap relative to gold): LONG silver
- When z-score < -2 (silver way too expensive relative to gold): SHORT silver
- Exit at z-score cross of zero (mean reversion complete) OR fixed time exit (candidate: 3 weeks)

**Why this could work:** gold-silver ratio has historical bounds (roughly 30 to 100). Extreme readings are historically associated with silver mean-reversion. This is a documented pattern in precious-metals literature.

**Why this could fail:** the ratio can stay extreme for months. Historical extremes reset during regime shifts (e.g. 2020 COVID). Mean reversion might be too slow relative to any tolerable time exit.

**Data needed:** gold Dukascopy (have it), silver Dukascopy (have it).

**Direct connection to Janus's approach:** this uses the extreme-reversion structural pattern. Not identical (Janus uses funding rates on crypto perps, not asset-price ratios) but same "fade the extreme" thesis. Their invariants (per-symbol relative thresholds, distribution-range guard, cold-start floor) apply here too.

### Candidate 3: Silver volatility regime signal

Silver has distinct volatility regimes. Historical data suggests different edge exists in each.

**Rules:**
- Compute silver realized volatility on rolling 20-day window (annualized)
- Classify regime: LOW (realized vol < 25%), MEDIUM (25-40%), HIGH (>40%)
- In LOW-vol regime: mean-reversion strategies work better
- In HIGH-vol regime: momentum-continuation strategies work better
- Signal fires based on regime + short-term price behavior:
  - LOW regime, price above 20-day mean: SHORT (mean reversion)
  - HIGH regime, price crossing above 10-day mean: LONG (breakout)
  - Everything else: FLAT

**Why this could work:** silver's regime-switching is well documented. Adapting mechanism to regime is a known technique that has some literature support (Kaufman Ch 17 discusses adaptive strategies, though we've been careful about that book).

**Why this could fail:** three-regime classification is a lot of parameters (thresholds, timeframes, direction rules per regime). Real risk of curve-fitting. Simpler variants like "low-vol mean-reversion only, ignore high-vol" may generalize better.

**Data needed:** silver Dukascopy (have it) only. No external macro.

## Which one to prioritize

Candidate 2 (gold-silver ratio reversion) is the easiest to design and test. No external data, clean rule, historically documented pattern. Should be first backtest.

Candidate 1 (silver-native momentum) is second because it requires deciding which industrial macro input to use, adding a design step.

Candidate 3 (regime signal) is third because it has the most parameters and highest curve-fit risk. Worth testing but with skepticism.

## Ship trigger (per user directive)

Same as gold NORTH: 0.5% mean R per trade minimum.

Additional realistic considerations:
- Silver's higher volatility means the same percentage move produces larger dollar swings. Position sizing must respect this.
- Silver's mean R must survive cost-adjustment. Silver futures (SI) have thinner books than gold futures (GC). Slippage defaults for silver in `cost_model.py` are more conservative (0.0005 vs gold's 0.0002).

## Backtest process (using shared tools)

For each of the 3 candidates:
1. Implement the signal function
2. Run backtest on 2010-2026 silver Dukascopy data
3. Compute per-trade returns
4. Apply cost model with silver-appropriate defaults
5. Evaluate with `bootstrap_stats.evaluate_signal(..., n_hypotheses_in_batch=3, ci_lower_threshold=0.005)` (n=3 because we're testing 3 candidates)
6. Kill anything with verdict "negative" or "indist"
7. Rank surviving candidates by mean R, per-year robustness, drawdown

## Files to build

- `scripts/silver_candidate_gsr_ratio.py` - candidate 2 (highest priority)
- `scripts/silver_candidate_native_momentum.py` - candidate 1
- `scripts/silver_candidate_vol_regime.py` - candidate 3
- `scripts/silver_backtest_compare.py` - side-by-side comparison of all 3

## Not building yet

- Publisher for any silver signal (waits on backtest results)
- Site pages for silver (waits on ship decision)
- Silver-specific data pipeline (Dukascopy already has what we need)

## Explicit fallbacks

- If all 3 candidates fail 0.5%: publish honest research summary, retire silver-native signal effort, discuss next asset (options include copper, GDX/GDXJ, DXY, platinum, or a new gold-only mechanism family) with user.
- If one candidate passes: ship as a versioned FAR product. Naming and channels decided at that point.
- If more than one passes: ship the strongest as the primary, keep the second in reserve as a potential filter or diversification signal for later.
