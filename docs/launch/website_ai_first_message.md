# First message to send to the website AI

*Copy the block below verbatim into your website AI (v0, Cursor, Lovable, Bolt, etc). Attach the three referenced images/files.*

---

Hi. I'm building the public website for a project called **NORTH** - a
weekly gold direction call (LONG / SHORT / FLAT). The signal, code,
data, and content are all done. What I need you for is the design.

The repo is public: **https://github.com/dayfartrade/north**. Everything
I describe below lives in that repo. I want the final site deployed
to **GitHub Pages** at `dayfartrade.github.io/north/` (or a similar
route) so it updates automatically every time my Sunday cron job pushes
new call data.

## Three references I'm attaching

1. `preview_week.html` - a chronological-feed mockup my backend AI built.
   Shows every piece of content that exists across one week. Use this
   as the **content spec** (what data is available, what copy is
   final). Do NOT copy this layout.
2. `Screenshot 2026-07-31 142040.png` - an older two-column dashboard
   design from an earlier iteration. **THIS is the format I want.**
   Big directional badge on the left, a "Daily read" panel on the
   right that updates each day of the week.
3. `Screenshot 2026-07-31 142043.png` - same design in a COMPACT toggle
   view. I want both FULL and COMPACT modes.

## Data sources (what your site will fetch)

All these files live in the repo and auto-update on the Sunday cron.
Fetch them directly via the raw GitHub URL or the deployed Pages URL.

| File | What's in it | When it updates |
|---|---|---|
| `site/data/far_weekly_current.json` | THIS week's call: direction, entry, stop, ATR, signal drivers | every Sunday 22:00 UTC + on daily briefs |
| `site/data/far_weekly_history.json` | Every call ever, resolved outcomes | every Sunday + on Friday resolves |
| `site/data/far_weekly_backtest_curve.json` | 16-year backtest equity curve (date, $P&L, buy-hold comparison) | static (one-time) |
| `site/data/far_weekly_backtest_summary.json` | Backtest headline metrics: 55.9% WR, +0.23%/trade, Sharpe 0.77, $56,043 max DD, 13/17 positive years, 363 directional trades | static |
| `site/data/registry.json` | All 52 experiments run, 34 rejected with verdict + date | every Sunday |
| `site/api/latest.json` | Same as current.json (public API surface) | every Sunday |
| `site/api/calls.json` | Same as history.json (public API surface) | every Sunday |
| `site/feed.xml` | RSS feed of all calls | every Sunday |
| `docs/launch/track_record_current.md` | Rendered live track record + honesty statement | every Sunday |
| `docs/launch/retirement_wall.md` | Rendered retirement wall (34 rejects) | every Sunday |

## Update cadence (what fires when)

| When | What happens | UI impact |
|---|---|---|
| **Sunday 22:00 UTC** | New weekly call publishes: LONG, SHORT, or FLAT | Full page state changes; the Weekly call card becomes the new week |
| **Mon-Fri 12:00 UTC** (only when directional call is open) | Daily brief update | The right-hand "Daily read" panel refreshes |
| **Friday 21:00 UTC** | Position auto-resolves (stop hit or time exit) | Resolve card + track record update |
| **Sunday 23:00 UTC** | Drift monitor runs (private notifications only right now, but data available at `data/halt_state.json`) | Could power a "SYSTEM STATUS" indicator |
| **End of month** | Knox monthly market read (manual, from template) | Would need a blog/read section |

## Everything the site needs to show

Numbered so we can iterate on each independently.

### 1. Header / hero
- Title "NORTH"
- Sub-tagline: "One directional gold call per week. Published Sunday 22:00 UTC. Live-tracked, unedited. Every failed strategy documented."
- System status indicator (LIVE / HALTED) from `halt_state.json`
- Full / Compact toggle (from screenshot 2)

### 2. Weekly call card (Sunday-driven)
Fields from `far_weekly_current.json`:
- Big direction badge: LONG (green), SHORT (red), FLAT (grey)
- Week range: `week_of` → `week_end`
- Reference entry price: `entry_approx`
- Stop price: `stop_price`
- ATR (20d): `atr_20d`
- Stop distance: derived from entry/stop/ATR
- Exit rule: `exit_type` ("Fri 21:00 UTC close or stop hit")
- Signal drivers block with the four inputs from `signal_components`:
  - 4-week momentum (`M20_pct`) with ✓/✗ marker
  - 12-week momentum (`M60_pct`) with ✓/✗
  - MA10 vs MA40 (`MA10_above_MA40`) with ✓/✗
  - Real yield 20d change (`RY_chg_20d_bps`) with ✓/✗
- Shadow signals section:
  - v2 (DXY-filtered) direction from v2 shadow log
  - Ensemble (v1+v2+monthly) direction from ensemble shadow log

Context line under the title, e.g., "Signal fired: all four conditions
bullish · first directional call after three FLAT weeks." - this is
computed from the recent history (last 3 weeks).

