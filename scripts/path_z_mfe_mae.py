"""MFE / MAE analysis for Path Z trades.

For each of the n=85 Path Z in-sample trades, walk the 5m bars from entry
to exit (or MAX_HOLD) and compute:
  - MFE (max favorable excursion): peak unrealized profit
  - MAE (max adverse excursion):   peak unrealized loss

Then check: on LOSING trades, did MFE go positive by material amount?
If yes, a break-even-at-X stop would rescue those losers into ~$0 trades.

Also compute: if we moved stop to break-even after price reached +1×ATR
in favor, what would the P&L be?
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

XAU = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"
PATH_Z_LOG = ROOT / "data" / "shadow_equity_path_z.jsonl"

CONTRACT_SIZE = 100
RT_COST = 24.0
MAX_HOLD_BARS = 36


def load_bars() -> pd.DataFrame:
    df = pd.read_csv(XAU, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df


def load_trades() -> list[dict]:
    rows = []
    with open(PATH_Z_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def analyze_one(bars: pd.DataFrame, tr: dict) -> dict | None:
    """Return per-trade MFE/MAE + break-even simulation."""
    try:
        entry_price = float(tr["entry_price"])
        stop_price = float(tr["stop_price"])
        target_price = float(tr["target_price"])
        direction = tr["direction_bias"]
        or_close_ts = pd.Timestamp(tr["or_close_utc"])
        if or_close_ts.tz is None:
            or_close_ts = or_close_ts.tz_localize("UTC")
    except Exception:
        return None

    # Find entry bar in 5m — need to walk bars past or_close for entry breakout
    or_close_idx = bars.index.get_loc(bars.index[bars.index <= or_close_ts][-1])
    # Simulate finding entry within watch window (matches backfill logic)
    WATCH = 12
    entry_idx = None
    for k in range(WATCH):
        i = or_close_idx + 1 + k
        if i >= len(bars):
            break
        b = bars.iloc[i]
        if direction == "LONG" and b["high"] >= entry_price:
            entry_idx = i
            break
        if direction == "SHORT" and b["low"] <= entry_price:
            entry_idx = i
            break
    if entry_idx is None:
        return None

    dir_sign = 1 if direction == "LONG" else -1
    mfe = 0.0
    mae = 0.0
    original_pnl = float(tr["outcome"]["net_pnl"])

    # ATR proxy from or_range
    or_range = float(tr["or_range"])
    breakeven_trigger = 0.5 * or_range  # move stop to entry after +0.5 OR in favor
    breakeven_active = False
    be_stop = stop_price
    be_exit_price = None
    be_exit_reason = None

    for k in range(MAX_HOLD_BARS + 1):
        if entry_idx + k >= len(bars):
            break
        b = bars.iloc[entry_idx + k]
        hi_pnl = (float(b["high"]) - entry_price) * dir_sign
        lo_pnl = (float(b["low"]) - entry_price) * dir_sign
        # For LONG: high is best-case, low is worst-case
        # For SHORT: opposite (already handled by dir_sign in the differences)
        if direction == "LONG":
            bar_mfe = float(b["high"]) - entry_price
            bar_mae = float(b["low"]) - entry_price
        else:
            bar_mfe = entry_price - float(b["low"])
            bar_mae = entry_price - float(b["high"])
        mfe = max(mfe, bar_mfe)
        mae = min(mae, bar_mae)

        # Break-even simulation
        if not breakeven_active and bar_mfe >= breakeven_trigger:
            breakeven_active = True
            be_stop = entry_price  # stop moves to entry

        # Simulate outcome under break-even stop
        if be_exit_price is None:
            if direction == "LONG":
                be_hit_stop = float(b["low"]) <= be_stop
                be_hit_tp = float(b["high"]) >= target_price
            else:
                be_hit_stop = float(b["high"]) >= be_stop
                be_hit_tp = float(b["low"]) <= target_price
            if be_hit_stop and be_hit_tp:
                be_exit_price = be_stop
                be_exit_reason = "stop_conservative"
            elif be_hit_stop:
                be_exit_price = be_stop
                be_exit_reason = "stop"
            elif be_hit_tp:
                be_exit_price = target_price
                be_exit_reason = "target"

    if be_exit_price is None:
        # Time exit
        end_idx = min(entry_idx + MAX_HOLD_BARS, len(bars) - 1)
        be_exit_price = float(bars.iloc[end_idx]["close"])
        be_exit_reason = "time"

    be_gross = (be_exit_price - entry_price) * dir_sign * CONTRACT_SIZE
    be_net = be_gross - RT_COST

    return {
        "date": tr["or_open_utc"][:10],
        "direction": direction,
        "entry_price": entry_price,
        "or_range": or_range,
        "original_pnl": original_pnl,
        "mfe_pts": mfe,
        "mae_pts": mae,
        "mfe_dollars": mfe * CONTRACT_SIZE,
        "mae_dollars": mae * CONTRACT_SIZE,
        "was_win": original_pnl > 0,
        "be_stop_triggered": breakeven_active,
        "be_exit_reason": be_exit_reason,
        "be_net_pnl": be_net,
    }


def main() -> None:
    print(f"Loading bars...")
    bars = load_bars()
    print(f"Loading Path Z trades...")
    trades = load_trades()
    print(f"  {len(trades)} trades")

    results = []
    for tr in trades:
        r = analyze_one(bars, tr)
        if r is not None:
            results.append(r)

    df = pd.DataFrame(results)
    print(f"\nAnalyzed {len(df)} trades")

    winners = df[df["was_win"]]
    losers = df[~df["was_win"]]

    print(f"\n=== MFE (Max Favorable Excursion) ===")
    for label, group in [("winners", winners), ("losers", losers)]:
        if len(group):
            print(f"  {label:8s}  n={len(group):>3d}  "
                  f"MFE mean={group['mfe_dollars'].mean():>+8,.0f}  "
                  f"median={group['mfe_dollars'].median():>+8,.0f}  "
                  f"max={group['mfe_dollars'].max():>+8,.0f}")

    print(f"\n=== MAE (Max Adverse Excursion) ===")
    for label, group in [("winners", winners), ("losers", losers)]:
        if len(group):
            print(f"  {label:8s}  n={len(group):>3d}  "
                  f"MAE mean={group['mae_dollars'].mean():>+8,.0f}  "
                  f"median={group['mae_dollars'].median():>+8,.0f}  "
                  f"worst={group['mae_dollars'].min():>+8,.0f}")

    # Key question: what fraction of losers had positive MFE >= 0.5 OR range?
    losers_had_favorable = losers[losers["mfe_pts"] >= losers["or_range"] * 0.5]
    print(f"\n=== Key question — did losers show gain BEFORE reversing? ===")
    print(f"Losers with MFE >= 0.5 * OR range: {len(losers_had_favorable)}/{len(losers)} "
          f"({100*len(losers_had_favorable)/len(losers):.0f}%)")
    print(f"Losers with MFE >= 1.0 * OR range: "
          f"{len(losers[losers['mfe_pts'] >= losers['or_range']])} / {len(losers)}")

    # Break-even stop simulation
    print(f"\n=== Break-even stop simulation ===")
    print(f"Rule: after MFE >= 0.5 * OR range, move stop from entry-OR to entry (0-risk).")
    total_orig = df["original_pnl"].sum()
    total_be = df["be_net_pnl"].sum()
    mean_orig = df["original_pnl"].mean()
    mean_be = df["be_net_pnl"].mean()
    diff = total_be - total_orig
    print(f"Original total P&L:      ${total_orig:>+10,.0f}  mean=${mean_orig:>+7,.2f}")
    print(f"Break-even-stop P&L:     ${total_be:>+10,.0f}  mean=${mean_be:>+7,.2f}")
    print(f"Lift from break-even:    ${diff:>+10,.0f}  ({100*diff/max(abs(total_orig),1):+.1f}%)")

    be_wins = (df["be_net_pnl"] > 0).sum()
    be_flat = ((df["be_net_pnl"] > -30) & (df["be_net_pnl"] < 30)).sum()
    print(f"Under break-even: wins={be_wins} ({100*be_wins/len(df):.1f}%), "
          f"~flat (|P&L|<$30)={be_flat}")

    # BE-triggered vs not
    be_triggered = df[df["be_stop_triggered"]]
    be_not = df[~df["be_stop_triggered"]]
    print(f"\nBreak-even was triggered on: {len(be_triggered)}/{len(df)} trades")
    if len(be_triggered):
        print(f"  Of those, original was: {(be_triggered['original_pnl']>0).sum()} wins / "
              f"{(be_triggered['original_pnl']<=0).sum()} losses")
        print(f"  Under BE: mean=${be_triggered['be_net_pnl'].mean():+,.2f}")
        print(f"  vs original: mean=${be_triggered['original_pnl'].mean():+,.2f}")


if __name__ == "__main__":
    main()
