"""Telegram card formatter + publisher for FAR Weekly Gold Read.

Two message types:
  1. Weekly call — fires Sunday when a new call is published
  2. Weekly resolve — fires Friday (or next Sunday) when prior call is resolved

Card design goals:
  - Direction badge dominant (LONG / SHORT / FLAT)
  - Entry / stop / exit prices clear + copyable
  - Signal drivers in one line (M20, M60, MA, RY)
  - Track record: n calls, WR, cum return
  - Risk profile: max DD, worst year, position sizing hint
  - Compact enough for mobile Telegram — renders in ~15 lines

Uses Markdown legacy formatting (compat with existing bot).
"""
from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent

RULE = "━━━━━━━━━━━━━━━━━━━━━━━━"


def _direction_badge(direction: str) -> str:
    if direction == "LONG":
        return "🟢 *LONG*"
    if direction == "SHORT":
        return "🔴 *SHORT*"
    return "⚪ *FLAT*"


def _dir_emoji(direction: str) -> str:
    return {"LONG": "📈", "SHORT": "📉", "FLAT": "⏸"}.get(direction, "•")


def format_weekly_call(call: dict, track: dict | None = None) -> str:
    """Format a FAR Weekly call for Telegram publication."""
    direction = call.get("direction", "?")
    week_of = call.get("week_of", "?")
    week_end = call.get("week_end", "?")
    entry = call.get("entry_approx")
    stop = call.get("stop_price")
    atr = call.get("atr_20d")
    sc = call.get("signal_components", {})

    lines = [
        f"⭐ *FAR WEEKLY GOLD READ*",
        f"_by Knox_  ·  _week of {week_of}_",
        RULE,
        f"{_direction_badge(direction)}  {_dir_emoji(direction)}",
    ]

    if direction == "FLAT":
        lines += [
            "",
            "No position this week — signal filters disagreed.",
            f"Next check: Sunday after {week_end}.",
        ]
    else:
        lines += [
            "",
            f"📍 *Entry* (Mon 13:00 UTC): *${entry:,.2f}*",
            f"🛑 *Stop*: *${stop:,.2f}*",
            f"🏁 *Exit*: Fri 21:00 UTC (time exit)",
            f"📊 ATR(20d): ${atr:.2f}  ·  ~{abs(entry-stop):.2f} risk per oz",
        ]

    # Signal drivers
    lines += [
        RULE,
        "*Signal drivers*",
    ]
    m20 = sc.get("M20_pct")
    m60 = sc.get("M60_pct")
    ma = sc.get("MA10_above_MA40")
    ry = sc.get("RY_chg_20d_bps")
    if m20 is not None:
        s = f"{m20:+.2f}%"
        lines.append(f"  4-week momentum   {s:>10s}  {'✅' if (direction == 'LONG' and m20 > 0) or (direction == 'SHORT' and m20 < 0) else ('❌' if direction != 'FLAT' else '·')}")
    if m60 is not None:
        s = f"{m60:+.2f}%"
        lines.append(f"  12-week momentum  {s:>10s}  {'✅' if (direction == 'LONG' and m60 > 0) or (direction == 'SHORT' and m60 < 0) else ('❌' if direction != 'FLAT' else '·')}")
    if ma is not None:
        s = ("10d > 40d" if ma else "10d < 40d")
        lines.append(f"  MA trend          {s:>10s}  {'✅' if (direction == 'LONG' and ma) or (direction == 'SHORT' and not ma) else ('❌' if direction != 'FLAT' else '·')}")
    if ry is not None:
        s = f"{ry:+.1f} bps"
        lines.append(f"  Real yield Δ 4w   {s:>10s}  {'✅' if (direction == 'LONG' and ry < 0) or (direction == 'SHORT' and ry > 0) else ('❌' if direction != 'FLAT' else '·')}")

    # Track record
    if track and track.get("resolved_calls", 0) > 0:
        lines += [
            RULE,
            "*Live track record*",
            f"  Calls resolved:  {track['resolved_calls']}",
            f"  Win rate:        {track.get('win_rate_pct', 0)}%",
            f"  Cumulative:      {track.get('cumulative_return_pct', 0):+.2f}%",
        ]
    else:
        lines += [
            RULE,
            "*Live track record*",
            "  _Accumulating — resolves every Friday close_",
        ]

    # Full details / how to trade
    lines += [
        RULE,
        "📖 Full details, backtest, position calculator:",
        "   *faractionradar.com/weekly*",
        "",
        "_Not financial advice. Futures carry risk._",
        "_BETA product — 16yr backtest passes but live not yet validated._",
    ]

    return "\n".join(lines)


def format_weekly_resolve(prior_call: dict, outcome: dict) -> str:
    """Format the resolution of last week's call."""
    direction = prior_call.get("direction", "?")
    week_of = prior_call.get("week_of", "?")
    entry = prior_call.get("entry_approx")
    stop = prior_call.get("stop_price")
    exit_price = outcome.get("exit_price")
    exit_reason = outcome.get("exit_reason", "?")
    ret_pct = outcome.get("net_return_pct", 0)

    win = ret_pct > 0
    result_line = ("✅ *WIN*" if win else ("🟥 *LOSS*" if ret_pct < 0 else "➖ *FLAT*"))
    reason_pretty = {
        "friday_close": "closed at Friday 21:00 UTC",
        "stop": "stopped out mid-week",
    }.get(exit_reason, exit_reason)

    lines = [
        f"🏁 *WEEK RESOLVED*",
        f"_FAR Weekly Gold Read · {week_of}_",
        RULE,
        f"{_direction_badge(direction)}  ·  {result_line}",
        "",
        f"📍 Entry:  ${entry:,.2f}" if entry else "",
        f"🏁 Exit:   ${exit_price:,.2f}  ({reason_pretty})" if exit_price else "",
        f"📊 Return: *{ret_pct:+.3f}%* per unit position",
        RULE,
        "Track record updates on the page:",
        "   *faractionradar.com/weekly*",
    ]
    return "\n".join([l for l in lines if l is not None])


def publish_weekly_call(call: dict, track: dict | None = None,
                        audience: str = "public") -> dict:
    """Send the formatted weekly call to Telegram."""
    from telegram_bot import send
    if call.get("direction") == "FLAT":
        # Still send FLAT calls — transparency about signal accuracy
        pass
    msg = format_weekly_call(call, track=track)
    return send(msg, audience=audience)


def publish_weekly_resolve(prior_call: dict, outcome: dict,
                            audience: str = "public") -> dict:
    from telegram_bot import send
    msg = format_weekly_resolve(prior_call, outcome)
    return send(msg, audience=audience)
