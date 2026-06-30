"""System health checks. Used by dispatch and run_daily to avoid acting on stale data."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json

import pandas as pd

from data_gc import load as gc_load

ROOT = Path(__file__).resolve().parent.parent
HEALTH_FILE = ROOT / "data" / "health.json"

STALE_BAR_HOURS = 24  # yfinance free GC=F has ~15h delay; only warn if older than 24h
                       # For true real-time, switch to broker data feed
HEARTBEAT_DAILY = True


def bar_freshness() -> dict:
    """How stale is our latest 1h bar?"""
    bars = gc_load("60m")
    last = pd.Timestamp(bars.index[-1])
    if last.tz is None:
        last = last.tz_localize("UTC")
    age = (pd.Timestamp.now(tz="UTC") - last).total_seconds() / 3600.0
    return {"last_bar_utc": last.isoformat(), "age_hours": float(age),
            "stale": age > STALE_BAR_HOURS}


def market_likely_open(now: pd.Timestamp | None = None) -> bool:
    """GC trades nearly 24/5. Closed Friday 17:00 ET → Sunday 18:00 ET (CME).
    We approximate by checking US weekday & avoiding the maintenance gap.
    """
    now = now or pd.Timestamp.now(tz="UTC")
    et = now.tz_convert("America/New_York")
    wd = et.weekday()  # Mon=0 .. Sun=6
    h = et.hour
    if wd == 5:  # Saturday all day closed
        return False
    if wd == 4 and h >= 17:  # Friday after 5pm
        return False
    if wd == 6 and h < 18:  # Sunday before 6pm
        return False
    return True


def load_health() -> dict:
    if HEALTH_FILE.exists():
        return json.loads(HEALTH_FILE.read_text())
    return {}


def save_health(state: dict):
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(json.dumps(state, indent=2, default=str))


def daily_heartbeat_due() -> bool:
    """Return True if we haven't sent a heartbeat today (UTC)."""
    h = load_health()
    today = pd.Timestamp.now(tz="UTC").date().isoformat()
    return h.get("last_heartbeat_utc_date") != today


def record_heartbeat():
    h = load_health()
    h["last_heartbeat_utc_date"] = pd.Timestamp.now(tz="UTC").date().isoformat()
    save_health(h)


def maybe_send_heartbeat(force: bool = False):
    """Once per day, send a system-alive ping with key health stats."""
    from telegram_bot import send
    if not force and not daily_heartbeat_due():
        return False
    bf = bar_freshness()
    open_ = market_likely_open()
    msg = (f"💓 *heartbeat* {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
           f"  GC last bar: {bf['last_bar_utc'][:16]} "
           f"({bf['age_hours']:.1f}h old)  "
           f"{'⚠️ STALE' if bf['stale'] else '✅'}\n"
           f"  Market: {'OPEN' if open_ else 'CLOSED (weekend gap)'}")
    r = send(msg)
    if r.get("ok"):
        record_heartbeat()
        return True
    return False
