"""Weekly Knox ship-gate report — publishes to public + research channels.

Scheduled by ops/systemd/knox-weekly-report.timer (Sunday 22:15 UTC, 15 min
after weekly validation). Reads shadow_equity_since_halt.jsonl and computes
per-candidate ship-gate progress via shadow_ship_gate_report.py's analyzer,
then formats two versions:
  - short: one-liner for GOLDTRADER_TG_CHAT_PUBLIC
  - full:  breakdown for GOLDTRADER_TG_CHAT_RESEARCH

Fail-open: never breaks the timer if Telegram is unreachable.
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

from shadow_ship_gate_report import (
    analyze_candidate,
    gate_status,
    load_rows,
    CANDIDATES,
)

HALT_STATE = ROOT / "data/halt_state.json"


def _git_commit_short() -> str:
    """Return `git rev-parse --short HEAD` or 'unknown' on failure."""
    try:
        import subprocess
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                            cwd=str(ROOT), capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _fmt_short(name: str, r: dict, halt_snapshot: str) -> str:
    if r["n"] == 0:
        return (f"📈 Knox week — n=0 shadow decisions with valid candidate signal.\n"
                f"Engine A halt: {halt_snapshot}")
    return (
        f"📈 Knox week — n={r['n']}/{CANDIDATES[name]['n_ship']} shadow, "
        f"precision {100*r['precision_on_losers']:.0f}%, "
        f"lift ${r['pnl_lift_mean_per_trade']:+.0f}/trade, "
        f"CI [${r['pnl_lift_ci95_lo_mean']:+.0f}, ${r['pnl_lift_ci95_hi_mean']:+.0f}]. "
        f"Gate = *{gate_status(name, r)}*.\n"
        f"Engine A halt: {halt_snapshot}"
    )


def _fmt_full(name: str, r: dict, halt_snapshot: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if r["n"] == 0:
        return (f"📊 *Knox weekly ship-gate report — {ts}*\n\n"
                f"No resolved shadow decisions with valid candidate signal yet.\n\n"
                f"Engine A halt: {halt_snapshot}")

    gates = CANDIDATES[name]
    ci_lo = r["pnl_lift_ci95_lo_mean"]
    ci_hi = r["pnl_lift_ci95_hi_mean"]

    def _tick(cond: bool) -> str:
        return "✅" if cond else "❌"

    n_ok = r["n"] >= gates["n_ship"]
    p_ok = r["precision_on_losers"] >= gates["precision_ship"]
    ci_ok = ci_lo > 0
    skip_ok = r["skip_rate"] <= gates["skip_rate_max"]
    hard_stop_ok = ts[:10] < gates["hard_stop_utc"]

    return (
        f"📊 *Knox weekly ship-gate report — {ts}*\n\n"
        f"Shadow decisions:      n = {r['n']} / {gates['n_ship']}\n"
        f"Candidate skip-rate:   {100*r['skip_rate']:.1f}%\n"
        f"Skips: W={r['skips_won']}  L={r['skips_lost']}  "
        f"precision-on-losers = {100*r['precision_on_losers']:.1f}%\n"
        f"P&L (no filter):       ${r['pnl_no_filter']:+,.0f}\n"
        f"P&L (with filter):     ${r['pnl_with_filter']:+,.0f}\n"
        f"P&L lift (total):      ${r['pnl_lift_total']:+,.0f}\n"
        f"P&L lift (mean/trade): ${r['pnl_lift_mean_per_trade']:+,.2f}\n"
        f"Bootstrap 95% CI:      [${ci_lo:+,.2f}, ${ci_hi:+,.2f}]\n\n"
        f"Gate status: *{gate_status(name, r)}*\n"
        f"  {_tick(n_ok)} n ≥ {gates['n_ship']}\n"
        f"  {_tick(p_ok)} precision ≥ {100*gates['precision_ship']:.0f}%\n"
        f"  {_tick(ci_ok)} CI clears zero\n"
        f"  {_tick(skip_ok)} skip-rate ≤ {100*gates['skip_rate_max']:.0f}%\n"
        f"  {_tick(hard_stop_ok)} before hard-stop {gates['hard_stop_utc']}\n\n"
        f"Engine A halt: {halt_snapshot}\n"
        f"Report commit: `{_git_commit_short()}`"
    )


def _halt_snapshot() -> str:
    if not HALT_STATE.exists():
        return "unknown (halt_state.json missing)"
    try:
        h = json.loads(HALT_STATE.read_text())
    except Exception:
        return "unknown (halt_state.json unreadable)"
    verdict = h.get("verdict", "?")
    n = h.get("n_trades_since_launch", "?")
    dd = h.get("realized_max_dd", 0)
    lr = h.get("sprt", {}).get("log_lr", 0)
    return f"verdict={verdict}, n={n}, DD=${dd:,.0f}, SPRT log-LR={lr:+.2f}"


def _send_or_log(text: str, audience: str) -> None:
    # Dry-run override: KNOX_REPORT_DRY_RUN=1 prints instead of sending.
    # Useful for local smoke tests without spamming your Telegram.
    if os.environ.get("KNOX_REPORT_DRY_RUN") == "1":
        # Windows console (cp1252) can't render emoji — write bytes with replace
        line = f"[knox_weekly_report] DRY_RUN audience={audience}:\n{text}\n"
        try:
            sys.stdout.write(line + "\n")
        except UnicodeEncodeError:
            sys.stdout.buffer.write(line.encode("utf-8", errors="replace"))
            sys.stdout.write("\n")
        return
    try:
        from telegram_bot import send as _tg_send
    except Exception:
        print(f"[knox_weekly_report] telegram_bot import failed; "
              f"would have sent to {audience}:\n{text}")
        return
    try:
        r = _tg_send(text, audience=audience)
        ok = r.get("ok") if isinstance(r, dict) else False
        print(f"[knox_weekly_report] audience={audience} ok={ok}")
    except Exception as e:
        print(f"[knox_weekly_report] send failed for {audience}: {e}")


def _maybe_auto_activate_sprt() -> str:
    """If Knox has n>=50 engine_b_takes rows with outcomes AND SPRT state
    file doesn't yet exist, auto-run knox_sprt_activate.py per pre-reg.
    Returns a short status line for inclusion in the weekly report.
    """
    state_file = ROOT / "data/knox_sprt_state.json"
    if state_file.exists():
        return "SPRT: activated"

    # Count engine_b_takes with resolved outcomes
    rows = load_rows()
    n = sum(
        1 for r in rows
        if r.get("engine_b_takes") and r.get("outcome", {}).get("net_pnl") is not None
    )
    if n < 50:
        return f"SPRT: dormant (n={n}/50)"

    # Trigger activation
    import subprocess
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "knox_sprt_activate.py"),
             "--reason", f"auto-triggered by weekly report at n={n}"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return f"SPRT: 🎯 AUTO-ACTIVATED at n={n} — see data/knox_sprt_state.json"
        return f"SPRT: activation attempted but failed (rc={r.returncode}) — {r.stderr[:100]}"
    except Exception as e:
        return f"SPRT: activation error: {type(e).__name__}: {e}"


def main() -> None:
    rows = load_rows()
    halt_snap = _halt_snapshot()
    sprt_line = _maybe_auto_activate_sprt()
    for name in CANDIDATES:
        r = analyze_candidate(rows, name)
        short = _fmt_short(name, r, halt_snap) + f"\n{sprt_line}"
        full = _fmt_full(name, r, halt_snap) + f"\n\n{sprt_line}"
        _send_or_log(short, audience="public")
        _send_or_log(full, audience="research")


if __name__ == "__main__":
    main()
