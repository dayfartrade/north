# Backup archive — 2026-07-22

Created after FAR Weekly Gold Read v1 ship, before continuing autonomous
research/development.

## What's inside

### `dukascopy_data_YYYYMMDD-HHMMSSZ.tar.gz` (~100 MB compressed / 441 MB raw)

Historical 5m and 1m gold/silver/oil/BTC/SPY data fetched from Dukascopy
during 2026-07-22 session. These files are gitignored (too large for git)
and can only be re-fetched by re-running the backfill scripts — worth
minutes-to-hours of VPS time.

Contents:
- `XAUUSD_5m_2010_2014.csv` (28 MB) — supplementary OOS
- `XAUUSD_5m_historical.csv` (50 MB) — 2015-2023 OOS
- `XAUUSD_5m.csv` (14 MB) — 2024-2026 live
- `XAUUSD_1m_historical.csv` (140 MB) — 2019-2023 for Path S
- `XAGUSD_5m_historical.csv` (45 MB) — silver 2010-2023
- `LIGHT.CMDUSD_5m_historical.csv` (42 MB) — WTI 2015-2023
- `BTCUSD_5m_historical.csv` (46 MB) — BTC 2015-2023
- `USA500.IDXUSD_5m_historical.csv` (42 MB) — SPY 2015-2023

### `vps_state_YYYYMMDD-HHMMSSZ.tar.gz` (~38 KB)

Live state from VPS at backup moment:
- `data/far_weekly_calls.jsonl` — call history for FAR Weekly product
- `data/shadow_equity_since_halt.jsonl` — Path Y shadow log
- `data/shadow_equity_path_z.jsonl` — Path Z in-sample log
- `data/halt_state.json` — Engine A halt state
- `data/dispatch_state.json` — dispatch state
- `data/experiments/registry.json` — Bonferroni-N registry (33 trials)

### `memory_YYYYMMDD-HHMMSSZ.tar.gz` (~80 KB)

All Claude memory files under `C:\Users\farha\.claude\projects\C--golddaytrador\memory\`.
Includes session logs, feedback notes, project state, pre-reg outcomes.

## What's NOT here (already safe elsewhere)

- **Repo state**: on GitHub `far-reach/golddaytrador` main branch — everything
  committed and pushed as of 5e4e36a (FAR Weekly execution guide).
- **VPS system state**: systemd services + timers reproducible from
  `ops/systemd/*.{service,timer}` in the repo.
- **Config**: `.env.vps` on VPS contains healthcheck UUIDs + token references
  (kept out of git; user must maintain separately).

## Restore procedure

To restore from these archives:

```bash
# Repo
git clone https://github.com/far-reach/golddaytrador.git
cd golddaytrador

# Data
tar xzf backups/dukascopy_data_*.tar.gz -C data/external/

# Live state
tar xzf backups/vps_state_*.tar.gz -C .  # extracts to data/*

# Memory (host-local, restore only if lost)
tar xzf backups/memory_*.tar.gz -C /c/Users/farha/.claude/projects/C--golddaytrador/
```

## Cadence

- Manual per-session for now
- Should automate weekly if project grows further
- GitHub is the authoritative source for code; archives are for
  gitignored data + local state

## Backup snapshots

- **20260722-095745Z** — first backup after FAR Weekly v1 ship
- **20260722-124027Z** — end-of-session backup after Telegram integration,
  RSS/API endpoints, v2 shadow tracking, meta-labeling test, GSR test,
  sensitivity analysis, seasonality scan, error handling.
  Includes `far_weekly_v2_shadow.jsonl` (v2 candidate log).
- **20260724-080510Z** — mid-session backup after A+C+D+E workstreams.
  4 rejections registered (BTC v1, WTI v1, COT extreme v1, seasonality
  v1). D-track fresh data: COT extended to 2010-2026 (863 rows, 133
  fresh 2024+), FOMC calendar (137 dates), GVZ Gold IV (4732 rows).
  E-track: v1 outcome pipeline verified. C1 pre-reg written
  (`far_weekly_gold_short_put_income_v1`, pre_registered, backtest
  pending). Registry N=40.
  New archive: `macro_data_20260724-080510Z.tar.gz` (gitignored COT
  raw + simplified + new macro CSVs already in git for redundancy).
- **20260724-115741Z** — end-of-session backup after full 10-iteration
  autonomous /loop. Total 15 commits pushed to origin (main
  faff663..21f6e58). Session output: 6 formal mechanism-family
  rejections (BTC v1, WTI v1, COT extreme v1, seasonality v1,
  short-put income v1, ML direction v1) + 2 exploratory rejections
  (COT fresh 2024+ n=7, pre-FOMC drift sign-flip). Site product
  polish: v1 vs Buy-hold card + equity chart overlay + landing
  callout + /research.html public research log (41 trials filterable)
  + pre-first-resolution empty state UX. Publisher wired to auto-sync
  registry.json to site on each dispatch. Registry N=41.
  Only shipped product remains: FAR Weekly Gold Read v1 (BETA).
  Next scheduled event: Sunday 2026-08-02 22:00 UTC first live
  outcome resolves + week 2026-08-03 call publishes.
- **20260724-142614Z** — final session close backup. 20 commits
  pushed total (main faff663..5f16d2a). Additional session output
  after 11:57 backup: codebase audit fix (session_config_hash
  TODO replaced with real sha1[:12] hash), put-spread income v1
  REJECTED (kill switch on skew -6.73), ensemble v1+v2+monthly
  PASSES all 5 gates (first pass of session; registered
  pre_registered_shadow, wired into publisher for forward log),
  Davey book pre-reg seeds filed (3 mean-reversion candidates
  for future work), soft-launch discussion memory prepped as
  next-session top priority with 9-point walkthrough agenda.
  Registry N=43. Tests: 107 passed, 3 skipped.
  Next scheduled event unchanged: Sunday 2026-08-02 22:00 UTC.
- **20260729-053550Z** — operational-sweep snapshot (2026-07-29).
  No new code changes since 20260724-142614Z (repo stable, main at
  10e3d74). Session verified: TG bot @GOLDDAYTARDER_bot alive,
  Engine A halted (correct), Knox disabled (correct), publisher
  wiring for v2+ensemble shadow on origin/main, live site
  faractionradar.com serving Next.js app (`/market-read`,
  `/track-record`, `/docs`, `/blog`). Flagged: RSS/API endpoints
  (`/feed.xml`, `/api/latest.json`) return 404 on live domain —
  script generates URLs pointing at non-existent routes
  (memory-claim mismatch with live site architecture). First
  live v1 outcome resolves Fri 2026-07-31 close; first
  ensemble/v2 shadow log fires Sun 2026-08-02 22:00 UTC.
- **20260729-062813Z** — session-close snapshot after full day.
  Includes: RSS/API URL fix (`/track-record`), Davey Seed 2
  countertrend REJECTED (auto-reject on -$8k OOS, single-trade
  -$20k on 2026 gold ATH). Registry N=44. 2 commits pushed
  (main at f18e24e → b6791fe). Reading: Davey Ch 15-19 full notes,
  Kaufman Ch 17 Adaptive Techniques (Table 17.1 confirms gold
  hostile to trend methods). Memory correction: adaptive is
  Kaufman Ch 17 not Ch 24. IBKR application rejected 2026-07-29
  (doesn't block product launch, subscribers execute on own broker).
  Next session (2026-07-30): soft-launch 9-point walkthrough
  targeting Mon 2026-08-03 announce.

Latest backup is authoritative for restoring session state.
Data archive (`dukascopy_data_*`) hasn't changed since the first backup
(source data files were fetched only once).
