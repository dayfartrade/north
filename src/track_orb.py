"""Forward-result tracker for Session ORB trades."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

from data_gc import load as gc_load
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on, fetch_higher_tf_trend
from mers_v3_peb import compute_atr
from backtest import CONTRACT_SIZE, RT_COST_PER_CONTRACT

# Match the validated config
OR_BARS = 6
WATCH = 12
HOLD = 24
TP_MULT = 1.5
STOP_MULT = 1.0
REQUIRE_TREND = True

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "tracker" / "orb_forward_log.csv"
FORWARD_START = pd.Timestamp("2026-06-19", tz="UTC")


def resolve_orb(bars, atr, slope, open_ts):
    """Simulate one ORB attempt given an open timestamp."""
    if open_ts not in bars.index:
        # try nearest
        mask = bars.index >= open_ts
        if not mask.any():
            return None
        s_ts = bars.index[mask][0]
    else:
        s_ts = open_ts
    s_idx = bars.index.get_loc(s_ts)
    if s_idx + OR_BARS + WATCH + HOLD + 1 >= len(bars):
        return None
    or_window = bars.iloc[s_idx: s_idx + OR_BARS]
    or_high = float(or_window["high"].max())
    or_low = float(or_window["low"].min())
    or_range = or_high - or_low
    if or_range <= 0:
        return None
    cur_slope = float(slope.iloc[s_idx + OR_BARS - 1])
    if not np.isfinite(cur_slope):
        return None
    entry_dir = 0; entry_idx = None; entry_price = None
    for k in range(WATCH):
        i = s_idx + OR_BARS + k
        b = bars.iloc[i]
        hit_long = b["high"] >= or_high
        hit_short = b["low"] <= or_low
        if hit_long and hit_short:
            continue
        if hit_long:
            if not REQUIRE_TREND or cur_slope > 0:
                entry_dir = 1; entry_idx = i; entry_price = or_high
            break
        if hit_short:
            if not REQUIRE_TREND or cur_slope < 0:
                entry_dir = -1; entry_idx = i; entry_price = or_low
            break
    if entry_dir == 0:
        return {"open_ts": s_ts, "took_trade": False, "or_high": or_high, "or_low": or_low,
                "or_range": or_range, "trend_slope": cur_slope}
    stop_lvl = entry_price - STOP_MULT * or_range * entry_dir
    target_lvl = entry_price + TP_MULT * or_range * entry_dir
    exit_price = None; exit_idx = None
    mae_dollars = 0.0  # max adverse excursion (positive = against position)
    mfe_dollars = 0.0  # max favorable excursion
    mae_price_distance = 0.0  # in price units, for stop-geometry analysis
    mfe_price_distance = 0.0
    for k in range(HOLD + 1):
        if entry_idx + k >= len(bars): break
        b = bars.iloc[entry_idx + k]
        # Track excursions BEFORE checking exit hit — captures intrabar adverse moves
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
        if adverse > mae_price_distance:
            mae_price_distance = adverse
            mae_dollars = adverse * CONTRACT_SIZE
        if favorable > mfe_price_distance:
            mfe_price_distance = favorable
            mfe_dollars = favorable * CONTRACT_SIZE
        if hit_stop and hit_tp:
            exit_price = stop_lvl; exit_idx = entry_idx + k; break
        if hit_stop:
            exit_price = stop_lvl; exit_idx = entry_idx + k; break
        if hit_tp:
            exit_price = target_lvl; exit_idx = entry_idx + k; break
    if exit_price is None:
        exit_idx = min(entry_idx + HOLD, len(bars) - 1)
        exit_price = float(bars.iloc[exit_idx]["close"])
    gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
    net = gross - RT_COST_PER_CONTRACT
    return {
        "open_ts": s_ts, "took_trade": True,
        "or_high": or_high, "or_low": or_low, "or_range": or_range,
        "trend_slope": cur_slope, "direction": entry_dir,
        "entry_ts": bars.index[entry_idx], "exit_ts": bars.index[exit_idx],
        "entry_price": float(entry_price), "exit_price": float(exit_price),
        "stop_price": float(stop_lvl), "target_price": float(target_lvl),
        "gross_pnl": float(gross), "net_pnl": float(net),
        "mae_dollars": float(mae_dollars), "mfe_dollars": float(mfe_dollars),
        "mae_price_distance": float(mae_price_distance),
        "mfe_price_distance": float(mfe_price_distance),
    }


def main():
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None: bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    slope = fetch_higher_tf_trend(bars)

    if LOG.exists():
        existing = pd.read_csv(LOG, parse_dates=["open_ts"])
        existing_keys = set(str(r["open_ts"]) + "|" + str(r.get("session", "")) for _, r in existing.iterrows())
    else:
        existing = pd.DataFrame()
        existing_keys = set()

    now = pd.Timestamp.now(tz="UTC")
    rows = []
    # Iterate from FORWARD_START to now; resolve each (date, session) ORB
    cur = FORWARD_START
    while cur.date() <= now.date():
        # Skip weekends (GC closed Sat all day, Sun before 18:00 ET)
        if cur.weekday() == 5:  # Saturday
            cur += pd.Timedelta(days=1)
            continue
        for sess_name in SESSIONS_LOCAL:
            # DST-aware per-date session UTC time
            sess_t = session_utc_time_on(cur.date(), sess_name)
            open_ts = pd.Timestamp.combine(cur.date(), sess_t).tz_localize("UTC")
            resolve_by = open_ts + pd.Timedelta(minutes=5 * (OR_BARS + WATCH + HOLD + 5))
            if now < resolve_by:
                continue
            key = f"{open_ts.isoformat()}|{sess_name}"
            if key in existing_keys:
                continue
            res = resolve_orb(bars, atr, slope, open_ts)
            if res is None:
                continue
            res["session"] = sess_name
            rows.append(res)
        cur += pd.Timedelta(days=1)

    if not rows:
        print(f"[track_orb] no new ORB events to resolve since {FORWARD_START.date()}")
        return
    new_df = pd.DataFrame(rows)
    if not existing.empty:
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = new_df
    merged = merged.drop_duplicates(subset=["open_ts", "session"]).sort_values("open_ts")
    merged.to_csv(LOG, index=False)

    taken = merged[merged["took_trade"] == True]
    print(f"[track_orb] +{len(rows)} resolved.  total resolved: {len(merged)}  taken: {len(taken)}")
    if not taken.empty:
        n = len(taken)
        wins = (taken["net_pnl"] > 0).sum()
        total = taken["net_pnl"].sum()
        print(f"  ORB live: n={n}  wins={wins}/{n} ({wins/n*100:.1f}%)  total=${total:+.0f}  mean=${taken['net_pnl'].mean():+.2f}")


if __name__ == "__main__":
    main()
