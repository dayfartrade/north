# Pre-registration: FAR Weekly Bitcoin Read v1 (cross-asset conditioning)

**Registered UTC:** 2026-07-24T06:00:00Z
**Owner:** Knox (autonomous under user product-design delegation)
**Trial id:** `far_weekly_bitcoin_read_v1`
**Predecessor:** none (fresh mechanism-family application to new asset)
**Related:** `far_weekly_gold_read_v1` (shipped BETA, gold), `far_weekly_gold_read_v2` (shadow, gold+DXY)

## Motivation

Gold ORB family declared dead 2026-07-22 (12-year OOS). FAR Weekly gold
signal (momentum + macro conditioning) is the surviving mechanism.
Applying the same mechanism to a different asset with fundamentally
different drivers tests whether the *mechanism* generalizes or was
gold-specific curve fit.

Bitcoin as new-asset test:
- Fundamentally different (risk asset vs metal/safe-haven)
- Different macro sensitivity (weak USD → risk-on → BTC up; well-documented)
- 24/7 market simplifies execution timing
- 6.5 years of clean 5m data available (2017-05 to 2023-12)
- Retail-audience overlap with gold+macro readers
- Never before tested with FAR Weekly framework (multimarket test used
  gold-native RY signal on BTC; borderline result attributed to
  wrong-signal mismatch, not BTC-native drivers)

**Hypothesis:** BTC weekly momentum (M60) confirmed by DXY change
produces positive-Sharpe weekly signals with characteristics comparable
to FAR Weekly Gold v2 (which uses momentum + DXY on gold).

## Signal definition

Identical mechanism to `far_weekly_gold_read_v2`, applied to BTC:

- **Momentum:** M60 = 60-daily-bar rate of change on BTC daily close
- **Macro:** DXY_chg = 20-business-day change in DXY (FRED DTWEXBGS)
- **Direction:**
  - LONG BTC if M60 > 0 AND DXY_chg < 0 (BTC trending up, USD falling)
  - SHORT BTC if M60 < 0 AND DXY_chg > 0 (BTC trending down, USD rising)
  - FLAT otherwise

No RY conditioning (BTC lacks direct real-yield correlation).

## Position management

- Entry: Monday 00:00 UTC open (BTC 24/7)
- Stop: 2 × ATR(20 daily) on BTC daily bars
- Target: Friday 23:55 UTC close (time exit)
- Sizing: $10,000 notional per call (fractional BTC)
- Cost model: 0.1% RT (~$10 on $10k) — Coinbase/Kraken spot realistic

## Sample split (fixed BEFORE any backtest)

- **Training (~180 weeks):** 2017-05-07 to 2020-12-31
- **OOS (~156 weeks):** 2021-01-01 to 2023-12-31
- **Hold-out:** unavailable (no 2024+ BTC 5m data locally); if BTC data
  fetched in future, 2024+ becomes hold-out

**Anti-tuning rule:** all parameters (M60=60, DXY_chg=20, stop=2×ATR,
ATR=20) are fixed to match gold v2. No BTC-specific optimization.

## Ship gates (all must pass on OOS 2021-2023)

| # | Gate | Threshold | Rationale |
|---|------|-----------|-----------|
| 1 | OOS Sharpe (ann) | ≥ 0.50 | Half of gold v2's 1.04 accounts for asset-drift |
| 2 | OOS win rate | ≥ 50% | No worse than coinflip |
| 3 | OOS mean P&L per trade | > 0 | Positive expectancy |
| 4 | OOS PSR vs SR=0 | ≥ 0.90 | Statistical significance |
| 5 | OOS total P&L | > 0 | Absolute profitability |
| 6 | Trade count (OOS) | ≥ 50 | Statistical power (n>50 for CLT) |

**Any failure → REJECTED, no ship. Publish rejection with data.**

**Training-only failure:** if training Sharpe < 0.3, retire before
running OOS (candidate is dead). Training result is informational only
for design comparison, NOT a ship gate (avoids selection bias).

## Reject-gates (kill switches)

- OOS max drawdown > 60% of total capital → REJECTED (unshippable risk)
- OOS negative Sharpe → REJECTED
- OOS n < 30 → REJECTED (over-filtered)

## Live effect

**None during backtest phase.** If ship gates pass:
- Register as `far_weekly_bitcoin_read_v1` verdict `shadow_beta`
- Add BTC card to `weekly.html` page (parallel to gold card)
- Add publisher timer (Sunday 22:00 UTC alongside gold)
- Public disclosure of training/OOS metrics + this pre-reg link

If ship gates fail:
- Register verdict `rejected_ship_gates`
- Publish rejection notes in registry + memory
- No further BTC work until fresh mechanism candidate

## Bonferroni-adjusted DSR

Registry count at time of pre-reg: 34 trials (post-2026-07-22 session).
This trial increments to N=35. DSR computed post-backtest with N=35 for
familywise-error correction.

## Compliance with framework

- **Pre-registration:** ✅ this doc (before any BTC backtest)
- **No parameter tuning:** all params inherited from gold v2
- **Sample honesty:** train/OOS split fixed before any BTC data touched
- **Ship gates:** 6 explicit thresholds; all must pass
- **Registry:** entry created with verdict `pre_registered` before backtest
