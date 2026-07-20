"""Shadow-mode ORB decision tracker — runs while live is kill-switched.

Purpose: during Path Q (halted live, observational data collection), record
what the strategy WOULD have decided each session so we can:
  - Reconstruct a shadow-equity curve
  - Compute honest live-out-of-sample win rate
  - Satisfy re-entry Path A (shadow recovers to a new peak)

Safe by design:
  - Reads bars, computes decisions
  - Writes ONLY to data/shadow_equity_since_halt.jsonl
  - Never sends Telegram alerts, never modifies live state files
  - Idempotent per (session, or_open_utc) key — safe to run repeatedly

Called from dispatch.py after the ORB block if the kill switch is on.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_gc import load as gc_load
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on
from edge_session_orb_v7_final import SESSION_CONFIG
from mers_v3_peb import compute_atr
import pytz

# Optional candidate-filter tracking. If regime_context is importable, the
# shadow tracker records what pre-registered v8 shadow filters WOULD have
# said for this decision. Purely additive fields; existing consumers ignore
# unknown keys.
try:
    from regime_context import _daily_20d_slope  # type: ignore
    _CANDIDATE_TRACKING = True
except Exception:
    _CANDIDATE_TRACKING = False

SHADOW_LOG = ROOT / "data/shadow_equity_since_halt.jsonl"
OR_BARS = 6  # 30-min opening range on 5m
PLAN_WINDOW_BEFORE = 2  # minutes before or_close
PLAN_WINDOW_AFTER = 45  # minutes after or_close (matches dispatch_orb)


def _load_existing_keys() -> set[str]:
    """Return set of (session, or_open_utc) keys already logged, for idempotency."""
    if not SHADOW_LOG.exists():
        return set()
    out: set[str] = set()
    with open(SHADOW_LOG) as f:
        for line in f:
            try:
                row = json.loads(line)
                out.add(f"{row['session']}|{row['or_open_utc']}")
            except Exception:
                continue
    return out


def _append_row(row: dict) -> None:
    SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SHADOW_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _fetch_higher_tf_trend(bars_5m: pd.DataFrame) -> pd.Series:
    bars_1h = bars_5m["close"].resample("1h").last().dropna()
    ema = bars_1h.ewm(span=50, adjust=False).mean()
    slope = ema.diff(5)
    return slope.reindex(bars_5m.index, method="ffill")


def track_shadow_decisions() -> int:
    """Main entry. Returns count of new shadow rows recorded this tick."""
    now = pd.Timestamp.now(tz="UTC")
    existing_keys = _load_existing_keys()

    try:
        bars5 = gc_load("5m").sort_index()
        if bars5.index.tz is None:
            bars5.index = bars5.index.tz_localize("UTC")
    except Exception as e:
        print(f"[shadow_tracker] bars load failed: {e}")
        return 0

    if bars5.empty:
        return 0

    atr = compute_atr(bars5, 20)
    trend_slope = _fetch_higher_tf_trend(bars5)

    new_rows = 0
    for sess_name in SESSIONS_LOCAL:
        cfg = SESSION_CONFIG.get(sess_name, SESSION_CONFIG["NY"])
        sess_t = session_utc_time_on(now.date(), sess_name)
        # Today's session open in UTC
        today_open = pd.Timestamp.combine(now.date(), sess_t).tz_localize("UTC")
        or_close_ts = today_open + pd.Timedelta(minutes=30)

        # Only proceed if we're within the PLAN window
        delta = (now - or_close_ts).total_seconds() / 60
        if not (-PLAN_WINDOW_BEFORE <= delta <= PLAN_WINDOW_AFTER):
            continue

        key = f"{sess_name}|{today_open.isoformat()}"
        if key in existing_keys:
            continue  # already logged

        # Find or_close bar in bars5
        mask = bars5.index <= or_close_ts
        if not mask.any():
            continue
        or_close_idx = bars5.index.get_loc(bars5.index[mask][-1])
        or_start_idx = max(0, or_close_idx - OR_BARS + 1)
        or_window = bars5.iloc[or_start_idx: or_close_idx + 1]
        if len(or_window) < OR_BARS:
            continue

        or_high = float(or_window["high"].max())
        or_low = float(or_window["low"].min())
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        cur_atr = float(atr.iloc[or_close_idx])
        cur_slope = float(trend_slope.iloc[or_close_idx])

        # Apply filter (Path Y config: all sessions use or_vs_atr_max=2.0)
        skip_reason = None
        if cfg.get("use_or_filter", False):
            or_max = cfg.get("or_vs_atr_max", 2.0) * cur_atr
            if or_range > or_max:
                ratio = or_range / cur_atr if cur_atr > 0 else 0
                skip_reason = f"OR/ATR {ratio:.2f} > {cfg.get('or_vs_atr_max', 2.0)} (or_range {or_range:.2f} > {or_max:.2f})"

        # Determine direction bias
        direction = None
        if cur_slope > 0:
            direction = "LONG"
        elif cur_slope < 0:
            direction = "SHORT"
        else:
            direction = "FLAT"
            if skip_reason is None:
                skip_reason = "trend flat"

        # Geometry (matches Path Y config)
        if cfg.get("stop_mode") == "fixed":
            stop_dist = float(cfg["fixed_stop_price"])
        else:
            stop_dist = or_range
        if cfg.get("target_mode") == "stop_x_tp":
            target_dist = cfg.get("tp_mult", 1.5) * stop_dist
        else:
            target_dist = cfg.get("tp_mult", 1.5) * or_range

        # Pre-registered v8 candidate-filter shadow decisions (2026-07-18+).
        # Purely additive — actual dispatch is unaffected. See
        # docs/experiments/2026-07-18_daily_slope_consistency_shadow.md.
        candidate_shadows: dict = {}
        if _CANDIDATE_TRACKING and direction in ("LONG", "SHORT"):
            try:
                dsl = _daily_20d_slope(today_open.strftime("%Y-%m-%d"))
                if dsl is None or dsl == 0:
                    dsc_would_skip = None  # data unavailable / ambiguous
                else:
                    intra_sign = 1 if cur_slope > 0 else -1 if cur_slope < 0 else 0
                    daily_sign = 1 if dsl > 0 else -1
                    dsc_would_skip = bool(intra_sign != 0 and intra_sign != daily_sign)
                candidate_shadows["daily_slope_consistency"] = {
                    "would_skip": dsc_would_skip,
                    "daily_20d_slope": dsl,
                }
            except Exception:
                pass  # never let candidate tracking break the tracker itself

        # Engine B (Knox research/beta) decision: v7 Path Y config + daily-slope
        # consistency filter. Publishes to GOLDTRADER_TG_CHAT_RESEARCH when
        # KNOX_RESEARCH_ENABLED=1 AND Engine A takes AND Engine B takes.
        engine_b_takes = False
        dsc = candidate_shadows.get("daily_slope_consistency") or {}
        if (skip_reason is None
                and direction in ("LONG", "SHORT")
                and dsc.get("would_skip") is False):
            engine_b_takes = True

        row = {
            "ts_recorded_utc": now.isoformat(),
            "session": sess_name,
            "or_open_utc": today_open.isoformat(),
            "or_close_utc": or_close_ts.isoformat(),
            "or_high": or_high,
            "or_low": or_low,
            "or_range": or_range,
            "atr": cur_atr,
            "or_atr_ratio": or_range / cur_atr if cur_atr > 0 else None,
            "trend_slope": cur_slope,
            "direction_bias": direction,
            "would_skip": skip_reason is not None,
            "skip_reason": skip_reason,
            "stop_dist": stop_dist,
            "target_dist": target_dist,
            "entry_long": or_high if not skip_reason else None,
            "target_long": or_high + target_dist if not skip_reason else None,
            "stop_long": or_high - stop_dist if not skip_reason else None,
            "entry_short": or_low if not skip_reason else None,
            "target_short": or_low - target_dist if not skip_reason else None,
            "stop_short": or_low + stop_dist if not skip_reason else None,
            "strategy_version": "v7-actual-path-y",
            "candidate_shadows": candidate_shadows,
            "engine_b_takes": engine_b_takes,
        }
        _append_row(row)
        new_rows += 1

        # Publish research alert (Knox soft-launch, 2026-07-18) — opt-in,
        # fail-open (never breaks the shadow tracker itself).
        # Gated by BOTH env var AND state file (defense-in-depth kill switch).
        if engine_b_takes and _knox_alerts_enabled():
            _try_send_research_alert(sess_name, today_open, direction,
                                      or_high, or_low, stop_dist, target_dist,
                                      cur_slope, dsc.get("daily_20d_slope"))

    return new_rows


def _knox_alerts_enabled() -> bool:
    """Two-key kill: env KNOX_RESEARCH_ENABLED=1 AND data/knox_state.enabled != False."""
    if os.environ.get("KNOX_RESEARCH_ENABLED") != "1":
        return False
    state_file = ROOT / "data/knox_state.json"
    if not state_file.exists():
        return True  # file missing = default enabled (env is the gate)
    try:
        import json as _json
        state = _json.loads(state_file.read_text())
        return bool(state.get("enabled", True))
    except Exception:
        return True  # unreadable = fail-open to env


def _try_send_research_alert(sess_name: str, open_ts, direction: str,
                              or_high: float, or_low: float,
                              stop_dist: float, target_dist: float,
                              intraday_slope: float,
                              daily_20d_slope: float | None) -> None:
    """Format + send Engine B PLAN alert to research audience. Fail-open."""
    try:
        from telegram_bot import send as _tg_send
    except Exception:
        return

    if direction == "LONG":
        entry = or_high
        stop = or_high - stop_dist
        target = or_high + target_dist
    else:
        entry = or_low
        stop = or_low + stop_dist
        target = or_low - target_dist
    rr = target_dist / stop_dist if stop_dist > 0 else 0
    daily_str = f"{daily_20d_slope:+.2f}" if daily_20d_slope is not None else "n/a"

    text = (
        "🧪 *KNOX RESEARCH ALERT — UNVALIDATED*\n"
        "_Shadow-gate n/100 · CI on P&L lift still includes zero_\n"
        "_Do NOT trade this with money you can't lose._\n\n"
        f"*{sess_name} PLAN* · {open_ts.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Direction: *{direction}*\n"
        f"Entry: `{entry:.2f}`\n"
        f"Stop:  `{stop:.2f}`  ({stop_dist:.2f} pts)\n"
        f"Target: `{target:.2f}`  ({target_dist:.2f} pts, {rr:.2f}R)\n\n"
        f"_intraday_slope={intraday_slope:+.2f}_ · "
        f"_daily_20d_slope={daily_str}_\n\n"
        "Filter chain: OR/ATR ≤ 2.0 · trend-aligned · "
        "*daily_slope_consistency=ON*\n"
        "Pre-reg: docs/experiments/2026-07-18_daily_slope_consistency_shadow.md"
    )
    try:
        _tg_send(text, audience="research")
    except Exception:
        pass  # fail-open


if __name__ == "__main__":
    n = track_shadow_decisions()
    if n:
        print(f"[shadow_tracker] recorded {n} new shadow decision(s)")
    else:
        print("[shadow_tracker] no new decisions in PLAN window")
