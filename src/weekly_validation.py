"""Weekly auto-revalidation: runs Phase 7 gates and posts result to private.

Fires once per UTC week. State stored in dispatch_state.json under
key `weekly_validation|YYYY-Wxx`. Called from dispatch.py.

Default schedule: Sunday between 22:00 and 23:00 UTC (after Friday's
close has been digested, before Sunday open).

The post is intentionally compact — a launch sanity-check the owner
can glance at to confirm v7 is still in the green.
"""
from __future__ import annotations
from pathlib import Path
import json
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "dispatch_state.json"
SCRIPT = ROOT / "scripts" / "validate_v7_phase7.py"

WEEKLY_HOUR_UTC = 22
WEEKLY_WEEKDAY = 6  # Sunday (Mon=0)


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"sent": []}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def _run_validation() -> str:
    """Run the validation script and return stdout (verdict block included)."""
    try:
        env_extra = {"PYTHONIOENCODING": "utf-8"}
        import os
        env = {**os.environ, **env_extra}
        r = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, env=env, timeout=180,
            encoding="utf-8", errors="replace",
        )
        return r.stdout if r.stdout else f"(validation failed exit={r.returncode}): {r.stderr[:500]}"
    except Exception as e:
        return f"(validation runner failed: {type(e).__name__}: {e})"


def _extract_verdict(output: str) -> str:
    """Pull just the verdict block from the validation output for a compact alert."""
    lines = output.splitlines()
    # find "VERDICT" header line
    try:
        i = next(idx for idx, ln in enumerate(lines) if "VERDICT" in ln)
        verdict_lines = lines[i:i+10]
        return "\n".join(verdict_lines)
    except StopIteration:
        return output[-800:]  # fallback: tail


def maybe_publish_weekly_validation() -> bool:
    """Run + publish once per ISO week. Returns True if sent."""
    from telegram_bot import send
    now = pd.Timestamp.now(tz="UTC")
    if now.weekday() != WEEKLY_WEEKDAY or now.hour != WEEKLY_HOUR_UTC:
        return False
    iso = now.isocalendar()
    key = f"weekly_validation|{iso.year}-W{iso.week:02d}"
    state = _load_state()
    if key in state.get("sent", []):
        return False
    output = _run_validation()
    verdict = _extract_verdict(output)
    msg = (f"🔎 *Weekly v7 validation — {now.strftime('%Y-%m-%d')} UTC*\n\n"
           f"```\n{verdict}\n```")
    send(msg, audience="private")
    state.setdefault("sent", []).append(key)
    _save_state(state)
    return True


if __name__ == "__main__":
    if "--dry" in sys.argv:
        out = _run_validation()
        print(_extract_verdict(out))
    else:
        sent = maybe_publish_weekly_validation()
        print(f"weekly_validation sent={sent} at {pd.Timestamp.now(tz='UTC').isoformat(timespec='minutes')}")
