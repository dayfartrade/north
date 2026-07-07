"""End-to-end smoke test — simulate a PLAN firing without waiting for the
live time window. Exercises the 3 brittle points that fail SILENTLY in
dispatch_orb.py (wrapped in try/except _log):

  1. alert_format_v2.plan_public()   — the polished PLAN string builder
  2. alerts_stream.jsonl writer      — audit sub-blocks + strategy stamp
  3. shadow_log.record_shadow()      — candidate feature evaluation

If any of these raise, dispatch_orb catches and logs — subscribers silently
lose the alert. This test catches those failures pre-launch.

Uses today's real GC 5m bars + a plausible synthetic OR window. Writes to
TEMP JSONL files so the real production streams aren't polluted.
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_gc import load as gc_load
from edge_session_orb import session_utc_time_on
from edge_session_orb_v7_final import SESSION_CONFIG, TP_MULT_DEFAULT
from mers_v3_peb import compute_atr
from strategy_version import strategy_stamp, STRATEGY_VERSION
from alert_format_v2 import plan_public as fmt_plan_public


PASS = "PASS"
FAIL = "FAIL"


def build_plan_payload(sess_name: str) -> dict:
    """Build a payload that mirrors what dispatch_orb.py assembles at PLAN time,
    using today's real bars. Returns the payload plus computed derived fields."""
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    # Use the most recent full 30-min block as the "OR window"
    last_bar = bars.index[-1]
    or_close_ts = last_bar
    or_open_ts = or_close_ts - pd.Timedelta(minutes=30)
    or_window = bars.loc[or_open_ts:or_close_ts]
    or_high = float(or_window["high"].max())
    or_low = float(or_window["low"].min())
    or_range = or_high - or_low

    cfg = SESSION_CONFIG[sess_name]
    if cfg.get("stop_mode") == "fixed":
        stop_dist = float(cfg["fixed_stop_price"])
    else:
        stop_dist = or_range
    if cfg.get("target_mode") == "stop_x_tp":
        target_dist = cfg.get("tp_mult", TP_MULT_DEFAULT) * stop_dist
    else:
        target_dist = cfg.get("tp_mult", TP_MULT_DEFAULT) * or_range
    rr_ratio = target_dist / stop_dist if stop_dist > 0 else 0

    stop_long = or_high - stop_dist
    target_long = or_high + target_dist
    stop_short = or_low + stop_dist
    target_short = or_low - target_dist

    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=50, adjust=False).mean()
    cur_slope = float(ema.diff(5).iloc[-1])
    trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
    dir_hint = ("LONG only (trend up)" if cur_slope > 0
                else "SHORT only (trend down)" if cur_slope < 0 else "SKIP")

    watch_end = or_close_ts + pd.Timedelta(minutes=60)

    return {
        "session": sess_name, "version": STRATEGY_VERSION,
        "or_open_ts": or_open_ts, "or_close_ts": or_close_ts,
        "or_high": or_high, "or_low": or_low, "or_range": or_range,
        "long_entry": or_high, "long_stop": stop_long, "long_target": target_long,
        "short_entry": or_low, "short_stop": stop_short, "short_target": target_short,
        "stop_dist": stop_dist, "target_dist": target_dist, "rr_ratio": rr_ratio,
        "trend": trend, "dir_hint": dir_hint,
        "watch_end_ts": watch_end, "hold_hours": 36 * 5 / 60,
        "funding_line": "💱 Funding neutral (+0.4% ann)",
        "basis_line": "",
        "cot_line": "📑 COT 2026-07-01: managed money net long 213,456 (P62 52w)",
        "vol_line": "📊 OR volume 1.42× prior · 🔊 normal",
        "sd_windows": [],
    }


def test_plan_formatter(payload: dict) -> tuple[str, str]:
    """1. Verify plan_public() doesn't raise on realistic input."""
    try:
        msg = fmt_plan_public(payload)
        assert isinstance(msg, str)
        assert len(msg) > 200, f"suspiciously short: {len(msg)} chars"
        assert "ORB PLAN" in msg
        assert "LONG SETUP" in msg
        assert "SHORT SETUP" in msg
        assert payload["version"] in msg
        return PASS, f"len={len(msg)} chars"
    except Exception as e:
        return FAIL, f"{type(e).__name__}: {e}"


