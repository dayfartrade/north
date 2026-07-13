# v7.2.2 filter-sync proposal — live ↔ backtest divergence

**Discovered UTC:** 2026-07-13 14:20
**Status:** PROPOSAL (not applied). Live is kill-switched via H3 (validation_state.json="NOT READY") pending user decision.
**Owner:** Knox

## Core finding

`src/dispatch_orb.py:528` — the only OR/ATR filter in live:
```python
or_max = cfg.get("or_vs_atr_max", 2.0) * cur_atr
if or_range > or_max: skip
```

`edge_session_orb_v7_final.py` SESSION_CONFIG (backtest):
- LON: `or_vs_atr_max=2.0` — same as live ✓
- NY: `or_vs_atr_min=2.5` — **not in live**
- ASIA: `or_atr_deadzone=(2.0, 2.5)` — **not in live**

Live for NY/ASIA falls through to default `or_vs_atr_max=2.0` (LON's filter). **The v7.1 per-session filters (commit `a363282`, 2026-07-07) were only added to `edge_session_orb_v7_final.py` — `dispatch_orb.py` was never touched.**

## What live actually runs vs what was DSR-validated

- **DSR audit (2026-07-07):** validated backtest with per-session filters. n=72, 56.9% win, +$466/trade, CI [+$74, +$870].
- **Live since 07-01 launch:** running old v7.0-era filter (uniform 2.0 max). n=10, 10% win, -$12,095 net.
- **In-sample replay of 24 forward trades:**
  - LIVE filter kept 6 trades: 4W/2L (67%), +$3,291
  - BACKTEST (v7.1 intended) filter kept 11 trades: 6W/5L (55%), +$301

## Complications

1. **Live may be stricter/better** than intended v7.1 on in-sample data. Small n, but suggestive.
2. **Regime confound.** Live has been running in the 100% ry≥2.2 tail regime. Filter comparison is regime-contaminated.
3. **ATR revisions.** yfinance may have revised historical bars. In-sample replay ratios may not match what the strategy saw at trade time. Only today's NY (ratio 4.12) is unambiguous.
4. **Applied to today's NY (13:30 UTC):**
   - Live filter: skip (OR 21.90 > 2.0×5.32=10.64). Correct outcome.
   - v7.1 intended NY filter: pass (ratio 4.12 > 2.5). Would have taken the trade in a hostile regime.
   - **v7.1 would likely have added another loss.** This is not a strong endorsement for shipping v7.1 to live.

## Three decision paths

### Path X: SYNC live to backtest (implement v7.1 per-session filters in live)

```python
# In dispatch_orb.py:528, replace the current block with:
if cfg.get("use_or_filter", False):
    ratio = or_range / cur_atr if cur_atr > 0 else 0
    skip_reason = None
    if "or_vs_atr_max" in cfg and or_range > cfg["or_vs_atr_max"] * cur_atr:
        skip_reason = f"OR/ATR {ratio:.2f} > max {cfg['or_vs_atr_max']}"
    elif "or_vs_atr_min" in cfg and ratio < cfg["or_vs_atr_min"]:
        skip_reason = f"OR/ATR {ratio:.2f} < min {cfg['or_vs_atr_min']}"
    elif "or_atr_deadzone" in cfg:
        dz_lo, dz_hi = cfg["or_atr_deadzone"]
        if dz_lo <= ratio <= dz_hi:
            skip_reason = f"OR/ATR {ratio:.2f} in dead zone [{dz_lo}, {dz_hi}]"
    if skip_reason:
        msg = fmt_filtered({
            "session": sess_name, "or_range": or_range,
            "or_atr_mult": None, "atr_limit": None,
            "skip_reason": skip_reason,
        })
        _safe_send(msg, sent, k, actions, "orb_filtered", sess_name, open_ts, audience="public")
        continue
```

**Pro:** Live matches DSR-validated strategy. Restores design intent. Enables shadow-log candidates to be interpretable.
**Con:** In-sample replay suggests v7.1 filter is WORSE than what's actually live. Would have taken today's NY (probably a loser). Regime confound.

### Path Y: SYNC backtest to live (accept v7.0 filter as the "real" strategy)

Update `edge_session_orb_v7_final.py` SESSION_CONFIG:
- Remove `or_vs_atr_min` from NY
- Remove `or_atr_deadzone` from ASIA
- Set `or_vs_atr_max=2.0` explicitly on NY and ASIA (matches live default)

Then re-run DSR audit on this "actual" strategy.

**Pro:** Honest accounting of what live has been running. Doesn't change trading behavior. DSR is now valid for what actually deploys.
**Con:** Retroactively "loses" the v7.1 improvement claim. Prior confidence needs downgrading. v7.2 (TP 1.5→1.0 for NY) was tuned against v7.1 backtest — may not apply to v7.0-actual.

### Path Z: HALT + rebuild (retire v7.2.1, start v8)

Keep the kill switch on. Investigate the ATR-revision issue rigorously. Rebuild the backtest infrastructure so live and backtest share the same filter module (import from same source). Restart forward test under a clean strategy definition.

**Pro:** Cleanest. Removes ALL live/backtest divergence risk.
**Con:** Weeks of work. Delays public launch (07-30). Deep sunk-cost pain.

## Recommendation

**Path Y + rebuild strategy module for eventual v8.**

Rationale:
- Live has been running v7.0 filter and today's NY skip was arguably correct behavior. Don't fix what may not be broken.
- Re-running DSR on v7.0-actual gives us honest metrics — probably lower expectancy than v7.1 claim, but real.
- Buys time to design v8 with proper single-source-of-truth for filters.
- Kill switch stays on until we have new SPRT baseline against v7.0-actual metrics.

## Immediate consequences

1. **Kill switch stays on.** No live ORB entries until decision made and re-validated.
2. **VPS migration deferred** — no value migrating a halted system until strategy is settled.
3. **Public launch (07-30) at risk** — 17 days. If we choose Path Z, launch slips.
4. **All prior DSR/SPRT reasoning is regime + strategy contaminated.** Halt monitor's SPRT_HALT verdict is still directionally correct but the specific H0=0.57 baseline needs re-derivation.

## Suggested next-session sequence

1. Re-run backtest with LIVE filter (Path Y patch to SESSION_CONFIG) → new DSR audit
2. Update `sprt_v72_1_launch` pre-reg with corrected H0 based on live-filter backtest
3. Re-evaluate SPRT verdict against corrected baseline
4. If SPRT still HALT under corrected baseline: strategy is truly broken; investigate v8
5. If SPRT no longer HALT: reset kill switch, resume forward test
