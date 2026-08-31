"""Signal-strength gradient probe for v1.

v1 uses a binary gate: 4-of-4 conditions align OR FLAT. Question:
what does 3-of-4 look like? 2-of-4? Does the binary gate correctly
identify where the edge is, or could a gradient scoring help?

For each week, compute:
  long_score  = sum of (M20>0, M60>0, MA10>MA40, RY_chg<0)
  short_score = sum of (M20<0, M60<0, MA10<MA40, RY_chg>0)

Then simulate trades at:
  score>=4 (v1's actual rule)
  score>=3 (relaxed: 3-of-4 counts)
  score>=2 (very relaxed)

Direction: LONG if long_score > short_score, SHORT if short_score > long_score.

Report Sharpe, WR, cum per level. Interpretation:
  - If 4-of-4 has much better Sharpe than 3-of-4: v1's gate is well-
    calibrated
  - If 3-of-4 has comparable Sharpe with 3x more trades: the gate
    is too strict; a gradient version could add value
  - If 2-of-4 loses money: v1's condition set has real signal

Also test "3-of-4 only" (exactly 3, not >=3) to isolate the 3-condition
subset.

Usage: python scripts/v1_signal_strength_gradient.py
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


def load_signals() -> pd.DataFrame:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-08-31", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    return far.build_signals(daily, ry)


def add_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["long_score"] = ((df["M20"] > 0).astype(int)
                         + (df["M60"] > 0).astype(int)
                         + (df["MA10"] > df["MA40"]).astype(int)
                         + (df["RY_chg"] < 0).astype(int))
    df["short_score"] = ((df["M20"] < 0).astype(int)
                          + (df["M60"] < 0).astype(int)
                          + (df["MA10"] < df["MA40"]).astype(int)
                          + (df["RY_chg"] > 0).astype(int))
    return df


def simulate(df: pd.DataFrame, min_score: int, exact: bool = False) -> dict:
    weeks = far.week_indices(df)
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")):
            continue
        ls = int(sig["long_score"]); ss = int(sig["short_score"])
        # Direction: whichever side has the higher score and clears min
        if ls > ss and ls >= min_score and (not exact or ls == min_score):
            direction = "LONG"
        elif ss > ls and ss >= min_score and (not exact or ss == min_score):
            direction = "SHORT"
        else:
            continue

        entry = float(df.loc[mon, "open"])
        atr = float(sig["ATR"])
        if atr <= 0: continue
        stop = entry - far.STOP_ATR_MULT * atr if direction == "LONG" else entry + far.STOP_ATR_MULT * atr
        r = far.simulate_week(df.loc[mon:fri], mon, fri, direction, entry, stop)
        if not r: continue
        trades.append({
            "net": r["net"],
            "ret": r["net"] / (entry * far.CONTRACT_SIZE),
        })
    n = len(trades)
    if n == 0: return {"n": 0}
    rets = [t["ret"] for t in trades]
    pnls = [t["net"] for t in trades]
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


def line(label: str, s: dict) -> str:
    if s.get("n", 0) == 0: return f"  {label:<40} n=0"
    return (f"  {label:<40} n={s['n']:>3}  WR={s['wr']:>5.1f}%  "
            f"mean={s['mean_pct']:>+7.3f}%  Sharpe={s['sharpe']:>+7.3f}  "
            f"cum=${s['cum']:>10,.0f}")


def main() -> None:
    print("[load]")
    df = add_scores(load_signals())
    print()

    print("=== SIGNAL-STRENGTH GRADIENT ===")
    print(line("min_score >= 4 (v1 baseline)",  simulate(df, 4)))
    print(line("min_score >= 3",                simulate(df, 3)))
    print(line("min_score >= 2",                simulate(df, 2)))
    print()

    print("=== EXACT SCORE PARTITIONS ===")
    print(line("score == 4 (v1 baseline)",       simulate(df, 4, exact=True)))
    print(line("score == 3 (weakest v1 exclude)", simulate(df, 3, exact=True)))
    print(line("score == 2 (mixed)",              simulate(df, 2, exact=True)))
    print()

    # Distribution of scores
    print("=== SCORE DISTRIBUTION ===")
    for s in range(0, 5):
        n_long = int((df["long_score"] == s).sum())
        n_short = int((df["short_score"] == s).sum())
        print(f"  score={s}   long_side_weeks={n_long:>4}   short_side_weeks={n_short:>4}")


if __name__ == "__main__":
    main()
