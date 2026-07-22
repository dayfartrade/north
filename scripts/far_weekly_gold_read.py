"""FAR Weekly Gold Read backtest engine.

Pre-reg: docs/experiments/2026-07-22_far_weekly_gold_read_prereg.md
Signal: momentum (M20, M60, MA10/40 crossover) + macro (RY_chg)
Timeframe: weekly (Monday open -> Friday close)
Cost model: $5 RT per contract (GC IBKR realistic)

Fixed parameters per pre-reg:
  M20_lag = 20 daily bars (4 weeks)
  M60_lag = 60 daily bars (12 weeks)
  MA_short = 10 daily bars
  MA_long = 40 daily bars
  RY_chg_lag = 20 business days
  ATR_period = 20 daily bars
  Stop_multiplier = 2.0 * ATR
  Contract_size = 100 oz
  RT_cost = $5

Usage:
  python far_weekly_gold_read.py --start 2015-01-01 --end 2020-12-31 --label TRAINING
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

EARLY_5M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m_2010_2014.csv"
HISTORICAL_5M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m_historical.csv"
LIVE_5M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"
RY = ROOT / "data" / "macro" / "real_yield_10y__DFII10.csv"
DXY = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"

CONTRACT_SIZE = 100
RT_COST = 5.0
STOP_ATR_MULT = 2.0

M20_LAG = 20
M60_LAG = 60
MA_SHORT = 10
MA_LONG = 40
RY_LAG = 20
ATR_PERIOD = 20


def load_daily_bars(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Combine 2015-2023 historical + 2024-onward live, resample to daily
    (Monday-open, Friday-close)."""
    dfs = []
    for path in [EARLY_5M, HISTORICAL_5M, LIVE_5M]:
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["ts"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        dfs.append(df)
    combined = pd.concat(dfs, ignore_index=True) \
        .drop_duplicates(subset=["ts"], keep="first") \
        .sort_values("ts") \
        .set_index("ts")

    # Filter to date range (with buffer for signal computation)
    buffer = pd.Timedelta(days=100)
    subset = combined[(combined.index >= start - buffer) & (combined.index <= end)]

    # Resample to daily: use last 5m of NY session (~21:00 UTC) as daily close,
    # first 5m of NY session (~13:00 UTC) as daily open, high/low over full day
    daily = subset.resample("1D").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna()
    # Weekdays only (Mon=0..Fri=4)
    daily = daily[daily.index.weekday < 5]
    return daily


def load_macro_series(path: Path, name: str) -> pd.Series:
    df = pd.read_csv(path, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df["value"].rename(name)


def compute_atr(bars: pd.DataFrame, n: int) -> pd.Series:
    high = bars["high"]; low = bars["low"]; close_prev = bars["close"].shift(1)
    tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()],
                    axis=1).max(axis=1)
    return tr.rolling(n).mean()


def build_signals(daily: pd.DataFrame, ry: pd.Series) -> pd.DataFrame:
    df = daily.copy()
    df["M20"] = df["close"].pct_change(M20_LAG)
    df["M60"] = df["close"].pct_change(M60_LAG)
    df["MA10"] = df["close"].rolling(MA_SHORT).mean()
    df["MA40"] = df["close"].rolling(MA_LONG).mean()
    df["ATR"] = compute_atr(df, ATR_PERIOD)

    # RY change: 20-day change in real yield
    ry_daily = ry.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                           method="ffill")
    ry_daily.index = df.index
    df["RY"] = ry_daily
    df["RY_chg"] = df["RY"].diff(RY_LAG)

    # Direction signal
    long_cond = ((df["M20"] > 0) & (df["M60"] > 0) &
                 (df["MA10"] > df["MA40"]) & (df["RY_chg"] < 0))
    short_cond = ((df["M20"] < 0) & (df["M60"] < 0) &
                  (df["MA10"] < df["MA40"]) & (df["RY_chg"] > 0))
    df["direction"] = np.where(long_cond, "LONG",
                                np.where(short_cond, "SHORT", "FLAT"))
    return df


