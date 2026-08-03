# Follow-up answers

Answers to 4 follow-up questions. Kept tight, no digressions.

---

## 1) Source code

`code/funding_extreme_revert.py` in this drop. 421 lines. Contains:

- Per-symbol funding-rate history maintenance (module state `_history`,
  keyed by symbol, appended per scan; capped at 90d)
- Rolling percentile computation (numpy percentile on the 90d window)
- REL_MULT guard (Path B): `current >= 1.3 * median(21_readings)`
  where 21 readings ≈ 7d at 8h cadence
- Cold-start guard: `n >= 50 historical readings` before first fire
- Env-driven SUPPRESS list, funding-phase BOOST, tier-inversion routing

`should_emit()` is the top-level entry point called by the scanner
loop. Read that first, then trace into the helpers below it.

---

## 2) Pre-registration template — structure + thresholds

Structure of every pre-registration doc we ship:

```
# <topic> — pre-reg <date>

**Author:** <name>
**Trigger:** <what motivated writing this pre-reg NOW>
**Status:** PARKED / IN-SHADOW / LIVE

## Background
<what exists today, what problem this solves>

## Hypothesis
H0: <null — current behavior is optimal>
H1: <alternative — the change improves outcomes on locked metric>

## LOCKED evaluation criteria
Sample: <exact query + cutoff timestamp>
Decision rule (ALL must hold to SHIP):
  1. n >= <floor>
  2. CI95 lower bound >= <threshold R>
  3. Mean R >= <threshold R>
  4. <per-slice constraint — e.g. no single symbol > 40% of edge>

Verdict outcomes:
  - PASS all N: SHIP with env change <exact string>
  - FAIL sample floor: INSUFFICIENT-SAMPLE, revisit trigger <date or n>
  - PASS sample, FAIL edge: PARK. Do NOT re-tune. Reconsider at
    <next major-review calendar trigger>

## Calendar trigger
Whichever first: <date> OR <data condition>

## What NOT to do
- Do NOT expand on current n=<x> read
- Do NOT re-tune <threshold> if data narrowly misses
- Do NOT drop <current behavior> if new one fails

## Kill switch (if shipped)
<env flag flip that reverts>

## Query to run at gate
<exact query text, ready to hand to Atlas or run>
```

Threshold values we use for reference (crypto perp funding_extreme_revert
context — re-tune for gold):

- **Sample floor**: n=30 for capital-scaling gate; n=200 for
  Path-B-style additive-gate expansion; n=50 minimum before ANY
  first fire from a percentile-based specialist
- **CI95 LCB threshold**: +0.15R minimum for a "meaningful edge"
  claim; +0.10R for "cost-model-clears-baseline"
- **Mean R threshold**: same +0.15R for meaningful, +0.10R for
  baseline
- **Bonferroni correction**: divide alpha by number of hypotheses
  tested in the same pre-reg batch (typically 4-6 hypotheses per
  gate → alpha/4 to alpha/6)
- **Max daily loss floor**: -2R
- **SHADOW → LIVE promotion**: n>=15 shadow rows OR 5 trading days,
  whichever first; sign of shadow_mean must match backtest sign;
  shadow_delta must be >= 0.5 × backtest_lcb

See `pre_reg_examples/01_dynamic_threshold_pre_reg.md` for a full
worked example that shows the threshold semantics in context.

---

## 3) Gold-specific

### a) Data source for GOFO / lease rate

I don't have deep knowledge of the gold-data landscape. LBMA
discontinued official daily GOFO publication in January 2015. Since
then, gold lease-rate data has been fragmented. Candidates worth
investigating (from most to least likely free):

1. **LBMA website** — still publishes some lease rate indicators
   at lbma.org.uk under "Prices and Data." Historical depth
   variable. Free but manual scraping likely needed.
2. **World Gold Council** — publishes select rate history in
   research reports. Free.
3. **Kitco / Bullion Vault / Perth Mint** — some published metrics.
   Free but low frequency.
4. **Reuters / Refinitiv / Bloomberg** — paid terminal
   subscriptions. Definitive source; expensive.
5. **Quandl / Nasdaq Data Link** — check for gold-lease datasets;
   some free tiers, deeper history often paid.
6. **CME COMEX ancillary data** — CME publishes some gold-futures
   term-structure data that can be used to infer implied lease
   rates (contango/backwardation → basis → implicit borrowing cost).

Verify data quality before committing. Specifically:
- Update cadence (daily is likely; weekly is too sparse)
- Historical depth (need at least 3-5 years for reliable percentile
  computation)
- Whether the series has published discontinuities (LBMA's 2015
  discontinuation is a real gap)

### b) Have I personally sketched this before?

No. The gold-lease-rate transplant idea originated today in response
to the first message forwarded to me about the funding-based
approach. Before that, this was crypto-only work with no gold
angle considered.

That means:
- Zero prior evidence the transplant works
- Zero prior evidence it fails
- The 3 invariants I called out (per-symbol relative threshold,
  distribution range guard, cold-start floor) come from crypto
  experience but are structurally likely to matter in any market
- Everything else is educated speculation until backtest data
  shows otherwise

### c) What would cause the transplant to fail

In descending order of likelihood, from my perspective:

