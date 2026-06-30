"""Daily brief publisher — 1 fixed publication per UTC day.

Posts once per UTC day at BRIEF_HOUR_UTC. State persisted in
dispatch_state.json under key "daily_brief|YYYY-MM-DD" to dedupe.

Brief contents:
  - Yesterday: tracker P&L summary (n trades, win%, net P&L)
  - Today: macro events in next 24h with stand-down windows
  - Today: session-open clock (LON / NY / ASIA in UTC + local)
  - Markets: GC close, ATR, trend, Bitget price + basis, funding regime

This is the public-feed daily anchor. Pre-session calls + plan
alerts publish their own messages on top of this.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, time
import json
import pandas as pd
import pytz

from data_gc import load as gc_load
from mers_v3_peb import compute_atr
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on
from telegram_bot import send

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "dispatch_state.json"
TRACKER_LOG = ROOT / "data" / "tracker" / "orb_forward_log.csv"

BRIEF_HOUR_UTC = 22  # UTC — fires once between 22:00 and 23:00 UTC
TREND_N = 50
ET = pytz.timezone("America/New_York")

DISCLAIMER = ("\n_Not financial advice. Futures trading involves substantial risk "
              "of loss. Past results do not guarantee future performance. "
              "Your capital, your decision._")


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"sent": []}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def _yesterday_summary() -> str:
    if not TRACKER_LOG.exists():
        return "   No tracker data yet."
    df = pd.read_csv(TRACKER_LOG)
    if df.empty:
        return "   No tracker data yet."
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], errors="coerce", utc=True)
    yest = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)).date()
    sub = df[(df["took_trade"] == True) & (df["entry_ts"].dt.date == yest)]
    if sub.empty:
        return f"   No trades fired on {yest}."
    n = len(sub); wins = int((sub["net_pnl"] > 0).sum())
    return (f"   {yest}: n={n}, win={wins}/{n}, net=${sub['net_pnl'].sum():+,.0f}")


def _todays_events() -> str:
    try:
        from calendar_events import build_all
        from mers_v5 import TOP_EVENTS_V5, dedupe_co_released
        cal = dedupe_co_released(build_all())
    except Exception:
        return "   (event calendar unavailable)"
    now = pd.Timestamp.now(tz="UTC")
    tomorrow = now + pd.Timedelta(hours=24)
    upc = cal[(cal["event"].isin(TOP_EVENTS_V5))
              & (cal["ts_utc"] >= now)
              & (cal["ts_utc"] <= tomorrow)].sort_values("ts_utc")
    if upc.empty:
        return "   No top-tier events in next 24h."
    lines = []
    for _, ev in upc.iterrows():
        ts = pd.Timestamp(ev["ts_utc"])
        ts_et = ts.tz_convert(ET).strftime("%H:%M %Z")
        lines.append(f"   📰 {ev['event']}  ·  {ts.strftime('%H:%M')} UTC ({ts_et})  ·  ±15m stand-down")
    return "\n".join(lines)


def _session_clock() -> str:
    today = pd.Timestamp.now(tz="UTC").date()
    lines = []
    for sess_name in ["ASIA", "LON", "NY"]:
        sess_t = session_utc_time_on(today, sess_name)
        open_utc = pd.Timestamp.combine(today, sess_t).tz_localize("UTC")
        open_et = open_utc.tz_convert(ET).strftime("%H:%M %Z")
        flag = {"LON": "🇬🇧", "NY": "🇺🇸", "ASIA": "🇯🇵"}[sess_name]
        lines.append(f"   {flag} {sess_name:5s} open  {sess_t.strftime('%H:%M')} UTC  ({open_et})")
    return "\n".join(lines)


def _market_snapshot() -> str:
    out = []
    try:
        bars = gc_load("60m").sort_index()
        if bars.index.tz is None:
            bars.index = bars.index.tz_localize("UTC")
        atr = compute_atr(bars, 20)
        ema = bars["close"].ewm(span=TREND_N, adjust=False).mean()
        slope = ema.diff(5)
        last = float(bars["close"].iloc[-1])
        a = float(atr.iloc[-1]); s = float(slope.iloc[-1])
        trend = "UP" if s > 0 else "DOWN" if s < 0 else "FLAT"
        out.append(f"   📊 COMEX GC: ${last:,.2f}  ·  ATR(20)/1h ${a:.2f}  ·  EMA{TREND_N} slope {s:+.2f} ({trend})")
    except Exception as e:
        out.append(f"   COMEX snapshot unavailable ({type(e).__name__})")
    try:
        from basis_tracker import current_basis
        b = current_basis()
        if "error" not in b:
            out.append(f"   🔵 Bitget XAUUSDT: ${b['bitget_xauusdt']:,.2f}  ·  basis ${b['basis_dollars']:+.2f} ({b['basis_pct']:+.3f}%)")
    except Exception:
        pass
    try:
        from funding_filter import get_current_regime
        r = get_current_regime()
        ann = r["current_rate"] * 1095
        tag = "EXTREME" if r["extreme"] else "neutral"
        out.append(f"   💱 Funding: {ann:+.2%} ann  ·  P{int(r['abs_percentile']*100)}  ·  {tag}")
    except Exception:
        pass
    return "\n".join(out)


def build_brief() -> str:
    now = pd.Timestamp.now(tz="UTC")
    return (
        f"☀️ *Daily Brief — {now.strftime('%Y-%m-%d')} UTC*\n"
        f"\n*Yesterday:*\n{_yesterday_summary()}\n"
        f"\n*Today — top events (next 24h):*\n{_todays_events()}\n"
        f"\n*Today — session schedule:*\n{_session_clock()}\n"
        f"\n*Market snapshot:*\n{_market_snapshot()}\n"
        f"\n_v7 hybrid live  ·  stand-down enabled  ·  4-box audit gate_"
        f"{DISCLAIMER}"
    )


def maybe_publish_daily_brief() -> bool:
    """Publish brief at BRIEF_HOUR_UTC, once per day. Returns True if sent."""
    now = pd.Timestamp.now(tz="UTC")
    if now.hour != BRIEF_HOUR_UTC:
        return False
    key = f"daily_brief|{now.date().isoformat()}"
    state = _load_state()
    if key in state.get("sent", []):
        return False
    send(build_brief())
    state.setdefault("sent", []).append(key)
    _save_state(state)
    return True


if __name__ == "__main__":
    import sys
    if "--dry" in sys.argv:
        print(build_brief())
    else:
        sent = maybe_publish_daily_brief()
        print(f"daily_brief sent={sent} at {pd.Timestamp.now(tz='UTC').isoformat(timespec='minutes')}")
