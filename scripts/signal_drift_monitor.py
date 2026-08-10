"""NORTH signal drift monitor.

Checks whether the live v1 track record is diverging from the backtest
expectation in ways that warrant operator attention (or an actual halt).

Trip wires (each is INDEPENDENT — any trip fires an alert):
  1. Loss streak: 3 consecutive resolved losses
  2. Weak rolling: last 8 resolved calls sum to a return < -3%
  3. Silent stops: 2 stops in the last 4 resolved calls (backtest baseline
     was 15% stop rate; 50% would be a regime signal)
  4. Live vs backtest divergence: live mean-per-call is > 1.5 standard
     errors below the backtest mean (0.10% per call at 0.77 ann Sharpe)

Sends a private-chat alert whenever ANY tripwire trips. Does NOT
touch the kill switch — that's an operator decision. Just information.

Meant to run once per week, ideally right after the Sunday resolve.

Usage:
    python scripts/signal_drift_monitor.py                (send alerts)
    python scripts/signal_drift_monitor.py --dry-run      (print only)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"

# Baseline from far_weekly_gold_read_v1 (extended 2010-2026 sample)
BACKTEST_MEAN_PCT = 0.10   # rough per-call mean return %
BACKTEST_STD_PCT = 1.0     # rough per-call std %


def load_resolved() -> list[dict]:
    if not CALLS_LOG.exists():
        return []
    rows = [json.loads(l) for l in open(CALLS_LOG) if l.strip()]
    return [r for r in rows
            if r.get("type") == "call"
            and r.get("outcome", {}).get("result") == "resolved"]


def check_loss_streak(resolved: list[dict]) -> tuple[bool, str]:
    if len(resolved) < 3:
        return False, ""
    last3 = resolved[-3:]
    if all(c["outcome"]["net_return_pct"] < 0 for c in last3):
        weeks = ", ".join(c.get("week_of","?") for c in last3)
        return True, f"3 consecutive losses ({weeks})"
    return False, ""


def check_weak_rolling(resolved: list[dict]) -> tuple[bool, str]:
    if len(resolved) < 8:
        return False, ""
    last8 = resolved[-8:]
    total = sum(c["outcome"]["net_return_pct"] for c in last8)
    if total < -3.0:
        return True, f"Last 8 resolved calls sum to {total:+.2f}% (< -3.0% floor)"
    return False, ""


def check_silent_stops(resolved: list[dict]) -> tuple[bool, str]:
    if len(resolved) < 4:
        return False, ""
    last4 = resolved[-4:]
    stops = sum(1 for c in last4 if c["outcome"].get("exit_reason") == "stop")
    if stops >= 2:
        return True, (f"{stops}/4 recent calls hit stops "
                      "(backtest baseline: 15% stop rate)")
    return False, ""


def check_backtest_divergence(resolved: list[dict]) -> tuple[bool, str]:
    n = len(resolved)
    if n < 12:
        return False, ""
    rets = [c["outcome"]["net_return_pct"] for c in resolved]
    mean = sum(rets) / n
    se = BACKTEST_STD_PCT / math.sqrt(n)
    z = (mean - BACKTEST_MEAN_PCT) / se
    if z < -1.5:
        return True, (f"Live mean {mean:+.3f}% at n={n} is "
                      f"{-z:.2f} SE below backtest baseline {BACKTEST_MEAN_PCT:+.2f}%")
    return False, ""


def format_alert(trips: list[tuple[str, str]], n_resolved: int) -> str:
    lines = [
        "🚨 NORTH DRIFT ALERT — private",
        f"as of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"resolved sample: n={n_resolved}",
        "---",
    ]
    for tag, msg in trips:
        lines.append(f"• {tag}: {msg}")
    lines += [
        "---",
        "This is INFORMATION, not an automatic halt.",
        "To halt manually: touch data/far\\_weekly\\_paused",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    resolved = load_resolved()
    n = len(resolved)
    print(f"[drift monitor] resolved sample: n={n}")

    checks = [
        ("Loss streak", check_loss_streak),
        ("Weak rolling", check_weak_rolling),
        ("Silent stops", check_silent_stops),
        ("Backtest divergence", check_backtest_divergence),
    ]
    trips = []
    for tag, fn in checks:
        tripped, msg = fn(resolved)
        status = "TRIPPED" if tripped else "ok"
        print(f"  {tag}: {status}{'  --  ' + msg if msg else ''}")
        if tripped:
            trips.append((tag, msg))

    if not trips:
        print("[drift monitor] no tripwires — no alert.")
        return

    msg = format_alert(trips, n)
    print("\n" + msg)
    if args.dry_run:
        print("\n[dry-run] alert would have been sent")
        return
    from telegram_bot import send
    r = send(msg, audience="private")
    print(f"\n[telegram] {r.get('ok')}")


if __name__ == "__main__":
    main()
