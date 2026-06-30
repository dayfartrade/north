"""Funding-extreme filter for gold (port of crypto funding_extreme_revert).

Rule (from the user's notes):
  When |funding| ≥ P85 within gold's own history (NOT BTC absolute):
    - If positive extreme  -> skip LONG entries, prefer SHORT/fade
    - If negative extreme  -> skip SHORT entries, prefer LONG/fade
  Otherwise: no filter applied.

This is a FILTER (regime tilt), not a primary signal.
Caveat from notes: Gold has central-bank absorption that crypto lacks.
The signal is real but noisier than crypto. Use with bootstrap CI before
declaring edge.

Cadence:
  Bitget funding posts every 8H. So this filter updates 3×/day.
  At signal time (ORB entry), query the most recent funding rate.

Implementation:
  funding_history = last N rows from data/bitget/funding_XAUUSDT.csv
  current_funding = latest row
  abs_pctile = percentile rank of |current| within |history|
  if abs_pctile >= 85:
      regime_tilt = -sign(current_funding)  # fade the crowded side
  else:
      regime_tilt = 0  # neutral
"""
from __future__ import annotations
import pandas as pd
import data_bitget


EXTREME_PERCENTILE = 0.85  # threshold per notes (85th pct)


def compute_funding_regime(history_df: pd.DataFrame, current_rate: float) -> dict:
    """Return regime tilt based on funding extremes.

    Returns:
        {
          "current_rate": float,
          "abs_percentile": float in [0,1],
          "extreme": bool,
          "regime_tilt": int (-1, 0, +1)  # +1=prefer longs, -1=prefer shorts, 0=neutral
          "reason": str
        }
    """
    if history_df.empty:
        return {"current_rate": current_rate, "abs_percentile": 0.0,
                "extreme": False, "regime_tilt": 0, "reason": "no_history"}

    abs_history = history_df["funding_rate"].abs()
    abs_current = abs(current_rate)
    pct = (abs_history < abs_current).mean()  # fraction of history strictly below current

    if pct < EXTREME_PERCENTILE:
        return {"current_rate": current_rate, "abs_percentile": pct,
                "extreme": False, "regime_tilt": 0, "reason": "below_85th_pct"}

    # Extreme — fade the sign
    if current_rate > 0:
        return {"current_rate": current_rate, "abs_percentile": pct,
                "extreme": True, "regime_tilt": -1,
                "reason": f"longs_crowded (pct={pct:.2f}) -> prefer shorts"}
    else:
        return {"current_rate": current_rate, "abs_percentile": pct,
                "extreme": True, "regime_tilt": +1,
                "reason": f"shorts_crowded (pct={pct:.2f}) -> prefer longs"}


def get_current_regime() -> dict:
    """Fetch live current funding + history, compute regime."""
    history = data_bitget.load_funding()
    if history.empty:
        # Pull from API on first run
        history = data_bitget.refresh_funding_history(pages=10)
    current = data_bitget.fetch_current_funding()
    return compute_funding_regime(history, current["funding_rate"])


def filter_entry(direction: int, regime: dict | None = None) -> dict:
    """Decide whether to take a directional entry given the funding regime.

    direction: +1 long, -1 short
    Returns: {"allow": bool, "reason": str, "regime_tilt": int}
    """
    if regime is None:
        regime = get_current_regime()
    tilt = regime["regime_tilt"]
    if tilt == 0:
        return {"allow": True, "reason": "no_funding_extreme", "regime_tilt": 0}
    # Tilt is the PREFERRED direction. Disagree -> skip.
    if direction == tilt:
        return {"allow": True, "reason": f"aligned_with_funding_tilt ({regime['reason']})",
                "regime_tilt": tilt}
    return {"allow": False, "reason": f"against_funding_tilt ({regime['reason']})",
            "regime_tilt": tilt}


if __name__ == "__main__":
    regime = get_current_regime()
    print("=== Current funding regime ===")
    print(f"current_rate:    {regime['current_rate']:.6f}  ({regime['current_rate']*1095:+.2%} annualized)")
    print(f"abs_percentile:  {regime['abs_percentile']:.3f}")
    print(f"extreme:         {regime['extreme']}")
    print(f"regime_tilt:     {regime['regime_tilt']:+d}")
    print(f"reason:          {regime['reason']}")
    print()
    print("=== Entry filter test ===")
    for d in (+1, -1):
        f = filter_entry(d, regime)
        print(f"direction={d:+d}: allow={f['allow']}  reason={f['reason']}")

    # Backfill historical analysis: how often does this filter fire?
    print()
    print("=== Filter fire rate over history ===")
    hist = data_bitget.load_funding()
    if not hist.empty:
        abs_h = hist["funding_rate"].abs()
        # P85 threshold within own history
        p85 = abs_h.quantile(0.85)
        fires = (abs_h >= p85).sum()
        print(f"  history rows:  {len(hist)}")
        print(f"  P85 |funding|: {p85:.6f}  ({p85*1095:.1%} annualized)")
        print(f"  fires:         {fires} / {len(hist)} = {fires/len(hist)*100:.1f}%")
        # Note: 15% by construction. The real test is whether fade-direction wins.
