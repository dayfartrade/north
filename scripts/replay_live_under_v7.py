"""Replay the live ORB trades under the v7-hybrid logic to estimate the difference."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import numpy as np

from data_gc import load as gc_load
from mers_v3_peb import compute_atr
from backtest import CONTRACT_SIZE, RT_COST_PER_CONTRACT

# v7-hybrid config: only LON gets the new geometry
HYBRID = {
    "ASIA": {"use_filter": False, "stop_mode": "or_range", "target_mode": "or_range"},
    "LON":  {"use_filter": True,  "stop_mode": "adaptive", "target_mode": "stop_x_tp",
             "stop_dist": 13.0, "or_vs_atr_max": 2.0},
    "NY":   {"use_filter": False, "stop_mode": "or_range", "target_mode": "or_range"},
}
TP_MULT = 1.5

def replay_one(bars, atr, row):
    """Given a live trade row + bars, return replay net_pnl under v7 hybrid."""
    sess = row["session"]
    cfg = HYBRID[sess]
    or_high = float(row["or_high"]); or_low = float(row["or_low"])
    or_range = or_high - or_low
    open_ts = pd.Timestamp(row["open_ts"])
    if open_ts.tz is None: open_ts = open_ts.tz_localize("UTC")

    # ATR at open
    try:
        atr_at_open = float(atr.loc[atr.index <= open_ts].iloc[-1])
    except Exception:
        return None
    if cfg["use_filter"] and or_range > cfg.get("or_vs_atr_max", 2.0) * atr_at_open:
        return {"replay_action": "skipped_filter", "replay_pnl": 0.0}

    # Did the breakout happen in original? If took_trade=True, we know it did.
    if not row.get("took_trade", False):
        return {"replay_action": "no_breakout", "replay_pnl": 0.0}

    entry_dir = int(row["direction"])
    entry_price = float(row["entry_price"])
    entry_ts = pd.Timestamp(row["entry_ts"])
    if entry_ts.tz is None: entry_ts = entry_ts.tz_localize("UTC")

    # Compute new stop/target
    if cfg["stop_mode"] == "adaptive":
        stop_dist = cfg["stop_dist"]
    else:
        stop_dist = or_range
    if cfg["target_mode"] == "or_range":
        target_dist = TP_MULT * or_range
    else:
        target_dist = TP_MULT * stop_dist

    stop_lvl = entry_price - stop_dist * entry_dir
    target_lvl = entry_price + target_dist * entry_dir

    # Walk bars from entry_ts to find exit
    exit_price = None
    forward_window = bars.loc[bars.index >= entry_ts].head(25)  # up to MAX_HOLD bars + 1
    for _, b in forward_window.iterrows():
        if entry_dir == 1:
            hit_stop = b["low"] <= stop_lvl
            hit_tp = b["high"] >= target_lvl
        else:
            hit_stop = b["high"] >= stop_lvl
            hit_tp = b["low"] <= target_lvl
        if hit_stop:
            exit_price = stop_lvl; break
        if hit_tp:
            exit_price = target_lvl; break
    if exit_price is None:
        # time exit at last bar in window
        exit_price = float(forward_window.iloc[-1]["close"]) if not forward_window.empty else entry_price

    gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
    net = gross - RT_COST_PER_CONTRACT
    return {"replay_action": "traded", "replay_pnl": float(net),
            "replay_stop": float(stop_lvl), "replay_target": float(target_lvl)}


def main():
    LOG = ROOT / "data" / "tracker" / "orb_forward_log.csv"
    df = pd.read_csv(LOG, parse_dates=["open_ts", "entry_ts", "exit_ts"])
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None: bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)

    print(f"{'date':<12s} {'sess':5s} {'OR':>6s} {'orig_pnl':>10s}  {'action':<18s} {'v7_pnl':>10s}")
    orig_total = 0; v7_total = 0
    counts = {"traded": 0, "skipped_filter": 0, "no_breakout": 0}
    for _, row in df.iterrows():
        if not row.get("took_trade", False):
            continue
        res = replay_one(bars, atr, row)
        if res is None:
            continue
        d = str(row['open_ts'])[:10]
        orig = float(row['net_pnl']) if pd.notna(row['net_pnl']) else 0
        v7 = res['replay_pnl']
        orig_total += orig
        v7_total += v7
        counts[res['replay_action']] = counts.get(res['replay_action'], 0) + 1
        print(f"{d:<12s} {row['session']:5s} {float(row['or_range']):>6.2f} {orig:>+10.2f}  {res['replay_action']:<18s} {v7:>+10.2f}")

    print()
    print(f"Original total: ${orig_total:+.2f}")
    print(f"v7-hybrid total: ${v7_total:+.2f}")
    print(f"Delta: ${v7_total - orig_total:+.2f}")
    print(f"Counts: {counts}")


if __name__ == "__main__":
    main()
