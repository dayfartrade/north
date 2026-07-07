"""Post-hoc JSONL shadow logger — for SIGNAL tests, per Janus's 2026-07-07 note.

Every time a real PLAN fires, this module also evaluates every REGISTERED
CANDIDATE filter against the same features and records what the candidate
WOULD have done. Zero capital risk; pure observational data.

After 30 days / n=100 cumulative shadow decisions, we can measure whether
a candidate filter's would-have-skipped events are systematically losers
(ship it) or a mix (reject it) — without ever gating a live trade on it.

Use for SIGNAL tests only (filter thresholds, gates). For EXECUTION tests
(trailing stops, mid-position rules) use trajectory_snapshot.py instead.
"""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SHADOW_LOG = ROOT / "data" / "shadow_decisions.jsonl"


# ---------------------------------------------------------------------------
# Candidate filter registry
# Add a new entry to test a new filter without touching dispatch code.
# ---------------------------------------------------------------------------
# Each candidate has:
#   description      : one-line human summary
#   feature          : field name in the features dict passed to record_shadow
#   operator         : one of 'lt', 'le', 'gt', 'ge', 'in_range', 'out_range'
#   threshold        : float, or (lo, hi) tuple for range ops
#   registered_utc   : when it entered shadow mode (for filtering by min-shadow-days)
#   preregistered_at : path to the docs/experiments/*.md pre-registration file
#   status           : 'shadow' | 'promoted_to_live' | 'rejected'
#
# CANDIDATES are frozen after registration. Never edit or delete a candidate
# post-hoc — that would break the shadow record. Add a new entry instead.
CANDIDATES = {
    "vol_ratio_ge_1_0": {
        "description": "Skip PLAN if OR-window volume ratio < 1.0 (v7.3 candidate)",
        "feature": "or_win_vol_ratio",
        "operator": "lt",  # skip if feature < threshold (i.e. condition-matches skip)
        "threshold": 1.0,
        "registered_utc": "2026-07-07T18:00:00Z",
        "preregistered_at": "docs/experiments/2026-07-07_vol_ratio_shadow.md",
        "status": "shadow",
    },
}


def _would_skip(op: str, feature_value, threshold) -> bool | None:
    if feature_value is None:
        return None
    try:
        v = float(feature_value)
    except (TypeError, ValueError):
        return None
    if op == "lt":
        return v < float(threshold)
    if op == "le":
        return v <= float(threshold)
    if op == "gt":
        return v > float(threshold)
    if op == "ge":
        return v >= float(threshold)
    if op == "in_range":
        lo, hi = threshold
        return lo <= v <= hi
    if op == "out_range":
        lo, hi = threshold
        return v < lo or v > hi
    return None


def record_shadow(plan_context: dict, features: dict) -> None:
    """Called from dispatch_orb after each PLAN dispatches. Logs one JSONL row
    with the plan context, the extracted features, and each candidate's
    would-have-skipped decision. Idempotent — single append, single write.

    plan_context keys expected: session, or_open_utc, or_close_utc,
    direction, entry_price, strategy_version, filter_config_hash.

    features keys expected (as available): or_range, or_atr_ratio,
    or_win_vol_ratio, trend_slope, funding_pct, basis_pct, cot_pct_52w.
    """
    decisions = {}
    for name, spec in CANDIDATES.items():
        if spec.get("status") != "shadow":
            continue
        val = features.get(spec["feature"])
        would_skip = _would_skip(spec["operator"], val, spec["threshold"])
        decisions[name] = {
            "would_skip": would_skip,
            "feature_value": val,
        }

    row = {
        "ts_recorded_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "plan": plan_context,
        "features": features,
        "shadow_decisions": decisions,
    }
    SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SHADOW_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def load_shadow_log(min_days: int = 0) -> pd.DataFrame:
    """Load the shadow log as a DataFrame. min_days filters to rows at least
    `min_days` old (useful when a candidate registered mid-window)."""
    if not SHADOW_LOG.exists():
        return pd.DataFrame()
    rows = []
    with open(SHADOW_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["ts_recorded_utc"] = pd.to_datetime(df["ts_recorded_utc"], utc=True)
    if min_days > 0:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=min_days)
        df = df[df["ts_recorded_utc"] <= cutoff]
    return df.reset_index(drop=True)
