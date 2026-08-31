# Post-mortem: NORTH LONG week 2026-08-24 to 08-28

**Date:** 2026-08-31
**Author:** Knox
**Status:** Post-mortem. Not a rule change.
**Trigger:** First live directional loss on a LONG signal; two-of-two live directional trades are now losers.

## The trade

| field | value |
|---|---|
| Direction | LONG |
| Signal date | 2026-08-21 (Fri close) |
| Week | 2026-08-24 → 2026-08-28 |
| Entry proxy | $4602.06 (Fri 08-21 close, before Mon open gap) |
| Stop | $4401.00 (2 x ATR20, ATR20 = $100.53) |
| Exit | $4450.06 (Friday time-exit) |
| Net return | **-3.30%** |
| MAE (week low) | $4451.80 on Fri 08-28, 0.49 ATR from stop |
| Days held | 5 |

The v1 signal fired with all four conditions positive: 4-week momentum +13.66%, 12-week momentum +1.42%, MA10 above MA40, real-yield 20d change -2 bps. It was the strongest LONG setup published since the pre-reg went live in July.

## Anatomy of the loss

Daily walk from GC futures (`data/gc/GC_1d.csv`):

| day | open | high | low | close | vs entry |
|---|---|---|---|---|---|
| Mon 08-24 | 4638.0 | 4670.9 | 4635.1 | 4640.8 | +0.84% |
| Tue 08-25 | 4630.5 | 4638.1 | 4626.2 | 4638.1 | +0.78% |
| Wed 08-26 | 4615.3 | 4615.3 | 4598.2 | 4598.2 | -0.08% |
| Thu 08-27 | 4609.7 | 4609.7 | 4609.7 | 4609.7 | +0.17% |
| **Fri 08-28** | **4599.3** | **4625.5** | **4451.8** | **4478.1** | **-2.69%** |

The trade was mild-positive through Thursday. The entire loss came from a single Friday session: -2.69% close-to-close, with an intraday low of $4451.80 that put us within $50 (0.5 ATR) of the stop before recovering to $4478.10 by 21:00 UTC time-exit. There was no drift, no early warning, no partial exit gate that would have helped. The stop held. The rules resolved as designed.

**One thin bar of note.** Thursday 08-27's daily bar shows open=high=low=close=$4609.70 with 5,558 volume - likely a data artifact from the GC continuous contract during a low-liquidity session. Does not change the outcome. Flag for the data-refresh workflow to sanity-check.

## What the three signal variants said at 08-21

Reconstructed offline from GC daily bars + local macro. Numbers deviate slightly from the production shadow log (which uses XAUUSD 5m resampled and had fresher DXY/RY data), but directions are stable.

| variant | direction | driver |
|---|---|---|
| **v1 (live product)** | **LONG** | All 4 conditions bullish: M20 +13.68%, M60 +3.33%, MA10>MA40, RY_chg -2bps |
| v2 shadow (v1 + DXY) | **FLAT** | DXY 20d change ≈ 0 (need < 0 for LONG confirmation) - dollar not weakening |
| Ensemble (v1 + v2 + monthly M12) | **LONG** | Votes: v1 LONG, v2 FLAT, monthly M12 LONG (+37%). 2-of-3 majority → LONG |

**Live P&L implication (if the shadows had been the product):**

- v1 traded: -3.30%
- v2 would have skipped: 0%
- Ensemble would have traded LONG: -3.30% (same result - v1 loser was not blocked by the ensemble)

## Rolled-up two-trade sample

Both live directional trades were losers. Both shadows would have blocked (or matched) v1's action asymmetrically:

| week | v1 | v1 P&L | v2 shadow | v2 P&L | ensemble | ensemble P&L |
|---|---|---|---|---|---|---|
| 2026-07-27 SHORT | SHORT | -0.72% | FLAT (DXY -0.006, need >0) | 0% | FLAT (v1 SHORT, v2 FLAT, monthly LONG = split) | 0% |
| 2026-08-24 LONG | LONG | -3.30% | FLAT (DXY ≈ 0, need <0) | 0% | LONG (v1+monthly outvote v2) | -3.30% |
| **cumulative** | | **-4.02%** | | **0%** | | **-3.30%** |

