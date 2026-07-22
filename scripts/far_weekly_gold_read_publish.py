"""FAR Weekly Gold Read — live publisher.

Runs weekly (Sunday 22:00 UTC via systemd timer on VPS). Computes signal
for the upcoming week (Monday open -> Friday close) and publishes to:

  1. data/far_weekly_calls.jsonl — machine-readable append-only log
  2. site/data/far_weekly_current.json — current call (website consumes)
  3. site/data/far_weekly_history.json — full history (website consumes)

Also resolves LAST week's call (adds outcome to history + updates track record).

Pre-reg: docs/experiments/2026-07-22_far_weekly_gold_read_prereg.md
Product: BETA. Live tracking replaces failed statistical gates.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Reuse backtest engine components
import importlib.util
spec = importlib.util.spec_from_file_location("far_backtest",
                                                str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far_backtest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far_backtest)

CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"
SITE_CURRENT = ROOT / "site" / "data" / "far_weekly_current.json"
SITE_HISTORY = ROOT / "site" / "data" / "far_weekly_history.json"


def load_call_history() -> list[dict]:
    if not CALLS_LOG.exists():
        return []
    with open(CALLS_LOG) as f:
        return [json.loads(l) for l in f if l.strip()]


def append_call(call: dict) -> None:
    CALLS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CALLS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(call, default=str) + "\n")


def compute_current_signal(today: pd.Timestamp) -> dict:
    """Compute signal for next Monday's entry based on data available now."""
    # Backtest window: last 6 months of data ending today
    start = today - pd.Timedelta(days=180)
    daily = far_backtest.load_daily_bars(start, today)
    ry = far_backtest.load_macro_series(far_backtest.RY, "real_yield_10y")
    df = far_backtest.build_signals(daily, ry)

    # Latest complete day (signal date)
    if len(df) < 60:
        return {"status": "INSUFFICIENT_DATA", "n_bars": len(df)}

    latest = df.iloc[-1]
    signal_date = df.index[-1]

    # Determine next Monday
    days_until_monday = (7 - signal_date.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = signal_date + pd.Timedelta(days=days_until_monday)
    next_friday = next_monday + pd.Timedelta(days=4)

    direction = str(latest["direction"])

    call = {
        "type": "call",
        "signal_date_utc": signal_date.isoformat(),
        "week_of": next_monday.strftime("%Y-%m-%d"),
        "week_end": next_friday.strftime("%Y-%m-%d"),
        "direction": direction,
        "instrument": "GC (Gold Futures) or GLD ETF",
        "signal_components": {
            "M20_pct": round(float(latest["M20"]) * 100, 3) if pd.notna(latest["M20"]) else None,
            "M60_pct": round(float(latest["M60"]) * 100, 3) if pd.notna(latest["M60"]) else None,
            "MA10_above_MA40": bool(latest["MA10"] > latest["MA40"]) if pd.notna(latest["MA10"]) else None,
            "RY_chg_20d_bps": round(float(latest["RY_chg"]) * 100, 1) if pd.notna(latest["RY_chg"]) else None,
        },
        "current_price": round(float(latest["close"]), 2),
        "atr_20d": round(float(latest["ATR"]), 2) if pd.notna(latest["ATR"]) else None,
    }

    if direction != "FLAT":
        entry_price = float(latest["close"])  # proxy — real entry at Mon open
        atr = float(latest["ATR"])
        if direction == "LONG":
            stop_price = entry_price - 2 * atr
        else:
            stop_price = entry_price + 2 * atr
        call["entry_approx"] = round(entry_price, 2)
        call["stop_price"] = round(stop_price, 2)
        call["exit_type"] = "Friday close (time exit) or stop hit"
        call["expected_atr_move"] = round(atr, 2)
    else:
        call["message"] = "No signal this week. FLAT (no position)."

    call["published_utc"] = datetime.now(timezone.utc).isoformat()
    call["pre_reg_ref"] = "2026-07-22_far_weekly_gold_read_prereg.md"
    call["confidence_disclaimer"] = ("BETA — 3 of 6 pre-reg gates borderline failed. "
                                     "Live-tracking is the final validation. "
                                     "Position size accordingly.")
    return call


def resolve_prior_call(prior_call: dict, today: pd.Timestamp) -> dict:
    """Given a prior call whose week has ended, compute the actual outcome."""
    if prior_call.get("direction") == "FLAT":
        prior_call["outcome"] = {"result": "FLAT_no_position", "net_return_pct": 0.0}
        return prior_call

    week_end = pd.Timestamp(prior_call["week_end"], tz="UTC")
    if today <= week_end:
        return prior_call  # not yet resolved

    week_start = pd.Timestamp(prior_call["week_of"], tz="UTC")
    daily = far_backtest.load_daily_bars(week_start - pd.Timedelta(days=5),
                                          week_end + pd.Timedelta(days=2))
    if len(daily) == 0:
        return prior_call

    entry_price = prior_call.get("entry_approx")
    stop_price = prior_call.get("stop_price")
    direction = prior_call.get("direction")
    if entry_price is None or stop_price is None:
        return prior_call

    week_bars = daily[(daily.index >= week_start) & (daily.index <= week_end)]
    if len(week_bars) == 0:
        return prior_call

    dir_sign = 1 if direction == "LONG" else -1
    exit_price = None; exit_reason = None
    for _, row in week_bars.iterrows():
        hit_stop = ((direction == "LONG" and float(row["low"]) <= stop_price) or
                    (direction == "SHORT" and float(row["high"]) >= stop_price))
        if hit_stop:
            exit_price = stop_price; exit_reason = "stop"; break
    if exit_price is None:
        exit_price = float(week_bars.iloc[-1]["close"])
        exit_reason = "friday_close"

    pct_return = ((exit_price - entry_price) / entry_price) * dir_sign * 100
    prior_call["outcome"] = {
        "result": "resolved",
        "exit_price": round(exit_price, 2),
        "exit_reason": exit_reason,
        "net_return_pct": round(pct_return, 3),
        "resolved_utc": today.isoformat(),
    }
    return prior_call


def write_site_files(current_call: dict, history: list[dict]) -> None:
    for f in (SITE_CURRENT, SITE_HISTORY):
        f.parent.mkdir(parents=True, exist_ok=True)
    with open(SITE_CURRENT, "w") as f:
        json.dump(current_call, f, indent=2, default=str)

    # Track record summary from resolved history
    resolved = [c for c in history
                if c.get("outcome", {}).get("result") == "resolved"]
    n_resolved = len(resolved)
    wins = sum(1 for c in resolved
               if c["outcome"]["net_return_pct"] > 0)
    total_return = sum(c["outcome"]["net_return_pct"] for c in resolved)

    summary = {
        "product_name": "FAR Weekly Gold Read",
        "status": "BETA",
        "operator": "Knox",
        "since_utc": history[0]["published_utc"] if history else None,
        "resolved_calls": n_resolved,
        "wins": wins,
        "losses": n_resolved - wins,
        "win_rate_pct": round(100 * wins / n_resolved, 1) if n_resolved else None,
        "cumulative_return_pct": round(total_return, 2),
        "history": history,
    }
    with open(SITE_HISTORY, "w") as f:
        json.dump(summary, f, indent=2, default=str)


def check_kill_switch() -> bool:
    """Return True if publishing should be paused. Two ways to pause:

    - Env var FAR_WEEKLY_PAUSED=1 (systemd/shell control)
    - File data/far_weekly_paused (touch this file to pause)
    """
    import os
    if os.environ.get("FAR_WEEKLY_PAUSED", "").strip() in ("1", "true", "yes", "on"):
        return True
    kill_file = ROOT / "data" / "far_weekly_paused"
    if kill_file.exists():
        return True
    return False


def check_data_freshness(max_lag_days: int = 3) -> tuple[bool, str]:
    """Verify XAUUSD_5m.csv has recent data. Returns (fresh_ok, message)."""
    live_csv = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"
    if not live_csv.exists():
        return False, f"Live CSV missing: {live_csv}"
    try:
        # Read only the last line for speed
        with open(live_csv, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            offset = min(file_size, 4096)
            f.seek(file_size - offset)
            tail = f.read().decode("utf-8", errors="ignore")
        last_line = [l for l in tail.strip().split("\n") if l][-1]
        last_ts_str = last_line.split(",", 1)[0]
        last_ts = pd.Timestamp(last_ts_str)
        if last_ts.tz is None:
            last_ts = last_ts.tz_localize("UTC")
        age_days = (pd.Timestamp.now(tz="UTC") - last_ts).total_seconds() / 86400
        if age_days > max_lag_days:
            return False, f"Data stale by {age_days:.1f} days (last bar {last_ts})"
        return True, f"Data fresh: last bar {last_ts} ({age_days:.1f}d ago)"
    except Exception as e:
        return False, f"Failed to check data freshness: {e}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute + print but don't write to logs")
    ap.add_argument("--force", action="store_true",
                    help="Bypass kill switch and stale-data guard (use with care)")
    args = ap.parse_args()

    today = pd.Timestamp.now(tz="UTC")
    print(f"[FAR Weekly Gold Read] Running at {today.isoformat()}")

    if not args.force:
        # Kill switch check
        if check_kill_switch():
            print("[HALT] Kill switch active (FAR_WEEKLY_PAUSED env or "
                  "data/far_weekly_paused file). Not publishing.")
            sys.exit(0)

        # Stale-data guard
        ok, msg = check_data_freshness()
        print(f"[data freshness] {msg}")
        if not ok:
            print("[HALT] Data too stale. Aborting to avoid publishing on old data. "
                  "Rerun with --force after confirming data is intentional.")
            sys.exit(2)

    # Compute current call
    call = compute_current_signal(today)
    print(f"\nSignal: {call.get('direction', 'ERROR')}")
    if call.get("direction") != "FLAT":
        print(f"  Entry approx: {call.get('entry_approx')}")
        print(f"  Stop price:   {call.get('stop_price')}")
        print(f"  Week: {call.get('week_of')} -> {call.get('week_end')}")
    print(f"  Components: {call.get('signal_components')}")

    # Load history + resolve prior weeks
    history = load_call_history()
    for prior in history:
        if prior.get("type") == "call" and prior.get("outcome") is None:
            resolve_prior_call(prior, today)

    # Add new call if not duplicate week
    if history and history[-1].get("week_of") == call.get("week_of"):
        print(f"\n[note] already published call for week {call.get('week_of')} — not appending")
        history[-1] = call  # update in place
    else:
        history.append(call)
        if not args.dry_run:
            append_call(call)
            print(f"\n[appended] to {CALLS_LOG}")

    if not args.dry_run:
        write_site_files(call, history)
        print(f"[wrote] {SITE_CURRENT.name}, {SITE_HISTORY.name}")
        # Best-effort git commit + push so website picks up the new call.
        # Silently no-op on failure (VPS may not have creds; log will show).
        import subprocess
        try:
            # Rebase onto origin/main with autostash so all local churn
            # (dispatch state, GC bars, etc.) doesn't block the rebase.
            fetch = subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=str(ROOT), check=False, capture_output=True, timeout=30)
            pull = subprocess.run(
                ["git", "pull", "--rebase", "--autostash", "origin", "main"],
                cwd=str(ROOT), check=False, capture_output=True, timeout=90)
            if pull.returncode != 0:
                print(f"[git] pull-rebase failed: {pull.stderr.decode()[:200]}")
            # Re-write JSON in case autostash pop had issues
            write_site_files(call, history)

            subprocess.run(
                ["git", "add", str(CALLS_LOG), str(SITE_CURRENT), str(SITE_HISTORY)],
                cwd=str(ROOT), check=False, capture_output=True, timeout=30)
            msg = f"FAR Weekly Gold Read: {call.get('direction', 'ERROR')} "\
                  f"call for {call.get('week_of', 'unknown')}"
            r = subprocess.run(
                ["git", "commit", "-m", msg,
                 "--author=Knox VPS <knox@golddaytrador.local>"],
                cwd=str(ROOT), check=False, capture_output=True, timeout=30)
            if r.returncode == 0:
                push = subprocess.run(
                    ["git", "push", "origin", "main"],
                    cwd=str(ROOT), check=False, capture_output=True, timeout=60)
                if push.returncode == 0:
                    print("[git] committed + pushed")
                else:
                    print(f"[git] commit OK, push failed: "
                          f"{push.stderr.decode()[:200]}")
            else:
                print(f"[git] no commit needed: {r.stdout.decode()[:100]}")
        except Exception as e:
            print(f"[git] skipped: {e}")
    else:
        print("\n[dry-run] no files written")


if __name__ == "__main__":
    main()
