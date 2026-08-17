# site/archive - staged HTML design variants (not deployed)

These six HTML files were built during the 2026-07-31 design phase but not
deployed. As of 2026-08-17, the launch decision is Telegram-only. The
website will be activated later when Farhad is satisfied with live
Telegram results. Activation runbook: `docs/launch/website_activation.md`.

Why kept: `weekly_v3.html` has the Full/Compact toggle that will eventually
replace the currently-tracked `site/weekly.html`. It just needs to be wired
to the live JSON data pipeline (`site/data/*.json`, already auto-updated by
the weekly-publish workflow). The other five files are supporting layout /
landing designs from the same round.

## What's here

- `launch_preview.html` - first-cut of the launch landing page
- `soft_launch.html` - soft-launch landing variant
- `vision.html` - long-form "what NORTH is" page
- `weekly_v2_a.html` - weekly card layout variant A
- `weekly_v2_b.html` - weekly card layout variant B
- `weekly_v3.html` - weekly card layout, further iteration

## Status: staged, not deployed

The site data pipeline (`site/data/*.json`) refreshes every Sunday whether or
not the site is deployed. When you activate (per website_activation.md), the
JSON files already have historical data. Activation is a one-day job, not a
rebuild.
