"""Per-trade journal: snapshot full context for each event so we can post-mortem.

For each resolved event (whether traded or skipped), we capture:
  - Event metadata (type, ts, surprise z if known)
  - Market context (pre-event close, ATR, EMA slope, volume_ratio, regime)
  - Decision (took_trade, direction, trigger_levels, stop/target)
  - Outcome (entry, exit, exit_reason, gross/net P&L, MFE/MAE during hold)
  - What-if (what would the OTHER direction have done, what would a longer hold have done)

Output: data/tracker/journal.csv

This lets us later answer questions like:
  - Are we losing on a particular event type?
  - Are stops too tight / targets too far?
  - Is the trend filter rejecting profitable setups?
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v3_peb import compute_atr
from mers_v5 import (TOP_EVENTS_V5, WATCH, MAX_HOLD, B_ATR, STOP_MULT, TP_MULT,
                       TREND_N, dedupe_co_released, peb_event_v5)


ROOT = Path(__file__).resolve().parent.parent
JOURNAL = ROOT / "data" / "tracker" / "journal.csv"
FORWARD_START = pd.Timestamp("2026-06-19", tz="UTC")


def _bar_index_containing(bars, ts):
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    mask = (bars.index <= ts) & (bars.index + freq > ts)
    matches = bars.index[mask]
    if len(matches) == 0:
        return None
    return bars.index.get_loc(matches[-1])


def what_if_other_direction(bars, i, ev_high, ev_low, pre_atr, original_dir):
    """If we had taken the opposite breakout (no trend filter), what P&L?"""
    if i is None or i + WATCH + MAX_HOLD + 1 >= len(bars):
        return None
    buffer = B_ATR * pre_atr
    if original_dir == 1:
        trig = ev_low - buffer
        opp_dir = -1
    else:
        trig = ev_high + buffer
        opp_dir = 1
    entry_idx = None
    for k in range(1, WATCH + 1):
        b = bars.iloc[i + k]
        if opp_dir == -1 and b["low"] <= trig:
            entry_idx = i + k
            break
        if opp_dir == 1 and b["high"] >= trig:
            entry_idx = i + k
            break
    if entry_idx is None:
        return None
    rng = ev_high - ev_low
    stop = trig - STOP_MULT * rng * opp_dir
    tgt = trig + TP_MULT * rng * opp_dir
    for k in range(0, MAX_HOLD + 1):
        if entry_idx + k >= len(bars):
            break
        b = bars.iloc[entry_idx + k]
        if opp_dir == 1:
            if b["low"] <= stop:
                return (stop - trig) * opp_dir * 100 - 24
            if b["high"] >= tgt:
                return (tgt - trig) * opp_dir * 100 - 24
        else:
            if b["high"] >= stop:
                return (stop - trig) * opp_dir * 100 - 24
            if b["low"] <= tgt:
                return (tgt - trig) * opp_dir * 100 - 24
    ix = min(entry_idx + MAX_HOLD, len(bars) - 1)
    return (bars.iloc[ix]["close"] - trig) * opp_dir * 100 - 24


def mfe_mae(bars, entry_idx, exit_idx, entry_price, direction):
    """Maximum favorable excursion / max adverse excursion during hold."""
    if entry_idx is None:
        return None, None
    sub = bars.iloc[entry_idx:exit_idx + 1]
    if direction == 1:
        mfe = (sub["high"].max() - entry_price) * 100
        mae = (sub["low"].min() - entry_price) * 100
    else:
        mfe = (entry_price - sub["low"].min()) * 100
        mae = (entry_price - sub["high"].max()) * 100
    return float(mfe), float(mae)


def journal_event(bars, atr, slope, ema, ev) -> dict:
    ev_ts = pd.Timestamp(ev["ts_utc"]).tz_convert("UTC")
    i = _bar_index_containing(bars, ev_ts)
    out = {
        "event_ts": ev_ts,
        "event_type": ev["event"],
        "logged_at": pd.Timestamp.now(tz="UTC"),
    }
    if i is None:
        out["status"] = "no_bar"
        return out
    pre_atr = float(atr.iloc[i - 1]) if i > 0 else float("nan")
    slp = float(slope.iloc[i - 1]) if i > 0 else float("nan")
    ev_bar = bars.iloc[i]
    out.update({
        "pre_close": float(bars.iloc[i - 1]["close"]) if i > 0 else None,
        "ev_open": float(ev_bar["open"]),
        "ev_high": float(ev_bar["high"]),
        "ev_low": float(ev_bar["low"]),
        "ev_close": float(ev_bar["close"]),
        "ev_range": float(ev_bar["high"] - ev_bar["low"]),
        "pre_atr": pre_atr,
        "ema_slope": slp,
        "trend_dir": "UP" if slp > 0 else "DOWN" if slp < 0 else "FLAT",
    })
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    t = peb_event_v5(bars, ev_ts, freq, atr, slope)
    if t is None:
        out["status"] = "no_trade_taken"
        # Check if breakout occurred but trend filter blocked it
        buffer = B_ATR * pre_atr
        for k in range(1, WATCH + 1):
            if i + k >= len(bars):
                break
            b = bars.iloc[i + k]
            if b["high"] >= ev_bar["high"] + buffer:
                out["status_detail"] = "long_break_blocked_by_trend" if slp < 0 else "long_break_skipped_other"
                break
            if b["low"] <= ev_bar["low"] - buffer:
                out["status_detail"] = "short_break_blocked_by_trend" if slp > 0 else "short_break_skipped_other"
                break
        return out
    out["status"] = "traded"
    out["direction"] = t["direction"]
    out["entry_ts"] = t["entry_ts"]
    out["entry_price"] = t["entry_price"]
    out["exit_ts"] = t["exit_ts"]
    out["exit_price"] = t["exit_price"]
    out["stop_price"] = t["stop_price"]
    out["target_price"] = t["target_price"]
    out["exit_reason"] = t["exit_reason"]
    out["gross_pnl"] = t["gross_pnl"]
    out["net_pnl"] = t["net_pnl"]

    entry_idx = bars.index.get_loc(t["entry_ts"])
    exit_idx = bars.index.get_loc(t["exit_ts"])
    mfe, mae = mfe_mae(bars, entry_idx, exit_idx, t["entry_price"], t["direction"])
    out["mfe_dollars"] = mfe
    out["mae_dollars"] = mae

    # What-if other direction
    out["what_if_opp_dir_pnl"] = what_if_other_direction(
        bars, i, ev_bar["high"], ev_bar["low"], pre_atr, t["direction"]
    )
    return out


def main():
    bars = gc_load("60m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=TREND_N, adjust=False).mean()
    slope = ema.diff(5)
    cal = dedupe_co_released(build_all())

    # Existing journal
    if JOURNAL.exists():
        existing = pd.read_csv(JOURNAL, parse_dates=["event_ts"])
        existing_keys = set(existing["event_ts"].astype(str))
    else:
        existing = pd.DataFrame()
        existing_keys = set()

    rows = []
    for _, ev in cal.iterrows():
        if ev["event"] not in TOP_EVENTS_V5:
            continue
        ev_ts = pd.Timestamp(ev["ts_utc"]).tz_convert("UTC")
        # Skip future events
        if ev_ts + pd.Timedelta(hours=12) > pd.Timestamp.now(tz="UTC"):
            continue
        # Skip if already logged AND we have GC bar coverage (no need to re-log historical)
        # For HISTORICAL events, log them once (they don't change)
        key = str(ev_ts)
        if key in existing_keys:
            continue
        row = journal_event(bars, atr, slope, ema, ev)
        rows.append(row)

    if not rows:
        print("[journal] no new events to log")
        return

    new_df = pd.DataFrame(rows)
    if not existing.empty:
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = new_df
    merged = merged.drop_duplicates(subset=["event_ts", "event_type"]).sort_values("event_ts")
    merged.to_csv(JOURNAL, index=False)

    print(f"[journal] +{len(rows)} new entries  ·  total {len(merged)}")
    # Stats
    traded = merged[merged["status"] == "traded"]
    no_trade = merged[merged["status"] == "no_trade_taken"]
    print(f"  traded:    {len(traded)}")
    print(f"  no-trade:  {len(no_trade)}")
    if not no_trade.empty and "status_detail" in no_trade.columns:
        print("\n  No-trade reasons:")
        print(no_trade["status_detail"].value_counts())


if __name__ == "__main__":
    main()
