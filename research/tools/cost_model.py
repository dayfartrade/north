"""Cost-adjusted realized R.

Adapted from Janus's bluechipsignal cost_model.py (2026-07-31). Adjusted
to be asset-agnostic so we can use it for gold, silver, or any other
market. Slippage and fee defaults are now caller-provided rather than
hardcoded to a specific exchange.

The theoretical R for a trade is:
    long:  (exit - entry) / (entry - sl)
    short: (entry - exit) / (sl - entry)

That figure assumes frictionless fill at `entry` and `exit`. Real fills
have slippage plus round-trip fees. `compute_cost_adjusted_r` adjusts
entry and exit by slippage in the adverse direction for the side, then
deducts round-trip fees proportional to entry.

The risk denominator stays `abs(entry - sl)`, so the resulting R is
interpretable as "what fraction of the intended risk did this trade
actually return after costs."

For time-exit outcomes we model `exit_price = entry`, which yields
purely the cost drag as a small negative number. Meaningful for
per-signal expected R.
"""
from __future__ import annotations


def exit_price_for_outcome(
    outcome: str,
    *,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
) -> float:
    """Pick the appropriate exit price for a terminal outcome.

    Returns `entry` for unknown or cancelled outcomes (no-movement model
    that yields only the cost drag).
    """
    mapping = {
        "tp1_hit": tp1,
        "tp2_hit": tp2,
        "sl_hit": sl,
        "expired": entry,
        "time_exit": entry,
        "cancelled": entry,
    }
    return mapping.get(outcome, entry)


def compute_cost_adjusted_r(
    *,
    side: str,
    entry: float,
    exit_price: float,
    sl: float,
    slippage_pct: float,
    fee_pct: float,
) -> float:
    """Net realized R after slippage on both fills and round-trip fees.

    Arguments:
        side:          'long' or 'short'
        entry:         intended entry price
        exit_price:    actual or modeled exit price
        sl:            intended stop-loss price
        slippage_pct:  adverse slippage per side, expressed as decimal (0.0005 = 5bps)
        fee_pct:       fee per side, expressed as decimal (0.0006 = 6bps)

    Returns:
        Net R, rounded to 3 decimals. Returns 0.0 on pathological inputs
        (zero risk, invalid side) rather than raising, so callers can
        persist this into a numeric column without blocking on data
        anomalies.

    Suggested slippage/fee defaults per market (as of 2026-07):
        Gold futures (GC on CME):    slippage 0.0002, fee 0.00003 (IBKR ~$1.70 RT / $200k notional)
        Gold ETF (GLD):              slippage 0.0003, fee 0.00005 (retail commission-free)
        Silver futures (SI):         slippage 0.0005, fee 0.00003 (thinner book than GC)
        Crypto perp (Bitget VIP0):   slippage 0.0005, fee 0.0006

    All defaults are estimates. Calibrate against live fills once you
    have them. See `analysis_helpers.entry_slippage_bps` for the
    calibration measurement.
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
