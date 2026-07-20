"""Knox post-mortem — publishes outcome follow-up for each dispatched Knox alert.

For each shadow_equity_since_halt.jsonl row where:
  - engine_b_takes=True   (Knox actually alerted this decision live)
  - research_alert_sent=True (or inferred from engine_b_takes if not tracked)
  - outcome is present (resolved by shadow_outcome_resolver.py)
  - research_post_mortem_sent NOT True (idempotency)

...post a follow-up to GOLDTRADER_TG_CHAT_RESEARCH showing what happened,
then mark the row post_mortem_sent=True.

Gated by KNOX_RESEARCH_ENABLED=1 AND knox_state.enabled (same two-key kill
as the entry alerts — if Knox is killed, we don't spam post-mortems either).

Run frequency: every 30 min via systemd timer (aligned with dispatch cadence).
Fail-open: never breaks resolver or dispatcher.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

SHADOW_LOG = ROOT / "data/shadow_equity_since_halt.jsonl"


def _load_rows() -> list[dict]:
    if not SHADOW_LOG.exists():
        return []
    out: list[dict] = []
    with open(SHADOW_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _write_atomic(rows: list[dict]) -> None:
    tmp = SHADOW_LOG.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    os.replace(tmp, SHADOW_LOG)


def _knox_alerts_enabled() -> bool:
    """Two-key kill: env AND state file. Matches shadow_orb_tracker gate."""
    if os.environ.get("KNOX_RESEARCH_ENABLED") != "1":
        return False
    state_file = ROOT / "data/knox_state.json"
    if not state_file.exists():
        return True
    try:
        state = json.loads(state_file.read_text())
        return bool(state.get("enabled", True))
    except Exception:
        return True


def _running_gate_stats() -> str:
    """One-line cumulative ship-gate summary for the follow-up alert footer."""
    try:
        from shadow_ship_gate_report import (
            analyze_candidate, gate_status, load_rows as _load_gate_rows, CANDIDATES,
        )
        rows = _load_gate_rows()
        r = analyze_candidate(rows, "daily_slope_consistency")
        if r["n"] == 0:
            return "gate: n=0"
        n_ship = CANDIDATES["daily_slope_consistency"]["n_ship"]
        return (f"gate: n={r['n']}/{n_ship}, precision {100*r['precision_on_losers']:.0f}%, "
                f"CI [${r['pnl_lift_ci95_lo_mean']:+.0f},${r['pnl_lift_ci95_hi_mean']:+.0f}], "
                f"{gate_status('daily_slope_consistency', r)}")
    except Exception:
        return "gate: unknown"


def _outcome_emoji(kind: str, net_pnl: float) -> str:
    if net_pnl > 0:
        return "🟢"
    if net_pnl < 0:
        return "🔴"
    return "⚪"


def _fmt_post_mortem(row: dict, gate_stats: str) -> str:
    o = row["outcome"]
    kind = o.get("kind", "?")
    net = float(o.get("net_pnl") or 0)
    exit_price = o.get("exit_price")
    session = row.get("session", "?")
    direction = row.get("direction_bias", "?")
    or_open = row.get("or_open_utc", "?")[:16].replace("T", " ")
    resolved = o.get("resolved_utc", "?")[:16].replace("T", " ")

    if direction == "LONG":
        entry = row.get("entry_long")
    elif direction == "SHORT":
        entry = row.get("entry_short")
    else:
        entry = None

    exit_line = (f"Exit: `{exit_price:.2f}` ({kind})" if exit_price is not None
                 else f"Exit: {kind}")
    entry_line = f"Entry: `{entry:.2f}` -> " if entry is not None else ""

    emoji = _outcome_emoji(kind, net)
    return (
        f"🧪 *KNOX RESEARCH — Alert resolved*\n"
        f"{emoji} {session} {direction} @ {or_open}Z\n"
        f"{entry_line}{exit_line}\n"
        f"P&L: `${net:+,.2f}` (1 contract, RT cost $24)\n"
        f"Resolved: {resolved}Z\n\n"
        f"_Cumulative Knox {gate_stats}_"
    )


def _try_send(text: str) -> bool:
    if os.environ.get("KNOX_POSTMORTEM_DRY_RUN") == "1":
        try:
            sys.stdout.write(f"[knox_post_mortem] DRY_RUN:\n{text}\n\n")
        except UnicodeEncodeError:
            sys.stdout.buffer.write(f"[knox_post_mortem] DRY_RUN:\n{text}\n\n"
                                     .encode("utf-8", errors="replace"))
        return True
    try:
        from telegram_bot import send as _tg_send
    except Exception:
        return False
    try:
        r = _tg_send(text, audience="research")
        return bool(r.get("ok")) if isinstance(r, dict) else False
    except Exception:
        return False


def main() -> int:
    if not _knox_alerts_enabled():
        print("[knox_post_mortem] Knox disabled (env or state); skipping.")
        return 0

    rows = _load_rows()
    if not rows:
        print("[knox_post_mortem] no shadow rows")
        return 0

    gate_stats = _running_gate_stats()
    changed = False
    posted = 0
    skipped_no_engine_b = 0
    skipped_no_outcome = 0
    skipped_already_sent = 0
    failed = 0

    for row in rows:
        if not row.get("engine_b_takes"):
            skipped_no_engine_b += 1
            continue
        if not row.get("outcome"):
            skipped_no_outcome += 1
            continue
        if row.get("research_post_mortem_sent"):
            skipped_already_sent += 1
            continue

        text = _fmt_post_mortem(row, gate_stats)
        ok = _try_send(text)
        if ok:
            row["research_post_mortem_sent"] = True
            row["research_post_mortem_utc"] = datetime.now(timezone.utc).isoformat()
            posted += 1
            changed = True
        else:
            failed += 1

    if changed:
        _write_atomic(rows)

    print(f"[knox_post_mortem] posted={posted}, failed={failed}, "
          f"skipped(no_engine_b={skipped_no_engine_b}, no_outcome={skipped_no_outcome}, "
          f"already={skipped_already_sent})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