**Read:** N=2. Not evidence. But both v1 losers had the DXY filter tripped, which is the exact failure mode v2 was designed to guard against (v1 firing without dollar confirmation). If this pattern held through the 26-week pre-reg forward window (24 more directional trades minimum), it would substantially strengthen the case for v2 ship. Right now it is a suggestive datapoint, nothing more.

Ensemble is a wash on this trade - v2's FLAT was outvoted by v1's LONG plus monthly M12's LONG. That is by design (majority rule) but it means the ensemble does NOT benefit from v2's specific edge on this trade.

## Shadow log gap (operational finding)

The `data/far_weekly_v2_shadow.jsonl` and `data/far_weekly_ensemble_shadow.jsonl` logs have **no entry** for signal_date 2026-08-21. The 2026-08-23 weekly-publish run failed at the git-push step (documented in prior session), and the state-reconstruction commit (`1213fb5`) only re-appended the public call - the shadow log entries were lost. Next commit to the shadow log is 2026-08-30.

**Action:** left in place. Filling the log after the fact with reconstructed numbers would compromise the append-only guarantee that makes the shadow useful for forward validation. The reconstruction above is the record. Any future gap-checks should treat 2026-08-21 as missing.

**Follow-up:** the same failure mode could recur. The weekly-publish workflow should either commit shadow-log rows in the same atomic push as the call, or the fallback state-reconstruction script should include the shadow logs.

## Signal-side conclusions

1. **v1 rules behaved exactly as pre-registered.** No implementation bug. Entry, stop, time-exit all correct. This was a normal loss, not a system error.
2. **The stop worked.** MAE reached 0.49 ATR from the stop. A tighter stop (1.5 ATR) would have been hit intra-Friday. A wider stop (2.5 ATR) would have taken a larger loss on time-exit. 2 ATR is not vindicated by N=1 but it wasn't punished either.
3. **v2's edge case survived first contact.** DXY filter was designed to block "v1 fires without dollar confirmation" - it did, on both live losers. This is the first live evidence that the pre-reg finding (v2 as legitimate v1 replacement candidate) is showing up in production data.
4. **Ensemble did not help here.** The 2-of-3 majority rule allowed monthly M12 (long-side bullish since gold's YoY momentum is +30%+) to override v2's caution. Consider whether monthly M12 is contributing useful signal or just going along with v1.

## What NOT to do

- Do not change v1 rules. N=2, both losers, is inside the noise distribution of 55.9% win-rate strategy. Two-loss streaks are common.
- Do not ship v2 early. Pre-reg is 26 weeks forward. We have 2. Wait for the sample.
- Do not tighten or loosen the stop. 2 ATR was pre-registered; deviating now is p-hacking.
- Do not add a "trend-strength" filter or any other in-flight tweak driven by these two trades.
- Do not soften the public track record page. -3.30% loss is what it is; the honesty statement is already appropriately calibrated (the sample-size disclaimer covers this).

## What to watch next

1. **Every future directional trade, log v2 and ensemble in parallel with v1's live result.** After 4-6 more directional trades, revisit whether the v2-skips-losers pattern is holding or randoming out.
2. **Backfill the shadow logs if any future publish fails.** Change the workflow so shadow rows are part of the same commit as the call.
3. **Consider a monthly M12 sanity check.** If the ensemble is systematically LONG-biased because monthly is stuck LONG in a bull market, ensemble may not add value over v1 alone. Worth an audit at N=6+ directional.
4. **Friday-flush risk in general.** Both losses closed the position on Friday near session lows. If this becomes a pattern (3+ losses closing in the bottom half of Friday's range), consider a Thursday-close or intraweek partial-exit variant. Not now - after more sample.

## Track record after this trade

- Directional resolved: 2 (both losses)
- Cumulative return on directional: -4.02%
- FLAT weeks: 2 (2026-08-10, 2026-08-17)
- New FLAT for 2026-08-31 → 09-04
- 16-year backtest reference: 55.9% WR, +0.23% mean/trade, Sharpe 0.77
- Sample size to reach pre-reg statistical validity: 24 more directional trades

## Files touched (or intentionally NOT touched)

- Post-mortem: `docs/experiments/2026-08-31_long_postmortem.md` (this file)
- Development story: appended entry for 2026-08-31
- Shadow logs: NOT modified. Gap for 2026-08-21 documented above, not backfilled.
- Signal code, stop rules, workflow triggers: unchanged.
