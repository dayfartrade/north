"""Resolve shadow-decision outcomes by scanning subsequent bars.

Called each dispatch tick alongside shadow_orb_tracker. For each unresolved
shadow entry (has entry/target/stop but no outcome yet), scans 5m bars
after entry to determine:
  - hit target (win at target_price)
  - hit stop (loss at stop_price)
  - timeout at max_hold (close at last bar)

Writes resolved outcome back into data/shadow_equity_since_halt.jsonl by
rewriting the file (idempotent — only processes rows without 'outcome').

Cost model: $24/contract round-trip (same as backtest). Position size
assumed 1 contract (shadow P&L is unit-normalized).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_gc import load as gc_load

SHADOW_LOG = ROOT / "data/shadow_equity_since_halt.jsonl"
MAX_HOLD_BARS = 36  # 180min on 5m bars (Path Y max_hold)
CONTRACT_SIZE = 100  # oz per GC contract
RT_COST_PER_CONTRACT = 24.0  # matches backtest.RT_COST_PER_CONTRACT


def _load_rows() -> list[dict]:
    if not SHADOW_LOG.exists():
        return []
    rows = []
    with open(SHADOW_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _write_rows_atomic(rows: list[dict]) -> None:
    tmp = SHADOW_LOG.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    os.replace(tmp, SHADOW_LOG)


def _resolve_one(row: dict, bars: pd.DataFrame) -> dict | None:
    """Compute outcome dict or None if not yet resolvable."""
    if row.get("outcome") is not None:
        return None  # already resolved
    if row.get("would_skip"):
        return {
            "kind": "skipped",
            "net_pnl": 0.0,
            "resolved_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        }

    entry_ts = pd.Timestamp(row["or_close_utc"])
    if entry_ts.tz is None:
        entry_ts = entry_ts.tz_localize("UTC")
    direction_str = row.get("direction_bias", "FLAT")
    if direction_str == "LONG":
        entry_dir = 1
        entry_price = row["entry_long"]
        target_price = row["target_long"]
        stop_price = row["stop_long"]
    elif direction_str == "SHORT":
        entry_dir = -1
        entry_price = row["entry_short"]
        target_price = row["target_short"]
        stop_price = row["stop_short"]
    else:
        return {
            "kind": "flat_no_entry",
            "net_pnl": 0.0,
            "resolved_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        }
    if entry_price is None:
        return None

    # We need at least the entry bar and max_hold bars after
    mask = bars.index >= entry_ts
    if not mask.any():
        return None  # bars don't cover this timestamp yet
    window = bars.loc[mask].iloc[:MAX_HOLD_BARS + 1]
    if len(window) < 1:
        return None
    # If we don't have enough bars past entry AND target/stop haven't been hit,
    # leave unresolved (need more data)
    exit_price = None
    exit_reason = None
    for _, bar in window.iterrows():
        if entry_dir == 1:
            hit_stop = bar["low"] <= stop_price
            hit_tp = bar["high"] >= target_price
        else:
            hit_stop = bar["high"] >= stop_price
            hit_tp = bar["low"] <= target_price
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
        # No exit hit yet
        if len(window) >= MAX_HOLD_BARS + 1:
            # Full window elapsed; timeout at last bar close
            exit_price = float(window.iloc[-1]["close"])
            exit_reason = "time"
        else:
            return None  # not enough bars to resolve

    gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
    net = gross - RT_COST_PER_CONTRACT
    return {
        "kind": exit_reason,
        "exit_price": float(exit_price),
        "gross_pnl": float(gross),
        "net_pnl": float(net),
        "resolved_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }


def resolve_outcomes() -> tuple[int, int]:
    """Returns (n_newly_resolved, n_still_pending)."""
    rows = _load_rows()
    if not rows:
        return (0, 0)

    try:
        bars = gc_load("5m").sort_index()
        if bars.index.tz is None:
            bars.index = bars.index.tz_localize("UTC")
    except Exception as e:
        print(f"[shadow_resolver] bars load failed: {e}")
        return (0, 0)

    newly_resolved = 0
    still_pending = 0
    for row in rows:
        if row.get("outcome") is not None:
            continue
        outcome = _resolve_one(row, bars)
        if outcome is not None:
            row["outcome"] = outcome
            newly_resolved += 1
        else:
            still_pending += 1

    if newly_resolved:
        _write_rows_atomic(rows)

    return (newly_resolved, still_pending)


def summary() -> dict:
    rows = _load_rows()
    if not rows:
        return {"n_total": 0}
    resolved = [r for r in rows if r.get("outcome") is not None]
    took = [r for r in resolved if not r.get("would_skip") and r["direction_bias"] != "FLAT"]
    wins = [r for r in took if r["outcome"]["net_pnl"] > 0]
    total_pnl = sum(r["outcome"]["net_pnl"] for r in resolved)
    return {
        "n_total": len(rows),
        "n_resolved": len(resolved),
        "n_pending": len(rows) - len(resolved),
        "n_took": len(took),
        "n_wins": len(wins),
        "win_rate": len(wins) / max(len(took), 1),
        "shadow_net_pnl": total_pnl,
    }


if __name__ == "__main__":
    n_new, n_pending = resolve_outcomes()
    s = summary()
    print(f"[shadow_resolver] newly_resolved={n_new}  still_pending={n_pending}")
    print(f"  total rows: {s.get('n_total', 0)}  resolved: {s.get('n_resolved', 0)}")
    if s.get("n_took", 0) > 0:
        print(f"  took: {s['n_took']}  wins: {s['n_wins']} ({s['win_rate']:.0%})  shadow_net=${s['shadow_net_pnl']:,.0f}")