### 3. Daily read panel (right-hand side, Mon-Fri driven)
Powered by daily brief data. Fields:
- Day header: "FRI 2026-08-28, DAY 5 OF 5"
- Health verdict badge: HEALTHY / CHOPPY / RISK
- Yesterday recap (one-line narrative - see NOTE below about narrative)
- Open P&L per contract in dollars: `pnl_pct` × entry × 100 (100 oz per contract)
- Distance to stop in dollars
- Signal health narrative
- Time to Friday close
- Event today (economic calendar - NOTE: I don't currently have this data source; can add or defer)

**Important:** the daily brief JSON isn't published to a site path yet.
Backend AI will need to add a step. For now, the daily brief data is
in `data/far_weekly_daily_brief.jsonl` (write path added by
`scripts/north_daily_brief.py`). I'll wire it to the site - just tell
me the JSON schema you want.

### 4. Live track record (always visible)
Fields, derived from `far_weekly_history.json`:
- Weeks published (count)
- Directional calls (count)
- FLAT weeks (count)
- Directional resolved (count)
- Wins / total → hit rate %
- Cumulative net return %
- Table of recent resolves: week, direction, entry, exit, net %
- Honesty disclaimer: "Small sample. Any conclusion from fewer than
  ~25 resolved directional trades is noise. 16-year backtest: 55.9%
  win rate on directional weeks, +0.23% mean return, $56,043 max
  drawdown (5.6% of a $1M account)."

### 5. Retirement wall (always visible)
Fields, derived from `registry.json`:
- "34 rejected / 52 tested"
- Table of latest 5-10 rejects with name, verdict, resolved date
- Link to full page (paginated or scroll)

### 6. Backtest equity curve (always visible)
- Chart from `far_weekly_backtest_curve.json`: yellow line = NORTH
  strategy cumulative $P&L, white dashed = buy-and-hold gold
- X-axis: 2010 → 2026
- Y-axis: cumulative $P&L
- Summary metrics from `far_weekly_backtest_summary.json`: Sharpe,
  positive years, max DD, directional trades

### 7. How the signal works (always visible)
Static explainer. Copy already written in
`docs/launch/subscriber_faq.md` under "How does the signal actually
work?" section. Use that verbatim.

### 8. Footer
- Repo link, "verify backtest" command, disclaimers, contact.

## What's in the mockup that I already have production-ready

Everything under sections 2, 4, 5, 6, 7, 8. Sunday call data lands
correctly; track record + retirement wall auto-regen; backtest curve is
static JSON.

## What's in the mockup but NOT production-ready yet

- Daily read panel content (section 3): the backend script generates
  the data but currently only ships it to Telegram, not to a site JSON.
  I'll wire this after we agree on the JSON schema you want to consume.
- "First directional call after three FLAT weeks" contextual line: need
  a small backend computation on top of `far_weekly_history.json`.

## What's in the target screenshots but NOT in my data yet

- Economic calendar / EVENT TODAY (Chicago PMI, FOMC, etc.): no data
  source wired. Options: skip it, wire via FRED, or manually curate
  weekly. Your call.
- Analysis narrative ("Momentum broken on both horizons, real yields
  rising"): currently no auto-generator. Two options: (a) I write a
  small script that takes the signal components and generates a rules-
  based sentence, or (b) Farhad writes it manually per call.
- COT positioning summary: I have raw data at `data/cot/` but haven't
  processed it for display. Can add if you want it in the Analysis
  block.
- COMPACT vs FULL toggle: this is pure UI behavior; nothing needed
  from backend.

## Design direction

Match the two target screenshots. Dark theme, financial dashboard
aesthetic (Bloomberg-ish). Big directional badge as the anchor of the
left column. Green/red for direction, muted greys for labels, monospace
for numbers.

## How I want to work with you

Iterate. Show me one section at a time as HTML+CSS. I'll evaluate,
give feedback, and we'll converge. Priority order:

1. Weekly call card (section 2) - most important, anchors the whole page
2. Daily read panel (section 3) - the right column
3. Live track record (section 4)
4. Retirement wall (section 5)
5. Header + footer + system status (sections 1, 8)
6. Backtest chart (section 6)
7. Signal explainer (section 7)

## Constraints

- Vanilla HTML + CSS + JS. No React, no build step. Fetches happen
  client-side from raw GitHub URLs (or from Pages once deployed).
- No em-dashes anywhere (Farhad's writing rule; pre-commit hook enforces).
- No stock photos, no lorem ipsum.
- All copy that will ship must be exact. No placeholders in final output.
- Mobile-first responsive.

## Kickoff

Start by acknowledging you've read everything. Then show me your first
draft of the Weekly Call card (section 2), rendered against
`far_weekly_current.json` (fetch it live from the repo). Once that
looks right, we'll do the Daily read panel next.
