"""FAR Weekly meta-labeling (Prado AFML Ch 3.6) — pre-committed pipeline.

Pre-reg: docs/experiments/2026-07-22_far_weekly_meta_labeling_prereg.md

Pipeline:
  1. Generate FAR Weekly v1 non-FLAT signals over full 16-year sample
  2. For each signal, compute 15 pre-committed features at signal date
  3. Split TRAIN (2010-2020) / HOLDOUT (2021-2026)
  4. Fit RandomForest on TRAIN
  5. Evaluate on HOLDOUT — report filtered strategy vs baseline
  6. Judge against pre-committed ship + reject gates
"""
from __future__ import annotations

import sys
import math
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import numpy as np
import importlib.util
spec = importlib.util.spec_from_file_location("far",
                                                str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

# Data paths for extra features
DXY = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"
WTI_CSV = ROOT / "data" / "external" / "dukascopy" / "LIGHT.CMDUSD_5m_historical.csv"


def load_wti_daily() -> pd.DataFrame:
    """Load WTI daily prices for gold-oil ratio feature."""
    df = pd.read_csv(WTI_CSV, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    daily = df.resample("1D").agg(close=("close", "last")).dropna()
    daily.index = daily.index.tz_localize(None) if daily.index.tz else daily.index
    return daily


def build_feature_frame(signals_df: pd.DataFrame, ry: pd.Series,
                        dxy: pd.Series, wti: pd.DataFrame) -> pd.DataFrame:
    """Compute the 15 pre-committed features for each signal row.

    signals_df must have columns: signal_date_idx, direction, and the daily
    dataframe columns (close, high, low, M20, M60, MA10, MA40, ATR, RY_chg).
    """
    df = signals_df.copy()

    # Signal magnitude
    df["abs_M20"] = df["M20"].abs()
    df["abs_M60"] = df["M60"].abs()
    df["MA_dist_pct"] = (df["MA10"] - df["MA40"]) / df["MA40"]
    df["abs_RY_chg"] = df["RY_chg"].abs()

    # Volatility
    df["ATR_pct"] = df["ATR"] / df["close"]

    # ATR ratio requires ATR60
    atr60 = df["close"].rolling(60).apply(lambda x: (x.max() - x.min()) / 60, raw=True)
    # simpler: recompute both
    df["ATR_ratio"] = df["ATR"] / (df["ATR"].rolling(60).mean() + 1e-9)

    # Trend position
    df["close_vs_MA40"] = df["close"] / df["MA40"] - 1
    rolling_min = df["close"].rolling(20).min()
    rolling_max = df["close"].rolling(20).max()
    df["pos_in_20d_range"] = (df["close"] - rolling_min) / (rolling_max - rolling_min + 1e-9)

    # DXY
    dxy_reindex = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                                method="ffill")
    dxy_reindex.index = df.index
    df["DXY"] = dxy_reindex
    df["DXY_chg_20d"] = df["DXY"].diff(20)

    # Real yield level + longer memory
    ry_reindex = ry.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                             method="ffill")
    ry_reindex.index = df.index
    df["RY_level"] = ry_reindex
    df["RY_chg_60d"] = df["RY_level"].diff(60)

    # Gold / WTI ratio
    wti_reindex = wti["close"].reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                                        method="ffill")
    wti_reindex.index = df.index
    df["gold_oil_ratio"] = df["close"] / (wti_reindex + 1e-9)
    df["gold_oil_ratio_chg_20d"] = df["gold_oil_ratio"] - df["gold_oil_ratio"].shift(20)

    # Direction encoding
    df["primary_direction_long"] = (df["direction"] == "LONG").astype(int)
    df["primary_direction_short"] = (df["direction"] == "SHORT").astype(int)

    return df


FEATURE_COLS = [
    "abs_M20", "abs_M60", "MA_dist_pct", "abs_RY_chg",
    "ATR_pct", "ATR_ratio",
    "close_vs_MA40", "pos_in_20d_range",
    "DXY_chg_20d", "RY_level", "RY_chg_60d",
    "gold_oil_ratio", "gold_oil_ratio_chg_20d",
    "primary_direction_long", "primary_direction_short",
]


