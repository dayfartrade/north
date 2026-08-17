# NORTH-BB design (originally titled "v2")

**Date:** 2026-07-31
**Author:** Knox
**Status:** TESTED 2026-08-17. Rejected as a v1 replacement. See "Backtest results" section.
**Naming note:** The shipped v2 shadow is the DXY filter (`scripts/far_weekly_v2_backtest.py`). This document is a separate, orthogonal refinement that swaps calendar entry/exit for Bollinger Band S/R. To avoid confusion with the live v2 shadow, this design is now referred to as NORTH-BB.
**Related:** `memory/north_v1_factsheet.md`, `docs/development_story.md`

---

## What v2 changes vs v1

v1 uses fixed calendar rules for entry and exit (Monday NY open, Friday NY close). User called this out as arbitrary. v2 replaces those calendar rules with support and resistance based on Bollinger Bands.

Everything else about v1 stays.

## Signal (unchanged from v1)

Same 4 conditions on daily XAU/USD closes, computed after Friday close for the next week:

- 4-week momentum M20 > 0 (LONG-eligible)
- 12-week momentum M60 > 0 (LONG-eligible)
- MA10 > MA40 (LONG-eligible)
- 20-day change in US 10y real yield < 0 (LONG-eligible)

**LONG** if all 4 LONG-eligible.
**SHORT** if all 4 SHORT-eligible (inverted).
**FLAT** otherwise.

The signal fires the direction. That's the thesis. v2 changes what happens next.

## Entry rule (new)

**Default timeframe:** 4-hour candles. Chosen because gold's macro-driven moves tend to unfold over hours to days, and 4H captures actionable support/resistance without being noisy.

**Bollinger Band parameters:** 20-period, 2 standard deviations. Standard defaults. Not tuned.

