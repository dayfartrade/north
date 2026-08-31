# v2 elevation ship package

**Purpose:** everything needed to ship v2 as the live NORTH product IF the pre-registered forward window (2027-01-22) closes with v2 clearing its ship gate.

**Status:** DRAFT. Contingent on forward-validation outcome. Not to be executed before the window closes.

**Owner:** Farhad's decision to execute. Knox prepared the package.

---

## The gate that must clear (from v2 pre-reg 2026-07-22)

- v2 forward mean weekly return > v1 forward mean weekly return, AND
- Both individually > 0
- Window: 2026-07-22 through 2027-01-22 (26 weeks)
- Sample: all directional weeks resolved in the window

If any of these fail, v2 does NOT ship. Instead:
- v2 forward mean <= 0: reject v2, retire the candidate
- v2 forward mean > 0 but not > v1: continue v2 shadow another window, or downgrade to "no material improvement"

## Pre-flight checklist (day of ship, likely 2027-01-25 or similar Sunday)

- [ ] Pre-reg gate confirmed cleared (compute forward-only stats, no in-sample leak)
- [ ] Farhad approves the version swap
- [ ] `docs/development_story.md` appended with the ship-day entry
- [ ] `data/experiments/registry.json` v2 verdict updated `pre_registered_shadow` → `shipped`
- [ ] `data/experiments/registry.json` v1 verdict updated `shadow_beta` → `retired_replaced_by_v2`
- [ ] Retirement wall regenerated (`scripts/build_retirement_wall.py`)
- [ ] Track record regenerated (`scripts/render_track_record.py`)
- [ ] Announcement post drafted, reviewed, ready to send

## Code changes required at ship

Minimal. v2 is currently a shadow computation inside `scripts/far_weekly_gold_read_publish.py` alongside v1. Ship = flip which variant drives the public call.

### Change 1: `scripts/far_weekly_gold_read_publish.py`

Replace `compute_current_signal()` to use v2 rule (v1 conditions AND DXY-alignment) instead of v1 alone. Or add a `--use-v2` flag and switch the workflow to pass it.

Simpler: rename the function and add a version constant at the top:

```python
PRODUCT_VERSION = "v2"  # was v1 through 2027-01-22
```

Add DXY_chg to the entry conditions. Keep the shadow logs running so we can compare v2-live vs v1-shadow going forward. Same as we did the other way around before.

### Change 2: `scripts/verify_north_v1_backtest.py`

Add a companion `scripts/verify_north_v2_backtest.py` with v2's advertised numbers hardcoded and a reproduction script. Keep v1 verify script alive as the archive check.

### Change 3: `site/data/far_weekly_backtest_summary.json`

Update the summary payload with v2's numbers:
- win_rate_pct: 58.5 (v2 backtest 16yr)
- mean_return_pct: 0.31
- sharpe_ratio: 1.04
- sharpe_alt_weekly_basis: 0.68 (recompute at ship)
- directional_trades: 270 (backtest count; live count separate)
- Include a `previous_version` object with v1's numbers preserved

### Change 4: `docs/launch/subscriber_faq.md`

Update the "What is the signal?" and "How does it work?" answers to describe the v2 rule (v1 + DXY-alignment). Add the version-history section:

> **Version history**
> - v1 (BETA, 2026-07-22 through 2027-01-22): 4-condition weekly filter. Live track record preserved.
> - v2 (LIVE, 2027-01-22 onward): v1 + DXY-alignment filter. Backtest Sharpe 1.04 vs v1's 0.77.

## Announcement copy (candidate, Farhad reviews)

**Telegram post text:**

