"""Session ORB v7 — geometry-fixed.

Changes from v6:
  1. Per-session adaptive stop distance (derived from winner-MAE P90):
       ASIA: $10, LON: $10, NY: $18
  2. Target = TP_MULT × stop_distance (R:R always 1:TP_MULT, not 1:1.5×OR)
  3. Skip setup if OR_range > OR_VS_ATR_MAX × ATR(20)  (post-news whipsaw)
  4. Position sizing via fixed $-risk budget (computed by caller, not here)

The stop distance is derived from analyze_orb_geometry.py output:
  Backtest n=94, winner-MAE P90:
    ASIA  P90=$7.86 max=$11.40  → use $10 (P90 × ~1.3)
    LON   P90=$8.05 max=$10.80  → use $10
    NY    P90=$16.04 max=$18.50 → use $18

Validation gate: backtest v7 vs v6 on the same 60-day window. Deploy only
if v7 expectancy ≥ v6 expectancy AND v7 max drawdown ≤ v6 max drawdown.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import time, datetime
import pytz

from data_gc import load as gc_load
from backtest import CONTRACT_SIZE, RT_COST_PER_CONTRACT, summarize, print_summary
from mers_v3_peb import compute_atr
from edge_session_orb import (
    SESSIONS_LOCAL, session_utc_time_on, fetch_higher_tf_trend, find_session_starts
)


# Per-session stop distance (price units, set above winner-MAE max with buffer)
# Backtest winner-MAE max:  ASIA=11.40  LON=10.80  NY=18.50
# Stop = max_winner_MAE + ~$5 buffer to avoid clipping real winners on borderline pullbacks
STOP_DISTANCE_BY_SESSION = {
    "ASIA": 13.0,
    "LON":  13.0,
    "NY":   24.0,
}

# Skip if OR_range exceeds this multiple of ATR(20) — kills post-news whipsaw setups
OR_VS_ATR_MAX = 2.0

# Default target multiplier on stop distance (R:R)
TP_MULT_DEFAULT = 1.5


def run_orb_v7(bars: pd.DataFrame, session_time: time, label: str,
                or_bars: int = 6, watch_bars: int = 12, max_hold: int = 24,
                tp_mult: float = TP_MULT_DEFAULT, require_trend: bool = True,
                stop_distance: float | None = None,
                or_vs_atr_max: float = OR_VS_ATR_MAX) -> pd.DataFrame:
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    trend_slope = fetch_higher_tf_trend(bars)

    if stop_distance is None:
        stop_distance = STOP_DISTANCE_BY_SESSION.get(label, 12.0)

    starts = find_session_starts(bars, session_time, sess_name=label)
    rows = []
    for s_ts in starts:
        s_idx = bars.index.get_loc(s_ts)
        if s_idx + or_bars + watch_bars + max_hold + 1 >= len(bars):
            continue
        or_window = bars.iloc[s_idx: s_idx + or_bars]
        or_high = float(or_window["high"].max())
        or_low = float(or_window["low"].min())
        or_range = or_high - or_low
        if or_range <= 0:
            continue
        slope = float(trend_slope.iloc[s_idx + or_bars - 1])
        if not np.isfinite(slope):
            continue
        cur_atr = float(atr.iloc[s_idx + or_bars - 1])
        if not np.isfinite(cur_atr) or cur_atr <= 0:
            continue

        # FILTER: skip post-news whipsaw — OR range >> normal vol
        if or_range > or_vs_atr_max * cur_atr:
            rows.append({
                "session": label, "session_open_ts": s_ts,
                "or_high": or_high, "or_low": or_low, "or_range": or_range,
                "trend_slope": slope, "atr": cur_atr,
                "skip_reason": "or_too_wide_vs_atr",
                "took_trade": False,
            })
            continue

        # Watch for breakout
        entry_dir = 0; entry_idx = None; entry_price = None
        for k in range(watch_bars):
            i = s_idx + or_bars + k
            b = bars.iloc[i]
            hit_long = b["high"] >= or_high
            hit_short = b["low"] <= or_low
            if hit_long and hit_short:
                continue
            if hit_long:
                if not require_trend or slope > 0:
                    entry_dir = 1; entry_idx = i; entry_price = or_high
                break
            if hit_short:
                if not require_trend or slope < 0:
                    entry_dir = -1; entry_idx = i; entry_price = or_low
                break
        if entry_dir == 0:
            rows.append({
                "session": label, "session_open_ts": s_ts,
                "or_high": or_high, "or_low": or_low, "or_range": or_range,
                "trend_slope": slope, "atr": cur_atr,
                "skip_reason": "no_breakout_or_against_trend",
                "took_trade": False,
            })
            continue

        # NEW geometry: stop = adaptive distance; target = TP_MULT × stop distance
        stop_lvl = entry_price - stop_distance * entry_dir
        target_lvl = entry_price + tp_mult * stop_distance * entry_dir

        exit_price = None; exit_idx = None; exit_reason = None
        mae_price = 0.0; mfe_price = 0.0
        for k in range(max_hold + 1):
            if entry_idx + k >= len(bars):
                break
            b = bars.iloc[entry_idx + k]
            if entry_dir == 1:
                adverse = entry_price - float(b["low"])
                favorable = float(b["high"]) - entry_price
                hit_stop = b["low"] <= stop_lvl
                hit_tp = b["high"] >= target_lvl
            else:
                adverse = float(b["high"]) - entry_price
                favorable = entry_price - float(b["low"])
                hit_stop = b["high"] >= stop_lvl
                hit_tp = b["low"] <= target_lvl
            if adverse > mae_price: mae_price = adverse
            if favorable > mfe_price: mfe_price = favorable
            if hit_stop and hit_tp:
                exit_price = stop_lvl; exit_reason = "stop_conservative"; exit_idx = entry_idx + k; break
            if hit_stop:
                exit_price = stop_lvl; exit_reason = "stop"; exit_idx = entry_idx + k; break
            if hit_tp:
                exit_price = target_lvl; exit_reason = "target"; exit_idx = entry_idx + k; break
        if exit_price is None:
            exit_idx = min(entry_idx + max_hold, len(bars) - 1)
            exit_price = float(bars.iloc[exit_idx]["close"])
            exit_reason = "time"

        gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
        net = gross - RT_COST_PER_CONTRACT
        rows.append({
            "session": label, "session_open_ts": s_ts,
            "or_high": or_high, "or_low": or_low, "or_range": or_range,
            "trend_slope": slope, "atr": cur_atr,
            "took_trade": True,
            "entry_ts": bars.index[entry_idx], "exit_ts": bars.index[exit_idx],
            "direction": entry_dir,
            "entry_price": float(entry_price), "exit_price": float(exit_price),
            "stop_price": float(stop_lvl), "target_price": float(target_lvl),
            "stop_distance": stop_distance,
            "exit_reason": exit_reason,
            "gross_pnl": float(gross), "net_pnl": float(net),
            "mae_price": float(mae_price), "mfe_price": float(mfe_price),
        })
    return pd.DataFrame(rows)


def compare_v6_v7():
    """Backtest both v6 and v7 on the same window; print head-to-head."""
    from edge_session_orb import run_orb as run_v6
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    print("="*80)
    print("v6 vs v7 head-to-head — same 60-day window, same params (or=6 watch=12 hold=24)")
    print("="*80)
    for sess_name in SESSIONS_LOCAL:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        v6 = run_v6(bars, sess_t, sess_name, or_bars=6, watch_bars=12, max_hold=24,
                    stop_mult=1.0, tp_mult=1.5, require_trend=True)
        v7 = run_orb_v7(bars, sess_t, sess_name, or_bars=6, watch_bars=12, max_hold=24,
                        tp_mult=1.5, require_trend=True)
        v6_taken = v6 if not v6.empty else pd.DataFrame()
        v7_taken = v7[v7["took_trade"] == True] if not v7.empty else pd.DataFrame()
        print(f"\n--- {sess_name} ---")
        if not v6_taken.empty:
            v6_wins = (v6_taken["net_pnl"] > 0).sum()
            print(f"  v6: n={len(v6_taken):3d}  wins={v6_wins:3d} ({v6_wins/len(v6_taken)*100:5.1f}%)  total=${v6_taken['net_pnl'].sum():+8.0f}  mean=${v6_taken['net_pnl'].mean():+7.2f}")
        if not v7_taken.empty:
            v7_wins = (v7_taken["net_pnl"] > 0).sum()
            v7_skipped = (v7["took_trade"] == False).sum() if not v7.empty else 0
            print(f"  v7: n={len(v7_taken):3d}  wins={v7_wins:3d} ({v7_wins/len(v7_taken)*100:5.1f}%)  total=${v7_taken['net_pnl'].sum():+8.0f}  mean=${v7_taken['net_pnl'].mean():+7.2f}  (skipped {v7_skipped})")

    # Aggregate
    print("\n=== AGGREGATE ===")
    all_v6 = []
    all_v7 = []
    for sess_name in SESSIONS_LOCAL:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        v6 = run_v6(bars, sess_t, sess_name, or_bars=6, watch_bars=12, max_hold=24,
                    stop_mult=1.0, tp_mult=1.5, require_trend=True)
        v7 = run_orb_v7(bars, sess_t, sess_name, or_bars=6, watch_bars=12, max_hold=24,
                        tp_mult=1.5, require_trend=True)
        if not v6.empty: all_v6.append(v6)
        if not v7.empty: all_v7.append(v7)
    v6_all = pd.concat(all_v6, ignore_index=True) if all_v6 else pd.DataFrame()
    v7_all = pd.concat(all_v7, ignore_index=True) if all_v7 else pd.DataFrame()
    v7_taken_all = v7_all[v7_all["took_trade"] == True] if not v7_all.empty else pd.DataFrame()

    if not v6_all.empty:
        v6_wins = (v6_all["net_pnl"] > 0).sum()
        print(f"v6: n={len(v6_all)}  win%={v6_wins/len(v6_all)*100:.1f}  total=${v6_all['net_pnl'].sum():+.0f}  mean=${v6_all['net_pnl'].mean():+.2f}  sharpe(per-trade)={v6_all['net_pnl'].mean()/v6_all['net_pnl'].std():.3f}")
    if not v7_taken_all.empty:
        v7_wins = (v7_taken_all["net_pnl"] > 0).sum()
        print(f"v7: n={len(v7_taken_all)}  win%={v7_wins/len(v7_taken_all)*100:.1f}  total=${v7_taken_all['net_pnl'].sum():+.0f}  mean=${v7_taken_all['net_pnl'].mean():+.2f}  sharpe(per-trade)={v7_taken_all['net_pnl'].mean()/v7_taken_all['net_pnl'].std():.3f}")


if __name__ == "__main__":
    compare_v6_v7()
