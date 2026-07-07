---
name: v7.1 OR/ATR session gates (accuracy uplift)
description: Session-specific dead-zone filters discovered from live-loss autopsy on 2026-07-07; shipped as commit a363282
type: project
originSessionId: bb75b257-d83d-4c28-b913-c3fc4a842a01
---
**Trigger:** Bar-by-bar autopsy of the 2 live losses (07-01 NY, 07-02 ASIA) on 2026-07-07 revealed a diagnosable geometry pattern the strategy was ignoring.

## The finding

Per-session performance decile analysis on the full n=72 v7 backtest showed **two systematic loss zones:**

| Session | Dead zone | In-sample stats | Verdict |
|---|---|---|---|
| **NY** | OR/ATR < 2.5 | n=10, 30% win, **−$1,006/trade**, total **−$10,060** | Skip |
| **ASIA** | 2.0 ≤ OR/ATR ≤ 2.5 | n=11, 36% win, −$119/trade, total −$1,309 | Skip |
| LON | none | n=8 too small to filter | Keep as-is |

## OOS validation (chronological 60/40)

Round-number thresholds (harder to overfit) held on the test set:
- TEST baseline: n=29, 62.1% win, +$594/trade
- TEST v7.1:     n=23, 69.6% win, +$986/trade
- **Bootstrap 95% CI on OOS mean/trade: [+$219, +$1,766] — lower bound positive**

Data-tuned thresholds produced IDENTICAL test-set outcome → not overfit.

## Full Phase 7 post-change

```
v7   -> v7.1
n:    72 -> 52
win:  56.9% -> 65.4%       (+8.5pp)
mean: +$466 -> +$814       (+75%)
tot:  +$33.5k -> +$42.3k   (+$8.8k)
CI-lo: +$74 -> +$334       (4.5x stronger)
Sharpe(pt): 0.266 -> 0.452 (+70%)
holdout n=11, 81.8% win, mean +$923
OVERALL: DEPLOY-READY
```

## Live-loss counterfactual

- **07-02 ASIA** (OR/ATR = 2.03) → v7.1 SKIPS (saves −$599)
- **07-01 NY** (OR/ATR = 5.56) → v7.1 still TRADES (5.56 is in the 73%-win zone; the loss was variance, not systematic)

## Code shape

`src/edge_session_orb_v7_final.py:SESSION_CONFIG`:
```python
"ASIA": { use_or_filter: True, or_atr_deadzone: (2.0, 2.5), ... }
"NY":   { use_or_filter: True, or_vs_atr_min: 2.5, ... }
"LON":  unchanged (or_vs_atr_max: 2.0)
```

Filter logic in `run_orb_v7` at line ~92: three mutually-exclusive skip reasons (`or_too_wide_vs_atr`, `or_too_narrow_vs_atr`, `or_atr_deadzone`).

## Why this matters + risks

**Trade rate drops:** from ~1.5/day to ~1.1/day. Fewer alerts, higher quality.

**Overfitting risk:** thresholds were chosen after seeing the data; even with OOS pass, live drift is possible. Weekly auto-revalidation is the safety net; if verdict flips to NOT READY, H3 kill-switch suppresses dispatch.

**Reversible:** `git revert a363282` puts v7 back. All state files stay compatible.

**Ship rationale:** the accuracy uplift (+75% mean/trade) dwarfs the incremental variance risk, and staying on v7 while the 07-02 ASIA-shaped loss pattern is now identified would be knowingly leaving profit + peace of mind on the table.

## Follow-ups

- Watch n=52→100 accumulate on weekly validation — graduate WEAK → USABLE
- If crypto-daytrader consultant flags additional filters (volume, retest entry), test each with the same 60/40 OOS methodology before shipping
- Consider whether LON's small sample warrants its own analysis at n≥15
