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
from stand_down import (stand_down_for_or_window, stand_down_for_entry,
                          _load_calendar, MAJOR_NEWS, NEWS_BUFFER_MINUTES,
                          LON_FIX_TIMES_LOCAL, FIX_BUFFER_MINUTES, _LON_TZ)
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
MAX_BAR_LAG_MIN = 15     # max age of latest 5m bar vs or_close_ts to trust OR levels
PLAN_WINDOW_BEFORE = 10  # min before or_close still allowed to fire (asymmetric)
PLAN_WINDOW_AFTER = 35   # min after or_close — wide enough for 14:30 backstop tick

DISCLAIMER = ("\n_Not financial advice. Futures trading involves substantial risk "
              "of loss. Past results do not guarantee future performance. "
              "Your capital, your decision._")

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
            arrow = "▲ longs crowded — fade short" if r["regime_tilt"] < 0 \
                    else "▼ shorts crowded — fade long"
            return f"   💱 Funding {ann:+.1%} ann (extreme P{int(r['abs_percentile']*100)}) · {arrow}\n"
        # Suppress neutral funding line to reduce noise; only show when interesting
        return ""
    except Exception as e:
        return f"   💱 Funding ctx unavailable ({type(e).__name__})\n"


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


def _upcoming_standdown(start_ts: pd.Timestamp, end_ts: pd.Timestamp,
                          cal: pd.DataFrame) -> list[str]:
    """Return human-readable list of stand-down windows that fall within
    [start_ts, end_ts]. Used by the PLAN alert so traders see when NOT to enter."""
    windows = []
    # News events in window
    if cal is not None and not cal.empty:
        relevant = cal[cal["event"].isin(MAJOR_NEWS)]
        for _, ev in relevant.iterrows():
            ev_ts = pd.Timestamp(ev["ts_utc"])
            if ev_ts.tz is None:
                ev_ts = ev_ts.tz_localize("UTC")
            buf = pd.Timedelta(minutes=NEWS_BUFFER_MINUTES)
            if (ev_ts + buf >= start_ts) and (ev_ts - buf <= end_ts):
                windows.append(f"news {ev['event']} {ev_ts.strftime('%H:%M')}UTC "
                                f"(±{NEWS_BUFFER_MINUTES}m)")
    # London fix windows in [start, end]
    for fix_t in LON_FIX_TIMES_LOCAL:
        # Check each date the watch window spans (rare to cross days, but be safe)
        for d_off in (0, 1):
            day = (start_ts.astimezone(_LON_TZ) + pd.Timedelta(days=d_off)).normalize()
            fix_dt_lon = day + pd.Timedelta(hours=fix_t.hour, minutes=fix_t.minute)
            fix_utc = fix_dt_lon.tz_convert("UTC")
            buf = pd.Timedelta(minutes=FIX_BUFFER_MINUTES)
            if (fix_utc + buf >= start_ts) and (fix_utc - buf <= end_ts):
                windows.append(f"LON fix {fix_t.strftime('%H:%M')}LT "
                                f"= {fix_utc.strftime('%H:%M')}UTC (±{FIX_BUFFER_MINUTES}m)")
    return windows


def _log(msg: str):
    """File log when invoked under pythonw (stdout discarded)."""
    import builtins
    fn = getattr(builtins, "_dispatch_log", None)
    if fn:
        fn(msg)
    else:
        print(msg)


