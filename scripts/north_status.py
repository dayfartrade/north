"""NORTH status probe — one-shot health check.

Prints a Markdown-flavored summary of:
  - Latest GitHub Actions runs (5 workflows) via `gh`
  - Active weekly call + most-recent resolve
  - Shadow log state (gold basis, silver GSR)
  - Data freshness (XAU/USD, XAG/USD, GC=F, macro CSVs)
  - Kill switch status (halt file present?)
  - Telegram credential sanity

Usage:
    python scripts/north_status.py
    python scripts/north_status.py --github    (adds GH Actions status; needs gh CLI + token)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

RULE = "-" * 60


def hdr(txt):
    print(f"\n{RULE}\n{txt}\n{RULE}")


def check_calls():
    p = ROOT / "data" / "far_weekly_calls.jsonl"
    if not p.exists():
        print("  no calls log")
        return
    rows = [json.loads(l) for l in open(p) if l.strip()]
    print(f"  total calls: {len(rows)}")
    if not rows:
        return
    latest = rows[-1]
    print(f"  latest: {latest.get('week_of','?')} -> {latest.get('week_end','?')}")
    print(f"         direction: {latest.get('direction','?')}")
    if latest.get("outcome"):
        o = latest["outcome"]
        print(f"         RESOLVED: {o.get('result')} {o.get('net_return_pct'):+.2f}% "
              f"({o.get('exit_reason','?')})")
    else:
        print(f"         status: LIVE (window not closed or unresolved)")
    resolved = [r for r in rows if r.get("outcome",{}).get("result") == "resolved"]
    if resolved:
        pnls = [r["outcome"]["net_return_pct"] for r in resolved]
        wins = sum(1 for p in pnls if p>0)
        print(f"  track: n={len(resolved)} wins={wins} cum={sum(pnls):+.2f}%")


def check_shadow(label, path, key):
    if not path.exists():
        print(f"  {label}: no log")
        return
    rows = [json.loads(l) for l in open(path) if l.strip()]
    sigs = [r for r in rows if r.get("type")=="signal"]
    res = [r for r in rows if r.get("type")=="resolve"]
    print(f"  {label}: {len(sigs)} signals, {len(res)} resolves")
    if res:
        rs = [r["r_multiple"] for r in res]
        dol = [r["pnl_dollars"] for r in res]
        wins = sum(1 for r in rs if r>0)
        print(f"    R mean {sum(rs)/len(rs):+.3f}  $ total {sum(dol):+.0f}  "
              f"wins {wins}/{len(rs)}")


def check_data_freshness():
    # (label, path, is_gitignored, weekend_ok)
    # is_gitignored=True means the file is intentionally not versioned
    # (fetched fresh into cache by CI each run). Local staleness is
    # cosmetic, not a live-pipeline problem.
    # weekend_ok=True means daily bars naturally lag on Sat/Sun with
    # no market activity, so weekend staleness is expected.
    paths = [
        ("XAU/USD 5m", ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv", True,  False),
        ("XAG/USD 5m", ROOT / "data" / "external" / "dukascopy" / "XAGUSD_5m.csv", True,  False),
        ("GC=F daily", ROOT / "data" / "gc" / "GC_1d.csv",                          False, True),
    ]
    now = pd.Timestamp.now(tz="UTC")
    for label, p, is_gitignored, weekend_ok in paths:
        if not p.exists():
            print(f"  {label}: MISSING ({p})")
            continue
        try:
            with open(p, "rb") as f:
                f.seek(0, 2); sz = f.tell()
                f.seek(max(0, sz - 4096))
                tail = f.read().decode("utf-8", errors="ignore")
            last = [l for l in tail.strip().split("\n") if l][-1]
            ts_str = last.split(",", 1)[0]
            ts = pd.Timestamp(ts_str)
            if ts.tz is None:
                ts = ts.tz_localize("UTC")
            age_h = (now - ts).total_seconds() / 3600

            # Choose flag with the file's context in mind.
            if is_gitignored:
                flag = "local-only (CI fetches fresh)"
            elif weekend_ok and now.weekday() >= 5 and age_h < 24 * 4:
                flag = "ok (weekend)"
            elif age_h > 24 * 3:
                flag = "STALE"
            else:
                flag = "ok"
            print(f"  {label}: last={ts}  age={age_h:.1f}h  [{flag}]")
        except Exception as e:
            print(f"  {label}: read error {type(e).__name__}: {e}")


def check_kill_switch():
    k = ROOT / "data" / "far_weekly_paused"
    if k.exists():
        print("  [HALTED] KILL SWITCH ACTIVE — publishing halted (touch removed via rm)")
    else:
        print("  ok — publishing enabled")


def check_telegram():
    creds = ROOT / ".telegram"
    if creds.exists():
        n = sum(1 for l in open(creds) if "GOLDTRADER" in l)
        print(f"  .telegram exists ({n} keys)")
    else:
        print("  .telegram file MISSING")
    import os
    for k in ("GOLDTRADER_TG_TOKEN","GOLDTRADER_TG_CHAT","GOLDTRADER_TG_CHAT_PUBLIC"):
        print(f"  env {k}: {'SET' if os.environ.get(k) else '(from file)'}")


def check_github_actions(token_file=".github-token"):
    tp = ROOT / token_file
    if not tp.exists():
        print("  no .github-token — skipping GH checks")
        return
    tok = tp.read_text().strip()
    import os
    env = os.environ.copy(); env["GH_TOKEN"] = tok
    for wf in ("data-refresh.yml","shadow-log.yml","silver-shadow-log.yml",
               "weekly-publish.yml","daily-brief.yml","pre-publish-preview.yml"):
        try:
            r = subprocess.run(
                ["gh","run","list","--workflow",wf,"--repo","dayfartrade/north","--limit","1",
                 "--json","status,conclusion,createdAt","-q",
                 ".[0] | \"\\(.status)|\\(.conclusion // \"-\")|\\(.createdAt)\""],
                capture_output=True, text=True, env=env, timeout=30)
            line = (r.stdout or "").strip() or "(no runs)"
            print(f"  {wf:30s} {line}")
        except Exception as e:
            print(f"  {wf}: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--github", action="store_true", help="include GitHub Actions status")
    args = ap.parse_args()

    print(f"NORTH STATUS — {datetime.now(timezone.utc).isoformat()}")

    hdr("WEEKLY CALLS")
    check_calls()

    hdr("SHADOW LOGS")
    check_shadow("gold basis", ROOT / "data" / "gold_basis_shadow.jsonl", "signal_id")
    check_shadow("silver GSR", ROOT / "data" / "silver_gsr_shadow.jsonl", "signal_id")

    hdr("DATA FRESHNESS")
    check_data_freshness()

    hdr("KILL SWITCH")
    check_kill_switch()

    hdr("TELEGRAM")
    check_telegram()

    if args.github:
        hdr("GITHUB ACTIONS (last run per workflow)")
        check_github_actions()


if __name__ == "__main__":
    main()
