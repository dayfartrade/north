"""Universe expansion probe: apply v1's exact rule structure natively
to platinum, palladium, GDX, GDXJ. This is a DATA PROBE, not a ship
gate. Purpose: find out whether the gold-momentum family generalizes
to other precious metals or mining equities.

Rule (identical to gold v1):
    LONG  if M20 > 0 AND M60 > 0 AND MA10 > MA40 AND RY_chg < 0
    SHORT if M20 < 0 AND M60 < 0 AND MA10 < MA40 AND RY_chg > 0
    FLAT  otherwise

Trade cycle (identical to v1):
    Signal at Friday close, enter Monday open, exit Friday close.
    2 x ATR(20) stop from entry.

Notional normalization:
    Each asset trades 1 unit (share for ETFs, contract for futures).
    Comparisons are made on percent-return per trade, not dollar P&L,
    so contract sizes and share prices are apples-to-apples.

Usage:
    python scripts/universe_v1_probe.py --asset platinum
    python scripts/universe_v1_probe.py --asset gdx --start 2010-01-01 --end 2026-08-14
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

ASSETS = {
    "platinum":  {"csv": ROOT / "data/universe/platinum_daily.csv",  "label": "Platinum futures (PL=F)"},
    "palladium": {"csv": ROOT / "data/universe/palladium_daily.csv", "label": "Palladium futures (PA=F)"},
    "gdx":       {"csv": ROOT / "data/universe/gdx_daily.csv",       "label": "VanEck Gold Miners (GDX)"},
    "gdxj":      {"csv": ROOT / "data/universe/gdxj_daily.csv",      "label": "VanEck Junior Gold Miners (GDXJ)"},
}

RY_CSV = ROOT / "data/macro/real_yield_10y__DFII10.csv"

M20_LAG = 20
M60_LAG = 60
MA_SHORT = 10
MA_LONG = 40
RY_LAG = 20
ATR_PERIOD = 20
STOP_ATR_MULT = 2.0


def load_asset_daily(csv_path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df = df[(df.index >= start - pd.Timedelta(days=100)) & (df.index <= end)]
    df = df[df.index.weekday < 5]
    return df


def load_real_yield() -> pd.Series:
    df = pd.read_csv(RY_CSV, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df["value"].rename("real_yield_10y")


def compute_atr(bars: pd.DataFrame, n: int) -> pd.Series:
    high = bars["high"]; low = bars["low"]; close_prev = bars["close"].shift(1)
    tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def build_signals(daily: pd.DataFrame, ry: pd.Series) -> pd.DataFrame:
    df = daily.copy()
    df["M20"] = df["close"].pct_change(M20_LAG)
    df["M60"] = df["close"].pct_change(M60_LAG)
    df["MA10"] = df["close"].rolling(MA_SHORT).mean()
    df["MA40"] = df["close"].rolling(MA_LONG).mean()
    df["ATR"] = compute_atr(df, ATR_PERIOD)

    idx_naive = df.index.tz_localize(None) if df.index.tz else df.index
    ry_daily = ry.reindex(idx_naive, method="ffill")
    ry_daily.index = df.index
    df["RY"] = ry_daily
    df["RY_chg"] = df["RY"].diff(RY_LAG)

    long_cond = ((df["M20"] > 0) & (df["M60"] > 0) & (df["MA10"] > df["MA40"]) & (df["RY_chg"] < 0))
    short_cond = ((df["M20"] < 0) & (df["M60"] < 0) & (df["MA10"] < df["MA40"]) & (df["RY_chg"] > 0))
    df["direction"] = np.where(long_cond, "LONG", np.where(short_cond, "SHORT", "FLAT"))
    return df


def week_indices(daily: pd.DataFrame):
    weeks = []
    df = daily.copy()
    df["iso_year"] = df.index.isocalendar().year
    df["iso_week"] = df.index.isocalendar().week
    for _, grp in df.groupby(["iso_year", "iso_week"]):
        if len(grp) < 2:
            continue
        monday = grp.index[grp.index.weekday == 0]
        friday = grp.index[grp.index.weekday == 4]
        if len(monday) == 0 or len(friday) == 0:
            continue
        mon = monday[0]; fri = friday[-1]
        prior_days = df.index[df.index < mon]
        if len(prior_days) == 0:
            continue
        weeks.append((prior_days[-1], mon, fri))
    return weeks


def backtest(asset_key: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    cfg = ASSETS[asset_key]
    daily = load_asset_daily(cfg["csv"], start, end)
    ry = load_real_yield()
    signals = build_signals(daily, ry)
    signals = signals[(signals.index >= start) & (signals.index <= end)]
    weeks = week_indices(signals)

    trades = []
    flat = 0
    for signal_date, mon, fri in weeks:
        if signal_date not in signals.index:
            continue
        row = signals.loc[signal_date]
        direction = row["direction"]
        if direction == "FLAT":
            flat += 1
            continue
        if pd.isna(row["ATR"]) or pd.isna(row["M60"]) or pd.isna(row["RY_chg"]):
            continue
        atr = float(row["ATR"])
        if atr <= 0:
            continue
        if mon not in signals.index:
            continue
        entry = float(signals.loc[mon, "open"])
        stop = entry - STOP_ATR_MULT * atr if direction == "LONG" else entry + STOP_ATR_MULT * atr
        week_bars = signals.loc[mon:fri]
        exit_price = None
        exit_reason = None
        for _, r in week_bars.iterrows():
            if direction == "LONG":
                if float(r["low"]) <= stop:
                    exit_price = stop; exit_reason = "stop"; break
            else:
                if float(r["high"]) >= stop:
                    exit_price = stop; exit_reason = "stop"; break
        if exit_price is None:
            exit_price = float(week_bars.iloc[-1]["close"])
            exit_reason = "time"
        dir_sign = 1 if direction == "LONG" else -1
        ret_pct = (exit_price - entry) * dir_sign / entry
        trades.append({
            "signal_date": signal_date, "week_start": mon,
            "direction": direction, "entry": entry, "exit": exit_price,
            "exit_reason": exit_reason, "return_pct": ret_pct,
        })
    return {"trades": trades, "flat_weeks": flat, "total_weeks": len(weeks)}


def summarize(trades: list[dict], label: str) -> None:
    n = len(trades)
    if n == 0:
        print(f"  {label}: no trades")
        return
    rets = [t["return_pct"] for t in trades]
    wins = sum(1 for r in rets if r > 0)
    total = sum(rets)
    mean = total / n
    if n > 1:
        std = (sum((r - mean) ** 2 for r in rets) / (n - 1)) ** 0.5
    else:
        std = 0.0
    sharpe = (mean / std) * math.sqrt(52) if std > 0 else 0.0
    equity = []
    running = 0.0
    for r in rets:
        running += r
        equity.append(running)
    peak = 0.0; max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    by_year = defaultdict(list)
    for t in trades:
        by_year[str(t["week_start"])[:4]].append(t["return_pct"])
    positive_years = sum(1 for _, tp in by_year.items() if sum(tp) > 0)
    print(f"  {label}:  n={n}  WR={100*wins/n:.1f}%")
    print(f"    mean R:       {100*mean:+.3f}%")
    print(f"    std R:        {100*std:.3f}%")
    print(f"    Sharpe (ann): {sharpe:+.3f}")
    print(f"    total cum R:  {100*total:+.2f}%")
    print(f"    max DD:       {100*max_dd:.2f}%")
    print(f"    positive yrs: {positive_years}/{len(by_year)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", choices=list(ASSETS.keys()) + ["all"], default="all")
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-08-14")
    args = ap.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    assets = list(ASSETS.keys()) if args.asset == "all" else [args.asset]

    print(f"UNIVERSE V1 PROBE: {args.start} to {args.end}")
    print("Signal: gold v1 rules applied to each asset's own price series.")
    print("This is a DATA PROBE, not a ship gate.\n")

    for asset_key in assets:
        cfg = ASSETS[asset_key]
        print(f"{'='*68}\n {cfg['label']}\n{'='*68}")
        r = backtest(asset_key, start, end)
        total = r["total_weeks"]
        flat = r["flat_weeks"]
        n = len(r["trades"])
        print(f"Signal weeks: {total}   FLAT: {flat} ({100*flat/max(total,1):.0f}%)   Traded: {n}")
        summarize(r["trades"], "all")
        summarize([t for t in r["trades"] if t["direction"] == "LONG"], "long")
        summarize([t for t in r["trades"] if t["direction"] == "SHORT"], "short")
        print()


if __name__ == "__main__":
    main()
