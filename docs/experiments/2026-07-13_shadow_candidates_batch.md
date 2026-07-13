# Shadow candidates batch — 3 filters pending dispatch_orb.py feature extension

**⚠️ UPDATED 2026-07-13T11:00:00Z — `real_yield_gt_2_2` REJECTED PRE-APPLY.** OOS regime test on 20+ years found high-ry regimes historically produce HIGHER fwd gold returns. 3 of 4 launch LONG losses occurred on days GC closed UP intraday. Failure mode is intraday microstructure, not macro. See `scripts/oos_real_yield_regime.py` output. Filter would suppress correct-direction days. `prior_day_range_gt_80` and `gap_after_down_day` remain candidates because they target intraday-chop mechanics more directly.

**Registered UTC:** 2026-07-13T10:15:00Z (design; code apply deferred to post-CPI)
**Blinded until:** n=100 cumulative shadow decisions per candidate
**Owner:** Knox

## Why deferred

These 3 candidates need feature values not currently computed by `dispatch_orb.py`:
- `real_yield_gt_2_2` needs `real_yield_10y`
- `prior_day_range_gt_80` needs `prior_day_gc_range`
- `gap_after_down_day` needs `prior_day_close_change`

Applying these requires editing the live-dispatch path (feature dict extension). Doing that during CPI window (12:30 UTC) risks silently breaking the CPI PLAN. **Apply post-CPI at 14:00 UTC**, after CPI PLAN has fired and been observed.

## Diff spec — `src/dispatch_orb.py`

Add a helper (top of file, near other imports):

```python
# Local macro cache — cheap CSV lookup, no network
from pathlib import Path
import csv
_MACRO_CACHE = {}

def _load_macro(name):
    if name in _MACRO_CACHE:
        return _MACRO_CACHE[name]
    fp = ROOT / f"data/macro/{name}.csv"
    if not fp.exists():
        _MACRO_CACHE[name] = {}
        return {}
    out = {}
    with open(fp, newline="") as f:
        for row in csv.DictReader(f):
            try: out[row["date"][:10]] = float(row["value"])
            except: pass
    _MACRO_CACHE[name] = out
    return out

def _lookup_macro_le(name, d):
    data = _load_macro(name)
    best = None
    for k in data:
        if k <= d and (best is None or k > best): best = k
    return data.get(best) if best else None

def _gc_prior_day_stats(d):
    """Return (prior_day_range, prior_day_close_change) — cheap CSV read of GC_1d.csv."""
    fp = ROOT / "data/gc/GC_1d.csv"
    if not fp.exists(): return (None, None)
    prev_close = None
    prev_range = None
    cur_close = None
    with open(fp, newline="") as f:
        for row in csv.DictReader(f):
            try:
                k = row["ts"][:10]
                if k < d:
                    prev_close = float(row["close"])
                    prev_range = float(row["high"]) - float(row["low"])
                elif k == d:
                    cur_close = float(row["close"])
                    break
            except: pass
    close_change = (cur_close - prev_close) if (cur_close and prev_close) else None
    return (prev_range, close_change)
```

At line ~717 (features dict inside the shadow-log try block), add three keys:

```python
features = {
    ...existing keys...,
    "real_yield_10y": _lookup_macro_le("real_yield_10y__DFII10", open_ts.strftime("%Y-%m-%d")),
    "prior_day_gc_range": _gc_prior_day_stats(open_ts.strftime("%Y-%m-%d"))[0],
    "prior_day_close_change": _gc_prior_day_stats(open_ts.strftime("%Y-%m-%d"))[1],
}
```

## Diff spec — `src/shadow_log.py`

Add three CANDIDATES entries:

```python
"real_yield_gt_2_2": {
    "description": "Skip LONG PLAN if 10y TIPS real yield >= 2.2 (Erb-Harvey 2013 canonical; regime-conditioning per WGC framework)",
    "feature": "real_yield_10y",
    "operator": "ge",
    "threshold": 2.2,
    "registered_utc": "2026-07-13T14:00:00Z",  # SET AT APPLY TIME
    "preregistered_at": "docs/experiments/2026-07-13_shadow_candidates_batch.md",
    "status": "shadow",
},
"prior_day_range_gt_80": {
    "description": "Skip PLAN if prior-day GC range > 80 pt (whipsaw filter; from 07-13 post-mortem)",
    "feature": "prior_day_gc_range",
    "operator": "gt",
    "threshold": 80.0,
    "registered_utc": "2026-07-13T14:00:00Z",
    "preregistered_at": "docs/experiments/2026-07-13_shadow_candidates_batch.md",
    "status": "shadow",
},
"gap_after_down_day": {
    "description": "Skip LONG PLAN if prior-day close change <= -30 pt (dead-cat bounce filter; from 07-13 post-mortem)",
    "feature": "prior_day_close_change",
    "operator": "le",
    "threshold": -30.0,
    "registered_utc": "2026-07-13T14:00:00Z",
    "preregistered_at": "docs/experiments/2026-07-13_shadow_candidates_batch.md",
    "status": "shadow",
},
```

## In-sample results (24 forward-log trades)

| Candidate | Skips | W_skip | L_skip | Net after | Δ | p_raw (H0=57%) | Bonferroni × 6 (WGC vars) |
|---|---|---|---|---|---|---|---|
| real_yield_gt_2_2 (LONG-only) | 7 | 0 | 7 | −$1,008 | +$12,588 | 0.0027 | **0.0163** |
| prior_day_range_gt_80 | 9 | 3 | 6 | −$2,860 | +$10,736 | (untested LONG/all) | — |
| gap_after_down_day (LONG-only) | 2 | 0 | 2 | −$9,653 | +$3,943 | 0.185 | 1.0 |

## Ship gates (all)

Same as `vol_ratio_ge_1_0`: n ≥ 100 shadow decisions AND ≥ 60% precision on skipped losers AND expected P&L lift > 0 with holdout CI > 0. `real_yield_gt_2_2` will hit gate fastest given its unconditional-record semantics.

## Rejection conditions (all)

- Precision on skipped losers < 55% at n=100 → REJECT
- Skip rate > 30% of PLANs → REJECT (unless P&L improvement is decisive)
- Not cleared by 2026-10-01 → REJECT

## Compliance with quant framework (memory: quant_framework_gold.md)

- **Pre-registration:** ✅ this doc
- **Bonferroni:** ✅ WGC × 6 applied to real_yield_gt_2_2 (still p<0.05)
- **OOS on pre-regime data:** ⏳ needs backtest replay 2003-2007 (35% ry≥2.2 days) — do post-CPI
- **3-months-ago test:** ✅ real yield IS in the WGC gold framework since 2013; would have been named 3 months ago. `slope_gt_8` and `prior_day_range_gt_80` FAIL this test → weaker candidates.
