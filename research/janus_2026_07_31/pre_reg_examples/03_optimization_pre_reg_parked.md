# TP1 limit-close fee optimization — pre-reg (design-only, build-gated to $2K)

**Author:** Janus 2026-07-31
**Status:** DESIGN PRE-REG. Not for build until capital-scaling gate met
+ $2K sub-account threshold. Locks the decision rule now so build is
fast when unlocked.
**Related:** `reference_bitget_fees.md` (parked as "highest-value
fee-optimization lever"), `project_2026_07_04_auto_trader_operational.md`
§Fee optimization v1.1

---

## Problem statement

Current auto-trader lifecycle uses **3 taker fills per trade**:

1. Entry: MARKET (taker)
2. Exit A (SL): MARKET (taker, position-attached `pos_loss`)
3. Exit B (TP1): MARKET (taker, position-attached `pos_profit`)

Bitget V2 USDT-M perp fees:
- **Taker:** 0.06% per side
- **Maker:** 0.02% per side (68% discount vs taker)

**Round-trip fee drag under current design:** 3 × 0.06% = **0.18%**

Actually — SL is only paid IF SL hits (~35% of trades at our WR).
TP1 is paid IF TP1 hits (~55% of trades). Weighted expected fees:

  Entry (100%) + WR*TP1 + (1-WR-expired)*SL + expired*none
  = 0.06% + 0.55*0.06% + 0.30*0.06% + 0*  (approximate)
  = 0.06% + 0.033% + 0.018%
  = **~0.111% per trade in expected fees**

At current sizing ($4 risk × 10x lev ≈ $40 notional), that's ~$0.044/
trade. Small in absolute terms but 5.5% of R-unit (measurable).
At the $2K sizing target (~$400 notional), 0.111% = ~$0.44/trade;
across 30 trades/mo = ~$13/mo.

## Proposed optimization

Replace **TP1 MARKET close** with **TP1 LIMIT-maker close**. Fee
becomes:

  0.06% entry + 0.55*0.02% TP1(maker) + 0.30*0.06% SL(taker) + 0
  = 0.06% + 0.011% + 0.018%
  = **~0.089% per trade** (20% reduction in expected fees)

## Locked hypothesis (H1)

**H1:** TP1 limit-close achieves ≥90% fill rate on setups where the
theoretical R resolves to `tp1_hit` in backtest, with negligible
uncaptured-move loss (< 0.05R per un-filled fill).

**H0:** TP1 limit-close achieves < 90% fill OR uncaptured-move loss
> 0.05R per un-filled fill (i.e. price wicks through TP1 without
resting long enough to fill a maker order, then reverses).

## Locked decision rule (ALL must hold to SHIP)

1. **Backtest fill rate ≥ 90%** on funding_extreme_revert TP1 hits in
   a ≥ 100-trade window. Fill counted as YES when price prints at or
   below (short) / at or above (long) TP1 for ≥ 5 seconds cumulatively
   within the price window that contains the tp1_hit.
2. **Backtest uncaptured-move R ≤ 0.05R per un-filled trade**
   (unfilled + adverse reversal price at 30s post-TP1-touch).
3. **Fee-saving delta ≥ 0.02% per trade** on the backtest sample
   (validates our arithmetic against real trade distribution).
4. **No regression in TP1-hit accounting.** setups.status still transitions
   `submitted → filled → tp1_hit → resolved` with realized_r within
   0.02R of the current MARKET-fill numbers.

## What ships (locked build spec, when unblocked)

- New env: `AUTO_TRADER_TP1_LIMIT_ENABLED` (default OFF)
- `src/auto_trader/placer.py` — when flag ON, submit TP1 as `pos_profit`
  with `orderType='limit'` at exactly the setup's `tp1_price` instead
  of `orderType='market'` triggered at the same price
- Fallback path: if TP1 limit sits > `AUTO_TRADER_TP1_LIMIT_TIMEOUT_MIN`
  minutes after price touches TP1 without filling, `resolver_hook`
  cancels the limit + submits MARKET close at current price. Timeout
  default: 10 min.
- New column `auto_trader_orders.fill_method` values gain `limit_maker`
  and `market_fallback` (mirrors the entry_method pattern from
  schema 028)
- Tests: 8-10 new unit tests on placer + resolver_hook path, matching
  the entry-method test coverage pattern

## SHADOW window (before LIVE)

- 5 trading days OR n=30 TP1-hit resolutions under the new flag,
  whichever first
- Metrics captured: fill_rate, mean_uncaptured_R, actual observed
  fee delta vs MARKET baseline (from Bitget position-history integration)
- Kill switch (during SHADOW): `AUTO_TRADER_TP1_LIMIT_ENABLED=false`

## Kill switch (post-LIVE)

- Env flip. Instant. Next scanner cadence reverts to MARKET closes.
- No code rollback required; MARKET path stays live behind the flag.

## What NOT to do

- Do NOT extend to LIMIT SL. SL fills are time-critical (protect
  capital) — a 5-second delay on a fast move can turn -1R into -2R
  or worse. Taker fee on SL is a feature, not a bug.
- Do NOT extend to LIMIT entry without a separate pre-reg. Entry
  LIMIT vs MARKET is a well-known execution tradeoff (fill certainty
  vs slippage); needs its own backtest.
- Do NOT re-tune the 90% fill-rate threshold if backtest lands at
  85-89%. Same locked-discipline pattern as Path B / tier=medium.
- Do NOT scale the timeout parameter to force higher fill rate.
  10 min is the pre-reg; if 10 min gives 85%, 30 min might give 92%
  but you're now holding a naked TP1 candidate for 30 min = raises
  the same risk class SL-taker was chosen to avoid.

## Calendar trigger for build authorization

**Whichever fires LAST:**

- Capital-scaling gate GATE_MET verdict (per
  `capital_scaling_gate_prereg_2026_07_13.md`)
- Sub-account balance ≥ $2K
- 30 days after this pre-reg date (2026-08-30) — soft "not while
  everything else is unproven" cooldown

Rationale for gating: at current $200 sub / $4 risk, monthly fee
savings ≈ $1.30. Not worth the complexity + risk. At $2K sub / $40
risk, monthly savings ≈ $13. Worth ~4h of build + shadow window.

## Cross-references

- Bitget fees canonical: `memory/reference_bitget_fees.md`
- Entry method LIMIT variant precedent: `src/auto_trader/placer.py`
  `entry_method` field + schema 028
- Position-history integration (needed for observed-fee measurement):
  `src/data/bitget_positions.py` (D2 reconciler infra)
- SHADOW pattern reference: `research/library/dynamic_funding_threshold_design_2026_07_04.md`

## Pre-reg discipline note

Writing this pre-reg NOW, well before build. If backtest at gate-day
gives 92% fill + 0.02R uncaptured + 0.025% fee savings, that's a
locked SHIP. If it gives 87% + 0.06R uncaptured + 0.03% fee savings,
that's a locked PARK — do NOT ship a "close-enough" TP1-limit that
imports fill-uncertainty risk into a working system.
