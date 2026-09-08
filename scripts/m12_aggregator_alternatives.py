"""Alternative monthly-regime aggregators for the ensemble.

Current M12 aggregator (252-day price momentum sign) has been LONG-stuck
since 2023-03-17. Prior finding (2026-08-31 m12_regime_bias): the ensemble
is effectively behaving as v1 minus SHORT signals because M12 always votes
LONG. Can a different aggregator make the ensemble a real 3-way vote?

Two-phase analysis:

PHASE 1: characterize each aggregator variant.
  Count flips, streak lengths, current state.

PHASE 2: rebuild the ensemble with each aggregator and backtest.
  Compare to v1 and v2 baselines.

Variants tested:
  - M3   (63 trading days,  ~3 months)
  - M6   (126 td, ~6 months)
  - M12  (252 td, baseline)
  - M24  (504 td, ~2 years)
  - multi_consensus: majority of {M3, M6, M12} signs
  - recency_weighted_M12: exponentially-weighted 12mo momentum

Usage:
  python scripts/m12_aggregator_alternatives.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util
spec = importlib.util.spec_from_file_location("far", str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

DXY_PATH = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"


def load_signals() -> pd.DataFrame:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-09-08", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    df = far.build_signals(daily, ry)
    dxy = far.load_macro_series(DXY_PATH, "dxy")
    dxy_daily = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                              method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(far.RY_LAG)

    df["M3"]  = df["close"].pct_change(63)
    df["M6"]  = df["close"].pct_change(126)
    df["M12"] = df["close"].pct_change(252)
    df["M24"] = df["close"].pct_change(504)

    # Recency-weighted M12: EWM with half-life = 63 trading days (3 months)
    # so recent 3 months carry ~50% weight of the 12 month total
    log_ret = np.log(df["close"] / df["close"].shift(1))
    df["M12_rw"] = log_ret.ewm(halflife=63, min_periods=252).mean() * 252

    return df


def aggregator_direction(row, name: str) -> str:
    if name == "M3":
        v = row.get("M3"); return _sign_or_flat(v)
    if name == "M6":
        v = row.get("M6"); return _sign_or_flat(v)
    if name == "M12":
        v = row.get("M12"); return _sign_or_flat(v)
    if name == "M24":
        v = row.get("M24"); return _sign_or_flat(v)
    if name == "M12_rw":
        v = row.get("M12_rw"); return _sign_or_flat(v)
    if name == "multi_consensus":
        # Majority of {M3, M6, M12} signs
        votes = []
        for k in ("M3", "M6", "M12"):
            d = _sign_or_flat(row.get(k))
            if d != "FLAT":
                votes.append(d)
        if not votes: return "FLAT"
        long_c = sum(1 for v in votes if v == "LONG")
        short_c = sum(1 for v in votes if v == "SHORT")
        if long_c > short_c: return "LONG"
        if short_c > long_c: return "SHORT"
        return "FLAT"
    return "FLAT"


def _sign_or_flat(v):
    if v is None or pd.isna(v): return "FLAT"
    if v > 0: return "LONG"
    if v < 0: return "SHORT"
    return "FLAT"


def characterize(df: pd.DataFrame, name: str) -> dict:
    """Flip frequency, streak stats, current state."""
    valid = df.dropna(subset=[c for c in ["M3", "M6", "M12", "M24", "M12_rw"] if c in df.columns])
    directions = valid.apply(lambda r: aggregator_direction(r, name), axis=1)
    directions = directions[directions != "FLAT"]
    if len(directions) == 0:
        return {"name": name, "n_days": 0}
    total = len(directions)
    long_pct = (directions == "LONG").sum() / total
    # Count flips (change in direction)
    changes = (directions != directions.shift(1)).sum() - 1
    # Streak stats
    streak_ids = (directions != directions.shift(1)).cumsum()
    streak_lens = directions.groupby(streak_ids).size()
    current_dir = directions.iloc[-1]
    current_streak_id = streak_ids.iloc[-1]
    current_streak_len = int((streak_ids == current_streak_id).sum())
    return {
        "name": name, "n_days": total,
        "long_pct": long_pct, "n_flips": int(changes),
        "streak_median": int(streak_lens.median()),
        "streak_max": int(streak_lens.max()),
        "current_dir": current_dir,
        "current_streak_days": current_streak_len,
    }


def ensemble_direction(row, agg_name: str) -> tuple[str, str]:
    """Given a signal row, compute ensemble direction under a given aggregator."""
    v1 = str(row["direction"])
    dxy_chg = row.get("DXY_chg")
    if v1 == "LONG" and pd.notna(dxy_chg) and dxy_chg < 0: v2 = "LONG"
    elif v1 == "SHORT" and pd.notna(dxy_chg) and dxy_chg > 0: v2 = "SHORT"
    else: v2 = "FLAT"

    monthly = aggregator_direction(row, agg_name)

    long_c = sum(1 for d in (v1, v2, monthly) if d == "LONG")
    short_c = sum(1 for d in (v1, v2, monthly) if d == "SHORT")
    if long_c >= 2: ens = "LONG"
    elif short_c >= 2: ens = "SHORT"
    else: ens = "FLAT"
    return ens, monthly


def backtest_ensemble(df: pd.DataFrame, weeks: list, agg_name: str) -> list[dict]:
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")):
            continue
        ens_dir, monthly_dir = ensemble_direction(sig, agg_name)
        if ens_dir == "FLAT":
            continue
        entry = float(df.loc[mon]["open"])
        atr = float(sig["ATR"])
        if atr <= 0:
            continue
        if ens_dir == "LONG":
            stop = entry - far.STOP_ATR_MULT * atr
        else:
            stop = entry + far.STOP_ATR_MULT * atr
        r = far.simulate_week(df.loc[mon:fri], mon, fri, ens_dir, entry, stop)
        if not r:
            continue
        trades.append({
            "signal_date": signal_date, "direction": ens_dir,
            "net": r["net"], "entry": entry,
        })
    return trades


def summarize(trades: list, label: str) -> dict:
    if not trades: return {"label": label, "n": 0}
    n = len(trades)
    pnls = np.array([t["net"] for t in trades])
    wr = (pnls > 0).sum() / n
    returns = np.array([t["net"] / (t["entry"] * far.CONTRACT_SIZE) for t in trades])
    sharpe = (returns.mean() / returns.std(ddof=1)) * np.sqrt(52) if returns.std(ddof=1) > 0 else 0
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    max_dd = float((cum - peak).min())
    long_n = sum(1 for t in trades if t["direction"] == "LONG")
    short_n = sum(1 for t in trades if t["direction"] == "SHORT")
    return {
        "label": label, "n": n, "n_long": long_n, "n_short": short_n,
        "wr": wr, "sharpe": sharpe, "cum": float(cum[-1]), "max_dd": max_dd,
    }


def main():
    df = load_signals()
    print(f"Loaded {len(df)} daily bars ({df.index.min().date()} to {df.index.max().date()})")

    print("\n=== PHASE 1: aggregator characterization (daily direction) ===")
    print(f"  {'variant':<18} {'n_days':>7}  {'%LONG':>7}  {'flips':>5}  {'strk_med':>8}  {'strk_max':>8}  {'current':>10}")
    variant_names = ["M3", "M6", "M12", "M24", "M12_rw", "multi_consensus"]
    for name in variant_names:
        c = characterize(df, name)
        if c.get("n_days", 0) == 0:
            print(f"  {name:<18} (no data)"); continue
        print(f"  {name:<18} {c['n_days']:>7}  {c['long_pct']*100:>6.1f}%  {c['n_flips']:>5}  "
              f"{c['streak_median']:>8}  {c['streak_max']:>8}  "
              f"{c['current_dir']:>7} {c['current_streak_days']:>4}d")

    print("\n=== PHASE 2: ensemble backtest under each aggregator ===")
    weeks = far.week_indices(df)
    print(f"  {len(weeks)} weeks total")

    # v1 and v2 baselines for reference
    v1_trades = []
    v2_trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index: continue
        sig = df.loc[signal_date]
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")): continue
        v1_dir = str(sig["direction"])
        entry = float(df.loc[mon]["open"]); atr = float(sig["ATR"])
        if atr <= 0: continue
        # v1
        if v1_dir != "FLAT":
            stop = entry - far.STOP_ATR_MULT * atr if v1_dir == "LONG" else entry + far.STOP_ATR_MULT * atr
            r = far.simulate_week(df.loc[mon:fri], mon, fri, v1_dir, entry, stop)
            if r: v1_trades.append({"direction": v1_dir, "net": r["net"], "entry": entry})
        # v2
        dxy_chg = sig.get("DXY_chg")
        if v1_dir == "LONG" and pd.notna(dxy_chg) and dxy_chg < 0: v2_dir = "LONG"
        elif v1_dir == "SHORT" and pd.notna(dxy_chg) and dxy_chg > 0: v2_dir = "SHORT"
        else: v2_dir = "FLAT"
        if v2_dir != "FLAT":
            stop = entry - far.STOP_ATR_MULT * atr if v2_dir == "LONG" else entry + far.STOP_ATR_MULT * atr
            r = far.simulate_week(df.loc[mon:fri], mon, fri, v2_dir, entry, stop)
            if r: v2_trades.append({"direction": v2_dir, "net": r["net"], "entry": entry})

    results = [summarize(v1_trades, "v1 baseline"), summarize(v2_trades, "v2 baseline")]

    for name in ["M3", "M6", "M12", "M24", "M12_rw", "multi_consensus"]:
        trades = backtest_ensemble(df, weeks, name)
        results.append(summarize(trades, f"ensemble[{name}]"))

    print(f"\n  {'variant':<22} {'n':>4}  {'#L':>4}  {'#S':>4}  {'WR':>6}  {'Sharpe':>7}  {'cum $':>10}  {'maxDD':>10}")
    for r in results:
        if r["n"] == 0:
            print(f"  {r['label']:<22} (no trades)"); continue
        print(f"  {r['label']:<22} {r['n']:>4}  {r['n_long']:>4}  {r['n_short']:>4}  "
              f"{r['wr']*100:>5.1f}%  {r['sharpe']:>7.2f}  ${r['cum']:>9,.0f}  ${r['max_dd']:>9,.0f}")

    print("\n=== Ensemble variants ranked by Sharpe ===")
    ens = [r for r in results if r["label"].startswith("ensemble")]
    for i, r in enumerate(sorted(ens, key=lambda x: -x["sharpe"]), 1):
        print(f"  {i}. {r['label']:<22} Sharpe {r['sharpe']:.2f}  n={r['n']}  #S={r['n_short']}")


if __name__ == "__main__":
    main()
