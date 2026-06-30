"""Pull winner-MAE / loser-MAE distribution from full ORB backtest history.

Runs the ORB strategy across all available 5m bars (60-day window),
then derives the stop placement recommendation for v7 geometry.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import numpy as np

from data_gc import load as gc_load
from edge_session_orb import run_orb, SESSIONS_LOCAL, session_utc_time_on
from datetime import datetime
import pytz


def main():
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    # Use the validated config from track_orb.py: or=6, watch=12, hold=24, tp=1.5
    all_trades = []
    for sess_name in SESSIONS_LOCAL:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb(bars, sess_t, sess_name,
                     or_bars=6, watch_bars=12, max_hold=24,
                     stop_mult=1.0, tp_mult=1.5, require_trend=True)
        if not df.empty:
            df["session"] = sess_name
            all_trades.append(df)
    if not all_trades:
        print("[geom] no trades from backtest")
        return
    trades = pd.concat(all_trades, ignore_index=True)
    trades["is_win"] = trades["net_pnl"] > 0
    winners = trades[trades["is_win"]]
    losers = trades[~trades["is_win"]]

    print(f"=== ORB backtest sweep: n={len(trades)} trades, wins={len(winners)} ({len(winners)/len(trades)*100:.1f}%) ===")
    print(f"Net P&L: ${trades['net_pnl'].sum():+.0f}  mean=${trades['net_pnl'].mean():+.2f}")
    print()

    if not winners.empty:
        w_mae = winners["mae_price"]
        print(f"=== Winner-MAE distribution (price units) — n={len(winners)} ===")
        for p in [0.50, 0.75, 0.85, 0.90, 0.95, 0.99]:
            print(f"  P{int(p*100):02d}: ${w_mae.quantile(p):6.2f}")
        print(f"  max:  ${w_mae.max():6.2f}")
        print(f"  mean: ${w_mae.mean():6.2f}")
        print()
        # Per session
        print("=== Winner-MAE per session ===")
        for sess in sorted(winners["session"].unique()):
            sub = winners[winners["session"] == sess]["mae_price"]
            if len(sub) < 3:
                print(f"  {sess:5s} n={len(sub):3d} (too thin)")
                continue
            print(f"  {sess:5s} n={len(sub):3d}  mean=${sub.mean():6.2f}  P75=${sub.quantile(0.75):6.2f}  P90=${sub.quantile(0.90):6.2f}  max=${sub.max():6.2f}")
        print()

    if not losers.empty:
        l_mae = losers["mae_price"]
        print(f"=== Loser-MAE distribution — n={len(losers)} ===")
        for p in [0.50, 0.75, 0.90]:
            print(f"  P{int(p*100):02d}: ${l_mae.quantile(p):6.2f}")
        print(f"  mean: ${l_mae.mean():6.2f}")
        print(f"  max:  ${l_mae.max():6.2f}")
        print()

    # Counterfactual: what if stop was at winner P90?
    if not winners.empty and not losers.empty:
        p90 = winners["mae_price"].quantile(0.90)
        print(f"=== Counterfactual: tighten stop to winner-MAE P90 = ${p90:.2f} ===")
        # Winners that would have been stopped out (their MAE exceeded the new stop)
        kept_winners = winners[winners["mae_price"] <= p90]
        lost_winners = winners[winners["mae_price"] > p90]
        print(f"  Winners kept:     {len(kept_winners)}/{len(winners)} ({len(kept_winners)/len(winners)*100:.1f}%)")
        print(f"  Winners stopped:  {len(lost_winners)}/{len(winners)} (we'd have lost ${p90*100:.0f} on each instead of winning)")
        # Estimate new P&L: kept winners keep their pnl; lost winners become -p90*$100; losers all capped at -p90*$100
        from_kept = kept_winners["net_pnl"].sum()
        from_lost_winners = -p90 * 100 * len(lost_winners)
        from_losers = -p90 * 100 * len(losers)
        new_total = from_kept + from_lost_winners + from_losers
        print(f"  Estimated new total P&L: ${new_total:+.0f}  (was ${trades['net_pnl'].sum():+.0f})")

    # OR range distribution — for "skip if range > 2×ATR" filter
    print()
    print(f"=== OR range distribution ===")
    for p in [0.50, 0.75, 0.90, 0.95]:
        print(f"  P{int(p*100):02d} OR range: ${trades['or_range'].quantile(p):.2f}")
    # And how OR-range correlates with win
    if not losers.empty and not winners.empty:
        print(f"  Mean OR range: winners=${winners['or_range'].mean():.2f}  losers=${losers['or_range'].mean():.2f}")


if __name__ == "__main__":
    main()
