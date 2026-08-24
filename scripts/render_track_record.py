"""Render NORTH's live track record as a compact Telegram-ready block.

Reads `data/far_weekly_calls.jsonl` and produces the "current call +
last N resolves" summary that goes into the public pinned message and
the weekly card footer.

Usage:
    python scripts/render_track_record.py           # writes docs/launch/track_record_current.md
    python scripts/render_track_record.py --stdout  # prints only
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CALLS = ROOT / "data" / "far_weekly_calls.jsonl"
OUT = ROOT / "docs" / "launch" / "track_record_current.md"


def load_calls() -> list[dict]:
    if not CALLS.exists():
        return []
    return [json.loads(l) for l in CALLS.read_text().splitlines() if l.strip()]


def render(rows: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not rows:
        return f"# NORTH track record\n\n*Generated {now}*\n\nNo calls on record yet.\n"

    latest = rows[-1]
    direction = latest.get("direction", "?")
    week_of = latest.get("week_of", "?")
    week_end = latest.get("week_end", "?")

    resolved = [r for r in rows if r.get("outcome", {}).get("result") in ("resolved", "stop", "friday_close")]
    resolved_pnl = [r for r in rows if r.get("outcome", {}).get("net_return_pct") is not None]
    flat_count = sum(1 for r in rows if r.get("direction") == "FLAT")

    lines = []
    lines.append("# NORTH - live track record")
    lines.append("")
    lines.append(f"*Auto-generated from `data/far_weekly_calls.jsonl` on {now}*")
    lines.append("")
    lines.append("## Current call")
    lines.append("")
    lines.append(f"- **Week:** {week_of} to {week_end}")
    lines.append(f"- **Direction:** {direction}")
    if direction != "FLAT":
        lines.append(f"- **Entry approx:** ${latest.get('entry_approx', '?')}")
        lines.append(f"- **Stop:** ${latest.get('stop_price', '?')}")
        lines.append(f"- **Reference price at publish:** ${latest.get('current_price', '?')}")
    else:
        lines.append(f"- **Reference price at publish:** ${latest.get('current_price', '?')}")
        lines.append(f"- **Note:** No trade this week. Signal did not clear all four conditions. "
                     f"Sitting out is the correct action, not a missed opportunity.")
    lines.append("")

    lines.append("## Cumulative record")
    lines.append("")
    total = len(rows)
    directional = sum(1 for r in rows if r.get("direction") in ("LONG", "SHORT"))
    n_resolved = sum(1 for r in rows if r.get("outcome", {}).get("net_return_pct") is not None
                     and r.get("direction") in ("LONG", "SHORT"))
    pnls = [r["outcome"]["net_return_pct"] for r in rows
            if r.get("outcome", {}).get("net_return_pct") is not None
            and r.get("direction") in ("LONG", "SHORT")]
    wins = sum(1 for p in pnls if p > 0)
    cum = sum(pnls)
    lines.append(f"- **Weeks published:** {total}")
    lines.append(f"- **Directional calls (LONG/SHORT):** {directional}")
    lines.append(f"- **FLAT weeks:** {flat_count}")
    lines.append(f"- **Directional calls resolved:** {n_resolved}")
    if n_resolved > 0:
        lines.append(f"- **Wins:** {wins}/{n_resolved} ({100*wins/n_resolved:.0f}% hit rate)")
        lines.append(f"- **Cumulative return (net of costs):** {cum:+.2f}%")
    else:
        lines.append(f"- **Wins:** none resolved yet")
    lines.append("")

    if n_resolved > 0:
        lines.append("## Recent resolves")
        lines.append("")
        lines.append("| Week | Direction | Entry | Exit | Reason | Net % |")
        lines.append("|---|---|---|---|---|---|")
        recent = [r for r in rows if r.get("outcome", {}).get("net_return_pct") is not None
                  and r.get("direction") in ("LONG", "SHORT")][-8:]
        for r in recent:
            o = r["outcome"]
            week = r.get("week_of", "?")
            d = r.get("direction", "?")
            entry = r.get("entry_approx", "?")
            exit_p = o.get("exit_price", "?")
            reason = o.get("exit_reason", "?")
            net = o.get("net_return_pct", 0)
            lines.append(f"| {week} | {d} | ${entry} | ${exit_p} | {reason} | {net:+.2f}% |")
        lines.append("")

    lines.append("## Honesty statement")
    lines.append("")
    lines.append("This is a small sample. NORTH v1 has been live since 2026-07-22. Any conclusion "
                 "drawn from fewer than ~25 resolved directional trades is noise. The 16-year "
                 "historical backtest is our best current estimate of expected behavior, and it "
                 "showed 55.9% win rate on directional weeks with +0.23% mean return per trade "
                 "after costs. Live results should converge toward that over quarters and years, "
                 "not weeks.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true", help="print to stdout, do not write file")
    args = ap.parse_args()

    rows = load_calls()
    text = render(rows)

    if args.stdout:
        print(text)
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text)
        print(f"Wrote {OUT} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
