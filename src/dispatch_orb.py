"""ORB live dispatcher with v7-hybrid 4-box audit gate.

Runs every 30 min via Task Scheduler (called from dispatch.py).

4-BOX AUDIT GATE (applied per session at PLAN alert):
  Box 1  Signal     : run_orb_v7 per-session config (LON: OR<2*ATR filter +
                       fixed $13 stop; NY/ASIA: OR-range stop/target)
  Box 2  Stand-down : ±15min news, ±10min London-fix (auto via run_orb_v7,
                       cross-checked here for the plan-time announcement)
  Box 3  Funding    : Bitget XAUUSDT funding regime (P85 -> tilt context,
                       SOFT signal — surfaces in alert, does not gate)
  Box 4  Basis      : COMEX vs Bitget divergence > 0.5% -> data-sanity warn

State persisted in dispatch_state.json so we don't re-alert.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on, fetch_higher_tf_trend
from edge_session_orb_v7_final import SESSION_CONFIG, TP_MULT_DEFAULT
from stand_down import stand_down_for_or_window, stand_down_for_entry, _load_calendar
from mers_v3_peb import compute_atr
from telegram_bot import send
from alert_formatter import fmt_et
from health import market_likely_open

OR_BARS = 6       # 30-min opening range on 5m
WATCH = 12        # 60-min breakout window
HOLD = 24         # 2-hour time exit
TP_MULT = TP_MULT_DEFAULT
REQUIRE_TREND = True
BASIS_DIVERGE_PCT = 0.5  # flag if |basis| > this %

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


def _funding_context() -> str:
    """Box 3: funding regime context block (soft signal). Empty string on failure."""
    try:
        from funding_filter import get_current_regime
        r = get_current_regime()
        ann = r["current_rate"] * 1095  # 3x/day * 365
        if r["extreme"]:
            arrow = "▲" if r["regime_tilt"] < 0 else "▼"  # crowded long -> fade short
            return (f"   💱 funding {ann:+.1%} ann (P{int(r['abs_percentile']*100)}) "
                    f"{arrow} {r['reason']}\n")
        return f"   💱 funding {ann:+.1%} ann (P{int(r['abs_percentile']*100)}) neutral\n"
    except Exception as e:
        return f"   💱 funding ctx unavailable ({type(e).__name__})\n"


def _basis_context() -> str:
    """Box 4: basis sanity warning. Empty unless divergence exceeds threshold."""
    try:
        from basis_tracker import current_basis
        b = current_basis()
        if "error" in b:
            return ""
        if abs(b["basis_pct"]) > BASIS_DIVERGE_PCT:
            return (f"   ⚠️ basis ${b['basis_dollars']:+.2f} ({b['basis_pct']:+.2f}%) "
                    f"— GC vs Bitget diverging\n")
        return ""
    except Exception:
        return ""


def dispatch_orb_alerts():
    state = load_state()
    sent = set(state.get("sent", []))
    actions = []

    if not market_likely_open():
        return actions

    bars5 = gc_load("5m").sort_index()
    if bars5.index.tz is None: bars5.index = bars5.index.tz_localize("UTC")
    if bars5.empty:
        return actions
    atr = compute_atr(bars5, 20)
    trend_slope = fetch_higher_tf_trend(bars5)
    cal = _load_calendar()

    now = pd.Timestamp.now(tz="UTC")
    today = now.date()

    for sess_name in SESSIONS_LOCAL:
        cfg = SESSION_CONFIG.get(sess_name, SESSION_CONFIG["NY"])
        sess_t = session_utc_time_on(today, sess_name)
        open_ts = pd.Timestamp.combine(today, sess_t).tz_localize("UTC")
        or_close_ts = open_ts + pd.Timedelta(minutes=5 * OR_BARS)

        # ---- PREVIEW alert: T-30 to T-15 min before session open (pre-session call)
        if pd.Timedelta(minutes=15) <= (open_ts - now) <= pd.Timedelta(minutes=45):
            k = f"ORB|{open_ts.isoformat()}|{sess_name}|preview"
            if k not in sent:
                cur_slope = float(trend_slope.iloc[-1]) if len(trend_slope) else float("nan")
                cur_atr = float(atr.iloc[-1]) if len(atr) else float("nan")
                trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
                # Stand-down check for the OR window
                sd_or, sd_or_reason = stand_down_for_or_window(open_ts, calendar=cal)
                sd_line = (f"   ⛔ stand-down: {sd_or_reason} — session will be skipped\n"
                           if sd_or else "")
                cfg_line = ("   geom: LON filter OR<2×ATR + fixed $13 stop, 1.5R target\n"
                            if cfg.get("use_or_filter") else
                            "   geom: stop=OR-range, target=1.5×OR\n")
                msg = (f"⏰ *{sess_name} session in ~30min* {session_emoji(sess_name)}\n"
                       f"   Open {fmt_et(open_ts)}  ·  OR builds {OR_BARS*5}min after\n"
                       f"   Pre-session trend: *{trend}* (slope {cur_slope:+.2f})  ·  ATR ${cur_atr:.2f}\n"
                       f"{cfg_line}{sd_line}"
                       f"{_funding_context()}{_basis_context()}"
                       f"   Plan alert posts when OR closes.")
                send(msg)
                sent.add(k)
                actions.append(("orb_preview", sess_name, open_ts))

        # ---- PRE alert: ~15 min before OR closes
        if pd.Timedelta(minutes=5) <= (or_close_ts - now) <= pd.Timedelta(minutes=30):
            k = f"ORB|{open_ts.isoformat()}|{sess_name}|pre"
            if k not in sent:
                cur_slope = float(trend_slope.iloc[-1]) if len(trend_slope) else float("nan")
                trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
                msg = (f"🕐 *{sess_name} ORB forming* {session_emoji(sess_name)}\n"
                       f"   Opening range builds: {fmt_et(open_ts)} -> {fmt_et(or_close_ts)}\n"
                       f"   Current 1h trend: *{trend}* (slope {cur_slope:+.2f})\n"
                       f"   Will alert with levels once OR closes.")
                send(msg)
                sent.add(k)
                actions.append(("orb_pre", sess_name, open_ts))

        # ---- PLAN alert: OR just closed (within +/-10 min)
        if pd.Timedelta(minutes=-10) <= (now - or_close_ts) <= pd.Timedelta(minutes=10):
            k = f"ORB|{open_ts.isoformat()}|{sess_name}|plan"
            if k not in sent:
                # ----- Box 2: OR-window stand-down check (skip session entirely)
                sd_or, sd_or_reason = stand_down_for_or_window(open_ts, calendar=cal)
                if sd_or:
                    msg = (f"⏸ *{sess_name} ORB STAND-DOWN* {session_emoji(sess_name)}\n"
                           f"   Opening range overlaps news window: {sd_or_reason}\n"
                           f"   Skipping this session — OR levels unreliable.")
                    send(msg); sent.add(k)
                    actions.append(("orb_standdown", sess_name, open_ts))
                    continue

                # Find or_close bar
                if or_close_ts in bars5.index:
                    or_close_idx = bars5.index.get_loc(or_close_ts)
                else:
                    mask = bars5.index <= or_close_ts
                    if not mask.any():
                        continue
                    or_close_idx = bars5.index.get_loc(bars5.index[mask][-1])
                or_start_idx = max(0, or_close_idx - OR_BARS + 1)
                or_window = bars5.iloc[or_start_idx: or_close_idx + 1]
                or_high = float(or_window["high"].max())
                or_low = float(or_window["low"].min())
                or_range = or_high - or_low
                if or_range <= 0:
                    continue
                cur_slope = float(trend_slope.iloc[or_close_idx])
                cur_atr = float(atr.iloc[or_close_idx])

                # ----- Box 1: per-session OR-vs-ATR filter (LON only per SESSION_CONFIG)
                if cfg.get("use_or_filter", False):
                    or_max = cfg.get("or_vs_atr_max", 2.0) * cur_atr
                    if or_range > or_max:
                        msg = (f"⏸ *{sess_name} ORB FILTERED* {session_emoji(sess_name)}\n"
                               f"   OR range ${or_range:.2f} > {cfg['or_vs_atr_max']}x ATR "
                               f"(${or_max:.2f})\n"
                               f"   Skipping — high-vol open historically loses on this session.")
                        send(msg); sent.add(k)
                        actions.append(("orb_filtered", sess_name, open_ts))
                        continue

                # ----- Geometry per session config
                if cfg.get("stop_mode") == "fixed":
                    stop_dist = float(cfg["fixed_stop_price"])
                    geom_tag = f"fixed ${stop_dist:.0f}"
                else:
                    stop_dist = or_range
                    geom_tag = f"OR=${stop_dist:.2f}"
                if cfg.get("target_mode") == "stop_x_tp":
                    target_dist = TP_MULT * stop_dist
                else:
                    target_dist = TP_MULT * or_range

                trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
                dir_hint = ("LONG only" if cur_slope > 0
                            else "SHORT only" if cur_slope < 0
                            else "SKIP (flat)")
                stop_long = or_high - stop_dist
                target_long = or_high + target_dist
                stop_short = or_low + stop_dist
                target_short = or_low - target_dist

                # ----- Position sizing
                from position_sizing import recommend, SizingConfig, format_for_alert
                from config import load as load_config
                lcfg = load_config()
                try:
                    import yfinance as yf
                    gld_p = float(yf.Ticker("GLD").history(period="1d", interval="1h")["Close"].iloc[-1])
                except Exception:
                    gld_p = None
                sz = recommend(
                    stop_dist_per_oz=stop_dist,
                    gld_price=gld_p,
                    cfg=SizingConfig(mode=lcfg["sizing_mode"],
                                      account_equity=lcfg["account_equity"],
                                      risk_pct=lcfg["risk_pct_per_trade"],
                                      fixed_risk_dollars=lcfg["fixed_risk_dollars"]),
                )
                sizing_block = format_for_alert(sz)

                # ----- Box 3 & 4 context blocks
                fund_block = _funding_context()
                basis_block = _basis_context()

                msg = (f"📊 *{sess_name} ORB PLAN* {session_emoji(sess_name)}  v7\n"
                       f"   Opening range ({fmt_et(open_ts)} -> {fmt_et(or_close_ts)})\n"
                       f"   H = *${or_high:,.2f}*  ·  L = *${or_low:,.2f}*  ·  range ${or_range:.2f}\n"
                       f"   Geometry: stop {geom_tag}  ·  TP {TP_MULT}x stop  ·  ATR ${cur_atr:.2f}\n\n"
                       f"   ↗️ LONG: buy-stop *${or_high:,.2f}*  "
                       f"stop ${stop_long:,.2f}  tgt ${target_long:,.2f}\n"
                       f"   ↘️ SHORT: sell-stop *${or_low:,.2f}*  "
                       f"stop ${stop_short:,.2f}  tgt ${target_short:,.2f}\n\n"
                       f"   Trend filter (1h EMA50 slope {cur_slope:+.2f}): *{dir_hint}*\n"
                       f"   Watch {WATCH * 5}min for breakout, cancel after.\n"
                       f"   Time exit: {HOLD * 5}min max.\n"
                       f"   ⛔ entry stand-down: ±15min news, ±10min London fix\n\n"
                       f"{fund_block}{basis_block}"
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
