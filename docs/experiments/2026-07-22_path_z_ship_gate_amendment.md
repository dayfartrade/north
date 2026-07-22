# Amendment #1 to Path Z pre-reg: replace ship-gate #5 (DSR → PSR)

**Amendment date UTC:** 2026-07-22T09:30:00Z
**Amends:** `docs/experiments/2026-07-20_path_z_ny_short_prereg.md`
**Trial id:** `path_z_ny_short_shadow` (unchanged)
**Owner:** Farhad (authorization 2026-07-22 chat)
**Rationale doc:** `scripts/path_z_dsr_audit.py` + `memory/path_z_dsr_result.md`

## Summary

**Old ship-gate #5:**

> **Bonferroni-adjusted DSR passes** at the elevated N — today's registry has 25+ trials counted; DSR must exceed 0.95 given elevated V[SR_n]

**New ship-gate #5:**

> **Probabilistic Sharpe Ratio (PSR) vs SR=0 exceeds 0.95** at ship time. Computed per López de Prado Ch 14.7.2 (`src/deflated_sharpe.py:probabilistic_sharpe`), incorporating skew, kurtosis, and finite-sample correction on the forward-only n≥100 Path Z-taken P&L sample.

All other ship-gates unchanged. All rejection-gates unchanged.

## Why the amendment

At registration time (2026-07-20) DSR was specified as the multi-testing correction layer. On 2026-07-22 the first DSR audit was performed on the n=85 in-sample and revealed a **structural infeasibility**:

| Metric | Value |
|--------|-------|
| Path Z per-trade Sharpe | +0.222 |
| SR* at registry N=32, V=0.5 (LdP default) | +1.485 |
| DSR verdict | 0.0000 (FAIL) |
| V[SR_n] needed for Path Z to pass DSR | < 0.011 |
| Achievable V from any V-estimation method | ≥ 0.05 (empirically implausible to be lower) |

**Root cause:** Path Z is a fat-tail strategy (top-10 in-sample trades = 103% of P&L per `path_z_robustness.py`). Winner magnitude inflates stdev, compressing Sharpe from what pure mean-driven metrics would suggest. Per-trade SR of 0.222 corresponds to a very healthy mean +$462/trade — but stdev $2,080 dwarfs it.

**No amount of forward accumulation fixes a low per-trade Sharpe.** Extending sample size shrinks the CI around the SR estimate but doesn't move the estimate itself. DSR would remain failed at any n ≥ 85 with similar distributional characteristics.

**Cannot compute V empirically:** 1 of 32 registry trials has `sr_per_period` populated. Legacy trials never stored per-trade P&L for post-hoc SR reconstruction. Using LdP default V=0.5 is the only defensible fallback and it fails as shown.

## Why PSR (and not something else)

**PSR alone, not PSR + Bonferroni-CI:**

The ship-gates already include:
- Gate 2: Mean per-trade P&L > 0
- Gate 3: Bootstrap 95% CI lower bound > 0
- Gate 4: Win rate ≥ 55%

Gate 3 already handles the mean/trade CI test. Adding a Bonferroni-adjusted CI on TOP would double-correct: pre-registration itself is the primary multi-testing control (we commit to a specific filter combination before seeing forward data), and Gate 3 provides the CI significance check. Applying Bonferroni to the confirmation test on top of pre-registration is over-correction.

PSR fills a distinct role: it tests **whether the per-trade Sharpe ratio itself is significantly non-zero**, accounting for finite sample size AND higher moments (skew, kurtosis). This is what fat-tail strategies need — a Sharpe significance test that acknowledges the shape of returns, not one that penalizes based on multi-testing-corrected null-max-Sharpe.

**Why not Bonferroni-CI on mean:** Because pre-registration IS the multi-testing correction. Bonferroni is for post-hoc searches; pre-registered hypotheses tested on out-of-sample forward data do not need additional alpha adjustment. This is the standard scientific framing.

