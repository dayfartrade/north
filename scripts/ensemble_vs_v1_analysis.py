"""Same v1-vs-v2 filter analysis but for the ensemble (v1+v2+monthly-M12, >=2).

For each week, compare what v1 said vs what the ensemble would have traded.
Ensemble filters MORE than v2 (v2 filters ~25%, ensemble requires >=2 votes).
Question: does the extra filtering catch more losers or drop more winners?
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

spec = importlib.util.spec_from_file_location("far",
    str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec); spec.loader.exec_module(far)


def build_ensemble_direction(daily, ry, dxy):
    """Same logic as compute_ensemble_shadow in the publisher, but for every week."""
    df = far.build_signals(daily, ry)
    dxy_daily = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                             method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(far.RY_LAG)
    df["M12"] = df["close"].pct_change(252)

    def ensemble_row(r):
        v1 = r["direction"]
        dxy_ok = pd.notna(r["DXY_chg"])
        m12_ok = pd.notna(r["M12"])
        if v1 == "LONG" and dxy_ok and r["DXY_chg"] < 0:
            v2 = "LONG"
        elif v1 == "SHORT" and dxy_ok and r["DXY_chg"] > 0:
            v2 = "SHORT"
        else:
            v2 = "FLAT"
        if not m12_ok:
            monthly = "FLAT"
        elif r["M12"] > 0:
            monthly = "LONG"
        elif r["M12"] < 0:
            monthly = "SHORT"
        else:
            monthly = "FLAT"
        long_votes = sum(1 for d in (v1, v2, monthly) if d == "LONG")
        short_votes = sum(1 for d in (v1, v2, monthly) if d == "SHORT")
        if long_votes >= 2: return "LONG"
        if short_votes >= 2: return "SHORT"
        return "FLAT"
    df["ensemble_dir"] = df.apply(ensemble_row, axis=1)
    return df


def analyze(label, start, end):
    print(f"\n{'#'*70}\n# {label}: {start.date()} to {end.date()}\n{'#'*70}")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    dxy_path = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"
    dxy = far.load_macro_series(dxy_path, "dxy")

    df_v1 = far.build_signals(daily, ry)
    df_ens = build_ensemble_direction(daily, ry, dxy)

    df_v1 = df_v1[(df_v1.index >= start) & (df_v1.index <= end)]
    df_ens = df_ens[(df_ens.index >= start) & (df_ens.index <= end)]
    weeks = far.week_indices(df_v1)

    v1_trades, ens_trades = [], []
    for signal_date, mon, fri in weeks:
        if signal_date not in df_v1.index: continue
        for label2, direction_col, trades in [("v1", "direction", v1_trades),
                                              ("ens", "ensemble_dir", ens_trades)]:
            src = df_v1 if label2 == "v1" else df_ens
            row = src.loc[signal_date]
            d = row[direction_col]
            if d == "FLAT": continue
            if pd.isna(row["ATR"]) or pd.isna(row["M60"]): continue
            if mon not in df_v1.index: continue
            entry = float(df_v1.loc[mon]["open"])
            atr = float(row["ATR"])
            if atr <= 0: continue
            stop = entry - 2*atr if d == "LONG" else entry + 2*atr
            week_slice = df_v1.loc[mon:fri]
            r = far.simulate_week(week_slice, mon, fri, d, entry, stop)
            if r:
                r["signal_date"] = signal_date
                trades.append(r)

    v1_by_week = {t["week_start"]: t for t in v1_trades}
    ens_weeks = {t["week_start"] for t in ens_trades}
    filtered = [t for wk, t in v1_by_week.items() if wk not in ens_weeks]
    kept = [t for wk, t in v1_by_week.items() if wk in ens_weeks]
    def stats(trades):
        if not trades: return "n=0"
        n = len(trades); pnl = sum(t["net"] for t in trades)
        w = sum(1 for t in trades if t["net"]>0)
        return f"n={n}  total=${pnl:+,.0f}  mean=${pnl/n:+,.0f}  WR={100*w/n:.1f}%"
    print(f"v1 all:       {stats(list(v1_by_week.values()))}")
    print(f"ens kept:     {stats(kept)}")
    print(f"ens filtered: {stats(filtered)}  "
          f"({100*len(filtered)/max(1,len(v1_by_week)):.1f}% of v1)")
    # Ensemble-only trades (direction flipped or NOT in v1 non-flat)
    ens_only = [t for t in ens_trades if t["week_start"] not in v1_by_week]
    if ens_only:
        print(f"ens-only (v1 was FLAT, ensemble traded): {stats(ens_only)}")


def main():
    for label, s, e in [
        ("FULL", "2010-01-01", "2026-07-20"),
        ("TRAIN", "2010-01-01", "2017-12-31"),
        ("OOS",   "2018-01-01", "2026-07-20"),
    ]:
        analyze(label, pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC"))


if __name__ == "__main__":
    main()
