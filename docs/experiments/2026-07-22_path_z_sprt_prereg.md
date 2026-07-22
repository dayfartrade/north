# Path Z SPRT halt parameters — pre-registration

**Registered UTC:** 2026-07-22T09:00:00Z
**Owner:** Farhad
**Trial id:** `sprt_path_z_live`
**Depends on:** `2026-07-20_path_z_ny_short_prereg.md` (Path Z filter itself)
**Applies to:** `scripts/halt_monitor.py` when Path Z transitions from shadow to live capital
**Status:** PRE-REGISTERED, dormant until first Path Z live trade

## Rationale

Path Z pre-reg ship-gate #6 explicitly requires:

> **Path Z-specific SPRT pre-reg** before first live capital — cannot inherit `sprt_v72_1_launch_path_y`; requires fresh pre-reg with Path Z-specific H0/H1

This doc satisfies that gate. Registered NOW (well before shipping) so parameters cannot be hindsight-fit to future live data — the same discipline principle that killed `real_yield_gt_2_2` and forced the original `sprt_v72_1_launch` framework.

Path Z is currently 100% shadow-only. Zero live trades exist. This SPRT will begin evaluating at trade #1 live and will freeze on the first boundary crossing per SPRT semantics (no re-running with different parameters mid-window).

## Parameters

- **H0 (Path Z works):** p = 0.541 — the in-sample WR observed on n=85 Path Z-taken trades (Dukascopy XAU/USD 2024-2026). This is the strategy's "as-designed" hit rate.
- **H1 (Path Z broken):** p = 0.35 — a "meaningfully broken" threshold, well below random-ORB baseline (~40-45%). Chosen as a natural "clearly not working" watermark; NOT the eventual observed live rate (which would be circular).
- **Type I error (alpha):** 0.05 — 5% chance of halting a working Path Z.
- **Type II error (beta):** 0.05 — 5% chance of continuing a broken Path Z.

## SPRT boundaries

- **Halt (accept H1):** log-LR ≥ ln((1-beta)/alpha) = ln(19) = **+2.9444**
- **Safe (accept H0):** log-LR ≤ ln(beta/(1-alpha)) = ln(1/19) = **-2.9444**
- **Continue sampling:** -2.9444 < log-LR < +2.9444

## Per-trade log-LR

- **Win:** log(p1/p0) = log(0.35/0.541) = **-0.4355**
- **Loss:** log((1-p1)/(1-p0)) = log(0.65/0.459) = **+0.3479**

## Reference decision points (pure-run scenarios)

- **Halt** after ~8.5 consecutive losses starting from log-LR = 0 (`⌈2.944 / 0.3479⌉ = 9 losses`)
- **Safe** after ~6.8 consecutive wins (`⌈2.944 / 0.4355⌉ = 7 wins`)
- Mixed sequences resolve slower

Note: n≈7-9 pure-run trades to boundary. In practice mixed sequences take 12-30 trades to fire.

## Comparison to `sprt_v72_1_launch`

| Parameter | v7.2.1 Path Y (retired) | Path Z |
|-----------|------------------------|--------|
| p0 (works) | 0.57 | 0.541 |
| p1 (broken) | 0.35 | 0.35 |
| alpha | 0.05 | 0.05 |
| beta | 0.05 | 0.05 |
| Halt boundary | +2.9444 | +2.9444 |
| Per-win LR | -0.488 | -0.4355 |
| Per-loss LR | +0.413 | +0.3479 |

Path Z has a lower p0 (54% vs 57%) reflecting its slightly lower in-sample WR. This makes wins accumulate SPRT "safe" credit slower and losses fire "halt" slower than the Path Y SPRT — more conservative in both directions, appropriate for a smaller-sample-derived candidate.

## Sample window

