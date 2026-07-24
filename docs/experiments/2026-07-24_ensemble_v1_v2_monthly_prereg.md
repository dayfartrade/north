# Pre-registration: FAR Weekly Gold Ensemble (v1 + v2 + monthly) v1

**Registered UTC:** 2026-07-24T13:20:00Z
**Trial id:** `far_weekly_gold_ensemble_v1`

## Motivation

Six single-mechanism candidates failed today. But an ensemble that requires
multiple independent-ish signals to AGREE might filter out one-off signal
noise. Fresh mechanism (voting), not a single new signal.

## Signal definition

Weekly cycle. Enter LONG or SHORT only when ≥2 of the following agree:
- **v1** (M20+M60+MA+RY): direction as shipped
- **v2** (v1 + DXY): direction as shadow
- **Monthly M12 momentum**: LONG if 12-month gold return > 0, SHORT if < 0

If ≥2 agree on LONG → LONG. If ≥2 agree on SHORT → SHORT. Else FLAT.

Same position mgmt as v1 (2×ATR stop, Friday close exit, 1 contract, $5 RT).

## Ship gates (all must pass on OOS 2019-2026)

| # | Gate | Threshold |
|---|------|-----------|
| 1 | OOS Sharpe ≥ 0.80 (higher than v1's 0.77) | — |
| 2 | OOS Sharpe > v1's OOS Sharpe | — |
| 3 | OOS WR ≥ 55% | — |
| 4 | OOS n ≥ 50 (voting should filter) | — |
| 5 | OOS total > 0 | — |

Kill: negative Sharpe → REJECTED. If Sharpe simply matches v1's ±10%, REJECTED (no diversification benefit).

## Sample split

- Training: 2010-2018
- OOS: 2019-2026

Note: v1 + v2 already extensively tested on 2019-2026 as their shadow window. Ensemble is new construction from known components.
