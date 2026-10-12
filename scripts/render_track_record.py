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

    # SPRT state (mechanical halt check)
    if n_resolved > 0:
        losses = n_resolved - wins
        log_lr = losses * 0.3879 + wins * (-0.4682)
        halt_boundary = 2.773
        safe_boundary = -1.558
        if log_lr >= halt_boundary:
            sprt_verdict = "HALT fired. v1 is retired per pre-reg."
        elif log_lr <= safe_boundary:
            sprt_verdict = "SAFE. Baseline accepted."
        else:
            # how many more consecutive losses to halt
            needed = 0
            lr = log_lr
            while lr < halt_boundary and needed < 50:
                lr += 0.3879
                needed += 1
            sprt_verdict = (f"CONTINUE. Log-LR {log_lr:+.3f}, halt boundary +{halt_boundary}. "
                            f"Needs {needed} more consecutive losses to halt.")
        lines.append("## Mechanical halt check (SPRT)")
        lines.append("")
        lines.append(f"- **Verdict:** {sprt_verdict}")
        lines.append("- **Rule:** pre-registered sequential test on win rate. Halt fires automatically "
                     "if evidence crosses the pre-set boundary. No subjective call. Published alongside "
                     "every weekly dispatch so you can audit it.")
        lines.append("")

    lines.append("## What we are doing about it")
    lines.append("")
    lines.append("Current research pipeline (public, same discipline as the shipped product):")
    lines.append("")
    lines.append("- **v2 shadow** (DXY-filtered v1): tracking since 2026-07-22. Forward window closes "
                 "2027-01-22. If v2 forward beats v1 forward on Sharpe and mean weekly return, v2 "
                 "becomes the ship candidate.")
    lines.append("- **v3-m20 pre-reg** (`far_weekly_gold_read_v3_m20`, drafted 2026-10-12): v2 plus "
                 "a filter that would skip LONG signals in the historically bad "
                 "high-momentum-exhaustion bucket (M20 above 7%). Four converging analyses identified "
                 "this zone as v1's structural weak point; the one resolved live LONG loss sat in it. "
                 "Pre-reg is drafted but blocked by a cooling-off requirement before the backtest can "
                 "run. See `docs/experiments/2026-10-12_far_weekly_v3_m20_extremity_prereg.md`.")
    lines.append("- **No live rule change** while pre-reg windows are open. v1 continues to run as "
                 "published. If and when v2 or v3-m20 earns promotion, the transition is documented "
                 "with full before/after track records.")
    lines.append("")
    lines.append("What we are NOT doing: panic-shipping an unvalidated filter, retiring the engine "
                 "on a two-trade sample, adding instruments or signals mid-drawdown. Every one of "
                 "those is a documented failure mode in `docs/development_story.md`.")
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