def week_indices(daily: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Return list of (signal_date, monday, friday) for each trading week
    where all three exist in daily. signal_date = last friday BEFORE monday."""
    weeks = []
    dates = daily.index
    # Group by ISO week
    df = daily.copy()
    df["iso_year"] = df.index.isocalendar().year
    df["iso_week"] = df.index.isocalendar().week
    for (y, w), grp in df.groupby(["iso_year", "iso_week"]):
        if len(grp) < 2:
            continue
        monday = grp.index[grp.index.weekday == 0]
        friday = grp.index[grp.index.weekday == 4]
        if len(monday) == 0 or len(friday) == 0:
            continue
        mon = monday[0]; fri = friday[-1]
        # Signal date = last trading day BEFORE Monday (Fri of prior week)
        prior_days = df.index[df.index < mon]
        if len(prior_days) == 0:
            continue
        signal_date = prior_days[-1]
        weeks.append((signal_date, mon, fri))
    return weeks


def simulate_week(daily: pd.DataFrame, mon: pd.Timestamp, fri: pd.Timestamp,
                   direction: str, entry_price: float, stop_price: float) -> dict:
    """Simulate one week's trade."""
    week_bars = daily[(daily.index >= mon) & (daily.index <= fri)]
    if len(week_bars) == 0:
        return None
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
    gross = (exit_price - entry_price) * dir_sign * CONTRACT_SIZE
    net = gross - RT_COST
    return {
        "week_start": mon, "week_end": fri,
        "direction": direction, "entry": entry_price, "exit": exit_price,
        "stop": stop_price, "exit_reason": exit_reason,
        "gross": gross, "net": net,
    }


def backtest(start: pd.Timestamp, end: pd.Timestamp, verbose: bool = False) -> dict:
    daily = load_daily_bars(start, end)
    ry = load_macro_series(RY, "real_yield_10y")
    df = build_signals(daily, ry)

    # Get weeks in the [start, end] range
    df = df[(df.index >= start) & (df.index <= end)]
    weeks = week_indices(df)

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
            stop_price = entry_price - STOP_ATR_MULT * atr
        else:
            stop_price = entry_price + STOP_ATR_MULT * atr

        # Slice daily bars in the week
        week_slice = df.loc[mon:fri]
        result = simulate_week(week_slice, mon, fri, direction,
                                entry_price, stop_price)
        if result:
            trades.append(result)

    return {"trades": trades, "flat_weeks": flat_count, "total_weeks": len(weeks)}


def report(label: str, trades: list, flat: int, total: int) -> dict:
    if not trades:
        print(f"\n{label}: NO TRADES ({flat}/{total} flat)")
        return {}
    n = len(trades)
    pnls = [t["net"] for t in trades]
    total_pnl = sum(pnls); mean = total_pnl / n
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    wr = wins / n

    # Weekly returns as fraction of entry (proxy for Sharpe)
    returns = [t["net"] / (t["entry"] * CONTRACT_SIZE) for t in trades]
    mean_r = np.mean(returns); std_r = np.std(returns, ddof=1)
    sharpe_weekly = mean_r / std_r if std_r > 0 else 0
    sharpe_ann = sharpe_weekly * np.sqrt(52)

    # Drawdown on cumulative net P&L
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd = float(dd.min())

    print(f"\n=== {label} ===")
    print(f"  Total weeks:      {total}   (FLAT: {flat}, {100*flat/total:.0f}%)")
    print(f"  Traded weeks:     {n}   ({wins}W / {losses}L)")
    print(f"  Win rate:         {100*wr:.1f}%")
    print(f"  Total P&L:        ${total_pnl:+,.0f}")
    print(f"  Mean $/week:      ${mean:+,.0f}")
    print(f"  Sharpe (weekly):  {sharpe_weekly:.3f}")
    print(f"  Sharpe (ann):     {sharpe_ann:.3f}")
    print(f"  Max drawdown:     ${max_dd:+,.0f}")
    return {"n": n, "total_pnl": total_pnl, "mean": mean, "wr": wr,
            "sharpe_ann": sharpe_ann, "max_dd": max_dd, "flat": flat,
            "total": total}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--label", default="RUN")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    result = backtest(start, end, verbose=args.verbose)
    report(args.label, result["trades"], result["flat_weeks"], result["total_weeks"])


if __name__ == "__main__":
    main()
