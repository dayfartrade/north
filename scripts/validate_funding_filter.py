"""Backtest validation: does the funding-extreme filter actually improve ORB?

Method:
  1. Run v7-hybrid ORB across the 60-day backtest window.
  2. For each trade, look up the funding rate at session-open time
     (use the most recent funding posting prior to the open).
  3. Compute funding percentile within history-up-to-that-moment
     (walk-forward, not look-ahead).
  4. Classify each trade as "filter_allowed" or "filter_blocked":
       blocked: extreme funding AND entry direction == crowded side
       allowed: otherwise
  5. Compare mean/sum/win-rate of allowed vs blocked.

Hypothesis: blocked trades have negative or zero mean (justifying the skip).
Null: blocked trades have positive mean comparable to allowed (filter
worthless or harmful).

Honest caveat: only ~3 months of overlap between Bitget funding history
and ORB backtest window. Small n on blocked-trades expected.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import numpy as np
from datetime import datetime
import pytz

from data_gc import load as gc_load
from edge_session_orb_v7_final import run_orb_v7, SESSION_CONFIG
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on
import data_bitget


EXTREME_PCT = 0.85


def funding_at_time(funding_df: pd.DataFrame, when: pd.Timestamp) -> dict:
    """Return funding rate observation most recently posted at-or-before `when`.
    Computes walk-forward percentile (no look-ahead)."""
    if funding_df.empty:
        return {"rate": None, "abs_pct": None}
    eligible = funding_df[funding_df["ts"] <= when]
    if eligible.empty:
        return {"rate": None, "abs_pct": None}
    current_rate = float(eligible.iloc[-1]["funding_rate"])
    # Use ALL eligible history for percentile (walk-forward)
    abs_h = eligible["funding_rate"].abs()
    abs_pct = (abs_h < abs(current_rate)).mean() if len(abs_h) > 1 else 0.0
    return {"rate": current_rate, "abs_pct": abs_pct}


def classify(funding: dict, direction: int) -> dict:
    """Return whether the funding filter would have blocked this entry."""
    rate = funding["rate"]
    pct = funding["abs_pct"]
    if rate is None:
        return {"blocked": False, "reason": "no_funding_data", "tilt": 0}
    if pct < EXTREME_PCT:
        return {"blocked": False, "reason": "below_85th", "tilt": 0}
    # Extreme — fade the sign
    tilt = -1 if rate > 0 else +1
    if direction == tilt:
        return {"blocked": False, "reason": "aligned_with_tilt", "tilt": tilt}
    return {"blocked": True, "reason": "against_tilt", "tilt": tilt}


def main():
    # Load funding history
    funding = data_bitget.load_funding()
    if funding.empty:
        print("[validate] no Bitget funding history cached. Run data_bitget.py first.")
        return
    print(f"Funding history: {len(funding)} rows  range: {funding['ts'].min()} -> {funding['ts'].max()}")
    print()

    # Run v7-hybrid ORB
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    all_trades = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        if not df.empty:
            all_trades.append(df)
    trades = pd.concat(all_trades, ignore_index=True)
    taken = trades[trades["took_trade"] == True].copy()
    print(f"v7-hybrid trades: n={len(taken)}")

    # Classify each trade
    classifications = []
    for _, row in taken.iterrows():
        when = pd.Timestamp(row["session_open_ts"])
        if when.tz is None:
            when = when.tz_localize("UTC")
        f = funding_at_time(funding, when)
        c = classify(f, int(row["direction"]))
        classifications.append({**f, **c})
    cl_df = pd.DataFrame(classifications)
    taken = taken.reset_index(drop=True)
    taken["funding_rate"] = cl_df["rate"]
    taken["abs_pct"] = cl_df["abs_pct"]
    taken["blocked"] = cl_df["blocked"]
    taken["block_reason"] = cl_df["reason"]
    taken["tilt"] = cl_df["tilt"]

    # Restrict to trades where we HAVE funding data overlap
    have_data = taken[taken["funding_rate"].notna()].copy()
    print(f"Trades with funding data overlap: n={len(have_data)} / {len(taken)}")
    print()

    if have_data.empty:
        print("[validate] no overlap window. Bitget funding starts {} but trades end {}".format(
            funding["ts"].min(), taken["session_open_ts"].max()))
        return

    allowed = have_data[have_data["blocked"] == False]
    blocked = have_data[have_data["blocked"] == True]
    print(f"=== If we APPLIED the funding filter ===")
    print(f"  ALLOWED  trades: n={len(allowed):3d}  wins={(allowed['net_pnl']>0).sum():3d}  total=${allowed['net_pnl'].sum():+8.0f}  mean=${allowed['net_pnl'].mean() if not allowed.empty else 0:+.2f}")
    print(f"  BLOCKED  trades: n={len(blocked):3d}  wins={(blocked['net_pnl']>0).sum():3d}  total=${blocked['net_pnl'].sum():+8.0f}  mean=${blocked['net_pnl'].mean() if not blocked.empty else 0:+.2f}")
    print()
    # Win rates
    if not allowed.empty:
        print(f"  ALLOWED  win%={(allowed['net_pnl']>0).mean()*100:.1f}")
    if not blocked.empty:
        print(f"  BLOCKED  win%={(blocked['net_pnl']>0).mean()*100:.1f}")
    print()

    # By percentile bucket
    print("=== P&L by funding-percentile bucket ===")
    for lo, hi in [(0, 0.5), (0.5, 0.85), (0.85, 0.95), (0.95, 1.01)]:
        sub = have_data[(have_data["abs_pct"] >= lo) & (have_data["abs_pct"] < hi)]
        if sub.empty:
            print(f"  pct [{lo:.2f},{hi:.2f}): n=0")
            continue
        wins = (sub["net_pnl"] > 0).sum()
        print(f"  pct [{lo:.2f},{hi:.2f}): n={len(sub):3d}  win%={wins/len(sub)*100:5.1f}  total=${sub['net_pnl'].sum():+8.0f}  mean=${sub['net_pnl'].mean():+8.2f}")
    print()

    # Detail: list blocked trades
    if not blocked.empty:
        print("=== Detail: what we'd have blocked ===")
        for _, r in blocked.iterrows():
            print(f"  {str(r['session_open_ts'])[:16]} {r['session']:5s} dir={int(r['direction']):+d}  funding={r['funding_rate']:.6f} pct={r['abs_pct']:.2f}  tilt={int(r['tilt']):+d}  net_pnl=${r['net_pnl']:+.2f}")


if __name__ == "__main__":
    main()