def _safe_send(msg: str, sent: set, key: str, actions: list, action_tag: str,
                sess_name: str, open_ts: pd.Timestamp) -> bool:
    """Wrap send() so a Telegram failure still marks the key sent.

    This prevents duplicate-alert storms when Telegram glitches: at-most-once
    semantics with the cost of possibly missing the alert. We log the failure
    so it shows in dispatch output.
    """
    try:
        send(msg)
        sent.add(key)
        actions.append((action_tag, sess_name, open_ts))
        _log(f"[orb] SENT {action_tag} {sess_name} {open_ts}")
        return True
    except Exception as e:
        _log(f"[orb] send FAILED for {action_tag} {sess_name}: {type(e).__name__}: {e}")
        sent.add(key)  # don't retry — at-most-once
        actions.append((f"{action_tag}_send_failed", sess_name, open_ts))
        return False


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
                # Heads-up: upcoming entry stand-down windows during OR+watch
                watch_end = open_ts + pd.Timedelta(minutes=5 * (OR_BARS + WATCH))
                sd_windows = _upcoming_standdown(open_ts, watch_end, cal)
                sd_line = ("   ⛔ Don't enter during: " + " · ".join(sd_windows) + "\n"
                           if sd_windows else "")
                cfg_line = ("   geom: LON filter OR<2×ATR + fixed $13 stop, 1.5R target\n"
                            if cfg.get("use_or_filter") else
                            "   geom: stop=OR-range, target=1.5×OR\n")
                msg = (f"⏰ *{sess_name} session in ~30min* {session_emoji(sess_name)}\n"
                       f"   Open {fmt_et(open_ts)}  ·  OR builds {OR_BARS*5}min after\n"
                       f"   Pre-session trend: *{trend}* (slope {cur_slope:+.2f})  ·  ATR ${cur_atr:.2f}\n"
                       f"{cfg_line}{sd_line}"
                       f"{_funding_context()}{_basis_context()}"
                       f"   Plan alert posts when OR closes.")
                _safe_send(msg, sent, k, actions, "orb_preview", sess_name, open_ts)

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
                _safe_send(msg, sent, k, actions, "orb_pre", sess_name, open_ts)

        # ---- PLAN alert: OR just closed. Asymmetric window: small grace
        # before or_close (catches early dispatch ticks), wide buffer after
        # so a deferred 14:00 tick gets a second chance at the 14:30 tick
        # with fresh bars.
        if (pd.Timedelta(minutes=-PLAN_WINDOW_BEFORE) <= (now - or_close_ts)
              <= pd.Timedelta(minutes=PLAN_WINDOW_AFTER)):
            k = f"ORB|{open_ts.isoformat()}|{sess_name}|plan"
            if k not in sent:
                # ----- Box 2: OR-window news stand-down (skip ONLY if OR bars overlap
                # a top-tier news release — fix windows do NOT invalidate OR levels,
                # they're handled by per-entry stand-down advisory below).
                news_overlap = False
                news_reason = ""
                if cal is not None and not cal.empty:
                    relevant = cal[cal["event"].isin(MAJOR_NEWS)]
                    for _, ev in relevant.iterrows():
                        ev_ts = pd.Timestamp(ev["ts_utc"])
                        if ev_ts.tz is None: ev_ts = ev_ts.tz_localize("UTC")
                        buf = pd.Timedelta(minutes=NEWS_BUFFER_MINUTES)
                        if (ev_ts + buf >= open_ts) and (ev_ts - buf <= or_close_ts):
                            news_overlap = True
                            news_reason = f"{ev['event']}@{ev_ts.strftime('%H:%M')}UTC"
                            break
                if news_overlap:
                    msg = (f"⏸ *{sess_name} ORB STAND-DOWN* {session_emoji(sess_name)}\n"
                           f"   Opening range overlaps news: {news_reason}\n"
                           f"   Skipping this session — OR levels unreliable on event bars.")
                    _safe_send(msg, sent, k, actions, "orb_standdown", sess_name, open_ts)
                    continue

                # Find or_close bar
                if or_close_ts in bars5.index:
                    or_close_idx = bars5.index.get_loc(or_close_ts)
                else:
                    mask = bars5.index <= or_close_ts
                    if not mask.any():
                        continue
                    latest_bar_ts = bars5.index[mask][-1]
                    lag_min = (or_close_ts - latest_bar_ts).total_seconds() / 60
                    if lag_min > MAX_BAR_LAG_MIN:
                        # Data lag too large — bars don't cover the OR window.
                        # Skip THIS tick (don't dedup) so a fresher tick can retry.
                        _log(f"[orb] {sess_name} PLAN DEFERRED: latest bar "
                             f"{latest_bar_ts} is {lag_min:.0f}min before "
                             f"or_close_ts {or_close_ts} (lag > {MAX_BAR_LAG_MIN}min)")
                        continue
                    or_close_idx = bars5.index.get_loc(latest_bar_ts)
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
                        _safe_send(msg, sent, k, actions, "orb_filtered", sess_name, open_ts)
                        continue

                # ----- Geometry per session config
                if cfg.get("stop_mode") == "fixed":
                    stop_dist = float(cfg["fixed_stop_price"])
                    geom_tag = f"${stop_dist:.0f} fixed"
                else:
                    stop_dist = or_range
                    geom_tag = f"${stop_dist:.2f} (=OR range)"
                if cfg.get("target_mode") == "stop_x_tp":
                    target_dist = TP_MULT * stop_dist
                else:
                    target_dist = TP_MULT * or_range
                rr_ratio = target_dist / stop_dist if stop_dist > 0 else 0

                trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
                dir_hint = ("LONG only (trend up)" if cur_slope > 0
                            else "SHORT only (trend down)" if cur_slope < 0
                            else "SKIP — trend flat")
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

                # Compute upcoming entry stand-down windows during watch
                watch_end = or_close_ts + pd.Timedelta(minutes=5 * WATCH)
                sd_windows = _upcoming_standdown(or_close_ts, watch_end, cal)
                sd_block = ("   ⛔ Don't enter during: " + " · ".join(sd_windows) + "\n"
                            if sd_windows else "")

                msg = (f"📊 *{sess_name} ORB PLAN* {session_emoji(sess_name)}  ·  v7\n"
                       f"   OR window: {fmt_et(open_ts)} → {fmt_et(or_close_ts)}\n"
                       f"   H *${or_high:,.2f}*  ·  L *${or_low:,.2f}*  ·  range ${or_range:.2f}\n"
                       f"   Stop {geom_tag}  ·  target ${target_dist:.2f} ({rr_ratio:.1f}R)\n\n"
                       f"   ↗️ LONG  entry *${or_high:,.2f}*  ·  stop ${stop_long:,.2f}  ·  tgt ${target_long:,.2f}\n"
                       f"   ↘️ SHORT entry *${or_low:,.2f}*  ·  stop ${stop_short:,.2f}  ·  tgt ${target_short:,.2f}\n\n"
                       f"   Trend: *{dir_hint}*\n"
                       f"   Cancel both stops if no breakout in {WATCH*5}min.\n"
                       f"   Time-exit if still open after {HOLD*5}min.\n"
                       f"{sd_block}\n"
                       f"{fund_block}{basis_block}"
                       f"{sizing_block}"
                       f"{DISCLAIMER}")
                _safe_send(msg, sent, k, actions, "orb_plan", sess_name, open_ts)

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
