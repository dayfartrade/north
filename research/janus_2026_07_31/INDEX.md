# Janus transplant package · index and mapping to our project

**Received:** 2026-07-31
**Source:** Janus, the AI operator on Farhad's bluechipsignal crypto-perpetuals project
**Purpose:** Materials to support transplanting the funding-rate extreme reversion approach from crypto perpetuals to gold, via gold lease rates as the structural analog.

---

## How this material maps to NORTH work

This is NOT ready-to-use NORTH code. It's Janus's actual production code from a different market (crypto perps) plus documentation. We adapt or extract ideas from it, we do not copy-paste into our own scripts.

## Reading priority for a new session

1. **Start with `README.md`** - Janus's own overview and reading order recommendation
2. **Then `FOLLOWUP_ANSWERS.md`** - honest answers to the 4 questions Knox asked, including specific gold data-source guidance and failure-mode predictions
3. **Then `code/funding_extreme_revert.py`** - the actual specialist source, 421 lines. This is what a gold-lease-rate transplant would take structural cues from.
4. **Then `pre_reg_examples/01_dynamic_threshold_pre_reg.md`** - the design-first pre-reg pattern (only IF we adopt any of it, and only as informed by our own project needs)

## The mechanism transplant, one paragraph

Crypto perpetual futures charge funding between long and short holders every 8 hours to keep the perp price anchored to spot. Extreme funding readings mean one side of the book is paying the other for the privilege of being crowded; historically that positioning unwinds. Janus's specialist SHORTS when funding hits its 90-day 95th percentile.

For gold, the closest structural analog is gold lease rates (GOFO or similar LBMA-published data). Same idea: extremes signal stress in the physical-vs-paper spread, which historically has been associated with positioning unwind events.

## Three invariants Janus says carry across markets

1. Per-symbol relative threshold (not global)
2. Distribution-range guard (prevents firing on flat lines)
3. Cold-start floor (require enough history for percentile to be meaningful)

## Numeric parameters that must be re-tuned for gold

- 90d lookback likely too short (Janus suggests 180-365d for gold's slower cycles)
- 95th percentile threshold needs its own backtest
- 48h expiry likely too short (Janus suggests 3-7 days on gold)
- 1R geometry depends on our invalidation model

## Discipline items Janus recommends adopting

Janus recommends their SHIP/PARK/KILL pre-registration pattern. Their framing is that this is what protects a signal from post-hoc curve-fitting pressure.

**Important**: This is another framework. Behavioral overrides apply. Do not adopt this or any part of Janus's discipline pattern as if it were physics. Evaluate it against user's goal and adopt selectively. User has not explicitly approved any Janus-derived discipline pattern yet. Ask before applying.

## Gold data source guidance from Janus

Janus does not have deep gold-data knowledge but suggests investigating:
1. LBMA website (still publishes some lease-rate indicators after 2015 GOFO discontinuation, likely needs manual scraping)
2. World Gold Council research reports
3. Kitco / Bullion Vault / Perth Mint published metrics
4. Reuters / Refinitiv / Bloomberg paid feeds
5. Nasdaq Data Link (Quandl) checks for gold-lease datasets
6. CME COMEX ancillary data (term structure implies lease rate)

**We should verify what's actually accessible before spending time.**

## What is NOT in this package (Janus flagged as intentional)

- Live trading credentials
- Bitget-specific auth, client, DB schema
- Their auto-trader router (SHORT-only crypto, unusable for gold)
- Operator-specific universe / calendar gates

## Files in this drop

See `MANIFEST.md` for the full file list with line counts.

**Code (7 files, ~1500 lines):**
- `code/funding_extreme_revert.py` - the specialist
- `code/cost_model.py` - slippage + fees math
- `code/perf_bootstrap.py` - Bonferroni-corrected bootstrap CI (statistical test)
- `code/analysis_helpers.py` - shared pure helpers
- `code/level_picker.py` - SL/TP geometry chooser (~600 lines)
- `code/types.py` - SetupCandidate dataclass

**Pre-registration doc examples (3 files):**
- `pre_reg_examples/01_dynamic_threshold_pre_reg.md`
- `pre_reg_examples/02_tier_expansion_pre_reg.md`
- `pre_reg_examples/03_optimization_pre_reg_parked.md`

**Verdict doc examples (3 files):**
- `verdict_examples/analysis_batch_verdict.md`
- `verdict_examples/park_verdict_example.md`
- `verdict_examples/insufficient_directional_verdict.md`

**Analysis scripts (3 files):**
- `analysis_scripts/trade_decomposition.py`
- `analysis_scripts/cost_model_calibration.py`
- `analysis_scripts/exit_slippage_calibration.py`

**Docs:**
- `README.md` - Janus's overview and reading path
- `MANIFEST.md` - file inventory with purposes
- `FOLLOWUP_ANSWERS.md` - answers to Knox's 4 followup questions

## Next steps for NORTH work (proposal, needs user OK)

1. Verify gold lease rate data availability (Janus suggested sources, we should test)
2. If data works, sketch a gold-lease-rate signal design informed by (not copied from) Janus's specialist
3. Run backtest with any parameters we pick, following our own project norms
4. Decide whether to ship, shelve, or evolve based on results
