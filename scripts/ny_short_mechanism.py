"""Mechanism investigation for the NY-SHORT+Low-ER+Mon-Wed edge.

Questions to answer:
  1. Is exit-time bimodal? (target hit fast = intraday flush pattern; time-exit = drift)
  2. Correlation with prior-day DXY move? (dollar strength catalyst)
  3. Correlation with prior-day real-yield change? (macro catalyst)
  4. Overlap with FOMC/CPI/NFP days from calendar? (news catalyst)
  5. Time-since-London-close pattern? (London profit-taking bleeding into NY?)
  6. Where do stops hit vs targets — MAE/MFE if we can approximate?
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TRADES = ROOT / "data" / "analysis_gold_trades.csv"
XAU_5M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"
DXY = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"
REAL_YIELD = ROOT / "data" / "macro" / "real_yield_10y__DFII10.csv"
CALENDAR = ROOT / "data" / "calendar" / "events.csv"


def load_daily_series(path: Path) -> pd.Series:
    df = pd.read_csv(path)
    date_col = "date" if "date" in df.columns else ("ts" if "ts" in df.columns else df.columns[0])
    df[date_col] = pd.to_datetime(df[date_col]).dt.date
    val_col = "value" if "value" in df.columns else df.columns[-1]
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna(subset=[val_col])
    return df.set_index(date_col)[val_col]


def main() -> None:
    trades = pd.read_csv(TRADES)
    trades["date"] = pd.to_datetime(trades["date"]).dt.date
    sub = trades[(trades["session"] == "NY") & (trades["direction_fwd"] == "SHORT")
                 & (trades["er_band"] == "low") & (trades["dow"].isin(["Mon", "Tue", "Wed"]))].copy()
    print(f"NY-SHORT+LowER+Mon-Wed subset: n={len(sub)}")
    print(f"Wins: n={(sub['pnl_forward']>0).sum()}  Losses: n={(sub['pnl_forward']<=0).sum()}")
    print()

    winners = sub[sub["pnl_forward"] > 0]
    losers = sub[sub["pnl_forward"] <= 0]

    # -------- 1. DXY move analysis --------
    print("=== DXY (dollar index) — prior-day change ===")
    try:
        dxy = load_daily_series(DXY).sort_index()
        # Compute prior-day % change; dxy is monthly-ish in your setup? check
        # Actually DFEXBGS is weekly. Use last-value-on-or-before + 1w back.
        def prev_1w_change(d):
            key = None
            for k in dxy.index:
                if k <= d:
                    if key is None or k > key:
                        key = k
            if key is None:
                return None
            # 5 trading days back
            prior_key = None
            target = key - pd.Timedelta(days=7)
            for k in dxy.index:
                if k <= target.date():
                    if prior_key is None or k > prior_key:
                        prior_key = k
            if prior_key is None:
                return None
            return 100 * (dxy[key] - dxy[prior_key]) / dxy[prior_key]

        sub["dxy_1w_pct"] = sub["date"].apply(prev_1w_change)
        for label, group in [("winners", winners), ("losers", losers)]:
            g = group.copy()
            g["dxy_1w_pct"] = g["date"].apply(prev_1w_change)
            g = g.dropna(subset=["dxy_1w_pct"])
            if len(g):
                print(f"  {label:8s}  n={len(g):>3d}  mean DXY 1w chg = {g['dxy_1w_pct'].mean():+.2f}%  median = {g['dxy_1w_pct'].median():+.2f}%")
    except Exception as e:
        print(f"  DXY analysis skipped: {e}")
    print()

    # -------- 2. Real yield --------
    print("=== 10Y real yield — prior-day level ===")
    try:
        ry = load_daily_series(REAL_YIELD).sort_index()
        def last_on_or_before(d):
            key = None
            for k in ry.index:
                if k <= d:
                    if key is None or k > key:
                        key = k
            return ry.get(key) if key else None
        for label, group in [("winners", winners), ("losers", losers)]:
            vals = group["date"].apply(last_on_or_before).dropna()
            if len(vals):
                print(f"  {label:8s}  n={len(vals):>3d}  mean real yield = {vals.mean():.2f}%  median = {vals.median():.2f}%")
    except Exception as e:
        print(f"  Real yield analysis skipped: {e}")
    print()

    # -------- 3. Calendar overlap --------
    print("=== Macro calendar overlap (FOMC/CPI/NFP/PPI) ===")
    try:
        cal = pd.read_csv(CALENDAR)
        # Detect date column
        date_col = None
        for c in ["date", "release_date", "ts", "event_date"]:
            if c in cal.columns:
                date_col = c
                break
        if date_col:
            cal[date_col] = pd.to_datetime(cal[date_col], errors="coerce").dt.date
        # Detect event column
        evt_col = None
        for c in ["event", "release", "code", "name", "series"]:
            if c in cal.columns:
                evt_col = c
                break
        important = cal[cal[evt_col].astype(str).str.upper().str.contains("FOMC|CPI|NFP|PAYROLLS|PPI", na=False)] if evt_col else pd.DataFrame()
        important_dates = set(important[date_col].dropna())
        for label, group in [("winners", winners), ("losers", losers)]:
            match = sum(1 for d in group["date"] if d in important_dates)
            print(f"  {label:8s}  n={len(group):>3d}  on macro-event day: {match} ({100*match/max(len(group),1):.1f}%)")
        print(f"  Sample size of important dates in window: {sum(1 for d in important_dates if d >= min(sub['date']) and d <= max(sub['date']))}")
    except Exception as e:
        print(f"  Calendar analysis skipped: {e}")
    print()

    # -------- 4. Time-since-London-close (14:00 UTC?) — winners vs losers exit time --------
    print("=== Exit price info (approximate — mean/std P&L by group) ===")
    for label, group in [("winners", winners), ("losers", losers)]:
        if len(group):
            print(f"  {label:8s}  n={len(group):>3d}  mean P&L = ${group['pnl_forward'].mean():+.2f}  "
                  f"median = ${group['pnl_forward'].median():+.2f}  "
                  f"std = ${group['pnl_forward'].std():+.2f}")
    print()

    # -------- 5. Feature summary — winners vs losers on entry features --------
    print("=== Entry feature comparison (winners vs losers) ===")
    features = ["or_range", "atr", "or_atr_ratio", "er"]
    for f in features:
        if f in sub.columns:
            w = winners[f]
            l = losers[f]
            print(f"  {f:15s}  winners mean={w.mean():.3f}  losers mean={l.mean():.3f}  ratio={w.mean()/l.mean() if l.mean() else float('nan'):.2f}")
    print()

    # -------- 6. Hour-within-NY-session breakdown (entry hour UTC) --------
    print("=== Entry hour UTC (should mostly be 13:00 = NY open) ===")
    hr_stats = sub.groupby("hour_utc")["pnl_forward"].agg(["count", "sum", "mean", lambda x: (x>0).mean()])
    hr_stats.columns = ["n", "total", "mean", "win_rate"]
    for h, r in hr_stats.iterrows():
        print(f"  {h:02d}:00  n={int(r['n']):>2d}  total=${r['total']:>+7,.0f}  mean=${r['mean']:>+7.2f}  win={100*r['win_rate']:.0f}%")
    print()

    # -------- 7. Month-of-year pattern --------
    sub["month"] = pd.to_datetime(sub["date"]).dt.month
    print("=== Month of year (seasonality) ===")
    m_stats = sub.groupby("month")["pnl_forward"].agg(["count", "sum", "mean"])
    m_stats.columns = ["n", "total", "mean"]
    for m, r in m_stats.iterrows():
        month_name = pd.Timestamp(2020, int(m), 1).strftime("%b")
        print(f"  {month_name}  n={int(r['n']):>2d}  total=${r['total']:>+7,.0f}  mean=${r['mean']:>+7.2f}")


if __name__ == "__main__":
    main()
