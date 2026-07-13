"""Backfill data/shadow_equity_since_halt.jsonl from historical GC bars.

Runs strategy_engine.evaluate_session over the last N days of GC bars,
producing shadow entries for each session's OR window. Simulates the
would-be trade outcome using the same bar-by-bar simulation as the
backtest.

Idempotent — dedupe on (session, or_open_utc) key.

Purpose:
  - Seed the shadow log with pre-kill-switch history
  - Validate the tracker + resolver logic against known trades
  - Give the shadow-equity dashboard immediate content

Warning: This is IN-SAMPLE data. Not honest OOS. Forward-shadow starts
with the first entry AFTER the kill switch (2026-07-13 14:30 UTC).

Usage:
  python scripts/backfill_shadow_log.py [--days N] [--start YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_gc import load as gc_load
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on
from mers_v3_peb import compute_atr
from strategy_engine import (
    OrContext,
    RegimeContext,
    SESSION_CONFIGS_V8_INITIAL,
    evaluate_session,
)
from regime_context import build_regime_context

SHADOW_LOG = ROOT / "data/shadow_equity_since_halt.jsonl"
OR_BARS = 6  # 30-min OR on 5m
MAX_HOLD_BARS = 36  # 180min max hold
CONTRACT_SIZE = 100
RT_COST_PER_CONTRACT = 24.0


def _existing_keys() -> set[str]:
    if not SHADOW_LOG.exists():
        return set()
    keys = set()
    with open(SHADOW_LOG) as f:
        for line in f:
            try:
                r = json.loads(line)
                keys.add(f"{r['session']}|{r['or_open_utc']}")
            except Exception:
                continue
    return keys


def _fetch_slope(bars_5m: pd.DataFrame) -> pd.Series:
    bars_1h = bars_5m["close"].resample("1h").last().dropna()
    ema = bars_1h.ewm(span=50, adjust=False).mean()
    slope = ema.diff(5)
    return slope.reindex(bars_5m.index, method="ffill")


def _simulate_outcome(bars_5m: pd.DataFrame, entry_idx: int, decision) -> dict:
    """Bar-by-bar simulate the would-be trade outcome."""
    from strategy_engine import Direction
    entry_dir = 1 if decision.direction == Direction.LONG else -1
    entry_price = decision.entry_price
    target_price = decision.target_price
    stop_price = decision.stop_price
    exit_price = None
    exit_reason = None
    for k in range(MAX_HOLD_BARS + 1):
        if entry_idx + k >= len(bars_5m):
            break
        b = bars_5m.iloc[entry_idx + k]
        if entry_dir == 1:
            hit_stop = b["low"] <= stop_price
            hit_tp = b["high"] >= target_price
        else:
            hit_stop = b["high"] >= stop_price
            hit_tp = b["low"] <= target_price
        if hit_stop and hit_tp:
            exit_price = stop_price
            exit_reason = "stop_conservative"
            break
        if hit_stop:
            exit_price = stop_price
            exit_reason = "stop"
            break
        if hit_tp:
            exit_price = target_price
            exit_reason = "target"
            break
    if exit_price is None:
        end_idx = min(entry_idx + MAX_HOLD_BARS, len(bars_5m) - 1)
        exit_price = float(bars_5m.iloc[end_idx]["close"])
        exit_reason = "time"
    gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
    net = gross - RT_COST_PER_CONTRACT
    return {
        "kind": exit_reason,
        "exit_price": float(exit_price),
        "gross_pnl": float(gross),
        "net_pnl": float(net),
        "resolved_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }


def backfill(days: int = 30, start_date: str | None = None) -> int:
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    slope = _fetch_slope(bars)

    now = pd.Timestamp.now(tz="UTC")
    if start_date:
        start = pd.Timestamp(start_date, tz="UTC")
    else:
        start = now - pd.Timedelta(days=days)

    existing = _existing_keys()
    new_rows = []
    cur = start
    while cur.date() <= now.date():
        if cur.weekday() == 5:  # Saturday skip
            cur += pd.Timedelta(days=1)
            continue
        for sess_name in SESSIONS_LOCAL:
            cfg = SESSION_CONFIGS_V8_INITIAL[sess_name]
            sess_t = session_utc_time_on(cur.date(), sess_name)
            open_ts = pd.Timestamp.combine(cur.date(), sess_t).tz_localize("UTC")
            key = f"{sess_name}|{open_ts.isoformat()}"
            if key in existing:
                continue
            or_close_ts = open_ts + pd.Timedelta(minutes=30)
            # Need bars covering OR + at least a few more for outcome
            mask = bars.index >= open_ts
            if not mask.any():
                continue
            first_ts = bars.index[mask][0]
            if (first_ts - open_ts) > pd.Timedelta(minutes=30):
                continue  # market closed at nominal open
            s_idx = bars.index.get_loc(first_ts)
            if s_idx + OR_BARS + MAX_HOLD_BARS + 1 >= len(bars):
                continue
            or_window = bars.iloc[s_idx: s_idx + OR_BARS]
            or_high = float(or_window["high"].max())
            or_low = float(or_window["low"].min())
            or_range = or_high - or_low
            if or_range <= 0:
                continue
            cur_atr = float(atr.iloc[s_idx + OR_BARS - 1])
            cur_slope = float(slope.iloc[s_idx + OR_BARS - 1])
            if cur_atr <= 0:
                continue

            or_ctx = OrContext(
                session_open_utc=open_ts,
                or_close_utc=bars.index[s_idx + OR_BARS - 1],
                or_high=or_high, or_low=or_low, or_range=or_range,
                atr_at_close=cur_atr, slope_at_close=cur_slope,
                or_bars_df=or_window,
            )
            regime = build_regime_context(bars.index[s_idx + OR_BARS - 1])
            decision = evaluate_session(cfg, or_ctx, regime)

            row = {
                "ts_recorded_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                "session": sess_name,
                "or_open_utc": open_ts.isoformat(),
                "or_close_utc": bars.index[s_idx + OR_BARS - 1].isoformat(),
                "or_high": or_high, "or_low": or_low, "or_range": or_range,
                "atr": cur_atr,
                "or_atr_ratio": or_range / cur_atr if cur_atr > 0 else None,
                "trend_slope": cur_slope,
                "direction_bias": decision.direction.name,
                "would_skip": not decision.would_take,
                "skip_reason": " | ".join(decision.would_skip_reasons) if decision.would_skip_reasons else None,
                "stop_dist": abs(decision.entry_price - decision.stop_price) if decision.would_take else None,
                "target_dist": abs(decision.target_price - decision.entry_price) if decision.would_take else None,
                "entry_long": decision.entry_price if decision.would_take and decision.direction.name == "LONG" else None,
                "target_long": decision.target_price if decision.would_take and decision.direction.name == "LONG" else None,
                "stop_long": decision.stop_price if decision.would_take and decision.direction.name == "LONG" else None,
                "entry_short": decision.entry_price if decision.would_take and decision.direction.name == "SHORT" else None,
                "target_short": decision.target_price if decision.would_take and decision.direction.name == "SHORT" else None,
                "stop_short": decision.stop_price if decision.would_take and decision.direction.name == "SHORT" else None,
                "strategy_version": "v7-actual-path-y-backfill",
            }

            # Simulate outcome — matches backtest's watch-window semantics:
            # Only fire if breakout actually happens in 12-bar watch window.
            if decision.would_take:
                WATCH_BARS = 12
                from strategy_engine import Direction
                entry_dir = 1 if decision.direction == Direction.LONG else -1
                entry_idx = None
                for k in range(WATCH_BARS):
                    i = s_idx + OR_BARS + k
                    if i >= len(bars):
                        break
                    b = bars.iloc[i]
                    hit_long = b["high"] >= or_high
                    hit_short = b["low"] <= or_low
                    if hit_long and hit_short:
                        continue
                    if entry_dir == 1 and hit_long:
                        entry_idx = i
                        break
                    if entry_dir == -1 and hit_short:
                        entry_idx = i
                        break
                if entry_idx is None:
                    # No breakout in watch window — reclassify as no-entry
                    row["would_skip"] = True
                    row["skip_reason"] = "no_breakout_in_watch_window"
                    row["outcome"] = {"kind": "no_breakout", "net_pnl": 0.0,
                                      "resolved_utc": pd.Timestamp.now(tz="UTC").isoformat()}
                    for k in ("entry_long", "target_long", "stop_long",
                             "entry_short", "target_short", "stop_short"):
                        row[k] = None
                else:
                    row["outcome"] = _simulate_outcome(bars, entry_idx, decision)
            elif decision.direction.name == "FLAT":
                row["outcome"] = {"kind": "flat_no_entry", "net_pnl": 0.0,
                                  "resolved_utc": pd.Timestamp.now(tz="UTC").isoformat()}
            else:
                row["outcome"] = {"kind": "skipped", "net_pnl": 0.0,
                                  "resolved_utc": pd.Timestamp.now(tz="UTC").isoformat()}

            new_rows.append(row)
            existing.add(key)
        cur += pd.Timedelta(days=1)

    # Append atomically
    SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = SHADOW_LOG.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        # Read existing first
        if SHADOW_LOG.exists():
            with open(SHADOW_LOG) as g:
                for line in g:
                    f.write(line)
        for r in new_rows:
            f.write(json.dumps(r, default=str) + "\n")
    os.replace(tmp, SHADOW_LOG)
    return len(new_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--start", default=None, help="YYYY-MM-DD")
    args = parser.parse_args()

    n = backfill(days=args.days, start_date=args.start)
    print(f"[backfill] added {n} shadow decisions to {SHADOW_LOG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
