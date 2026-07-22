"""Path S: post-event momentum bot scalping — 1m gold feasibility test.

Theoretical basis: Andersen-Bollerslev-Dobrev (2007) showed macro releases
cause rapid price adjustment in the first 1-5 minutes. Retail-tractable
version: on release days, wait for the first 5-min post-release move,
enter in direction, hold 10-20 minutes.

Test on 2019-2023 1m XAUUSD (5 years OOS).

Config (fixed; DON'T post-hoc tune):
  - Events: FOMC, NFP, CPI, PPI, UNRATE (from calendar_events.py)
  - Release timing: use event calendar's ts_utc directly
  - Initial move window: 5 minutes after release
  - Direction: sign of initial move
  - Entry: at 5 min post-release close
  - Hold: 15 minutes
  - Stop: 1.5x ATR(30min proxy = 30 1m bars)
  - Cost: $3 round-trip on GC futures (aggressive but realistic scalping)

Retire criteria (before formal pre-reg):
  If test on 2019-2023 shows Sharpe < 0.5 or WR < 45%, retire — not a
  scalping-tractable edge. If passes, proceed to formal pre-reg.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from collections import defaultdict

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS_1M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_1m_historical.csv"
EVENTS = ROOT / "data" / "calendar" / "events.csv"

CONTRACT_SIZE = 100
RT_COST = 3.0
INITIAL_WINDOW_MIN = 5
HOLD_MIN = 15
STOP_ATR_MULT = 1.5
ATR_BARS = 30  # 30 1m bars = 30 min
MOVE_THRESHOLD_TICKS = 0.0  # take any directional 5-min move
INCLUDE_EVENTS = {"FOMC", "NFP", "CPI", "PPI", "UNRATE"}


def load_bars() -> pd.DataFrame:
    df = pd.read_csv(BARS_1M, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


def load_events() -> pd.DataFrame:
    ev = pd.read_csv(EVENTS, parse_dates=["ts_utc"])
    ev["ts_utc"] = pd.to_datetime(ev["ts_utc"], utc=True)
    return ev[ev["event"].isin(INCLUDE_EVENTS)].sort_values("ts_utc")


def compute_atr_1m(bars: pd.DataFrame, n: int) -> pd.Series:
    high = bars["high"]; low = bars["low"]; close_prev = bars["close"].shift(1)
    tr = pd.concat([high - low, (high - close_prev).abs(),
                    (low - close_prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def find_release_bar(bars: pd.DataFrame, event_ts: pd.Timestamp) -> int | None:
    """Find index of 1m bar containing/immediately after the release."""
    if event_ts < bars.index[0] or event_ts > bars.index[-1]:
        return None
    idx = bars.index.searchsorted(event_ts, side="left")
    if idx >= len(bars):
        return None
    return int(idx)


def simulate_event(bars: pd.DataFrame, atr: pd.Series,
                    release_idx: int) -> dict | None:
    """Simulate one post-event momentum trade."""
    # Wait INITIAL_WINDOW_MIN bars post release
    win_end_idx = release_idx + INITIAL_WINDOW_MIN
    if win_end_idx >= len(bars):
        return None

    release_price = float(bars.iloc[release_idx]["open"])
    win_end_price = float(bars.iloc[win_end_idx]["close"])
    initial_move = win_end_price - release_price

    if abs(initial_move) <= MOVE_THRESHOLD_TICKS:
        return {"skipped": "no_directional_move", "release_ts": bars.index[release_idx]}

    direction = "LONG" if initial_move > 0 else "SHORT"
    dir_sign = 1 if direction == "LONG" else -1
    entry_price = win_end_price
    entry_idx = win_end_idx

    cur_atr = float(atr.iloc[entry_idx])
    if cur_atr <= 0 or pd.isna(cur_atr):
        return None
    stop_price = entry_price - dir_sign * STOP_ATR_MULT * cur_atr

    # Hold HOLD_MIN bars
    exit_price = None; exit_reason = None
    for k in range(HOLD_MIN):
        i = entry_idx + 1 + k
        if i >= len(bars):
            break
        b = bars.iloc[i]
        if direction == "LONG":
            hit_stop = float(b["low"]) <= stop_price
        else:
            hit_stop = float(b["high"]) >= stop_price
        if hit_stop:
            exit_price = stop_price; exit_reason = "stop"; break
    if exit_price is None:
        end_idx = min(entry_idx + HOLD_MIN, len(bars) - 1)
        exit_price = float(bars.iloc[end_idx]["close"])
        exit_reason = "time"

    gross = (exit_price - entry_price) * dir_sign * CONTRACT_SIZE
    net = gross - RT_COST
    return {
        "release_ts": bars.index[release_idx],
        "direction": direction, "initial_move_pts": round(initial_move, 3),
        "entry": entry_price, "exit": exit_price, "exit_reason": exit_reason,
        "atr": cur_atr, "stop": stop_price,
        "net_pnl": net,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2023-12-31")
    args = ap.parse_args()

    print(f"Loading 1m bars from {BARS_1M.name}...")
    bars = load_bars()
    print(f"  {len(bars):,} bars {bars.index[0].date()} -> {bars.index[-1].date()}")

    print(f"Loading events...")
    events = load_events()
    events = events[(events["ts_utc"] >= pd.Timestamp(args.start, tz="UTC")) &
                    (events["ts_utc"] <= pd.Timestamp(args.end, tz="UTC"))]
    print(f"  {len(events)} events in window (of types {INCLUDE_EVENTS})")

    atr = compute_atr_1m(bars, ATR_BARS)

    trades = []
    skipped = 0
    for _, ev in events.iterrows():
        ts = ev["ts_utc"]
        if ts < bars.index[0] or ts > bars.index[-1]:
            continue
        release_idx = find_release_bar(bars, ts)
        if release_idx is None:
            continue
        result = simulate_event(bars, atr, release_idx)
        if result is None:
            continue
        if "skipped" in result:
            skipped += 1
            continue
        result["event"] = ev["event"]
        trades.append(result)

    print(f"\nTotal trades: {len(trades)}   (skipped no-move: {skipped})")
    if not trades:
        return

    pnls = [t["net_pnl"] for t in trades]
    n = len(pnls); total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    print(f"  Total P&L:  ${total:+,.0f}")
    print(f"  Mean $/trade: ${mean:+,.2f}")
    print(f"  WR: {100*wins/n:.1f}%")

    # By event type
    print(f"\nBy event type:")
    by_ev = defaultdict(list)
    for t in trades:
        by_ev[t["event"]].append(t)
    for ev in sorted(by_ev):
        tr = by_ev[ev]
        pl = [t["net_pnl"] for t in tr]
        n_e = len(pl); w = sum(1 for p in pl if p > 0)
        print(f"  {ev:8s} n={n_e:>3d}  mean=${sum(pl)/n_e:>+7,.0f}  "
              f"WR={100*w/n_e:>4.1f}%  total=${sum(pl):>+7,.0f}")

    # By year
    print(f"\nBy year:")
    by_yr = defaultdict(list)
    for t in trades:
        by_yr[str(t["release_ts"])[:4]].append(t)
    for y in sorted(by_yr):
        tr = by_yr[y]
        pl = [t["net_pnl"] for t in tr]
        n_y = len(pl); w = sum(1 for p in pl if p > 0)
        print(f"  {y}: n={n_y:>3d}  mean=${sum(pl)/n_y:>+7,.0f}  "
              f"WR={100*w/n_y:>4.1f}%  total=${sum(pl):>+7,.0f}")

    # By direction
    print(f"\nBy direction:")
    by_dir = defaultdict(list)
    for t in trades:
        by_dir[t["direction"]].append(t)
    for d in sorted(by_dir):
        tr = by_dir[d]
        pl = [t["net_pnl"] for t in tr]
        n_d = len(pl); w = sum(1 for p in pl if p > 0)
        print(f"  {d}: n={n_d:>3d}  mean=${sum(pl)/n_d:>+7,.0f}  "
              f"WR={100*w/n_d:>4.1f}%")


if __name__ == "__main__":
    main()
