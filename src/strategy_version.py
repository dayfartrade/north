"""Strategy version + config hash — stamped into every live-dispatched PLAN.

Purpose: after a config change, we can slice performance by version and see
whether v7.2 outperformed v7.1 at the same regime. Every trade record in
alerts_stream.jsonl carries these fields; retrospective analysis is trivial.

Layer classification (per our 3-layer discipline model, 2026-07-07):
  - strategy_engine (LOCKED, quarterly)      -> run_orb_v7 body, session times
  - session_config (MEDIUM, pre-reg+shadow)  -> SESSION_CONFIG per-session dicts
  - calendar_audit (FAST, weekly ok)         -> stand_down calendar, audit boxes

STRATEGY_VERSION should bump on ANY change to strategy_engine or session_config
layers. Calendar/audit tweaks don't require a bump but do get logged.
"""
from __future__ import annotations
import hashlib
import json

STRATEGY_VERSION = "v7.2.1"
STRATEGY_LAYER_MAP = {
    "strategy_engine": "run_orb_v7 body, SESSIONS_LOCAL, MAJOR_NEWS",
    "session_config":  "SESSION_CONFIG dict (per-session filters/geometry/exits)",
    "calendar_audit":  "stand_down calendar, _funding/_basis/_cot/_volume context",
}


def filter_config_hash() -> str:
    """Short SHA-1 (first 12 chars) of the currently-active SESSION_CONFIG.
    Bumps automatically when any session config value changes. Combined with
    STRATEGY_VERSION, gives a fully-reproducible pointer to what was live."""
    from edge_session_orb_v7_final import SESSION_CONFIG
    canonical = json.dumps(SESSION_CONFIG, sort_keys=True, default=str)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def strategy_stamp() -> dict:
    """Return the stamp block to embed in alerts_stream rows + trajectory snapshots."""
    return {
        "strategy_version": STRATEGY_VERSION,
        "filter_config_hash": filter_config_hash(),
    }
