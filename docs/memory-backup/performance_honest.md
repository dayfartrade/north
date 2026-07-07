---
name: Honest v5 performance estimate
description: Realistic Sharpe & DSR, NOT the headline backtest number
type: project
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
**Use these numbers — not the headline.**

| Metric | Realistic | Notes |
|---|---|---|
| Per-trade Sharpe | 0.147 | mean / std of net P&L |
| **Annualized Sharpe** | **~0.59** | × √(16 trades/yr) — proper trade-rate scaling |
| Headline Sharpe (×√252) | 2.30 | conventional published, NOT realistic |
| Win rate | 55.3% | over 38 backtest trades |
| Mean P&L / trade | +$468 | per GC contract, post $24 RT cost |
| Profit factor | 1.62 | |
| Quarters profitable | 5/9 | walk-forward, params frozen |

**Deflated Sharpe Ratio (multiple-testing corrected):**
- N_TRIALS=50 → DSR = 10.3% (marginal)
- N_TRIALS=200 → DSR = 4.0% (just barely significant at p<0.05)
- N_TRIALS=1000 → DSR = 1.2% (weak)

**How to apply:** When reporting performance to user, lead with annualized Sharpe ~0.59 and DSR. Don't quote the 2.30 number unprefixed — it'll mislead. The strategy probably has small real edge (multiple nulls support it) but smaller than naive backtest implies. Forward-testing is essential to converge on truth.

**Validation that survived:**
- Random-timestamp null: p=0.03 (news timing matters)
- Inverse-strategy null: real +$17,792 vs inverse −$10,214 (filter is real edge)
- GLD cross-asset: FOMC subset 70% wins (edge transfers vehicle)
- Parameter stability: 240/240 nearby configs all profitable
