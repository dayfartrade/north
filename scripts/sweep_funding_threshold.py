"""Sweep funding-filter threshold to find any meaningful cutoff.

Notes hypothesized P85 is the threshold. Our P85 backtest showed
inconclusive (n=1 blocked). Sweep P50, P60, ..., P95 to see if any
threshold cleanly identifies losing trades.
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
from edge_session_orb import session_utc_time_on
import data_bitget


def funding_at(funding_df, when):
    eligible = funding_df[funding_df["ts"] <= when]
    if eligible.empty:
        return None, None
    current = float(eligible.iloc[-1]["funding_rate"])
    abs_h = eligible["funding_rate"].abs()
    if len(abs_h) <= 1:
        return current, 0.0
    pct = (abs_h < abs(current)).mean()
    return current, pct


def main():
    funding = data_bitget.load_funding()
    if funding.empty:
        return
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    rows = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        if not df.empty:
            rows.append(df)
    trades = pd.concat(rows, ignore_index=True)
    taken = trades[trades["took_trade"] == True].copy().reset_index(drop=True)

    enriched = []
    for _, r in taken.iterrows():
        when = pd.Timestamp(r["session_open_ts"])
        if when.tz is None:
            when = when.tz_localize("UTC")
        rate, pct = funding_at(funding, when)
        enriched.append({"rate": rate, "abs_pct": pct})
    en = pd.DataFrame(enriched)
    taken["funding_rate"] = en["rate"]
    taken["abs_pct"] = en["abs_pct"]
    have = taken[taken["funding_rate"].notna()].copy()
    print(f"trades with funding overlap: {len(have)}\n")

    # Approach A: fade-direction filter at varying thresholds
    print(f"{'thresh':>7s}  {'allowed_n':>10s}  {'allowed_mean':>13s}  {'allowed_sum':>12s}  {'blocked_n':>10s}  {'blocked_mean':>13s}  {'blocked_sum':>12s}")
    print("-"*100)
    for thresh in [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
        blocked_mask = (have["abs_pct"] >= thresh) & (
            ((have["funding_rate"] > 0) & (have["direction"] == 1)) |
            ((have["funding_rate"] < 0) & (have["direction"] == -1))
        )
        a = have[~blocked_mask]
        b = have[blocked_mask]
        print(f"{thresh:7.2f}  {len(a):>10d}  ${a['net_pnl'].mean() if not a.empty else 0:>12.2f}  ${a['net_pnl'].sum():>11.0f}  {len(b):>10d}  ${b['net_pnl'].mean() if not b.empty else 0:>12.2f}  ${b['net_pnl'].sum():>11.0f}")

    print()
    print("=== Approach B: bucket P&L by sign of funding x sign of direction ===")
    # Funding sign vs direction sign: do longs lose when funding > 0 (long-crowded)?
    have["funding_sign"] = np.sign(have["funding_rate"]).astype(int)
    have["aligned_with_funding"] = (have["funding_sign"] == have["direction"])
    for sign in (-1, 0, +1):
        for aligned in (True, False):
            sub = have[(have["funding_sign"] == sign) & (have["aligned_with_funding"] == aligned)]
            if sub.empty: continue
            wins = (sub["net_pnl"] > 0).sum()
            print(f"  funding_sign={sign:+d}  aligned_with_funding={aligned}: n={len(sub):3d}  win%={wins/len(sub)*100:5.1f}  total=${sub['net_pnl'].sum():+8.0f}  mean=${sub['net_pnl'].mean():+.2f}")

    print()
    print("=== Approach C: bucket by funding magnitude (abs value, not percentile) ===")
    abs_h = funding["funding_rate"].abs()
    cuts = [0, 1e-6, 1e-5, 5e-5, 1e-4, 5e-4, 1e-2]
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        sub = have[(have["funding_rate"].abs() >= lo) & (have["funding_rate"].abs() < hi)]
        if sub.empty:
            print(f"  |rate| [{lo:.0e}, {hi:.0e}): n=0")
            continue
        wins = (sub["net_pnl"] > 0).sum()
        print(f"  |rate| [{lo:.0e}, {hi:.0e}): n={len(sub):3d}  win%={wins/len(sub)*100:5.1f}  total=${sub['net_pnl'].sum():+8.0f}  mean=${sub['net_pnl'].mean():+.2f}")


if __name__ == "__main__":
    main()
