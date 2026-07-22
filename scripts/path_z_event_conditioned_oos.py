"""Event-conditioned Path Z variant tested on 12-year OOS.

Hypothesis: Path Z's mechanism (fade upside during noisy NY opens) may
work IF gated by macro-release timing — the theory being that
scheduled releases create the specific liquidation flow patterns
that Path Z relies on.

Test: apply full Path Z filter (NY-SHORT + Low-ER + Mon-Wed) AND
restrict to days matching macro-event conditioning:
  - VARIANT A: ONLY on days with an event released 8:30-14:00 ET
  - VARIANT B: ONLY on days AFTER a FOMC/NFP/CPI release
  - VARIANT C: SKIP days with events (opposite of A)

Sample: 12 years XAUUSD 5m (2015-01-01 to 2026-07-20, 2015-2023
from historical file + 2024-2026 from live file).

If any variant shows persistent edge across the 12-year sample with
proper year-by-year stability, that's a new pre-reg candidate.
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mers_v3_peb import compute_atr
from regime_context import _efficiency_ratio, build_regime_context
from strategy_engine import (
    OrContext, SESSION_CONFIGS_V9_Z, evaluate_session, Direction,
)

CONTRACT_SIZE = 100
RT_COST = 24.0
OR_BARS = 6
WATCH_BARS = 12
MAX_HOLD_BARS = 36
NY_HOUR_UTC = 13

HISTORICAL_CSV = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m_historical.csv"
LIVE_CSV = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"
EVENTS_CSV = ROOT / "data" / "calendar" / "events.csv"


def load_bars() -> pd.DataFrame:
    """Combine 2015-2023 historical + 2024-2026 live into one dataframe."""
    dfs = []
    for path in [HISTORICAL_CSV, LIVE_CSV]:
        df = pd.read_csv(path, parse_dates=["ts"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        dfs.append(df)
    combined = pd.concat(dfs, ignore_index=True)
    combined = combined.drop_duplicates(subset=["ts"], keep="first").sort_values("ts")
    combined = combined.set_index("ts")
    return combined


def load_events() -> pd.DataFrame:
    ev = pd.read_csv(EVENTS_CSV, parse_dates=["ts_utc"])
    ev["ts_utc"] = pd.to_datetime(ev["ts_utc"], utc=True)
    ev["date"] = ev["ts_utc"].dt.date
    return ev


def slope_5h(bars_1h: pd.Series, up_to_ts) -> float:
    seg = bars_1h[bars_1h.index <= up_to_ts]
    if len(seg) < 55:
        return 0.0
    ema = seg.ewm(span=50, adjust=False).mean()
    return float(ema.iloc[-1] - ema.iloc[-6])


def simulate(bars: pd.DataFrame, entry_idx: int, entry: float,
             stop: float, target: float, direction: str) -> dict:
    dir_sign = 1 if direction == "LONG" else -1
    for k in range(MAX_HOLD_BARS + 1):
        if entry_idx + k >= len(bars):
            break
        b = bars.iloc[entry_idx + k]
        if direction == "LONG":
            hit_stop = float(b["low"]) <= stop
            hit_tp = float(b["high"]) >= target
        else:
            hit_stop = float(b["high"]) >= stop
            hit_tp = float(b["low"]) <= target
        if hit_stop and hit_tp:
            exit_price = stop; kind = "stop_conservative"; break
        if hit_stop:
            exit_price = stop; kind = "stop"; break
        if hit_tp:
            exit_price = target; kind = "target"; break
    else:
        end_idx = min(entry_idx + MAX_HOLD_BARS, len(bars) - 1)
        exit_price = float(bars.iloc[end_idx]["close"])
        kind = "time"
    gross = (exit_price - entry) * dir_sign * CONTRACT_SIZE
    return {"kind": kind, "net_pnl": gross - RT_COST}


def is_event_day(date, events: pd.DataFrame, event_filter=None) -> tuple[bool, list[str]]:
    """Return (True/False, list of event types on this date)."""
    same_day = events[events["date"] == date]
    if event_filter is not None:
        same_day = same_day[same_day["event"].isin(event_filter)]
    return (len(same_day) > 0, sorted(set(same_day["event"])) if len(same_day) else [])


def main() -> None:
    print("Loading bars...")
    bars = load_bars()
    print(f"  {len(bars):,} bars {bars.index[0].date()} -> {bars.index[-1].date()}")

    events = load_events()
    print(f"  {len(events)} macro events {events['date'].min()} -> {events['date'].max()}")

    atr = compute_atr(bars, 20)
    bars_1h = bars["close"].resample("1h").last().dropna()

    cfg = SESSION_CONFIGS_V9_Z["NY"]

    # High-info events (FOMC, NFP, CPI, PPI)
    high_info_events = ["FOMC", "NFP", "CPI", "PPI", "UNRATE"]

    all_trades = []
    for date in sorted(set(bars.index.date)):
        d = pd.Timestamp(date, tz="UTC")
        if d.weekday() == 5:  # Saturday
            continue
        open_ts = d + pd.Timedelta(hours=NY_HOUR_UTC)
        or_close_ts = open_ts + pd.Timedelta(minutes=30)
        or_slice = bars[(bars.index >= open_ts) & (bars.index < or_close_ts)]
        if len(or_slice) < OR_BARS:
            continue
        or_slice = or_slice.iloc[:OR_BARS]
        or_high = float(or_slice["high"].max())
        or_low = float(or_slice["low"].min())
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        or_close_actual = or_slice.index[-1]
        or_close_idx = bars.index.get_loc(or_close_actual)

        cur_atr = float(atr.iloc[or_close_idx])
        if cur_atr <= 0:
            continue

        cur_slope = slope_5h(bars_1h, or_close_actual)
        closes_pre = bars.iloc[max(0, or_close_idx - 20): or_close_idx + 1]["close"].tolist()
        er = _efficiency_ratio(closes_pre, n=20)

        or_ctx = OrContext(
            session_open_utc=open_ts, or_close_utc=or_close_actual,
            or_high=or_high, or_low=or_low, or_range=or_range,
            atr_at_close=cur_atr, slope_at_close=cur_slope,
            or_bars_df=or_slice,
        )
        regime = build_regime_context(or_close_actual, efficiency_ratio_5m_20=er)
        decision = evaluate_session(cfg, or_ctx, regime)

        if not decision.would_take:
            continue

        # Find entry breakout
        entry_idx = None; entry_price = None
        for k in range(WATCH_BARS):
            i = or_close_idx + 1 + k
            if i >= len(bars): break
            b = bars.iloc[i]
            if decision.direction == Direction.LONG and b["high"] >= or_high:
                entry_idx = i; entry_price = or_high; break
            if decision.direction == Direction.SHORT and b["low"] <= or_low:
                entry_idx = i; entry_price = or_low; break
        if entry_idx is None:
            continue

        outcome = simulate(bars, entry_idx, entry_price,
                            decision.stop_price, decision.target_price,
                            decision.direction.name)

        # Classify event context
        prev_d = date - pd.Timedelta(days=1)
        has_event_today, events_today = is_event_day(date, events, high_info_events)
        has_event_prev, events_prev = is_event_day(prev_d, events, high_info_events)

        all_trades.append({
            "date": date, "net_pnl": outcome["net_pnl"],
            "kind": outcome["kind"],
            "has_event_today": has_event_today,
            "has_event_prev": has_event_prev,
            "events_today": ",".join(events_today) if events_today else "",
            "events_prev": ",".join(events_prev) if events_prev else "",
        })

    print(f"\nTotal Path Z-taken trades (2015-2026): {len(all_trades)}")

    def report(label: str, trades: list) -> None:
        if not trades:
            print(f"  {label:40s} NO TRADES")
            return
        n = len(trades); pnls = [t["net_pnl"] for t in trades]
        m = sum(pnls) / n; tot = sum(pnls)
        wr = sum(1 for p in pnls if p > 0) / n
        print(f"  {label:40s} n={n:>4d}  mean=${m:>+7,.0f}  WR={100*wr:>4.1f}%  total=${tot:>+8,.0f}")

    # Variants
    A_event_day = [t for t in all_trades if t["has_event_today"]]
    B_after_event = [t for t in all_trades if t["has_event_prev"]]
    C_quiet = [t for t in all_trades if not t["has_event_today"] and not t["has_event_prev"]]
    D_event_or_after = [t for t in all_trades if t["has_event_today"] or t["has_event_prev"]]

    print("\n=== Variants (12yr sample) ===")
    report("baseline (all Path Z)", all_trades)
    report("A: EVENT-DAY only", A_event_day)
    report("B: DAY-AFTER-EVENT only", B_after_event)
    report("D: EVENT-DAY or DAY-AFTER (combined)", D_event_or_after)
    report("C: QUIET days only (no event ±1)", C_quiet)

    # Year-by-year for D (event-or-after) since it has most trades
    print("\n=== VARIANT D (event or day-after) year-by-year ===")
    by_year = defaultdict(list)
    for t in D_event_or_after:
        by_year[str(t["date"])[:4]].append(t)
    for y in sorted(by_year):
        report(f"  {y}", by_year[y])

    # Year-by-year for A (event day only) — most targeted
    print("\n=== VARIANT A (event day only) year-by-year ===")
    by_year = defaultdict(list)
    for t in A_event_day:
        by_year[str(t["date"])[:4]].append(t)
    for y in sorted(by_year):
        report(f"  {y}", by_year[y])


if __name__ == "__main__":
    main()
