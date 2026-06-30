"""Session ORB v7 — hybrid per-session geometry (PRODUCTION CANDIDATE).

Backtest finding (60-day window): a single rule that improves all three
sessions does not exist. Per-session optimal:

  ASIA: v6 (OR-range stop, OR-range target, no filter)
        n=30  win=57%  total=+$15,205  mean=+$507
  LON:  v7 (filter OR<2×ATR, adaptive stop $13, target 1.5×stop)
        n=8   win=75%  total=+$7,028   mean=+$879
  NY:   v6 (OR-range stop, OR-range target, no filter)
        n=34  win=44%  total=+$3,674   mean=+$108

Combined projected total: ~$25,907 vs v6 unified +$18,499 (+40%).

Live replay (n=11 since 2026-06-19): original -$6,784 → hybrid +$773 (delta +$7,557).
The filter skipped 3 high-vol LON setups that became -$7,737 in production.

⚠  STATUS: Validated on backtest + live replay. Pending Phase 7
   (bootstrap CI, 80/20 holdout) before going live.

PER-SESSION CONFIG IS THE PUBLIC API of this module.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import time, datetime
import pytz

from data_gc import load as gc_load
from backtest import CONTRACT_SIZE, RT_COST_PER_CONTRACT
from mers_v3_peb import compute_atr
from edge_session_orb import (
    SESSIONS_LOCAL, session_utc_time_on, fetch_higher_tf_trend, find_session_starts
)
from stand_down import stand_down_for_entry, _load_calendar


SESSION_CONFIG = {
    "ASIA": {
        "use_or_filter": False,
        "stop_mode": "or_range",     # "or_range" | "fixed"
        "fixed_stop_price": None,
        "target_mode": "or_range",   # "or_range" | "stop_x_tp"
    },
    "LON": {
        "use_or_filter": True,
        "or_vs_atr_max": 2.0,
        "stop_mode": "fixed",
        "fixed_stop_price": 13.0,
        "target_mode": "stop_x_tp",
    },
    "NY": {
        "use_or_filter": False,
        "stop_mode": "or_range",
        "fixed_stop_price": None,
        "target_mode": "or_range",
    },
}
TP_MULT_DEFAULT = 1.5


def run_orb_v7(bars: pd.DataFrame, session_time: time, label: str,
                or_bars: int = 6, watch_bars: int = 12, max_hold: int = 24,
                tp_mult: float = TP_MULT_DEFAULT, require_trend: bool = True,
                config: dict | None = None,
                apply_stand_down: bool = True) -> pd.DataFrame:
    cfg = (config or SESSION_CONFIG.get(label, SESSION_CONFIG["NY"]))
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    trend_slope = fetch_higher_tf_trend(bars)
    cal = _load_calendar() if apply_stand_down else None

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
        cur_atr = float(atr.iloc[s_idx + or_bars - 1])
        if not (np.isfinite(slope) and np.isfinite(cur_atr) and cur_atr > 0):
            continue

        # OR vs ATR filter
        if cfg.get("use_or_filter", False):
            if or_range > cfg.get("or_vs_atr_max", 2.0) * cur_atr:
                rows.append({
                    "session": label, "session_open_ts": s_ts,
                    "or_high": or_high, "or_low": or_low, "or_range": or_range,
                    "trend_slope": slope, "atr": cur_atr,
                    "took_trade": False, "skip_reason": "or_too_wide_vs_atr",
                })
                continue

        # Watch for breakout
        entry_dir = 0; entry_idx = None; entry_price = None
        stand_down_skipped = 0
        for k in range(watch_bars):
            i = s_idx + or_bars + k
            b = bars.iloc[i]
            hit_long = b["high"] >= or_high
            hit_short = b["low"] <= or_low
            if hit_long and hit_short:
                continue
            if hit_long or hit_short:
                # Stand-down check at entry time — skip news/fix windows, keep watching
                if apply_stand_down:
                    sd, _ = stand_down_for_entry(bars.index[i], cal)
                    if sd:
                        stand_down_skipped += 1
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
                "took_trade": False, "skip_reason": "no_breakout",
            })
            continue

        # Geometry per config
        if cfg.get("stop_mode") == "fixed":
            stop_dist = float(cfg["fixed_stop_price"])
        else:
            stop_dist = or_range
        if cfg.get("target_mode") == "stop_x_tp":
            target_dist = tp_mult * stop_dist
        else:
            target_dist = tp_mult * or_range

        stop_lvl = entry_price - stop_dist * entry_dir
        target_lvl = entry_price + target_dist * entry_dir

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
            "stop_distance": stop_dist, "target_distance": target_dist,
            "exit_reason": exit_reason,
            "gross_pnl": float(gross), "net_pnl": float(net),
            "mae_price": float(mae_price), "mfe_price": float(mfe_price),
        })
    return pd.DataFrame(rows)


def run_all_sessions() -> pd.DataFrame:
    """Run v7-hybrid across all configured sessions, return concatenated trades."""
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    all_df = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        if not df.empty:
            all_df.append(df)
    return pd.concat(all_df, ignore_index=True) if all_df else pd.DataFrame()


if __name__ == "__main__":
    df = run_all_sessions()
    taken = df[df["took_trade"] == True] if not df.empty else df
    if not taken.empty:
        n = len(taken); wins = (taken["net_pnl"] > 0).sum()
        print(f"v7-hybrid backtest: n={n}  win%={wins/n*100:.1f}  total=${taken['net_pnl'].sum():+.0f}  mean=${taken['net_pnl'].mean():+.2f}")
        for sess in sorted(taken["session"].unique()):
            sub = taken[taken["session"] == sess]
            sw = (sub["net_pnl"] > 0).sum()
            print(f"  {sess:5s} n={len(sub):3d} win={sw}/{len(sub)} ({sw/len(sub)*100:5.1f}%)  total=${sub['net_pnl'].sum():+8.0f}  mean=${sub['net_pnl'].mean():+8.2f}")
