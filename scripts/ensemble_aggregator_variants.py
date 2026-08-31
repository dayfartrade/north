"""Alternative ensemble aggregator variants.

Follow-on to today's finding that the current ensemble (2-of-3
majority of v1+v2+monthly M12) reduces to essentially v1 in the
current M12 LONG regime, and only differs from v1 in M12 SHORT.

Question: is there a better aggregator? Specifically:
  - Does M12 add anything over v2 alone?
  - Would requiring unanimous 3-way agreement produce a tighter,
    higher-quality filter at the cost of fewer trades?

Test three aggregators:
  1. ensemble_current: 2-of-3 majority of {v1, v2, monthly M12} (baseline)
  2. ensemble_unanimous: all three must agree (v1 == v2 == monthly)
  3. v2_alone: v2 direction only (reference; equivalent to "v1 AND v2")

Report full-sample + regime-cell stats for each.

This is exploratory analysis. Not a pre-reg for a new candidate.

Usage: python scripts/ensemble_aggregator_variants.py
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


def variant_directions(sig: pd.Series) -> dict:
    v1 = str(sig["direction"])
    dxy_chg = float(sig["DXY_chg"]) if pd.notna(sig.get("DXY_chg")) else None
    m12 = float(sig["M12"]) if pd.notna(sig.get("M12")) else None

    if v1 == "LONG" and dxy_chg is not None and dxy_chg < 0: v2 = "LONG"
    elif v1 == "SHORT" and dxy_chg is not None and dxy_chg > 0: v2 = "SHORT"
    else: v2 = "FLAT"

    if m12 is None: monthly = "FLAT"
    elif m12 > 0: monthly = "LONG"
    elif m12 < 0: monthly = "SHORT"
    else: monthly = "FLAT"

    votes_long = sum(1 for d in (v1, v2, monthly) if d == "LONG")
    votes_short = sum(1 for d in (v1, v2, monthly) if d == "SHORT")

    # ensemble_current: 2-of-3 majority
    if votes_long >= 2:   ens_curr = "LONG"
    elif votes_short >= 2: ens_curr = "SHORT"
    else: ens_curr = "FLAT"

    # ensemble_unanimous: all three agree (non-FLAT)
    if v1 == v2 == monthly and v1 != "FLAT":
        ens_una = v1
    else:
        ens_una = "FLAT"

    return {
        "v1": v1, "v2": v2, "monthly": monthly,
        "ens_curr": ens_curr, "ens_una": ens_una,
        "m12": m12,
    }


def collect(df: pd.DataFrame, variant_key: str) -> list[dict]:
    weeks = far.week_indices(df)
    out = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")):
            continue
        dirs = variant_directions(sig)
        direction = dirs[variant_key]
        if direction == "FLAT":
            continue
        entry = float(df.loc[mon, "open"])
        atr = float(sig["ATR"])
        if atr <= 0:
            continue
        if direction == "LONG":
            stop = entry - far.STOP_ATR_MULT * atr
        else:
            stop = entry + far.STOP_ATR_MULT * atr
        r = far.simulate_week(df.loc[mon:fri], mon, fri, direction, entry, stop)
        if not r:
            continue
        m12 = dirs["m12"]
        regime = "M12_LONG" if (m12 is not None and m12 > 0) else "M12_SHORT"
        out.append({
            "signal_date": signal_date,
            "ret": r["net"] / (entry * far.CONTRACT_SIZE),
            "net": r["net"],
            "regime": regime,
        })
    return out


def stats(trades: list[dict], regime: str | None = None) -> dict:
    subset = trades if regime is None else [t for t in trades if t["regime"] == regime]
    n = len(subset)
    if n == 0: return {"n": 0}
    rets = [t["ret"] for t in subset]
    pnls = [t["net"] for t in subset]
    wins = sum(1 for p in pnls if p > 0)
    mean_r = sum(rets) / n
    std_r = ((sum((r - mean_r) ** 2 for r in rets) / (n - 1)) ** 0.5) if n > 1 else 0.0
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0
    return {
        "n": n, "wr": round(100 * wins / n, 1),
        "mean_pct": round(100 * mean_r, 3),
        "sharpe": round(sharpe, 3),
        "cum": round(sum(pnls), 0),
    }


def line(label: str, s: dict) -> str:
    if s.get("n", 0) == 0: return f"  {label:<30} n=0"
    return (f"  {label:<30} n={s['n']:>3}  WR={s['wr']:>5.1f}%  "
            f"mean={s['mean_pct']:>+7.3f}%  Sharpe={s['sharpe']:>+7.3f}  "
            f"cum=${s['cum']:>10,.0f}")


def main() -> None:
    print("[load]")
    df = load_signals()

    variants = [
        ("v1",       "v1"),
        ("v2",       "v2"),
        ("ens_curr", "ensemble_current (2-of-3 maj)"),
        ("ens_una",  "ensemble_unanimous (all 3)"),
    ]

    print("\n=== FULL SAMPLE 2010-2026 ===")
    for key, label in variants:
        trades = collect(df, key)
        print(line(label, stats(trades)))

    print("\n=== M12 LONG regime ===")
    for key, label in variants:
        trades = collect(df, key)
        print(line(label, stats(trades, regime="M12_LONG")))

    print("\n=== M12 SHORT regime ===")
    for key, label in variants:
        trades = collect(df, key)
        print(line(label, stats(trades, regime="M12_SHORT")))


if __name__ == "__main__":
    main()
