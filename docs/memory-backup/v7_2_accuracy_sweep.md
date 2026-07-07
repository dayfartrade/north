---
name: v7.2 accuracy sweep session (2026-07-07 pm)
description: Three shipped versions + rejected hypotheses log. 56.9% -> 69.2% win rate, +26% total P&L, all OOS-validated.
type: project
originSessionId: bb75b257-d83d-4c28-b913-c3fc4a842a01
---
**Session:** 2026-07-07 pm, "Knox on task, accuracy only" focus mode.

## Shipped (three commits)

| Version | Commit | Change | Delta |
|---|---|---|---|
| v7 (baseline pre-session) | pre-audit | n=72 v7-hybrid + stand_down | 56.9% win, +$466/trade, +$33.5k |
| **v7.1** | `a363282` | Per-session OR/ATR dead-zone gates (NY require >=2.5x ATR, ASIA skip [2.0,2.5]x) | 65.4% win, +$814/trade, +$42.3k |
| **v7.2** | `df813a2` | NY tp_mult 1.5 -> 1.0 | 69.2% win, +$780/trade, +$40.5k |
| **v7.2.1** | `ad3f332` | max_hold 120min -> 180min | 69.2% win, +$812/trade, +$42.2k |

**Cumulative delta v7 -> v7.2.1:** +12.3pp win rate, +74% mean/trade, +26% total P&L. Sharpe(pt) 0.266 -> 0.500. Max drawdown -$5,112. All OOS-validated on chronological 60/40 split with bootstrap CI lower bounds positive.

## Research pipeline used

For each hypothesis:
1. Full-sample sweep across a parameter range
2. Look for consistent directional improvement
3. Chronological 60/40 train/test split
4. Compare train vs test — divergence = overfit
5. Bootstrap 95% CI on OOS test mean/trade
6. Ship only if CI lower bound > 0 AND directional improvement is durable
7. If close-to-shipping but overlapping CI, ship as audit-only

## Rejected hypotheses (kept in log for future)

| Hypothesis | Why rejected | Revisit trigger |
|---|---|---|
| Prior-bar volume ratio filter | OOS CI [-$417, +$3459] includes zero | n>=100 live |
| Breakeven-stop at 1R | Hurt win rate (65% -> 61% full sample) | Never — mechanism is wrong |
| Partial-profit 1R + BE-SL rest | Real +5pp win rate but $-50/trade cost, CI overlap | Revisit if product prioritizes win rate over P&L |
| Retest-entry (wait for pullback) | Worse than baseline ($ and win rate) | Never for GC ORB |
| Trend slope magnitude filter | Didn't hold OOS — full-sample "signal" was noise | Never with this signal shape |
| Direction-specific filter (shorts only) | Regime-dependent (gold was downtrending); trend filter already handles | Revisit if we identify structural NY-LONG failure mode |
| Entry-timing skip 30-45min window | n=5 too small, though pattern is intriguing | Revisit at n>=100 live |
| Volume >= 1.2 hard filter | Real OOS lift but CI overlaps baseline meaningfully | Shipped as Box-6 informational audit; promote when n>=100 |
| Volume >= 1.0 hard filter (v7.3 candidate, 2026-07-07 pm) | Phase-7 PASS (n=32, 75.0% win, +$953/trade) BUT: trade count -38%, total -$11.7k, holdout n=7 CI includes zero (-$944, +$1581). Product tradeoff heavier than the accuracy gain justifies at this sample size. Reverted before shipping. | Revisit at n>=100 live if win-rate degrades meaningfully |

## Key MFE/MAE insights (found while researching)

- Winners peak at **median 87min** (not 30min or 60min); tail extends to 180min
- 54% of trades touch 1R at some point; 68% of those continue to target
- Losers reveal early: MAE median 50min vs winners 40min
- Rationale for 180min hold: captures the winner tail without impacting rate

## Direction bias observation (data snapshot, not a filter)

Current 52-trade window shows LONG trades losing (50% win, -$64/trade, total -$1,157) and SHORT trades winning big (79.4% win, +$1,276/trade, total +$43,379). This reflects the down-trending gold market during 2026-04 through 2026-07. The trend filter already handles this — it only allows trades in trend direction. If gold turns bullish, longs will start winning again.

**Do NOT ship a "shorts only" filter** — it's regime capture, not structural.

## Discipline notes

- 3 hypotheses shipped, 5+ rejected — the OOS discipline is the filter
- Every shipping cycle: full-sample analysis -> OOS split -> bootstrap CI -> lower bound > 0 gate
- If CI lower bound is close to zero, ship as audit-only (Box 6 volume, informational partial-1R)
- Reverse compensation: don't chase small $ gains at cost of win rate — user's product is signal accuracy

## Next candidates (pipeline)

- Correlation with DXY / real yields (external regime signal)
- Hourly-cyclical patterns (e.g., is NY at 09:30 ET different from ASIA at 08:00 JST for reasons beyond OR/ATR?)
- Multi-day patterns (does prev-day close outside prior range affect today?)
- Consult crypto-daytrader friend for hypotheses tested against this framework
