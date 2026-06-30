"""Sweep v7 variants to isolate which change drives the improvement.

Variants:
  v6     : original (stop=OR, target=1.5×OR)
  v7a    : OR_VS_ATR filter only (stop=OR, target=1.5×OR)
  v7b    : Per-session adaptive stop + filter (current v7)
  v7c    : Adaptive stop + filter + target = max(1.5×stop, OR_range)
  v7d    : Filter only with stricter threshold (1.5×ATR)
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
from edge_session_orb import run_orb as run_v6, SESSIONS_LOCAL, session_utc_time_on, fetch_higher_tf_trend, find_session_starts
from mers_v3_peb import compute_atr
from backtest import CONTRACT_SIZE, RT_COST_PER_CONTRACT


def run_variant(bars, session_time, label, *,
                stop_mode="or_range",        # "or_range" | "adaptive"
                target_mode="or_range",      # "or_range" | "stop_x_tp" | "max"
                use_or_filter=False,
                or_vs_atr_max=2.0,
                or_bars=6, watch_bars=12, max_hold=24,
                stop_distances=None,
                tp_mult=1.5, require_trend=True):
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    trend_slope = fetch_higher_tf_trend(bars)
    starts = find_session_starts(bars, session_time, sess_name=label)
    stop_distances = stop_distances or {"ASIA": 13.0, "LON": 13.0, "NY": 24.0}
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
        if use_or_filter and or_range > or_vs_atr_max * cur_atr:
            continue
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
            continue

        if stop_mode == "or_range":
            stop_dist = or_range
        else:
            stop_dist = stop_distances.get(label, 15.0)
        stop_lvl = entry_price - stop_dist * entry_dir

        if target_mode == "or_range":
            target_dist = tp_mult * or_range
        elif target_mode == "stop_x_tp":
            target_dist = tp_mult * stop_dist
        else:  # "max"
            target_dist = max(tp_mult * stop_dist, or_range)
        target_lvl = entry_price + target_dist * entry_dir

        exit_price = None; exit_idx = None
        for k in range(max_hold + 1):
            if entry_idx + k >= len(bars): break
            b = bars.iloc[entry_idx + k]
            if entry_dir == 1:
                hit_stop = b["low"] <= stop_lvl
                hit_tp = b["high"] >= target_lvl
            else:
                hit_stop = b["high"] >= stop_lvl
                hit_tp = b["low"] <= target_lvl
            if hit_stop:
                exit_price = stop_lvl; exit_idx = entry_idx + k; break
            if hit_tp:
                exit_price = target_lvl; exit_idx = entry_idx + k; break
        if exit_price is None:
            exit_idx = min(entry_idx + max_hold, len(bars) - 1)
            exit_price = float(bars.iloc[exit_idx]["close"])
        gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
        net = gross - RT_COST_PER_CONTRACT
        rows.append({"session": label, "net_pnl": net, "gross_pnl": gross})
    return pd.DataFrame(rows)


def summarize_variant(name, run_per_session):
    parts = []
    total = 0
    n_total = 0
    wins_total = 0
    for sess, df in run_per_session.items():
        if df.empty:
            parts.append(f"{sess}:n=0")
            continue
        n = len(df); wins = (df["net_pnl"] > 0).sum()
        total += df["net_pnl"].sum()
        n_total += n; wins_total += wins
        parts.append(f"{sess}:n={n} {wins/n*100:.0f}% ${df['net_pnl'].sum():+.0f}")
    pnl_all = pd.concat([d for d in run_per_session.values() if not d.empty], ignore_index=True) if run_per_session else pd.DataFrame()
    if pnl_all.empty:
        return
    mean = pnl_all["net_pnl"].mean()
    sd = pnl_all["net_pnl"].std()
    sharpe = mean / sd if sd > 0 else 0
    print(f"{name:6s}  n={n_total:3d}  win%={wins_total/n_total*100:5.1f}  total=${total:+7.0f}  mean=${mean:+7.2f}  sharpe(pt)={sharpe:+.3f}  |  " + "  ".join(parts))


def main():
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    variants = {
        "v6":  dict(stop_mode="or_range",  target_mode="or_range",  use_or_filter=False),
        "v7a": dict(stop_mode="or_range",  target_mode="or_range",  use_or_filter=True,  or_vs_atr_max=2.0),
        "v7b": dict(stop_mode="adaptive",  target_mode="stop_x_tp", use_or_filter=True,  or_vs_atr_max=2.0),
        "v7c": dict(stop_mode="adaptive",  target_mode="max",       use_or_filter=True,  or_vs_atr_max=2.0),
        "v7d": dict(stop_mode="or_range",  target_mode="or_range",  use_or_filter=True,  or_vs_atr_max=1.5),
        "v7e": dict(stop_mode="adaptive",  target_mode="or_range",  use_or_filter=True,  or_vs_atr_max=2.0),
    }
    print(f"{'name':6s}  {'agg':<40s}  per-session breakdown")
    print("-" * 130)
    for name, params in variants.items():
        per_sess = {}
        for sess_name in SESSIONS_LOCAL:
            sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
            per_sess[sess_name] = run_variant(bars, sess_t, sess_name, **params)
        summarize_variant(name, per_sess)


if __name__ == "__main__":
    main()
