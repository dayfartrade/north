"""Sunday pre-publish preview — sends to private Telegram one hour
before the public weekly-publish fires.

Content:
  1. What v1 would publish (the actual call about to go public)
  2. What v2 (DXY-confirmed) says — agrees or filters?
  3. What ensemble (v1+v2+monthly-M12, >=2) says
  4. Upcoming resolve: prior week's outcome preview if window has closed
  5. Halt reminder if any divergence between models

Goal: give the operator a heads-up on what subscribers will see, and a
chance to intervene (kill switch, manual override) BEFORE public publish.

Usage:
    python scripts/pre_publish_preview.py                (send to private)
    python scripts/pre_publish_preview.py --dry-run      (print only)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

RULE = "━━━━━━━━━━━━━━━━━━━━━━━━"
CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"


def esc(s):
    """Escape legacy Markdown special chars in raw content strings."""
    return str(s).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")

spec = importlib.util.spec_from_file_location("pub",
    str(ROOT / "scripts" / "far_weekly_gold_read_publish.py"))
pub = importlib.util.module_from_spec(spec); spec.loader.exec_module(pub)


def load_prior_call() -> dict | None:
    """Latest call whose window has closed but hasn't been publicly resolved."""
    if not CALLS_LOG.exists():
        return None
    with open(CALLS_LOG) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    now = pd.Timestamp.now(tz="UTC")
    for row in reversed(rows):
        if row.get("type") != "call":
            continue
        we = pd.Timestamp(row.get("week_end", "1970-01-01"), tz="UTC")
        if now > we + pd.Timedelta(hours=21):
            return row
    return None


def format_preview() -> str:
    today = pd.Timestamp.now(tz="UTC")
    v1_call = pub.compute_current_signal(today)
    v2_shadow = pub.compute_v2_shadow(today)
    ens_shadow = pub.compute_ensemble_shadow(today)

    v1_dir = v1_call.get("direction", "?")
    v2_dir = v2_shadow.get("v2_direction", "?")
    ens_dir = ens_shadow.get("ensemble_direction", "?")

    lines = [
        "🔍 *PRE-PUBLISH PREVIEW* (private)",
        f"_by Knox · {today.strftime('%Y-%m-%d %H:%M UTC')}_",
        f"_public publish at 22:00 UTC (~{60 - today.minute}m if run at 21:00)_",
        RULE,
        f"*Week of {v1_call.get('week_of','?')} → {v1_call.get('week_end','?')}*",
        "",
        f"📢 *v1 (will go public):*  `{v1_dir}`",
    ]

    if v1_dir != "FLAT":
        lines += [
            f"    Entry ≈ `${v1_call.get('entry_approx','?')}`",
            f"    Stop  = `${v1_call.get('stop_price','?')}`",
            f"    ATR20 = ${v1_call.get('atr_20d','?')}",
        ]
        sc = v1_call.get("signal_components", {})
        lines += [
            f"    Drivers: M20 {sc.get('M20_pct','?')}%, M60 {sc.get('M60_pct','?')}%, "
            f"MA10>MA40 {sc.get('MA10_above_MA40','?')}, "
            f"{esc('RY_chg')} {sc.get('RY_chg_20d_bps','?')}bp",
        ]

    def emoji(d):
        return {"LONG":"🟢","SHORT":"🔴","FLAT":"⚪"}.get(d,"❓")

    lines += [
        "",
        f"🔬 *v2 (shadow, DXY-confirmed):*  {emoji(v2_dir)} `{v2_dir}`",
    ]
    if v2_shadow.get("filtered_by_dxy"):
        lines.append(f"    (v1 said {v1_dir} but DXY did not confirm — v2 FLAT)")
    if v2_shadow.get("dxy_chg_20d") is not None:
        lines.append(f"    {esc('DXY_chg_20d')}: {v2_shadow['dxy_chg_20d']:+.3f}")

    lines += [
        "",
        f"🧪 *ensemble (v1+v2+monthly, ≥2 agree):*  {emoji(ens_dir)} `{ens_dir}`",
    ]
    if ens_shadow.get("unanimous"):
        lines.append("    (unanimous 3/3)")
    else:
        lines.append(f"    votes: LONG={ens_shadow.get('votes_long','?')}  "
                     f"SHORT={ens_shadow.get('votes_short','?')}")
    if ens_shadow.get("m12_pct") is not None:
        lines.append(f"    M12 momentum: {ens_shadow['m12_pct']:+.2f}%")

    # Divergence
    dirs = {v1_dir, v2_dir, ens_dir}
    lines += [RULE]
    if len(dirs) == 1:
        lines.append(f"✅ *All three agree: {v1_dir}*")
    elif "LONG" in dirs and "SHORT" in dirs:
        lines.append("🚨 *DIVERGENCE: models pointing opposite ways.* "
                     "Consider halting.")
    else:
        lines.append("⚠️  *Partial divergence:* v1 will publish, "
                     "shadow models disagree. Consider review.")

    # Upcoming resolve
    prior = load_prior_call()
    if prior and not prior.get("outcome"):
        lines += [
            RULE,
            f"⏳ *Prior week ({prior.get('week_of','?')}) not yet resolved in log*",
            "    The public publish will attempt to resolve it. Verify data is fresh.",
        ]
    elif prior and prior.get("outcome"):
        out = prior["outcome"]
        r = out.get("net_return_pct", 0)
        icon = "✅" if r > 0 else ("🟥" if r < 0 else "➖")
        lines += [
            RULE,
            f"📋 *Prior week ({prior.get('week_of','?')}) resolve:*  "
            f"{prior.get('direction','?')} {r:+.2f}% {icon}",
        ]

    lines += [
        RULE,
        "*Actions available before public publish:*",
        f"  • Halt: touch {esc('data/far_weekly_paused')} (in repo)",
        "  • Wait for next Sunday if uncertain",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    msg = format_preview()
    print(msg)
    if args.dry_run:
        return
    from telegram_bot import send
    r = send(msg, audience="private")
    print("\nsend result:", r)


if __name__ == "__main__":
    main()
