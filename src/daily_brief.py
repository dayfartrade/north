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

from alert_format_v2 import RULE, DISCLAIMER


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
    total = float(sub["net_pnl"].sum())
    win_pct = wins / n * 100 if n else 0
    return (f"   Date:   {yest}\n"
            f"   Trades: {n}   Wins: {wins}/{n}  ({win_pct:.0f}%)\n"
            f"   Net:    ${total:+,.0f}")


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
        lines.append(f"   📰 *{ev['event']}*  ·  {ts.strftime('%H:%M')} UTC  ({ts_et})  ·  _±15m stand-down_")
    return "\n".join(lines)


def _session_clock() -> str:
    today = pd.Timestamp.now(tz="UTC").date()
    lines = []
    for sess_name in ["ASIA", "LON", "NY"]:
        sess_t = session_utc_time_on(today, sess_name)
        open_utc = pd.Timestamp.combine(today, sess_t).tz_localize("UTC")
        open_et = open_utc.tz_convert(ET).strftime("%H:%M %Z")
        flag = {"LON": "🇬🇧", "NY": "🇺🇸", "ASIA": "🇯🇵"}[sess_name]
        lines.append(f"   {flag} *{sess_name}*   {sess_t.strftime('%H:%M')} UTC   ({open_et})")
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
        trend = "UP 📈" if s > 0 else "DOWN 📉" if s < 0 else "FLAT ⏸"
        out.append(f"   COMEX GC     *${last:,.2f}*")
        out.append(f"   ATR(20)/1h    ${a:.2f}")
        out.append(f"   EMA{TREND_N} slope   {s:+.2f}   → {trend}")
    except Exception as e:
        out.append(f"   COMEX snapshot unavailable ({type(e).__name__})")
    try:
        from basis_tracker import current_basis
        b = current_basis()
        if "error" not in b:
            out.append(f"   Bitget XAU    ${b['bitget_xauusdt']:,.2f}")
            basis_d = b['basis_dollars']
            basis_str = f"{'+' if basis_d >= 0 else '-'}${abs(basis_d):.2f}"
            out.append(f"   Basis         {basis_str}   ({b['basis_pct']:+.3f}%)")
    except Exception:
        pass
    try:
        from funding_filter import get_current_regime
        r = get_current_regime()
        ann = r["current_rate"] * 1095
        tag = "EXTREME ⚠️" if r["extreme"] else "neutral"
        out.append(f"   Funding       {ann:+.2%} ann   ·   P{int(r['abs_percentile']*100)}   ·   {tag}")
    except Exception:
        pass
    return "\n".join(out)


def build_public_brief() -> str:
    """Public daily brief — broadcast to subscribers (no account-specific data)."""
    now = pd.Timestamp.now(tz="UTC")
    try:
        from strategy_version import STRATEGY_VERSION
        version = STRATEGY_VERSION
    except Exception:
        version = "v7"
    return "\n".join([
        f"☀️ *DAILY BRIEF* · _{now.strftime('%Y-%m-%d')} UTC_",
        RULE,
        "📅 *Today's top events (next 24h)*",
        _todays_events(),
        RULE,
        "🕒 *Session schedule*",
        _session_clock(),
        RULE,
        "📊 *Market snapshot*",
        _market_snapshot(),
        RULE,
        f"_{version} live  ·  stand-down enabled  ·  4-box audit gate_",
        "",
        DISCLAIMER,
    ])


def build_private_brief() -> str:
    """Private addendum — yesterday's P&L (account-specific, owner only)."""
    return "\n".join([
        "📒 *YESTERDAY'S RESULTS* · _private_",
        RULE,
        _yesterday_summary(),
    ])


def build_shadow_equity_brief() -> str | None:
    """Shadow-equity digest (private, owner only). Returns None if no data.

    Fires alongside daily brief at 22:00 UTC. Summarizes what strategy
    WOULD have decided since kill switch fired 2026-07-13 14:30 UTC.
    """
    try:
        import sys as _sys
        from pathlib import Path as _P
        _sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "scripts"))
        from shadow_equity_dashboard import _load_rows, _summarize_session
    except Exception:
        return None
    rows = _load_rows()
    if not rows:
        return None
    total = _summarize_session(rows)
    lines = [
        "👤 *SHADOW-EQUITY DIGEST* · _private_",
        RULE,
        f"Total decisions since kill switch: {total['n_decisions']}",
        f"Would-take: {total['n_took']}  Skip: {total['n_decisions'] - total['n_took']}",
    ]
    if total["n_took"] > 0:
        lines.append(f"Wins: {total['n_wins']}/{total['n_took']} "
                    f"({100 * total['win_rate']:.0f}%)")
        lines.append(f"Shadow P&L: ${total['total_pnl']:+,.0f} "
                    f"(mean ${total['mean_pnl']:+,.0f}/trade)")
    else:
        lines.append("_no take-decisions yet_")

    # Per-session breakdown
    sessions = sorted(set(r["session"] for r in rows))
    if sessions and total["n_took"] > 0:
        lines.append("")
        lines.append("*Per session:*")
        for sess in sessions:
            sub = [r for r in rows if r["session"] == sess]
            s = _summarize_session(sub)
            if s["n_took"] > 0:
                lines.append(f"  `{sess:5s}` n={s['n_took']:2d} "
                            f"({100 * s['win_rate']:2.0f}%) "
                            f"${s['total_pnl']:+,.0f}")
    return "\n".join(lines)


# Back-compat alias for any older caller (also used by `--dry` flag)
def build_brief() -> str:
    return build_public_brief() + "\n\n" + build_private_brief()


def maybe_publish_daily_brief() -> bool:
    """Publish brief at BRIEF_HOUR_UTC, once per day. Returns True if sent."""
    now = pd.Timestamp.now(tz="UTC")
    if now.hour != BRIEF_HOUR_UTC:
        return False
    key = f"daily_brief|{now.date().isoformat()}"
    state = _load_state()
    if key in state.get("sent", []):
        return False
    # Public daily brief goes to subscribers; private P&L goes to owner only
    send(build_public_brief(), audience="public")
    try:
        send(build_private_brief(), audience="private")
    except Exception:
        pass
    # Shadow-equity digest (private, non-fatal if it fails)
    try:
        _shadow = build_shadow_equity_brief()
        if _shadow:
            send(_shadow, audience="private")
    except Exception:
        pass
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
