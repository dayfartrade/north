"""M12 regime-transition leading indicators.

Follow-up #1 from docs/experiments/2026-08-31_m12_regime_persistence.md.

Question: what macro conditions typically precede an M12 sign flip?
If any feature is systematically different in the 30 or 60 days
BEFORE a flip vs during steady-state regime, we could add an
early-warning signal.

For each M12 flip:
  - Snapshot macro state 30 and 60 trading days before the flip
  - Snapshot the same features during "steady-state" (mid-regime)
  - Compare distributions

Features:
  - DXY level and 20d change
  - Real yield level and 20d change
  - Gold M20 (near-term momentum)
  - Gold ATR (volatility)
  - Distance from current M12 (how close to zero already?)

Exploratory: no pre-reg, no rule. Just: is there any signal?

Usage: python scripts/m12_transition_indicators.py
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


def load_all() -> pd.DataFrame:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-08-31", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    dxy = far.load_macro_series(DXY_PATH, "dxy")
    df = daily.copy()
    df["M20"] = df["close"].pct_change(20)
    df["M12"] = df["close"].pct_change(252)
    df["ATR"] = far.compute_atr(df, 20)
    df["ATR_pct"] = 100 * df["ATR"] / df["close"]
    ry_daily = ry.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                           method="ffill")
    ry_daily.index = df.index
    df["RY"] = ry_daily
    df["RY_chg"] = df["RY"].diff(20)
    dxy_daily = dxy.reindex(df.index.tz_localize(None) if df.index.tz else df.index,
                             method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(20)
    return df


def find_flips(df: pd.DataFrame) -> list[dict]:
    m12 = df["M12"].dropna()
    prev_sign = None
    prev_date = None
    flips = []
    for ts, val in m12.items():
        sign = "L" if val > 0 else "S" if val < 0 else "Z"
        if prev_sign is not None and sign != prev_sign and sign != "Z" and prev_sign != "Z":
            flips.append({
                "date": ts,
                "from": prev_sign,
                "to": sign,
                "m12_at_flip": val,
                "m12_1w_before": m12.loc[prev_date] if prev_date in m12.index else None,
            })
        prev_sign = sign
        prev_date = ts
    return flips


def snapshot(df: pd.DataFrame, date: pd.Timestamp, lookback: int) -> dict | None:
    """Snapshot features `lookback` trading days before `date`."""
    idx = df.index.get_indexer([date], method="ffill")[0]
    if idx - lookback < 0:
        return None
    snap = df.iloc[idx - lookback]
    return {
        "date": df.index[idx - lookback],
        "DXY": float(snap["DXY"]) if pd.notna(snap.get("DXY")) else None,
        "DXY_chg_20d": float(snap["DXY_chg"]) if pd.notna(snap.get("DXY_chg")) else None,
        "RY": float(snap["RY"]) if pd.notna(snap.get("RY")) else None,
        "RY_chg_20d": float(snap["RY_chg"]) if pd.notna(snap.get("RY_chg")) else None,
        "gold_M20": float(snap["M20"]) if pd.notna(snap.get("M20")) else None,
        "gold_ATR_pct": float(snap["ATR_pct"]) if pd.notna(snap.get("ATR_pct")) else None,
        "gold_M12_abs": abs(float(snap["M12"])) if pd.notna(snap.get("M12")) else None,
    }


def compare_dists(pre_flip: list[dict], control: list[dict]) -> None:
    features = ["DXY_chg_20d", "RY", "RY_chg_20d", "gold_M20", "gold_ATR_pct", "gold_M12_abs"]
    print(f"  {'feature':<20} {'pre-flip (n=' + str(len(pre_flip)) + ')':>25} "
          f"{'steady (n=' + str(len(control)) + ')':>25} {'diff':>10}")
    for f in features:
        pre = [x[f] for x in pre_flip if x.get(f) is not None]
        ctl = [x[f] for x in control if x.get(f) is not None]
        if not pre or not ctl:
            continue
        mp = np.median(pre); mc = np.median(ctl)
        diff = mp - mc
        print(f"  {f:<20} med={mp:>+8.4f} mean={np.mean(pre):>+8.4f}    "
              f"med={mc:>+8.4f} mean={np.mean(ctl):>+8.4f}    "
              f"{diff:>+9.4f}")


def main() -> None:
    df = load_all()
    print(f"loaded {len(df)} daily bars")

    flips = find_flips(df)
    print(f"total M12 flips detected: {len(flips)}")
    # Filter to "meaningful" flips: only count if the streak that ended was >= 20 days
    # Otherwise we're counting single-day whipsaws.
    m12 = df["M12"].dropna()
    prev_sign = None
    streak_start = None
    streaks_by_end = {}
    for ts, val in m12.items():
        sign = "L" if val > 0 else "S" if val < 0 else "Z"
        if sign != prev_sign and sign != "Z" and prev_sign is not None and prev_sign != "Z":
            # streak ended at ts
            length = (ts - streak_start).days if streak_start else 0
            streaks_by_end[ts] = length
        if sign != prev_sign:
            streak_start = ts
        prev_sign = sign

    meaningful_flips = [f for f in flips if streaks_by_end.get(f["date"], 0) >= 20]
    print(f"meaningful flips (from streak >= 20d): {len(meaningful_flips)}")

    # For each meaningful flip, snapshot 30 and 60 trading days before
    pre_30 = []
    pre_60 = []
    for flip in meaningful_flips:
        s30 = snapshot(df, flip["date"], 30)
        s60 = snapshot(df, flip["date"], 60)
        if s30: pre_30.append(s30)
        if s60: pre_60.append(s60)

    # Control: random dates in mid-regime (M12 direction stable both 30d before and 30d after)
    import random
    random.seed(42)
    m12_sign = np.where(df["M12"] > 0, 1, np.where(df["M12"] < 0, -1, 0))
    control = []
    for i in range(90, len(df) - 30):
        if m12_sign[i] != 0 and all(m12_sign[i - 30:i + 30] == m12_sign[i]):
            control.append(df.index[i])
    random.shuffle(control)
    control_dates = control[:200]  # cap at 200 samples
    control_snaps = []
    for d in control_dates:
        snap = snapshot(df, d, 0)
        if snap: control_snaps.append(snap)

    print(f"\n=== 30 trading days BEFORE meaningful M12 flip vs steady-state ===")
    compare_dists(pre_30, control_snaps)

    print(f"\n=== 60 trading days BEFORE meaningful M12 flip vs steady-state ===")
    compare_dists(pre_60, control_snaps)

    # Split by flip direction (LONG->SHORT vs SHORT->LONG)
    long_to_short = [f for f in meaningful_flips if f["from"] == "L" and f["to"] == "S"]
    short_to_long = [f for f in meaningful_flips if f["from"] == "S" and f["to"] == "L"]
    print(f"\nflip counts: L->S: {len(long_to_short)}   S->L: {len(short_to_long)}")

    if long_to_short:
        pre60_ls = [snapshot(df, f["date"], 60) for f in long_to_short]
        pre60_ls = [x for x in pre60_ls if x]
        print(f"\n=== 60 days BEFORE L->S flip (bull ending) vs steady state ===")
        compare_dists(pre60_ls, control_snaps)


if __name__ == "__main__":
    main()
