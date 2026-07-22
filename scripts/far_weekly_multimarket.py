"""Generic FAR Weekly test on any 5m CSV — same signal, per-market sizing.

For quick cross-market validation. Reads --csv, --contract-size, --cost.
"""
from __future__ import annotations

import sys
from pathlib import Path
import argparse
import math
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import importlib.util
spec = importlib.util.spec_from_file_location("far",
                                                str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)


def load_daily(csv_path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    buffer = pd.Timedelta(days=100)
    sub = df[(df.index >= start - buffer) & (df.index <= end)]
    daily = sub.resample("1D").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna()
    daily = daily[daily.index.weekday < 5]
    return daily


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--contract-size", type=float, default=100.0)
    ap.add_argument("--rt-cost", type=float, default=5.0)
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2023-12-31")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    daily = load_daily(csv_path, start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    df = far.build_signals(daily, ry)

    df_win = df[(df.index >= start) & (df.index <= end)]
    weeks = far.week_indices(df_win)

    trades = []
    flat_count = 0
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index:
            continue
        sig_row = df.loc[signal_date]
        direction = sig_row["direction"]
        if direction == "FLAT":
            flat_count += 1
            continue
        if pd.isna(sig_row["ATR"]) or pd.isna(sig_row["M60"]):
            continue
        entry_row = df.loc[mon] if mon in df.index else None
        if entry_row is None:
            continue
        entry_price = float(entry_row["open"])
        atr = float(sig_row["ATR"])
        if atr <= 0:
            continue
        if direction == "LONG":
            stop_price = entry_price - 2.0 * atr
        else:
            stop_price = entry_price + 2.0 * atr

        week_bars = df.loc[mon:fri]
        if len(week_bars) == 0:
            continue
        dir_sign = 1 if direction == "LONG" else -1
        exit_price = None; exit_reason = None
        for _, row in week_bars.iterrows():
            if direction == "LONG":
                hit_stop = float(row["low"]) <= stop_price
            else:
                hit_stop = float(row["high"]) >= stop_price
            if hit_stop:
                exit_price = stop_price; exit_reason = "stop"; break
        if exit_price is None:
            exit_price = float(week_bars.iloc[-1]["close"])
            exit_reason = "time"
        gross = (exit_price - entry_price) * dir_sign * args.contract_size
        net = gross - args.rt_cost
        trades.append({
            "week_start": mon, "direction": direction,
            "entry": entry_price, "exit": exit_price,
            "exit_reason": exit_reason, "net": net,
        })

    print(f"\n=== {args.label} ({args.start} to {args.end}) ===")
    print(f"  Total weeks: {len(weeks)}   FLAT: {flat_count} ({100*flat_count/len(weeks):.0f}%)")
    print(f"  Traded weeks: {len(trades)}")
    if not trades:
        return

    pnls = [t["net"] for t in trades]
    n = len(pnls); total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    returns = [t["net"] / (t["entry"] * args.contract_size) for t in trades if t["entry"] > 0]
    if returns:
        mean_r = sum(returns) / len(returns)
        std_r = (sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5
        sharpe_ann = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0
    else:
        sharpe_ann = 0

    print(f"  Win rate:  {100*wins/n:.1f}%")
    print(f"  Total P&L: ${total:+,.0f}")
    print(f"  Mean $/wk: ${mean:+,.0f}")
    print(f"  Sharpe ann: {sharpe_ann:.3f}")

    by_year = defaultdict(list)
    for t in trades:
        by_year[str(t["week_start"])[:4]].append(t)
    print(f"\n  Year breakdown:")
    for y in sorted(by_year):
        tr = by_year[y]
        pl = [t["net"] for t in tr]
        n_y = len(pl); w = sum(1 for p in pl if p > 0)
        print(f"    {y}: n={n_y:>3d}  mean=${sum(pl)/n_y:>+6,.0f}  "
              f"WR={100*w/n_y:>4.1f}%  total=${sum(pl):>+7,.0f}")


if __name__ == "__main__":
    main()
