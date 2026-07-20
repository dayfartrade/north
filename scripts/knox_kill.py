"""Knox kill switch — flip data/knox_state.json to disable/enable soft-launch
alerts without restart. Read every tick by shadow_orb_tracker.

Usage:
    python scripts/knox_kill.py off      # disable (defense-in-depth on top of env)
    python scripts/knox_kill.py on       # re-enable
    python scripts/knox_kill.py status   # print current state

Design:
  - State file: data/knox_state.json = {"enabled": bool, "changed_utc": ts, "reason": str}
  - Missing file = enabled (fail-open to the env-var gate — env still ultimately controls)
  - shadow_orb_tracker checks BOTH:
      env KNOX_RESEARCH_ENABLED=1  AND  knox_state.enabled != False
  - Either says off -> Knox alerts suppressed
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data/knox_state.json"


def _load() -> dict:
    if not STATE_FILE.exists():
        return {"enabled": True, "changed_utc": None, "reason": "default (file missing)"}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"enabled": True, "changed_utc": None, "reason": "default (file unreadable)"}


def _write_atomic(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE_FILE)


def _set(enabled: bool, reason: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    state = {"enabled": enabled, "changed_utc": now, "reason": reason or ""}
    _write_atomic(state)
    print(f"Knox: {'ENABLED' if enabled else 'DISABLED'}  ({now})")
    if reason:
        print(f"  reason: {reason}")


def _status() -> int:
    s = _load()
    en = s.get("enabled", True)
    print(f"Knox: {'ENABLED' if en else 'DISABLED'}")
    print(f"  changed_utc: {s.get('changed_utc') or 'never (default)'}")
    print(f"  reason:      {s.get('reason') or '-'}")
    print(f"  env KNOX_RESEARCH_ENABLED: {os.environ.get('KNOX_RESEARCH_ENABLED', '<unset>')}")
    return 0 if en else 1


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("on", "off", "status"):
        print("usage: knox_kill.py {on|off|status} [reason...]", file=sys.stderr)
        return 2
    cmd = argv[1]
    reason = " ".join(argv[2:]) if len(argv) > 2 else ""
    if cmd == "on":
        _set(True, reason)
    elif cmd == "off":
        _set(False, reason)
    else:
        return _status()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
