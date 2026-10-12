# Regime context indicator - design decision

**Date:** 2026-10-12
**Author:** Knox
**Status:** Design proposal. Deferred to Rook/Vega review before any implementation.
**Trigger:** Queue item #2 from 2026-09-08 agenda: "Add 'M12 LONG vs M6 SHORT' state to the weekly report. Doesn't drive trades but improves transparency."

## What the user originally wanted

A visible "regime disagreement" indicator in the weekly report when the monthly M12 regime disagrees with M6. The original intuition was that this disagreement signals caution - the trend is topping or bottoming.

## What the data actually says

The 2026-10-12 regime-disagreement trade analysis (`2026-10-12_regime_disagreement_trade_analysis.md`) rejected the general hypothesis that disagreement = worse trades. Of the eight (regime × direction) cells with meaningful n:

- Full agreement SHORT: Sharpe 0.30 (v2)
- Disagreement SHORT: Sharpe 0.85 (v2) - **better**
- Full agreement LONG: Sharpe 1.24 (v2)
- Disagreement LONG: Sharpe 1.64 (v2) - **better**

Only one disagreement state is reliably negative (M6_FLIP SHORT, n=9 on v2) and one is reliably positive (SPLIT_LONG SHORT, n=19 on v2). The rest are mixed or indistinguishable from the agreement baseline.

**Implication for the indicator design:** we should not frame disagreement as a caution signal. That would be a positive misrepresentation given the data. Instead, frame it as neutral *regime context* - show the facts, let the reader decide.

## Design options

### Option A - "Three-horizon trend tape"

A one-line field in the weekly report body (after the current signal row, before signal components):

> **Trend tape (1y / 6mo / 3mo):** LONG / LONG / SHORT

Each horizon is labeled by sign of the respective pct_change (M12=252d, M6=126d, M3=63d). Three labels, no editorializing. If all three agree, three LONGs or three SHORTs; if they disagree, the mix is visible.

**Pros:** fact-based, no narrative claim, works for every state.
**Cons:** three labels may feel dense; subscriber may not know what to do with it.

### Option B - Qualitative label

A short label field:

> **Regime context:** Trend fully aligned (M12/M6/M3 all LONG).

Or:

> **Regime context:** Mixed - annual trend LONG, 6-month trend SHORT.

**Pros:** readable, familiar.
**Cons:** harder to parse at a glance; risk of implying meaning (e.g., "Mixed" sounds cautionary even though the data says mixed is often *better*).

### Option C - Three-horizon numeric tape

Show the pct_change values directly, no labels:

> **Price vs 1y / 6mo / 3mo:** +18.4% / +4.1% / −3.2%

**Pros:** maximally honest, no interpretation layer, lets subscriber infer trend direction from the sign.
**Cons:** requires numeric literacy; weakens signal when readers don't do the math.

### Option D - Do not add this indicator

The user's original intuition (disagreement = caution) is wrong. The alternative "neutral context" indicator may not be worth the real-estate it takes.

**Pros:** avoids introducing a field whose semantic meaning will confuse readers.
**Cons:** doesn't honor the user's transparency goal; leaves a transparency gap.

## Recommendation

**Option A (Trend tape) + Option C (Numeric tape) combined** on a single line:

> **Price trend (1y / 6mo / 3mo):** +18.4% ↑ / +4.1% ↑ / −3.2% ↓

Reasoning:
1. Shows both the sign label (reader-friendly) and the magnitude (interpretable). No wasted real estate.
2. Does not editorialize or imply meaning.
3. Lets subscriber see when the shortest-horizon trend has flipped against the longest, without us having to coach them on what to think about it.
4. If future research surfaces specific regime states as meaningfully predictive (e.g., SPLIT_LONG SHORT is +2.14 Sharpe, M6_FLIP SHORT is −3.37 Sharpe), we can introduce qualitative annotations then - once we have *evidence* for them, not just an intuition.

## Placement in weekly report

Weekly report structure (per `product_focus_and_structure.md`):
- Frozen header: current call direction, instrument, confidence disclaimer
- Body: signal components, context, performance context

The indicator belongs in the **body**, immediately after the signal components row. Not in the header (header is frozen). Not in the daily brief (daily brief has its own changing-header + updates).

## Trigger condition

**Always show, every week.** Not just when disagreement occurs. Rationale:
- Removes the "indicator appearing = flag event" implication, which would be wrong given our data.
- Gives the reader a running sense of what regime we are in.
- Consistency makes it feel like data, not editorial.

## Field name

**`price_trend_tape`** - the data field in the JSON output.
**`Price trend (1y / 6mo / 3mo)`** - the display label.

## Computation

```python
m12 = (close_today / close_252d_ago) - 1
m6  = (close_today / close_126d_ago) - 1
m3  = (close_today / close_63d_ago)  - 1
```

If any of these cannot be computed (insufficient history), show "n/a" for that horizon. In practice all three will be computable from 2010-06-01 onward, so this is only a concern during data pipeline bootstrapping.

## What NOT to include

- No "regime caution" labels or color coding.
- No "disagreement warning" styling.
- No "wait for alignment" messaging.
- The data does not support any of these framings.

## Flagged for research debt

The M6_FLIP SHORT cell (v1: n=16 Sharpe −2.95; v2: n=9 Sharpe −3.37) remains interesting but is NOT ready for product-side action. Next session should decide whether to replicate on new data when Dukascopy pulls another 3 months, or to leave it as a flagged observation for the longer term.

Does not change the main v3 pre-reg scope.

## Deferred to Rook/Vega

This is a weekly-report content change. Per the shared workspace model (`shared_workspace_northengine.md`):
- Rook owns `app/north/**` - the subscriber-facing display.
- Vega owns `app/api/**` - the JSON structure that drives it.

Both need to approve the field addition before implementation. This design doc is the artifact to share with them.

## Files touched

- Doc: `docs/experiments/2026-10-12_regime_disagreement_indicator_design.md` (this file)

No code written. No live changes. Awaits Rook/Vega review.
