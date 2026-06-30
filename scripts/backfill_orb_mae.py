"""Backfill MAE/MFE into the existing ORB forward log.

Re-resolves every took_trade=True row from 5m bars, computing MAE/MFE
in price units and dollars. Used once to bring the live tracker up to
the v7 schema before geometry surgery.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import numpy as np

from data_gc import load as gc_load
from backtest import CONTRACT_SIZE

LOG = ROOT / "data" / "tracker" / "orb_forward_log.csv"


def compute_mae_mfe(bars: pd.DataFrame, entry_ts, exit_ts, entry_price, direction):
    """Walk 5m bars from entry to exit inclusive, return (mae_price, mfe_price)."""
    entry_ts = pd.Timestamp(entry_ts)
    exit_ts = pd.Timestamp(exit_ts)
    if entry_ts.tz is None:
        entry_ts = entry_ts.tz_localize("UTC")
    if exit_ts.tz is None:
        exit_ts = exit_ts.tz_localize("UTC")
    window = bars.loc[(bars.index >= entry_ts) & (bars.index <= exit_ts)]
    if window.empty:
        return 0.0, 0.0
    mae = 0.0
    mfe = 0.0
    for _, b in window.iterrows():
        if direction == 1:
            adverse = entry_price - float(b["low"])
            favorable = float(b["high"]) - entry_price
        else:
            adverse = float(b["high"]) - entry_price
            favorable = entry_price - float(b["low"])
        if adverse > mae:
            mae = adverse
        if favorable > mfe:
            mfe = favorable
    return mae, mfe


def main():
    if not LOG.exists():
        print(f"[backfill] no log at {LOG}")
        return
    df = pd.read_csv(LOG, parse_dates=["open_ts", "entry_ts", "exit_ts"])
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    # Add new columns if missing
    for col in ["mae_price", "mfe_price", "mae_dollars", "mfe_dollars"]:
        if col not in df.columns:
            df[col] = np.nan

    n_updated = 0
    for i, row in df.iterrows():
        if not row.get("took_trade", False):
            continue
        if pd.isna(row.get("entry_ts")) or pd.isna(row.get("exit_ts")):
            continue
        mae, mfe = compute_mae_mfe(
            bars, row["entry_ts"], row["exit_ts"],
            float(row["entry_price"]), int(row["direction"])
        )
        df.at[i, "mae_price"] = mae
        df.at[i, "mfe_price"] = mfe
        df.at[i, "mae_dollars"] = mae * CONTRACT_SIZE
        df.at[i, "mfe_dollars"] = mfe * CONTRACT_SIZE
        n_updated += 1

    df.to_csv(LOG, index=False)
    print(f"[backfill] updated {n_updated} rows in {LOG.name}")

    # Quick summary on what we just learned
    taken = df[df["took_trade"] == True].copy()
    if taken.empty:
        return
    taken["is_win"] = taken["net_pnl"] > 0
    winners = taken[taken["is_win"]]
    losers = taken[~taken["is_win"]]
    print("\n=== Winner-MAE distribution (price units) ===")
    if not winners.empty:
        w_mae = winners["mae_price"]
        print(f"  n={len(winners)}  mean=${w_mae.mean():.2f}  median=${w_mae.median():.2f}  P75=${w_mae.quantile(0.75):.2f}  P90=${w_mae.quantile(0.90):.2f}  max=${w_mae.max():.2f}")
        print(f"  winner-MAE per session:")
        for sess in winners["session"].unique():
            sub = winners[winners["session"] == sess]["mae_price"]
            print(f"    {sess:5s} n={len(sub)}  mean=${sub.mean():.2f}  max=${sub.max():.2f}")
    print("\n=== Loser-MAE (i.e. our actual stop-out distance) ===")
    if not losers.empty:
        l_mae = losers["mae_price"]
        print(f"  n={len(losers)}  mean=${l_mae.mean():.2f}  median=${l_mae.median():.2f}  max=${l_mae.max():.2f}")
    print("\n=== OR range vs stop-out: per loser ===")
    if not losers.empty:
        for _, r in losers.iterrows():
            print(f"  {str(r['open_ts'])[:16]} {r['session']:5s} OR={r['or_range']:6.2f}  MAE={r['mae_price']:6.2f}  net=${r['net_pnl']:+8.2f}")


if __name__ == "__main__":
    main()
