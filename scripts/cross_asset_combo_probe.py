"""Cross-asset combo probe: gold v1 + palladium LONG-only.

Follow-up mentioned in docs/experiments/2026-08-17_universe_probe.md.
Neither gold v1 nor palladium LONG cleared the ship gates as standalone.
The question this probe answers:

  Do they trigger on DIFFERENT weeks? If yes, combining them into a
  portfolio gives more weeks with a signal AND lower per-trade
  variance (uncorrelated diversification).

The test:
  For each week 2010-2026, compute both:
    - gold v1 direction (LONG / SHORT / FLAT)
    - palladium v1 LONG signal (LONG or NOT)
  Report:
    - overlap: weeks where both fire directional
    - complement: weeks where only one fires
    - portfolio metrics: 50/50 blend of the two returns
  Compare to gold v1 alone.

This is a DATA PROBE, not a ship gate. Does not violate the pre-reg
discipline because neither leg is being changed post-hoc; we are
simply asking whether combining two known signals adds diversification.
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))

spec = importlib.util.spec_from_file_location(
    "far", str(ROOT / "scripts" / "far_weekly_gold_read.py")
)
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

spec2 = importlib.util.spec_from_file_location(
    "universe", str(ROOT / "scripts" / "universe_v1_probe.py")
)
u = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(u)


def run_gold(start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    sig = far.build_signals(daily, ry)
    sig = sig[(sig.index >= start) & (sig.index <= end)]
    weeks = far.week_indices(sig)
    trades = []
    for signal_date, mon, fri in weeks:
        if signal_date not in sig.index:
            continue
        row = sig.loc[signal_date]
        direction = row["direction"]
        if pd.isna(row["ATR"]) or pd.isna(row["M60"]):
            continue
        rec = {"week_start": mon, "signal_date": signal_date, "direction": direction, "return_pct": 0.0}
        if direction == "FLAT" or mon not in sig.index:
            trades.append(rec); continue
        atr = float(row["ATR"])
        if atr <= 0:
            trades.append(rec); continue
        entry = float(sig.loc[mon, "open"])
        stop = entry - far.STOP_ATR_MULT * atr if direction == "LONG" else entry + far.STOP_ATR_MULT * atr
        week = sig.loc[mon:fri]
        exit_price = None
        for _, r in week.iterrows():
            if direction == "LONG" and float(r["low"]) <= stop:
                exit_price = stop; break
            if direction == "SHORT" and float(r["high"]) >= stop:
                exit_price = stop; break
        if exit_price is None:
            exit_price = float(week.iloc[-1]["close"])
        dir_sign = 1 if direction == "LONG" else -1
        rec["return_pct"] = (exit_price - entry) * dir_sign / entry
        trades.append(rec)
    return trades


def run_palladium_long(start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    r = u.backtest("palladium", start, end)
    trades = []
    for t in r["trades"]:
        if t["direction"] != "LONG":
            continue
        trades.append({
            "week_start": t["week_start"],
            "signal_date": t["signal_date"],
            "direction": "LONG",
            "return_pct": t["return_pct"],
        })
    return trades


def key_of(mon: pd.Timestamp) -> str:
    return str(mon.date())


def summarize(returns: list[float], label: str) -> None:
    n = len(returns)
    if n == 0:
        print(f"  {label}: no trades"); return
    wins = sum(1 for r in returns if r > 0)
    mean = sum(returns) / n
    if n > 1:
        std = (sum((r - mean) ** 2 for r in returns) / (n - 1)) ** 0.5
    else:
        std = 0.0
    sharpe = (mean / std) * math.sqrt(52) if std > 0 else 0.0
    total = sum(returns)
    equity = []; running = 0.0
    for r in returns:
        running += r; equity.append(running)
    peak = 0.0; max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak - v > max_dd:
            max_dd = peak - v
    print(f"  {label}:  n={n}  WR={100*wins/n:.1f}%")
    print(f"    mean R:       {100*mean:+.3f}%")
    print(f"    Sharpe (ann): {sharpe:+.3f}")
    print(f"    cum R:        {100*total:+.2f}%")
    print(f"    max DD:       {100*max_dd:.2f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-08-14")
    args = ap.parse_args()
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    print(f"CROSS-ASSET COMBO PROBE: gold v1 + palladium LONG-only")
    print(f"Window: {args.start} to {args.end}\n")

    print("Running gold v1...")
    gold = run_gold(start, end)
    print("Running palladium LONG-only...")
    pd_long = run_palladium_long(start, end)

    # Index by week_start
    gold_by_week = {key_of(t["week_start"]): t for t in gold}
    pd_by_week = {key_of(t["week_start"]): t for t in pd_long}

    all_weeks = sorted(set(gold_by_week) | set(pd_by_week))

    both_fire = 0
    only_gold = 0
    only_pd = 0
    neither = 0
    gold_dir_pd_dir_matrix = defaultdict(int)

    for w in all_weeks:
        g = gold_by_week.get(w)
        p = pd_by_week.get(w)
        g_fires = g and g["direction"] in ("LONG", "SHORT")
        p_fires = p and p["direction"] == "LONG"
        if g_fires and p_fires:
            both_fire += 1
        elif g_fires:
            only_gold += 1
        elif p_fires:
            only_pd += 1
        else:
            neither += 1
        if g:
            gold_dir_pd_dir_matrix[(g["direction"], "PD-LONG" if p_fires else "PD-FLAT")] += 1

    total_weeks = len(all_weeks)
    print(f"\nWeek overlap analysis (n={total_weeks}):")
    print(f"  Both fire:  {both_fire} ({100*both_fire/total_weeks:.1f}%)")
    print(f"  Only gold:  {only_gold} ({100*only_gold/total_weeks:.1f}%)")
    print(f"  Only pd:    {only_pd} ({100*only_pd/total_weeks:.1f}%)")
    print(f"  Neither:    {neither} ({100*neither/total_weeks:.1f}%)")

    print(f"\nGold direction x Palladium status:")
    for (gd, ps), count in sorted(gold_dir_pd_dir_matrix.items()):
        print(f"  gold={gd:>5s}  {ps}: {count}")

    print(f"\n{'='*60}")
    print(" Standalone leg performance (directional weeks only)")
    print("=" * 60)
    gold_dir_returns = [t["return_pct"] for t in gold if t["direction"] in ("LONG", "SHORT")]
    pd_returns = [t["return_pct"] for t in pd_long]
    summarize(gold_dir_returns, "gold v1 (LONG+SHORT)")
    print()
    summarize(pd_returns, "palladium LONG-only")

    print(f"\n{'='*60}")
    print(" Portfolio blend: 50/50 by dollar risk when both fire, full weight when one fires")
    print("=" * 60)
    combo_returns = []
    for w in all_weeks:
        g = gold_by_week.get(w)
        p = pd_by_week.get(w)
        g_fires = g and g["direction"] in ("LONG", "SHORT")
        p_fires = p and p["direction"] == "LONG"
        if g_fires and p_fires:
            r = 0.5 * g["return_pct"] + 0.5 * p["return_pct"]
        elif g_fires:
            r = g["return_pct"]
        elif p_fires:
            r = p["return_pct"]
        else:
            continue
        combo_returns.append(r)
    summarize(combo_returns, "50/50 blend (either fires)")

    print(f"\n{'='*60}")
    print(" Correlation of same-week returns (both-fire weeks only)")
    print("=" * 60)
    same_week = []
    for w in all_weeks:
        g = gold_by_week.get(w); p = pd_by_week.get(w)
        if g and p and g["direction"] in ("LONG", "SHORT") and p["direction"] == "LONG":
            same_week.append((g["return_pct"], p["return_pct"]))
    n = len(same_week)
    if n >= 3:
        mg = sum(x for x, _ in same_week) / n
        mp = sum(y for _, y in same_week) / n
        num = sum((x - mg) * (y - mp) for x, y in same_week)
        dg = (sum((x - mg) ** 2 for x, _ in same_week)) ** 0.5
        dp = (sum((y - mp) ** 2 for _, y in same_week)) ** 0.5
        corr = num / (dg * dp) if (dg > 0 and dp > 0) else float("nan")
        print(f"  n(both-fire weeks): {n}")
        print(f"  correlation:        {corr:+.3f}")
        print(f"  interpretation: {'high correlation (little diversification benefit)' if abs(corr) > 0.5 else 'low correlation (some diversification benefit)' if abs(corr) < 0.3 else 'moderate correlation'}")
    else:
        print(f"  n(both-fire weeks) = {n}, not enough to compute correlation")


if __name__ == "__main__":
    main()
