# NORTH site audit - one week after go-live

**Date:** 2026-08-31
**Author:** Knox
**Status:** Observational audit. No changes made to the site (built and operated by website AI in shared workspace).
**Scope:** Live URL `https://www.faractionradar.com/north`, data pipeline that feeds it, and the surrounding workflows.

## Deployment situation

- **Live URL:** `https://www.faractionradar.com/north` (Next.js, Cloudflare-fronted). Returns 200.
- **`readnorth.com`:** parked at HugeDomains, not the live site.
- **`dayfartrade.github.io/north/`:** 404. GitHub Pages is NOT configured on the north repo (Pages API returns 404). The launch runbook's "Option 1" was never executed; deployment landed on the existing FAR domain (runbook's "Option 2") instead.
- **Search visibility:** page ships with `<meta name="robots" content="noindex, follow">`. Correct for soft-launch.

## What's rendering (from live SSR HTML, 2026-08-31 12:00 UTC)

Working sections:

- Weekly call card: direction (FLAT), spot $4,450, week AUG 31 → SEP 4, "Updated 13h ago"
- Signal breakdown with week-over-week deltas: M20 +10.06% (▼ -3.59% wk), M60 +2.85% (▲ +1.43% wk), MA10>MA40 (unchanged), RY 0 bps (▲ +2 bps wk)
- 4-of-4 conditions meter with hint text ("LEAN BULL 3/4 bull · needs 1 more bull")
- Recent calls timeline: 5 items, showing net % for resolved (AUG 24 LONG -3.30%, JUL 27 SHORT -0.72%)
- Daily read panel with empty-state copy ("No active position this week. Daily reads run only when a directional call is open. Next check-in Sunday 22:00 UTC.")
- Thesis + Primary risk widgets (both wired to the `primary_risk` field we ship)
- Track record footer (since JUL 22, resolved 2, 0W-2L, cum return -4.03%)
- Legal disclaimer

Nav bar routes that 404 today:

- `/live-read` (real 404; may be intentional section header, TBD)
- `/compass` (dropdown parent; probably intentional, dropdowns don't need a landing)

**Correction to earlier audit note:** the original probe list here used the wrong paths. `/methodology`, `/blog`, and `/track-record/archive` all render 200. The "Ledger Archive" nav item links to `/track-record/archive` (engine-chooser page), not `/ledger/archive`. Retirement wall lives at `/north/retirement-wall` as a peer of the live track record, not under the `/ledger` namespace. The nav is more populated than I initially claimed.

Content from the launch-kit vision that is not on the site yet:

- Retirement wall (34 rejected / 52 tested)
- 16-year backtest equity curve chart (NORTH vs buy-and-hold gold)
- Backtest headline metrics (55.9% WR, +0.23%/trade, Sharpe 0.77, $56K max DD)
- "How the signal works" static explainer (FAQ verbatim)
- RSS feed link, Telegram subscribe link
- v2 / ensemble shadow companion signals (was pending user sign-off anyway)

Style compliance:

- No em-dashes visible in rendered text. Uses `·` interpunct, arrow glyphs, and `│` box-drawing.
- Tone and terse phrasing match the "Bloomberg-ish financial dashboard" brief.

## Data pipeline health

Workflows on `dayfartrade/north` over last 7 days:

- Failed runs in last 50: 2 (both stale: 2026-08-17 data-refresh, 2026-08-03 gold-basis shadow). No failures in the last 7 days.
- Every weekly-publish, daily-brief, data-refresh, and shadow-log run since the site went live has completed with `success`.
- Backup job (`backup: snapshot NORTH calls to Telegram DM + GitHub Release weekly`) is running.

Site JSON files are current:

- `site/data/far_weekly_current.json` - FLAT for 2026-08-31 → 09-04, `published_utc` 2026-08-30 22:05, includes `primary_risk` object ✓
- `site/data/far_weekly_history.json` - 5 entries, matches calls log ✓
- `site/data/far_weekly_price_series.json` - 60 bytes, `{"week_of":"2026-08-31","week_end":"2026-09-04","series":[]}` (empty is correct for FLAT weeks) ✓
- `site/data/far_daily_briefs.json` - `[]` (correct: no directional call this week) ✓
- `site/data/registry.json` - 52 entries ✓
- `site/api/latest.json`, `site/api/calls.json`, `site/feed.xml` - all fresh ✓

Data leak / branding drift:

- `site/data/far_weekly_history.json` still has `"product_name": "FAR Weekly Gold Read"` at the top level. Rook is not consuming that field (the site shows "NORTH" everywhere), but it's a mild data-model inconsistency that will confuse if we ever expose the raw JSON. Non-blocking.

## What went well

1. **Zero data-pipeline incidents** in the live week. Every scheduled run succeeded.
2. **The 08-30 Sunday publish executed cleanly** (the 08-23 git-push bug from prior session did not recur).
3. **The site correctly rendered a directional loss** (AUG 24 LONG -3.30%) without needing UI changes.
4. **FLAT-week UX is graceful.** The daily-read panel and thesis widget both have appropriate empty-state copy.
5. **"NO TRADABLE EDGE / STANDING DOWN" headline** on FLAT weeks is a nice, honest framing. Not defensive.

## What to raise with the website AI (ping Rook, do NOT edit directly)

Priority order:

1. **Track-record completeness.** The site shows W/L record and cum return, but omits the 16-year backtest context (55.9% WR, Sharpe 0.77, $56K max DD, 13/17 positive years). A first-time visitor cannot calibrate whether 0-2 is normal (it is: about 19.4% of two-trade sequences from a 55.9% WR strategy come out 0-2 - not exotic). Adding a "vs 16-yr backtest" strip next to the live W/L would land the honesty framing without changing our data emit.
2. **Backtest equity curve.** `site/data/far_weekly_backtest_curve.json` already exists and is static. Chart it.
3. **Retirement wall.** `docs/launch/retirement_wall.md` and `site/data/registry.json` both auto-regen. Wire the ledger route to render one of them.
4. **Nav 404s.** Mostly a non-issue after re-probing. Only `/live-read` remains as a real 404 (may be intentional). See correction note above.
5. **Consider making a page dedicated to the current week's Daily Read history** so subscribers can see the LONG week's daily briefs even after the trade is resolved. Right now the daily briefs are only visible on Telegram; the site drops them at week close.

## What I explicitly did NOT do

- Did not edit any site HTML/JS/CSS. Deferring to website AI on the surface.
- Did not push branding-drift fix (`product_name` in history JSON). Cosmetic and cross-workspace.
- Did not enable GitHub Pages. Current FAR-domain deployment is fine and was Farhad's call.
- Did not modify launch kit docs.

## Files touched

- Audit: `docs/experiments/2026-08-31_site_liveweek_audit.md` (this file)