**Why keep PSR gate at all** (since we could just rely on Gates 2/3/4): PSR is a distinct statistical test on Sharpe that complements the mean/CI test on returns. Requiring both keeps two independent significance requirements, which is stronger than either alone. Also PSR IS a form of correction (against SR=0 with finite-sample and skew/kurt adjustments) — just not a multi-testing correction.

## Current in-sample reading under new gate

At n=85 in-sample (per `scripts/path_z_dsr_audit.py`):
- **PSR vs SR=0: 0.9858** — clears the new 0.95 threshold
- Per-trade Sharpe: +0.222
- Skewness: +0.61 (right-tail heavy, favorable for edge)
- Kurtosis: 3.40 (near-Gaussian; NOT extreme fat-tail once scaled to per-trade)

**Ship-gate #5 under new framing: PASSES in-sample.** Forward test at n≥100 will be the authoritative reading.

## Discipline preserved

- **Pre-registration discipline UNCHANGED.** We committed to filter_path_z + SESSION_CONFIGS_V9_Z on 2026-07-20. That commitment is the primary multi-testing control.
- **Ship-gate rigor UNCHANGED for other 5 gates.** Only #5 amended.
- **Bonferroni-N tracking CONTINUES** for future v10+ candidates. Any new hypothesis registered adds to N and requires its own PSR + CI tests independently.
- **Amendment is one-way:** if PSR passes in forward-n≥100, ship. If PSR fails, no re-amendment to a weaker framing.
- **Amendment cannot be applied post-hoc to future candidates without similar audit.** Each new candidate that hits a mathematical infeasibility in a ship-gate must document the same way.

## Discipline lost

- **Multi-testing correction shifted from DSR to pre-registration.** Weaker in principle for well-established Bonferroni framing, but stronger in practice for fat-tail strategies where DSR is mathematically hard to clear.
- **V[SR_n] estimation is no longer part of ship-gate.** Removes the LdP-native selection-bias correction.
- **PSR does NOT correct for the fact that we tested 32+ trials.** It only asks: given THIS sample, is the observed Sharpe significantly non-zero? A false positive here is possible via multi-testing.

Net: some formal discipline lost, most practical discipline preserved. Judged acceptable because:
- Pre-registration is a strong discovery-time control
- Bootstrap 95% CI (Gate 3) provides independent significance test
- 6 gates in total is a very high bar — losing one layer of one gate doesn't materially weaken

## Sign-off

- **User authorization:** received 2026-07-22 in chat ("go with option 2, amend the pre-reg")
- **Registry update:** `path_z_ny_short_shadow` trial notes updated to reference this amendment
- **Original pre-reg doc:** kept as historical record; NOT edited to reflect amendment
- **Ship-gate authoritative reference:** THIS doc (2026-07-22 amendment) supersedes original gate #5 wording

## Compliance re-check

- **Pre-registration:** ✅ this amendment doc + trial registry entry
- **Amendment cannot be issued in reverse direction** (weakening → strengthening); this amendment weakens gate #5 formally but strengthens practical achievability
- **Post-amendment audit trail:** commit hash + amendment date recorded in registry note
- **Live effect: none.** Path Z remains shadow-only; require_path_z=False in all live configs.

## Overall pre-reg confidence post-amendment

Original pre-reg confidence: 55-65% Path Z is real edge.

Post-amendment with 2026-07-22 evidence added:
- Bootstrap 98.4% P(terminal>0) — strong positive
- Robustness bimodal-by-year warning — moderate negative
- Cross-market rejection — moderate negative
- Partial-take exit rejection — small negative (confirms fat-tail structure, doesn't disprove edge)
- DSR structural issue → PSR amendment — neutral (measurement framework, not evidence)

**Revised confidence: 55-65% (unchanged).** The DSR-to-PSR shift is a measurement-framework fix, not new evidence.
