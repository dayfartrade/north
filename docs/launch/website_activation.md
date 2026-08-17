# Website activation runbook

*How to flip the switch and turn on the NORTH website when Farhad is satisfied with Telegram-only results.*
*Estimated activation time: 1-2 hours once you decide to do it.*

---

## Current state (2026-08-17)

The website infrastructure is BUILT and LIVE-UPDATING but NOT DEPLOYED.

- `site/weekly.html` + `site/weekly.js` - data-driven weekly page. Fetches from `site/data/far_weekly_current.json` and `far_weekly_history.json`. Already updates automatically on every Sunday publish via `.github/workflows/weekly-publish.yml`.
- `site/index.html`, `research.html`, `feed.xml` - supporting pages, tracked and versioned.
- `site/data/*.json` - the live data pipeline. 5 files, all refresh on Sunday publish.
- `site/archive/weekly_v3.html` - future upgrade with Full/Compact toggle (design only, needs data wiring).

The data pipeline runs every Sunday whether or not the site is deployed. When you activate, all historical calls since the pipeline started are already in the JSON files.

## Activation - three deployment options

### Option 1: GitHub Pages (fastest, free, recommended for soft-launch site)

**Steps:**
1. Go to `github.com/dayfartrade/north/settings/pages`.
2. Under "Source" pick "Deploy from a branch".
3. Branch: `main`. Folder: `/site`.
4. Save. Wait ~1 min for build.
5. Your site is live at `https://dayfartrade.github.io/north/weekly.html`.
6. Update the NORTH Telegram intro pinned message to include the new URL.
7. Optional: buy a domain like `north.trade` or `readnorth.com` and point it at GitHub Pages via CNAME.

**Cost:** free (GitHub Pages). Domain costs $10-15/year if you buy one.

### Option 2: faractionradar.com/north (existing FAR domain)

**Steps:**
1. Copy the contents of `site/` into the FAR site's `/north` subdirectory on the FAR hosting.
2. Update the FAR site's build/deploy pipeline to include the NORTH pages.
3. Set up automated sync from this repo to the FAR site (either a GitHub Action that pushes to FAR, or a git submodule).
4. Test at `faractionradar.com/north/weekly`.

**Cost:** zero incremental (FAR already hosted). Complexity: medium - depends on how FAR is deployed.

### Option 3: dedicated NORTH domain

Buy `readnorth.com`, `northsignal.com`, or similar. Deploy `site/` there via Cloudflare Pages, Netlify, or Vercel (all free tiers work).

**Cost:** $10-15/year for domain, free hosting. Complexity: low if you have a preferred host.

## After activation - Telegram integration

Once the site is live, update these to link to it:

1. `docs/launch/north_public_intro.md` - change the retirement wall / track record links from GitHub blob URLs to the deployed site URLs.
2. `docs/launch/subscriber_faq.md` - same URL updates.
3. Optional: add a "See full history" link to the bottom of every weekly Telegram post. Small footer change in `scripts/far_weekly_gold_read_publish.py`.

## Enhancements to schedule after activation

Not urgent, but worth doing in the first month post-activation:

- **Wire v3 toggle to live data.** The design at `site/archive/weekly_v3.html` has the Full/Compact toggle already implemented in CSS/JS. It just needs the data-fetch code from `weekly.js`. Merge those together and replace `weekly.html`.
- **Retirement wall page.** Currently `docs/launch/retirement_wall.md` renders on GitHub as Markdown. Would look much better as a proper HTML page with search/filter. Data source is `data/experiments/registry.json`.
- **Knox monthly market read.** New page or blog post surface. Currently the template is at `docs/launch/knox_market_read_template.md`.
- **Chart of live track record vs backtest.** Overlay live P&L on the 16-year backtest curve. Data is already in `site/data/far_weekly_backtest_curve.json`.

## Trigger criteria - when to actually activate

Farhad's call, but reasonable gates:

- At least 4-8 weeks of live Telegram publishing without incident
- At least 2-3 resolved directional calls (so the track record page has something to show)
- Invite-list feedback positive on the Telegram experience
- No pending kill switches or halts

## What NOT to do at activation

- Do not deploy the archived `soft_launch.html`, `vision.html`, `launch_preview.html` as pages. They're stale designs from earlier iterations. Only `weekly.html` and `index.html` should be live surfaces initially.
- Do not put the site URL in the intro Telegram message before the site actually deploys. Broken links are worse than no links.
- Do not switch to the v3 toggle design until it is wired to live data. Static values on a page dated "Sample" is embarrassing.
