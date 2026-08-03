# File manifest

All files in this drop, with 1-line purpose. Alphabetical within
each directory.

## Root

| File | Purpose |
|---|---|
| README.md | Start here — reading order, transplant guidance, discipline items |
| MANIFEST.md | This file |
| FOLLOWUP_ANSWERS.md | Answers to 4 follow-up questions: source ref, pre-reg template, gold-specific data/history/failure-modes, live-execution pitfalls |

## code/

The actual specialist source + math it depends on.

| File | Lines | Purpose |
|---|---|---|
| funding_extreme_revert.py | 421 | The specialist — what Knox asked for. Emits SHORT/LONG on 90d funding-rate extreme percentile with degenerate-distribution guard. |
| cost_model.py | 88 | Adjusts theoretical R for slippage + fees per side. Populates `realized_r_after_costs`. |
| perf_bootstrap.py | 224 | Bonferroni-corrected bootstrap CI. THE statistical test at every SHIP/PARK decision. |
| analysis_helpers.py | 81 | Shared pure helpers (entry-slippage bps, session bucket, percentile). |
| level_picker.py | ~600 | SL/TP geometry chooser (4H swing + order-book walls, fallback to fixed %). Imported by the specialist. |
| types.py | 88 | `SetupCandidate` dataclass — the exact contract between signal + downstream. |

## pre_reg_examples/

Real pre-registration docs showing SHIP/PARK/KILL discipline.

| File | What it demonstrates |
|---|---|
| 01_dynamic_threshold_pre_reg.md | Design-first pre-reg for a new secondary gate. Includes numeric locking, kill switch, calendar trigger. |
| 02_tier_expansion_pre_reg.md | Locked 4-criterion expansion rule; strictly all-4-must-hold. Rejected at PARK (see verdict_examples/). |
| 03_optimization_pre_reg_parked.md | Fee-optimization pre-reg locked NOW but build-gated to $2K capital. Shows the "design ready, build later" pattern. |

## verdict_examples/

Real verdict docs showing how pre-reg + backtest read produces a
locked decision. Discipline in action.

| File | Verdict class |
|---|---|
| analysis_batch_verdict.md | Comprehensive multi-analytic verdict (our most recent). Includes cost calibration + funding-paid + trade decomposition. |
| park_verdict_example.md | 4-criterion pre-reg met 3/4 → PARK locked. No re-tuning, no fishing. |
| insufficient_directional_verdict.md | Sample floor met but effect within decision-band → INSUFFICIENT-DIRECTIONAL. Continue SHADOW to next calendar trigger. |

## analysis_scripts/

Read-only analytics we run against live data to measure edge post-ship.

| File | What it measures |
|---|---|
| cost_model_calibration.py | Entry-side slippage: observed live vs modeled 5bps. Verdict MATCHES/UNDER/OVER-estimates. |
| exit_slippage_calibration.py | Same but for close side vs intended TP1/SL prices. |
| trade_decomposition.py | Per-trade breakdown sorted by drag. Aggregates by session + symbol. Identifies outlier fills. |

---

Total: ~2000 lines of source + ~50k words of pre-reg / verdict /
README material. All transplantable ideas, none of the Bitget-
specific plumbing.

If you build the gold transplant with these building blocks, I'd
genuinely like to hear how it went.

— Janus
