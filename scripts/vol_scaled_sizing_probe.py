"""Volatility-scaled position sizing probe.

Current v1 uses 1 fixed contract per trade. Since ATR varies from
~$5 (2015 low-vol regime) to ~$100 (2026 high-vol), a $ risk per
trade varies by 20x across the sample. High-ATR trades dominate the
P&L variance and drawdowns.

Alternative: size by 1/ATR to hold constant dollar risk per trade.
Position = risk_target / (2 x ATR x contract_size).

Question: does vol-target sizing improve Sharpe? Sharpe is scale-
invariant to sizing multiplier, so it depends on whether the mean
return / std ratio changes when we equal-weight the trades.

Test: v1 and v2 with:
  - 1 fixed contract (shipping baseline)
  - vol-target $2,500 risk per trade (about what 1 contract at avg ATR represented)
  - vol-target $2,500 with 5-contract cap (retail-realistic)

Report Sharpe, cum P&L (scaled), and max drawdown.

Usage: python scripts/vol_scaled_sizing_probe.py
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
RISK_TARGET_USD = 2500.0


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


def backtest_with_sizing(df: pd.DataFrame, variant: str,
                          sizing: str, cap: float | None = None) -> dict:
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
        if atr <= 0:
            continue

        # Sizing: contracts count
        if sizing == "fixed_1":
            contracts = 1.0
        elif sizing == "vol_target":
            per_contract_risk = 2 * atr * far.CONTRACT_SIZE  # $ per contract if stop hits
            contracts = RISK_TARGET_USD / per_contract_risk
            if cap is not None:
                contracts = min(contracts, cap)
        else:
            raise ValueError(sizing)

        if direction == "LONG":
            stop = entry - far.STOP_ATR_MULT * atr
        else:
            stop = entry + far.STOP_ATR_MULT * atr
        r = far.simulate_week(df.loc[mon:fri], mon, fri, direction, entry, stop)
        if not r:
            continue
        # Scale P&L by contracts (base simulate uses 1 contract)
        scaled_net = r["net"] * contracts
        # Return-on-nominal per contract stays same but with scaled dollar
        base_ret = r["net"] / (entry * far.CONTRACT_SIZE)
        trades.append({
            "net": scaled_net,
            "ret": base_ret,  # per-contract return still % of nominal
            "contracts": contracts,
        })

    n = len(trades)
    if n == 0: return {"n": 0}
    rets = [t["ret"] for t in trades]
    pnls = [t["net"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    mean_r = sum(rets) / n
    std_r = ((sum((r - mean_r) ** 2 for r in rets) / (n - 1)) ** 0.5) if n > 1 else 0.0
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0

    # Recompute Sharpe on dollar-P&L series (more appropriate for
    # different sizing schemes)
    mean_p = sum(pnls) / n
    std_p = ((sum((p - mean_p) ** 2 for p in pnls) / (n - 1)) ** 0.5) if n > 1 else 0.0
    sharpe_dollar = (mean_p / std_p) * math.sqrt(52) if std_p > 0 else 0.0

    # Max drawdown
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(np.concatenate([[0], equity]))[1:]
    dd = peak - equity
    max_dd = float(np.max(dd)) if len(dd) else 0.0

    contracts_med = np.median([t["contracts"] for t in trades])

    return {
        "n": n, "wr": round(100 * wins / n, 1),
        "mean_pnl": round(mean_p, 2),
        "sharpe_dollar": round(sharpe_dollar, 3),
        "cum": round(sum(pnls), 0),
        "max_dd": round(max_dd, 0),
        "contracts_med": round(contracts_med, 2),
    }


def line(label: str, s: dict) -> str:
    if s.get("n", 0) == 0: return f"  {label:<40} n=0"
    return (f"  {label:<40} n={s['n']:>3}  WR={s['wr']:>5.1f}%  "
            f"contracts_med={s['contracts_med']:>4.2f}  "
            f"Sharpe_$={s['sharpe_dollar']:>+6.3f}  "
            f"cum=${s['cum']:>10,.0f}  maxDD=${s['max_dd']:>8,.0f}")


def main() -> None:
    print("[load]")
    df = load_signals()
    print(f"risk target per trade (vol-target): ${RISK_TARGET_USD:,.0f}\n")

    for variant in ("v1", "v2"):
        print(f"=== {variant} ===")
        print(line("fixed 1 contract (shipping)", backtest_with_sizing(df, variant, "fixed_1")))
        print(line("vol-target no cap",            backtest_with_sizing(df, variant, "vol_target")))
        print(line("vol-target 5-contract cap",    backtest_with_sizing(df, variant, "vol_target", cap=5)))
        print()

    # Also look at return/DD ratio (Calmar-like) for the comparisons
    print("=== return/max-DD ratios ===")
    for variant in ("v1", "v2"):
        for sizing, label in [("fixed_1", "fixed"), ("vol_target", "voltar"), ("vol_target-cap", "voltar-cap")]:
            cap = 5 if "cap" in sizing else None
            s = backtest_with_sizing(df, variant, sizing.replace("-cap",""), cap=cap)
            if s.get("cum") and s.get("max_dd"):
                r = s["cum"] / s["max_dd"]
                print(f"  {variant:<4} {label:<12} cum/DD = {r:.2f}x")


if __name__ == "__main__":
    main()
