"""Cross-asset check: does DXY-filter mechanism generalize beyond gold?

Follow-up to today's v2 analyses. Question: v2 = v1 + DXY filter beats
v1 in every cell for gold. Is the DXY-alignment principle
gold-specific, or does it generalize to other USD-denominated assets?

Test on:
  - Silver (XAG/USD) - close cousin to gold, similar macro drivers
  - S&P 500 (USA500.IDXUSD) - risk asset, different macro sensitivity

For each asset:
  1. Apply gold-v1 rule shape (M20+M60+MA10/40+RY_chg) to the asset's
     own price series
  2. Then apply the DXY filter as an additional condition
  3. Compare rule-alone vs rule + DXY-filter performance

This is a probe, not a pre-reg. Purpose: does the DXY-alignment
mechanism improve v1-shape rules on other assets, or is it
gold-specific?

Usage: python scripts/dxy_filter_cross_asset.py
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
RY_PATH = far.RY
CONTRACT_MULT = {"XAUUSD": 100, "XAGUSD": 5000, "SPX": 50}  # rough per-unit
ATR_STOP = 2.0
RT_COST = 5.0


def load_asset_daily(csv_paths: list[Path], start: pd.Timestamp,
                      end: pd.Timestamp) -> pd.DataFrame:
    dfs = []
    for p in csv_paths:
        if not p.exists():
            continue
        df = pd.read_csv(p, parse_dates=["ts"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        dfs.append(df)
    combined = pd.concat(dfs, ignore_index=True) \
        .drop_duplicates(subset=["ts"], keep="first") \
        .sort_values("ts").set_index("ts")
    buffer = pd.Timedelta(days=100)
    subset = combined[(combined.index >= start - buffer) & (combined.index <= end)]
    daily = subset.resample("1D").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
    ).dropna()
    daily = daily[daily.index.weekday < 5]
    return daily


def build_v1_signals(daily: pd.DataFrame, ry: pd.Series) -> pd.DataFrame:
    df = daily.copy()
    df["M20"] = df["close"].pct_change(20)
    df["M60"] = df["close"].pct_change(60)
    df["MA10"] = df["close"].rolling(10).mean()
    df["MA40"] = df["close"].rolling(40).mean()
    df["ATR"] = far.compute_atr(df, 20)
    ry_daily = ry.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                           method="ffill")
    ry_daily.index = df.index
    df["RY"] = ry_daily
    df["RY_chg"] = df["RY"].diff(20)
    long_cond = ((df["M20"] > 0) & (df["M60"] > 0) &
                 (df["MA10"] > df["MA40"]) & (df["RY_chg"] < 0))
    short_cond = ((df["M20"] < 0) & (df["M60"] < 0) &
                  (df["MA10"] < df["MA40"]) & (df["RY_chg"] > 0))
    df["direction"] = np.where(long_cond, "LONG",
                                np.where(short_cond, "SHORT", "FLAT"))
    return df


def add_dxy(df: pd.DataFrame) -> pd.DataFrame:
    dxy = far.load_macro_series(DXY_PATH, "dxy")
    dxy_daily = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                             method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(20)
    return df


def simulate(df: pd.DataFrame, direction_col: str,
              contract_size: float, invert_dxy_for_risk: bool = False) -> dict:
    """Weekly cycle, Monday open entry, Friday close exit, 2xATR stop.

    For SPX (risk asset): DXY-alignment inverts (strong dollar = risk off).
    invert_dxy_for_risk flips SHORT/LONG interpretation of DXY alignment.
    """
    weeks = far.week_indices(df)
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        direction = str(sig[direction_col])
        if direction == "FLAT":
            continue
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")):
            continue
        entry = float(df.loc[mon, "open"])
        atr = float(sig["ATR"])
        if atr <= 0:
            continue
        if direction == "LONG":
            stop = entry - ATR_STOP * atr
        else:
            stop = entry + ATR_STOP * atr
        wk = df.loc[mon:fri]
        dir_sign = 1 if direction == "LONG" else -1
        exit_price = None
        for _, row in wk.iterrows():
            if direction == "LONG":
                if float(row["low"]) <= stop:
                    exit_price = stop; break
            else:
                if float(row["high"]) >= stop:
                    exit_price = stop; break
        if exit_price is None:
            exit_price = float(wk.iloc[-1]["close"])
        gross = (exit_price - entry) * dir_sign * contract_size
        net = gross - RT_COST
        trades.append({
            "week_start": mon, "direction": direction,
            "entry": entry, "exit": exit_price, "net": net,
            "ret": net / (entry * contract_size),
        })
    return {"trades": trades, "n": len(trades)}


def add_dxy_filter_direction(df: pd.DataFrame,
                              invert_for_risk: bool = False) -> pd.DataFrame:
    """Add direction_dxy column: keeps v1 direction only when DXY aligns.

    For commodities (gold, silver, DXY-inverse assets):
      LONG confirmed if DXY_chg < 0 (dollar falling supports)
      SHORT confirmed if DXY_chg > 0

    For risk assets (SPX):
      LONG confirmed if DXY_chg < 0 (weak dollar = risk on)
      SHORT confirmed if DXY_chg > 0

    Same convention actually for both when the asset is "long dollar
    strength = bearish for asset." invert_for_risk kept as arg for
    future flexibility but unused right now (SPX behaves like commodities
    in DXY terms - strong dollar hurts multinationals).
    """
    def v2_dir(row):
        v1 = row["direction"]
        d = row.get("DXY_chg")
        if pd.isna(d):
            return "FLAT"
        if v1 == "LONG" and d < 0: return "LONG"
        if v1 == "SHORT" and d > 0: return "SHORT"
        return "FLAT"
    df["direction_dxy"] = df.apply(v2_dir, axis=1)
    return df


def report(label: str, sim: dict) -> None:
    trades = sim["trades"]
    n = sim["n"]
    if n == 0:
        print(f"  {label:<30} n=0")
        return
    rets = [t["ret"] for t in trades]
    pnls = [t["net"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    mean_r = np.mean(rets); std_r = np.std(rets, ddof=1) if n > 1 else 0
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0
    print(f"  {label:<30} n={n:>3}  WR={100*wins/n:>5.1f}%  "
          f"mean={100*mean_r:>+7.3f}%  Sharpe={sharpe:>+7.3f}  "
          f"cum=${sum(pnls):>10,.0f}")


def probe_asset(name: str, csv_paths: list[Path], contract_size: float,
                 invert_dxy: bool = False) -> None:
    print(f"\n=== {name} ===")
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-08-31", tz="UTC")
    daily = load_asset_daily(csv_paths, start, end)
    if len(daily) < 100:
        print(f"  insufficient data ({len(daily)} bars)")
        return
    print(f"  daily bars: {len(daily)}   "
          f"range {daily.index.min().date()} -> {daily.index.max().date()}")
    ry = far.load_macro_series(RY_PATH, "real_yield_10y")
    df = build_v1_signals(daily, ry)
    df = add_dxy(df)
    df = add_dxy_filter_direction(df, invert_for_risk=invert_dxy)

    rule_alone = simulate(df, "direction", contract_size)
    rule_dxy = simulate(df, "direction_dxy", contract_size)

    report(f"v1-shape rule alone", rule_alone)
    report(f"v1-shape + DXY filter (v2)", rule_dxy)

    n_alone = rule_alone["n"]; n_dxy = rule_dxy["n"]
    skipped = n_alone - n_dxy
    if n_alone > 0:
        print(f"  DXY-filter dropped {skipped}/{n_alone} = {100*skipped/n_alone:.1f}% of firings")


def main() -> None:
    dukascopy = ROOT / "data" / "external" / "dukascopy"

    # Gold (baseline reproduction)
    probe_asset(
        "GOLD (XAU/USD) - baseline",
        [dukascopy / "XAUUSD_5m_2010_2014.csv",
         dukascopy / "XAUUSD_5m_historical.csv",
         dukascopy / "XAUUSD_5m.csv"],
        contract_size=100,
    )

    # Silver
    probe_asset(
        "SILVER (XAG/USD)",
        [dukascopy / "XAGUSD_5m_historical.csv",
         dukascopy / "XAGUSD_5m.csv"],
        contract_size=5000,
    )

    # SPX
    probe_asset(
        "S&P 500 (USA500)",
        [dukascopy / "USA500.IDXUSD_5m_historical.csv"],
        contract_size=50,
    )


if __name__ == "__main__":
    main()