- **Starts:** first Path Z live trade after promotion (currently n=0; require_path_z=False in all live configs).
- **Ends:** whenever SPRT crosses a boundary OR Path Z hits the 2026-10-13 hard-stop from `sprt_v72_1_reentry_prereg` (Path C ship deadline).
- **Frozen:** if SPRT has not fired by 2026-10-13 hard-stop → Path Z REJECTED regardless of intermediate log-LR. Aligns with Path Z pre-reg rejection gate #5.

## Interpretation rules

1. **On SPRT_HALT during live Path Z trading:** private alert fires. Path Z live trading halted. Reverts to shadow-only. `data/halt_state.json` updated. Engine A remains halted (Path C revert).
2. **On SPRT_SAFE during live Path Z trading:** SPRT test complete for THIS hypothesis pair. Path Z continues at full ramp (100% size). Any future SPRT re-registration requires fresh parameters + new sample window.
3. **On SPRT_CONTINUE:** keep sampling. Verdict revisited each new live Path Z trade.
4. **Once verdict fires, this SPRT is frozen.** Restart requires a new pre-registration.

## Interaction with Path Z first-trade ramp

Per Path Z pre-reg § "Interaction with Engine A halt":
- First 5 live Path Z trades sized at **50% nominal** (Path B ramp discipline)
- Full 100% size only after Path Z-specific SPRT clears SAFE boundary at n ≥ 5 clean live trades

This SPRT is the "SAFE at n ≥ 5" gate for ramp-up. Combined interpretation:
- SPRT_SAFE at n < 5: cannot claim ramp-up yet; wait for at least 5 trades
- SPRT_SAFE at n ≥ 5: OK to size to 100%
- SPRT_HALT at any n during 50% or 100%: full halt, revert to shadow

## Why not use mean/trade instead of WR?

Path Z has a fat-tail P&L distribution (top-10 in-sample = 103% of P&L per `scripts/path_z_robustness.py`). Mean/trade would be a more informative test statistic in principle. However:

1. Prior SPRT infrastructure (`halt_monitor.py`) is WR-based (Bernoulli). Reusing it avoids new code paths that would need their own validation.
2. WR is stationary in a way mean isn't — extreme trades don't distort SPRT verdict, they just slow safe-boundary approach.
3. Mean-based SPRT requires distributional assumptions (t-test / bootstrap-adjusted) that are harder to pre-register cleanly.

The trade-off: SPRT_HALT could fire on a genuinely-working Path Z that happens to have a losing streak within a fat-tail regime. Accepted as a conservative bias — halting a working strategy costs less than continuing a broken one.

## Escalation

**If SPRT_HALT fires:**
1. Halt Path Z live (no new positions).
2. Continue shadow mode.
3. Track shadow-equity vs live at halt point for 30 days.
4. If shadow-equity recovers to new peak within 30 days: halt was correct (regime); do not re-enter until fresh SPRT pre-reg + new sample window.
5. If shadow-equity continues bleeding: Path Z edge is dead; retire candidate; return to Path C search.

**If user overrides SPRT_HALT:**
1. Document override rationale in registry.
2. Set explicit max additional-DD before user commits to halt.
3. Reset SPRT with new pre-reg after 5 more live trades.

## Registration in registry

Added to `data/experiments/registry.json` as `sprt_path_z_live` trial entry with these parameters. Verdict: `pre_registered`. Bonferroni-N incremented.

## Files that reference this pre-reg

- `docs/experiments/2026-07-20_path_z_ny_short_prereg.md` (ship-gate #6 satisfied by this doc)
- `data/experiments/registry.json` (new trial `sprt_path_z_live`)
- Future: `scripts/halt_monitor.py` (Path-Z-aware SPRT branch to be added when promoted to live)

## Confidence in pre-reg design

The parameters are conservative variants of the well-tested `sprt_v72_1_launch` framework. Only p0 is Path Z-specific; p1 and error rates carry over. This means:
- Low risk of design bug (heavily validated framework)
- Appropriate calibration to Path Z's slightly lower in-sample WR
- Registered before any live capital deployed → cannot be accused of hindsight-fitting
- Frozen sample window semantics prevent hypothesis fishing
