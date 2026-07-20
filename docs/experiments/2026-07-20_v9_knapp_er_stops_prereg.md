# v9 candidate: Knapp asymmetric ER-based stops — pre-registration DRAFT

**Draft written UTC:** 2026-07-20T14:45:00Z
**Status:** `pre_registered_draft` — filter code + tests + registry entry present, `require_er_adaptive_stop=False` in all live configs. NO live effect until user reviews + explicitly promotes to `pre_registered` verdict.
**Trial id (proposed):** `knapp_er_stops_v9`
**Owner:** Farhad (post-review)
**Layer:** `strategy_engine` (stop management, not entry filter)

## Motivation

Path Y is formally closed (see `docs/experiments/2026-07-20_path_y_postmortem.md`). Adding filters to Path Y produced negative-lift `daily_slope_consistency` (rejected 2026-07-20 at n=329). The remaining v9 direction per Kaufman Ch 17 read notes is **structural** change: different STOP management, or different ENTRY-range framing.

This pre-reg proposes the STOP-management change (Volker Knapp, Active Trader Sep 2010, Kaufman 5th Ed. p.792). A parallel candidate (Meyers asymmetric ORB range) exists but is deferred pending this one's outcome.

**Direct fit for observed failure mode:** post-halt review of n=18 launch-era live trades (2026-07-01 → 2026-07-17) showed all 6 LONG losses were stop-hits (per `2026-07-13_regime_diagnosis.md`), 3 of them on days where GC closed UP 1.0-1.6% intraday. Symmetric fixed stops in a directional-but-noisy tape produced systematic whipsaw. Knapp's asymmetric-ER-based stop tightens LONG stops LESS than SHORT stops in trending ER regimes, which by construction targets this failure mode.

## Hypothesis

For a trade taken by any session's ORB entry rule, replacing the fixed stop (`stop_atr` × ATR) with a Knapp-style ER-adaptive stop reduces stop-hit frequency on LONG trades in trending regimes without materially increasing max-adverse-excursion on losing trades.

**H0** (null): Mean per-trade P&L under Knapp stops = mean per-trade P&L under fixed stops (paired on same entry).
**H1** (alt): Mean per-trade P&L under Knapp stops > mean per-trade P&L under fixed stops (paired), by at least $50/trade on gold.

The $50/trade threshold is not arbitrary — it's derived from `research material/Kaufman 5th Ed` Table 17.4 which reports Knapp's own study lift of +7-15% on 8 markets; scaling to Path Y-like $-16.70/trade base is +$1-3/trade lift, which is below noise floor. We require at least an order of magnitude above the historical study lift to declare edge on gold (per gold-caution flag from Table 17.1: KAMA PF 0.86 on gold vs 1.53 avg).

## Filter specification (skeleton, not enabled)

```python
# strategy_engine.filter_knapp_er_adaptive_stop
def filter_knapp_er_adaptive_stop(cfg, ctx, regime):
    """MODIFIES stop_price at entry time based on ER.

    Does NOT skip trades. Does NOT change entry price or target price.
    Only affects the stop_price field of the returned Decision.
    """
    if not cfg.require_er_adaptive_stop:  # no-op until flag flipped
        return None  # signals "no modification"
    er = regime.efficiency_ratio_20  # to be added to RegimeContext
    if er is None:
        return None  # no data; fall back to fixed stop
    base_stop_dist = 6.0 * ctx.atr_at_close  # Knapp starts at 6×ATR
    direction = ctx.direction  # LONG or SHORT
    if er < 0.30:
        reduction = 0.0
    elif er < 0.60:
        reduction = 0.1 if direction == "LONG" else 0.5  # asymmetric
    else:
        reduction = 0.2 if direction == "LONG" else 0.1  # asymmetric
    return {"stop_dist_atr": base_stop_dist - reduction * ctx.atr_at_close}
```

