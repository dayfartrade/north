"""Generate the public-facing retirement wall from the experiments registry.

Output: docs/launch/retirement_wall.md - every rejected/retired experiment
in one honest list, ready to link from the Telegram intro pin.

The purpose is transparency. NORTH promises to show every failure, not just
wins. This script produces the receipts.

Usage:
    python scripts/build_retirement_wall.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "experiments" / "registry.json"
OUT = ROOT / "docs" / "launch" / "retirement_wall.md"

# Verdict categorization
REJECTED_PREFIXES = ("rejected", "retired", "killed", "halted")
SHIPPED_PREFIXES = ("shipped", "live")


def classify(verdict: str) -> str:
    v = (verdict or "").lower()
    for p in REJECTED_PREFIXES:
        if v.startswith(p):
            return "rejected"
    for p in SHIPPED_PREFIXES:
        if v.startswith(p):
            return "shipped"
    return "other"


def first_line(notes: str, max_len: int = 220) -> str:
    if not notes:
        return "(no notes)"
    first = notes.split(".")[0].strip()
    if len(first) > max_len:
        first = first[:max_len - 3].rstrip() + "..."
    return first


def render() -> str:
    d = json.loads(REGISTRY.read_text())
    trials = d["trials"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rejected = [t for t in trials if classify(t.get("verdict", "")) == "rejected"]
    shipped = [t for t in trials if classify(t.get("verdict", "")) == "shipped"]

    # Sort rejected: newest first by resolved_utc (fallback registered_utc)
    def sort_key(t):
        return t.get("resolved_utc") or t.get("registered_utc") or ""
    rejected.sort(key=sort_key, reverse=True)

    lines = []
    lines.append("# NORTH - the retirement wall")
    lines.append("")
    lines.append(f"*Auto-generated from `data/experiments/registry.json` on {now}. "
                 f"{len(rejected)} rejected trials on record.*")
    lines.append("")
    lines.append("Why this exists: NORTH publishes signals. Signals fail. We show every "
                 "failure here so subscribers can judge the discipline honestly. If it isn't "
                 "on this list, we haven't tested it. If it is, here's what happened and why "
                 "we killed it.")
    lines.append("")
    lines.append(f"- **Trials ever run:** {len(trials)}")
    lines.append(f"- **Rejected / retired:** {len(rejected)}")
    lines.append(f"- **Currently live:** NORTH v1 weekly gold read "
                 f"({len(shipped)} historical shipping entries in registry, most are "
                 f"pre-NORTH engines that have since been retired)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Rejected trials, newest first")
    lines.append("")

    for t in rejected:
        tid = t.get("id", "(no id)")
        verdict = t.get("verdict", "?")
        resolved = t.get("resolved_utc", "?")
        n = t.get("n_observations")
        sr = t.get("sr_per_period")
        summary = first_line(t.get("notes", ""))
        lines.append(f"### `{tid}`")
        lines.append("")
        lines.append(f"- **Verdict:** {verdict}")
        lines.append(f"- **Resolved:** {resolved}")
        if n is not None:
            lines.append(f"- **Observations:** {n}")
        if sr is not None:
            lines.append(f"- **SR per period:** {sr}")
        lines.append(f"- **Why:** {summary}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## What is currently live")
    lines.append("")
    lines.append("**NORTH v1** - weekly gold direction call. Published every Sunday 22:00 UTC "
                 "on the public Telegram channel. Signal is a 4-condition momentum + macro "
                 "filter (M20, M60, MA10 vs MA40, 20-day change in US 10y real yield). The "
                 "call publishes for the following Monday-Friday window with a defined entry, "
                 "stop, and time-based exit. If any condition disagrees, the call is FLAT and "
                 "no trade is taken that week.")
    lines.append("")
    lines.append("Everything else in this repo is either a retired engine, a shadow-log "
                 "candidate accruing forward evidence, or an internal research artifact.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = render()
    OUT.write_text(text)
    print(f"Wrote {OUT} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
