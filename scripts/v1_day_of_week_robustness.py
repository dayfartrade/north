"""Day-of-week robustness audit for v1's Monday-Friday entry/exit.

Known gap per NORTH v1 factsheet: "Robustness of Monday-Friday
entry/exit choice. All 25 day-combinations never tested. Would run
before hard launch."

Test all 25 combinations of entry_day x exit_day (Mon/Tue/Wed/Thu/Fri
x Mon/Tue/Wed/Thu/Fri) using the same v1 signal (frozen at prior-week
Friday close). For each combination, compute Sharpe/WR/mean/cum
across the 16-year sample.

Question: is v1's Mon-Fri choice a sweet spot, an average, or a
random pick that got lucky?

If Mon-Fri is:
  - Near the top of the 25: robust, but suspicious (were we searching?)
  - Near the middle: robust and honest
  - Near the bottom: fragile, and the shipped product got lucky

Per pre-reg, v1's Mon-Fri was NOT optimized - it was picked before
backtest because "one signal per week, Mon open to Fri close is the
natural cycle." So this audit is post-hoc but the choice was pre-hoc.

Exit day earlier than entry day = holds through the weekend into
next week's exit day. e.g., entry Wed, exit Tue = 4 trading-day
hold across weekend.

Usage: python scripts/v1_day_of_week_robustness.py
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

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def load_signals() -> pd.DataFrame:
    start = pd.Timestamp("2010-01-01", tz="UTC")
    end = pd.Timestamp("2026-08-31", tz="UTC")
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    return far.build_signals(daily, ry)


def simulate_combo(df: pd.DataFrame, entry_dow: int, exit_dow: int) -> dict:
    """Run backtest with custom entry/exit day of week.

    Signal frozen at prior-week Friday close (v1 convention).
    Entry: `entry_dow` of the following week (0=Mon..4=Fri).
    Exit: `exit_dow` of the following week if >= entry_dow, else of
      the week after (wraps around, holds over weekend).
    Same 2xATR stop.
    """
    df = df.copy()
    df["iso_year"] = df.index.isocalendar().year
    df["iso_week"] = df.index.isocalendar().week
    trades = []

    for (y, w), grp in df.groupby(["iso_year", "iso_week"]):
        if len(grp) < 2:
            continue
        # Signal date: prior week's Friday (last trading day BEFORE Monday)
        first_day = grp.index[0]
        prior = df.index[df.index < first_day]
        if len(prior) == 0:
            continue
        signal_date = prior[-1]
        sig = df.loc[signal_date]
        direction = str(sig["direction"])
        if direction == "FLAT":
            continue
        if pd.isna(sig.get("ATR")) or pd.isna(sig.get("M60")):
            continue

        entry_bars = grp.index[grp.index.weekday == entry_dow]
        if len(entry_bars) == 0:
            continue
        entry_ts = entry_bars[0]

        if exit_dow >= entry_dow:
            exit_bars = grp.index[grp.index.weekday == exit_dow]
        else:
            # Exit wraps to next week
            next_week_start = grp.index[-1] + pd.Timedelta(days=1)
            future = df.index[df.index >= next_week_start]
            exit_bars = future[future.weekday == exit_dow]
        if len(exit_bars) == 0:
            continue
        exit_ts = exit_bars[0]

        entry_price = float(df.loc[entry_ts, "open"])
        atr = float(sig["ATR"])
        if atr <= 0:
            continue
        if direction == "LONG":
            stop = entry_price - far.STOP_ATR_MULT * atr
        else:
            stop = entry_price + far.STOP_ATR_MULT * atr

        # Simulate: walk bars from entry_ts to exit_ts, check stop first
        window = df.loc[entry_ts:exit_ts]
        dir_sign = 1 if direction == "LONG" else -1
        exit_price = None
        for ts, row in window.iterrows():
            if ts == entry_ts:
                continue  # skip entry bar
            if direction == "LONG":
                if float(row["low"]) <= stop:
                    exit_price = stop; break
            else:
                if float(row["high"]) >= stop:
                    exit_price = stop; break
        if exit_price is None:
            exit_price = float(df.loc[exit_ts, "close"])

        gross = (exit_price - entry_price) * dir_sign * far.CONTRACT_SIZE
        net = gross - far.RT_COST
        trades.append({
            "entry_ts": entry_ts,
            "direction": direction,
            "entry": entry_price,
            "exit": exit_price,
            "net": net,
            "ret": net / (entry_price * far.CONTRACT_SIZE),
        })

    n = len(trades)
    if n == 0:
        return {"n": 0}
    rets = [t["ret"] for t in trades]
    pnls = [t["net"] for t in trades]
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


def main() -> None:
    print("[load]")
    df = load_signals()

    print("\nRunning 5x5 = 25 entry/exit combinations...\n")
    results = {}
    for e in range(5):
        for x in range(5):
            key = f"{WEEKDAY_NAMES[e]}-{WEEKDAY_NAMES[x]}"
            s = simulate_combo(df, e, x)
            results[key] = s
            print(f"  {key:<8} n={s.get('n',0):>3}  "
                  f"WR={s.get('wr',0):>5.1f}%  "
                  f"Sharpe={s.get('sharpe',0):>+7.3f}  "
                  f"cum=${s.get('cum',0):>9,.0f}")

    # Rank by Sharpe
    ranked = sorted(results.items(),
                     key=lambda kv: -kv[1].get("sharpe", -99))
    print("\n=== RANKED BY SHARPE ===")
    for i, (k, s) in enumerate(ranked):
        mark = " <-- shipped v1" if k == "Mon-Fri" else ""
        print(f"  #{i+1:>2}  {k:<8} Sharpe={s.get('sharpe',0):+.3f}  "
              f"cum=${s.get('cum',0):>9,.0f}{mark}")

    mon_fri = results.get("Mon-Fri", {})
    if mon_fri.get("n"):
        rank = 1 + next(i for i, (k, _) in enumerate(ranked) if k == "Mon-Fri")
        all_sharpes = [s.get("sharpe", 0) for s in results.values()]
        pct = np.mean([s >= mon_fri["sharpe"] for s in all_sharpes])
        median = np.median(all_sharpes)
        best = max(all_sharpes)
        worst = min(all_sharpes)
        pos_frac = np.mean([s > 0 for s in all_sharpes])
        print(f"\n=== Mon-Fri (shipped v1) assessment ===")
        print(f"  Rank: #{rank}/25 by Sharpe")
        print(f"  Mon-Fri Sharpe: {mon_fri['sharpe']:.3f}")
        print(f"  25-combo median: {median:.3f}")
        print(f"  25-combo best/worst: {best:.3f} / {worst:.3f}")
        print(f"  Fraction of combos with Sharpe > 0: {pos_frac:.0%}")
        print(f"  Fraction with Sharpe >= 0.50: {np.mean([s >= 0.5 for s in all_sharpes]):.0%}")


if __name__ == "__main__":
    main()
