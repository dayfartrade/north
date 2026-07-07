"""Visually polished Telegram alert formatters (v2, 2026-07-07).

Design goals:
  1. Scannable in <5 seconds — key levels bold and separated
  2. Consistent visual language across all 5 alert types
  3. Complete context in one message — no click-through required
  4. Renders cleanly on mobile Telegram (checked: em-dash rules, emoji)

Public API:
  plan_public(payload)       -> str
  preview(payload)           -> str
  pre(payload)               -> str
  stand_down(payload)        -> str
  filtered(payload)          -> str

Each function returns a Telegram-Markdown (legacy) string. Bold with *,
italic with _, no MarkdownV2 escaping needed.
"""
from __future__ import annotations
import pandas as pd
import pytz

ET = pytz.timezone("America/New_York")

RULE = "━━━━━━━━━━━━━━━━━━━━━━━━"

SESSION_EMOJI = {"LON": "🇬🇧", "NY": "🇺🇸", "ASIA": "🇯🇵"}

DISCLAIMER_PLAIN = (
    "Not financial advice. Futures trading involves substantial risk of loss. "
    "Past results do not guarantee future performance. Your capital, your decision."
)
DISCLAIMER = f"_{DISCLAIMER_PLAIN}_"  # Telegram-italicized form


def _emoji(sess: str) -> str:
    return SESSION_EMOJI.get(sess, "📍")


def _fmt_et(ts) -> str:
    """HH:MM ET — short form, since context (date) is usually clear."""
    return pd.Timestamp(ts).tz_convert(ET).strftime("%H:%M ET")


def _fmt_et_long(ts) -> str:
    """YYYY-MM-DD HH:MM ET — used at message top for full disambiguation."""
    return pd.Timestamp(ts).tz_convert(ET).strftime("%a %b %d · %H:%M ET")


def _money(x: float, cents: bool = True) -> str:
    """$4,132.80 with thousands separators."""
    if cents:
        return f"${x:,.2f}"
    return f"${x:,.0f}"


def _signed_money(x: float) -> str:
    """+$18.60 / -$12.40"""
    sign = "+" if x >= 0 else "-"
    return f"{sign}${abs(x):,.2f}"


# ---------------------------------------------------------------------------
# PLAN — the flagship alert, sent right after OR closes
# ---------------------------------------------------------------------------

