"""M12 regime-split ensemble analysis.

Follow-up to docs/experiments/2026-08-31_monthly_m12_regime_audit.md.

Runs a full 16-year backtest for v1, v2 (v1 + DXY filter), and the
ensemble (v1 + v2 + monthly M12 majority) using the shipping backtest
engine. Then partitions every trade by the monthly M12 regime that was
active at signal_date (LONG regime = M12 > 0, SHORT regime = M12 < 0).

For each (variant x regime) cell, reports:
  - n trades, WR, mean %/trade, Sharpe (per-trade * sqrt(52))
  - cumulative $ P&L per contract
  - fraction of that regime's weeks the variant took a trade

Purpose: answer "is the ensemble's Sharpe 1.012 backtest driven by one
regime, or is the vote actually adding value in both regimes?"

Data source: Dukascopy XAUUSD 5m (through 2026-07-20 locally) + FRED
DFII10 + DTWEXBGS. Run this on a workstation with fresh data for the
authoritative number.

Usage:
    python scripts/m12_regime_split_ensemble.py
    python scripts/m12_regime_split_ensemble.py --write-doc  # append
                                                              # findings to
                                                              # a dated doc
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from pathlib import Path
from collections import defaultdict

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


def load_all() -> pd.DataFrame:
    """Load daily bars + RY + DXY + M12, return signals df with everything."""
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


def variant_directions(sig_row: pd.Series) -> dict:
    """Return {v1, v2, ensemble} directions for one signal row."""
    v1 = str(sig_row["direction"])
    dxy_chg = sig_row.get("DXY_chg")
    dxy_chg = float(dxy_chg) if pd.notna(dxy_chg) else None
    m12 = sig_row.get("M12")
    m12 = float(m12) if pd.notna(m12) else None

    if v1 == "LONG" and dxy_chg is not None and dxy_chg < 0:
        v2 = "LONG"
    elif v1 == "SHORT" and dxy_chg is not None and dxy_chg > 0:
        v2 = "SHORT"
    else:
        v2 = "FLAT"

    if m12 is None:
        monthly = "FLAT"
    elif m12 > 0:
        monthly = "LONG"
    elif m12 < 0:
        monthly = "SHORT"
    else:
        monthly = "FLAT"

    votes_long = sum(1 for d in (v1, v2, monthly) if d == "LONG")
    votes_short = sum(1 for d in (v1, v2, monthly) if d == "SHORT")
    if votes_long >= 2:
        ensemble = "LONG"
    elif votes_short >= 2:
        ensemble = "SHORT"
    else:
        ensemble = "FLAT"

    return {"v1": v1, "v2": v2, "monthly": monthly,
            "ensemble": ensemble, "m12": m12}


def collect_trades(df: pd.DataFrame) -> list[dict]:
    """One record per week with v1/v2/ensemble outcomes and regime tag."""
    weeks = far.week_indices(df)
    out = []
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index or mon not in df.index:
            continue
        sig_row = df.loc[signal_date]
        if pd.isna(sig_row.get("ATR")) or pd.isna(sig_row.get("M60")):
            continue
        dirs = variant_directions(sig_row)
        m12 = dirs["m12"]
        if m12 is None:
            continue
        regime = "M12_LONG" if m12 > 0 else "M12_SHORT"

        entry_row = df.loc[mon]
        entry_price = float(entry_row["open"])
        atr = float(sig_row["ATR"])
        if atr <= 0:
            continue

        rec = {
            "signal_date": signal_date,
            "week_start": mon,
            "week_end": fri,
            "regime": regime,
            "m12_pct": round(m12 * 100, 2),
        }
        for variant in ("v1", "v2", "ensemble"):
            direction = dirs[variant]
            if direction == "FLAT":
                rec[f"{variant}_net"] = None
                rec[f"{variant}_ret"] = None
                rec[f"{variant}_dir"] = "FLAT"
                continue
            if direction == "LONG":
                stop_price = entry_price - far.STOP_ATR_MULT * atr
            else:
                stop_price = entry_price + far.STOP_ATR_MULT * atr
            week_slice = df.loc[mon:fri]
            result = far.simulate_week(
                week_slice, mon, fri, direction, entry_price, stop_price)
            if result:
                rec[f"{variant}_net"] = result["net"]
                rec[f"{variant}_ret"] = result["net"] / (entry_price * far.CONTRACT_SIZE)
                rec[f"{variant}_dir"] = direction
            else:
                rec[f"{variant}_net"] = None
                rec[f"{variant}_ret"] = None
                rec[f"{variant}_dir"] = "FLAT"
        out.append(rec)
    return out


def summarize(trades: list[dict], variant: str, regime_filter: str | None = None) -> dict:
    """Cell stats for one variant, optionally filtered to a regime."""
    subset = [t for t in trades if regime_filter is None or t["regime"] == regime_filter]
    directional = [t for t in subset if t[f"{variant}_net"] is not None]
    n = len(directional)
    total_weeks = len(subset)
    if n == 0:
        return {"n": 0, "total_weeks": total_weeks, "fire_rate_pct": 0.0}
    pnls = [t[f"{variant}_net"] for t in directional]
    rets = [t[f"{variant}_ret"] for t in directional]
    wins = sum(1 for p in pnls if p > 0)
    total_pnl = sum(pnls)
    mean_r = sum(rets) / n
    if n > 1:
        std_r = (sum((r - mean_r) ** 2 for r in rets) / (n - 1)) ** 0.5
    else:
        std_r = 0.0
    sharpe = (mean_r / std_r) * math.sqrt(52) if std_r > 0 else 0.0
    return {
        "n": n,
        "total_weeks": total_weeks,
        "fire_rate_pct": round(100 * n / total_weeks, 1),
        "wr_pct": round(100 * wins / n, 1),
        "mean_ret_pct": round(100 * mean_r, 3),
        "sharpe": round(sharpe, 3),
        "cum_pnl_usd": round(total_pnl, 0),
    }


def render_table(header: str, rows: list[tuple[str, dict]]) -> str:
    lines = [header]
    lines.append(f"{'variant':<12} {'n':>4} {'wks':>4} {'fire%':>6} "
                 f"{'WR%':>6} {'mean%':>7} {'Sharpe':>7} {'cum$':>10}")
    lines.append("-" * 66)
    for label, s in rows:
        if s.get("n", 0) == 0:
            lines.append(f"{label:<12} {0:>4} {s.get('total_weeks',0):>4} "
                         f"{'0.0':>6} {'-':>6} {'-':>7} {'-':>7} {'-':>10}")
            continue
        lines.append(
            f"{label:<12} {s['n']:>4} {s['total_weeks']:>4} "
            f"{s['fire_rate_pct']:>6} {s['wr_pct']:>6} "
            f"{s['mean_ret_pct']:>+7.3f} {s['sharpe']:>+7.3f} "
            f"${s['cum_pnl_usd']:>9,.0f}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-doc", action="store_true")
    args = ap.parse_args()

    print("[load] fetching daily bars + macro (this takes a moment)")
    df = load_all()
    print(f"[load] {len(df)} daily bars, "
          f"range {df.index.min().date()} to {df.index.max().date()}")

    trades = collect_trades(df)
    print(f"[collect] {len(trades)} weekly decision points captured")

    regime_counts = defaultdict(int)
    for t in trades:
        regime_counts[t["regime"]] += 1
    print(f"[regime] M12_LONG weeks: {regime_counts['M12_LONG']}, "
          f"M12_SHORT weeks: {regime_counts['M12_SHORT']}")

    output = []

    for regime_label, regime_filter in [
            ("FULL SAMPLE", None),
            ("M12 LONG regime", "M12_LONG"),
            ("M12 SHORT regime", "M12_SHORT")]:
        rows = [(v, summarize(trades, v, regime_filter))
                for v in ("v1", "v2", "ensemble")]
        table = render_table(f"\n=== {regime_label} ===", rows)
        print(table)
        output.append(table)

    if args.write_doc:
        doc_path = ROOT / "docs" / "experiments" / \
            "2026-08-31_m12_regime_split_ensemble.md"
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write("# M12 regime-split ensemble analysis\n\n")
            f.write("**Date:** 2026-08-31\n")
            f.write("**Author:** Knox\n")
            f.write("**Status:** Analytical follow-up to the M12 regime audit.\n")
            f.write("**Data:** Dukascopy XAUUSD 5m + FRED DFII10 + DTWEXBGS, "
                    f"local snapshot through {df.index.max().date()}.\n\n")
            f.write("## Results\n\n```\n")
            f.write("\n\n".join(output))
            f.write("\n```\n\n")
            f.write("## Reading the table\n\n")
            f.write("- **fire%**: fraction of weeks in that regime where the "
                    "variant took a directional trade (rest were FLAT).\n")
            f.write("- **WR%**: win rate on the trades taken.\n")
            f.write("- **mean%**: mean per-trade return as a % of nominal.\n")
            f.write("- **Sharpe**: per-trade returns times sqrt(52). Same "
                    "methodology as the shipping v1 Sharpe 0.77 headline; "
                    "known to be technically loose but kept for comparability.\n")
            f.write("- **cum$**: cumulative dollar P&L per contract "
                    "(100 oz gold futures).\n\n")
            f.write("## Interpretation\n\n")
            f.write("The full-sample row reproduces the pre-reg ensemble "
                    "backtest number (Sharpe ~1.01, WR ~59%). If the M12 LONG "
                    "and M12 SHORT rows show very different behavior, the "
                    "ensemble's headline number is regime-conditional and "
                    "should be interpreted with that caveat. If both regimes "
                    "give roughly comparable stats, the vote is genuinely "
                    "adding value across regimes.\n")
        print(f"[wrote] {doc_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