> NORTH v2 goes live starting the call this Sunday.
>
> Same weekly cycle. Same publish time. Same honest disclosure.
> One change: v2 adds a dollar-strength filter on top of v1's four conditions. LONG needs dollar to be weakening. SHORT needs dollar to be strengthening.
>
> The filter drops about a quarter of v1's directional signals. In backtest, the dropped quarter is where v1 loses money (Sharpe -0.14 over 16 years). Keeping only the DXY-confirmed trades gives Sharpe 1.04 vs v1's 0.77 in the same backtest.
>
> Live validation:
> - v1 forward record from 2026-07-22 to 2027-01-22 (26 weeks): [insert numbers]
> - v2 shadow forward record over the same window: [insert numbers]
> - Ship gate cleared: v2 forward mean > v1 forward mean, both > 0.
>
> v1's full track record stays visible. Retirement wall lists v1 as "retired, replaced by v2 2027-01-22" with a link back to its verified backtest and its 26-week live results.
>
> Same product structure. Same publish cadence. Same honesty.

## Site changes (route through Rook)

Rook builds; Vega SEO-reviews. Do not touch site code from the NORTH side.

Items to request (in one Rook message on ship-day):

1. Update `/north` header from "NORTH BETA" to "NORTH v2 LIVE"
2. Add version-history section to methodology page (or wherever it lives by then)
3. Update the backtest strip to reflect v2 numbers primary, v1 as historical reference
4. Add a "See v1 track record" link that shows the frozen v1 26-week live record
5. Update the small-sample note to reset counts for v2 live (n=0 at ship)

## What NOT to change at ship

- Retirement wall keeps all 39 retired candidates
- Development story stays complete (no rewriting history)
- Old v1 factsheet stays accessible (mark superseded, don't delete)
- Backup workflow keeps running
- Ensemble shadow keeps running with its own forward window (independent from v2 ship decision)

## Rollback plan if v2 misbehaves post-ship

If v2 live goes 0-6 in the first months post-ship (formal halt zone under SPRT), or if there's a mechanical bug discovered:

1. Immediate: `touch data/far_weekly_paused` (kill switch, halts publish)
2. Diagnose: full post-mortem, same discipline as any prior halt
3. Options: rollback to v1 (which stays runnable in the codebase), suspend indefinitely, or advance to a v3 candidate that was pre-registered before v2 shipped

The v1 code stays runnable even after v2 ships. `scripts/far_weekly_gold_read.py` doesn't change; only the publish wrapper switches variant.

## What has to be true for this package to be executed

All of the following:

- 26-week forward window has closed cleanly
- Both v1 and v2 forward samples have at least 8 directional resolved trades (enough for the mean-difference test to have any power)
- v2 forward mean > v1 forward mean, both > 0
- No pending halt, no fraud, no data anomaly
- Farhad wants to ship

If ANY of these are false, this package sits. It doesn't ship on partial evidence.

## Files that would be modified at ship (advance list)

- `scripts/far_weekly_gold_read_publish.py` (add v2 rule as the primary path)
- `scripts/verify_north_v2_backtest.py` (new)
- `site/data/far_weekly_backtest_summary.json` (v2 numbers primary)
- `docs/launch/subscriber_faq.md` (rule description update)
- `docs/launch/north_public_intro.md` (headline update)
- `docs/launch/north_public_intro_alternates.md` (parallel updates)
- `data/experiments/registry.json` (verdict updates)
- `docs/launch/retirement_wall.md` (auto-regen)
- `docs/launch/track_record_current.md` (v1 record frozen, v2 fresh)
- `docs/development_story.md` (ship-day entry)
- Memory updates: `north_v1_factsheet.md` → mark superseded, add `north_v2_factsheet.md`

## Files that would NOT be modified at ship

- `scripts/far_weekly_gold_read.py` (backtest engine unchanged; v1 rule stays computable)
- `data/far_weekly_calls.jsonl` (append-only history, no rewrite)
- Any historical shadow logs
- Any prior experiment docs (frozen record)
- Rook's or Vega's site code (route through them)

## Package status

DRAFT ready. Not to be executed before 2027-01-22 at earliest. Not to be executed even then if any pre-flight checklist item fails.

Farhad decides ship or no-ship. This document is a plan, not a commitment.
