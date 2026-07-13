# Path Y results — sync backtest to live-actual filter

**Executed UTC:** 2026-07-13 15:00
**Config change:** `src/edge_session_orb_v7_final.py` SESSION_CONFIG updated so ASIA and NY both use `or_vs_atr_max=2.0` (matching live default). NY `tp_mult` reverted 1.0 → 1.5 (v7.2 rationale no longer applies).

## Backtest verdict (validate_v7_phase7)

Window 2026-04-10 → 2026-07-08 (89 days):

```
FULL SAMPLE: n=25  win=13/25 (52.0%)  total=$+10,600
  mean=+$424/trade  95% CI [-$112, +$954]  sharpe(pt)=+0.31
  ASIA  n=13  win=6  (46.2%)  mean=+$309
  LON   n= 8  win=6  (75.0%)  mean=+$1,031  ← edge
  NY    n= 4  win=1  (25.0%)  mean=-$415    ← negative expectancy

TRAIN (80%): n=20  mean=+$172  CI [-$400, +$753]
HOLDOUT (20%): n=5  mean=+$1,434  (all wins ex 1)

VERDICT: NOT READY (CI lower bound < 0; drift > 1 SE)
```

## Compare to prior v7.1 (invalid — never actually live)

- v7.1 backtest: n=72, 56.9% win, +$466/trade, CI [+$74, +$870] → PASS
- **v7.1 was a phantom validation.** Live never ran that filter.

## SPRT re-baseline

Old pre-reg (sprt_v72_1_launch):
- H0 = 0.57 → log-LR = +3.23 → SPRT_HALT

New pre-reg (sprt_v72_1_launch_path_y):
- H0 = 0.52 (Path Y backtest win rate)
- H1 = 0.35 (unchanged; "clearly broken")
- alpha = beta = 0.05 (unchanged)
- Boundaries: HALT ≥ +2.94, SAFE ≤ -2.94

Recomputed on live 1W/9L:
- log-LR per win: log(0.35/0.52) = -0.396
- log-LR per loss: log(0.65/0.48) = +0.303
- Total: 1×(-0.396) + 9×(+0.303) = **+2.33**
- Verdict: **SPRT_CONTINUE** (below halt boundary +2.94)

At H1=0.30: log-LR = +2.84 → still CONTINUE
At H1=0.25: log-LR = +3.28 → HALT
At H1=0.40: log-LR = +1.79 → CONTINUE

**SPRT halt sensitivity is high to H1 choice. Under the pre-registered H1=0.35 with corrected H0=0.52, halt does NOT fire.**

## Combined verdict

Two independent signals:
- **DSR audit:** FAIL (NOT READY, CI includes 0). Strategy shouldn't be deploying.
- **SPRT (corrected):** CONTINUE. Live evidence not strong enough to reject at n=10.

These agree on: **do NOT trade live, but for a different reason than yesterday**. DSR fail means we don't have a validated strategy at all under honest metrics. SPRT continue means the live sample isn't yet decisive.

## Per-session picture

- **LON (75% win, +$1,031/trade, n=8):** likely real edge but small n. Could survive a proper OOS/purged CV.
- **ASIA (46% win, +$309/trade, n=13):** marginal. Needs more data.
- **NY (25% win, -$415/trade, n=4):** negative in-sample. Halt NY specifically.

## Refined proposal for next step

**Path Y' (Y-refined):**

1. **Keep kill switch on** for NY specifically (negative expectancy in backtest).
2. **Re-enable LON and ASIA** with reduced position size (50%) for a 20-trade window.
3. **After 20 trades**, re-run DSR audit with combined backtest + live sample. Check if CI clears zero.
4. **If still FAIL:** halt entire strategy, scope v8.
5. **If PASS:** return to full position size.

## Files changed this run

- `src/edge_session_orb_v7_final.py` — SESSION_CONFIG synced to live
- `data/experiments/registry.json` — new SPRT pre-reg entry (path_y baseline)
- `docs/experiments/2026-07-13_path_y_results.md` — this file

## Immediate action

Kill switch stays on. User decides on Path Y' vs alternative.
