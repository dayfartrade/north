"""Refresh site JSON payloads for the active week.

Emits the following files consumed by the NORTH site (Rook):

  1. site/data/far_weekly_current.json - adds fields on non-FLAT weeks:
       live_pnl_pct        - trade P&L (positive = winning for current
                             direction; SHORT with falling gold reads +).
       live_updated_utc    - refresh timestamp.
       primary_risk        - {sentence, severity: high|med|low, trigger}.
     On FLAT weeks live_pnl_pct is absent; primary_risk is still emitted
     with a FLAT-specific sentence + severity=low + trigger=null.

  2. site/data/far_weekly_price_series.json - hourly OHLC for the active
     week window (week_of Monday 00:00 UTC through week_end Friday 21:00
     UTC), resampled from Dukascopy XAUUSD 5m. Envelope matches the
     pattern used by far_weekly_history.json so the client can assert
     the series matches the active week before rendering:
       { "week_of": "YYYY-MM-DD", "week_end": "YYYY-MM-DD",
         "series": [ { "time_utc": <int epoch seconds>, "open": float,
                       "high": float, "low": float, "close": float }, ... ] }
     time_utc is Unix epoch seconds so lightweight-charts consumes it
     directly.

  3. site/data/far_daily_briefs.json - one entry per weekday of the
     active week on non-FLAT weeks; empty array on FLAT weeks. Fields:
       { date, openPnlPct, distanceStopAtr,
         gates: [{ name, value, ok }],  # M20/M60/MA/RY
         event: { name, timeUtc, impact } | null,
         commentary: str }
     Gates use "confirms active direction" semantics: ok=true means the
     raw metric agrees with the week's direction. Future days have
     openPnlPct=null, distanceStopAtr=null; today uses current spot.

Runs both from the weekly publisher (Sunday 22 UTC seeds the files
before the week starts) and from the daily-brief workflow (Mon-Fri
12 UTC intraweek refresh).

Usage:
    python scripts/north_site_refresh.py
    python scripts/north_site_refresh.py --dry-run
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

CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"
SITE_CURRENT = ROOT / "site" / "data" / "far_weekly_current.json"
SITE_PRICE_SERIES = ROOT / "site" / "data" / "far_weekly_price_series.json"
SITE_DAILY_BRIEFS = ROOT / "site" / "data" / "far_daily_briefs.json"
XAUUSD_5M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"
CALENDAR_CSV = ROOT / "data" / "calendar" / "events.csv"

_spec = importlib.util.spec_from_file_location(
    "far_backtest", str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far_backtest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(far_backtest)

EVENT_IMPACT = {
    "FOMC": "high", "NFP": "high", "CPI": "high",
    "PPI": "med", "RETAIL": "med", "UNRATE": "med",
    "CLAIMS": "low",
}
IMPACT_RANK = {"high": 3, "med": 2, "low": 1}


def load_active_call() -> dict | None:
    if not CALLS_LOG.exists():
        return None
    with open(CALLS_LOG) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    for row in reversed(rows):
        if row.get("type") == "call" and row.get("outcome") is None:
            return row
    return None


def load_week_bars(week_of: str, week_end: str) -> pd.DataFrame:
    if not XAUUSD_5M.exists():
        return pd.DataFrame()
    start = pd.Timestamp(week_of, tz="UTC")
    end = pd.Timestamp(week_end, tz="UTC") + pd.Timedelta(hours=21)
    df = pd.read_csv(XAUUSD_5M, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df[(df["ts"] >= start) & (df["ts"] <= end)].sort_values("ts")
    return df.reset_index(drop=True)


def resample_hourly(bars: pd.DataFrame) -> list[dict]:
    if bars.empty:
        return []
    idx = bars.set_index("ts")
    agg = idx.resample("1h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna(how="all")
    out = []
    for ts, row in agg.iterrows():
        if pd.isna(row["close"]):
            continue
        out.append({
            "time_utc": int(ts.timestamp()),
            "open": round(float(row["open"]), 3),
            "high": round(float(row["high"]), 3),
            "low": round(float(row["low"]), 3),
            "close": round(float(row["close"]), 3),
        })
    return out


def compute_live_pnl_pct(call: dict, bars: pd.DataFrame) -> float | None:
    if bars.empty:
        return None
    entry = call.get("entry_approx")
    direction = call.get("direction")
    if entry is None or direction not in ("LONG", "SHORT"):
        return None
    now_price = float(bars["close"].iloc[-1])
    if direction == "LONG":
        return round((now_price - float(entry)) / float(entry) * 100, 3)
    return round((float(entry) - now_price) / float(entry) * 100, 3)


def gate_ok(name: str, value: float | bool | None, direction: str) -> bool | None:
    """Return True if the raw metric confirms the week's direction, else False.

    Semantics mirror src/far_weekly_telegram.py:91-102 (agrees with direction).
    """
    if value is None or direction == "FLAT":
        return None
    if name == "M20" or name == "M60":
        return (direction == "LONG" and value > 0) or (direction == "SHORT" and value < 0)
    if name == "MA":
        return (direction == "LONG" and bool(value)) or (direction == "SHORT" and not bool(value))
    if name == "RY":
        return (direction == "LONG" and value < 0) or (direction == "SHORT" and value > 0)
    return None


def build_gates_from_signal_row(row: pd.Series, direction: str) -> list[dict]:
    """Compute the four gate objects for one row of build_signals output."""
    m20 = float(row["M20"]) * 100 if pd.notna(row.get("M20")) else None
    m60 = float(row["M60"]) * 100 if pd.notna(row.get("M60")) else None
    ma_bool = bool(row["MA10"] > row["MA40"]) if pd.notna(row.get("MA10")) and pd.notna(row.get("MA40")) else None
    ry = float(row["RY_chg"]) * 100 if pd.notna(row.get("RY_chg")) else None
    return [
        {"name": "M20", "value": round(m20, 3) if m20 is not None else None,
         "ok": gate_ok("M20", m20, direction)},
        {"name": "M60", "value": round(m60, 3) if m60 is not None else None,
         "ok": gate_ok("M60", m60, direction)},
        {"name": "MA", "value": ma_bool,
         "ok": gate_ok("MA", ma_bool, direction)},
        {"name": "RY", "value": round(ry, 1) if ry is not None else None,
         "ok": gate_ok("RY", ry, direction)},
    ]


def load_calendar_for_week(week_of: str, week_end: str) -> pd.DataFrame:
    if not CALENDAR_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(CALENDAR_CSV, parse_dates=["ts_utc"])
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    start = pd.Timestamp(week_of, tz="UTC")
    end = pd.Timestamp(week_end, tz="UTC") + pd.Timedelta(hours=23, minutes=59)
    return df[(df["ts_utc"] >= start) & (df["ts_utc"] <= end)].sort_values("ts_utc")


def pick_event_for_day(events: pd.DataFrame, day: pd.Timestamp) -> dict | None:
    day_start = day.normalize()
    day_end = day_start + pd.Timedelta(hours=23, minutes=59)
    day_events = events[(events["ts_utc"] >= day_start) & (events["ts_utc"] <= day_end)]
    if day_events.empty:
        return None
    best = None
    best_rank = -1
    for _, r in day_events.iterrows():
        impact = EVENT_IMPACT.get(str(r["event"]), "low")
        rank = IMPACT_RANK[impact]
        if rank > best_rank:
            best_rank = rank
            best = {
                "name": str(r["event"]),
                "timeUtc": r["ts_utc"].isoformat(),
                "impact": impact,
            }
    return best


def build_commentary(pnl: float | None, stop_atr: float | None,
                     gates: list[dict], event: dict | None,
                     is_future: bool) -> str:
    if is_future:
        base = "Upcoming session, position unchanged."
    elif pnl is None or stop_atr is None:
        base = "No live read available for this session."
    elif stop_atr < 0.5:
        base = f"Within half an ATR of stop, {pnl:+.2f}% open."
    elif pnl >= 0.5:
        base = f"On track, {pnl:+.2f}% in the money."
    elif pnl <= -0.5:
        base = f"Underwater {pnl:+.2f}%, stop {stop_atr:.2f}x ATR away."
    else:
        base = f"Chopping near flat ({pnl:+.2f}%)."
    n_ok = sum(1 for g in gates if g.get("ok") is True)
    n_total = sum(1 for g in gates if g.get("ok") is not None)
    if n_total:
        base += f" Gates {n_ok}/{n_total}."
    if event and event["impact"] in ("high", "med"):
        base += f" Watch {event['name']} at {event['timeUtc'][11:16]} UTC."
    return base


def compute_daily_briefs(call: dict, week_bars_5m: pd.DataFrame,
                          now_utc: pd.Timestamp) -> list[dict]:
    """One entry per weekday of the active week. Empty on FLAT."""
    direction = call.get("direction")
    if direction == "FLAT":
        return []
    entry = call.get("entry_approx")
    stop = call.get("stop_price")
    if entry is None or stop is None:
        return []

    week_of = pd.Timestamp(call["week_of"], tz="UTC")
    week_end = pd.Timestamp(call["week_end"], tz="UTC")
    weekdays = [week_of + pd.Timedelta(days=i) for i in range(5)]

    # Load 6mo of daily bars + macro for gate recompute (as of each weekday)
    start = week_of - pd.Timedelta(days=180)
    daily = far_backtest.load_daily_bars(start, week_end + pd.Timedelta(days=2))
    ry = far_backtest.load_macro_series(far_backtest.RY, "real_yield_10y")
    signals = far_backtest.build_signals(daily, ry)

    events = load_calendar_for_week(call["week_of"], call["week_end"])
    dir_sign = 1 if direction == "LONG" else -1

    now_price = None
    if not week_bars_5m.empty:
        now_price = float(week_bars_5m["close"].iloc[-1])

    briefs = []
    for d in weekdays:
        d_end = d + pd.Timedelta(hours=23, minutes=59)
        is_future = d.normalize() > now_utc.normalize()
        is_today = d.normalize() == now_utc.normalize()

        # Signal row as of this weekday (last available signal row <= end of day)
        sig_slice = signals[signals.index <= d_end]
        sig_row = sig_slice.iloc[-1] if len(sig_slice) else None
        gates = build_gates_from_signal_row(sig_row, direction) if sig_row is not None else []

        # Close price for the day (or now_price if today)
        day_bars = week_bars_5m[(week_bars_5m["ts"] >= d) & (week_bars_5m["ts"] <= d_end)]
        if is_future:
            close_for_day = None
        elif is_today and now_price is not None:
            close_for_day = now_price
        elif not day_bars.empty:
            close_for_day = float(day_bars["close"].iloc[-1])
        else:
            close_for_day = None

        if close_for_day is not None:
            pnl = round((close_for_day - float(entry)) / float(entry) * 100 * dir_sign, 3)
            atr = call.get("atr_20d") or (float(sig_row["ATR"]) if sig_row is not None and pd.notna(sig_row.get("ATR")) else None)
            if atr:
                stop_atr = round(abs(float(stop) - close_for_day) / float(atr), 3)
            else:
                stop_atr = None
        else:
            pnl = None
            stop_atr = None

        event = pick_event_for_day(events, d)
        commentary = build_commentary(pnl, stop_atr, gates, event, is_future)

        briefs.append({
            "date": d.strftime("%Y-%m-%d"),
            "openPnlPct": pnl,
            "distanceStopAtr": stop_atr,
            "gates": gates,
            "event": event,
            "commentary": commentary,
        })
    return briefs


def compute_primary_risk(call: dict, live_pnl: float | None,
                          bars: pd.DataFrame) -> dict:
    """One-sentence risk statement + severity + trigger."""
    direction = call.get("direction")
    if direction == "FLAT":
        return {
            "sentence": ("No position this week. Primary risk is missing a "
                         "directional move that develops without our M20/M60/MA/RY setup."),
            "severity": "low",
            "trigger": None,
        }

    entry = call.get("entry_approx")
    stop = call.get("stop_price")
    if entry is None or stop is None or bars.empty:
        return {
            "sentence": "Position live, insufficient data to assess risk.",
            "severity": "low",
            "trigger": None,
        }

    now_price = float(bars["close"].iloc[-1])
    atr = float(call.get("atr_20d") or 0)
    stop_dist_atr = abs(float(stop) - now_price) / atr if atr > 0 else None
    week_end = pd.Timestamp(call["week_end"], tz="UTC") + pd.Timedelta(hours=21)
    hours_to_close = max(0.0, (week_end - pd.Timestamp.now(tz="UTC")).total_seconds() / 3600)

    pnl = live_pnl if live_pnl is not None else 0.0
    if stop_dist_atr is not None and stop_dist_atr < 0.75:
        severity = "high"
    elif (stop_dist_atr is not None and stop_dist_atr < 1.25) or pnl <= -0.5:
        severity = "med"
    else:
        severity = "low"

    if direction == "SHORT":
        trigger = f"Intraday break above ${float(stop):,.2f}"
        friday_condition = f"or Friday close above ${float(entry):,.2f}"
    else:
        trigger = f"Intraday break below ${float(stop):,.2f}"
        friday_condition = f"or Friday close below ${float(entry):,.2f}"

    if severity == "high":
        sentence = (f"Stop is {stop_dist_atr:.2f}x ATR away with {hours_to_close:.0f}h "
                    f"to Friday close. One volatile session flips this to a loss.")
    elif severity == "med":
        if pnl <= -0.5:
            sentence = (f"Position underwater {pnl:+.2f}%. Stop {stop_dist_atr:.2f}x ATR "
                        f"away, {hours_to_close:.0f}h to time exit.")
        else:
            sentence = (f"Stop {stop_dist_atr:.2f}x ATR away. Room to run but a "
                        f"1.25x ATR move against locks the loss.")
    else:
        sentence = (f"Stop {stop_dist_atr:.2f}x ATR away with {hours_to_close:.0f}h "
                    f"to close. Primary risk is a Friday-close reversal.")

    return {
        "sentence": sentence,
        "severity": severity,
        "trigger": f"{trigger} {friday_condition}",
    }


def refresh(dry_run: bool = False) -> None:
    call = load_active_call()
    if call is None:
        print("[skip] no active call in far_weekly_calls.jsonl")
        return
    week_of = call.get("week_of")
    week_end = call.get("week_end")
    if not week_of or not week_end or week_of == "unknown":
        print(f"[skip] active call missing week_of/week_end: {call}")
        return
    direction = call.get("direction")
    print(f"[active] week {week_of} -> {week_end}, direction={direction}")

    bars = load_week_bars(week_of, week_end)
    series = resample_hourly(bars)
    print(f"[bars] {len(bars)} 5m bars -> {len(series)} hourly points")

    live_pnl = compute_live_pnl_pct(call, bars) if direction != "FLAT" else None
    now_utc_iso = datetime.now(timezone.utc).isoformat()

    primary_risk = compute_primary_risk(call, live_pnl, bars)
    print(f"[primary_risk] severity={primary_risk['severity']}")

    try:
        briefs = compute_daily_briefs(call, bars, pd.Timestamp.now(tz="UTC"))
        print(f"[daily_briefs] {len(briefs)} entries")
    except Exception as e:
        print(f"[daily_briefs] failed: {type(e).__name__}: {e} (emitting [])")
        briefs = []

    if not SITE_CURRENT.exists():
        print(f"[warn] {SITE_CURRENT} missing - not writing live fields")
    else:
        current = json.loads(SITE_CURRENT.read_text(encoding="utf-8"))
        if direction == "FLAT":
            current.pop("live_pnl_pct", None)
            current.pop("live_updated_utc", None)
        elif live_pnl is not None:
            current["live_pnl_pct"] = live_pnl
            current["live_updated_utc"] = now_utc_iso
        current["primary_risk"] = primary_risk
        if not dry_run:
            SITE_CURRENT.write_text(
                json.dumps(current, indent=2, default=str), encoding="utf-8")
            print(f"[wrote] {SITE_CURRENT.name} live_pnl_pct={live_pnl} "
                  f"primary_risk.severity={primary_risk['severity']}")
        else:
            print(f"[dry-run] would write live_pnl_pct={live_pnl}")

    price_series_payload = {
        "week_of": week_of,
        "week_end": week_end,
        "series": series,
    }
    if not dry_run:
        SITE_PRICE_SERIES.parent.mkdir(parents=True, exist_ok=True)
        SITE_PRICE_SERIES.write_text(
            json.dumps(price_series_payload, separators=(",", ":")),
            encoding="utf-8")
        print(f"[wrote] {SITE_PRICE_SERIES.name} ({len(series)} points, envelope)")
        SITE_DAILY_BRIEFS.write_text(
            json.dumps(briefs, indent=2, default=str), encoding="utf-8")
        print(f"[wrote] {SITE_DAILY_BRIEFS.name} ({len(briefs)} entries)")
    else:
        print(f"[dry-run] would write price_series ({len(series)}) + "
              f"daily_briefs ({len(briefs)})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(f"[north_site_refresh] {datetime.now(timezone.utc).isoformat()}")
    refresh(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
