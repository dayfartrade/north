"""FAR Weekly Gold Put-Spread Income backtest (defined-risk variant of C1).

Pre-reg: docs/experiments/2026-07-24_gold_put_spread_income_prereg.md
Signal: SHORT 5-delta put + LONG 2-delta put weekly (bull put spread).
Pricing: Black-Scholes with GVZ as IV.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("shortput",
                                                str(ROOT / "scripts" / "far_weekly_short_put_income.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

spec2 = importlib.util.spec_from_file_location("far",
                                                 str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(far)

CONTRACT_OZ = 100
RT_COST = 4.0  # 2 legs
T_YEARS = 5.0 / 365.0
SHORT_DELTA = 0.05
LONG_DELTA = 0.02


def backtest(start: pd.Timestamp, end: pd.Timestamp, label: str) -> dict:
    daily = far.load_daily_bars(start, end)
    gvz = sp.load_gvz()
    idx_naive = daily.index.tz_localize(None) if daily.index.tz else daily.index
    daily["GVZ"] = gvz.reindex(idx_naive, method="ffill").values

    dfw = daily[(daily.index >= start) & (daily.index <= end)]
    weeks = far.week_indices(dfw)
    trades = []
    for signal_date, mon, fri in weeks:
        if mon not in daily.index or fri not in daily.index:
            continue
        S = float(daily.loc[mon]["open"])
        iv = daily.loc[mon].get("GVZ")
        if pd.isna(iv) or iv <= 0 or S <= 0:
            continue
        sigma = float(iv)
        K_short = sp.strike_for_put_delta(S, sigma, T_YEARS, SHORT_DELTA)
        K_long = sp.strike_for_put_delta(S, sigma, T_YEARS, LONG_DELTA)
        prem_short = sp.put_premium(S, K_short, sigma, T_YEARS)
        prem_long = sp.put_premium(S, K_long, sigma, T_YEARS)
        net_premium = prem_short - prem_long  # $/oz credit

        exit_price = float(daily.loc[fri]["close"])
        # Payoff
        if exit_price >= K_short:
            payoff_short = 0.0
            payoff_long = 0.0
        elif exit_price >= K_long:
            payoff_short = -(K_short - exit_price)
            payoff_long = 0.0
        else:
            payoff_short = -(K_short - exit_price)
            payoff_long = (K_long - exit_price)
        net_payoff = net_premium + payoff_short + payoff_long  # $/oz total
        gross = net_payoff * CONTRACT_OZ
        net = gross - RT_COST

        trades.append({
            "week_start": mon, "S": S, "K_short": K_short, "K_long": K_long,
            "iv": sigma, "net_premium_per_oz": net_premium,
            "exit_price": exit_price, "gross": gross, "net": net,
            "max_loss_per_oz": (K_short - K_long) - net_premium,
        })
    return {"trades": trades, "total_weeks": len(weeks)}


def summarize(r: dict, label: str) -> dict:
    trades = r["trades"]
    n = len(trades)
    if n == 0:
        print(f"[{label}] 0 trades")
        return {}
    pnls = [t["net"] for t in trades]
    rets = [t["net"] / (t["K_short"] * CONTRACT_OZ) for t in trades]
    total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    max_loss = min(pnls)
    from deflated_sharpe import sr_stats, probabilistic_sharpe
    s = sr_stats(rets); psr = probabilistic_sharpe(s, benchmark_sr=0.0)
    mr = sum(rets)/n
    sr = (sum((r-mr)**2 for r in rets)/(n-1))**0.5 if n>1 else 0
    sharpe = mr/sr*math.sqrt(52) if sr>0 else 0

    median_income = sorted([p for p in pnls if p > 0])[len([p for p in pnls if p > 0]) // 2] \
                    if any(p > 0 for p in pnls) else 0
    ann_median_income = median_income * 52

    by_year = defaultdict(list)
    for t in trades: by_year[str(t["week_start"])[:4]].append(t)
    year_sharpes = {}
    for y, yr in by_year.items():
        yrets = [t["net"] / (t["K_short"] * CONTRACT_OZ) for t in yr]
        if len(yrets) > 1:
            ymr = sum(yrets)/len(yrets)
            ysr = (sum((r-ymr)**2 for r in yrets)/(len(yrets)-1))**0.5
            year_sharpes[y] = ymr/ysr*math.sqrt(52) if ysr>0 else 0
        else:
            year_sharpes[y] = 0
    pos_years = sum(1 for v in year_sharpes.values() if v > 0)

    print(f"\n=== Put-Spread Income [{label}] ===")
    print(f"  n={n}  WR={100*wins/n:.1f}%  Total ${total:+,.0f}  Mean ${mean:+,.1f}")
    print(f"  Median income: ${median_income:.1f}  Annualized: ${ann_median_income:,.0f}")
    print(f"  Sharpe(ann): {sharpe:.3f}  Skew: {s.skewness:+.3f}  PSR: {psr:.4f}")
    print(f"  Max weekly loss: ${max_loss:+,.0f}   Ratio max-loss / ann-median-income: "
          f"{abs(max_loss)/max(ann_median_income,1):.2f}x")
    print(f"  Positive-Sharpe years: {pos_years}/{len(year_sharpes)}")
    print("  Year-by-year:")
    for y in sorted(by_year):
        yr = by_year[y]; pl = [t["net"] for t in yr]; w = sum(1 for p in pl if p > 0)
        print(f"    {y}: n={len(pl):>3d} WR={100*w/len(pl):>4.1f}% total=${sum(pl):>+8,.0f}  "
              f"Sharpe={year_sharpes[y]:>+5.2f}")

    return {"sharpe": sharpe, "wr": 100*wins/n, "total": total, "psr": psr,
            "n": n, "max_loss": max_loss, "skew": s.skewness,
            "ann_median_income": ann_median_income,
            "positive_years": pos_years, "n_years": len(year_sharpes)}


def main():
    train_r = backtest(pd.Timestamp("2010-01-01", tz="UTC"),
                        pd.Timestamp("2018-12-31", tz="UTC"), "TRAINING 2010-2018")
    summarize(train_r, "TRAINING 2010-2018")
    oos_r = backtest(pd.Timestamp("2019-01-01", tz="UTC"),
                      pd.Timestamp("2026-06-30", tz="UTC"), "OOS 2019-2026")
    oos_s = summarize(oos_r, "OOS 2019-2026")

    if not oos_s:
        return
    gates = [
        ("1. OOS Sharpe >= 0.60", oos_s["sharpe"] >= 0.60, f"{oos_s['sharpe']:.3f}"),
        ("2. OOS WR >= 75%", oos_s["wr"] >= 75.0, f"{oos_s['wr']:.1f}%"),
        ("3. OOS total > 0", oos_s["total"] > 0, f"${oos_s['total']:+,.0f}"),
        ("4. max-loss / ann-med-income <= 3x",
         abs(oos_s["max_loss"]) / max(oos_s["ann_median_income"], 1) <= 3.0,
         f"{abs(oos_s['max_loss'])/max(oos_s['ann_median_income'],1):.2f}x"),
        ("5. OOS n >= 100", oos_s["n"] >= 100, f"{oos_s['n']}"),
        ("6. Skewness > -3.0", oos_s["skew"] > -3.0, f"{oos_s['skew']:.2f}"),
        ("7. Positive years >= 5", oos_s["positive_years"] >= 5,
         f"{oos_s['positive_years']}/{oos_s['n_years']}"),
    ]
    passing = sum(1 for _, p, _ in gates if p)
    print("\n=== SHIP GATES ===")
    for l, p, v in gates:
        print(f"  {'[PASS]' if p else '[FAIL]'} {l}  actual={v}")
    print(f"\n  {passing}/7 gates pass")
    kill = []
    if oos_s["sharpe"] < 0: kill.append("negative Sharpe")
    if oos_s["skew"] < -4: kill.append(f"skew {oos_s['skew']:.2f} < -4")
    if abs(oos_s["max_loss"]) / max(oos_s["ann_median_income"], 1) > 8:
        kill.append("max loss > 8x ann income")
    if kill:
        print(f"  KILL SWITCHES: {', '.join(kill)}")


if __name__ == "__main__":
    main()
