"""Stop-multiplier robustness for v1 and v2.

v1 uses 2xATR stop, picked pre-reg before backtest. Test whether that
choice is well-calibrated or arbitrary. Sweep 1.0, 1.5, 2.0 (baseline),
2.5, 3.0 xATR.

For each multiplier, compute Sharpe/WR/cum/max-DD.

Interpretation:
  - If 2.0x is near the peak: robust, not lucky
  - If a wider stop (2.5+) is dramatically better: v1's stop is too tight
  - If a tighter stop (1.5) is much better: too wide

Usage: python scripts/v1_v2_stop_multiplier_robustness.py
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
MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]


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


def simulate_variant_with_stop(df: pd.DataFrame, variant: str,
                                stop_mult: float) -> dict:
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
        direction = v1 if variant == "v1" else v2_dir(v1, dxy_chg)
        if direction == "FLAT":
            continue
        entry = float(df.loc[mon, "open"])
        atr = float(sig["ATR"])
        if atr <= 0: continue
        stop = entry - stop_mult * atr if direction == "LONG" else entry + stop_mult * atr
        r = far.simulate_week(df.loc[mon:fri], mon, fri, direction, entry, stop)
        if not r: continue
        trades.append({
            "net": r["net"],
            "ret": r["net"] / (entry * far.CONTRACT_SIZE),
            "exit_reason": r.get("exit_reason", "unknown"),
        })
    n = len(trades)
    if n == 0: return {"n": 0}
    rets = [t["ret"] for t in trades]
    pnls = [t["net"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    stops = sum(1 for t in trades if t["exit_reason"] == "stop")
    mean_r = sum(rets) / n
    std_r = ((sum((r - mean_r) ** 2 for r in rets) / (n - 1)) ** 0.5) if n > 1 else 0.0
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0

    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    max_dd = float(np.max(peak - equity)) if len(equity) else 0.0

    return {
        "n": n, "wr": round(100 * wins / n, 1),
        "stop_rate": round(100 * stops / n, 1),
        "sharpe": round(sharpe, 3),
        "cum": round(sum(pnls), 0),
        "max_dd": round(max_dd, 0),
    }


def line(label: str, s: dict) -> str:
    if s.get("n", 0) == 0: return f"  {label:<20} n=0"
    return (f"  {label:<20} n={s['n']:>3}  WR={s['wr']:>5.1f}%  "
            f"stop-hit={s['stop_rate']:>5.1f}%  "
            f"Sharpe={s['sharpe']:>+7.3f}  "
            f"cum=${s['cum']:>10,.0f}  maxDD=${s['max_dd']:>8,.0f}")


def main() -> None:
    print("[load]")
    df = load_signals()

    for variant in ("v1", "v2"):
        print(f"\n=== {variant} - stop multiplier sweep ===")
        for m in MULTS:
            mark = "  <-- shipped" if m == 2.0 else ""
            s = simulate_variant_with_stop(df, variant, m)
            print(line(f"{m}xATR", s) + mark)


if __name__ == "__main__":
    main()