**Long entry:**
- After a LONG signal fires at Sunday 22:00 UTC, wait for price to touch or trade below the lower BB on 4H
- Enter long at the close of the first 4H bar where price traded at or below the lower BB
- If price never touches lower BB within 48 hours after publish, enter at market at 48-hour mark (fallback so we don't skip trades entirely when the market runs away)

**Short entry:**
- Mirror: wait for price to touch or trade above the upper BB on 4H
- Enter short at the close of that 4H bar
- 48-hour fallback if never touched

## Exit rule (new)

**Primary exit:** at the opposing BB.
- Long positions exit when price closes at or above the upper BB on 4H
- Short positions exit when price closes at or below the lower BB on 4H

**Time fallback:** if the opposing BB is never touched, exit at Friday 21:00 UTC close (same as v1). This preserves the "don't hold over weekend" discipline.

**Multi-week extension:** if the signal for the following Sunday is the same direction AND we're still in the trade at Friday close, hold the position through the weekend rather than exiting and re-entering. Saves round-trip costs. This is a new mechanism v1 doesn't have. If the following Sunday's signal is FLAT or opposite, exit at Friday close as normal.

## Stop loss (mostly unchanged from v1)

Same 2 x ATR(20-day daily) as v1, computed at signal time.

**One tweak:** the stop applies from the actual entry price (whatever the BB triggered), not from the reference price at publish. This is more honest because your risk starts when you actually enter, not when the signal was computed.

## What we compare in backtest

For each historical week where v1 would have fired directional:
1. What did v1 do? (fixed Monday-Friday, known outcome)
2. What would v2 do? (BB-based entry/exit)
3. R per trade comparison

Metrics on the same 16-year gold dataset:
- Win rate (v1 vs v2)
- Mean R per trade (v1 vs v2)
- Sharpe annualized (v1 vs v2)
- Max drawdown (v1 vs v2)
- Positive years count (v1 vs v2)
- Total trades taken (v2 skips some, extends others)

## Ship trigger

Per user directive: 0.5% per trade minimum.

v2 ships if:
- v2 mean R per trade >= 0.5%
- AND v2 mean R per trade > v1 mean R per trade on same period

If v2 clears 0.5% but doesn't beat v1, we don't ship v2 (no point). If v2 beats v1 but doesn't clear 0.5%, we don't ship v2 (below the bar).

If v2 fails, v1 stays live. We document v2 as a failed refinement attempt in the development story.

## Known unknowns

- Will BB touches happen in time? On strong-trending weeks the lower BB (for LONG) might sit far below and never get touched. The 48h fallback catches this but might mean entering at bad prices.
- Will 4H be the right timeframe? Might be too slow (miss the move) or too fast (noisy false triggers). Only backtest can tell.
- Will multi-week extension help or hurt? Real cost savings but keeps exposure over weekends which was one of v1's honest value props (limited overnight risk).
- Will 2x ATR stop still be appropriate when entry is not at reference price? Might be too wide from entry level.

## What NOT to include in v2

Not part of this design (would be v3 or new candidates):
- Position sizing based on signal strength (v2 keeps 1-contract sizing)
- Adaptive BB parameters (v2 uses standard 20/2)
- Alternative timeframes for urgent vs patient (v2 uses 4H fixed)
- Any macro filter beyond the 4 conditions (v2 keeps the same thesis)

## Backtest implementation notes

Use `research/tools/analysis_helpers.bollinger_bands()` for the BB computation. Use `research/tools/cost_model.compute_cost_adjusted_r()` for realistic R per trade (gold futures GC defaults: slippage 0.0002, fee 0.00003). Use `research/tools/bootstrap_stats.evaluate_signal()` for the CI and ship-trigger evaluation.

Backtest window: 2010-2026 Dukascopy XAUUSD daily bars (already have). 4H bars constructed from 5m data.

Signal generation: identical to v1 (verified against `scripts/far_weekly_gold_read.py`).

## Files to build

- `scripts/north_v2_backtest.py` - v2 backtest engine using shared tools
- `scripts/north_v1_vs_v2_compare.py` - side-by-side comparison

## Not building yet

- Live publisher for v2 (waits on backtest passing)
- Site page updates (waits on ship decision)
- Telegram integration updates (waits on ship decision)

---

## Backtest results (2026-08-17)

**Scripts:** `scripts/north_bb_backtest.py`, `scripts/north_v1_vs_bb_compare.py`
**Window:** 2010-01-01 to 2026-07-20 (16 years, Dukascopy XAUUSD 5m resampled to 4H)
**Matched weeks:** 363 directional signal weeks (v1 and BB both filled)

Side-by-side, all directions:

| metric | v1 | NORTH-BB |
|---|---|---|
| Trades | 363 | 363 |
| Win rate | 55.9% | 65.3% |
| Total P&L | $+181,598 | $+154,712 |
| Mean $/trade | $+500 | $+426 |
| Mean R per trade | +0.227% | +0.147% |
| Sharpe (ann) | +0.767 | +0.787 |
| Max drawdown | $56,043 | $38,660 |
| Positive years | 13/17 | 12/17 |

Ship trigger:
- A. BB mean R >= 0.5%: **FAIL** (+0.147%)
- B. BB mean R > v1 mean R: **FAIL** (v1 is +0.227%)

**Verdict: DO NOT SHIP as a v1 replacement.**

### What actually happened

- 71% of BB exits were `bb_target` (opposing BB touched). The band-to-band excursion is typically much smaller than a five-day trending move, so BB is systematically clipping profit early.
- 58% of BB entries hit the 48-hour fallback (market never came back to the entry band). On strong-trending weeks, waiting for a pullback that never arrives means entering at a worse price than v1's Monday open.
- Win rate rose almost 10 points (55.9% → 65.3%), but average winner shrank enough that expected value dropped.

### What BB does do well

- Max drawdown dropped ~31% ($56k → $39k).
- Sharpe is marginally higher (+0.787 vs +0.767).
- Long-only Sharpe drops (0.98 → 0.84) but short-only Sharpe nearly doubles (0.40 → 0.69).

So BB is a **variance-reduction transformation, not an alpha enhancement**. That is not what this design was chartered to be.

### What we do NOT do next

- Do not tune BB parameters (period, std, timeframe) to find a passing configuration. That is exactly the kind of after-the-fact fitting the pre-reg discipline exists to prevent.
- Do not re-run with the multi-week extension mechanism as a rescue attempt. That was listed as a "known unknown" in this doc; adding it now would be the same failure mode.

### Legitimate follow-up ideas (each requires its own pre-reg)

- BB-based ATR-adaptive stop (variance reduction as an isolated question).
- BB entry only (keep v1's Friday-close exit).
- BB portfolio blend: allocate some weight to BB, some to v1. Uncorrelated variance profiles might combine well.

None of these are being scheduled right now. Silver Candidate 3 and the Gold basis / Janus transplant remain higher on the queue.

