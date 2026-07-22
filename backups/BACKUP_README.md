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

Latest backup is authoritative for restoring session state.
Data archive (`dukascopy_data_*`) hasn't changed since the first backup
(source data files were fetched only once).
