"""Feature probe on the v2-skipped v1 trades.

Follow-on from docs/experiments/2026-08-31_v1_fire_rate_by_v2.md.

Question: the 86 v2-skipped v1 trades collectively lose money (Sharpe
-0.14, cum -$8,538). DXY misalignment is the DEFINING feature by
construction. Is there a SECOND macro/technical feature that also
distinguishes them from the v2-confirmed trades? If yes, could
motivate a v3 candidate that layers a second filter. If no, DXY is
doing the work and further improvement needs a fresh mechanism.

Exploratory: no pre-reg, no ship gate. Fact-finding only.

Features probed at signal_date:
  - M20 magnitude (was v1 firing on marginal or strong momentum?)
  - M60 magnitude
  - MA10-MA40 spread as % of price (trend strength)
  - RY_chg magnitude
  - ATR20 as % of price (volatility regime)
  - Real yield level (not change)
  - Month of year (seasonality)
  - Day-of-year buckets
  - Preceding-week direction and outcome (drift state)

For each feature: compare distribution across (v2-confirmed winners,
v2-confirmed losers, v2-skipped winners, v2-skipped losers) subsets.
Report anything with a >30% median difference or a clear regime
divergence.

Usage: python scripts/v2_skipped_predictor_probe.py
"""
from __future__ import annotations

import importlib.util
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
    df["MA_spread_pct"] = 100 * (df["MA10"] - df["MA40"]) / df["close"]
    df["ATR_pct"] = 100 * df["ATR"] / df["close"]
    return df


def v2_direction(v1: str, dxy_chg: float | None) -> str:
    if v1 == "LONG" and dxy_chg is not None and dxy_chg < 0:
        return "LONG"
    if v1 == "SHORT" and dxy_chg is not None and dxy_chg > 0:
        return "SHORT"
    return "FLAT"


def collect_trades_with_features(df: pd.DataFrame) -> list[dict]:
    weeks = far.week_indices(df)
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        v1 = str(sig["direction"])
        if v1 == "FLAT":
            continue
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")):
            continue
        dxy_chg = float(sig["DXY_chg"]) if pd.notna(sig.get("DXY_chg")) else None
        v2_conf = (v2_direction(v1, dxy_chg) == v1)
        entry = float(df.loc[mon, "open"])
        atr = float(sig["ATR"])
        if atr <= 0:
            continue
        stop = entry - far.STOP_ATR_MULT * atr if v1 == "LONG" else entry + far.STOP_ATR_MULT * atr
        result = far.simulate_week(df.loc[mon:fri], mon, fri, v1, entry, stop)
        if not result:
            continue
        trades.append({
            "signal_date": signal_date,
            "direction": v1,
            "v2_confirmed": v2_conf,
            "won": result["net"] > 0,
            "ret": result["net"] / (entry * far.CONTRACT_SIZE),
            # Features
            "abs_M20": abs(float(sig["M20"])) if pd.notna(sig.get("M20")) else None,
            "abs_M60": abs(float(sig["M60"])) if pd.notna(sig.get("M60")) else None,
            "abs_RY_chg": abs(float(sig["RY_chg"])) if pd.notna(sig.get("RY_chg")) else None,
            "abs_MA_spread_pct": abs(float(sig["MA_spread_pct"])) if pd.notna(sig.get("MA_spread_pct")) else None,
            "ATR_pct": float(sig["ATR_pct"]) if pd.notna(sig.get("ATR_pct")) else None,
            "RY_level": float(sig["RY"]) if pd.notna(sig.get("RY")) else None,
            "month": signal_date.month,
        })
    return trades


def compare_dists(trades: list[dict], feature: str) -> None:
    conf = [t[feature] for t in trades if t["v2_confirmed"] and t[feature] is not None]
    skip = [t[feature] for t in trades if not t["v2_confirmed"] and t[feature] is not None]
    if not conf or not skip:
        return
    mc, ms = np.median(conf), np.median(skip)
    meanc, means = np.mean(conf), np.mean(skip)
    diff_pct = 100 * (ms - mc) / mc if mc != 0 else float("nan")
    print(f"  {feature:<22} confirmed(n={len(conf):>3}) med={mc:>7.3f} mean={meanc:>7.3f}   "
          f"skipped(n={len(skip):>3}) med={ms:>7.3f} mean={means:>7.3f}   "
          f"med_diff={diff_pct:+.1f}%")


def month_seasonality(trades: list[dict]) -> None:
    print("\n=== SEASONALITY: v2-skipped trades by month ===")
    print(f"{'month':<6} {'confirmed':>10} {'skipped':>10} {'skip%':>7} {'skip_win_rate':>15}")
    for m in range(1, 13):
        conf_m = [t for t in trades if t["month"] == m and t["v2_confirmed"]]
        skip_m = [t for t in trades if t["month"] == m and not t["v2_confirmed"]]
        total = len(conf_m) + len(skip_m)
        if total == 0:
            continue
        skip_pct = 100 * len(skip_m) / total
        skip_wr = 100 * sum(1 for t in skip_m if t["won"]) / len(skip_m) if skip_m else float("nan")
        print(f"{m:<6} {len(conf_m):>10} {len(skip_m):>10} {skip_pct:>6.0f}% "
              f"{skip_wr:>14.0f}%" if skip_m else
              f"{m:<6} {len(conf_m):>10} {len(skip_m):>10} {skip_pct:>6.0f}% "
              f"{'-':>15}")


def outcome_split(trades: list[dict], feature: str) -> None:
    """Compare feature between v2-skipped winners and losers."""
    skip = [t for t in trades if not t["v2_confirmed"] and t[feature] is not None]
    if not skip:
        return
    winners = [t[feature] for t in skip if t["won"]]
    losers = [t[feature] for t in skip if not t["won"]]
    if not winners or not losers:
        return
    mw = np.median(winners); ml = np.median(losers)
    diff_pct = 100 * (mw - ml) / ml if ml != 0 else float("nan")
    print(f"  {feature:<22} skip_winners(n={len(winners):>3}) med={mw:>7.3f}   "
          f"skip_losers(n={len(losers):>3}) med={ml:>7.3f}   "
          f"win-lose_diff={diff_pct:+.1f}%")


def main() -> None:
    print("[load]")
    df = load_signals()
    trades = collect_trades_with_features(df)
    print(f"[collect] {len(trades)} v1 directional trades with features")

    n_conf = sum(1 for t in trades if t["v2_confirmed"])
    n_skip = len(trades) - n_conf
    print(f"  v2-confirmed: {n_conf}   v2-skipped: {n_skip}")

    print("\n=== FEATURE DISTRIBUTIONS: v2-confirmed vs v2-skipped ===")
    features = ["abs_M20", "abs_M60", "abs_RY_chg", "abs_MA_spread_pct",
                "ATR_pct", "RY_level"]
    for f in features:
        compare_dists(trades, f)

    print("\n=== WITHIN v2-SKIPPED: winners vs losers ===")
    for f in features:
        outcome_split(trades, f)

    month_seasonality(trades)


if __name__ == "__main__":
    main()
