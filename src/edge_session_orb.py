"""Session Opening Range Breakout (ORB) on 5m bars.

Logic per session:
  1. Identify opening range = first OR_BARS 5m bars after session open
  2. Watch next WATCH_BARS for breakout above OR.high or below OR.low
  3. Apply higher-TF trend filter (1h EMA50 slope) — trade only with trend
  4. Stop = opposite side of OR (entry-side - range for longs, +range for shorts)
  5. Target = TP_MULT × OR range
  6. Time exit at MAX_HOLD bars

Sessions tested (UTC):
  - London open ~07:00 UTC summer (08:00 UK)
  - NY open    ~13:30 UTC summer (09:30 ET)
  - Asia open  ~23:00 UTC summer (08:00 Tokyo)

Outputs trade DataFrame compatible with backtest.summarize().
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import time, datetime
import pytz

from data_gc import load as gc_load
from backtest import CONTRACT_SIZE, RT_COST_PER_CONTRACT, summarize, print_summary
from mers_v3_peb import compute_atr


# Session opens defined in LOCAL TIME so DST transitions are handled correctly.
# Each entry: (local_tz, local_time). UTC time is computed per-date.
LON_TZ = pytz.timezone("Europe/London")
NY_TZ = pytz.timezone("America/New_York")
JST_TZ = pytz.timezone("Asia/Tokyo")

SESSIONS_LOCAL = {
    "LON":  (LON_TZ, time(8, 0)),    # London FX open 08:00 UK
    "NY":   (NY_TZ,  time(9, 30)),   # NY equities open 09:30 ET
    "ASIA": (JST_TZ, time(8, 0)),    # Tokyo morning 08:00 JST
}


def session_utc_time_on(date: datetime.date, sess_name: str) -> time:
    """Return the UTC time-of-day for a session on a given date.
    Handles DST transitions automatically."""
    tz, local_t = SESSIONS_LOCAL[sess_name]
    local_dt = tz.localize(datetime.combine(date, local_t))
    utc_dt = local_dt.astimezone(pytz.UTC)
    return utc_dt.time()


# Backward-compat: SESSIONS dict with CURRENT UTC times (used by backtest only)
# For LIVE dispatch, use session_utc_time_on() per-date.
SESSIONS = {
    name: session_utc_time_on(datetime.now(pytz.UTC).date(), name)
    for name in SESSIONS_LOCAL
}


def fetch_higher_tf_trend(bars_5m: pd.DataFrame) -> pd.Series:
    """Compute 1h-equivalent EMA-50 slope by resampling 5m to 1h."""
    bars_1h = bars_5m["close"].resample("1h").last().dropna()
    ema = bars_1h.ewm(span=50, adjust=False).mean()
    slope = ema.diff(5)
    # Forward-fill back to 5m granularity
    slope_5m = slope.reindex(bars_5m.index, method="ffill")
    return slope_5m


def find_session_starts(bars: pd.DataFrame, session_time: time,
                         sess_name: str | None = None) -> list[pd.Timestamp]:
    """Return the 5m-bar timestamps matching each session open on each day.

    If sess_name is provided, computes the correct UTC time-of-day per-date
    (DST-aware). Otherwise falls back to fixed session_time match.
    """
    idx = bars.index
    if sess_name is None or sess_name not in SESSIONS_LOCAL:
        return [ts for ts in idx if ts.time() == session_time]
    # DST-aware: per-date compute expected UTC time-of-day, then match
    out = []
    seen_dates = set()
    for ts in idx:
        d = ts.date()
        if d in seen_dates:
            continue
        expected = session_utc_time_on(d, sess_name)
        # Find the bar on this date matching expected UTC time
        for cand in idx:
            if cand.date() == d and cand.time() == expected:
                out.append(cand)
                break
        seen_dates.add(d)
    return out


def run_orb(bars: pd.DataFrame, session_time: time, label: str,
             or_bars: int = 6, watch_bars: int = 18, max_hold: int = 24,
             stop_mult: float = 1.0, tp_mult: float = 1.5,
             require_trend: bool = True) -> pd.DataFrame:
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    trend_slope = fetch_higher_tf_trend(bars)

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
        # Trend
        slope = float(trend_slope.iloc[s_idx + or_bars - 1])
        if not np.isfinite(slope):
            continue

        # Watch for breakout in bars [s_idx + or_bars, s_idx + or_bars + watch_bars)
        entry_dir = 0
        entry_idx = None
        entry_price = None
        for k in range(watch_bars):
            i = s_idx + or_bars + k
            b = bars.iloc[i]
            hit_long = b["high"] >= or_high
            hit_short = b["low"] <= or_low
            if hit_long and hit_short:
                continue  # ambiguous; keep watching
            if hit_long:
                if not require_trend or slope > 0:
                    entry_dir = 1
                    entry_idx = i
                    entry_price = or_high
                break
            if hit_short:
                if not require_trend or slope < 0:
                    entry_dir = -1
                    entry_idx = i
                    entry_price = or_low
                break

        if entry_dir == 0:
            continue

        # Exit: stop = opposite side of OR × stop_mult; target = tp_mult × OR range
        stop_lvl = entry_price - stop_mult * or_range * entry_dir
        target_lvl = entry_price + tp_mult * or_range * entry_dir
        exit_price = None
        exit_idx = None
        exit_reason = None
        mae_price = 0.0  # max adverse excursion (price units, positive = against)
        mfe_price = 0.0  # max favorable excursion
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
            if adverse > mae_price:
                mae_price = adverse
            if favorable > mfe_price:
                mfe_price = favorable
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
            "session": label,
            "session_open_ts": s_ts,
            "or_high": or_high,
            "or_low": or_low,
            "or_range": or_range,
            "trend_slope": slope,
            "entry_ts": bars.index[entry_idx],
            "exit_ts": bars.index[exit_idx],
            "direction": entry_dir,
            "entry_price": float(entry_price),
            "exit_price": float(exit_price),
            "exit_reason": exit_reason,
            "gross_pnl": float(gross),
            "net_pnl": float(net),
            "mae_price": float(mae_price),
            "mfe_price": float(mfe_price),
            "mae_dollars": float(mae_price * CONTRACT_SIZE),
            "mfe_dollars": float(mfe_price * CONTRACT_SIZE),
        })
    return pd.DataFrame(rows)


def main():
    print("="*100)
    print("Session ORB on 5m bars (60-day window)")
    print("="*100)
    bars = gc_load("5m")
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    # Sweep parameters
    print(f"\n{'session':<6s} {'or':>3s} {'watch':>5s} {'hold':>4s} {'tp':>4s} {'n':>4s} {'win%':>6s} {'mean_$':>10s} {'total_$':>10s} {'sharpe':>7s}")
    best_by_session = {}
    for sess_name, sess_time in SESSIONS.items():
        for or_bars in (3, 6, 12):
            for watch in (6, 12, 24):
                for hold in (12, 24, 48):
                    for tp in (1.0, 1.5, 2.0):
                        trades = run_orb(bars, sess_time, sess_name,
                                          or_bars=or_bars, watch_bars=watch,
                                          max_hold=hold, tp_mult=tp,
                                          require_trend=True)
                        s = summarize(trades, label=f"{sess_name}|or={or_bars}|w={watch}|h={hold}|tp={tp}")
                        if s["n"] >= 8:
                            print(f"{sess_name:<6s} {or_bars:>3d} {watch:>5d} {hold:>4d} {tp:>4.1f} "
                                  f"{s['n']:>4d} {s['win_rate']*100:>6.1f} "
                                  f"{s['mean_net_pnl']:+10.2f} {s['total_net_pnl']:+10.0f} {s['sharpe_per_trade']:+7.2f}")
                            if best_by_session.get(sess_name) is None or s["total_net_pnl"] > best_by_session[sess_name]["total_net_pnl"]:
                                best_by_session[sess_name] = s

    print("\nBest per session:")
    for name, s in best_by_session.items():
        print_summary(s)


if __name__ == "__main__":
    main()