**Feature computation** (new — will live in `src/regime_context.py`):
```python
def _efficiency_ratio(closes: pd.Series, n: int = 20) -> float | None:
    """ER = |p_t - p_{t-n}| / sum(|Δp|_1 ... |Δp|_n).
    Returns None if fewer than n+1 closes available."""
```

Applies to **5m bars** matching entry timeframe. Uses close-to-close on 20-bar window (100 minutes). Range [0, 1].

**Where it hooks:** `edge_session_orb_v7_final.py` `evaluate_session` returns a Decision with `stop_price`. If `require_er_adaptive_stop=True`, `stop_price` is recomputed via this filter *after* entry direction is determined.

## In-sample effect size (informational, DO NOT rely on)

To be computed via `scripts/backfill_knapp_er_stops.py` (to be written; not implemented in this draft):
- Run on same n=329 XAU/USD shadow sample used to reject dsc
- Paired-trades: for each entry, simulate outcome under both fixed and Knapp stops
- Report lift, precision-on-preserved-LONGs, and CI

This computation is NOT part of ship-gate. Ship-gate requires shadow forward n≥100 on new live/shadow accumulation (see below).

## OOS evidence bar (must show BEFORE promoting from draft → pre_registered)

Per `memory/quant_framework_gold.md` and Bonferroni-N discipline (registry now at ~24 trials):

1. **3-months-ago test:** ER was published in Chande/Kaufman by 1995; Knapp study 2010. This candidate WAS derivable 3+ years ago. ✅ PASSES
2. **20-year OOS on gold:** Kaufman Table 17.1 gives KAMA PF 0.86 on gold. That's the null hypothesis for gold-hostility. Must show that Knapp-stops does NOT inherit KAMA's gold failure. Test method: run Knapp-stops post-hoc on synthetic ORB entries from 60m GC bars 2000-2024 (n≥5,000 potential entries), measure paired-lift vs fixed 6×ATR stops.
3. **Cross-market sanity:** Kaufman's Active Trader article claims 8-market panel lift +7-15%. Reproduce on any 3 markets from that panel using free data (Dukascopy has EURUSD, EURJPY, etc.). Not required to match magnitude, but must show sign consistency.
4. **Independence from dsc:** stop management is orthogonal to entry direction filtering. The rejected dsc filter operated on ENTRY (would_take); this operates on STOP. Both can co-exist; neither disqualifies the other. But: if v10 revisits ER-based entry filtering, Bonferroni-N of ER-family will need to be counted separately.

Only after #1-#3 pass does this graduate from `pre_registered_draft` → `pre_registered`.

## Ship gates (ALL required, at n≥100 live+shadow decisions on Knapp stops)

1. **n ≥ 100 shadow decisions** — same threshold as dsc, same pre-reg discipline
2. **Mean paired lift ≥ +$50/trade** (this must clear the noise floor; +$50 is 3× the -$16.70 unfiltered base)
3. **Bootstrap 95% CI on paired lift clears zero** (2000 draws, alpha=0.05)
4. **No degradation in per-session precision** — LON, NY, ASIA precision-on-losers must each stay within ±5pp of Path Y baseline
5. **DSR audit passes** — Deflated Sharpe > 0.95 given growing Bonferroni-N. As of 2026-07-20 registry N ≈ 24 rejected + 3 shipped; V[SR_n] with LdP default 0.5. This will be recomputed at ship time.
6. **New Knapp-specific SPRT pre-reg** — cannot inherit `sprt_v72_1_launch_path_y` because that pre-reg was about Path Y's entry rule, not its stop management. Requires fresh pre-reg BEFORE first live trade.

## Rejection gates (any triggers REJECT)

