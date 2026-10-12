"""Regime-disagreement trade analysis.

Follow-up #4 from 2026-09-08 agenda queue: are historical trades in
regime-disagreement periods systematically worse? If yes, a "sit out
disagreement" filter is a legitimate v3 design element on its own.

Regime definitions (all computed on daily close as of signal date):
  M12 = 252-day percent change (annual trend)
  M6  = 126-day percent change (6-month trend)
  M3  =  63-day percent change (3-month trend)

Disagreement states:
  FULL_AGREE   : sign(M12) == sign(M6) == sign(M3) and all non-zero
  M3_FLIP      : M12 and M6 agree; M3 opposite sign
  M6_FLIP      : M12 and M3 agree; M6 opposite sign (unusual)
  M12_FLIP     : M6 and M3 agree; M12 opposite sign (classic reversal)
  SPLIT_LONG   : M12=LONG, M6=SHORT, M3=SHORT (fading extended uptrend)
  SPLIT_SHORT  : M12=SHORT, M6=LONG, M3=LONG (fading extended downtrend)
  ZERO         : any horizon exactly zero / missing

Analysis slices:
  (a) v1 trades × regime state × direction
  (b) v2 (DXY-filtered) trades × regime state × direction
  (c) cross-tab with M20 bucket (does disagreement explain the Q5 pathology?)

No pre-reg. Diagnostic for v3 design. Post-hoc slicing, Bonferroni cost tracked.

Usage:
  python scripts/regime_disagreement_trade_analysis.py
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

M12_WINDOW = 252
M6_WINDOW = 126
M3_WINDOW = 63


def sign(x: float) -> str:
    if pd.isna(x) or x == 0:
        return "0"
    return "L" if x > 0 else "S"


def classify_regime(m12: float, m6: float, m3: float) -> str:
    s12, s6, s3 = sign(m12), sign(m6), sign(m3)
    if "0" in (s12, s6, s3):
        return "ZERO"
    if s12 == s6 == s3:
        return "FULL_AGREE"
    # SPLIT patterns (M12 vs recent horizons)
    if s12 == "L" and s6 == "S" and s3 == "S":
        return "SPLIT_LONG"
    if s12 == "S" and s6 == "L" and s3 == "L":
        return "SPLIT_SHORT"
    # single-horizon flips
    if s12 == s3 and s6 != s12:
        return "M6_FLIP"
    if s12 == s6 and s3 != s12:
        return "M3_FLIP"
    if s6 == s3 and s12 != s6:
        return "M12_FLIP"
    return "OTHER"


def load_signals() -> pd.DataFrame:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-07-01", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    df = far.build_signals(daily, ry)
    dxy = far.load_macro_series(DXY_PATH, "dxy")
    dxy_daily = dxy.reindex(
        df.index.tz_localize(None) if df.index.tz else df.index, method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(far.RY_LAG)
    df["M12"] = df["close"].pct_change(M12_WINDOW)
    df["M6"] = df["close"].pct_change(M6_WINDOW)
    df["M3"] = df["close"].pct_change(M3_WINDOW)
    return df


def run_trades(df: pd.DataFrame) -> list[dict]:
    weeks = far.week_indices(df)
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig = df.loc[signal_date]
        v1_dir = str(sig["direction"])
        if v1_dir == "FLAT":
            continue
        if pd.isna(sig["ATR"]) or pd.isna(sig["M60"]):
            continue
        entry = float(df.loc[mon]["open"])
        atr = float(sig["ATR"])
        if atr <= 0:
            continue
        if v1_dir == "LONG":
            stop = entry - far.STOP_ATR_MULT * atr
        else:
            stop = entry + far.STOP_ATR_MULT * atr
        r = far.simulate_week(df.loc[mon:fri], mon, fri, v1_dir, entry, stop)
        if not r:
            continue
        dxy_chg = float(sig["DXY_chg"]) if pd.notna(sig.get("DXY_chg")) else None
        if v1_dir == "LONG" and dxy_chg is not None and dxy_chg < 0:
            v2_dir = "LONG"
        elif v1_dir == "SHORT" and dxy_chg is not None and dxy_chg > 0:
            v2_dir = "SHORT"
        else:
            v2_dir = "FLAT"
        m12 = float(sig["M12"]) if pd.notna(sig.get("M12")) else np.nan
        m6 = float(sig["M6"]) if pd.notna(sig.get("M6")) else np.nan
        m3 = float(sig["M3"]) if pd.notna(sig.get("M3")) else np.nan
        regime = classify_regime(m12, m6, m3)
        trades.append({
            "signal_date": signal_date,
            "v1_dir": v1_dir,
            "v2_dir": v2_dir,
            "M20_pct": float(sig["M20"]) * 100,
            "M3_pct": m3 * 100 if not np.isnan(m3) else np.nan,
            "M6_pct": m6 * 100 if not np.isnan(m6) else np.nan,
            "M12_pct": m12 * 100 if not np.isnan(m12) else np.nan,
            "regime": regime,
            "ret": r["net"] / (entry * far.CONTRACT_SIZE),
            "net": r["net"],
        })
    return trades


def sharpe(returns: np.ndarray) -> float:
    if len(returns) < 2:
        return float("nan")
    m, s = returns.mean(), returns.std(ddof=1)
    return (m / s) * np.sqrt(52) if s > 0 else 0.0


def summarize(trades: list[dict], label: str, dir_key: str) -> None:
    print(f"\n=== {label} ===")
    print(f"  {'regime':<12} {'dir':<6} {'n':>4} {'WR':>6} {'mean$':>9} {'total$':>10} {'Sharpe':>7}")
    df = pd.DataFrame(trades)
    if "regime" not in df.columns:
        return
    for regime in ["FULL_AGREE", "M3_FLIP", "M6_FLIP", "M12_FLIP",
                   "SPLIT_LONG", "SPLIT_SHORT", "OTHER", "ZERO"]:
        for direction in ["LONG", "SHORT"]:
            sub = df[(df["regime"] == regime) & (df[dir_key] == direction)]
            if len(sub) == 0:
                continue
            rets = sub["ret"].to_numpy()
            nets = sub["net"].to_numpy()
            wr = (nets > 0).mean() * 100
            print(f"  {regime:<12} {direction:<6} {len(sub):>4} "
                  f"{wr:>5.1f}% ${nets.mean():>7.0f} ${nets.sum():>9.0f} "
                  f"{sharpe(rets):>7.2f}")


def summarize_disagreement_binary(trades: list[dict], label: str, dir_key: str) -> None:
    """Binary: agree vs any-disagreement; by direction."""
    print(f"\n=== {label} - binary agree vs disagree ===")
    df = pd.DataFrame(trades)
    df["agree"] = df["regime"].eq("FULL_AGREE")
    print(f"  {'bucket':<30} {'n':>4} {'WR':>6} {'mean$':>9} {'total$':>10} {'Sharpe':>7}")
    for direction in ["LONG", "SHORT"]:
        for agree_val, agree_lbl in [(True, "FULL_AGREE"), (False, "disagree")]:
            sub = df[(df["agree"] == agree_val) & (df[dir_key] == direction)]
            if len(sub) == 0:
                continue
            rets = sub["ret"].to_numpy()
            nets = sub["net"].to_numpy()
            wr = (nets > 0).mean() * 100
            print(f"  {direction}_{agree_lbl:<22} {len(sub):>4} "
                  f"{wr:>5.1f}% ${nets.mean():>7.0f} ${nets.sum():>9.0f} "
                  f"{sharpe(rets):>7.2f}")


def crosstab_m20_regime(trades: list[dict], dir_key: str, direction: str) -> None:
    """2x2: {M20 top quintile} x {regime=agree/disagree} for one direction."""
    df = pd.DataFrame(trades)
    sub = df[df[dir_key] == direction].copy()
    if len(sub) < 20:
        return
    thresh = sub["M20_pct"].quantile(0.80)
    sub["m20_q5"] = sub["M20_pct"] >= thresh if direction == "LONG" else sub["M20_pct"] <= -abs(thresh)
    sub["agree"] = sub["regime"].eq("FULL_AGREE")
    print(f"\n=== {dir_key}:{direction} crosstab - M20 top quintile × full-agreement ===")
    print(f"  M20 threshold ({'>=' if direction=='LONG' else '<='}): "
          f"{thresh:.2f}% (|M20|)")
    print(f"  {'cell':<28} {'n':>4} {'WR':>6} {'mean$':>9} {'total$':>10} {'Sharpe':>7}")
    for m20_q5 in [True, False]:
        for agree in [True, False]:
            cell = sub[(sub["m20_q5"] == m20_q5) & (sub["agree"] == agree)]
            if len(cell) == 0:
                continue
            label = (f"{'Q5_extreme' if m20_q5 else 'Q1-Q4_norm'}"
                     f"×{'AGREE' if agree else 'DISAGREE'}")
            rets = cell["ret"].to_numpy()
            nets = cell["net"].to_numpy()
            wr = (nets > 0).mean() * 100
            print(f"  {label:<28} {len(cell):>4} "
                  f"{wr:>5.1f}% ${nets.mean():>7.0f} ${nets.sum():>9.0f} "
                  f"{sharpe(rets):>7.2f}")


def main() -> None:
    print("Regime-disagreement trade analysis")
    print("Window: 2010-01-01 to 2026-07-01")
    print("M12=252d pct_change, M6=126d, M3=63d (daily close)")
    df = load_signals()
    print(f"Signals rows: {len(df)}")

    trades = run_trades(df)
    print(f"v1 trades: {sum(1 for t in trades if t['v1_dir'] != 'FLAT')}")
    v2_trades = [t for t in trades if t["v2_dir"] != "FLAT"]
    print(f"v2 trades: {len(v2_trades)}")

    # Full regime breakdown counts (all v1 trades)
    df_all = pd.DataFrame(trades)
    print(f"\n=== Regime count distribution across v1 trades ===")
    print(df_all["regime"].value_counts().to_string())

    # v1
    summarize(trades, "v1 trades by regime × direction", "v1_dir")
    summarize_disagreement_binary(trades, "v1 trades", "v1_dir")
    crosstab_m20_regime(trades, "v1_dir", "LONG")
    crosstab_m20_regime(trades, "v1_dir", "SHORT")

    # v2 (DXY-filtered)
    summarize(v2_trades, "v2 (DXY-filtered) trades by regime × direction", "v2_dir")
    summarize_disagreement_binary(v2_trades, "v2 (DXY-filtered) trades", "v2_dir")
    crosstab_m20_regime(v2_trades, "v2_dir", "LONG")
    crosstab_m20_regime(v2_trades, "v2_dir", "SHORT")

    # Save trade-level CSV for later
    out = ROOT / "data" / "experiments" / "regime_disagreement_trades.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df_all.to_csv(out, index=False)
    print(f"\nTrade-level CSV: {out}")


if __name__ == "__main__":
    main()
