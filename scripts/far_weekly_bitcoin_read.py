"""FAR Weekly Bitcoin Read backtest engine.

Pre-reg: docs/experiments/2026-07-24_far_weekly_bitcoin_read_prereg.md
Signal: BTC 60d momentum + DXY 20d change (both must confirm direction)
Timeframe: weekly (Monday 00:00 UTC open -> Friday 23:55 UTC close)
Cost model: 0.1% RT on notional (Coinbase/Kraken spot realistic)

Usage:
  python scripts/far_weekly_bitcoin_read.py --start 2017-05-07 --end 2020-12-31 --label TRAINING
  python scripts/far_weekly_bitcoin_read.py --start 2021-01-01 --end 2023-12-31 --label OOS
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

BTC_5M = ROOT / "data" / "external" / "dukascopy" / "BTCUSD_5m_historical.csv"
DXY_CSV = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"

NOTIONAL = 10_000.0
RT_COST_PCT = 0.001
STOP_ATR_MULT = 2.0
M60_LAG = 60
DXY_LAG = 20
ATR_PERIOD = 20


def load_btc_daily(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    df = pd.read_csv(BTC_5M, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    buffer = pd.Timedelta(days=100)
    sub = df[(df.index >= start - buffer) & (df.index <= end)]
    daily = sub.resample("1D").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna()
    return daily


def load_dxy() -> pd.Series:
    df = pd.read_csv(DXY_CSV, parse_dates=["date"])
    df = df.set_index("date").sort_index()
    return df["value"].astype(float)


def build_signals(daily: pd.DataFrame, dxy: pd.Series) -> pd.DataFrame:
    df = daily.copy()
    df["M60"] = df["close"].pct_change(M60_LAG)
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(ATR_PERIOD).mean()

    idx_naive = df.index.tz_localize(None) if df.index.tz else df.index
    dxy_daily = dxy.reindex(idx_naive, method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(DXY_LAG)

    long_ok = (df["M60"] > 0) & (df["DXY_chg"] < 0)
    short_ok = (df["M60"] < 0) & (df["DXY_chg"] > 0)
    df["direction"] = np.where(long_ok, "LONG",
                                np.where(short_ok, "SHORT", "FLAT"))
    return df


def week_indices(df: pd.DataFrame) -> list[tuple]:
    """Return list of (signal_date=Sunday, entry=Monday, exit=Friday)."""
    out = []
    dates = df.index.normalize().unique()
    for d in dates:
        if d.weekday() != 6:
            continue
        mon = d + pd.Timedelta(days=1)
        fri = d + pd.Timedelta(days=5)
        if mon in df.index and fri in df.index:
            out.append((d, mon, fri))
    return out


def backtest(start: pd.Timestamp, end: pd.Timestamp) -> dict:
    daily = load_btc_daily(start, end)
    dxy = load_dxy()
    df = build_signals(daily, dxy)
    df_win = df[(df.index >= start) & (df.index <= end)]
    weeks = week_indices(df_win)

    trades = []
    flat = 0
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index:
            continue
        sig = df.loc[signal_date]
        direction = sig["direction"]
        if direction == "FLAT":
            flat += 1
            continue
        if pd.isna(sig["ATR"]) or pd.isna(sig["M60"]) or pd.isna(sig["DXY_chg"]):
            continue
        entry_price = float(df.loc[mon]["open"])
        atr = float(sig["ATR"])
        if atr <= 0 or entry_price <= 0:
            continue
        size = NOTIONAL / entry_price  # fractional BTC
        if direction == "LONG":
            stop_price = entry_price - STOP_ATR_MULT * atr
        else:
            stop_price = entry_price + STOP_ATR_MULT * atr

        week_bars = df.loc[mon:fri]
        if len(week_bars) == 0:
            continue
        dir_sign = 1 if direction == "LONG" else -1
        exit_price = None; exit_reason = None
        for _, row in week_bars.iterrows():
            hit_stop = (float(row["low"]) <= stop_price) if direction == "LONG" \
                       else (float(row["high"]) >= stop_price)
            if hit_stop:
                exit_price = stop_price; exit_reason = "stop"; break
        if exit_price is None:
            exit_price = float(week_bars.iloc[-1]["close"])
            exit_reason = "time"

        gross = (exit_price - entry_price) * dir_sign * size
        cost = RT_COST_PCT * (entry_price + exit_price) * size
        net = gross - cost
        trades.append({
            "week_start": mon, "direction": direction,
            "entry": entry_price, "exit": exit_price,
            "size": size, "exit_reason": exit_reason,
            "gross": gross, "cost": cost, "net": net,
        })
    return {"trades": trades, "flat": flat, "total_weeks": len(weeks)}


def summarize(trades: list[dict], label: str) -> None:
    n = len(trades)
    if n == 0:
        print(f"[{label}] No trades.")
        return
    pnls = [t["net"] for t in trades]
    returns = [t["net"] / NOTIONAL for t in trades]  # per-notional return
    total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    stops = sum(1 for t in trades if t["exit_reason"] == "stop")
    mean_r = sum(returns) / n
    std_r = (sum((r - mean_r) ** 2 for r in returns) / (n - 1)) ** 0.5 if n > 1 else 0
    sharpe = mean_r / std_r * math.sqrt(52) if std_r > 0 else 0

    from deflated_sharpe import sr_stats, probabilistic_sharpe
    s = sr_stats(returns)
    psr = probabilistic_sharpe(s, benchmark_sr=0.0)

    import random
    rng = random.Random(42)
    means = []
    for _ in range(10000):
        smp = [returns[rng.randrange(n)] for _ in range(n)]
        means.append(sum(smp) / n)
    means.sort()
    lo95 = means[250]; hi95 = means[9750]

    print(f"\n=== FAR Weekly Bitcoin [{label}] ===")
    print(f"  Trades: {n}   FLAT: NA (see all-window count)   Stops hit: {stops}")
    print(f"  Win rate: {100*wins/n:.1f}%")
    print(f"  Total P&L: ${total:+,.0f}   Mean $/week: ${mean:+,.0f}")
    print(f"  Total return on notional: {100*total/NOTIONAL:+.1f}%")
    print(f"  Sharpe (ann): {sharpe:.3f}")
    print(f"  Skewness: {s.skewness:+.3f}")
    print(f"  Bootstrap 95% CI on mean weekly return: [{100*lo95:+.4f}%, {100*hi95:+.4f}%]")
    print(f"  PSR vs SR=0: {psr:.4f}")

    by_year = defaultdict(list)
    for t in trades:
        by_year[str(t["week_start"])[:4]].append(t)
    print(f"\n  Year-by-year:")
    for y in sorted(by_year):
        tr = by_year[y]
        pl = [t["net"] for t in tr]
        n_y = len(pl); w = sum(1 for p in pl if p > 0)
        print(f"    {y}: n={n_y:>3d}  mean=${sum(pl)/n_y:>+7,.0f}  "
              f"WR={100*w/n_y:>4.1f}%  total=${sum(pl):>+9,.0f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--label", default="RUN")
    args = ap.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    r = backtest(start, end)
    print(f"\nTotal weeks in window: {r['total_weeks']}  FLAT: {r['flat']} "
          f"({100*r['flat']/r['total_weeks']:.0f}% if {r['total_weeks']>0})"
          if r['total_weeks'] > 0 else "\nNo weeks in window.")
    summarize(r["trades"], args.label)


if __name__ == "__main__":
    main()
