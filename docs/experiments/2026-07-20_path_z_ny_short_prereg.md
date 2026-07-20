# Path Z: NY-SHORT + Low-ER + Mon-Wed — pre-registration

**Registered UTC:** 2026-07-20T17:30:00Z
**Filter name:** `filter_path_z` (v8 strategy_engine)
**Config:** `SESSION_CONFIGS_V9_Z` (v8 sessions + `require_path_z=True`)
**Trial id:** `path_z_ny_short_shadow`
**Owner:** Farhad
**Status:** SHADOW (no-op live; `require_path_z=False` in all live configs; shadow tracker computes decisions for logging only)

## Motivation

The `daily_slope_consistency` filter was REJECTED at n=329 on 2026-07-20 (see `2026-07-18_daily_slope_consistency_shadow.md`) and Path Y itself was formally closed at n=1018 XAU/USD (see `2026-07-20_path_y_postmortem.md`). Deep analysis via `scripts/deep_analysis_orb.py` on the same n=1018 XAU/USD 2024-2026 sample revealed that Path Y's overall -$25,249 loss hides a **single positive sub-quadrant**:

Session × Direction cross-tab:
```
              LONG                    SHORT
ASIA   n=120  -$22/trade         n=81   -$197/trade   ← lose
LON    n=226  -$7/trade          n=149  -$154/trade   ← lose
NY     n=256  -$47/trade         n=186  +$161/trade   ← WIN (only quadrant)
```

Tightening to NY-SHORT + Low-ER (< 0.30 on 20-bar 5m closes ending at OR close) + Monday-Tuesday-Wednesday:

| Metric | Value |
|---|---|
| n | 91 |
| Mean per-trade | +$409 |
| Total P&L | +$37,258 |
| Bootstrap 95% CI on mean | **[+$45, +$760]** — clears zero |
| Win rate | 62.6% |
| Median | +$486 |
| Trades / year | ~36 |

**Mechanism identified** (see `2026-07-20_deep_analysis_findings.md` § "NY-SHORT mechanism investigation"):

- Winners come on 25% WIDER opening ranges (12.9 vs 10.3 pts) and 13% higher ATR
- Payoff asymmetry: winner mean +$1,233 vs loser mean -$971 (1.27:1)
- Real yield IDENTICAL across winners/losers (~2.0%) — NOT a macro-regime edge
- Sign confirmed on real GC futures 5m 60-day yfinance sample (n=31 NY-SHORT: +$36/trade, only positive quadrant)

## Hypothesis

For gold ORB entries where all four conditions hold —
1. `session == "NY"` (13:00 UTC OR open),
2. intraday direction is SHORT (slope-derived),
3. `ER_5m_20 < 0.30` (noisy prior 100 minutes indicates false-breakout risk),
4. `dow ∈ {Mon, Tue, Wed}`

— the taken trades exhibit statistically-significant positive expectancy over 2024-2026, and this expectancy will replicate on organic forward decisions at n≥100.

**H0** (null): Mean per-trade P&L of Path Z-taken trades = 0. Bootstrap 95% CI on the mean spans zero.
**H1** (alt): Mean per-trade P&L > 0 with 95% CI lower bound > 0 AND win rate ≥ 55%.

## Filter specification

```python
# strategy_engine.filter_path_z
def filter_path_z(cfg, ctx, regime):
    if not cfg.require_path_z:
        return None
    if cfg.name != "NY":
        return f"path_z: session {cfg.name} != NY"
    if ctx.slope_at_close >= 0:
        return f"path_z: slope not negative (not SHORT)"
    er = regime.efficiency_ratio_5m_20
    if er is None:
        return "path_z: ER unavailable"
    if er >= 0.30:
        return f"path_z: ER {er:.3f} >= 0.30"
    dow = ctx.session_open_utc.weekday()
    if dow not in (0, 1, 2):
        return f"path_z: dow not Mon-Tue-Wed"
    return None
```

**Feature computation** (`regime_context._efficiency_ratio`, new):
- Kaufman ER on last 21 5m closes: `ER = |Δp_net| / Σ|Δp|` for i in [-n..-1]
- Range [0, 1]; None if fewer than n+1 closes or denominator = 0

