"""FAR Weekly Gold Seed 2 — Countertrend Fade v1 backtest.

Pre-reg: docs/experiments/2026-07-29_seed2_countertrend_fade_prereg.md
Trial id: far_weekly_gold_seed2_countertrend_fade_v1
Author: Knox
Registered: 2026-07-29T05:55:00Z

Mechanism:
  LONG  if week_low  <= 4w-rolling-low  AND close > close[8w ago]
  SHORT if week_high >= 4w-rolling-high AND close < close[8w ago]
  Else FLAT

Position mgmt (frozen, DO NOT tune):
  Entry:  Monday open
  Stop:   entry +/- 2 * ATR(20d)
  Target: Friday close (time exit) or stop hit
  Cost:   $5 RT
  Size:   1 contract equivalent (100 oz)

Sample: 2010-2018 in-sample, 2019-2026 OOS.

Usage:
  python far_weekly_gold_seed2_countertrend.py --start 2010-01-01 --end 2018-12-31 --label TRAIN
  python far_weekly_gold_seed2_countertrend.py --start 2019-01-01 --end 2026-07-29 --label OOS
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse v1 infrastructure
import importlib.util
spec = importlib.util.spec_from_file_location(
    "v1", str(ROOT / "scripts" / "far_weekly_gold_read.py"))
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)

CONTRACT_SIZE = v1.CONTRACT_SIZE
RT_COST = v1.RT_COST
STOP_ATR_MULT = v1.STOP_ATR_MULT
ATR_PERIOD = v1.ATR_PERIOD

# Seed 2-specific params (FROZEN)
LOOKBACK_EXTREME_WEEKS = 4
LOOKBACK_TREND_WEEKS = 8


def resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Resample daily bars to weekly. Week ends Friday."""
    weekly = daily.resample("W-FRI").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    ).dropna()
    return weekly


def build_seed2_signal(daily: pd.DataFrame) -> pd.DataFrame:
    """Compute Seed 2 direction on WEEKLY bars, then map to daily signal_date.

    Returns DataFrame indexed by daily dates, with columns:
      direction: LONG/SHORT/FLAT (as of that daily bar's Friday's week)
      ATR: 20-day ATR
      week_high_4w, week_low_4w, close_8w_ago: signal components
    """
    weekly = resample_weekly(daily)
    weekly["high_4w"] = weekly["high"].shift(1).rolling(LOOKBACK_EXTREME_WEEKS).max()
    weekly["low_4w"] = weekly["low"].shift(1).rolling(LOOKBACK_EXTREME_WEEKS).min()
    weekly["close_8w_ago"] = weekly["close"].shift(LOOKBACK_TREND_WEEKS)

    # Signal per week: check current week's extreme vs prior 4-week extreme
    # + medium-term trend confirmation
    long_cond = ((weekly["low"] <= weekly["low_4w"]) &
                 (weekly["close"] > weekly["close_8w_ago"]))
    short_cond = ((weekly["high"] >= weekly["high_4w"]) &
                  (weekly["close"] < weekly["close_8w_ago"]))
    weekly["direction"] = np.where(long_cond, "LONG",
                                    np.where(short_cond, "SHORT", "FLAT"))

    # Map back to daily: each daily bar gets the direction of the week it belongs to.
    # Actually — we need signal_date = Friday of prior week, then trade Monday.
    # So for each Friday in weekly index, that Friday IS the signal_date, and we
    # trade the following week.
    df = daily.copy()
    df["ATR"] = v1.compute_atr(df, ATR_PERIOD)
    # Attach weekly direction to each Friday (align on date)
    daily_direction = pd.Series("FLAT", index=df.index)
    high_4w = pd.Series(np.nan, index=df.index)
    low_4w = pd.Series(np.nan, index=df.index)
    close_8w = pd.Series(np.nan, index=df.index)
    for wk_end, row in weekly.iterrows():
        # Match daily index to the last daily bar on/before wk_end (Friday)
        mask = df.index <= wk_end
        if not mask.any():
            continue
        last_daily = df.index[mask][-1]
        # Only assign if within 5 days of Friday (avoid mismatched holidays)
        if (wk_end - last_daily).days > 5:
            continue
        daily_direction.loc[last_daily] = row["direction"]
        high_4w.loc[last_daily] = row["high_4w"]
        low_4w.loc[last_daily] = row["low_4w"]
        close_8w.loc[last_daily] = row["close_8w_ago"]
    df["direction"] = daily_direction
    df["high_4w"] = high_4w
    df["low_4w"] = low_4w
    df["close_8w_ago"] = close_8w
    return df


