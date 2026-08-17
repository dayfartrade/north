"""Render Stage 1 Message 2 (warm-up welcome) with current data.

Message 1 of the launch sequence is the intro pin (static text from
docs/launch/north_public_intro.md). Message 2 is the current-state
snapshot that changes every week. This script generates it dynamically.

The intent: on launch day (Sunday 2026-08-24), Farhad runs this to
get the current text, copies it, pastes to the public Telegram
channel after posting Message 1.

Regenerates from:
  - data/far_weekly_calls.jsonl  (calls, track record, latest FLAT streak)
  - Current UTC date for the "next publish" line

Usage:
    python scripts/render_warmup_message.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CALLS = ROOT / "data" / "far_weekly_calls.jsonl"


def load_calls() -> list[dict]:
    if not CALLS.exists():
        return []
    return [json.loads(l) for l in CALLS.read_text().splitlines() if l.strip()]


def next_sunday_utc(now: datetime) -> datetime:
    """Return the next Sunday 22:00 UTC after `now`."""
    days_ahead = (6 - now.weekday()) % 7
    if days_ahead == 0 and now.hour >= 22:
        days_ahead = 7
    return (now + timedelta(days=days_ahead)).replace(hour=22, minute=0, second=0, microsecond=0)


def render() -> str:
    now = datetime.now(timezone.utc)
    rows = load_calls()

    # Latest call
    if not rows:
        return "This channel is now live. No calls yet. First publish Sunday 22:00 UTC."

    latest = rows[-1]
    latest_week = latest.get("week_of", "?")
    latest_end = latest.get("week_end", "?")
    latest_dir = latest.get("direction", "?")

    # FLAT streak (consecutive most-recent FLAT calls)
    flat_streak = 0
    for row in reversed(rows):
        if row.get("direction") == "FLAT":
            flat_streak += 1
        else:
            break

    # Directional calls resolved
    resolved = [
        r for r in rows
        if r.get("outcome", {}).get("net_return_pct") is not None
        and r.get("direction") in ("LONG", "SHORT")
    ]
    directional_count = sum(1 for r in rows if r.get("direction") in ("LONG", "SHORT"))
    resolved_lines = []
    for r in resolved:
        w = r.get("week_of", "?")
        d = r.get("direction", "?")
        pct = r["outcome"]["net_return_pct"]
        reason = r["outcome"].get("exit_reason", "?")
        resolved_lines.append(f"  {w} {d} -> {pct:+.2f}% ({reason})")

    if resolved:
        pnls = [r["outcome"]["net_return_pct"] for r in resolved]
        cum = sum(pnls)
        cum_line = f"Cumulative net: {cum:+.2f}%"
    else:
        cum_line = "Cumulative net: pending (no resolved directional call yet)"

    next_pub = next_sunday_utc(now)
    next_pub_str = next_pub.strftime("%Y-%m-%d %H:%M UTC")

    parts = []
    parts.append("This channel is now live for a small invite list. Welcome.")
    parts.append("")
    parts.append("Here is where we are:")
    parts.append("")

    if flat_streak >= 2:
        parts.append(f"- Last {flat_streak} weeks were FLAT (latest: {latest_week}). That is the signal doing exactly what it is supposed to do when the four conditions disagree. Not a bug, not a miss.")
    elif latest_dir == "FLAT":
        parts.append(f"- Latest week ({latest_week}) is FLAT. Sitting out is the correct action, not a miss.")
    else:
        parts.append(f"- Latest week ({latest_week}) is {latest_dir}. Details in the automated post above.")

    parts.append(f"- Directional calls to date: {directional_count}. Resolved so far: {len(resolved)}.")
    if resolved_lines:
        parts.append("")
        parts.append("Resolved directional calls:")
        parts.extend(resolved_lines)
    parts.append(f"- {cum_line}")
    parts.append("")
    parts.append("What happens next:")
    parts.append("")
    parts.append(f"- Next publish: {next_pub_str} (one call for the following Mon-Fri).")
    parts.append("- Every Sunday 22:00 UTC: one call, three possible shapes (LONG, SHORT, or FLAT).")
    parts.append("- Mid-week updates (Mon-Fri 12:00 UTC) only when a directional call is open.")
    parts.append("")
    parts.append("If you were invited by Farhad and want to give feedback: DM him. Honest bad news is welcome.")
    parts.append("")
    parts.append("Repo: github.com/dayfartrade/north")
    parts.append("Track record: github.com/dayfartrade/north/blob/main/docs/launch/track_record_current.md")
    parts.append("Retirement wall: github.com/dayfartrade/north/blob/main/docs/launch/retirement_wall.md")
    return "\n".join(parts)


def main() -> None:
    print(render())


if __name__ == "__main__":
    main()
