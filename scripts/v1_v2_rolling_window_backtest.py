"""Rolling 5-year window backtest for v1 and v2.

Question: is v1's edge time-stable, or concentrated in specific
years? The headline Sharpe 0.77 is a full-sample average - it
could hide a great early period and a bad recent one, or vice versa.

Method: slide a 5-year window across 2010-2026 in 1-year steps.
For each window, compute Sharpe/WR/cum for v1 and v2. Report the
distribution and identify any window where the edge collapses.

If Sharpe is stable across all windows: robust, time-invariant edge.
If Sharpe collapses in one window: that period represents a regime
where the strategy failed; worth understanding what changed.

Usage: python scripts/v1_v2_rolling_window_backtest.py
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location(
    "far", str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

DXY_PATH = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"


def load_signals() -> pd.DataFrame:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-08-31", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    df = far.build_signals(daily, ry)
    dxy = far.load_macro_series(DXY_PATH, "dxy")
    dxy_daily = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                             method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(far.RY_LAG)
    return df


def v2_dir(v1: str, dxy_chg: float | None) -> str:
    if v1 == "LONG" and dxy_chg is not None and dxy_chg < 0: return "LONG"
    if v1 == "SHORT" and dxy_chg is not None and dxy_chg > 0: return "SHORT"
    return "FLAT"


def collect_trades(df: pd.DataFrame, variant: str) -> list[dict]:
    weeks = far.week_indices(df)
    out = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        v1 = str(sig["direction"])
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")):
            continue
        dxy_chg = float(sig["DXY_chg"]) if pd.notna(sig.get("DXY_chg")) else None
        direction = v1 if variant == "v1" else v2_dir(v1, dxy_chg)
        if direction == "FLAT":
            continue
        entry = float(df.loc[mon, "open"])
        atr = float(sig["ATR"])
        if atr <= 0: continue
        stop = entry - far.STOP_ATR_MULT * atr if direction == "LONG" else entry + far.STOP_ATR_MULT * atr
        r = far.simulate_week(df.loc[mon:fri], mon, fri, direction, entry, stop)
        if not r: continue
        out.append({
            "signal_date": signal_date,
            "year": signal_date.year,
            "net": r["net"],
            "ret": r["net"] / (entry * far.CONTRACT_SIZE),
        })
    return out


def window_stats(trades: list[dict], start_year: int, end_year: int) -> dict:
    subset = [t for t in trades if start_year <= t["year"] <= end_year]
    n = len(subset)
    if n == 0: return {"n": 0}
    rets = [t["ret"] for t in subset]
    pnls = [t["net"] for t in subset]
    wins = sum(1 for p in pnls if p > 0)
    mean_r = sum(rets) / n
    std_r = ((sum((r - mean_r) ** 2 for r in rets) / (n - 1)) ** 0.5) if n > 1 else 0.0
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0
    return {
        "n": n, "wr": round(100 * wins / n, 1),
        "mean_pct": round(100 * mean_r, 3),
        "sharpe": round(sharpe, 3),
        "cum": round(sum(pnls), 0),
    }


def main() -> None:
    print("[load]")
    df = load_signals()

    v1_trades = collect_trades(df, "v1")
    v2_trades = collect_trades(df, "v2")

    print(f"[collect] v1: {len(v1_trades)} trades   v2: {len(v2_trades)} trades")
    print()

    print("=== ROLLING 5-YEAR WINDOWS (start_year to start_year+4) ===")
    print(f"  {'window':<12} {'v1 n':>5} {'v1 Sharpe':>10} {'v1 WR':>7} "
          f"{'v1 cum $':>11}   {'v2 n':>5} {'v2 Sharpe':>10} {'v2 WR':>7} {'v2 cum $':>11}")
    print("-" * 110)
    for start in range(2010, 2023):  # 2010-2014, ..., 2022-2026
        end = start + 4
        v1_s = window_stats(v1_trades, start, end)
        v2_s = window_stats(v2_trades, start, end)
        if v1_s.get("n", 0) == 0: continue
        print(f"  {start}-{end}  "
              f"{v1_s['n']:>5} "
              f"{v1_s['sharpe']:>+10.3f} "
              f"{v1_s['wr']:>6.1f}% "
              f"${v1_s['cum']:>10,.0f}   "
              f"{v2_s.get('n', 0):>5} "
              f"{v2_s.get('sharpe', 0):>+10.3f} "
              f"{v2_s.get('wr', 0):>6.1f}% "
              f"${v2_s.get('cum', 0):>10,.0f}")
    print()

    print("=== YEAR-BY-YEAR (n / WR / Sharpe / cum) ===")
    print(f"  {'year':<6} {'v1 n':>5} {'v1 WR':>7} {'v1 Sh':>7} {'v1 cum':>9}   "
          f"{'v2 n':>5} {'v2 WR':>7} {'v2 Sh':>7} {'v2 cum':>9}")
    for y in range(2010, 2027):
        v1_s = window_stats(v1_trades, y, y)
        v2_s = window_stats(v2_trades, y, y)
        if v1_s.get("n", 0) == 0: continue
        print(f"  {y:<6} "
              f"{v1_s['n']:>5} {v1_s['wr']:>6.1f}% {v1_s['sharpe']:>+7.3f} ${v1_s['cum']:>7,.0f}   "
              f"{v2_s.get('n',0):>5} {v2_s.get('wr',0):>6.1f}% {v2_s.get('sharpe',0):>+7.3f} ${v2_s.get('cum',0):>7,.0f}")


if __name__ == "__main__":
    main()