def backtest_seed2(start: pd.Timestamp, end: pd.Timestamp) -> dict:
    # Load with buffer so 8-week lookback + ATR both have data
    buffer_start = start - pd.Timedelta(days=90)
    daily = v1.load_daily_bars(buffer_start, end)
    df = build_seed2_signal(daily)

    # Filter to [start, end] range for TRADING (signals may reference prior data)
    df_trade = df[(df.index >= start) & (df.index <= end)]
    weeks = v1.week_indices(df_trade)

    trades = []
    flat_count = 0
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index:
            continue
        sig_row = df.loc[signal_date]
        direction = sig_row.get("direction", "FLAT")

        if direction == "FLAT":
            flat_count += 1
            continue

        if pd.isna(sig_row["ATR"]):
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

        week_slice = df.loc[mon:fri]
        result = v1.simulate_week(week_slice, mon, fri, direction,
                                   entry_price, stop_price)
        if result:
            result["signal_date"] = signal_date
            trades.append(result)

    return {"trades": trades, "flat_weeks": flat_count,
            "total_weeks": len(weeks)}


def year_breakdown(trades: list) -> dict:
    """P&L and Sharpe per year."""
    by_year = {}
    for t in trades:
        y = t["week_start"].year
        by_year.setdefault(y, []).append(t["net"])
    out = {}
    for y, pnls in sorted(by_year.items()):
        n = len(pnls)
        total = sum(pnls)
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n if n else 0
        # rough Sharpe per year
        arr = np.array(pnls)
        sharpe = arr.mean() / arr.std(ddof=1) * np.sqrt(52 / n) if n > 1 and arr.std(ddof=1) > 0 else 0
        out[y] = {"n": n, "total": total, "wr": wr, "sharpe": sharpe}
    return out


def profit_factor(trades: list) -> float:
    pnls = [t["net"] for t in trades]
    gains = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    return gains / losses if losses > 0 else float("inf")


def daily_returns_correlation_with_v1(seed2_trades: list, v1_trades: list) -> float:
    """Compute R^2 correlation of weekly P&L series (Davey Ch 15 diversification)."""
    if not seed2_trades or not v1_trades:
        return None
    s2 = pd.Series({t["week_start"].date(): t["net"] for t in seed2_trades})
    v = pd.Series({t["week_start"].date(): t["net"] for t in v1_trades})
    joined = pd.concat([s2.rename("s2"), v.rename("v1")], axis=1).fillna(0)
    if len(joined) < 5:
        return None
    corr = joined["s2"].corr(joined["v1"])
    return corr ** 2 if corr is not None else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--label", default="RUN")
    ap.add_argument("--breakdown", action="store_true",
                    help="Print per-year breakdown")
    ap.add_argument("--compare-v1", action="store_true",
                    help="Compute diversification R^2 vs v1 on same window")
    args = ap.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    result = backtest_seed2(start, end)
    summary = v1.report(args.label, result["trades"], result["flat_weeks"],
                        result["total_weeks"])

    pf = profit_factor(result["trades"])
    print(f"  Profit factor:    {pf:.3f}")
    if summary and summary.get("max_dd", 0) < 0:
        r_dd = summary["total_pnl"] / abs(summary["max_dd"])
        print(f"  Return / MaxDD:   {r_dd:.3f}")

    if args.breakdown:
        yb = year_breakdown(result["trades"])
        print(f"\n  === Per-year breakdown ===")
        print(f"  {'Year':<6}{'n':>5}{'Total':>12}{'WR':>8}{'Sharpe':>10}")
        pos_years = 0
        for y, d in yb.items():
            marker = "+" if d["sharpe"] > 0 else "-"
            if d["sharpe"] > 0:
                pos_years += 1
            print(f"  {y:<6}{d['n']:>5}${d['total']:>10,.0f}{100*d['wr']:>7.1f}%{d['sharpe']:>10.3f} {marker}")
        print(f"\n  Positive-Sharpe years: {pos_years} of {len(yb)}")

    if args.compare_v1:
        print(f"\n  === Diversification vs v1 (same window) ===")
        try:
            v1_result = v1.backtest(start, end)
            r_sq = daily_returns_correlation_with_v1(result["trades"],
                                                     v1_result["trades"])
            if r_sq is not None:
                print(f"  R^2 (weekly P&L series):  {r_sq:.4f}")
                print(f"  Gate 7 (R^2 < 0.30):      "
                      f"{'PASS' if r_sq < 0.30 else 'FAIL'}")
            else:
                print(f"  R^2:                      N/A (insufficient overlap)")
        except Exception as e:
            print(f"  v1 compare failed: {e}")


if __name__ == "__main__":
    main()
