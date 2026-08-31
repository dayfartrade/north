"""FAR Weekly Gold Read v3 backtest.

Pre-reg: docs/experiments/2026-08-31_far_weekly_v3_ry_level_prereg.md

v3 rule:
  LONG  requires all v1 LONG conditions + DXY_chg < 0 + RY_level >= 0.25%
  SHORT requires all v1 SHORT conditions + DXY_chg > 0 + RY_level <= 1.50%
  FLAT otherwise

Compares v3 against v1 and v2 across:
  - Full sample 2010-2026
  - TRAIN 2010-2018 (split-sample train)
  - OOS 2019-2026 (split-sample OOS)
  - M12 LONG vs SHORT regime cells

Then checks all pre-reg ship gates:
  1. v3 OOS Sharpe >= v2 OOS Sharpe (RY_level filter must add value)
  2. v3 total P&L >= 80% of v2's on OOS
  3. v3 total trades on 16yr sample >= 100
  4. TRAIN and OOS Sharpes within 50% of each other
  5. Both regime cells' v3 Sharpes >= v2's cell Sharpes

Reject gates are hard - any single failure retires v3.

Usage: python scripts/far_weekly_v3_backtest.py
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

# Pre-reg locked thresholds
RY_LEVEL_LONG_FLOOR = 0.25   # LONG requires RY >= this
RY_LEVEL_SHORT_CEILING = 1.50  # SHORT requires RY <= this


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


def v2_dir(v1: str, dxy_chg: float | None) -> str:
    if v1 == "LONG" and dxy_chg is not None and dxy_chg < 0:
        return "LONG"
    if v1 == "SHORT" and dxy_chg is not None and dxy_chg > 0:
        return "SHORT"
    return "FLAT"


def v3_dir(v1: str, dxy_chg: float | None, ry_level: float | None) -> str:
    v2 = v2_dir(v1, dxy_chg)
    if v2 == "FLAT" or ry_level is None:
        return "FLAT"
    if v2 == "LONG" and ry_level >= RY_LEVEL_LONG_FLOOR:
        return "LONG"
    if v2 == "SHORT" and ry_level <= RY_LEVEL_SHORT_CEILING:
        return "SHORT"
    return "FLAT"


def collect(df: pd.DataFrame, variant: str) -> list[dict]:
    weeks = far.week_indices(df)
    out = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        v1 = str(sig["direction"])
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")):
            continue
        dxy_chg = float(sig["DXY_chg"]) if pd.notna(sig.get("DXY_chg")) else None
        ry_level = float(sig["RY"]) if pd.notna(sig.get("RY")) else None
        m12 = float(sig["M12"]) if pd.notna(sig.get("M12")) else None
        if variant == "v1":
            direction = v1
        elif variant == "v2":
            direction = v2_dir(v1, dxy_chg)
        elif variant == "v3":
            direction = v3_dir(v1, dxy_chg, ry_level)
        else:
            raise ValueError(variant)
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
        result = far.simulate_week(df.loc[mon:fri], mon, fri, direction, entry, stop)
        if not result:
            continue
        out.append({
            "signal_date": signal_date,
            "direction": direction,
            "regime": "M12_LONG" if (m12 is not None and m12 > 0) else "M12_SHORT",
            "ret": result["net"] / (entry * far.CONTRACT_SIZE),
            "net": result["net"],
            "ry_level": ry_level,
        })
    return out


def stats(trades: list[dict], window: tuple | None = None,
           regime: str | None = None) -> dict:
    subset = trades
    if window is not None:
        s, e = window
        subset = [t for t in subset if s <= t["signal_date"] <= e]
    if regime is not None:
        subset = [t for t in subset if t["regime"] == regime]
    n = len(subset)
    if n == 0:
        return {"n": 0}
    rets = [t["ret"] for t in subset]
    pnls = [t["net"] for t in subset]
    wins = sum(1 for p in pnls if p > 0)
    mean_r = sum(rets) / n
    std_r = ((sum((r - mean_r) ** 2 for r in rets) / (n - 1)) ** 0.5) if n > 1 else 0.0
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0
    return {
        "n": n,
        "wr": round(100 * wins / n, 1),
        "mean_pct": round(100 * mean_r, 3),
        "sharpe": round(sharpe, 3),
        "cum": round(sum(pnls), 0),
    }


def line(label: str, s: dict) -> str:
    if s.get("n", 0) == 0:
        return f"  {label:<32} n=0"
    return (f"  {label:<32} n={s['n']:>3}  WR={s['wr']:>5.1f}%  "
            f"mean={s['mean_pct']:>+7.3f}%  Sharpe={s['sharpe']:>+7.3f}  "
            f"cum=${s['cum']:>9,.0f}")


def main() -> None:
    print(f"v3 thresholds (LOCKED per pre-reg):")
    print(f"  LONG floor:    RY_level >= {RY_LEVEL_LONG_FLOOR}%")
    print(f"  SHORT ceiling: RY_level <= {RY_LEVEL_SHORT_CEILING}%")
    print()

    print("[load]")
    df = load_signals()

    v1_trades = collect(df, "v1")
    v2_trades = collect(df, "v2")
    v3_trades = collect(df, "v3")

    train = (pd.Timestamp("2010-01-01", tz="UTC"),
             pd.Timestamp("2018-12-31", tz="UTC"))
    oos =   (pd.Timestamp("2019-01-01", tz="UTC"),
             pd.Timestamp("2026-08-31", tz="UTC"))

    print("\n=== FULL SAMPLE 2010-2026 ===")
    print(line("v1", stats(v1_trades)))
    print(line("v2", stats(v2_trades)))
    print(line("v3", stats(v3_trades)))

    print("\n=== TRAIN 2010-2018 ===")
    print(line("v1", stats(v1_trades, window=train)))
    print(line("v2", stats(v2_trades, window=train)))
    print(line("v3", stats(v3_trades, window=train)))

    print("\n=== OOS 2019-2026 (ship gate window) ===")
    v1_oos = stats(v1_trades, window=oos)
    v2_oos = stats(v2_trades, window=oos)
    v3_oos = stats(v3_trades, window=oos)
    print(line("v1", v1_oos))
    print(line("v2", v2_oos))
    print(line("v3", v3_oos))

    print("\n=== v3 by M12 regime (full sample) ===")
    print(line("v3 M12 LONG",  stats(v3_trades, regime="M12_LONG")))
    print(line("v3 M12 SHORT", stats(v3_trades, regime="M12_SHORT")))

    print("\n=== v2 by M12 regime (baseline for comparison) ===")
    print(line("v2 M12 LONG",  stats(v2_trades, regime="M12_LONG")))
    print(line("v2 M12 SHORT", stats(v2_trades, regime="M12_SHORT")))

    print("\n=== PRE-REG SHIP GATES ===")
    fail = 0
    gates = []

    # Gate 1
    if v3_oos.get("n"):
        ok = v3_oos["sharpe"] >= v2_oos["sharpe"]
        gates.append(("Gate 1: v3 OOS Sharpe >= v2 OOS",
                      f"v3={v3_oos['sharpe']:.3f}  v2={v2_oos['sharpe']:.3f}", ok))
        if not ok: fail += 1

    # Gate 2
    if v3_oos.get("n") and v2_oos.get("n"):
        v3c = v3_oos["cum"]; v2c = v2_oos["cum"]
        ok = v3c >= 0.80 * v2c if v2c > 0 else v3c >= v2c
        gates.append(("Gate 2: v3 OOS P&L >= 80% of v2 OOS",
                      f"v3=${v3c:,.0f}  v2=${v2c:,.0f}  ratio={100*v3c/v2c if v2c else 0:.1f}%", ok))
        if not ok: fail += 1

    # Gate 3
    v3_full = stats(v3_trades)
    n_v3 = v3_full.get("n", 0)
    ok = n_v3 >= 100
    gates.append(("Gate 3: v3 total trades >= 100", f"n={n_v3}", ok))
    if not ok: fail += 1

    # Gate 4
    v3_train = stats(v3_trades, window=train)
    if v3_train.get("n") and v3_oos.get("n"):
        st = v3_train["sharpe"]; so = v3_oos["sharpe"]
        if st != 0:
            ratio = abs(so - st) / abs(st)
            ok = ratio <= 0.50
            gates.append(("Gate 4: |TRAIN vs OOS Sharpe| <= 50%",
                          f"train={st:.3f}  oos={so:.3f}  diff={100*ratio:.0f}%", ok))
            if not ok: fail += 1

    # Gate 5: regime cells
    v3_ml = stats(v3_trades, regime="M12_LONG")
    v3_ms = stats(v3_trades, regime="M12_SHORT")
    v2_ml = stats(v2_trades, regime="M12_LONG")
    v2_ms = stats(v2_trades, regime="M12_SHORT")
    if v3_ml.get("n") and v3_ms.get("n"):
        ok_l = v3_ml["sharpe"] >= v2_ml["sharpe"]
        ok_s = v3_ms["sharpe"] >= v2_ms["sharpe"]
        ok = ok_l and ok_s
        gates.append(("Gate 5: v3 Sharpe >= v2 in both regime cells",
                      f"LONG v3={v3_ml['sharpe']:.3f}/v2={v2_ml['sharpe']:.3f}  "
                      f"SHORT v3={v3_ms['sharpe']:.3f}/v2={v2_ms['sharpe']:.3f}", ok))
        if not ok: fail += 1

    for label, detail, ok in gates:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}   {detail}")

    print()
    if fail == 0:
        print("VERDICT: All ship gates PASS. v3 proceeds to forward-validation window.")
    else:
        print(f"VERDICT: {fail} gate(s) FAILED. Per pre-reg reject gates: v3 REJECTS.")


if __name__ == "__main__":
    main()
