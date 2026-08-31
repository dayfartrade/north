# Monthly M12 momentum regime audit (context for ensemble)

**Date:** 2026-08-31
**Author:** Knox
**Status:** Analytical finding. Does not require a rule change. Informs how we read the ensemble's forward window.
**Trigger:** Post-mortem on the LONG loss surfaced that the ensemble's 3-way vote reduces to a 2-way vote in the current regime because monthly M12 is stuck LONG. Wanted to quantify.

## The question

The ensemble strategy (`docs/experiments/2026-07-24_ensemble_v1_v2_monthly_prereg.md`) takes a directional trade when >= 2 of {v1, v2, monthly M12} agree. Monthly M12 = LONG if 12-month gold return > 0, SHORT if < 0. Simple sign check on trailing 252-day return.

If M12 is stable (rarely flips), the ensemble is effectively a 2-way vote between v1 and v2 with a persistent bias from whichever direction M12 is stuck on. If M12 flips often, it's actually contributing signal.

Which is it?

## Data

Combined Dukascopy XAU/USD daily bars from 2010-01-01 to 2026-07-20 (local snapshot; production is fresher but this is 4,297 weekday bars, plenty for a regime audit). Computed M12 = `close.pct_change(252)`, direction = sign.

## Results

**Full sample:** 4,297 weekdays, M12 direction distribution:

- LONG: 63.3%
- SHORT: 36.7%
- FLAT (exactly 0): 0

**Year-by-year fraction LONG:**

| year | LONG % | SHORT % | comment |
|---|---|---|---|
| 2011 | 100% | 0% | tail of 2008-2011 bull |
| 2012 | 75% | 25% | topping |
| 2013 | 2% | 98% | bear market |
| 2014 | 10% | 90% | bear |
| 2015 | 5% | 95% | bear |
| 2016 | 89% | 11% | flip up |
| 2017 | 54% | 46% | choppy |
| 2018 | 52% | 48% | choppy |
| 2019 | 62% | 38% | mostly LONG |
| 2020 | 100% | 0% | COVID rally |
| 2021 | 50% | 50% | choppy |
| 2022 | 40% | 60% | choppy |
| 2023 | 89% | 11% | flip up (final SHORT stretch ended 03-17) |
| 2024 | 100% | 0% | bull |
| 2025 | 100% | 0% | bull |
| 2026 (YTD) | 100% | 0% | bull |

**Sign flip count:** 101 total flips across 16 years, ~1 flip per 40 days on average. But flips cluster heavily in 2021-2022 (24 flips in 12 months, mostly single-day whipsaws around $1,800). Outside those two chop years, M12 direction is mostly stable per year.

**Current LONG streak:** started **2023-03-17**, ongoing as of 2026-07-20. That's **1,221 consecutive days of M12 = LONG.** Every ensemble signal computation for the past 3+ years has had monthly M12 voting LONG.

## What this means for the ensemble

Given monthly M12 has been LONG for 3+ years, the ensemble's 3-way vote reduces to:

