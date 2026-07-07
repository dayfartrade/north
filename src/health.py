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
    tmp = HEALTH_FILE.with_suffix(HEALTH_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    _atomic_replace_retry(tmp, HEALTH_FILE)


def _atomic_replace_retry(tmp: Path, target: Path, attempts: int = 5, delay: float = 0.02):
    """Windows os.replace race guard — retries when the target is briefly
    open by another process (e.g. API /health reader)."""
    import os, time
    last_err = None
    for _ in range(attempts):
        try:
            os.replace(tmp, target)
            return
        except PermissionError as e:
            last_err = e
            time.sleep(delay)
            delay *= 2
    raise last_err


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
    r = send(msg, audience="private")
    if r.get("ok"):
        record_heartbeat()
        return True
    return False


# ---- Dispatch-tick gap detection (watchdog) ----

GAP_ALERT_MINUTES = 90  # alert if previous tick was this many minutes ago


def record_orb_lag_defer(session: str, or_close_ts, lag_min: float) -> bool:
    """Track consecutive PLAN defers due to bar lag. Returns True if this is
    the 2nd+ consecutive defer for the same (session, or_close_ts) — caller
    should send a private escalation alert.

    Idempotent per (session, or_close_ts): once alerted, further defers on the
    same session/window won't re-alert.
    """
    h = load_health()
    defers = h.setdefault("orb_lag_defers", {})
    k = f"{session}|{pd.Timestamp(or_close_ts).isoformat()}"
    rec = defers.get(k, {"count": 0, "alerted": False,
                          "first_utc": pd.Timestamp.now(tz='UTC').isoformat()})
    rec["count"] += 1
    rec["last_lag_min"] = float(lag_min)
    rec["last_utc"] = pd.Timestamp.now(tz='UTC').isoformat()
    defers[k] = rec
    # Purge stale entries (older than 6h) so state doesn't grow
    cutoff = pd.Timestamp.now(tz='UTC') - timedelta(hours=6)
    for kk in list(defers.keys()):
        try:
            first = pd.Timestamp(defers[kk]["first_utc"])
            if first < cutoff:
                defers.pop(kk, None)
        except Exception:
            pass
    should_alert = rec["count"] >= 2 and not rec["alerted"]
    if should_alert:
        rec["alerted"] = True
    save_health(h)
    return should_alert


def clear_orb_lag_defers(session: str, or_close_ts):
    """Call on successful PLAN dispatch to reset defer counter for that window."""
    h = load_health()
    defers = h.get("orb_lag_defers", {})
    k = f"{session}|{pd.Timestamp(or_close_ts).isoformat()}"
    if k in defers:
        defers.pop(k, None)
        save_health(h)


def check_and_record_dispatch_tick():
    """Call at start of every dispatch.main().

    1. Reads previous tick timestamp from health.json
    2. If gap > GAP_ALERT_MINUTES AND market is now open, sends a PRIVATE
       'resumed after gap' alert so the owner knows the scheduler skipped
    3. Updates the timestamp to now

    No-ops on the very first tick (no previous timestamp).
    """
    from telegram_bot import send
    h = load_health()
    prev = h.get("last_dispatch_utc")
    now = pd.Timestamp.now(tz="UTC")
    h["last_dispatch_utc"] = now.isoformat()
    save_health(h)
    if not prev:
        return
    try:
        prev_ts = pd.Timestamp(prev)
        if prev_ts.tz is None:
            prev_ts = prev_ts.tz_localize("UTC")
    except Exception:
        return
    gap_min = (now - prev_ts).total_seconds() / 60
    if gap_min > GAP_ALERT_MINUTES and market_likely_open(now):
        try:
            send(f"⚠️ *dispatch gap detected*\n"
                 f"   Previous tick: {prev_ts.strftime('%Y-%m-%d %H:%M UTC')}\n"
                 f"   Gap: {gap_min:.0f} min (normal cadence is 30 min)\n"
                 f"   Scheduler skipped or was offline. Resumed now.",
                 audience="private")
        except Exception:
            pass