- Mean paired lift < 0 at n=100 → REJECT
- CI includes zero at n=100 AND lift < +$25 → REJECT (below insufficient-signal threshold)
- Any per-session precision drops >5pp vs Path Y baseline → REJECT (regime confound)
- Bonferroni-adjusted DSR < 0.90 at n=100 → REJECT
- Not cleared by 2026-10-13 (aligned with Path C hard-stop in `sprt_v72_1_reentry_prereg`) → REJECT
- Reproduction study (§ OOS #3) shows sign inversion on ≥2 of 3 test markets → REJECT

## Compliance with quant framework

- **Pre-registration:** ✅ this doc (draft; needs review to activate)
- **Bonferroni-N:** ✅ registry entry `knapp_er_stops_v9` will increment; also increments if reproduction study on 3 non-gold markets is registered
- **OOS on pre-registered data:** ❌ pending — see § OOS evidence bar #2, #3
- **3-months-ago test:** ✅ ER/Knapp published pre-2015; WGC canonical vars unaffected
- **20-year OOS test on the underlying regime signal:** ❌ pending — see § OOS evidence bar #2

## Interaction with Engine A halt and Path A/B/C

- **Does NOT flip Engine A kill switch off.** Kill switch remains ON per `sprt_v72_1_launch_path_y` halt.
- **This IS Path C.** `sprt_v72_1_reentry_prereg` Path C: "v7.3+ passes DSR AND new SPRT pre-reg." Knapp-stops IS the "v7.3+" candidate. If this candidate ships (all gates pass), it triggers Path C re-entry with the Knapp variant as the active strategy — NOT Path Y with a Knapp stop tacked on. The distinction matters: Knapp-stops replaces one degree of freedom (stop_price computation) so it can inherit Path Y's entry logic, but the *combined system* is treated as a new strategy for gate purposes.
- **First-live-trade size = 50%** of nominal (matches Path B ramp discipline). Full size only after Knapp-specific SPRT clears SAFE boundary.

## Files that will change on activation (NOT yet)

- `src/regime_context.py` — add `_efficiency_ratio(closes, n)` + wire into `build_regime_context`; add `efficiency_ratio_20` field to `RegimeContext` dataclass
- `src/strategy_engine.py` — add `filter_knapp_er_adaptive_stop`, add `require_er_adaptive_stop=False` field to `SessionConfig`, register in `REGISTERED_FILTERS`
- `src/edge_session_orb_v7_final.py` — modify `evaluate_session` so stop_price is post-processed by filter when flag=True
- `tests/test_strategy_engine.py` — new `TestFilterKnappErAdaptiveStop` class with 6+ test cases (ER regimes × LONG/SHORT × edge conditions)
- `scripts/backfill_knapp_er_stops.py` — NEW; paired-outcome simulator for shadow log
- `data/experiments/registry.json` — new entry `knapp_er_stops_v9` verdict `pre_registered_draft`

## What activation requires (checklist for user)

Before this pre-reg graduates from `_draft` to active `pre_registered`:

- [ ] User reviews this doc + confirms hypothesis + gates are reasonable
- [ ] User authorizes writing the filter code (marked above under § Files)
- [ ] Reproduction study on 3 non-gold markets passes (§ OOS #3)
- [ ] Gold 20-year OOS on 60m data passes (§ OOS #2)
- [ ] Bonferroni-N recomputed at time of pre-reg
- [ ] Registry entry updated from `pre_registered_draft` → `pre_registered`
- [ ] Knapp-specific SPRT pre-reg written (§ Ship gate #6)

## Immediate action

**None.** This draft is a placeholder. No code changes yet. No live effect. When user says "activate", the checklist above runs.

## References

- Kaufman, P. J. (2013). *Trading Systems and Methods*, 5th Ed. Wiley. Ch 17 (Adaptive Techniques), pp. 779-810. Specifically Knapp p.792, Table 17.1 p.787.
- Knapp, V. (2010, Sep). *Active Trader Magazine*, "The Efficiency Ratio and Position Sizing".
- `memory/kaufman_ch17_readnotes.md` — extracted candidate summary
- `docs/experiments/2026-07-20_path_y_postmortem.md` — motivation for structural v9 change
- `docs/experiments/2026-07-18_daily_slope_consistency_shadow.md` — rejected filter candidate that ruled out entry-side dsc solutions