| v1 says | v2 says | ensemble says (with monthly = LONG) |
|---|---|---|
| LONG | LONG | LONG (unanimous, 3-0) |
| LONG | FLAT | LONG (2-of-3: v1 + monthly outvote v2's FLAT) |
| LONG | SHORT | LONG (2-of-3: v1 + monthly outvote v2's SHORT) |
| FLAT | LONG | LONG (2-of-3: v2 + monthly) |
| FLAT | FLAT | FLAT (1-0-2 needs 2 to agree on a direction; only monthly LONG) |
| FLAT | SHORT | FLAT (1-1-1 no majority) |
| SHORT | LONG | LONG (v2 flips against v1 while monthly holds LONG) |
| SHORT | FLAT | FLAT (1-0-1 no majority; monthly=LONG blocks SHORT) |
| SHORT | SHORT | FLAT (2 SHORT votes but monthly LONG makes it 2-1 SHORT... wait) |

Actually the last row does trip a SHORT: v1=SHORT + v2=SHORT = 2 SHORT votes, monthly=LONG is 1 LONG. Ensemble = SHORT.

So the practical rules in the current regime become:

- **Ensemble = LONG** whenever v1 = LONG (regardless of v2), OR when v2 = LONG on a v1-FLAT week
- **Ensemble = SHORT** only when v1 AND v2 both say SHORT (requires DXY strengthening for v2 SHORT)
- **Ensemble = FLAT** for everything else, including any lone v1 SHORT

Compare to what the ensemble would do if M12 flipped SHORT (mid-2013 through 2015, for example):

- Ensemble = SHORT whenever v1 = SHORT (mirror)
- Ensemble = LONG only when v1 AND v2 both say LONG
- Ensemble = FLAT for everything else

**The ensemble is not a stable 3-way vote. It's a "v1 filtered by whichever direction M12 has been stuck on for months to years." The identity of the filter flips only when M12 flips, which happens rarely (about every 4 years on average, more often during chop periods).**

## Implication for the pre-reg forward window

The ensemble is in a 26-week shadow window ending ~2027-01-31. Every week of that window has M12 = LONG. So the shadow is not actually testing "ensemble as a 3-way voter" - it's testing "v1's LONG signals minus v1's SHORT signals" (approximately). That's a real strategy, and the OOS 2019-2026 backtest showed Sharpe 1.012 which is a legitimate result, but it's a regime-conditional result.

If M12 flips SHORT during the shadow window (it hasn't for 3+ years, so unlikely to flip in the next 6 months barring a >25% gold selloff), the ensemble will suddenly start behaving as a "v1 SHORT-only with LONG signals blocked" strategy. That would be a discontinuity the current shadow window cannot detect.

## Implication for the live product

The 2026-08-24 LONG loss was NOT blocked by the ensemble (monthly M12 outvoted v2's FLAT to keep the LONG). The 2026-07-27 SHORT loss WAS blocked by the ensemble (monthly M12 outvoted v1's SHORT).

Both losses fit the current-regime pattern:

- v1 LONG signals: ensemble follows unless v1+v2 both say otherwise → ensemble = v1 for LONGs → same L/L on LONG signals
- v1 SHORT signals: ensemble blocks unless v2 also confirms SHORT → ensemble skips most SHORTs → misses SHORT winners AND losers

If the live product ever ships to the ensemble, we should be honest about what we're actually shipping: not a "3-way ensemble" but a "v1 LONG + rare v1+v2 confirmed SHORT" strategy, which is a specific bet that gold continues to trend up or that when it doesn't, the dollar is strengthening.

## What I did NOT do

- Did not re-run the ensemble backtest. The pre-reg OOS results (Sharpe 1.012, WR 59.5%, +$135,357 across n=168) stand; this audit adds context, not correction.
- Did not modify the ensemble computation code. The 3-way vote is still what runs; it just happens to reduce to a 2-way vote in the current regime.
- Did not change any live rules. v1 stays live; v2 and ensemble stay in shadow.

## Follow-ups (queued, not urgent)

1. **Regime-conditional Sharpe.** Split the 16-year backtest into "M12 LONG" periods and "M12 SHORT" periods. Compute ensemble Sharpe separately. If Sharpe is much higher in one regime, we're really discovering a directional bias not a voting mechanism. **DONE 2026-08-31: see `docs/experiments/2026-08-31_m12_regime_split_ensemble.md`. Finding: v2 wins in every cell; ensemble matches v1 in M12 LONG regime, only beats v1 in M12 SHORT regime. Ensemble's headline appeal is regime-conditional.**
2. **Alternative aggregators.** If M12 is contributing noise more than signal (stuck LONG for years), consider:
 - Drop M12 entirely, ensemble becomes 2-way v1+v2 (unanimous only)
 - Replace M12 with a regime detector that only fires on genuinely trending regimes
 - Weight M12 by recency of its last flip (fresh flip = higher weight, stale = lower)
 All would need their own pre-reg. None are ready to propose.
3. **Public disclosure.** If ensemble ever ships, the shadow-window results need to carry a note: "measured during a period of persistent LONG monthly regime; expect different behavior when regime flips."

## Files touched

- Audit: `docs/experiments/2026-08-31_monthly_m12_regime_audit.md` (this file)
- Registry note: TODO. Ensemble trial `far_weekly_gold_ensemble_v1` should get a note appended describing the M12 regime-conditionality. Not doing it in this session; keeping registry updates atomic per formal test outcome.
