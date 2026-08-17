"""NORTH Daily Brief - midweek position update.

Publishes a 3-section card while a directional weekly call is live:

  🩺 Signal Health         - is the position behaving as expected
  💰 Cost Radar            - open P&L, MAE, distance to stop
  ⚠️  What Kills This Call  - the specific price move that flips WIN to LOSS

If the active call is FLAT: exits silently. No engagement theater on
sitting-out weeks (per soft_launch_decisions.md).

Data flow:
  - Active call:   data/far_weekly_calls.jsonl  (latest row, unresolved)
  - Current spot:  Dukascopy XAUUSD 5m (last complete bar)
  - MAE / bars since entry: XAUUSD 5m from entry date onward

Freshness gate: XAUUSD data must be no more than 3h stale on a
trading day, else refuses to publish (state stale is worse than silent).

Usage:
    python scripts/north_daily_brief.py --dry-run
    python scripts/north_daily_brief.py --audience private
    python scripts/north_daily_brief.py --audience public
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"
XAUUSD_5M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"
DAILY_BRIEF_LOG = ROOT / "data" / "north_daily_brief.jsonl"
KILL_FILE = ROOT / "data" / "far_weekly_paused"

MAX_STALE_HOURS = 6
RULE = "━━━━━━━━━━━━━━━━━━━━━━━━"


def load_active_call() -> dict | None:
    if not CALLS_LOG.exists():
        return None
    with open(CALLS_LOG) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    for row in reversed(rows):
        if row.get("type") == "call" and row.get("outcome") is None:
            return row
    return None


def load_xauusd_since(entry_date_utc: pd.Timestamp) -> pd.DataFrame:
    if not XAUUSD_5M.exists():
        raise FileNotFoundError(f"XAUUSD 5m missing: {XAUUSD_5M}")
    df = pd.read_csv(XAUUSD_5M, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df[df["ts"] >= entry_date_utc].sort_values("ts").reset_index(drop=True)
    return df


def check_freshness(bars: pd.DataFrame) -> tuple[bool, str]:
    if bars.empty:
        return False, "no bars since entry"
    last = bars["ts"].max()
    age_h = (pd.Timestamp.now(tz="UTC") - last).total_seconds() / 3600
    if age_h > MAX_STALE_HOURS:
        return False, f"XAUUSD stale by {age_h:.1f}h (last: {last})"
    return True, f"fresh: last={last} ({age_h:.1f}h ago)"


def compute_position_metrics(call: dict, bars: pd.DataFrame) -> dict:
    entry_price = float(call["entry_approx"])
    stop_price = float(call["stop_price"])
    direction = call["direction"]
    atr = float(call.get("atr_20d", 0)) or 0.0
    now_price = float(bars["close"].iloc[-1])

    if direction == "LONG":
        pnl_pct = (now_price - entry_price) / entry_price * 100
        mae_price = float(bars["low"].min())
        mae_pct = (mae_price - entry_price) / entry_price * 100
        stop_dist_pct = (now_price - stop_price) / now_price * 100
    else:  # SHORT
        pnl_pct = (entry_price - now_price) / entry_price * 100
        mae_price = float(bars["high"].max())
        mae_pct = (entry_price - mae_price) / entry_price * 100
        stop_dist_pct = (stop_price - now_price) / now_price * 100

    stop_dist_dollars = abs(stop_price - now_price)
    stop_dist_atr = stop_dist_dollars / atr if atr > 0 else 0

    week_end = pd.Timestamp(call["week_end"], tz="UTC") + pd.Timedelta(hours=21)
    week_start = pd.Timestamp(call["week_of"], tz="UTC")
    now = pd.Timestamp.now(tz="UTC")
    days_held = max(0, (now - week_start).days)
    hours_to_close = max(0.0, (week_end - now).total_seconds() / 3600)

    return {
        "direction": direction,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "now_price": now_price,
        "pnl_pct": pnl_pct,
        "mae_price": mae_price,
        "mae_pct": mae_pct,
        "stop_dist_dollars": stop_dist_dollars,
        "stop_dist_pct": stop_dist_pct,
        "stop_dist_atr": stop_dist_atr,
        "atr20": atr,
        "days_held": days_held,
        "hours_to_close": hours_to_close,
        "week_of": call["week_of"],
        "week_end": call["week_end"],
    }


def health_verdict(m: dict) -> tuple[str, str]:
    """Return (badge, one-line narrative) for signal health section."""
    pnl = m["pnl_pct"]
    stop_atr = m["stop_dist_atr"]
    if stop_atr < 0.5:
        return "🚨 AT RISK", f"Price is within 0.5x ATR of stop. One volatile session away from exit."
    if pnl >= 0.5:
        return "✅ ON TRACK", f"Position is {pnl:+.2f}% in the money. Trajectory matches thesis."
    if pnl >= -0.3:
        return "🟡 CHOPPING", f"Small drift ({pnl:+.2f}%). Within noise. Wait for the week to play out."
    return "⚠️ DRIFTING", f"Currently {pnl:+.2f}% underwater. Stop still {stop_atr:.2f}x ATR away."


def kill_conditions(m: dict) -> list[str]:
    """Direction-specific 'what flips this call' lines."""
    d = m["direction"]
    entry = m["entry_price"]
    stop = m["stop_price"]
    lines = []
    if d == "SHORT":
        lines.append(f"• Intraday break above `${stop:,.2f}` → immediate stop-out.")
        lines.append(f"• Friday close above `${entry:,.2f}` → time-exit loss.")
    else:
        lines.append(f"• Intraday break below `${stop:,.2f}` → immediate stop-out.")
        lines.append(f"• Friday close below `${entry:,.2f}` → time-exit loss.")
    return lines


def format_card(m: dict) -> str:
    badge, narrative = health_verdict(m)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    dir_badge = "🔴 *SHORT*" if m["direction"] == "SHORT" else "🟢 *LONG*"

    lines = [
        "📡 *NORTH - Daily Brief*",
        f"_by Knox · {today}_",
        RULE,
        f"Position: {dir_badge}  ·  week {m['week_of']} → {m['week_end']}",
        f"Held: {m['days_held']}d  ·  {m['hours_to_close']:.0f}h to Friday close",
        "",
        f"🩺 *Signal Health*  {badge}",
        f"  Entry:      `${m['entry_price']:,.2f}`",
        f"  Now:        `${m['now_price']:,.2f}`  ({m['pnl_pct']:+.2f}%)",
        f"  {narrative}",
        "",
        f"💰 *Cost Radar*",
        f"  Open P&L:   {m['pnl_pct']:+.2f}%",
        f"  MAE:        {m['mae_pct']:+.2f}%  (worst: `${m['mae_price']:,.2f}`)",
        f"  Stop:       `${m['stop_price']:,.2f}`  "
        f"({m['stop_dist_pct']:.2f}% / {m['stop_dist_atr']:.2f}x ATR away)",
        "",
        f"⚠️  *What Kills This Call*",
    ]
    lines += [f"  {line}" for line in kill_conditions(m)]
    lines += [
        RULE,
        "_BETA. Weekly signal, midweek observation only - no new trades._",
    ]
    return "\n".join(lines)


def append_brief_log(rec: dict):
    DAILY_BRIEF_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DAILY_BRIEF_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print card to stdout, no Telegram, no log write")
    ap.add_argument("--audience", choices=["private", "public"], default="private")
    ap.add_argument("--force", action="store_true",
                    help="publish even if XAUUSD data is stale (for testing)")
    args = ap.parse_args()

    print(f"[north_daily_brief] {datetime.now(timezone.utc).isoformat()}")

    import os
    if not args.force:
        paused_env = os.environ.get("FAR_WEEKLY_PAUSED", "").strip().lower() in ("1","true","yes","on")
        if paused_env or KILL_FILE.exists():
            print(f"[HALT] Kill switch active (FAR_WEEKLY_PAUSED env or "
                  f"{KILL_FILE.name} file). Not publishing brief.")
            sys.exit(0)

    call = load_active_call()
    if call is None:
        print("[skip] no active call in far_weekly_calls.jsonl")
        return
    if call.get("direction") == "FLAT":
        print(f"[skip] active call is FLAT for week {call.get('week_of')} - "
              "no midweek brief (per soft-launch decision, no sitting-out theater)")
        return
    if call.get("entry_approx") is None or call.get("stop_price") is None:
        print(f"[skip] active call missing entry/stop: {call}")
        return

    week_start = pd.Timestamp(call["week_of"], tz="UTC")
    bars = load_xauusd_since(week_start)
    fresh, msg = check_freshness(bars)
    print(f"[data] {msg} ({len(bars)} bars since {week_start.date()})")
    if not fresh and not args.force:
        print(f"[halt] stale XAUUSD data. Refusing to publish. Use --force to override.")
        sys.exit(2)
    if bars.empty:
        print("[skip] no bars yet - entry day not started")
        return

    metrics = compute_position_metrics(call, bars)
    card = format_card(metrics)
    print()
    print(card)
    print()

    if args.dry_run:
        print("[dry-run] no publish, no log write")
        return

    sys.path.insert(0, str(ROOT / "src"))
    from telegram_bot import send
    r = send(card, audience=args.audience)
    print(f"[telegram] {r}")

    rec = {
        "brief_utc": datetime.now(timezone.utc).isoformat(),
        "week_of": call["week_of"],
        "direction": call["direction"],
        "audience": args.audience,
        "metrics": {k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in metrics.items()},
        "telegram_ok": bool(r.get("ok") if isinstance(r, dict) else False),
    }
    append_brief_log(rec)
    print(f"[log] appended to {DAILY_BRIEF_LOG.name}")


if __name__ == "__main__":
    main()
