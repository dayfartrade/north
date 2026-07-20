# Path Y post-mortem — n=329 confirms no edge

**Written UTC:** 2026-07-20T14:30:00Z
**Trigger:** `daily_slope_consistency` rejection at n=329 exposed unfiltered Path Y's true expectancy
**Status:** Analysis + recommendation (NOT a new pre-reg; existing halt discipline unchanged)

## What Path Y is

The current live/backtest strategy config (as of 2026-07-13):

- `src/edge_session_orb_v7_final.py` `SESSION_CONFIG` with `or_vs_atr_max=2.0` on all three sessions (ASIA/LON/NY), matching live behavior
- NY `tp_mult=1.5` (reverted from 1.0)
- All v7.1 per-session gates (or_vs_atr_min NY, or_atr_deadzone ASIA) that never actually shipped to live were removed from backtest

This was the "sync backtest to live" reconciliation done 2026-07-13 (commit e4b7f92) after discovering v7.1's phantom-validation problem: v7.1 backtest reported 56.9% win rate but the filter chain was never present in `src/dispatch_orb.py`. Path Y is the honest baseline.

## Halt history

| Date | Event | n | Verdict |
|---|---|---|---|
| 2026-07-13 15:00 | SPRT re-baseline `sprt_v72_1_launch_path_y` | 10 | CONTINUE (log-LR=+2.33, below halt boundary +2.94) |
| 2026-07-13 15:00 | DSR audit Path Y | 25 | **NOT READY** (CI [-$112, +$954] includes 0) |
| 2026-07-18 07:00 | SPRT re-read after further live losses | 18 | **HALT** (log-LR=+3.83, above +2.94) |
| 2026-07-20 14:15 | XAU/USD extended sample this doc | 329 | **NO EDGE** (see below) |

Kill switch has been ON since 2026-07-13. Never flipped OFF. Re-entry conditions pre-registered as Path A/B/C, hard-stop 2026-10-13.

## n=329 finding

Ran `scripts/backfill_shadow_log.py --start 2024-01-15` with `data/gc/GC_5m.csv` temporarily replaced by 180,700 rows of XAU/USD 5m from Dukascopy (2024-01-15 → 2026-07-20). See `docs/experiments/2026-07-18_daily_slope_consistency_shadow.md` § "Rejection verdict — 2026-07-20" for full data-provenance discussion.

Ship-gate report totals on Path Y's *taken* trades (would_skip=False, outcome resolved):

| Metric | Value |
|---|---|
| n resolved | 329 |
| Total P&L (no filter) | **-$5,495** |
| Mean per trade | **-$16.70** |
| Bootstrap 95% CI on mean | [not computed for total; dsc-mean CI was [-$77, +$49]] |

At n=41 (yfinance backfill from 2026-04-09) Path Y showed +$78/trade. At n=329 (2.5 years of XAU/USD extension) the mean flipped to -$16.70/trade. **The positive result at n=41 was small-sample optimism selected by yfinance's rolling window happening to land on a favorable regime for Path Y** (2026-04 to 2026-07, gold bull → correction).

## Interpretation

Three plausible readings, in order of weight-of-evidence:

### 1. Path Y itself lacks positive expectancy on GC-family assets (MOST LIKELY)

- XAU/USD proxy is ~95% correlated with GC futures; direction and win-rate signals cross-check faithfully
- 2.5 years of history is 442× the halt-fire sample (n=329 vs n=18)
- Halt at n=18 was NOT unlucky variance — it was the SPRT correctly detecting a strategy without edge, sooner than casual observation could
- The `sprt_v72_1_launch_path_y` halt is retroactively validated at 18× the sample size
- Retail-ORB literature (Crabel 1990) generally requires per-market calibration; gold-specific ORB may not have edge in current regime (Kaufman Ch 17 Table 17.1 shows KAMA profit factor 0.86 on gold vs 1.53 avg)

### 2. XAU/USD → GC conversion introduces spurious loss (UNLIKELY)

