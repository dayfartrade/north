"""Cost sensitivity audit for v1 and v2.

The shipping v1 backtest uses $5 round-trip cost (IBKR-realistic for
a single GC contract). Question: does the edge survive higher costs
that a retail subscriber might actually pay (retail futures, GLD
options, wider spreads)?

Test v1 and v2 at RT costs: $5 (baseline), $10, $15, $25, $50.

At each cost level, compute Sharpe/WR/mean/cum for v1 and v2 across
the full 16-year sample.

Interpretation:
  - If edge survives $25+ cost: robust; safe for retail
  - If edge dies at $10-15: shipping cost is close to breakeven,
    disclosure must include this
  - If edge dies at $5 with a small perturbation: fragile, questionable

Usage: python scripts/v1_v2_cost_sensitivity.py
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
COSTS = [5, 10, 15, 25, 50]


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
    if v1 == "LONG" and dxy_chg is not None and dxy_chg < 0:
        return "LONG"
    if v1 == "SHORT" and dxy_chg is not None and dxy_chg > 0:
        return "SHORT"
    return "FLAT"


def simulate_week_custom_cost(daily: pd.DataFrame, mon: pd.Timestamp,
                                fri: pd.Timestamp, direction: str,
                                entry_price: float, stop_price: float,
                                rt_cost: float) -> dict | None:
    """Replica of far.simulate_week but with parameterized cost."""
    week_bars = daily[(daily.index >= mon) & (daily.index <= fri)]
    if len(week_bars) == 0:
        return None
    dir_sign = 1 if direction == "LONG" else -1
    exit_price = None
    for _, row in week_bars.iterrows():
        if direction == "LONG":
            if float(row["low"]) <= stop_price:
                exit_price = stop_price; break
        else:
            if float(row["high"]) >= stop_price:
                exit_price = stop_price; break
    if exit_price is None:
        exit_price = float(week_bars.iloc[-1]["close"])
    gross = (exit_price - entry_price) * dir_sign * far.CONTRACT_SIZE
    net = gross - rt_cost
    return {"gross": gross, "net": net, "entry": entry_price}


def backtest_at_cost(df: pd.DataFrame, variant: str, rt_cost: float) -> dict:
    weeks = far.week_indices(df)
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        v1 = str(sig["direction"])
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")):
            continue
        dxy_chg = float(sig["DXY_chg"]) if pd.notna(sig.get("DXY_chg")) else None
        if variant == "v1":
            direction = v1
        elif variant == "v2":
            direction = v2_dir(v1, dxy_chg)
        else:
            raise ValueError(variant)
        if direction == "FLAT":
            continue
        entry = float(df.loc[mon, "open"])
        atr = float(sig["ATR"])
        if atr <= 0:
            continue
        if direction == "LONG":
            stop = entry - far.STOP_ATR_MULT * atr
        else:
            stop = entry + far.STOP_ATR_MULT * atr
        r = simulate_week_custom_cost(df.loc[mon:fri], mon, fri, direction,
                                        entry, stop, rt_cost)
        if not r:
            continue
        trades.append({
            "net": r["net"],
            "ret": r["net"] / (r["entry"] * far.CONTRACT_SIZE),
        })
    n = len(trades)
    if n == 0:
        return {"n": 0}
    rets = [t["ret"] for t in trades]
    pnls = [t["net"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    mean_r = sum(rets) / n
    std_r = ((sum((r - mean_r) ** 2 for r in rets) / (n - 1)) ** 0.5) if n > 1 else 0.0
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0
    return {
        "n": n,
        "wr": round(100 * wins / n, 1),
        "mean_pct": round(100 * mean_r, 3),
        "sharpe": round(sharpe, 3),
        "cum": round(sum(pnls), 0),
    }


def main() -> None:
    print("[load]")
    df = load_signals()
    print()
    print(f"{'variant':<8} {'cost':>7} {'n':>5} {'WR':>6} {'mean%':>8} {'Sharpe':>8} {'cum $':>12}")
    print("-" * 60)
    for variant in ("v1", "v2"):
        for c in COSTS:
            s = backtest_at_cost(df, variant, c)
            print(f"{variant:<8} ${c:>6} {s.get('n',0):>5} "
                  f"{s.get('wr',0):>5.1f}% {s.get('mean_pct',0):>+7.3f}% "
                  f"{s.get('sharpe',0):>+7.3f} ${s.get('cum',0):>10,.0f}")
        print()

    # Breakeven cost (where cumulative crosses zero)
    print("=== Breakeven cost estimate (linear interpolation) ===")
    for variant in ("v1", "v2"):
        # Compute total gross P&L at cost=0 and n trades
        s5 = backtest_at_cost(df, variant, 5)
        gross_pnl = s5["cum"] + s5["n"] * 5  # net + total cost = gross
        breakeven_per_trade = gross_pnl / s5["n"] if s5["n"] else 0
        print(f"  {variant}: gross mean P&L per trade = ${breakeven_per_trade:.2f}   "
              f"n={s5['n']}")


if __name__ == "__main__":
    main()