def test_alerts_stream_row(payload: dict) -> tuple[str, str]:
    """2. Build the alerts_stream.jsonl row exactly as dispatch_orb.py does,
    write to a temp file, read back and confirm it parses."""
    try:
        now_iso = pd.Timestamp.now(tz='UTC').isoformat()
        stamp = strategy_stamp()
        audit = {
            "stand_down_windows": [],
            "funding": {"annualized_pct": 0.4, "regime": "neutral",
                        "abs_percentile": 0.42, "as_of_utc": now_iso},
            "basis":   {"error": "n/a", "as_of_utc": now_iso},
            "cot":     {"mm_net_long": 213456, "pct_52w": 0.62,
                        "as_of_utc": "2026-07-01T00:00:00"},
            "volume":  {"or_window_vol": 1234, "prior_20bar_vol": 869, "ratio": 1.42,
                        "as_of_utc": now_iso},
        }
        row = {
            "ts_sent_utc": now_iso,
            "kind": "orb_plan",
            "session": payload["session"],
            **stamp,
            "or_open_utc": payload["or_open_ts"].isoformat(),
            "or_close_utc": payload["or_close_ts"].isoformat(),
            "or_high": float(payload["or_high"]),
            "or_low": float(payload["or_low"]),
            "or_range": float(payload["or_range"]),
            "stop_dist": float(payload["stop_dist"]),
            "target_dist": float(payload["target_dist"]),
            "rr_ratio": float(payload["rr_ratio"]),
            "long":  {"entry": float(payload["long_entry"]),
                      "stop":  float(payload["long_stop"]),
                      "target": float(payload["long_target"])},
            "short": {"entry": float(payload["short_entry"]),
                      "stop":  float(payload["short_stop"]),
                      "target": float(payload["short_target"])},
            "trend": payload["trend"],
            "watch_expires_utc": payload["watch_end_ts"].isoformat(),
            "max_hold_min": 36 * 5,
            "audit": audit,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl",
                                          delete=False, encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
            tmp_path = f.name
        with open(tmp_path, "r", encoding="utf-8") as f:
            line = f.readline()
        parsed = json.loads(line)
        Path(tmp_path).unlink(missing_ok=True)
        assert parsed["kind"] == "orb_plan"
        assert parsed["strategy_version"] == STRATEGY_VERSION
        assert "filter_config_hash" in parsed
        assert parsed["long"]["entry"] == float(payload["long_entry"])
        return PASS, f"stamp={parsed['strategy_version']} keys={len(parsed)}"
    except Exception as e:
        return FAIL, f"{type(e).__name__}: {e}"


def test_shadow_log(payload: dict) -> tuple[str, str]:
    """3. Call record_shadow() with a realistic plan_context + features,
    write to a temp path, read back, verify vol_ratio_ge_1_0 evaluated."""
    try:
        from shadow_log import CANDIDATES
        # Monkeypatch the SHADOW_LOG path to a temp file
        import shadow_log
        original_path = shadow_log.SHADOW_LOG
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl",
                                           delete=False, encoding="utf-8")
        tmp.close()
        shadow_log.SHADOW_LOG = Path(tmp.name)
        try:
            stamp = strategy_stamp()
            features = {
                "or_range": payload["or_range"],
                "or_atr_ratio": 2.1,
                "or_win_vol_ratio": 1.42,
                "trend_slope": 0.42,
                "funding_pct": 0.4,
                "basis_pct": None,
                "cot_pct_52w": 0.62,
            }
            plan_context = {
                "session": payload["session"],
                "or_open_utc": payload["or_open_ts"].isoformat(),
                "or_close_utc": payload["or_close_ts"].isoformat(),
                "or_high": float(payload["or_high"]),
                "or_low": float(payload["or_low"]),
                **stamp,
            }
            shadow_log.record_shadow(plan_context, features)
            with open(tmp.name, "r", encoding="utf-8") as f:
                line = f.readline()
            parsed = json.loads(line)
            assert "shadow_decisions" in parsed
            decisions = parsed["shadow_decisions"]
            active = [n for n, s in CANDIDATES.items() if s.get("status") == "shadow"]
            for name in active:
                assert name in decisions, f"missing decision for {name}"
                assert "would_skip" in decisions[name]
            return PASS, f"decisions={list(decisions.keys())}"
        finally:
            Path(tmp.name).unlink(missing_ok=True)
            shadow_log.SHADOW_LOG = original_path
    except Exception as e:
        return FAIL, f"{type(e).__name__}: {e}"


def main():
    print("=" * 78)
    print("END-TO-END SMOKE TEST — polished PLAN + alerts_stream + shadow_log")
    print("=" * 78)

    payload = build_plan_payload("NY")
    print(f"\nSynthetic OR window: {payload['or_open_ts']} -> {payload['or_close_ts']}")
    print(f"H=${payload['or_high']:.2f}  L=${payload['or_low']:.2f}  range=${payload['or_range']:.2f}\n")

    tests = [
        ("plan_public formatter",  test_plan_formatter),
        ("alerts_stream JSONL row", test_alerts_stream_row),
        ("shadow_log record",       test_shadow_log),
    ]
    all_ok = True
    for label, fn in tests:
        verdict, detail = fn(payload)
        marker = "OK  " if verdict == PASS else "FAIL"
        print(f"  [{marker}] {label:30s} -> {detail}")
        if verdict != PASS:
            all_ok = False

    print()
    print("=" * 78)
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES DETECTED")
    print("=" * 78)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
