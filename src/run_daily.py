"""Daily refresh and alert pipeline.

Run this once per day (manually or via task scheduler). It:
  1. Snapshots fresh GC=F bars at all intervals (merges into local store).
  2. Refreshes FRED macro series.
  3. Rebuilds the event calendar (with forward-looking placeholders).
  4. Emits live alerts for upcoming top-tier events.
  5. Resolves any past pending trades (writes outcome to a tracking log).
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timezone

from data_gc import snapshot_all as gc_snapshot
from data_fred import snapshot_all as fred_snapshot
from calendar_events import build_all, save as save_cal
import subprocess


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_path = LOG_DIR / f"daily_{ts}.log"
    log = open(log_path, "w")

    def out(msg: str):
        print(msg)
        log.write(msg + "\n")
        log.flush()

    out(f"=== Daily refresh @ {datetime.now(timezone.utc).isoformat(timespec='seconds')} ===")

    out("\n[1/5] Refreshing GC bars...")
    stats = gc_snapshot(verbose=False)
    for iv, s in stats.items():
        if s.get("status") == "ok":
            out(f"   {iv:4s} stored {s['stored_before']} -> {s['stored_after']} (+{s['added']})")
        else:
            out(f"   {iv:4s} {s.get('status')} {s.get('error', '')}")

    out("\n[2/5] Refreshing FRED macro series...")
    stats = fred_snapshot(verbose=False)
    for name, s in stats.items():
        if s.get("status") == "ok":
            out(f"   {name:18s} rows={s['rows']:>6d} last={s['last']}")
        else:
            out(f"   {name} {s}")

    out("\n[3/5] Rebuilding event calendar...")
    cal = build_all()
    path = save_cal(cal)
    out(f"   saved {len(cal)} events -> {path}")

    out("\n[4/5] Generating live alerts (next 7 days)...")
    res = subprocess.run([sys.executable, str(ROOT / "src" / "signal_live.py"),
                          "--horizon-hours", "168"],
                          capture_output=True, text=True,
                          env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    out(res.stdout)
    if res.returncode != 0:
        out(f"   STDERR: {res.stderr}")

    import os
    utf8_env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

    out("\n[5/6] Resolving past trades (paper-trade tracker)...")
    res = subprocess.run([sys.executable, str(ROOT / "src" / "track_results.py")],
                          capture_output=True, text=True, env=utf8_env)
    out(res.stdout)
    if res.returncode != 0:
        out(f"   STDERR: {res.stderr}")

    out("\n[5b] Updating trade journal...")
    res = subprocess.run([sys.executable, str(ROOT / "src" / "trade_journal.py")],
                          capture_output=True, text=True, env=utf8_env)
    out(res.stdout)
    if res.returncode != 0:
        out(f"   STDERR: {res.stderr}")

    out("\n[5c] Resolving ORB forward trades...")
    res = subprocess.run([sys.executable, str(ROOT / "src" / "track_orb.py")],
                          capture_output=True, text=True, env=utf8_env)
    out(res.stdout)
    if res.returncode != 0:
        out(f"   STDERR: {res.stderr}")

    out("\n[6/6] Dispatching Telegram alerts (24h/1h/plan)...")
    res = subprocess.run([sys.executable, str(ROOT / "src" / "dispatch.py")],
                          capture_output=True, text=True, env=utf8_env)
    out(res.stdout)
    if res.returncode != 0:
        out(f"   STDERR: {res.stderr}")

    out("\nSending dashboard summary to Telegram...")
    try:
        from dashboard import build_dashboard
        from telegram_bot import send_split
        results = send_split(build_dashboard())
        if any(r.get("ok") for r in results):
            out(f"   sent {len(results)} message(s).")
        else:
            errs = ", ".join(set(r.get("error", "?") for r in results))
            out(f"   not sent ({errs}). Set GOLDTRADER_TG_TOKEN and GOLDTRADER_TG_CHAT or write to .telegram file.")
    except Exception as e:
        out(f"   skipped ({e})")

    out("\n=== done ===")
    log.close()
    print(f"\nFull log -> {log_path}")


if __name__ == "__main__":
    main()