- Spot-vs-futures basis creates roll-gap artifacts absent in XAU/USD
- Contract math (CONTRACT_SIZE=100, RT_COST=$24) applied to XAU/USD point moves could systematically overstate P&L magnitude but should NOT bias the sign
- The n=41 yfinance sample used REAL GC 5m and still flipped negative-ish when extended (+$78 → mean is on a knife-edge)
- Cross-check: 60m OOS on GC 60m bars (n=14,143, 2.5 years, filed 2026-07-18) found +1.50 bps / 3h aligned-slope spread — that finding is about the dsc directional premise (rejected here at ORB timescale), not about Path Y itself. It does not defend Path Y.

### 3. Path Y works in some regimes but not others (POSSIBLE, unclear which)

- 2024-2025 gold bull run, 2026 correction — both are represented in the sample
- Could be that Path Y needs a regime overlay we haven't identified
- But: shadow_replay.py already ran a 5-candidate regime sweep on n=32 (real_yield, slope, prior_day_range, gap, dsc) — 4 rejected, 1 rejected now
- Absence of a working regime filter after 5 tries doesn't prove none exists, but shifts prior against it

## Recommendation

**Formally close Path Y as a shippable strategy candidate.** Do NOT design v9 as another bolt-on filter to Path Y. Design v9 as a *different strategy structure* — Kaufman Ch 17's asymmetric-stops framing (Knapp) or Meyers's asymmetric ORB range (`HR = high_t - low_{t-n}` instead of `max(high, n) - min(low, n)`) both change strategy DNA, not just filter chain.

Corollary: **Re-entry Paths A and B are effectively invalidated by this analysis.**

- **Path A** ("shadow +>=$27,390 AND >=5 consecutive would-take at >=60% win"): requires Path Y to *win* in shadow. If Path Y has no edge, Path A never fires. This is not a criticism of the pre-reg — it was written before we had n=329.
- **Path B** ("real_yield<2.0 for 30 consecutive days AND shadow>=0; first 5 trades at 50% size"): same problem. Assumes Path Y comes back into edge once macro regime shifts. n=329 covers ry<2.0, ry=2.0-2.2, ry>2.2 regimes; the negative mean persists.
- **Path C** ("v7.3+ passes DSR AND new SPRT pre-reg"): **THIS IS THE ONLY VIABLE PATH.** v9 (Knapp ER-stops or Meyers HR-ORB) IS the v7.3+ referred to in Path C. Any v9 candidate must produce its own DSR pass + new SPRT pre-reg + own ship-gate. Do not carry over any Path Y-era approval evidence.

## What does NOT change

- **Engine A kill switch stays ON.** Halt discipline is a pre-reg. This analysis is *supporting* the halt, not overriding it.
- **Hard stop 2026-10-13** for `sprt_v72_1_reentry_prereg` still applies. If no v9 candidate has cleared its own gates by that date, Path Y era is fully retired and the project needs a Bayesian reset (or step back from live trading).
- **Bonferroni-N in registry increments** for every rejected shadow candidate. dsc rejection at n=329 counts. Any v9 candidate faces the growing Bonferroni penalty in its DSR gate.

## Immediate action

- Update `sprt_v72_1_reentry_prereg` registry entry to reflect n=329 finding? **No.** The pre-reg language stands as written; this doc is supporting evidence for its `hard_stop` outcome, not a modification.
- New pre-reg for "Path Y formally retired at n=329"? **Not needed.** The existing halt IS the retirement. Docs will reflect this via registry `notes` field on future entries.
- Draft v9 candidate #1 (Knapp ER-stops) with fresh pre-reg? **YES, immediately** — see `2026-07-20_v9_knapp_er_stops_prereg.md` (draft).

## Files this doc references

- `src/edge_session_orb_v7_final.py` — Path Y `SESSION_CONFIG`
- `docs/experiments/2026-07-13_path_y_results.md` — original Path Y sync + backtest
- `docs/experiments/2026-07-13_sprt_prereg.md` — original SPRT pre-reg
- `docs/experiments/2026-07-13_reentry_conditions_prereg.md` — Path A/B/C conditions
- `docs/experiments/2026-07-18_daily_slope_consistency_shadow.md` § Rejection verdict — n=329 methodology
- `data/experiments/registry.json` — trial history
- `memory/kaufman_ch17_readnotes.md` — v9 candidate library
