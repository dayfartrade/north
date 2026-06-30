"""Format MERS v5 alerts into human-readable Telegram messages."""
from __future__ import annotations
import pandas as pd
import pytz
import numpy as np

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v3_peb import compute_atr
from mers_v5 import (TOP_EVENTS_V5, WATCH, MAX_HOLD, B_ATR, STOP_MULT,
                       TP_MULT, TREND_N, dedupe_co_released)

ET = pytz.timezone("America/New_York")


def fmt_et(ts):
    return pd.Timestamp(ts).tz_convert(ET).strftime("%Y-%m-%d %H:%M %Z")


def event_emoji(ev: str) -> str:
    return {"FOMC": "🏛️", "JOBS": "👷", "CPI": "📈"}.get(ev, "📰")


def upcoming_alert(horizon_hours: int = 72) -> str:
    bars = gc_load("60m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=TREND_N, adjust=False).mean()
    slope = ema.diff(5)
    cal = dedupe_co_released(build_all())
    cal = cal[cal["event"].isin(TOP_EVENTS_V5)]
    now = pd.Timestamp.now(tz="UTC")
    horizon = now + pd.Timedelta(hours=horizon_hours)
    upc = cal[(cal["ts_utc"] >= now) & (cal["ts_utc"] <= horizon)].sort_values("ts_utc")

    last_close = float(bars["close"].iloc[-1])
    cur_atr = float(atr.iloc[-1])
    cur_slope = float(slope.iloc[-1])
    trend = "UP 🟢" if cur_slope > 0 else "DOWN 🔴" if cur_slope < 0 else "FLAT ⚪"

    header = (f"*GoldDayTrader — Upcoming events*\n"
              f"_({horizon_hours}h horizon)_\n\n"
              f"GC last close: *${last_close:,.2f}*\n"
              f"ATR(20)/1h: *${cur_atr:.2f}*\n"
              f"EMA{TREND_N} slope (5h): *{cur_slope:+.2f}* → trend *{trend}*\n")

    if upc.empty:
        return header + f"\nNo top-tier events ({', '.join(TOP_EVENTS_V5)}) in window."

    body = "\n*Scheduled signals:*\n"
    for _, ev in upc.iterrows():
        ts = pd.Timestamp(ev["ts_utc"])
        ev_type = ev["event"]
        dir_hint = "LONG only" if cur_slope > 0 else "SHORT only" if cur_slope < 0 else "SKIP (flat trend)"
        body += (f"\n{event_emoji(ev_type)} *{ev_type}*  ·  {fmt_et(ts)}\n"
                 f"   trend filter says: _{dir_hint}_")
    body += "\n\n*Trade rules (frozen v5):*"
    body += (f"\n• Watch event-bar close + {WATCH} bars\n"
             f"• Long-stop @ H + {B_ATR}·ATR  ·  short-stop @ L − {B_ATR}·ATR\n"
             f"• Stop: opposite side of event-bar range × {STOP_MULT}\n"
             f"• Target: {TP_MULT}× event-bar range  (R:R = {TP_MULT/STOP_MULT:.1f})\n"
             f"• Time exit: {MAX_HOLD} bars max\n"
             f"• Only take signal in trend direction.")
    return header + body


def imminent_alert(event_row, atr_value: float, slope_value: float, bar_ts) -> str:
    """Alert sent 30-60 min before an event."""
    ev_type = event_row["event"]
    ts = pd.Timestamp(event_row["ts_utc"])
    dir_hint = "LONG breakouts only" if slope_value > 0 else "SHORT breakouts only" if slope_value < 0 else "SKIP"
    return (f"⚠️ *Event in ~1 hour*  {event_emoji(ev_type)} *{ev_type}*\n"
            f"   Release: {fmt_et(ts)}\n"
            f"   Pre-event ATR(20): ${atr_value:.2f}\n"
            f"   Trend filter: *{dir_hint}*\n"
            f"   Buffer (entry offset): ${B_ATR * atr_value:.2f}\n"
            f"   Watch event bar close at {fmt_et(bar_ts + pd.Timedelta(hours=1))}")


def trade_plan_alert(plan: dict) -> str:
    """After event bar closes, send the concrete buy/sell levels."""
    bar_ts = plan["event_bar_ts"]
    ev = plan["event_type"]
    return (f"📊 *PLAN — {ev}* (event bar closed {fmt_et(bar_ts)})\n"
            f"   H = ${plan['ev_high']:.2f}, L = ${plan['ev_low']:.2f}, "
            f"range = ${plan['ev_range']:.2f}\n"
            f"   {'• Long-stop ' if plan['trend'] > 0 else ''}@ ${plan.get('long_trig', float('nan')):.2f}"
            if plan["trend"] > 0 else
            f"   • Short-stop @ ${plan.get('short_trig', float('nan')):.2f}\n")
