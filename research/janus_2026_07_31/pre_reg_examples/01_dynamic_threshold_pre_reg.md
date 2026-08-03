# Dynamic funding threshold — design proposal (Path B)

**Date:** 2026-07-04
**Trigger:** Operator ping after WIFUSDT 3-in-a-row losses on 07-03.
**Related:** `c4e0c87` (Path A auto-cooldown, reactive) —
this proposal is Path B (proactive, root-cause).

---

## Problem statement

`funding_extreme_revert` uses a **flat percentile gate**:

```
current_funding >= p95(rates over ~45 days)
```

The gate is symbol-relative — WIF's p95 is compared against WIF's own
distribution, not the cross-market distribution. That's correct in
principle (per-coin funding varies with structural OI), but it creates
a **degenerate-distribution failure mode**:

> When a coin's funding has been *stably elevated* for weeks, the
> current rate ≈ the p95 of its own history. The "extreme" gate fires
> continuously but there's no actual crowded-positioning signal
> unwinding — the rate is the baseline, not an outlier.

WIF over the 96h window in the investigation: funding = **0.0050%/8h
on every single one of the 15 fires**, and 0.0050% was exactly p95. The
gate wasn't reading extremity, it was reading a flat line.

Same failure mode caught KAS, BNB, UNI over Q2. Each ended up in the
manual `FUNDING_EXTREME_REVERT_SUPPRESS_SYMBOLS` env. That's a reactive
whitelist that grows every time a new symbol hits the pathology — not
scalable.

## Proposed fix

Add a **second gate** that measures the rate against a shorter, faster
baseline. Only fire when the current rate is elevated relative to BOTH
the long-window distribution AND the recent-window central tendency.

### Formal spec

```
FIRE_SHORT iff:
    current_funding > 0
    AND current_funding >= p95(45d_rates)
    AND current_funding >= REL_MULT * median(7d_rates)
```

Where `REL_MULT` is a parameter to be validated on backtest. Starting
proposal: **REL_MULT = 1.5**.

Same logic (mirrored) for the LONG branch when re-validated later.

### Why this fixes WIF

WIF funding was ~0.0050% for the full 96h. Median(7d) would have been
~0.0050% too. `1.5 * 0.0050% = 0.0075%`. Current 0.0050% < 0.0075%, so
the second gate FAILS. No fire.

By contrast a genuine spike — say BTC funding jumps from 0.0020%
median to 0.0080% current — passes both: 0.0080% ≥ 0.0075% (p95) AND
0.0080% ≥ 1.5 × 0.0020% = 0.0030%. Real extremities still fire.

### Why 1.5x median specifically

Rationale, to be validated:
- 1.0x median → identical to "elevated," no filtering effect.
- 2.0x median → probably too strict; kills too many genuine spikes.
- 1.5x median → allows moderate elevation while catching flat-pinned
  distributions. Precedent: 1.5x volume is the standard confirmation
  bar in the grimes_pullback specialist, chosen for similar reasons.

Alternate parameterizations to test:
- **Percentile of 7d** instead of median-multiple: `current >=
  p75(7d)` (catches short-term relative elevation).
- **Absolute delta**: `current - median(7d) >= 0.001%` (dollarized).
- **Ratio of vol**: `current / stdev(45d) >= X` (extremity as sigma).

The median-multiple form is the cleanest first pass — matches the
existing p95 mental model, one added parameter, one added comparison.

## Backtest requirements

Before any code change to the specialist:

1. **Snapshot current DB rows** — `SELECT funding_rate, status,
   realized_r, symbol, created_at FROM setups WHERE source_phase =
   'funding_extreme_revert' ORDER BY created_at`.
2. **For each historical fire**, reconstruct the 7d median funding
   from `funding_snapshots` (schema 019).
3. **Simulate the new gate**: keep the fire only if
   `current >= 1.5 * median(7d)`.
4. **Compute counterfactual**: net-R for the surviving subset vs.
   the full historical set. Compare hit-rate, mean-R, sharpe.
5. **Per-symbol pass-through rate**: what % of WIF / KAS / BNB / UNI
   fires survive? Target: ≤ 20% (i.e. the filter mostly excludes
   the known-drag symbols).
6. **Per-symbol survivor performance**: does the surviving subset on
   those symbols show positive edge, or is it still noise?

## Rollout plan

Pre-registered (same discipline as stop-tightening + regime-direction):

1. **Design doc committed** ← this file
2. **Backtest run** on `scripts/backtest_funding_revert.py` with a
   `--dynamic-threshold` flag simulating the new gate.
3. **Verdict:** SHIP / KILL / PARK based on pre-registered success
   criteria (net-R improvement vs. baseline, ideally with CI95
   excluding zero).
4. **If SHIP:** wire behind `FUNDING_REVERT_DYNAMIC_THRESHOLD_ENABLED`
   env flag, SHADOW phase first (log counterfactual, live emit
   unchanged), promote LIVE after N-week SHADOW + operator review.
5. **On LIVE promotion:** WIF / KAS / BNB / UNI can be removed from
   the manual SUPPRESS env — the dynamic threshold subsumes them.

## Success criteria (pre-registered)

- Net-R over historical `funding_extreme_revert` fires improves by
  ≥ 0.05R/setup after the new gate.
- The 4 currently-SUPPRESS'd symbols see ≥ 80% of their historical
  fires filtered.
- BTC + ETH + majors see ≤ 30% of historical fires filtered
  (evidence that genuine spike detection isn't over-suppressed).
- No test in the existing suite regresses.

## Interactions with Path A (auto-cooldown)

They compose:
- Auto-cooldown is a **reactive** silencer after losses accumulate.
- Dynamic threshold is a **proactive** filter that prevents the
  losing streak from starting.

If B ships and works, the frequency of auto-cooldown activations
should drop to near-zero — which is the intended outcome. Both stay
in place; A is the safety net for whatever B misses.

## Open questions for operator

1. Is `1.5 * median(7d)` the right starting parameterization, or
   prefer one of the alternates (p75(7d), stdev-based, absolute delta)?
2. Backtest window: last 30d? 60d? 90d? (More data = tighter CI but
   older regime; less data = clean recent regime but wider CI.)
3. Should the SHADOW phase be time-bound (2 weeks) or n-bound
   (50 fires per specialist)?

## Estimated effort

- Design (this doc): done.
- Backtest script extension: ~30 min.
- Backtest run + writeup: ~1 hour.
- SHADOW wire-in + env flag: ~30 min.
- Tests: ~30 min.
- **Total to SHADOW-ready:** ~2.5 hours.
- LIVE promotion decision: gated on SHADOW data + operator review.
