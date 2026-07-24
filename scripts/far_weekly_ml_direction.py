"""FAR Weekly Gold ML Direction v1 — walk-forward CV backtest.

Pre-reg: docs/experiments/2026-07-24_ml_direction_walkfwd_prereg.md
"""
from __future__ import annotations

import importlib.util
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

spec = importlib.util.spec_from_file_location("far",
                                                str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

CONTRACT_OZ = 100
RT_COST = 5.0
STOP_ATR_MULT = 2.0

RY_CSV = ROOT / "data" / "macro" / "real_yield_10y__DFII10.csv"
DXY_CSV = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"
GVZ_CSV = ROOT / "data" / "macro" / "gvz_gold_iv__GVZCLS.csv"
COT_CSV = ROOT / "data" / "macro" / "cot_gold_simplified.csv"

TRAIN_START = pd.Timestamp("2011-01-01", tz="UTC")
INIT_TRAIN_END = pd.Timestamp("2018-12-31", tz="UTC")
OOS_START = pd.Timestamp("2019-01-01", tz="UTC")
OOS_END = pd.Timestamp("2026-06-30", tz="UTC")
FOLD_WEEKS = 26


def load_series(path: Path, colname: str) -> pd.Series:
    df = pd.read_csv(path, parse_dates=[df_col(path)])
    df = df.set_index(df_col(path)).sort_index()
    return pd.to_numeric(df[colname], errors="coerce").dropna()


def df_col(path: Path) -> str:
    if "gvz" in path.name.lower():
        return "observation_date"
    return "date"


def build_features_labels(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    daily = far.load_daily_bars(start - pd.Timedelta(days=120), end + pd.Timedelta(days=10))
    daily["M20"] = daily["close"].pct_change(20)
    daily["M60"] = daily["close"].pct_change(60)
    daily["MA10"] = daily["close"].rolling(10).mean()
    daily["MA40"] = daily["close"].rolling(40).mean()
    daily["MA_ratio"] = daily["MA10"] / daily["MA40"]
    tr = pd.concat([(daily["high"] - daily["low"]).abs(),
                    (daily["high"] - daily["close"].shift()).abs(),
                    (daily["low"] - daily["close"].shift()).abs()], axis=1).max(axis=1)
    daily["ATR"] = tr.rolling(20).mean()
    daily["ATR_pct"] = daily["ATR"] / daily["close"]

    ry = load_series(RY_CSV, "value")
    dxy = load_series(DXY_CSV, "value")
    gvz = load_series(GVZ_CSV, "GVZCLS")

    idx_naive = daily.index.tz_localize(None) if daily.index.tz else daily.index
    daily["RY"] = ry.reindex(idx_naive, method="ffill").values
    daily["DXY"] = dxy.reindex(idx_naive, method="ffill").values
    daily["GVZ"] = gvz.reindex(idx_naive, method="ffill").values
    daily["RY_chg"] = daily["RY"].diff(20)
    daily["DXY_chg"] = daily["DXY"].diff(20)
    daily["GVZ_mean30"] = daily["GVZ"].rolling(30).mean()
    daily["GVZ_std30"] = daily["GVZ"].rolling(30).std()
    daily["GVZ_z"] = (daily["GVZ"] - daily["GVZ_mean30"]) / daily["GVZ_std30"]

    # COT nc_z (weekly)
    cot = pd.read_csv(COT_CSV, parse_dates=["date"]).sort_values("date").set_index("date")
    cot["nc_z"] = (cot["nc_net"] - cot["nc_net"].rolling(52).mean()) / cot["nc_net"].rolling(52).std()
    cot_z_daily = cot["nc_z"].reindex(idx_naive, method="ffill").values
    daily["nc_z"] = cot_z_daily

    # Now build weekly signal rows
    weeks = far.week_indices(daily[(daily.index >= start) & (daily.index <= end)])
    rows = []
    for signal_date, mon, fri in weeks:
        if mon not in daily.index or fri not in daily.index or signal_date not in daily.index:
            continue
        s = daily.loc[signal_date]
        entry = float(daily.loc[mon]["open"])
        exit_price = float(daily.loc[fri]["close"])
        if entry <= 0:
            continue
        # Direction target based on gross return (before stop)
        # But actual trade uses stop, so we label based on realized return AFTER stop
        atr = float(s["ATR"]) if pd.notna(s["ATR"]) else None
        if atr is None or atr <= 0:
            continue
        # Compute realized outcome for either LONG or SHORT choice
        wb = daily.loc[mon:fri]
        stop_long = entry - STOP_ATR_MULT * atr
        stop_short = entry + STOP_ATR_MULT * atr
        long_exit = None
        for _, row in wb.iterrows():
            if float(row["low"]) <= stop_long:
                long_exit = stop_long; break
        if long_exit is None:
            long_exit = exit_price
        short_exit = None
        for _, row in wb.iterrows():
            if float(row["high"]) >= stop_short:
                short_exit = stop_short; break
        if short_exit is None:
            short_exit = exit_price
        long_pnl = (long_exit - entry) * CONTRACT_OZ - RT_COST
        short_pnl = (entry - short_exit) * CONTRACT_OZ - RT_COST
        # Binary label: 1 if long_pnl > short_pnl (i.e., up week was more profitable)
        label = 1 if long_pnl > short_pnl else 0

        row = {
            "signal_date": signal_date, "mon": mon, "fri": fri,
            "entry": entry, "atr": atr, "long_pnl": long_pnl, "short_pnl": short_pnl,
            "label": label,
            "M20": s["M20"], "M60": s["M60"], "MA_ratio": s["MA_ratio"],
            "ATR_pct": s["ATR_pct"], "RY_chg": s["RY_chg"], "DXY_chg": s["DXY_chg"],
            "GVZ_z": s["GVZ_z"], "nc_z": s["nc_z"],
        }
        rows.append(row)
    return pd.DataFrame(rows).dropna().reset_index(drop=True)


FEATURES = ["M20", "M60", "MA_ratio", "ATR_pct", "RY_chg", "DXY_chg", "GVZ_z", "nc_z"]


def walk_forward(df: pd.DataFrame, fold_weeks: int = FOLD_WEEKS) -> dict:
    """Return list of test trades with predictions."""
    df = df.copy().sort_values("signal_date").reset_index(drop=True)
    train_end_pos = df[df["signal_date"] <= INIT_TRAIN_END].index.max()
    oos_start_pos = train_end_pos + 1

    trades = []
    fold_stats = []
    n = len(df)
    fold_idx = 0
    pos = oos_start_pos
    while pos < n:
        fold_end = min(pos + fold_weeks, n)
        train_df = df.iloc[:pos].copy()
        test_df = df.iloc[pos:fold_end].copy()
        if len(train_df) < 100 or len(test_df) < 5:
            pos = fold_end
            continue
        X_train = train_df[FEATURES].values
        y_train = train_df["label"].values
        X_test = test_df[FEATURES].values
        scaler = StandardScaler().fit(X_train)
        X_train_s = scaler.transform(X_train)
        X_test_s = scaler.transform(X_test)
        model = LogisticRegression(max_iter=1000, random_state=42).fit(X_train_s, y_train)
        probs = model.predict_proba(X_test_s)[:, 1]  # P(up)

        fold_pnls = []
        fold_dir_counts = defaultdict(int)
        for i, (_, row) in enumerate(test_df.iterrows()):
            p = probs[i]
            if p > 0.55:
                direction = "LONG"; net = row["long_pnl"]
            elif p < 0.45:
                direction = "SHORT"; net = row["short_pnl"]
            else:
                direction = "FLAT"; net = 0.0
            fold_dir_counts[direction] += 1
            trades.append({
                "signal_date": row["signal_date"], "direction": direction,
                "prob_up": p, "net": net, "entry": row["entry"],
                "fold": fold_idx,
            })
            fold_pnls.append(net)
        # Fold sharpe (using per-notional)
        rets = [p / (train_df["entry"].mean() * CONTRACT_OZ) for p in fold_pnls if p != 0.0]
        if len(rets) > 1:
            mr = sum(rets)/len(rets)
            sr = (sum((r-mr)**2 for r in rets)/(len(rets)-1))**0.5
            f_sharpe = mr/sr*math.sqrt(52) if sr > 0 else 0
        else:
            f_sharpe = 0.0
        fold_stats.append({
            "fold": fold_idx, "n": len(test_df),
            "total": sum(fold_pnls), "sharpe": f_sharpe,
            "long": fold_dir_counts["LONG"], "short": fold_dir_counts["SHORT"],
            "flat": fold_dir_counts["FLAT"],
        })
        fold_idx += 1
        pos = fold_end
    return {"trades": trades, "fold_stats": fold_stats}


def summarize(result: dict) -> None:
    trades = result["trades"]
    non_flat = [t for t in trades if t["direction"] != "FLAT"]
    n = len(non_flat)
    total_weeks = len(trades)
    if n == 0:
        print("No non-flat trades.")
        return
    pnls = [t["net"] for t in non_flat]
    rets = [t["net"] / (t["entry"] * CONTRACT_OZ) for t in non_flat]
    total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    mr = sum(rets)/n
    sr = (sum((r-mr)**2 for r in rets)/(n-1))**0.5 if n > 1 else 0
    sharpe = mr/sr*math.sqrt(52) if sr > 0 else 0
    from deflated_sharpe import sr_stats, probabilistic_sharpe
    s = sr_stats(rets); psr = probabilistic_sharpe(s, benchmark_sr=0.0)

    flat = sum(1 for t in trades if t["direction"] == "FLAT")
    flat_rate = 100 * flat / total_weeks

    fold_stats = result["fold_stats"]
    pos_folds = sum(1 for f in fold_stats if f["sharpe"] > 0)
    worst_fold = min(fold_stats, key=lambda f: f["sharpe"])

    print(f"\n=== FAR Weekly ML Direction v1 [OOS 2019-2026] ===")
    print(f"  Total weeks: {total_weeks}  Non-flat trades: {n}  FLAT: {flat} ({flat_rate:.1f}%)")
    print(f"  Win rate (non-flat): {100*wins/n:.1f}%")
    print(f"  Total P&L: ${total:+,.0f}  Mean/trade: ${mean:+,.0f}")
    print(f"  Sharpe(ann): {sharpe:.3f}  Skew: {s.skewness:+.3f}  PSR: {psr:.4f}")
    print(f"  Positive-Sharpe folds: {pos_folds}/{len(fold_stats)}")
    print(f"  Worst fold: fold {worst_fold['fold']}, sharpe {worst_fold['sharpe']:+.2f}, "
          f"total ${worst_fold['total']:+,.0f}")

    print("\n  Per-fold:")
    for f in fold_stats:
        print(f"    fold {f['fold']:>2d}: n={f['n']:>2d} "
              f"L={f['long']:>2d}/S={f['short']:>2d}/F={f['flat']:>2d} "
              f"total=${f['total']:>+7,.0f} sharpe={f['sharpe']:>+5.2f}")

    # Year breakdown
    by_year = defaultdict(list)
    for t in non_flat:
        by_year[str(t["signal_date"])[:4]].append(t)
    print("\n  Year-by-year (non-flat):")
    for y in sorted(by_year):
        yr = by_year[y]; pl = [t["net"] for t in yr]; w = sum(1 for p in pl if p > 0)
        print(f"    {y}: n={len(pl):>3d} WR={100*w/len(pl):>4.1f}% total=${sum(pl):>+8,.0f}")

    # Ship gates
    print("\n=== SHIP GATES ===")
    worst_sharpe = worst_fold["sharpe"]
    gates = [
        ("1. OOS Sharpe >= 0.60", sharpe >= 0.60, f"{sharpe:.3f}"),
        ("2. OOS WR >= 55%", 100*wins/n >= 55.0, f"{100*wins/n:.1f}%"),
        ("3. OOS total > 0", total > 0, f"${total:+,.0f}"),
        ("4. OOS PSR >= 0.90", psr >= 0.90, f"{psr:.3f}"),
        ("5. OOS n >= 100", n >= 100, f"{n}"),
        ("6. Positive folds >= 8/15", pos_folds >= 8, f"{pos_folds}/{len(fold_stats)}"),
        ("7. Worst fold >= -1.0", worst_sharpe >= -1.0, f"{worst_sharpe:.2f}"),
    ]
    passing = sum(1 for _, p, _ in gates if p)
    for label, passed, val in gates:
        print(f"  {'[PASS]' if passed else '[FAIL]'} {label}  actual={val}")
    print(f"\n  {passing}/7 gates pass")
    kill = []
    if sharpe < 0: kill.append("negative OOS Sharpe")
    if worst_sharpe < -1.5: kill.append(f"fold Sharpe {worst_sharpe:.2f} < -1.5")
    if flat_rate > 80: kill.append(f"FLAT rate {flat_rate:.1f}% > 80%")
    if flat_rate < 20: kill.append(f"FLAT rate {flat_rate:.1f}% < 20%")
    if kill:
        print(f"  KILL SWITCHES: {', '.join(kill)}")


def main() -> None:
    print("Building features + labels 2011-2026 ...")
    df = build_features_labels(TRAIN_START, OOS_END)
    print(f"  Rows: {len(df)}  Label balance: {df['label'].mean():.3f} (up-week fraction)")

    print("\nRunning walk-forward CV ...")
    result = walk_forward(df, fold_weeks=FOLD_WEEKS)
    summarize(result)


if __name__ == "__main__":
    main()
