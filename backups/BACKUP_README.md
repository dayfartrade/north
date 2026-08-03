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

---

## 2026-07-31 session snapshot

**File:** `session_20260731T134800Z_full_snapshot.tar.gz` (48 KB)

**Contains:**
- `memory/` = all 21 memory files post deep-audit clean state
- `site/` = 6 HTML mockups built today (weekly_v3, v2_a, v2_b, launch_preview, vision, soft_launch)
- `docs/development_story.md` = living Knox narrative
- `MANIFEST.md` = full description of what changed today

**What today accomplished:**
- Memory cleanup 76 -> 21 files, removed all book-framework worship
- Product renamed to NORTH (hosted on FAR site)
- Behavioral overrides created (7 rules against rigid/lazy/sycophantic drift)
- NORTH v1 factsheet cleaned of "cannot modify shipped" language
- Decision: refine NORTH to v2 using thesis + Bollinger Band S/R (not Monday-Friday)
- Janus collaboration opened for funding-based signal transplant to gold
- 3 intermediate memory backup snapshots created during the day

**Also preserved as loose folders (not tar-compressed):**
- `memory_20260731T134317Z_post_second_audit/`
- `memory_20260731T134644Z_deep_sweep_final/`
- `session_20260731T134800Z_full_snapshot/`

If disk space matters later, the tar.gz is the durable version. Delete the loose folders.

---

## 2026-07-31 evening addition: Janus transplant package

Not backed up as a separate archive because it lives at `research/janus_2026_07_31/` which is inside the working tree and version-controllable.

**Contents (18 files, ~192 KB):**
- Janus's `README.md`, `MANIFEST.md`, `FOLLOWUP_ANSWERS.md`
- `code/` = 6 Python files (~1500 lines): funding_extreme_revert.py, cost_model.py, perf_bootstrap.py, analysis_helpers.py, level_picker.py, types.py
- `pre_reg_examples/` = 3 real pre-reg docs
- `verdict_examples/` = 3 real verdict docs
- `analysis_scripts/` = 3 read-only analytics scripts

**Plus Knox's `INDEX.md` mapping the material to NORTH work.**

Memory pointer at `ref_janus_transplant_package.md`. Dev story updated with the evening addition entry.

Source directory (original Janus delivery) stays at `C:\Users\farha\OneDrive\Desktop\info\` for reference.

---

## 2026-07-31 late evening: Phase 2 partial snapshot

**File:** `session_20260731T150220Z_phase2_partial.tar.gz` (148 KB)

**What's inside (75 files):**
- memory/ = 22 memory files (unchanged since afternoon)
- site/ = 6 HTML mockups (unchanged since afternoon)
- docs/development_story.md = extended with Phase 2 findings
- docs/experiments/ = 2 design docs from Phase 1
- research/tools/ = 5 Python tools + README (backtest.py updated to add market_next_open entry type)
- scripts/ = 3 new backtest scripts (north_backtest, silver_candidate_gsr, silver_candidate_native)

**Findings preserved:**
- NORTH v2 with BB execution DOES NOT beat calibrated NORTH v1. v2 rejected.
- Silver GSR z-score reversion: 27 configs tested, all INDIST. lookback=180 pattern filed as future work.
- Silver native momentum + oil: clear FAIL (-$85k, 1/9 positive years).
- NORTH v1 stands as-is.

**Still open:**
- Silver Candidate 3 (volatility regime) not tested yet
- Site deployment situation
- 12-month retirement criterion needs user decision
- Gold lease rate data availability (Janus track)

**Session backups today (3 total):**
- `session_20260731T134800Z_full_snapshot.tar.gz` (initial state)
- `session_20260731T143213Z_phase1_complete.tar.gz` (tools + designs)
- `session_20260731T150220Z_phase2_partial.tar.gz` (this one)

---

## 2026-07-31 FINAL WRAP snapshot

**File:** `session_20260731T${TS}_final_wrap.tar.gz`

Final snapshot of the day. Includes next session agenda file.

**New vs Phase 2 partial:**
- memory/next_session_agenda.md (queued work for next session)
- memory/product_focus_and_structure.md (weekly + daily structure + focus directive)
- MEMORY.md index updated

**Session backups today (4 total):**
1. session_20260731T134800Z_full_snapshot.tar.gz
2. session_20260731T143213Z_phase1_complete.tar.gz
3. session_20260731T150220Z_phase2_partial.tar.gz
4. session_20260731T${TS}_final_wrap.tar.gz (this one)

---

## 2026-08-03 NORTH MIGRATION snapshot

**Dir:** `session_20260803T125929Z_north_migration/`  (747K uncompressed)

Contents:
- `memory/` — full Claude memory dump (includes new `ref_github_north.md` + updated `next_session_agenda.md`)
- `docs/development_story.md` — session narrative added (silver rejection, gold basis LONG-only OOS candidate, GitHub migration)
- `docs/experiments/` — full experiments folder
- `data/` — far_weekly_calls.jsonl (with 07-27 resolve + 08-10 SHORT), registry.json (49 trials, +4 today)
- `site_data/` — updated current + history JSONs
- `scripts/` — new: gold_basis_shadow_log.py, gold_basis_janus_transplant.py, gold_basis_long_only_oos.py, silver_candidate_vol_regime.py, silver_gsr_oos_revisit.py; edited: far_weekly_gold_read_publish.py, far_weekly_telegram.py
- `workflows/` — new: data-refresh.yml, weekly-publish.yml, shadow-log.yml (all live and verified on GitHub Actions)
- `requirements.txt`

**What changed this session:**
- Silver Candidate 3 REJECTED; silver research complete this round
- Gold basis Janus transplant tested; baseline REJECTED, LONG-only OOS profile very strong but underpowered (n=54, mean R +0.25, 78% positive years)
- Silver GSR fresh OOS revisit: same profile as gold basis (n=131, mean R +0.11, 78% positive years, underpowered)
- Diagnosed VPS pipeline dead (rebuilt without notice around 2026-07-22)
- Migrated the entire scheduled pipeline off Hetzner VPS onto GitHub Actions on dedicated dayfartrade/north repo (old far-reach repo deleted after verification)
- Elevated Telegram card design; added new performance snapshot card
- Fixed a data-format bug that emitted a broken FLAT card to subscribers; posted correction
- All 3 workflows live and verified end-to-end

**Still open:**
- Silver GSR shadow log (parallel to gold basis) — priority for next session
- Daily brief content (3-part bundle)
- Wire faractionradar.com to a real page
- Failure notifications on workflow failures
- Untracked in repo: `backups/session_*` dirs, `research material/` books, `.telegram`, `.github-token` (all correctly gitignored)
