"""Fire-rate analysis: how do v1 trades split by whether v2 confirmed?

Follow-up #3 from docs/experiments/2026-08-31_m12_regime_split_ensemble.md.

Question: v2 fires on ~33% of weeks vs v1's ~43%. So on ~10% of weeks
v1 fires but v2 doesn't. What do those v2-skipped v1 trades look like
compared to v1 trades where v2 also confirmed? If they systematically
underperform, v2's edge lives in the ability to skip low-quality v1
firings.

For each v1 directional trade:
  - Tag "v2_confirmed" if v2 signal matched v1 direction
  - Tag "v2_skipped" if v2 signal was FLAT (DXY not aligned)
  (v2 disagreeing with v1 direction is impossible by construction:
   v2 only fires when v1 already fires AND DXY aligns.)

Report WR, mean %/trade, Sharpe per subset, plus M12 regime split.

Usage: python scripts/v1_fire_rate_split_by_v2.py
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
M12_WINDOW = 252


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
    df["M12"] = df["close"].pct_change(M12_WINDOW)
    return df


def v2_direction(v1: str, dxy_chg: float | None) -> str:
    if v1 == "LONG" and dxy_chg is not None and dxy_chg < 0:
        return "LONG"
    if v1 == "SHORT" and dxy_chg is not None and dxy_chg > 0:
        return "SHORT"
    return "FLAT"


def collect_v1_trades(df: pd.DataFrame) -> list[dict]:
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
        m12 = float(sig["M12"]) if pd.notna(sig.get("M12")) else None
        if m12 is None:
            continue
        v2 = v2_direction(v1, dxy_chg)
        confirmed = (v2 == v1)

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
            "v2_confirmed": confirmed,
            "regime": "M12_LONG" if m12 > 0 else "M12_SHORT",
            "ret": result["net"] / (entry * far.CONTRACT_SIZE),
            "net": result["net"],
            "dxy_chg": dxy_chg,
        })
    return trades


def stats(trades: list[dict]) -> dict:
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
        "wr_pct": round(100 * wins / n, 1),
        "mean_pct": round(100 * mean_r, 3),
        "sharpe": round(sharpe, 3),
        "cum_usd": round(sum(pnls), 0),
    }


def render(label: str, s: dict) -> str:
    if s.get("n", 0) == 0:
        return f"  {label:<32} n=0"
    return (f"  {label:<32} n={s['n']:>3}  "
            f"WR={s['wr_pct']:>5.1f}%  "
            f"mean={s['mean_pct']:>+7.3f}%  "
            f"Sharpe={s['sharpe']:>+7.3f}  "
            f"cum=${s['cum_usd']:>9,.0f}")


def split_by_direction_regime_conf(trades: list[dict],
                                    direction: str | None = None,
                                    regime: str | None = None,
                                    confirmed: bool | None = None) -> list[dict]:
    out = trades
    if direction is not None:
        out = [t for t in out if t["direction"] == direction]
    if regime is not None:
        out = [t for t in out if t["regime"] == regime]
    if confirmed is not None:
        out = [t for t in out if t["v2_confirmed"] == confirmed]
    return out


def main() -> None:
    print("[load]")
    df = load_signals()
    trades = collect_v1_trades(df)
    print(f"[collect] {len(trades)} v1 directional trades")
    n_conf = sum(1 for t in trades if t["v2_confirmed"])
    n_skip = len(trades) - n_conf
    print(f"[split] v2-confirmed: {n_conf}   v2-skipped: {n_skip}   "
          f"(v2-fire-rate on v1 firings: {100*n_conf/len(trades):.1f}%)")

    print("\n=== ALL v1 TRADES ===")
    print(render("v1 all",              stats(trades)))
    print(render("v1 + v2 confirmed",   stats(split_by_direction_regime_conf(trades, confirmed=True))))
    print(render("v1 - v2 skipped",     stats(split_by_direction_regime_conf(trades, confirmed=False))))

    print("\n=== v1 LONG TRADES ===")
    print(render("v1 LONG all",              stats(split_by_direction_regime_conf(trades, direction="LONG"))))
    print(render("v1 LONG + v2 confirmed",   stats(split_by_direction_regime_conf(trades, direction="LONG", confirmed=True))))
    print(render("v1 LONG - v2 skipped",     stats(split_by_direction_regime_conf(trades, direction="LONG", confirmed=False))))

    print("\n=== v1 SHORT TRADES ===")
    print(render("v1 SHORT all",             stats(split_by_direction_regime_conf(trades, direction="SHORT"))))
    print(render("v1 SHORT + v2 confirmed",  stats(split_by_direction_regime_conf(trades, direction="SHORT", confirmed=True))))
    print(render("v1 SHORT - v2 skipped",    stats(split_by_direction_regime_conf(trades, direction="SHORT", confirmed=False))))

    print("\n=== v2-SKIPPED v1 TRADES BY M12 REGIME ===")
    print(render("v2-skipped, M12 LONG",  stats(split_by_direction_regime_conf(trades, regime="M12_LONG",  confirmed=False))))
    print(render("v2-skipped, M12 SHORT", stats(split_by_direction_regime_conf(trades, regime="M12_SHORT", confirmed=False))))

    print("\n=== v2-CONFIRMED v1 TRADES BY M12 REGIME ===")
    print(render("v2-confirmed, M12 LONG",  stats(split_by_direction_regime_conf(trades, regime="M12_LONG",  confirmed=True))))
    print(render("v2-confirmed, M12 SHORT", stats(split_by_direction_regime_conf(trades, regime="M12_SHORT", confirmed=True))))


if __name__ == "__main__":
    main()
