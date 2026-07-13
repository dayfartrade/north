"""Smart alert dispatcher.

NOTE: scheduled via pythonw.exe which discards stdout. Every dispatch
tick is also appended to data/dispatch.log so post-mortems are possible.


Designed to be run periodically (e.g., every 30 min via Task Scheduler).
For each top-tier event in the next 7 days, it emits Telegram alerts at the
right moments:

  T-24h  : "Heads-up: <event> tomorrow"
  T-1h   : "Event in 1 hour. Current trend filter says LONG/SHORT only."
  Event  : (event happens; we passively watch the bar)
  Event+1h close : "Plan posted" — concrete H/L levels and buy/sell stop prices
  Event+1h+watch bars : (entry monitoring done in track_results.py)
  Event+1h+watch+max_hold : Position resolved (logged in tracker)

State persistence: data/dispatch_state.json holds (event_ts, alert_type) pairs
that have already been sent.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v3_peb import compute_atr
from mers_v5 import TOP_EVENTS_V5, TREND_N, B_ATR, dedupe_co_released
from telegram_bot import send
from alert_formatter import upcoming_alert, event_emoji, fmt_et


ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "dispatch_state.json"
LOG_FILE = ROOT / "data" / "dispatch.log"


def _log(msg: str):
    """Append to dispatch.log AND print (print disappears under pythonw)."""
    ts = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
    line = f"{ts}  {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# Make _log available to dispatch_orb without circular import
import builtins
builtins._dispatch_log = _log


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"sent": []}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    _atomic_replace_retry(tmp, STATE_FILE)


def _atomic_replace_retry(tmp: Path, target: Path, attempts: int = 5, delay: float = 0.02):
    """os.replace with retry — Windows raises PermissionError if another process
    (e.g. the API's read) has the target file open during the swap.
    Retries with brief backoff; POSIX succeeds on first try."""
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


def key(ev_ts: pd.Timestamp, ev_type: str, alert: str) -> str:
    return f"{pd.Timestamp(ev_ts).isoformat()}|{ev_type}|{alert}"


def _get_gld_price() -> float | None:
    """Best-effort fetch of latest GLD price for sizing recommendation."""
    try:
        import yfinance as yf
        h = yf.Ticker("GLD").history(period="1d", interval="1h")
        if not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return None


def main():
    state = load_state()
    sent = set(state.get("sent", []))

    # Watchdog: detect scheduler gap before anything else
    from health import (bar_freshness, market_likely_open, maybe_send_heartbeat,
                         check_and_record_dispatch_tick)
    check_and_record_dispatch_tick()
    last_err = None
    for attempt in (1, 2, 3):
        try:
            from data_gc import snapshot_all as gc_snapshot
            gc_snapshot(verbose=False)
            last_err = None
            break
        except Exception as e:
            last_err = e
            print(f"[dispatch] refresh attempt {attempt}/3 failed: {e}")
            import time; time.sleep(5 * attempt)
    if last_err is not None:
        print(f"[dispatch] WARNING: all refresh attempts failed; using stored data")

    # Stale-data gate: refuse to send actionable alerts on >4h-old bars
    bf = bar_freshness()
    if bf["stale"] and market_likely_open():
        print(f"[dispatch] STALE bars ({bf['age_hours']:.1f}h old) during market hours — "
              f"only heartbeat will be sent.")
        send(f"⚠️ *stale data warning*: latest GC bar is "
             f"{bf['age_hours']:.1f}h old (UTC {bf['last_bar_utc'][:16]}). "
             f"Suppressing trade plan alerts until refreshed.")
        maybe_send_heartbeat(force=False)
        return

    # Daily heartbeat (once per UTC day)
    maybe_send_heartbeat(force=False)

    bars = gc_load("60m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=TREND_N, adjust=False).mean()
    slope = ema.diff(5)

    cal = dedupe_co_released(build_all())
    now = pd.Timestamp.now(tz="UTC")
    horizon = now + pd.Timedelta(days=7)
    upc = cal[(cal["event"].isin(TOP_EVENTS_V5))
              & (cal["ts_utc"] >= now - pd.Timedelta(hours=2))
              & (cal["ts_utc"] <= horizon)].sort_values("ts_utc")

    cur_atr = float(atr.iloc[-1])
    cur_slope = float(slope.iloc[-1])

    actions = []
    for _, ev in upc.iterrows():
        ts = pd.Timestamp(ev["ts_utc"])
        ev_type = ev["event"]
        delta = ts - now

        # T-24h alert
        if pd.Timedelta(hours=20) <= delta <= pd.Timedelta(hours=28):
            k = key(ts, ev_type, "T-24h")
            if k not in sent:
                msg = (f"📅 *Heads-up — {ev_type} in 24h*\n"
                       f"   {fmt_et(ts)}\n"
                       f"   Current trend filter (EMA{TREND_N} slope): "
                       f"{cur_slope:+.2f} → "
                       f"{'LONG' if cur_slope > 0 else 'SHORT' if cur_slope < 0 else 'FLAT'}")
                send(msg)
                sent.add(k)
                actions.append(("T-24h", ev_type, ts))

        # T-1h alert
        if pd.Timedelta(minutes=30) <= delta <= pd.Timedelta(minutes=90):
            k = key(ts, ev_type, "T-1h")
            if k not in sent:
                dir_s = "LONG breakouts only" if cur_slope > 0 else \
                        "SHORT breakouts only" if cur_slope < 0 else "SKIP (trend flat)"
                msg = (f"⚠️ *{ev_type} in 1 hour*  {event_emoji(ev_type)}\n"
                       f"   Release: {fmt_et(ts)}\n"
                       f"   Pre-event ATR(20): ${cur_atr:.2f}\n"
                       f"   Buffer (0.10·ATR): ${B_ATR * cur_atr:.2f}\n"
                       f"   Trend filter: *{dir_s}*")
                send(msg)
                sent.add(k)
                actions.append(("T-1h", ev_type, ts))

        # Event-bar close (~1h after release for hourly cadence).
        # Wide window (45 min) so a late scheduler tick still catches it; state file dedupes.
        bar_close = ts + pd.Timedelta(hours=1)
        if pd.Timedelta(minutes=-30) <= (bar_close - now) <= pd.Timedelta(minutes=30):
            k = key(ts, ev_type, "plan")
            if k not in sent:
                # Find the event bar
                mask = (bars.index <= ts) & (bars.index + pd.Timedelta(hours=1) > ts)
                matches = bars.index[mask]
                if len(matches):
                    ev_bar = bars.loc[matches[-1]]
                    H, L = float(ev_bar["high"]), float(ev_bar["low"])
                    rng = H - L
                    buf = B_ATR * cur_atr
                    dir_s = "LONG only" if cur_slope > 0 else "SHORT only" if cur_slope < 0 else "SKIP"
                    long_trig = H + buf
                    short_trig = L - buf
                    stop_long = long_trig - rng
                    target_long = long_trig + 2*rng
                    stop_short = short_trig + rng
                    target_short = short_trig - 2*rng

                    # Position sizing
                    from position_sizing import recommend, SizingConfig, format_for_alert
                    from config import load as load_config
                    cfg = load_config()
                    sz = recommend(
                        stop_dist_per_oz=rng,  # stop distance per oz = event-bar range
                        gld_price=_get_gld_price(),
                        cfg=SizingConfig(
                            mode=cfg["sizing_mode"],
                            account_equity=cfg["account_equity"],
                            risk_pct=cfg["risk_pct_per_trade"],
                            fixed_risk_dollars=cfg["fixed_risk_dollars"],
                        ),
                    )
                    sizing_block = format_for_alert(sz)

                    msg = (f"📊 *PLAN — {ev_type}* (event bar closed)\n"
                           f"   H = *${H:,.2f}*  ·  L = *${L:,.2f}*  ·  range ${rng:.2f}\n"
                           f"   Buffer: ${buf:.2f}\n\n"
                           f"   ↗️ LONG: buy-stop *${long_trig:,.2f}*  "
                           f"stop ${stop_long:,.2f}  tgt ${target_long:,.2f}\n"
                           f"   ↘️ SHORT: sell-stop *${short_trig:,.2f}*  "
                           f"stop ${stop_short:,.2f}  tgt ${target_short:,.2f}\n\n"
                           f"   Trend filter: *{dir_s}*\n"
                           f"   Cancel both after 2 bars if neither triggers.\n"
                           f"   Time exit: 6 bars max after entry.\n\n"
                           f"{sizing_block}")
                    send(msg)
                    sent.add(k)
                    actions.append(("plan", ev_type, ts))

    state["sent"] = sorted(sent)
    save_state(state)

    # ALSO dispatch session ORB signals (higher-frequency edge)
    try:
        from dispatch_orb import dispatch_orb_alerts
        orb_actions = dispatch_orb_alerts()
        actions.extend(orb_actions)
    except Exception as e:
        print(f"[dispatch] ORB sub-dispatch failed: {e}")

    # Shadow tracker (Path Q): record what strategy would have decided.
    # Idempotent, side-effect-only writes to data/shadow_equity_since_halt.jsonl.
    # Safe regardless of kill-switch state; useful data during halted period.
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        from shadow_orb_tracker import track_shadow_decisions
        _n_shadow = track_shadow_decisions()
        if _n_shadow:
            print(f"[dispatch] shadow_tracker recorded {_n_shadow} decision(s)")
    except Exception as e:
        print(f"[dispatch] shadow_tracker failed: {type(e).__name__}: {e}")

    # Shadow outcome resolver (Path Q): scan bars post-entry to resolve
    # target/stop/timeout for pending shadow entries. Idempotent, writes
    # updated JSONL via atomic tmp+rename.
    try:
        from shadow_outcome_resolver import resolve_outcomes
        _n_resolved, _n_pending = resolve_outcomes()
        if _n_resolved:
            print(f"[dispatch] shadow_resolver resolved {_n_resolved} (pending {_n_pending})")
    except Exception as e:
        print(f"[dispatch] shadow_resolver failed: {type(e).__name__}: {e}")

    # Halt monitor: DD + SPRT verdict. Advisory-only — kill switch (H3) is the
    # actual gate; this fires a private Telegram alert on verdict transitions
    # so the operator sees state changes without manually running the script.
    try:
        from halt_monitor import main as _halt_main
        _halt_main()  # writes data/halt_state.json + alerts on transitions
    except Exception as e:
        print(f"[dispatch] halt_monitor failed: {type(e).__name__}: {e}")

    # Daily brief — 1 fixed publication per UTC day at 22:00
    try:
        from daily_brief import maybe_publish_daily_brief
        if maybe_publish_daily_brief():
            actions.append(("daily_brief", "UTC", now))
    except Exception as e:
        print(f"[dispatch] daily_brief failed: {e}")

    # Weekly validation — private only, Sun 22:00 UTC
    try:
        from weekly_validation import maybe_publish_weekly_validation
        if maybe_publish_weekly_validation():
            actions.append(("weekly_validation", "UTC", now))
    except Exception as e:
        print(f"[dispatch] weekly_validation failed: {e}")

    if not actions:
        _log(f"[dispatch] no alerts due.")
    else:
        for item in actions:
            kind, ev, ts = item[0], item[1], item[2]
            _log(f"[dispatch] action={kind} ev={ev} ts={ts}")


if __name__ == "__main__":
    main()
