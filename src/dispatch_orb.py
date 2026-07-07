"""ORB live dispatcher with v7-hybrid 4-box audit gate.

Runs every 30 min via Task Scheduler (called from dispatch.py).

4-BOX AUDIT GATE (applied per session at PLAN alert):
  Box 1  Signal     : run_orb_v7 per-session config (LON: OR<2*ATR filter +
                       fixed $13 stop; NY/ASIA: OR-range stop/target)
  Box 2  Stand-down : ±15min news, ±10min London-fix (auto via run_orb_v7,
                       cross-checked here for the plan-time announcement)
  Box 3  Funding    : Bitget XAUUSDT funding regime (P85 -> tilt context,
                       SOFT signal — surfaces in alert, does not gate)
  Box 4  Basis      : COMEX vs Bitget divergence > 0.5% -> data-sanity warn

State persisted in dispatch_state.json so we don't re-alert.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on, fetch_higher_tf_trend
from edge_session_orb_v7_final import SESSION_CONFIG, TP_MULT_DEFAULT
from stand_down import (stand_down_for_or_window, stand_down_for_entry,
                          _load_calendar, MAJOR_NEWS, NEWS_BUFFER_MINUTES,
                          LON_FIX_TIMES_LOCAL, FIX_BUFFER_MINUTES, _LON_TZ)
from mers_v3_peb import compute_atr
from telegram_bot import send
from alert_formatter import fmt_et
from alert_format_v2 import (plan_public as fmt_plan_public,
                              preview as fmt_preview,
                              pre as fmt_pre,
                              stand_down as fmt_stand_down,
                              filtered as fmt_filtered,
                              validation_suppressed as fmt_validation_suppressed,
                              data_lag_persisting as fmt_data_lag_persisting,
                              sizing_followup as fmt_sizing_followup)
from health import market_likely_open

OR_BARS = 6       # 30-min opening range on 5m
WATCH = 12        # 60-min breakout window
HOLD = 36         # v7.2.1: 3-hour time exit (was 2h; same win rate, +$32/trade)
TP_MULT = TP_MULT_DEFAULT
REQUIRE_TREND = True
BASIS_DIVERGE_PCT = 0.5  # flag if |basis| > this %
MAX_BAR_LAG_MIN = 15     # max age of latest 5m bar vs or_close_ts to trust OR levels
PLAN_WINDOW_BEFORE = 10  # min before or_close still allowed to fire (asymmetric)
PLAN_WINDOW_AFTER = 35   # min after or_close — wide enough for 14:30 backstop tick

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "dispatch_state.json"
VALIDATION_STATE_FILE = ROOT / "data" / "validation_state.json"
VALIDATION_STALE_DAYS = 14  # if last run older than this, warn (but don't kill-switch)
ALERTS_STREAM = ROOT / "data" / "alerts_stream.jsonl"


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
    """Windows os.replace race guard — see dispatch.py for full explanation."""
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


def session_emoji(name: str) -> str:
    return {"LON": "🇬🇧", "NY": "🇺🇸", "ASIA": "🇯🇵"}.get(name, "📍")


def _funding_context() -> str:
    """Box 3: funding regime context block (soft signal). Empty string on failure."""
    try:
        from funding_filter import get_current_regime
        r = get_current_regime()
        ann = r["current_rate"] * 1095  # 3x/day * 365
        if r["extreme"]:
            arrow = "▲ longs crowded — fade short" if r["regime_tilt"] < 0 \
                    else "▼ shorts crowded — fade long"
            return f"   💱 Funding {ann:+.1%} ann (extreme P{int(r['abs_percentile']*100)}) · {arrow}\n"
        # Suppress neutral funding line to reduce noise; only show when interesting
        return ""
    except Exception as e:
        return f"   💱 Funding ctx unavailable ({type(e).__name__})\n"


def _cot_context(direction_hint: str = "") -> str:
    """COT managed-money percentile context (soft signal).

    direction_hint: "UP"/"DOWN"/"FLAT" (from trend) to annotate alignment.
    Empty string on failure or no data.
    """
    try:
        from data_cot import latest_snapshot, refresh_cot
        snap = latest_snapshot()
        if not snap:
            # First-time: fetch
            refresh_cot()
            snap = latest_snapshot()
        if not snap:
            return ""
        pct = snap["pct_52w"]
        if pct != pct:  # NaN
            return ""
        pct_i = int(pct * 100)
        side = "net long" if snap["mm_net_long"] > 0 else "net short"
        tag = ""
        if pct_i >= 85:
            tag = " ▲ crowded long — fade-short bias"
        elif pct_i <= 15:
            tag = " ▼ crowded short — fade-long bias"
        return (f"   📑 COT {snap['report_date']}: managed money "
                f"{side} {abs(int(snap['mm_net_long'])):,} (P{pct_i} 52w){tag}\n")
    except Exception:
        return ""


def _volume_context(or_bars: pd.DataFrame, prior_bars: pd.DataFrame) -> tuple[str, dict]:
    """Box 6 (v7.2, audit-only): OR-window volume vs prior 20-bar avg.

    Returns (text_block, audit_dict). Filter NOT enforced — informational context
    only until n>=100 live trades validate a threshold. Backtest research on
    2026-07-07 (n=52) shows: ratio >= 1.2 -> 77% win OOS (vs 65% baseline);
    ratio < 0.8 -> lower confidence. Not gated because CIs still overlap.
    """
    try:
        or_vol = float(or_bars["volume"].mean()) if len(or_bars) else 0.0
        prior_vol = float(prior_bars["volume"].mean()) if len(prior_bars) else 0.0
        if prior_vol <= 0:
            return "", {"error": "no_prior_volume"}
        ratio = or_vol / prior_vol
        if ratio >= 1.5:
            tag = "🔊 high (research: 80% OOS win when ratio >= 1.2)"
        elif ratio >= 1.0:
            tag = "🔊 normal"
        elif ratio >= 0.7:
            tag = "🔉 low"
        else:
            tag = "🔈 very low (research: lower confidence when ratio < 0.8)"
        text = f"   📊 OR volume {ratio:.2f}x prior · {tag}\n"
        return text, {"or_window_vol": or_vol, "prior_20bar_vol": prior_vol,
                       "ratio": round(ratio, 3),
                       "as_of_utc": pd.Timestamp.now(tz='UTC').isoformat()}
    except Exception as e:
        _log(f"[orb] volume ctx exception: {type(e).__name__}: {e}")
        return "", {"error": type(e).__name__}


def _basis_context() -> str:
    """Box 4: basis sanity warning. Empty when basis is within threshold;
    logs to dispatch.log on failure so silent Box-4 unmonitoring is visible."""
    try:
        from basis_tracker import current_basis
        b = current_basis()
        if "error" in b:
            _log(f"[orb] basis unavailable: {b.get('error')}")
            return ""
        if abs(b["basis_pct"]) > BASIS_DIVERGE_PCT:
            return (f"   ⚠️ basis ${b['basis_dollars']:+.2f} ({b['basis_pct']:+.2f}%) "
                    f"— GC vs Bitget diverging\n")
        return ""
    except Exception as e:
        _log(f"[orb] basis ctx exception: {type(e).__name__}: {e}")
        return ""


def _upcoming_standdown(start_ts: pd.Timestamp, end_ts: pd.Timestamp,
                          cal: pd.DataFrame) -> list[str]:
    """Return human-readable list of stand-down windows that fall within
    [start_ts, end_ts]. Used by the PLAN alert so traders see when NOT to enter."""
    windows = []
    # News events in window
    if cal is not None and not cal.empty:
        relevant = cal[cal["event"].isin(MAJOR_NEWS)]
        for _, ev in relevant.iterrows():
            ev_ts = pd.Timestamp(ev["ts_utc"])
            if ev_ts.tz is None:
                ev_ts = ev_ts.tz_localize("UTC")
            buf = pd.Timedelta(minutes=NEWS_BUFFER_MINUTES)
            if (ev_ts + buf >= start_ts) and (ev_ts - buf <= end_ts):
                windows.append(f"news {ev['event']} {ev_ts.strftime('%H:%M')}UTC "
                                f"(±{NEWS_BUFFER_MINUTES}m)")
    # London fix windows in [start, end]
    for fix_t in LON_FIX_TIMES_LOCAL:
        # Check each date the watch window spans (rare to cross days, but be safe)
        for d_off in (0, 1):
            day = (start_ts.astimezone(_LON_TZ) + pd.Timedelta(days=d_off)).normalize()
            fix_dt_lon = day + pd.Timedelta(hours=fix_t.hour, minutes=fix_t.minute)
            fix_utc = fix_dt_lon.tz_convert("UTC")
            buf = pd.Timedelta(minutes=FIX_BUFFER_MINUTES)
            if (fix_utc + buf >= start_ts) and (fix_utc - buf <= end_ts):
                windows.append(f"LON fix {fix_t.strftime('%H:%M')}LT "
                                f"= {fix_utc.strftime('%H:%M')}UTC (±{FIX_BUFFER_MINUTES}m)")
    return windows


def _log(msg: str):
    """File log when invoked under pythonw (stdout discarded)."""
    import builtins
    fn = getattr(builtins, "_dispatch_log", None)
    if fn:
        fn(msg)
    else:
        print(msg)


def _safe_send(msg: str, sent: set, key: str, actions: list, action_tag: str,
                sess_name: str, open_ts: pd.Timestamp,
                audience: str = "public") -> bool:
    """Wrap send() so a Telegram failure still marks the key sent.

    This prevents duplicate-alert storms when Telegram glitches: at-most-once
    semantics with the cost of possibly missing the alert. We log the failure
    so it shows in dispatch output.
    """
    try:
        send(msg, audience=audience)
        sent.add(key)
        actions.append((action_tag, sess_name, open_ts))
        _log(f"[orb] SENT[{audience}] {action_tag} {sess_name} {open_ts}")
        return True
    except Exception as e:
        _log(f"[orb] send FAILED for {action_tag} {sess_name}: {type(e).__name__}: {e}")
        sent.add(key)  # don't retry — at-most-once
        actions.append((f"{action_tag}_send_failed", sess_name, open_ts))
        return False


POSTMORTEM_LOOKBACK_HOURS = 6
POSTMORTEM_MIN_AGE_MIN = 10  # let the tracker settle for 10 min after exit


def _publish_postmortems(sent: set, actions: list) -> None:
    """Scan the ORB forward log for closed trades that haven't yet had a
    post-mortem posted. Fires at most one per (session, entry_ts) key.

    Public post-mortem is R-framed (no per-account P&L). Silent if no
    eligible trades — safe to call every dispatch tick.
    """
    tracker_log = ROOT / "data" / "tracker" / "orb_forward_log.csv"
    if not tracker_log.exists():
        return
    try:
        import csv
        rows = []
        with open(tracker_log, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
    except Exception as e:
        _log(f"[orb] postmortem read failed: {type(e).__name__}: {e}")
        return
    if not rows:
        return

    now = pd.Timestamp.now(tz="UTC")
    cutoff_recent = now - pd.Timedelta(hours=POSTMORTEM_LOOKBACK_HOURS)
    cutoff_settle = now - pd.Timedelta(minutes=POSTMORTEM_MIN_AGE_MIN)

    from alert_format_v2 import trade_postmortem as fmt_postmortem

    for r in rows:
        if r.get("took_trade", "").strip().lower() not in ("true", "1"):
            continue
        exit_ts_str = (r.get("exit_ts") or "").strip()
        entry_ts_str = (r.get("entry_ts") or "").strip()
        if not exit_ts_str or not entry_ts_str:
            continue
        try:
            exit_ts = pd.Timestamp(exit_ts_str)
            entry_ts = pd.Timestamp(entry_ts_str)
            if exit_ts.tz is None:
                exit_ts = exit_ts.tz_localize("UTC")
            if entry_ts.tz is None:
                entry_ts = entry_ts.tz_localize("UTC")
        except Exception:
            continue
        # Window: exit older than 10min (settle), newer than 6h (don't backfill ancient)
        if exit_ts > cutoff_settle or exit_ts < cutoff_recent:
            continue

        sess_name = r.get("session", "")
        key = f"postmortem|{sess_name}|{entry_ts.isoformat()}"
        if key in sent:
            continue

        try:
            entry_price = float(r["entry_price"])
            exit_price = float(r["exit_price"])
            stop_price = float(r["stop_price"])
            target_price = float(r["target_price"])
            direction = int(float(r["direction"]))
        except Exception as e:
            _log(f"[orb] postmortem skip {key}: bad field ({type(e).__name__})")
            continue

        # R-multiple: signed distance from entry to exit / stop-distance
        stop_dist = abs(entry_price - stop_price)
        if stop_dist <= 0:
            continue
        if direction > 0:
            r_mult = (exit_price - entry_price) / stop_dist
        else:
            r_mult = (entry_price - exit_price) / stop_dist

        mae_r = None; mfe_r = None
        try:
            mae_d = float(r.get("mae_price_distance") or "nan")
            mfe_d = float(r.get("mfe_price_distance") or "nan")
            if pd.notna(mae_d):
                mae_r = -abs(mae_d) / stop_dist  # MAE is loss-side, negative
            if pd.notna(mfe_d):
                mfe_r = abs(mfe_d) / stop_dist  # MFE is gain-side, positive
        except Exception:
            pass

        try:
            from strategy_version import STRATEGY_VERSION
            version = STRATEGY_VERSION
        except Exception:
            version = "v7"

        payload = {
            "session": sess_name, "version": version,
            "direction": direction,
            "entry_price": entry_price, "exit_price": exit_price,
            "stop_price": stop_price, "target_price": target_price,
            "entry_ts": entry_ts, "exit_ts": exit_ts,
            "r_multiple": r_mult,
            "mae_r": mae_r, "mfe_r": mfe_r,
        }
        msg = fmt_postmortem(payload)
        _safe_send(msg, sent, key, actions, "orb_postmortem", sess_name,
                    entry_ts, audience="public")


def _validation_gate() -> tuple[bool, str]:
    """H3 kill-switch: check latest weekly_validation verdict.

    Returns (allow_dispatch, reason). Bootstrap grace: if no validation file
    exists yet (first week post-launch), allow but note it.
    """
    if not VALIDATION_STATE_FILE.exists():
        return True, "no validation state yet (bootstrap grace)"
    try:
        v = json.loads(VALIDATION_STATE_FILE.read_text())
    except Exception as e:
        return True, f"validation file unreadable ({type(e).__name__}); allowing"
    if v.get("verdict") == "NOT READY":
        return False, (f"weekly validation verdict=NOT READY (n={v.get('n_trades')}, "
                       f"tag={v.get('size_tag')}, last_run={v.get('last_run_utc','?')})")
    return True, "validation OK"


def dispatch_orb_alerts():
    state = load_state()
    sent = set(state.get("sent", []))
    actions = []

    if not market_likely_open():
        return actions

    # H3 kill-switch: don't dispatch if edge has been marked NOT READY
    allow, reason = _validation_gate()
    if not allow:
        _log(f"[orb] DISPATCH SUPPRESSED: {reason}")
        # Alert once per calendar day
        day_key = f"validation_killswitch|{pd.Timestamp.now(tz='UTC').date().isoformat()}"
        if day_key not in sent:
            try:
                send(fmt_validation_suppressed({"reason": reason}), audience="private")
            except Exception:
                pass
            sent.add(day_key)
            state["sent"] = sorted(sent)
            save_state(state)
        return actions

    bars5 = gc_load("5m").sort_index()
    if bars5.index.tz is None: bars5.index = bars5.index.tz_localize("UTC")
    if bars5.empty:
        return actions
    atr = compute_atr(bars5, 20)
    trend_slope = fetch_higher_tf_trend(bars5)
    cal = _load_calendar()

    now = pd.Timestamp.now(tz="UTC")
    today = now.date()

    for sess_name in SESSIONS_LOCAL:
        cfg = SESSION_CONFIG.get(sess_name, SESSION_CONFIG["NY"])
        sess_t = session_utc_time_on(today, sess_name)
        open_ts = pd.Timestamp.combine(today, sess_t).tz_localize("UTC")
        or_close_ts = open_ts + pd.Timedelta(minutes=5 * OR_BARS)

        # ---- PREVIEW alert: T-30 to T-15 min before session open (pre-session call)
        if pd.Timedelta(minutes=15) <= (open_ts - now) <= pd.Timedelta(minutes=45):
            k = f"ORB|{open_ts.isoformat()}|{sess_name}|preview"
            if k not in sent:
                cur_slope = float(trend_slope.iloc[-1]) if len(trend_slope) else float("nan")
                cur_atr = float(atr.iloc[-1]) if len(atr) else float("nan")
                trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
                # Heads-up: upcoming entry stand-down windows during OR+watch
                watch_end = open_ts + pd.Timedelta(minutes=5 * (OR_BARS + WATCH))
                sd_windows = _upcoming_standdown(open_ts, watch_end, cal)
                sd_line = ("   ⛔ Don't enter during: " + " · ".join(sd_windows) + "\n"
                           if sd_windows else "")
                geom_summary = ("LON filter OR<2×ATR + fixed $13 stop, 1.5R target"
                                if cfg.get("use_or_filter") else
                                "stop=OR-range, target=1.5×OR")
                msg = fmt_preview({
                    "session": sess_name,
                    "open_ts": open_ts,
                    "or_bars_min": OR_BARS * 5,
                    "trend": trend,
                    "slope": cur_slope,
                    "atr": cur_atr,
                    "geom_summary": geom_summary,
                    "sd_windows": sd_windows,
                    "funding_line": _funding_context().strip(),
                    "basis_line": _basis_context().strip(),
                })
                _safe_send(msg, sent, k, actions, "orb_preview", sess_name, open_ts, audience="public")

        # ---- PRE alert: ~15 min before OR closes
        if pd.Timedelta(minutes=5) <= (or_close_ts - now) <= pd.Timedelta(minutes=30):
            k = f"ORB|{open_ts.isoformat()}|{sess_name}|pre"
            if k not in sent:
                cur_slope = float(trend_slope.iloc[-1]) if len(trend_slope) else float("nan")
                trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
                msg = fmt_pre({
                    "session": sess_name,
                    "open_ts": open_ts,
                    "or_close_ts": or_close_ts,
                    "trend": trend,
                    "slope": cur_slope,
                })
                _safe_send(msg, sent, k, actions, "orb_pre", sess_name, open_ts, audience="public")

        # ---- PLAN alert: OR just closed. Asymmetric window: small grace
        # before or_close (catches early dispatch ticks), wide buffer after
        # so a deferred 14:00 tick gets a second chance at the 14:30 tick
        # with fresh bars.
        if (pd.Timedelta(minutes=-PLAN_WINDOW_BEFORE) <= (now - or_close_ts)
              <= pd.Timedelta(minutes=PLAN_WINDOW_AFTER)):
            k = f"ORB|{open_ts.isoformat()}|{sess_name}|plan"
            if k not in sent:
                # ----- Box 2: OR-window news stand-down (skip ONLY if OR bars overlap
                # a top-tier news release — fix windows do NOT invalidate OR levels,
                # they're handled by per-entry stand-down advisory below).
                news_overlap = False
                news_reason = ""
                if cal is not None and not cal.empty:
                    relevant = cal[cal["event"].isin(MAJOR_NEWS)]
                    for _, ev in relevant.iterrows():
                        ev_ts = pd.Timestamp(ev["ts_utc"])
                        if ev_ts.tz is None: ev_ts = ev_ts.tz_localize("UTC")
                        buf = pd.Timedelta(minutes=NEWS_BUFFER_MINUTES)
                        if (ev_ts + buf >= open_ts) and (ev_ts - buf <= or_close_ts):
                            news_overlap = True
                            news_reason = f"{ev['event']}@{ev_ts.strftime('%H:%M')}UTC"
                            break
                if news_overlap:
                    msg = fmt_stand_down({"session": sess_name, "news_reason": news_reason})
                    _safe_send(msg, sent, k, actions, "orb_standdown", sess_name, open_ts, audience="public")
                    continue

                # Find or_close bar
                if or_close_ts in bars5.index:
                    or_close_idx = bars5.index.get_loc(or_close_ts)
                else:
                    mask = bars5.index <= or_close_ts
                    if not mask.any():
                        continue
                    latest_bar_ts = bars5.index[mask][-1]
                    lag_min = (or_close_ts - latest_bar_ts).total_seconds() / 60
                    if lag_min > MAX_BAR_LAG_MIN:
                        # Data lag too large — bars don't cover the OR window.
                        # Skip THIS tick (don't dedup) so a fresher tick can retry.
                        _log(f"[orb] {sess_name} PLAN DEFERRED: latest bar "
                             f"{latest_bar_ts} is {lag_min:.0f}min before "
                             f"or_close_ts {or_close_ts} (lag > {MAX_BAR_LAG_MIN}min)")
                        # Escalate on 2nd+ consecutive defer for this session/window
                        # (root cause of NFP 2026-07-03 3.5-day silent outage)
                        from health import record_orb_lag_defer
                        if record_orb_lag_defer(sess_name, or_close_ts, lag_min):
                            from telegram_bot import send as _tg_send
                            _tg_send(fmt_data_lag_persisting({
                                "session": sess_name,
                                "or_close_ts": or_close_ts,
                                "lag_min": lag_min,
                                "limit_min": MAX_BAR_LAG_MIN,
                            }), audience="private")
                        continue
                    or_close_idx = bars5.index.get_loc(latest_bar_ts)
                or_start_idx = max(0, or_close_idx - OR_BARS + 1)
                or_window = bars5.iloc[or_start_idx: or_close_idx + 1]
                or_high = float(or_window["high"].max())
                or_low = float(or_window["low"].min())
                or_range = or_high - or_low
                if or_range <= 0:
                    continue
                cur_slope = float(trend_slope.iloc[or_close_idx])
                cur_atr = float(atr.iloc[or_close_idx])

                # ----- Box 1: per-session OR-vs-ATR filter (LON only per SESSION_CONFIG)
                if cfg.get("use_or_filter", False):
                    or_max = cfg.get("or_vs_atr_max", 2.0) * cur_atr
                    if or_range > or_max:
                        msg = fmt_filtered({
                            "session": sess_name,
                            "or_range": or_range,
                            "or_atr_mult": cfg["or_vs_atr_max"],
                            "atr_limit": or_max,
                        })
                        _safe_send(msg, sent, k, actions, "orb_filtered", sess_name, open_ts, audience="public")
                        continue

                # ----- Geometry per session config
                if cfg.get("stop_mode") == "fixed":
                    stop_dist = float(cfg["fixed_stop_price"])
                    geom_tag = f"${stop_dist:.0f} fixed"
                else:
                    stop_dist = or_range
                    geom_tag = f"${stop_dist:.2f} (=OR range)"
                if cfg.get("target_mode") == "stop_x_tp":
                    target_dist = TP_MULT * stop_dist
                else:
                    target_dist = TP_MULT * or_range
                rr_ratio = target_dist / stop_dist if stop_dist > 0 else 0

                trend = "UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"
                dir_hint = ("LONG only (trend up)" if cur_slope > 0
                            else "SHORT only (trend down)" if cur_slope < 0
                            else "SKIP — trend flat")
                stop_long = or_high - stop_dist
                target_long = or_high + target_dist
                stop_short = or_low + stop_dist
                target_short = or_low - target_dist

                # ----- Position sizing
                from position_sizing import recommend, SizingConfig, format_for_alert
                from config import load as load_config
                lcfg = load_config()
                try:
                    import yfinance as yf
                    gld_p = float(yf.Ticker("GLD").history(period="1d", interval="1h")["Close"].iloc[-1])
                except Exception:
                    gld_p = None
                sz = recommend(
                    stop_dist_per_oz=stop_dist,
                    gld_price=gld_p,
                    cfg=SizingConfig(mode=lcfg["sizing_mode"],
                                      account_equity=lcfg["account_equity"],
                                      risk_pct=lcfg["risk_pct_per_trade"],
                                      fixed_risk_dollars=lcfg["fixed_risk_dollars"]),
                )
                sizing_block = format_for_alert(sz)

                # ----- Box 3, 4, 5, 6 context blocks (all soft signals)
                fund_block = _funding_context()
                basis_block = _basis_context()
                cot_block = _cot_context()
                # Box 6 (v7.2 informational): OR-window volume ratio
                # 20 bars prior to OR open, 6 bars of OR window
                prior_slice = bars5.iloc[max(0, or_close_idx-25):or_close_idx-5]
                or_slice = bars5.iloc[or_close_idx-5:or_close_idx+1]
                vol_block, vol_audit = _volume_context(or_slice, prior_slice)

                # Compute upcoming entry stand-down windows during watch
                watch_end = or_close_ts + pd.Timedelta(minutes=5 * WATCH)
                sd_windows = _upcoming_standdown(or_close_ts, watch_end, cal)

                # PUBLIC version: levels, direction, stand-down, market context.
                # No sizing block — subscribers have different equity.
                from strategy_version import STRATEGY_VERSION
                public_msg = fmt_plan_public({
                    "session": sess_name,
                    "version": STRATEGY_VERSION,
                    "or_open_ts": open_ts,
                    "or_close_ts": or_close_ts,
                    "or_high": or_high,
                    "or_low": or_low,
                    "or_range": or_range,
                    "long_entry": or_high,
                    "long_stop": stop_long,
                    "long_target": target_long,
                    "short_entry": or_low,
                    "short_stop": stop_short,
                    "short_target": target_short,
                    "stop_dist": stop_dist,
                    "target_dist": target_dist,
                    "rr_ratio": rr_ratio,
                    "trend": trend,
                    "dir_hint": dir_hint,
                    "watch_end_ts": watch_end,
                    "hold_hours": HOLD * 5 / 60.0,
                    "funding_line": fund_block.strip(),
                    "basis_line": basis_block.strip(),
                    "cot_line": cot_block.strip(),
                    "vol_line": vol_block.strip(),
                    "sd_windows": sd_windows,
                })
                _safe_send(public_msg, sent, k, actions, "orb_plan", sess_name,
                            open_ts, audience="public")
                # PLAN dispatched — reset any lag-defer escalation counter for this window
                from health import clear_orb_lag_defers
                clear_orb_lag_defers(sess_name, or_close_ts)
                # Structured emit for API layer (data/alerts_stream.jsonl).
                # One JSONL row per PLAN; single-write append is atomic for < PIPE_BUF.
                # Each audit sub-block carries its own as_of_utc so the website
                # can render honest freshness (COT is weekly, funding is 8-hourly).
                try:
                    watch_end = or_close_ts + pd.Timedelta(minutes=WATCH * 5)
                    now_iso = pd.Timestamp.now(tz='UTC').isoformat()
                    # Build audit sub-blocks (each with its own as_of_utc)
                    audit = {"stand_down_windows": list(sd_windows) if sd_windows else []}
                    try:
                        from funding_filter import get_current_regime
                        r = get_current_regime()
                        audit["funding"] = {
                            "annualized_pct": round(r["current_rate"] * 1095 * 100, 3),
                            "regime": ("extreme_long" if r["extreme"] and r["regime_tilt"] < 0
                                       else "extreme_short" if r["extreme"] and r["regime_tilt"] > 0
                                       else "neutral"),
                            "abs_percentile": round(r.get("abs_percentile", 0), 3),
                            "as_of_utc": r.get("as_of_utc") or now_iso,
                        }
                    except Exception as e:
                        audit["funding"] = {"error": type(e).__name__, "as_of_utc": now_iso}
                    try:
                        from basis_tracker import current_basis
                        b = current_basis()
                        if "error" not in b:
                            audit["basis"] = {
                                "dollars": round(float(b["basis_dollars"]), 2),
                                "pct": round(float(b["basis_pct"]), 4),
                                "as_of_utc": pd.Timestamp(b["comex_gc_ts"]).isoformat(),
                            }
                        else:
                            audit["basis"] = {"error": b["error"], "as_of_utc": now_iso}
                    except Exception as e:
                        audit["basis"] = {"error": type(e).__name__, "as_of_utc": now_iso}
                    try:
                        from data_cot import latest_snapshot
                        cot = latest_snapshot()
                        if cot:
                            audit["cot"] = {
                                "mm_net_long": int(cot["mm_net_long"]),
                                "pct_52w": round(float(cot["pct_52w"]), 3),
                                "as_of_utc": pd.Timestamp(cot["report_date"]).isoformat(),
                            }
                    except Exception as e:
                        audit["cot"] = {"error": type(e).__name__, "as_of_utc": now_iso}
                    audit["volume"] = vol_audit

                    # Strategy-version stamp (installed 2026-07-07 per Janus Q3A)
                    try:
                        from strategy_version import strategy_stamp
                        stamp = strategy_stamp()
                    except Exception:
                        stamp = {"strategy_version": "unknown", "filter_config_hash": "unknown"}

                    row = {
                        "ts_sent_utc": now_iso,
                        "kind": "orb_plan",
                        "session": sess_name,
                        **stamp,
                        "or_open_utc": open_ts.isoformat(),
                        "or_close_utc": or_close_ts.isoformat(),
                        "or_high": float(or_high),
                        "or_low": float(or_low),
                        "or_range": float(or_range),
                        "stop_dist": float(stop_dist),
                        "target_dist": float(target_dist),
                        "rr_ratio": float(rr_ratio),
                        "long":  {"entry": float(or_high), "stop": float(stop_long),
                                  "target": float(target_long)},
                        "short": {"entry": float(or_low),  "stop": float(stop_short),
                                  "target": float(target_short)},
                        "trend": ("UP" if cur_slope > 0 else "DOWN" if cur_slope < 0 else "FLAT"),
                        "trend_slope": float(cur_slope),
                        "watch_expires_utc": watch_end.isoformat(),
                        "max_hold_min": HOLD * 5,
                        "audit": audit,
                    }
                    ALERTS_STREAM.parent.mkdir(parents=True, exist_ok=True)
                    with open(ALERTS_STREAM, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row, default=str) + "\n")

                    # Shadow log: evaluate REGISTERED candidate filters against the
                    # same features and log would-have-skipped decisions. Zero live
                    # impact; used for post-hoc analysis at n>=100 shadow decisions.
                    try:
                        from shadow_log import record_shadow
                        features = {
                            "or_range": float(or_range),
                            "or_atr_ratio": float(or_range / cur_atr) if cur_atr else None,
                            "or_win_vol_ratio": (vol_audit.get("ratio")
                                                  if isinstance(vol_audit, dict) else None),
                            "trend_slope": float(cur_slope),
                            "funding_pct": (audit.get("funding", {}).get("annualized_pct")
                                            if isinstance(audit.get("funding"), dict) else None),
                            "basis_pct": (audit.get("basis", {}).get("pct")
                                          if isinstance(audit.get("basis"), dict) else None),
                            "cot_pct_52w": (audit.get("cot", {}).get("pct_52w")
                                            if isinstance(audit.get("cot"), dict) else None),
                        }
                        plan_context = {
                            "session": sess_name,
                            "or_open_utc": open_ts.isoformat(),
                            "or_close_utc": or_close_ts.isoformat(),
                            "or_high": float(or_high),
                            "or_low": float(or_low),
                            **stamp,
                        }
                        record_shadow(plan_context, features)
                    except Exception as e:
                        _log(f"[orb] shadow_log emit failed: {type(e).__name__}: {e}")
                except Exception as e:
                    _log(f"[orb] alerts_stream emit failed: {type(e).__name__}: {e}")
                # PRIVATE sizing follow-up (account-specific; never broadcast)
                try:
                    send(fmt_sizing_followup({"session": sess_name, "sizing_block": sizing_block}),
                         audience="private")
                except Exception as e:
                    _log(f"[orb] private sizing send failed: {type(e).__name__}: {e}")

    # Post-mortem scanner: publish recap for any recently-closed trades
    # (silent when no eligible trades — safe every tick)
    try:
        _publish_postmortems(sent, actions)
    except Exception as e:
        _log(f"[orb] postmortem scanner exception: {type(e).__name__}: {e}")

    state["sent"] = sorted(sent)
    save_state(state)
    return actions


if __name__ == "__main__":
    a = dispatch_orb_alerts()
    if not a:
        print(f"[orb] {pd.Timestamp.now(tz='UTC').isoformat(timespec='minutes')}  no ORB alerts due.")
    else:
        for action, sess, ts in a:
            print(f"[orb] {action} {sess} {ts}")