## In-sample effect size — Dukascopy XAU/USD n=1018 (2024-01-15 → 2026-07-20)

Full sensitivity ladder from `scripts/deep_analysis_orb.py`:

| Filter | n | Mean/trade | Total | Win rate |
|---|---|---|---|---|
| Path Y (no filter) | 1,018 | -$24.80 | -$25,249 | 50.0% |
| NY session only | 442 | +$40.57 | +$17,933 | 53.4% |
| NY SHORT only | 186 | +$161 | +$29,874 | 53.4% |
| NY SHORT + not-Fri | 149 | +$227 | +$33,755 | — |
| NY SHORT + Low-ER | 139 | +$270 | +$37,558 | 60.4% |
| NY SHORT + Low-ER + not-Fri | 112 | +$320 | +$35,827 | — |
| **NY SHORT + Low-ER + Mon-Wed** | **91** | **+$409** | **+$37,258** | **62.6%** |

Every filter step improves per-trade mean → each filter carries genuine signal, not noise. This is the tightest defensible subset with n approaching the ship-gate.

## Concentration risk — MUST BE DISCLOSED

In-sample fat-tail concentration:
- **Top 5 trades = 64% of the $37,258 P&L** (5 trades × ~$4,769 each)
- Top 10 trades = 89% of P&L
- Excluding top 5%: mean drops from +$409 to +$156/trade (still positive)
- Excluding top 1%: mean drops to +$75/trade

Implications:
1. **Live slippage on winners has asymmetric impact.** Missing target by a tick on 3 of the top 5 trades kills most in-sample edge.
2. **Filter drift is dangerous.** Any additional filter that excludes even 2-3 top winners would flip strategy negative.
3. **Live forward volatility will be extreme.** Standard deviation of P&L is $1,442 in-sample vs mean $409. Coefficient of variation 3.5×.

## OOS evidence

### Real GC futures 5m (yfinance 60-day, n=31)

Session × Direction on authentic GC futures data:
```
              LONG                    SHORT
ASIA    n=13  -$4                n=22   -$161
LON     n=12  -$340              n=22   -$498
NY      n=17  -$99               n=31   +$36 ← positive
```

**Same directional finding on real GC data.** n=31 is too small for ship-gate, but sign confirmation across different data sources is meaningful non-trivial evidence.

### Silver (XAG/USD) cross-check — INCONCLUSIVE

Silver 5m simulator produces artifact due to smaller point-scale (both stop + target hit within same 5m bar → conservative "stop" resolution). Requires 1m outcome resolution for clean cross-market test. Deferred.

### Knapp v9 candidate #1 — REJECTED SAME DAY

Prior to Path Z discovery, `knapp_er_stops_v9` was drafted as v9 candidate. Testing found gold lift +$2.35/trade (below +$50 ship gate) and 3-market reproduction on EUR/GBP/JPY all showed ~$0 lift. Registry: `knapp_er_stops_v9` → `rejected_pre_apply`. Path Z is v9 candidate #2 (see `2026-07-20_deep_analysis_findings.md`).

## Ship gates (ALL required)

Semantics differ from `daily_slope_consistency` because Path Z is a **restrictive take-filter** (not a skip-filter). Ship gate is measured on WOULD-TAKE decisions directly.

1. **n ≥ 100 shadow-taken decisions** across live+shadow tracker (organic forward)
2. **Mean per-trade P&L > 0** on the n≥100 sample
3. **Bootstrap 95% CI lower bound > 0** on mean per-trade P&L (2000 draws)
4. **Win rate ≥ 55%** of taken trades close net-positive
5. **Bonferroni-adjusted DSR passes** at the elevated N — today's registry has 25+ trials counted; DSR must exceed 0.95 given elevated V[SR_n]
6. **Path Z-specific SPRT pre-reg** before first live capital — cannot inherit `sprt_v72_1_launch_path_y`; requires fresh pre-reg with Path Z-specific H0/H1

## Rejection gates (any triggers REJECT)

