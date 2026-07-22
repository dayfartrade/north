"""Gap-fade test on 12-year gold data.

Different mechanism from ORB — trades the fade of overnight/session gaps.
At NY session open (13:00 UTC), measure gap from prior day's 21:00 UTC close:
  - If gap up > threshold * ATR: SELL, target = prior close
  - If gap down > threshold * ATR: BUY, target = prior close
  - Stop: entry ± 1×ATR
  - Time exit: end of NY session (17:00 UTC, ~48 bars max)

Tests both markets: XAUUSD (12yr) and USA500 (9yr).
Reports per-year performance to check regime stability.

If gap-fade shows persistent edge across most years, it becomes a
candidate for pre-registration (subject to OOS testing on hold-out).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mers_v3_peb import compute_atr


def load_bars(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


def simulate_gap_fade(bars: pd.DataFrame,
                       ny_hour: int = 13,
                       gap_threshold_atr: float = 0.5,
                       max_hold_bars: int = 48,
                       stop_atr: float = 1.0,
                       contract_size: float = 100,
                       rt_cost: float = 24) -> list[dict]:
    atr = compute_atr(bars, 20)
    trades = []

    # Group by date
    dates = sorted(set(bars.index.date))
    prev_close = None
    prev_date = None

    for date in dates:
        d = pd.Timestamp(date, tz="UTC")
        if d.weekday() >= 5:
            continue

        # Compute prior day's ~21:00 UTC close as reference
        if prev_date is not None:
            prior = pd.Timestamp(prev_date, tz="UTC") + pd.Timedelta(hours=21)
            prior_slice = bars[(bars.index >= prior - pd.Timedelta(hours=1)) &
                                (bars.index <= prior + pd.Timedelta(hours=1))]
            if len(prior_slice):
                prev_close = float(prior_slice.iloc[-1]["close"])
        prev_date = date

        if prev_close is None:
            continue

        # Locate NY open bar (~13:00 UTC)
        open_ts = d + pd.Timedelta(hours=ny_hour)
        candidates = bars[bars.index >= open_ts]
        if len(candidates) == 0:
            continue
        open_idx_int = bars.index.get_indexer([candidates.index[0]])[0]
        if open_idx_int < 0 or open_idx_int >= len(bars):
            continue

        open_bar = bars.iloc[open_idx_int]
        open_price = float(open_bar["open"])
        cur_atr = float(atr.iloc[open_idx_int])
        if cur_atr <= 0:
            continue

        gap = open_price - prev_close
        gap_atr = gap / cur_atr

        # Fire if gap exceeds threshold
        if abs(gap_atr) < gap_threshold_atr:
            continue

        if gap_atr > 0:
            direction = "SHORT"
            entry = open_price
            target = prev_close
            stop = entry + stop_atr * cur_atr
            dir_sign = -1
        else:
            direction = "LONG"
            entry = open_price
            target = prev_close
            stop = entry - stop_atr * cur_atr
            dir_sign = 1

        # Simulate forward
        exit_price = None; exit_reason = None
        for k in range(max_hold_bars):
            i = open_idx_int + k
            if i >= len(bars):
                break
            b = bars.iloc[i]
            if direction == "LONG":
                hit_stop = float(b["low"]) <= stop
                hit_tp = float(b["high"]) >= target
            else:
                hit_stop = float(b["high"]) >= stop
                hit_tp = float(b["low"]) <= target
            if hit_stop and hit_tp:
                exit_price = stop; exit_reason = "stop_conservative"; break
            if hit_stop:
                exit_price = stop; exit_reason = "stop"; break
            if hit_tp:
                exit_price = target; exit_reason = "target"; break
        if exit_price is None:
            end_idx = min(open_idx_int + max_hold_bars, len(bars) - 1)
            exit_price = float(bars.iloc[end_idx]["close"])
            exit_reason = "time"

        gross = (exit_price - entry) * dir_sign * contract_size
        net = gross - rt_cost
        trades.append({
            "date": str(date),
            "direction": direction,
            "gap_atr": gap_atr,
            "atr": cur_atr,
            "exit": exit_reason,
            "net_pnl": net,
        })

    return trades


def report(trades: list[dict], label: str) -> None:
    if not trades:
        print(f"  {label}: no trades")
        return
    n = len(trades)
    pnls = [t["net_pnl"] for t in trades]
    total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    print(f"{label}: n={n:>5d}  mean=${mean:>+7,.0f}  WR={100*wins/n:>4.1f}%  total=${total:>+9,.0f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="gap threshold in ATR units (default 0.5)")
    ap.add_argument("--contract-size", type=float, default=100)
    ap.add_argument("--rt-cost", type=float, default=24)
    args = ap.parse_args()

    print(f"Gap-fade on {args.csv}")
    print(f"  threshold={args.threshold} ATR, contract={args.contract_size}, "
          f"rt_cost=${args.rt_cost}")
    bars = load_bars(args.csv)
    print(f"  {len(bars):,} bars {bars.index[0].date()} -> {bars.index[-1].date()}\n")

    trades = simulate_gap_fade(bars, gap_threshold_atr=args.threshold,
                                contract_size=args.contract_size,
                                rt_cost=args.rt_cost)

    print("=== Overall ===")
    report(trades, "  all")

    # By year
    by_year = defaultdict(list)
    for t in trades:
        by_year[t["date"][:4]].append(t)
    print("\n=== By year ===")
    for y in sorted(by_year):
        report(by_year[y], f"  {y}")

    # By direction
    by_dir = defaultdict(list)
    for t in trades:
        by_dir[t["direction"]].append(t)
    print("\n=== By direction ===")
    for d, ts in by_dir.items():
        report(ts, f"  {d}")

    # By exit reason
    by_exit = defaultdict(list)
    for t in trades:
        by_exit[t["exit"]].append(t)
    print("\n=== By exit ===")
    for e, ts in by_exit.items():
        report(ts, f"  {e}")


if __name__ == "__main__":
    main()
