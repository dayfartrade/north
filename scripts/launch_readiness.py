"""Pre-launch readiness verifier for NORTH soft launch.

Runs the pre-launch punchlist from docs/launch/north_first_send.md as
executable checks. Exits with non-zero code if any hard requirement fails.

Checks performed:
  1. Kill switch is OFF (data/far_weekly_paused does not exist).
  2. All 7 launch docs exist at docs/launch/.
  3. retirement_wall.md is fresh (regenerable from current registry).
  4. track_record_current.md is fresh (regenerable from current calls log).
  5. Telegram bot token loads and getMe succeeds.
  6. Public channel exists via getChat, and bot is administrator with
     can_post_messages permission.
  7. Recent weekly-publish workflow run on GitHub Actions succeeded
     (proves the publish path + public secret work end-to-end).
  8. Data-refresh workflow's most recent run succeeded.

Usage:
    python scripts/launch_readiness.py
    python scripts/launch_readiness.py --strict   (exit 1 on any warning)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

LAUNCH_DOCS = [
    "docs/launch/north_public_intro.md",
    "docs/launch/north_first_send.md",
    "docs/launch/halt_notice.md",
    "docs/launch/invite_message.md",
    "docs/launch/knox_market_read_template.md",
    "docs/launch/retirement_wall.md",
    "docs/launch/track_record_current.md",
]

RESULT_PASS = "PASS"
RESULT_FAIL = "FAIL"
RESULT_WARN = "WARN"


def load_telegram_env():
    """Load .telegram file into environ if present."""
    p = ROOT / ".telegram"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


def check_kill_switch() -> tuple[str, str]:
    p = ROOT / "data" / "far_weekly_paused"
    if p.exists():
        return RESULT_FAIL, f"kill switch is ON (file exists: {p}). Delete to enable publishing."
    return RESULT_PASS, "kill switch OFF"


def check_launch_docs_exist() -> tuple[str, str]:
    missing = [d for d in LAUNCH_DOCS if not (ROOT / d).exists()]
    if missing:
        return RESULT_FAIL, f"missing: {', '.join(missing)}"
    return RESULT_PASS, f"all {len(LAUNCH_DOCS)} launch docs present"


def check_retirement_wall_fresh() -> tuple[str, str]:
    wall = ROOT / "docs" / "launch" / "retirement_wall.md"
    registry = ROOT / "data" / "experiments" / "registry.json"
    if not wall.exists():
        return RESULT_FAIL, "retirement_wall.md missing"
    if not registry.exists():
        return RESULT_FAIL, "registry.json missing"
    reg_data = json.loads(registry.read_text())
    n_rejected = sum(1 for t in reg_data["trials"]
                     if t.get("verdict", "").lower().startswith(("rejected", "retired", "killed", "halted")))
    wall_text = wall.read_text()
    if f"{n_rejected} rejected trials" not in wall_text:
        return RESULT_WARN, (
            f"retirement wall claims a rejection count that does not match registry "
            f"(registry has {n_rejected} rejected). Regenerate with "
            f"`python scripts/build_retirement_wall.py`."
        )
    return RESULT_PASS, f"retirement wall in sync with registry ({n_rejected} rejected trials)"


def check_track_record_fresh() -> tuple[str, str]:
    tr = ROOT / "docs" / "launch" / "track_record_current.md"
    calls = ROOT / "data" / "far_weekly_calls.jsonl"
    if not tr.exists():
        return RESULT_FAIL, "track_record_current.md missing"
    if not calls.exists():
        return RESULT_FAIL, "far_weekly_calls.jsonl missing"
    rows = [json.loads(l) for l in calls.read_text().splitlines() if l.strip()]
    if not rows:
        return RESULT_WARN, "no calls on record yet"
    latest_week = rows[-1].get("week_of", "?")
    tr_text = tr.read_text()
    if latest_week not in tr_text:
        return RESULT_WARN, (
            f"track record does not include latest week ({latest_week}). "
            f"Regenerate with `python scripts/render_track_record.py`."
        )
    return RESULT_PASS, f"track record includes latest week ({latest_week})"


def check_telegram_bot() -> tuple[str, str]:
    token = os.environ.get("GOLDTRADER_TG_TOKEN")
    if not token:
        return RESULT_FAIL, "GOLDTRADER_TG_TOKEN not set"
    try:
        import urllib.request
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        if not d.get("ok"):
            return RESULT_FAIL, f"getMe failed: {d}"
        return RESULT_PASS, f"bot @{d['result']['username']} (id {d['result']['id']})"
    except Exception as e:
        return RESULT_FAIL, f"getMe error: {type(e).__name__}: {e}"


def check_public_channel() -> tuple[str, str]:
    token = os.environ.get("GOLDTRADER_TG_TOKEN")
    chat_id = os.environ.get("GOLDTRADER_TG_CHAT_PUBLIC")
    if not token:
        return RESULT_FAIL, "GOLDTRADER_TG_TOKEN not set"
    if not chat_id:
        return RESULT_FAIL, "GOLDTRADER_TG_CHAT_PUBLIC not set"
    try:
        import urllib.request
        req1 = urllib.request.Request(f"https://api.telegram.org/bot{token}/getChat?chat_id={chat_id}")
        with urllib.request.urlopen(req1, timeout=10) as r:
            chat = json.loads(r.read())
        if not chat.get("ok"):
            return RESULT_FAIL, f"getChat failed: {chat}"
        title = chat["result"].get("title", "?")

        req_me = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
        with urllib.request.urlopen(req_me, timeout=10) as r:
            me = json.loads(r.read())
        bot_id = me["result"]["id"]

        req2 = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getChatMember"
            f"?chat_id={chat_id}&user_id={bot_id}"
        )
        with urllib.request.urlopen(req2, timeout=10) as r:
            mem = json.loads(r.read())
        if not mem.get("ok"):
            return RESULT_FAIL, f"getChatMember failed: {mem}"
        status = mem["result"].get("status")
        can_post = mem["result"].get("can_post_messages", False)
        if status != "administrator":
            return RESULT_FAIL, f"bot status is {status}, expected administrator"
        if not can_post:
            return RESULT_FAIL, "bot is admin but cannot post messages"
        msg = f'channel "{title}" ok, bot is admin with can_post_messages'
        # Channels do not have a separate pin permission; Message 1 is pinned
        # manually on launch day (documented in operator_runbook.md).
        return RESULT_PASS, msg
    except Exception as e:
        return RESULT_FAIL, f"channel check error: {type(e).__name__}: {e}"


def check_intro_backtest() -> tuple[str, str]:
    """Run the verify_north_v1_backtest.py script; PASS if it exits 0."""
    try:
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_north_v1_backtest.py")],
            capture_output=True, text=True, timeout=300
        )
        if r.returncode == 0:
            return RESULT_PASS, "all intro numbers match backtest"
        return RESULT_FAIL, f"verify script failed (rc={r.returncode}); run manually to see which metric drifted"
    except Exception as e:
        return RESULT_WARN, f"verify script error {type(e).__name__}: {e}"


def check_github_workflow(workflow_file: str) -> tuple[str, str]:
    token_path = ROOT / ".github-token"
    if not token_path.exists():
        return RESULT_WARN, ".github-token missing, cannot check Actions"
    env = os.environ.copy()
    env["GH_TOKEN"] = token_path.read_text().strip()
    try:
        r = subprocess.run(
            ["gh", "run", "list", "--workflow", workflow_file,
             "--repo", "dayfartrade/north", "--limit", "1",
             "--json", "status,conclusion,createdAt",
             "-q", '.[0] | "\\(.status)|\\(.conclusion // "-")|\\(.createdAt)"'],
            capture_output=True, text=True, env=env, timeout=30
        )
        line = (r.stdout or "").strip()
        if not line:
            return RESULT_FAIL, f"{workflow_file}: no runs found"
        status, conclusion, when = line.split("|")
        if status != "completed":
            return RESULT_WARN, f"{workflow_file}: last run status {status} ({when})"
        if conclusion != "success":
            return RESULT_FAIL, f"{workflow_file}: last run conclusion {conclusion} ({when})"
        return RESULT_PASS, f"{workflow_file}: last run success ({when})"
    except Exception as e:
        return RESULT_WARN, f"{workflow_file}: gh error {type(e).__name__}: {e}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit 1 on any WARN result")
    args = ap.parse_args()

    load_telegram_env()

    print("NORTH pre-launch readiness check")
    print("=" * 60)

    checks = [
        ("Kill switch off", check_kill_switch),
        ("Launch docs present", check_launch_docs_exist),
        ("Retirement wall fresh", check_retirement_wall_fresh),
        ("Track record fresh", check_track_record_fresh),
        ("Intro backtest numbers verified", check_intro_backtest),
        ("Telegram bot alive", check_telegram_bot),
        ("Public channel + bot perms", check_public_channel),
        ("weekly-publish workflow", lambda: check_github_workflow("weekly-publish.yml")),
        ("data-refresh workflow", lambda: check_github_workflow("data-refresh.yml")),
        ("pre-publish-preview workflow", lambda: check_github_workflow("pre-publish-preview.yml")),
    ]

    results = []
    for name, fn in checks:
        try:
            status, msg = fn()
        except Exception as e:
            status, msg = RESULT_FAIL, f"exception: {type(e).__name__}: {e}"
        icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
        print(f"  {icon} {name}: {msg}")
        results.append((name, status))

    print("=" * 60)
    passes = sum(1 for _, s in results if s == RESULT_PASS)
    warns = sum(1 for _, s in results if s == RESULT_WARN)
    fails = sum(1 for _, s in results if s == RESULT_FAIL)
    print(f"Summary: {passes} pass, {warns} warn, {fails} fail")

    if fails > 0:
        print("Not ready to launch. Fix FAIL items before Message 1 goes out.")
        sys.exit(2)
    if warns > 0 and args.strict:
        print("Warnings present (strict mode). Not launching.")
        sys.exit(1)
    print("Ready. Proceed with the launch sequence in docs/launch/north_first_send.md.")


if __name__ == "__main__":
    main()
