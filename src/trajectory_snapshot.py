"""Trajectory snapshots — for EXECUTION tests (trailing stops, mid-position
rules), per Janus's 2026-07-07 note.

Two paths:

1. Historical reconstruction (used by backtests): given a completed trade
   with entry_ts and exit_ts, walk 5m bars and emit synthetic snapshots at
   any resolution. Cheap, deterministic, replayable.

2. Live capture (called from dispatch every tick during open PLAN windows):
   snapshot the current mid + MAE + MFE + latency at each dispatch tick.
   Accumulates to data/trajectories.jsonl for future execution research.

Raw storage, no thinning, per Janus's advice ("storage is cheap, aggregation
loses information"). At the ~30-min tick cadence, 1 open position = 6
snapshots per 180-min hold = ~180 rows/month at 1 trade/day. Trivial.

IMPORTANT LIMITATION: yfinance provides mid only (no bid/ask). Every row
carries a `price_source` field (values: 'mid_yfinance' | 'ticker_bitget' |
'paid_feed_ibkr' etc.) so future execution-cost analysis can filter or
warn based on provenance. When we upgrade to a paid feed, new rows tag
themselves differently without breaking past data. Bitget XAUUSD spread is
carried alongside as a proxy (crypto perp, similar underlying).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TRAJECTORY_LOG = ROOT / "data" / "trajectories.jsonl"


def _bitget_spread_bps() -> float | None:
    """Best-effort Bitget XAUUSDT spread proxy (basis points).
    Fails silently — never crashes the caller."""
    try:
        from data_bitget import fetch_ticker
        t = fetch_ticker()
        bid = float(t.get("bidPr") or t.get("bid") or 0)
        ask = float(t.get("askPr") or t.get("ask") or 0)
        if bid > 0 and ask > 0:
            return (ask - bid) / ((ask + bid) / 2) * 10_000
    except Exception:
        pass
    return None


def _session_marker(ts_utc: pd.Timestamp) -> str:
    """Cheap label — which session's window are we inside?"""
    h = ts_utc.hour
    if 7 <= h < 10:   return "LON"
    if 13 <= h < 17:  return "NY"
    if 22 <= h or h < 3: return "ASIA"
    return "off"


def snapshot_live(entry_ts_utc: str, entry_price: float, direction: int,
                    stop_price: float, target_price: float,
                    session: str, strategy_version: str,
                    filter_config_hash: str) -> None:
    """Called from dispatch every tick during any open PLAN window. Reads the
    latest 5m bar as current mid, computes MAE/MFE-since-entry, appends one
    JSONL row. No live impact on dispatch flow."""
    from data_gc import load as gc_load
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    entry_ts = pd.Timestamp(entry_ts_utc)
    if entry_ts.tz is None:
        entry_ts = entry_ts.tz_localize("UTC")
    now_utc = pd.Timestamp.now(tz="UTC")

    since_entry = bars.loc[entry_ts:now_utc]
    if since_entry.empty:
        return

    latest_bar_ts = since_entry.index[-1]
    mid = float(since_entry.iloc[-1]["close"])
    latency_sec = (now_utc - latest_bar_ts).total_seconds()

    if direction == 1:
        mae = entry_price - float(since_entry["low"].min())
        mfe = float(since_entry["high"].max()) - entry_price
        unrealized = (mid - entry_price) * 100
    else:
        mae = float(since_entry["high"].max()) - entry_price
        mfe = entry_price - float(since_entry["low"].min())
        unrealized = (entry_price - mid) * 100

    row = {
        "ts_snapshot_utc": now_utc.isoformat(),
        "ts_latest_bar_utc": latest_bar_ts.isoformat(),
        "latency_sec": round(latency_sec, 1),
        "source": "live",
        "session": session,
        "entry_ts_utc": entry_ts.isoformat(),
        "entry_price": float(entry_price),
        "direction": int(direction),
        "stop_price": float(stop_price),
        "target_price": float(target_price),
        "mid": mid,
        "price_source": "mid_yfinance",  # future: 'ticker_bitget' | 'paid_feed_ibkr' etc.
        "bitget_spread_bps_proxy": _bitget_spread_bps(),
        "mae_dollars": round(mae * 100, 2),
        "mfe_dollars": round(mfe * 100, 2),
        "unrealized_pnl": round(unrealized, 2),
        "session_marker": _session_marker(now_utc),
        "strategy_version": strategy_version,
        "filter_config_hash": filter_config_hash,
    }
    TRAJECTORY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(TRAJECTORY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def reconstruct_from_bars(entry_ts_utc: pd.Timestamp, exit_ts_utc: pd.Timestamp,
                            entry_price: float, direction: int,
                            bars: pd.DataFrame,
                            step_bars: int = 3) -> Iterable[dict]:
    """Yield synthetic trajectory rows for a historical trade at `step_bars` cadence.
    Used by backtests (e.g., trailing-stop replay) without needing live capture.

    At step_bars=3 (15min on 5m bars), a 180-min position yields ~12 rows.
    """
    if bars.index.tz is None:
        bars = bars.copy()
        bars.index = bars.index.tz_localize("UTC")
    entry_ts = pd.Timestamp(entry_ts_utc)
    exit_ts = pd.Timestamp(exit_ts_utc)
    if entry_ts.tz is None: entry_ts = entry_ts.tz_localize("UTC")
    if exit_ts.tz is None:  exit_ts = exit_ts.tz_localize("UTC")

    if entry_ts not in bars.index:
        return
    i_entry = bars.index.get_loc(entry_ts)

    # Walk to exit (inclusive), yielding every step_bars
    for i in range(i_entry, len(bars), step_bars):
        ts = bars.index[i]
        if ts > exit_ts:
            break
        slice_ = bars.iloc[i_entry:i + 1]
        if direction == 1:
            mae = entry_price - float(slice_["low"].min())
            mfe = float(slice_["high"].max()) - entry_price
        else:
            mae = float(slice_["high"].max()) - entry_price
            mfe = entry_price - float(slice_["low"].min())
        mid = float(bars.iloc[i]["close"])
        unrealized = (mid - entry_price) * direction * 100
        yield {
            "ts_snapshot_utc": ts.isoformat(),
            "ts_latest_bar_utc": ts.isoformat(),
            "latency_sec": 0.0,
            "source": "reconstructed",
            "entry_ts_utc": entry_ts.isoformat(),
            "entry_price": float(entry_price),
            "direction": int(direction),
            "mid": mid,
            "price_source": "mid_yfinance",  # future: 'ticker_bitget' | 'paid_feed_ibkr' etc.
            "mae_dollars": round(mae * 100, 2),
            "mfe_dollars": round(mfe * 100, 2),
            "unrealized_pnl": round(unrealized, 2),
            "session_marker": _session_marker(ts),
        }
