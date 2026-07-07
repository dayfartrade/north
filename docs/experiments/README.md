# Pre-registered experiments

Per our discipline model (installed 2026-07-07 after Janus's multi-hypothesis
critique): every experiment that could change strategy behavior gets a
markdown file HERE, with the decision rule LOCKED before any data is looked
at.

## Files

- `TEMPLATE.md` — copy this for a new experiment
- `YYYY-MM-DD_<name>.md` — one per experiment, dated by registration UTC
- `README.md` — this file

## Workflow

1. Create the experiment file BEFORE running any code that would produce results
2. Fill in Hypothesis / Rationale / Data / Method / Decision rule sections
3. Commit the file (`git add docs/experiments/<file>.md; git commit`)
4. Run the code
5. Fill in the Results section
6. If SHIP: create a strategy commit with a link back to this file
7. If REJECT or SHADOW-CONTINUE: keep the file as a permanent record

## Hypothesis budget

Cap: **5 live-ship experiments per calendar month.** Shadow-mode experiments
don't count against budget.

Bonferroni denominator = number of LIVE-SHIP experiments run in the current
calendar month. Adjusted α = 0.05 / N.

## Layer classification

Every experiment names the layer it would touch:

- **strategy_engine** — `run_orb_v7` body, session times, `MAJOR_NEWS` list.
  LOCKED. Quarterly refit at most. Requires n ≥ 30 shadow + written pre-reg + operator OK.
- **session_config** — per-session filter/geometry/exit dicts in `SESSION_CONFIG`.
  MEDIUM cadence. Pre-registration + optional shadow.
- **calendar_audit** — `stand_down.py` calendar entries, audit-box context functions
  (`_funding_context`, `_basis_context`, `_cot_context`, `_volume_context`).
  FAST cadence. Inspection only.

## Active experiments

- `2026-07-07_janus_q4_trailing_stop.md` — trailing stop schedule (strategy_engine)
- `2026-07-07_vol_ratio_shadow.md` — OR-window volume filter (session_config, shadow-only)
