"""Telegram card formatter + publisher for FAR Weekly Gold Read (NORTH).

Three message types:
  1. Weekly call - fires Sunday when a new call is published
  2. Weekly resolve - fires when prior call's window closes (Friday close or stop)
  3. Weekly performance - cumulative track record snapshot, fires Sunday
     right before the new call

Card design goals:
  - Direction badge dominant (LONG / SHORT / FLAT)
  - Entry / stop / exit prices clear + copyable
  - Signal drivers in one line per driver, agreement marker
  - Track record: n, win rate, mean return per call, best/worst
  - Honest framing (BETA, small sample where relevant)
  - Mobile-friendly (~20 lines max per card)
  - No URLs pointing at non-existent pages
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


def _driver_check(direction: str, agrees: bool) -> str:
    if direction == "FLAT":
        return "·"
    return "✅" if agrees else "❌"


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
        f"⭐ *NORTH - Weekly Gold Read*",
        f"_by Knox_  ·  _week of {week_of} → {week_end}_",
        RULE,
        f"{_direction_badge(direction)}  {_dir_emoji(direction)}",
    ]

    if direction == "FLAT":
        lines += [
            "",
            "*No position this week.*",
            "Signal filters disagreed. Sitting out is a decision.",
            f"Next update: Sunday after {week_end}.",
        ]
    else:
        risk = abs(entry - stop) if (entry and stop) else 0
        risk_pct = (risk / entry * 100) if entry else 0
        lines += [
            "",
            f"📍 *Entry* (Mon 13:00 UTC): `${entry:,.2f}`",
            f"🛑 *Stop*: `${stop:,.2f}`  ({risk_pct:.2f}% away)",
            f"🏁 *Exit*: Fri 21:00 UTC (time exit, or stop if hit first)",
            f"📊 ATR(20d): ${atr:.2f}  ·  Risk per oz: ${risk:.2f}",
        ]

    # Signal drivers
    lines += [
        RULE,
        "*Why this call*",
    ]
    m20 = sc.get("M20_pct")
    m60 = sc.get("M60_pct")
    ma = sc.get("MA10_above_MA40")
    ry = sc.get("RY_chg_20d_bps")
    if m20 is not None:
        agrees = (direction == 'LONG' and m20 > 0) or (direction == 'SHORT' and m20 < 0)
        lines.append(f"  4w momentum      {m20:+7.2f}%   {_driver_check(direction, agrees)}")
    if m60 is not None:
        agrees = (direction == 'LONG' and m60 > 0) or (direction == 'SHORT' and m60 < 0)
        lines.append(f"  12w momentum     {m60:+7.2f}%   {_driver_check(direction, agrees)}")
    if ma is not None:
        agrees = (direction == 'LONG' and ma) or (direction == 'SHORT' and not ma)
        s = "10d > 40d" if ma else "10d < 40d"
        lines.append(f"  MA trend         {s:>10s}   {_driver_check(direction, agrees)}")
    if ry is not None:
        agrees = (direction == 'LONG' and ry < 0) or (direction == 'SHORT' and ry > 0)
        lines.append(f"  Real yield Δ4w   {ry:+6.1f}bps   {_driver_check(direction, agrees)}")

    # Track record - inline compact when data exists
    if track and track.get("resolved_calls", 0) > 0:
        n = track['resolved_calls']
        wr = track.get('win_rate_pct', 0)
        cum = track.get('cumulative_return_pct', 0)
        lines += [
            RULE,
            f"*Live track record*  (n={n})",
            f"  Win rate: {wr:.0f}%  ·  Cumulative return: {cum:+.2f}%",
        ]
    else:
        lines += [
            RULE,
            "*Live track record*",
            "  _Accumulating - first resolve pending._",
        ]

    lines += [
        RULE,
        f"_Next update: Fri 21:00 UTC (week close outcome)_",
        "_Not financial advice. BETA product - 16yr backtest passes, live still validating._",
        "_Sample: 363 backtested calls, 13/17 years positive. Live n growing every Sunday._",
    ]

    return "\n".join(lines)


def format_weekly_resolve(prior_call: dict, outcome: dict,
                          track: dict | None = None) -> str:
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
        f"🏁 *NORTH - Week Resolved*",
        f"_{week_of}_",
        RULE,
        f"{_direction_badge(direction)}  ·  {result_line}",
        "",
    ]
    if entry:
        lines.append(f"📍 Entry:  `${entry:,.2f}`")
    if exit_price:
        lines.append(f"🏁 Exit:   `${exit_price:,.2f}`  _({reason_pretty})_")
    lines.append(f"📊 Return: *{ret_pct:+.3f}%* per unit position")

    # Refreshed track record after this resolve
    if track and track.get("resolved_calls", 0) > 0:
        n = track['resolved_calls']
        wr = track.get('win_rate_pct', 0)
        cum = track.get('cumulative_return_pct', 0)
        lines += [
            RULE,
            f"*Track record now*  (n={n})",
            f"  Win rate: {wr:.0f}%  ·  Cumulative return: {cum:+.2f}%",
        ]
    return "\n".join(lines)


def format_weekly_performance(track: dict, history: list[dict]) -> str:
    """Cumulative-performance snapshot card. Fires Sunday before the new call.

    Reads from far_weekly_history.json summary block + full history list.
    """
    n = track.get("resolved_calls", 0)
    wr_pct = track.get("win_rate_pct", 0) or 0
    cum = track.get("cumulative_return_pct", 0) or 0

    lines = [
        f"📊 *NORTH - Performance Update*",
        f"_as of {datetime.now(timezone.utc).strftime('%Y-%m-%d')}_",
        RULE,
    ]

    if n == 0:
        lines += [
            "*No resolved calls yet.*",
            "First resolve pending. This card grows richer with every week.",
        ]
        return "\n".join(lines)

    # Aggregate stats from resolved history
    resolved = [c for c in history
                if c.get("outcome", {}).get("result") == "resolved"]
    if not resolved:
        resolved = []
    rets = [c["outcome"]["net_return_pct"] for c in resolved]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]

    best = max(rets) if rets else 0
    worst = min(rets) if rets else 0
    mean_win = (sum(wins) / len(wins)) if wins else 0
    mean_loss = (sum(losses) / len(losses)) if losses else 0
    mean_all = (sum(rets) / len(rets)) if rets else 0

    lines += [
        f"*Cumulative*  (n={n} resolved)",
        f"  Win rate:      {wr_pct:.0f}%",
        f"  Total return:  {cum:+.2f}%",
        f"  Mean per call: {mean_all:+.3f}%",
    ]

    lines += [
        RULE,
        "*Distribution*",
        f"  Best call:     {best:+.2f}%",
        f"  Worst call:    {worst:+.2f}%",
        f"  Avg win:       {mean_win:+.3f}%  ({len(wins)}w)",
        f"  Avg loss:      {mean_loss:+.3f}%  ({len(losses)}l)",
    ]

    # Last 4 outcomes
    last_4 = resolved[-4:] if len(resolved) >= 4 else resolved
    if last_4:
        lines += [RULE, "*Recent calls*"]
        for c in last_4:
            d = c.get("direction", "?")
            wk = c.get("week_of", "?")
            r = c["outcome"]["net_return_pct"]
            mark = "✅" if r > 0 else ("🟥" if r < 0 else "➖")
            lines.append(f"  {wk}  {d:>5s}  {r:+6.2f}%  {mark}")

    lines += [
        RULE,
        "_BETA. Small sample - read with humility._",
        "_Fresh call posts next in this channel._",
    ]
    return "\n".join(lines)


def publish_weekly_call(call: dict, track: dict | None = None,
                        audience: str = "public") -> dict:
    """Send the formatted weekly call to Telegram."""
    from telegram_bot import send
    msg = format_weekly_call(call, track=track)
    return send(msg, audience=audience)


def publish_weekly_resolve(prior_call: dict, outcome: dict,
                            track: dict | None = None,
                            audience: str = "public") -> dict:
    from telegram_bot import send
    msg = format_weekly_resolve(prior_call, outcome, track=track)
    return send(msg, audience=audience)


def publish_weekly_performance(track: dict, history: list[dict],
                                audience: str = "public") -> dict:
    from telegram_bot import send
    msg = format_weekly_performance(track, history)
    return send(msg, audience=audience)