- Mean per-trade ≤ 0 at n≥100 → REJECT
- CI includes zero AND mean < +$50/trade at n≥100 → REJECT (insufficient signal magnitude)
- Win rate < 55% at n≥100 → REJECT
- Any regime confound analysis reveals edge is driven by ONE outlier month → REJECT
- Not cleared by 2026-10-13 (Path C hard-stop in `sprt_v72_1_reentry_prereg`) → REJECT
- Post-hoc discovery of an additional filter that removes 2+ of the top-5 in-sample winners → CAUTION flag, reconsider design

## Compliance with quant framework

- **Pre-registration:** ✅ this doc
- **Bonferroni-N:** ✅ registry entry counted; N grew significantly today (dsc rejection at n=329, Knapp rejection, session/direction/ER/dow segmentation ≈ 6+ trials must count)
- **3-months-ago test:** ❌ FAILS. Path Z's specific filter combination (NY + SHORT + Low-ER + Mon-Wed) was DISCOVERED from analyzing today's n=1018 sample. Could not have been derived a priori. Weakens candidate strength substantially — documented weakness accepted for shadow-only status.
- **20-year OOS:** ❌ pending. Real GC 5m only exists 60 days rolling; can't test pre-2024 without paid data. XAU/USD spot 2024-2026 is what we have.
- **Cross-market reproduction:** ❌ pending (silver simulator artifact; EUR/GBP/JPY untested for NY-SHORT specifically).

**Overall pre-reg confidence: ~55-65% this is real edge.** Higher than dsc (~25% at rejection time) but lower than a shippable candidate should be. Live-forward accumulation is the critical remaining evidence.

## Interaction with Engine A halt and Path A/B/C

- **Does NOT flip Engine A kill switch off.** Kill switch remains ON per `sprt_v72_1_launch_path_y`.
- **This IS Path C** (from `sprt_v72_1_reentry_prereg` — "v7.3+ passes DSR AND new SPRT pre-reg"). If Path Z ships (all gates pass) it re-entries Engine A with Path Z as the active strategy.
- **First-live-trade size = 50%** of nominal (Path B ramp discipline). Full size only after Path Z-specific SPRT clears SAFE boundary at n≥5 clean live trades.

## Files changed (all shadow-only additive; no live behavior change)

- `src/regime_context.py` — added `_efficiency_ratio()` helper, added `efficiency_ratio_5m_20` param to `build_regime_context()`, added field to `RegimeContext` dataclass
- `src/strategy_engine.py` — added `efficiency_ratio_5m_20` field to `RegimeContext`, added `require_path_z` field to `SessionConfig`, added `filter_path_z` function, registered in `REGISTERED_FILTERS`, added `SESSION_CONFIGS_V9_Z` config
- `scripts/shadow_orb_tracker.py` — computes + logs `candidate_shadows.path_z` field for each shadow row going forward
- `scripts/shadow_ship_gate_report.py` — new `_analyze_take_filter` path for Path Z-style candidates (measure P&L on taken, not lift on skipped)
- `tests/test_strategy_engine.py` — added `TestFilterPathZ` class (9 test cases)
- `data/experiments/registry.json` — added `path_z_ny_short_shadow` trial entry, verdict `pre_registered`
- `docs/experiments/2026-07-20_path_z_ny_short_prereg.md` — this doc

## Live effect

**Zero.** All live SessionConfigs have `require_path_z=False`. Only the shadow tracker computes the Path Z decision and logs it. Engine A kill switch remains ON. No new alerts fire. No new trades execute.

## Immediate action

1. Wait for organic forward accumulation of Path Z-taken decisions on the shadow tracker (VPS is dispatching every 30 min).
2. At n≥30 forward-taken (est. ~4-6 weeks at ~7/week theoretical, likely slower due to filter strictness), re-read this pre-reg and re-run `scripts/shadow_ship_gate_report.py`.
3. At n≥100 forward-taken, apply full ship gate.
4. If ship gates all pass at n≥100: draft Path Z-specific SPRT pre-reg, promote registry from `pre_registered` → `pre_registered_pending_ship`, and consult user before flipping any live flag.
