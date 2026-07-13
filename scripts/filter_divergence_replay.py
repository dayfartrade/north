"""Replay each forward-log trade under BOTH filter versions and compare.

LIVE filter (dispatch_orb.py:528):
    or_max = cfg.get("or_vs_atr_max", 2.0) * cur_atr
    if or_range > or_max: skip

BACKTEST filter (edge_session_orb_v7_final.py SESSION_CONFIG):
    LON: skip if or_range > 2.0 * atr
    NY:  skip if or_range < 2.5 * atr
    ASIA: skip if 2.0 * atr <= or_range <= 2.5 * atr

Answers:
  - Which trades were misfiltered (diverge between live and backtest)?
  - What's total P&L under each filter?
  - What's the actual-live win rate we should use for SPRT re-baseline?
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import sys

ROOT = Path(__file__).resolve().parent.parent
FWD = ROOT / "data/tracker/orb_forward_log.csv"

sys.path.insert(0, str(ROOT / "src"))
from mers_v3_peb import compute_atr


def live_filter(session, or_range, atr):
    """LIVE dispatch_orb.py:528 with default 2.0."""
    or_max = 2.0 * atr  # NY/ASIA hit default; LON explicit but same
    return or_range > or_max


def backtest_filter(session, or_range, atr):
    """BACKTEST edge_session_orb_v7_final.py SESSION_CONFIG."""
    ratio = or_range / atr if atr > 0 else 0
    if session == "LON":
        return ratio > 2.0  # skip wide
    elif session == "NY":
        return ratio < 2.5  # skip narrow
    elif session == "ASIA":
        return 2.0 <= ratio <= 2.5  # skip dead zone
    return False


def main() -> None:
    bars5 = pd.read_csv(ROOT / "data/gc/GC_5m.csv", parse_dates=["ts"]).set_index("ts").sort_index()
    if bars5.index.tz is None:
        bars5.index = bars5.index.tz_localize("UTC")
    atr_series = compute_atr(bars5, 20)

    rows = []
    with open(FWD, newline="") as f:
        for r in csv.DictReader(f):
            if r["took_trade"] != "True":
                continue
            try:
                open_ts = pd.Timestamp(r["open_ts"])
                if open_ts.tz is None:
                    open_ts = open_ts.tz_localize("UTC")
                or_close_ts = open_ts + pd.Timedelta(minutes=30)  # 6 x 5m bars
                or_range = float(r["or_range"])
                session = r["session"]
                net_pnl = float(r["net_pnl"])
                # ATR at OR close
                mask = atr_series.index <= or_close_ts
                if not mask.any():
                    continue
                atr = float(atr_series.loc[atr_series.index <= or_close_ts].iloc[-1])
            except (ValueError, KeyError):
                continue

            live_skip = live_filter(session, or_range, atr)
            bt_skip = backtest_filter(session, or_range, atr)
            ratio = or_range / atr if atr > 0 else 0
            rows.append({
                "date": r["entry_ts"][:10],
                "session": session,
                "or_range": or_range,
                "atr": atr,
                "ratio": ratio,
                "net_pnl": net_pnl,
                "won": net_pnl > 0,
                "live_skip": live_skip,
                "backtest_skip": bt_skip,
                "diverges": live_skip != bt_skip,
            })

    if not rows:
        print("No taken trades found.")
        return

    total = len(rows)
    total_wins = sum(1 for r in rows if r["won"])
    total_pnl = sum(r["net_pnl"] for r in rows)
    diverge_count = sum(1 for r in rows if r["diverges"])

    print(f"n={total}  wins={total_wins} ({100*total_wins/total:.1f}%)  net=${total_pnl:,.0f}")
    print(f"Divergent trades (live != backtest filter): {diverge_count}/{total}")
    print()
    print(f"{'date':12s} {'sess':5s} {'OR':>7s} {'ATR':>7s} {'ratio':>6s} {'pnl':>7s}  live  backtest  ⇒ diverge")
    for r in rows:
        div_flag = "**" if r["diverges"] else "  "
        live_str = "SKIP" if r["live_skip"] else "PASS"
        bt_str = "SKIP" if r["backtest_skip"] else "PASS"
        print(f"{r['date']:12s} {r['session']:5s} {r['or_range']:7.2f} {r['atr']:7.2f} {r['ratio']:6.2f} {r['net_pnl']:7.0f}  {live_str:4s}  {bt_str:4s}      {div_flag}")

    print()
    print("=" * 70)
    print("COUNTERFACTUAL P&L UNDER EACH FILTER")
    print("=" * 70)
    # LIVE filter counterfactual: keep trades where live_skip=False
    live_kept = [r for r in rows if not r["live_skip"]]
    live_kept_wins = sum(1 for r in live_kept if r["won"])
    live_kept_pnl = sum(r["net_pnl"] for r in live_kept)
    print(f"  LIVE filter kept:      n={len(live_kept):2d}  wins={live_kept_wins} ({100*live_kept_wins/max(len(live_kept),1):.0f}%)  net=${live_kept_pnl:,.0f}")

    # BACKTEST filter counterfactual
    bt_kept = [r for r in rows if not r["backtest_skip"]]
    bt_kept_wins = sum(1 for r in bt_kept if r["won"])
    bt_kept_pnl = sum(r["net_pnl"] for r in bt_kept)
    print(f"  BACKTEST filter kept:  n={len(bt_kept):2d}  wins={bt_kept_wins} ({100*bt_kept_wins/max(len(bt_kept),1):.0f}%)  net=${bt_kept_pnl:,.0f}")

    # BOTH filters (intersection) - conservative
    both_kept = [r for r in rows if not r["live_skip"] and not r["backtest_skip"]]
    both_kept_wins = sum(1 for r in both_kept if r["won"])
    both_kept_pnl = sum(r["net_pnl"] for r in both_kept)
    print(f"  BOTH filters kept:     n={len(both_kept):2d}  wins={both_kept_wins} ({100*both_kept_wins/max(len(both_kept),1):.0f}%)  net=${both_kept_pnl:,.0f}")

    print()
    print("Interpretation:")
    print(f"  - What LIVE actually filtered vs what BACKTEST would have filtered.")
    print(f"  - Divergent rows are trades where live and backtest disagree.")
    print(f"  - 'Trade actually took' means live let it through (didn't apply the intended filter).")


if __name__ == "__main__":
    main()