1. **Cadence mismatch swamping the signal.** Crypto funding pays
   every 8h — extreme readings unwind fast (hours to days). Gold
   lease-rate cycles are much longer (weeks to months). If the
   "unwind" mechanism in gold takes 4 weeks and your time-stop is
   48h, you'll exit before the mean-reversion happens. Fix: much
   longer time-stop (weeks not days).
2. **Distribution too flat.** Gold lease rates historically sat
   near zero for extended periods post-2008. If the p95 is
   essentially zero, the trigger fires on noise not extremes.
   Fix: REL_MULT-equivalent guard.
3. **Insufficient data density.** If the free-feed cadence is
   weekly, 90d = 12 readings. Not enough for a stable p95.
   Fix: multi-year lookback OR find higher-frequency source.
4. **Regime dependence.** Gold macro regime shifts (central bank
   policy, real-rate regime, safe-haven demand) may make
   lease-rate extremes signal different things in different
   regimes. Crypto perps have this less because funding IS
   the crowded-positioning signal directly.
5. **Data source quality.** Free feeds may lag, revise, or
   contain gaps. Percentile-based logic is fragile to revisions.

Least likely (but worth watching):
- **Central bank lease intervention.** Central banks lend gold to
  bullion banks; large lease programs distort the market signal.
  If your data source captures net commercial lease activity
  correctly this is fine; if it captures notional gross including
  official-sector lending, the signal is confounded.

### On the 26-week window Knox mentioned

Knox flagged that our 5-30 day SHADOW is much shorter than the
26-week window Knox had been using. For gold, the 26-week window is
probably closer to right IF gold lease-rate extremes take weeks to
unwind. Our 5-30 day window is calibrated to crypto's hours-to-days
unwind cadence. Adapt the SHADOW window to your unwind cadence, not
ours.

---

## 4) Pitfalls we hit going live

Real incidents from crypto-side production. Sorted by which are
most likely to bite in gold-transplant land.

### High probability of hitting on gold:
- **Slippage understatement.** Our cost model assumed 5bps/side.
  Live entry slippage measured at +9.4bps mean (nearly 2x). Some
  individual fills hit +49bps. Our tail is much fatter than
  Gaussian. Gold futures liquidity is generally better than crypto
  perps but has session-of-day + event-day tail risk.
  Fix: cost-adjusted R alongside frictionless; measure calibration
  post-ship at n≥30; discount edge by measured excess before
  scaling.

- **Backtest / live divergence from cost drag.** Our +0.44R
  backtest edge translated to +0.24R live after cost adjustment.
  ~45% of theoretical edge absorbed by costs. Expect similar
  magnitude on gold or larger for full-round-trip futures.
  Fix: budget for it in sizing math. Do NOT scale on backtest
  numbers alone.

- **Time-stop causing systematic exit before mean-reversion.**
  Above. Bigger risk for gold given longer cycle length.

### Medium probability:
- **Data source going stale silently.** Any feed can lag or fail.
  If your specialist reads stale data, it either fires stale
  signals or stops firing entirely. Both silent failures.
  Fix: heartbeat / staleness alarm on data source. See our
  `pre_reg_examples/` for the pattern.

- **Discretionary override.** Operator saw a fire, second-guessed
  the entry, delayed. Result was either missed edge or entry at
  a worse price. Our fix was explicit: no discretionary override
  in the auto-trader router; every fire routes on the same rule
  or doesn't route at all.

- **Config drift.** Env flags for tuning parameters accidentally
  changed and no one noticed for days. Real drag before caught.
  Fix: safety-flag drift alarm on load-bearing settings; daily
  report shows current config snapshot.

### Lower probability but painful when they hit:
- **Order-placement API bugs on exchange side.** Bitget rejected
  8+ of our first live orders with various errors (precision,
  side semantics, size scale). Every reject was a naked position
  or a missed entry. Real capital cost during activation.
  Fix: canary-mode with tiny size before scaling; explicit
  bug-class taxonomy so alarms distinguish "known-closed" from
  "new failure mode."

- **Silent status-transition failures.** Our order status stayed
  'submitted' after successful fill because a code path didn't
  update it. DB accounting silently diverged from exchange truth
  for weeks before caught. See `pre_reg_examples/` for the
  reconciliation pattern.

- **Legacy data contamination in the sample.** Bug-window trades
  ran to worse-than-fair outcomes; when the bug was fixed, the
  trades stayed in the pre-registered sample. Aggregate mean R
  was materially dragged. We handled by counting them (pre-reg
  discipline: no cherry-picking) but the gate takes longer to
  clear as a result.
  Fix: incident logging so post-hoc you know which sample rows
  came from bug windows and which didn't. Don't act on that
  knowledge; just have it available.

### Simulated vs real execution gap:

Backtest assumes:
- Fills at candle close
- No slippage
- No fee
- No partial fills
- No timing lag between signal generation + order placement

Live has:
- Fills anywhere in the candle depending on order type
- Slippage always (usually adverse; occasionally favorable)
- Fees always
- Partial fills on thin books
- Signal-to-fill latency (ours measured p50=8s, p90=22s at
  scanner cadence; gold futures should be much tighter given
  market maker depth)

The gap between backtest and live edge for us was ~45% (0.44R →
0.24R). This is the RIGHT thing to expect. Don't be surprised;
budget for it.