def plan_public(payload: dict) -> str:
    """Build the polished PLAN alert.

    Required payload keys:
      session, version, or_open_ts, or_close_ts,
      or_high, or_low, or_range,
      long_entry, long_stop, long_target,
      short_entry, short_stop, short_target,
      stop_dist, target_dist, rr_ratio,
      trend, dir_hint,
      watch_end_ts, hold_hours,
      funding_line, basis_line, cot_line, vol_line,   # already-formatted or ""
      sd_windows,                                     # list of str
    """
    sess = payload["session"]
    e = _emoji(sess)

    long_stop_delta = payload["long_stop"] - payload["long_entry"]
    long_target_delta = payload["long_target"] - payload["long_entry"]
    short_stop_delta = payload["short_stop"] - payload["short_entry"]
    short_target_delta = payload["short_target"] - payload["short_entry"]

    lines = [
        f"📊 *{sess} ORB PLAN* {e}  ·  _{payload['version']}_",
        RULE,
        f"🕒 OR window: {_fmt_et(payload['or_open_ts'])} → {_fmt_et(payload['or_close_ts'])}",
        "",
        "🎯 *OPENING RANGE*",
        f"   High     *{_money(payload['or_high'])}*",
        f"   Low      *{_money(payload['or_low'])}*",
        f"   Range     {_money(payload['or_range'])}",
        RULE,
        "🟢 *LONG SETUP*",
        f"   Entry    *{_money(payload['long_entry'])}*",
        f"   Stop      {_money(payload['long_stop'])}   ({_signed_money(long_stop_delta)})",
        f"   Target    {_money(payload['long_target'])}   ({_signed_money(long_target_delta)})",
        f"   R:R       {payload['rr_ratio']:.1f}R",
        "",
        "🔴 *SHORT SETUP*",
        f"   Entry    *{_money(payload['short_entry'])}*",
        f"   Stop      {_money(payload['short_stop'])}   ({_signed_money(short_stop_delta)})",
        f"   Target    {_money(payload['short_target'])}   ({_signed_money(short_target_delta)})",
        f"   R:R       {payload['rr_ratio']:.1f}R",
        RULE,
        f"📈 *Trend:* {payload['trend']} → _{payload['dir_hint']}_",
        f"⏰ Cancel unfilled stops at {_fmt_et(payload['watch_end_ts'])}",
        f"⏳ Time-exit {payload['hold_hours']:.1f}h after fill",
    ]

    # Stand-down windows (only if any)
    sd_windows = payload.get("sd_windows") or []
    if sd_windows:
        lines += ["", "⛔ *Don't enter during:*"]
        for w in sd_windows:
            lines.append(f"   • {w}")

    # Market context — only include boxes that returned non-empty
    ctx_lines = []
    for key in ("funding_line", "basis_line", "cot_line", "vol_line"):
        s = (payload.get(key) or "").strip()
        if s:
            # Strip the leading '   ' indent the old blocks used, we re-indent uniformly
            ctx_lines.append("   " + s.lstrip())
    if ctx_lines:
        lines += [RULE, "🧭 *Market context*"] + ctx_lines

    # Sizing footer
    lines += [
        RULE,
        "📐 *Position sizing*",
        "   Size to your own risk. Rough guide:",
        "   risk ≈ stop-distance × $100/oz × contracts (GC)",
        "                       × $10/oz  × contracts (MGC)",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PREVIEW — ~30 min before session open
# ---------------------------------------------------------------------------

def preview(payload: dict) -> str:
    sess = payload["session"]
    e = _emoji(sess)
    lines = [
        f"⏰ *{sess} session in ~30 min* {e}",
        RULE,
        f"🕒 Opens: {_fmt_et_long(payload['open_ts'])}",
        f"📏 OR builds over next {payload['or_bars_min']} min",
        "",
        f"📈 Pre-session trend: *{payload['trend']}*  (slope {payload['slope']:+.2f})",
        f"📉 ATR(20): {_money(payload['atr'])}",
        f"⚙️ Geometry: _{payload['geom_summary']}_",
    ]
    sd_windows = payload.get("sd_windows") or []
    if sd_windows:
        lines += ["", "⛔ *Don't enter during:*"]
        for w in sd_windows:
            lines.append(f"   • {w}")

    ctx_lines = []
    for key in ("funding_line", "basis_line"):
        s = (payload.get(key) or "").strip()
        if s:
            ctx_lines.append("   " + s.lstrip())
    if ctx_lines:
        lines += [RULE, "🧭 *Market context*"] + ctx_lines

    lines += ["", "_Plan alert with entry levels posts when OR closes._"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PRE — ~15 min before OR closes
# ---------------------------------------------------------------------------

def pre(payload: dict) -> str:
    sess = payload["session"]
    e = _emoji(sess)
    return "\n".join([
        f"🕐 *{sess} ORB forming* {e}",
        RULE,
        f"🕒 OR window: {_fmt_et(payload['open_ts'])} → {_fmt_et(payload['or_close_ts'])}",
        f"📈 1h trend: *{payload['trend']}*  (slope {payload['slope']:+.2f})",
        "",
        "_Plan alert with entry levels posts when OR closes._",
    ])


# ---------------------------------------------------------------------------
# STAND-DOWN — OR overlaps news, skip this session
# ---------------------------------------------------------------------------

def stand_down(payload: dict) -> str:
    sess = payload["session"]
    e = _emoji(sess)
    return "\n".join([
        f"⏸ *{sess} ORB STAND-DOWN* {e}",
        RULE,
        f"⚠️ OR window overlaps news: *{payload['news_reason']}*",
        "",
        "_Skipping this session — OR levels unreliable on event bars._",
    ])


# ---------------------------------------------------------------------------
# FILTERED — OR range too wide vs ATR
# ---------------------------------------------------------------------------

def filtered(payload: dict) -> str:
    sess = payload["session"]
    e = _emoji(sess)
    return "\n".join([
        f"⏸ *{sess} ORB FILTERED* {e}",
        RULE,
        f"📏 OR range {_money(payload['or_range'])} exceeds "
        f"{payload['or_atr_mult']}× ATR ({_money(payload['atr_limit'])})",
        "",
        "_Skipping — high-vol opens historically lose on this session._",
    ])


# ---------------------------------------------------------------------------
# PRIVATE / operator alerts (owner-only, diagnostic-detail welcome)
# ---------------------------------------------------------------------------

def validation_suppressed(payload: dict) -> str:
    return "\n".join([
        "🛑 *ORB DISPATCH SUPPRESSED*",
        RULE,
        f"Reason: {payload['reason']}",
        "",
        "_Fix, then run:_",
        "`python -m src.weekly_validation --persist`",
    ])


def data_lag_persisting(payload: dict) -> str:
    return "\n".join([
        "🚨 *ORB PLAN data-lag persisting*",
        RULE,
        f"Session:    *{payload['session']}*  {_emoji(payload['session'])}",
        f"Window:     {pd.Timestamp(payload['or_close_ts']).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Bar age:    {payload['lag_min']:.0f} min  (limit {payload['limit_min']})",
        "",
        "_yfinance is stalling. PLAN suppressed until fresh bars arrive._",
        "_Check the feed._",
    ])


def sizing_followup(payload: dict) -> str:
    sess = payload["session"]
    return "\n".join([
        f"📐 *{sess} sizing* {_emoji(sess)}  ·  _your config_",
        RULE,
        payload["sizing_block"].rstrip(),
    ])


def heartbeat(payload: dict) -> str:
    bf = payload["bar_freshness"]
    stale = "⚠️ STALE" if bf["stale"] else "✅ fresh"
    market = "🟢 OPEN" if payload["market_open"] else "🔴 CLOSED (weekend gap)"
    ts_str = pd.Timestamp(payload["now_utc"]).strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join([
        "💓 *system heartbeat*",
        RULE,
        f"Time:      {ts_str}",
        f"GC bar:    {bf['last_bar_utc'][:16]}  ({bf['age_hours']:.1f}h old · {stale})",
        f"Market:    {market}",
    ])


def _direction_arrow(direction: int) -> str:
    return "LONG 🟢" if direction > 0 else "SHORT 🔴" if direction < 0 else "?"


def _exit_reason(exit_price: float, stop_price: float, target_price: float,
                 direction: int) -> tuple[str, str]:
    """Return (short_tag, verbose_line). Matches on approximate equality
    since fills sometimes round through the level."""
    tol = 0.01  # 1 cent tolerance for a level match
    if abs(exit_price - target_price) < tol:
        return "target hit ✅", "target"
    if abs(exit_price - stop_price) < tol:
        return "stopped out ❌", "stop"
    # Neither level exact — most likely a time exit (or partial that filled off-level)
    return "time exit ⏰", "time"


def trade_postmortem(payload: dict) -> str:
    """Trust-building trade recap. Fires ~15-45 min after exit (natural
    latency of the 30-min dispatch tick). R-framed so subscribers can
    apply to their own sizing.

    Required payload keys:
      session, version, direction, entry_price, exit_price, stop_price,
      target_price, entry_ts, exit_ts, r_multiple, mae_r, mfe_r
    """
    sess = payload["session"]
    e = _emoji(sess)
    dir_str = _direction_arrow(int(payload["direction"]))
    exit_tag, _ = _exit_reason(
        float(payload["exit_price"]),
        float(payload["stop_price"]),
        float(payload["target_price"]),
        int(payload["direction"]),
    )
    duration_min = int((pd.Timestamp(payload["exit_ts"]) -
                        pd.Timestamp(payload["entry_ts"])).total_seconds() / 60)
    r = float(payload["r_multiple"])
    r_sign = "📈" if r > 0 else "📉" if r < 0 else "⏸"
    lines = [
        f"📊 *{sess} ORB · TRADE RECAP* {e}  ·  _{payload['version']}_",
        RULE,
        f"Setup:     *{dir_str}* @ {_money(payload['entry_price'])}",
        f"Exit:       {_money(payload['exit_price'])}   ({exit_tag})",
        f"Duration:   {duration_min} min",
        f"Result:    *{r:+.1f}R*  {r_sign}",
    ]
    mae = payload.get("mae_r")
    mfe = payload.get("mfe_r")
    if mae is not None and mfe is not None:
        lines += [RULE, f"📏 MAE was {float(mae):+.1f}R,  MFE was {float(mfe):+.1f}R"]
    return "\n".join(lines)


def dispatch_gap(payload: dict) -> str:
    prev_str = pd.Timestamp(payload["prev_ts"]).strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join([
        "⚠️ *dispatch gap detected*",
        RULE,
        f"Previous tick:  {prev_str}",
        f"Gap:            {payload['gap_min']:.0f} min  (normal cadence 30 min)",
        "",
        "_Scheduler skipped or was offline. Resumed now._",
    ])
