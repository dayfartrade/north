"""ORB live dispatcher — generates real-time Telegram alerts for session ORBs.

Designed to run as part of dispatch.py (every 30 min via Task Scheduler).

For each session in SESSIONS:
  - If the OR window is COMPLETING in the next 30 min → send "OR forming" alert
  - If the OR window has just CLOSED → send "OR levels + plan" alert with
    buy-stop, sell-stop, stop, target, and trend-filter direction.
  - State persisted in dispatch_state.json so we don't re-alert.

Frozen params match orb_validate.py (the validated config).
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on, fetch_higher_tf_trend
from mers_v3_peb import compute_atr
from telegram_bot import send
from alert_formatter import fmt_et
from health import market_likely_open

OR_BARS = 6       # 30-min opening range on 5m
WATCH = 12        # 60-min breakout window
HOLD = 24         # 2-hour time exit
TP_MULT = 1.5
STOP_MULT = 1.0
REQUIRE_TREND = True

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "dispatch_state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"sent": []}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def session_emoji(name: str) -> str:
    return {"LON": "🇬🇧", "NY": "🇺🇸", "ASIA": "🇯🇵"}.get(name, "📍")


def dispatch_orb_alerts():
    state = load_state()
    sent = set(state.get("sent", []))
    actions = []

    # Weekend guard: GC futures closed Fri 17:00 ET → Sun 18:00 ET. Skip ORBs on closed market.
    if not market_likely_open():
        return actions

    bars5 = gc_load("5m").sort_index()
    if bars5.index.tz is None: bars5.index = bars5.index.tz_localize("UTC")
    if bars5.empty:
        return actions
    atr = compute_atr(bars5, 20)
    trend_slope = fetch_higher_tf_trend(bars5)

    now = pd.Timestamp.now(tz="UTC")
    today = now.date()

    for sess_name in SESSIONS_LOCAL:
        # DST-aware: compute today's session-open UTC time-of-day
        sess_t = session_utc_time_on(today, sess_name)
        open_ts = pd.Timestamp.combine(today, sess_t).tz_localize("UTC")
        or_close_ts = open_ts + pd.Timedelta(minutes=5 * OR_BARS)  # 30 min later

        # PRE alert: ~15 min before OR closes
        if pd.Timedelta(minutes=5) <= (or_close_ts - now) <= pd.Timedelta(minutes=30):
            k = f"ORB|{open_ts.isoformat()}|{sess_name}|pre"
            if k not in sent:
                cur_slope = float(trend_slope.iloc[-1]) if len(trend_slope) else float("nan")
                trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
                msg = (f"🕐 *{sess_name} ORB forming* {session_emoji(sess_name)}\n"
                       f"   Opening range builds: {fmt_et(open_ts)} → {fmt_et(or_close_ts)}\n"
                       f"   Current 1h trend: *{trend}* (slope {cur_slope:+.2f})\n"
                       f"   Will alert with levels once OR closes.")
                send(msg)
                sent.add(k)
                actions.append(("orb_pre", sess_name, open_ts))

        # PLAN alert: OR just closed (within +/-10 min)
        if pd.Timedelta(minutes=-10) <= (now - or_close_ts) <= pd.Timedelta(minutes=10):
            k = f"ORB|{open_ts.isoformat()}|{sess_name}|plan"
            if k not in sent:
                # Find or_close bar
                if or_close_ts in bars5.index:
                    or_close_idx = bars5.index.get_loc(or_close_ts)
                else:
                    # Use latest bar <= or_close_ts
                    mask = bars5.index <= or_close_ts
                    if not mask.any():
                        continue
                    or_close_idx = bars5.index[mask][-1]
                    or_close_idx = bars5.index.get_loc(or_close_idx)
                or_start_idx = max(0, or_close_idx - OR_BARS + 1)
                or_window = bars5.iloc[or_start_idx: or_close_idx + 1]
                or_high = float(or_window["high"].max())
                or_low = float(or_window["low"].min())
                or_range = or_high - or_low
                if or_range <= 0:
                    continue
                cur_slope = float(trend_slope.iloc[or_close_idx])
                trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
                dir_hint = ("LONG only" if cur_slope > 0
                            else "SHORT only" if cur_slope < 0
                            else "SKIP (flat)")
                stop_long = or_high - STOP_MULT * or_range
                target_long = or_high + TP_MULT * or_range
                stop_short = or_low + STOP_MULT * or_range
                target_short = or_low - TP_MULT * or_range

                # Position sizing
                from position_sizing import recommend, SizingConfig, format_for_alert
                from config import load as load_config
                cfg = load_config()
                try:
                    import yfinance as yf
                    gld_p = float(yf.Ticker("GLD").history(period="1d", interval="1h")["Close"].iloc[-1])
                except Exception:
                    gld_p = None
                sz = recommend(
                    stop_dist_per_oz=or_range,
                    gld_price=gld_p,
                    cfg=SizingConfig(mode=cfg["sizing_mode"],
                                      account_equity=cfg["account_equity"],
                                      risk_pct=cfg["risk_pct_per_trade"],
                                      fixed_risk_dollars=cfg["fixed_risk_dollars"]),
                )
                sizing_block = format_for_alert(sz)

                msg = (f"📊 *{sess_name} ORB PLAN* {session_emoji(sess_name)}\n"
                       f"   Opening range ({fmt_et(open_ts)} → {fmt_et(or_close_ts)})\n"
                       f"   H = *${or_high:,.2f}*  ·  L = *${or_low:,.2f}*  ·  range ${or_range:.2f}\n\n"
                       f"   ↗️ LONG: buy-stop *${or_high:,.2f}*  "
                       f"stop ${stop_long:,.2f}  tgt ${target_long:,.2f}\n"
                       f"   ↘️ SHORT: sell-stop *${or_low:,.2f}*  "
                       f"stop ${stop_short:,.2f}  tgt ${target_short:,.2f}\n\n"
                       f"   Trend filter (1h EMA50 slope {cur_slope:+.2f}): *{dir_hint}*\n"
                       f"   Watch {WATCH * 5}min for breakout, cancel after.\n"
                       f"   Time exit: {HOLD * 5}min max.\n\n"
                       f"{sizing_block}")
                send(msg)
                sent.add(k)
                actions.append(("orb_plan", sess_name, open_ts))

    state["sent"] = sorted(sent)
    save_state(state)
    return actions


if __name__ == "__main__":
    a = dispatch_orb_alerts()
    if not a:
        print(f"[orb] {pd.Timestamp.now(tz='UTC').isoformat(timespec='minutes')}  no ORB alerts due.")
    else:
        for action, sess, ts in a:
            print(f"[orb] {action} {sess} {ts}")
