"""Cost-adjusted realized R — the slippage + fee delta the backtest hides.

The existing `realized_r` column on `setups` is the theoretical R:
   long:  (exit - entry) / (entry - sl)
   short: (entry - exit) / (sl - entry)

That figure assumes a frictionless fill at `entry` and `exit`. Real
fills on Bitget perps have:
  - Slippage  — market entry pays a fraction worse than mid; market
                exit gets a fraction worse than mid. ~0.05% on the
                top crypto pairs at small size, more on thinner books.
  - Taker fee — VIP0 charges 0.06% per side; round trip 0.12%.

`compute_cost_adjusted_r` adjusts entry and exit by the slippage
fraction in the adverse direction for the side, then deducts round-
trip fees proportional to `entry`. The risk denominator stays
`abs(entry - sl)` — i.e., the sizing-time risk the operator targeted —
so the resulting R is interpretable as "what fraction of the intended
risk did this trade actually return after costs."

For `expired` outcomes we model `exit_price = entry` (i.e., the
position closed at entry-level after time-stop), which means the
adjusted R is purely the cost drag: -2*fee_pct*entry / risk, a small
but nonzero negative — meaningful for tier-by-tier expected R.
"""
from __future__ import annotations


DEFAULT_SLIPPAGE_PCT = 0.0005  # 0.05% adverse per side
DEFAULT_FEE_PCT = 0.0006       # 0.06% per side (Bitget VIP0 taker)


def exit_price_for_outcome(
    outcome: str,
    *,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
) -> float:
    """Pick the appropriate exit price for a terminal outcome.

    Returns `entry` for unknown/cancelled outcomes — a no-movement model
    that yields only the cost drag (defensive default).
    """
    mapping = {
        "tp1_hit": tp1,
        "tp2_hit": tp2,
        "sl_hit": sl,
        "expired": entry,
        "cancelled": entry,
    }
    return mapping.get(outcome, entry)


def compute_cost_adjusted_r(
    *,
    side: str,
    entry: float,
    exit_price: float,
    sl: float,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
    fee_pct: float = DEFAULT_FEE_PCT,
) -> float:
    """Net realized R after applying slippage to both fills and round-trip fees.

    Returns 0.0 on pathological inputs (zero risk, invalid side) rather
    than raising — callers persist this into a numeric column and
    raising would block the entire resolver run on a data anomaly.
    """
    if side not in ("long", "short"):
        return 0.0
    risk = abs(entry - sl)
    if risk <= 0 or entry <= 0:
        return 0.0
    if side == "long":
        # Long pays MORE on entry (price moves against us), gets LESS on exit.
        effective_entry = entry * (1.0 + slippage_pct)
        effective_exit = exit_price * (1.0 - slippage_pct)
        gross = effective_exit - effective_entry
    else:
        # Short sells for LESS on entry, buys back for MORE on exit.
        effective_entry = entry * (1.0 - slippage_pct)
        effective_exit = exit_price * (1.0 + slippage_pct)
        gross = effective_entry - effective_exit
    fees = 2.0 * fee_pct * entry
    net = gross - fees
    return round(net / risk, 3)