def run_pipeline():
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-07-20", tz="UTC")

    print("Loading data...")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    dxy = far.load_macro_series(DXY, "dxy")
    wti = load_wti_daily()

    # Build signals dataframe (identical to v1 backtest)
    sig_df = far.build_signals(daily, ry)
    sig_df = sig_df[(sig_df.index >= start) & (sig_df.index <= end)]

    # Get weekly signals + their outcomes
    print("Running v1 backtest to get signals + labels...")
    r = far.backtest(start, end)
    trades = r["trades"]
    print(f"  {len(trades)} non-FLAT signals")

    # Attach features to each trade
    trade_rows = []
    for t in trades:
        signal_date = t["week_start"] - pd.Timedelta(days=3)  # Friday before Monday
        # Get closest signal date in df
        avail = sig_df.index[sig_df.index <= signal_date]
        if len(avail) == 0:
            continue
        sd = avail[-1]
        sig_row = sig_df.loc[sd]
        trade_rows.append({
            "signal_date": sd,
            "week_start": t["week_start"],
            "direction": t["direction"],
            "net_pnl": t["net"],
            "close": float(sig_row["close"]),
            "high": float(sig_row["high"]),
            "low": float(sig_row["low"]),
            "M20": float(sig_row["M20"]),
            "M60": float(sig_row["M60"]),
            "MA10": float(sig_row["MA10"]),
            "MA40": float(sig_row["MA40"]),
            "ATR": float(sig_row["ATR"]),
            "RY_chg": float(sig_row["RY_chg"]),
        })
    trades_df = pd.DataFrame(trade_rows).set_index("signal_date")
    print(f"  attached signal-time features to {len(trades_df)} rows")

    # Compute all features
    print("Building features...")
    feat_df = build_feature_frame(trades_df, ry, dxy, wti)

    # Target
    feat_df["y"] = (feat_df["net_pnl"] > 0).astype(int)

    # Drop rows with any NaN feature
    n_before = len(feat_df)
    valid = feat_df.dropna(subset=FEATURE_COLS + ["y"])
    print(f"  dropped {n_before - len(valid)} rows with NaN features")

    # Split
    train = valid[valid["week_start"] < pd.Timestamp("2021-01-01", tz="UTC")]
    holdout = valid[valid["week_start"] >= pd.Timestamp("2021-01-01", tz="UTC")]
    print(f"\nTRAIN: {len(train)} signals ({train['y'].mean():.3f} base rate)")
    print(f"HOLDOUT: {len(holdout)} signals ({holdout['y'].mean():.3f} base rate)")

    # Fit random forest
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (precision_score, recall_score, f1_score,
                                   accuracy_score, confusion_matrix)

    X_train = train[FEATURE_COLS].values
    y_train = train["y"].values
    X_hold = holdout[FEATURE_COLS].values
    y_hold = holdout["y"].values

    print("\nFitting RandomForest (n=100, max_depth=None, min_samples_leaf=3)...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=None,
                                    min_samples_leaf=3, class_weight="balanced",
                                    random_state=42)
    clf.fit(X_train, y_train)

    # Train performance
    y_train_pred = clf.predict(X_train)
    print(f"\nTraining precision: {precision_score(y_train, y_train_pred):.3f}")
    print(f"Training recall:    {recall_score(y_train, y_train_pred):.3f}")
    print(f"Training F1:        {f1_score(y_train, y_train_pred):.3f}")

    # Feature importance
    print("\nFeature importance (top 10):")
    imp = sorted(zip(FEATURE_COLS, clf.feature_importances_),
                  key=lambda x: -x[1])
    for name, val in imp[:10]:
        print(f"  {name:32s} {val:.4f}")

    # HOLD-OUT evaluation
    print("\n" + "="*60)
    print("HOLD-OUT EVALUATION (2021-2026)")
    print("="*60)

    y_hold_pred = clf.predict(X_hold)
    y_hold_proba = clf.predict_proba(X_hold)[:, 1]

    # Classifier metrics
    prec = precision_score(y_hold, y_hold_pred)
    rec = recall_score(y_hold, y_hold_pred)
    f1 = f1_score(y_hold, y_hold_pred)
    print(f"\nClassifier metrics on hold-out:")
    print(f"  Precision: {prec:.3f}")
    print(f"  Recall:    {rec:.3f}")
    print(f"  F1:        {f1:.3f}")
    print(f"  Accuracy:  {accuracy_score(y_hold, y_hold_pred):.3f}")
    cm = confusion_matrix(y_hold, y_hold_pred)
    print(f"  Confusion: [[{cm[0,0]}, {cm[0,1]}], [{cm[1,0]}, {cm[1,1]}]]")

    # Strategy comparison
    holdout = holdout.copy()
    holdout["take"] = y_hold_pred
    holdout["p_hat"] = y_hold_proba

    baseline_pnl = holdout["net_pnl"].values
    filtered_pnl = holdout["net_pnl"].values * holdout["take"].values

    b_n = len(baseline_pnl); b_tot = baseline_pnl.sum(); b_mean = baseline_pnl.mean()
    b_wr = (baseline_pnl > 0).mean()
    b_ret = holdout["net_pnl"] / (holdout["close"] * 100)
    b_sharpe = b_ret.mean() / b_ret.std() * math.sqrt(52) if b_ret.std() > 0 else 0

    f_take = holdout[holdout["take"] == 1]
    f_n = len(f_take)
    f_tot = f_take["net_pnl"].sum() if f_n else 0
    f_mean = f_tot / f_n if f_n else 0
    f_wr = (f_take["net_pnl"] > 0).mean() if f_n else 0
    f_ret = f_take["net_pnl"] / (f_take["close"] * 100) if f_n else pd.Series([0])
    f_sharpe = f_ret.mean() / f_ret.std() * math.sqrt(52) if f_ret.std() > 0 else 0

    print(f"\n--- Strategy comparison on hold-out ---")
    print(f"{'':20s} {'Baseline v1':>12s} {'Meta-filtered':>14s}")
    print(f"{'Trades':20s} {b_n:>12d} {f_n:>14d}")
    print(f"{'Total P&L':20s} ${b_tot:>+11,.0f} ${f_tot:>+13,.0f}")
    print(f"{'Mean per week':20s} ${b_mean:>+11,.0f} ${f_mean:>+13,.0f}")
    print(f"{'Win rate':20s} {100*b_wr:>11.1f}% {100*f_wr:>13.1f}%")
    print(f"{'Sharpe (ann)':20s} {b_sharpe:>12.3f} {f_sharpe:>14.3f}")

    # Ship gate evaluation
    print(f"\n--- Ship gates ---")
    gate1 = f_mean > b_mean
    gate2 = f_wr >= b_wr
    gate3 = f_sharpe >= b_sharpe + 0.2
    gate4 = prec >= 0.60
    gate5 = f_n >= 40
    print(f"  1. Filtered mean > baseline mean:  {gate1}   ({f_mean:+.0f} vs {b_mean:+.0f})")
    print(f"  2. Filtered WR >= baseline WR:     {gate2}   ({100*f_wr:.1f}% vs {100*b_wr:.1f}%)")
    print(f"  3. Filtered Sharpe >= baseline+0.2:{gate3}   ({f_sharpe:.3f} vs {b_sharpe+0.2:.3f})")
    print(f"  4. Classifier precision >= 0.60:   {gate4}   ({prec:.3f})")
    print(f"  5. >= 40 trades taken:             {gate5}   ({f_n})")

    all_pass = all([gate1, gate2, gate3, gate4, gate5])
    reject_wr = f_wr < b_wr
    reject_mean = f_mean <= 0
    reject_few = f_n < 20

    print(f"\n--- Final verdict ---")
    if all_pass:
        print(f"  SHIP GATES PASS — meta-labeling qualifies as v3 candidate")
    elif reject_wr or reject_mean or reject_few:
        print(f"  REJECT GATE TRIGGERED — retire meta-labeling attempt")
        if reject_wr: print(f"    -> filtered WR {100*f_wr:.1f}% < baseline WR {100*b_wr:.1f}%")
        if reject_mean: print(f"    -> filtered mean {f_mean:+.0f} <= 0")
        if reject_few: print(f"    -> only {f_n} trades taken (< 20)")
    else:
        print(f"  BORDERLINE — some gates pass, some fail")
        print(f"  Do NOT ship without further analysis or forward validation")


if __name__ == "__main__":
    run_pipeline()
