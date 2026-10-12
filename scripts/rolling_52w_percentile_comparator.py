"""Rolling 52-week percentile comparator.

Queue item #3 from 2026-09-08 agenda: live signals compared to trailing
52-week backtest distribution instead of full 16-year. More informative
given the ATR regime shift (price doubled, volatility compressed).

For each weekly signal in a reporting window (default: most recent 26
weeks), compute percentile of key components (M20, M60, ATR, DXY_chg,
RY_chg) against:
  (a) the full 2010-01-01 .. signal_date historical distribution
  (b) the trailing 252-trading-day (~52-week) rolling distribution
      ending at the signal date

Report the pair side-by-side. Large gaps between (a) and (b) are the
regime-shift signal.

Also report: how many live signals in 2026 had their 2026 trailing-52w
M20 in the top 20% of that same window? (The "extreme-M20-LONG" problem
restated against the local-regime distribution.)

Usage:
  python scripts/rolling_52w_percentile_comparator.py
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
WINDOW_DAYS = 252  # ~52 trading weeks


def load_signals(end: pd.Timestamp) -> pd.DataFrame:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    df = far.build_signals(daily, ry)
    dxy = far.load_macro_series(DXY_PATH, "dxy")
    dxy_daily = dxy.reindex(
        df.index.tz_localize(None) if df.index.tz else df.index, method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(far.RY_LAG)
    return df


def percentile(series: pd.Series, value: float) -> float:
    """Percentile rank of value within series (0..100)."""
    arr = series.dropna().to_numpy()
    if len(arr) == 0 or pd.isna(value):
        return float("nan")
    return float((arr < value).mean() * 100)


def comparator_row(
    df: pd.DataFrame, signal_date: pd.Timestamp, components: list[str],
) -> dict:
    sig = df.loc[signal_date]
    row = {
        "signal_date": signal_date.strftime("%Y-%m-%d"),
        "direction": str(sig["direction"]),
    }
    # Full historical window (start .. signal_date, exclusive)
    full = df[df.index < signal_date]
    # Trailing 52w (last 252 trading days ending at signal_date, exclusive)
    trailing = full.iloc[-WINDOW_DAYS:] if len(full) >= WINDOW_DAYS else full
    for col in components:
        v = float(sig[col]) if pd.notna(sig[col]) else np.nan
        row[f"{col}_val"] = v
        row[f"{col}_pct_full"] = percentile(full[col], v)
        row[f"{col}_pct_52w"] = percentile(trailing[col], v)
    return row


def print_table(rows: list[dict], components: list[str]) -> None:
    for r in rows:
        print(f"\n--- {r['signal_date']}  ({r['direction']}) ---")
        print(f"  {'component':<10} {'value':>10} {'full%':>8} {'52w%':>8} {'delta_52w_full':>16}")
        for col in components:
            v = r[f"{col}_val"]
            pf = r[f"{col}_pct_full"]
            pw = r[f"{col}_pct_52w"]
            delta = pw - pf if not (np.isnan(pf) or np.isnan(pw)) else float("nan")
            unit = "%" if col in ("M20", "M60", "ATR") else ""
            vstr = f"{v*100:+.2f}%" if col in ("M20", "M60") else f"{v:+.2f}{unit}"
            print(f"  {col:<10} {vstr:>10} {pf:>7.1f}% {pw:>7.1f}% "
                  f"{delta:>+15.1f} pts")


def summary_table(rows: list[dict], components: list[str]) -> None:
    print("\n=== Summary - recent signals ===")
    cols = ["signal_date", "direction"]
    for col in components:
        cols += [f"{col}_val", f"{col}_pct_full", f"{col}_pct_52w"]
    df = pd.DataFrame(rows)[cols].copy()
    # Format
    for col in components:
        if col in ("M20", "M60"):
            df[f"{col}_val"] = (df[f"{col}_val"] * 100).map(lambda x: f"{x:+.2f}%" if pd.notna(x) else "")
        else:
            df[f"{col}_val"] = df[f"{col}_val"].map(lambda x: f"{x:+.2f}" if pd.notna(x) else "")
        df[f"{col}_pct_full"] = df[f"{col}_pct_full"].map(lambda x: f"{x:.0f}%" if pd.notna(x) else "")
        df[f"{col}_pct_52w"] = df[f"{col}_pct_52w"].map(lambda x: f"{x:.0f}%" if pd.notna(x) else "")
    print(df.to_string(index=False))


def live_signal_analysis(df: pd.DataFrame) -> None:
    """How many 2026 live signals had their M20 in the 52w top-20% of that
    moment? Compare to full-history top-20% test."""
    print("\n=== 2026 live signals - M20 extremity (52w vs full) ===")
    weeks = far.week_indices(df)
    sig_2026 = [sd for (sd, _, _) in weeks
                if sd.year == 2026 and sd in df.index
                and str(df.loc[sd]["direction"]) != "FLAT"]
    full_top20_count = 0
    trailing_top20_count = 0
    rows = []
    for sd in sig_2026:
        sig = df.loc[sd]
        m20 = float(sig["M20"])
        if pd.isna(m20):
            continue
        full = df[df.index < sd]
        trailing = full.iloc[-WINDOW_DAYS:] if len(full) >= WINDOW_DAYS else full
        full_pct = percentile(full["M20"], m20)
        trail_pct = percentile(trailing["M20"], m20)
        is_full_top20 = full_pct >= 80
        is_trail_top20 = trail_pct >= 80
        full_top20_count += int(is_full_top20)
        trailing_top20_count += int(is_trail_top20)
        rows.append({
            "date": sd.strftime("%Y-%m-%d"),
            "dir": str(sig["direction"]),
            "M20": f"{m20*100:+.2f}%",
            "full_pct": f"{full_pct:.0f}%",
            "trail_pct": f"{trail_pct:.0f}%",
            "full_top20": "YES" if is_full_top20 else "",
            "trail_top20": "YES" if is_trail_top20 else "",
        })
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"\n  2026 directional signals: {len(rows)}")
    print(f"  M20 in full-history top 20%: {full_top20_count}/{len(rows)}")
    print(f"  M20 in trailing-52w top 20%: {trailing_top20_count}/{len(rows)}")


def main() -> None:
    end = pd.Timestamp("2026-10-12", tz="UTC")
    df = load_signals(end)
    print(f"Signals rows (daily): {len(df)}")
    print(f"Latest signal date in data: {df.index[-1]}")

    components = ["M20", "M60", "ATR", "DXY_chg", "RY_chg"]
    # Last 26 weekly signal dates in-sample
    weeks = far.week_indices(df)
    recent_sigs = [sd for (sd, _, _) in weeks if sd in df.index][-26:]
    rows = [comparator_row(df, sd, components) for sd in recent_sigs]

    summary_table(rows, components)

    # Print the detail only for the most recent 6 signals
    print("\n=== Detail - most recent 6 signals ===")
    for r in rows[-6:]:
        print(f"\n--- {r['signal_date']}  ({r['direction']}) ---")
        print(f"  {'component':<10} {'value':>10} {'full%':>8} {'52w%':>8} {'delta_52w_full':>16}")
        for col in components:
            v = r[f"{col}_val"]
            pf = r[f"{col}_pct_full"]
            pw = r[f"{col}_pct_52w"]
            delta = pw - pf if not (np.isnan(pf) or np.isnan(pw)) else float("nan")
            if col in ("M20", "M60"):
                vstr = f"{v*100:+.2f}%"
            else:
                vstr = f"{v:+.2f}"
            print(f"  {col:<10} {vstr:>10} {pf:>7.1f}% {pw:>7.1f}% {delta:>+13.1f}")

    live_signal_analysis(df)

    # Save detailed CSV for reporting pipeline
    out = ROOT / "data" / "experiments" / "rolling_52w_percentile_recent.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nCSV: {out}")


if __name__ == "__main__":
    main()
