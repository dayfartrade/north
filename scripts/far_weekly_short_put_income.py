"""FAR Weekly Gold Short-Put Income backtest.

Pre-reg: docs/experiments/2026-07-24_gold_short_put_income_prereg.md
Signal: sell 1-week Δ=-0.05 OTM put on gold weekly, priced via
Black-Scholes with GVZ (Gold IV Index) as implied vol.

Usage: python scripts/far_weekly_short_put_income.py [--delta 0.05]
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import importlib.util
spec = importlib.util.spec_from_file_location("far",
                                                str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

GVZ_CSV = ROOT / "data" / "macro" / "gvz_gold_iv__GVZCLS.csv"
CONTRACT_OZ = 100  # 1 GC futures contract nominal
RT_COST = 2.0  # options RT (commissions + slippage)
T_YEARS = 5.0 / 365.0  # 5-day expiration
RISK_FREE = 0.0  # short-dated, negligible


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_inv(p: float) -> float:
    """Beasley-Springer-Moro approximation of the inverse normal CDF."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    if p <= p_high:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)


def strike_for_put_delta(S: float, sigma: float, T: float, target_delta: float,
                          r: float = 0.0) -> float:
    """Find K such that European put delta = -target_delta.
    Put delta = -N(-d1). So N(-d1) = target_delta -> d1 = -Φ⁻¹(target_delta).
    """
    d1 = -norm_inv(target_delta)
    # d1 = (ln(S/K) + (r + σ²/2)T) / (σ√T)
    # ln(S/K) = d1*σ*√T - (r + σ²/2)*T
    # K = S * exp(-(d1*σ*√T - (r + σ²/2)*T))
    return S * math.exp(-(d1 * sigma * math.sqrt(T) - (r + 0.5 * sigma * sigma) * T))


def put_premium(S: float, K: float, sigma: float, T: float, r: float = 0.0) -> float:
    """Black-Scholes European put price."""
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def load_gvz() -> pd.Series:
    df = pd.read_csv(GVZ_CSV, parse_dates=["observation_date"])
    df = df.set_index("observation_date").sort_index()
    return pd.to_numeric(df["GVZCLS"], errors="coerce").dropna() / 100.0


def backtest(start: pd.Timestamp, end: pd.Timestamp, delta: float,
              label: str) -> dict:
    daily = far.load_daily_bars(start, end)
    gvz = load_gvz()
    idx_naive = daily.index.tz_localize(None) if daily.index.tz else daily.index
    gvz_daily = gvz.reindex(idx_naive, method="ffill")
    gvz_daily.index = daily.index
    daily["GVZ"] = gvz_daily

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
        K = strike_for_put_delta(S, sigma, T_YEARS, delta)
        premium = put_premium(S, K, sigma, T_YEARS)  # $/oz
        exit_price = float(daily.loc[fri]["close"])
        # Check for assignment (if put ITM at expiration)
        if exit_price < K:
            assignment_loss = K - exit_price  # $/oz
            payoff = premium - assignment_loss  # net $/oz
            outcome = "assigned"
        else:
            payoff = premium
            outcome = "kept"
        gross = payoff * CONTRACT_OZ
        net = gross - RT_COST
        trades.append({
            "week_start": mon, "S": S, "K": K, "iv": sigma,
            "premium_per_oz": premium, "exit_price": exit_price,
            "outcome": outcome, "gross": gross, "net": net,
        })
    return {"trades": trades, "total_weeks": len(weeks)}


def summarize(r: dict, label: str, S_median: float = 3000.0) -> dict:
    trades = r["trades"]
    n = len(trades)
    if n == 0:
        print(f"\n[{label}] 0 trades")
        return {}
    pnls = [t["net"] for t in trades]
    # Return per notional (K*100 oz is capital-at-risk if assigned)
    rets = [t["net"] / (t["K"] * CONTRACT_OZ) for t in trades]
    total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    assigned = sum(1 for t in trades if t["outcome"] == "assigned")
    mr = sum(rets) / n
    sr = (sum((r - mr) ** 2 for r in rets) / (n - 1)) ** 0.5 if n > 1 else 0
    sharpe = mr / sr * math.sqrt(52) if sr > 0 else 0

    from deflated_sharpe import sr_stats, probabilistic_sharpe
    s = sr_stats(rets); psr = probabilistic_sharpe(s, benchmark_sr=0.0)

    max_loss = min(pnls)
    median_income = sorted([p for p in pnls if p > 0])[len([p for p in pnls if p > 0]) // 2] \
                    if any(p > 0 for p in pnls) else 0
    annualized_median_income = median_income * 52

    by_year = defaultdict(list)
    for t in trades:
        by_year[str(t["week_start"])[:4]].append(t)
    year_sharpes = {}
    for y in sorted(by_year):
        yr = by_year[y]
        yrets = [t["net"] / (t["K"] * CONTRACT_OZ) for t in yr]
        if len(yrets) > 1:
            ymr = sum(yrets)/len(yrets)
            ysr = (sum((r-ymr)**2 for r in yrets)/(len(yrets)-1))**0.5
            year_sharpes[y] = ymr/ysr*math.sqrt(52) if ysr > 0 else 0
        else:
            year_sharpes[y] = 0

    print(f"\n=== Gold Short-Put Income [{label}] ===")
    print(f"  Weeks: {r['total_weeks']}  Trades: {n}  Assigned: {assigned} ({100*assigned/n:.1f}%)")
    print(f"  Win rate: {100*wins/n:.1f}%  Total P&L: ${total:+,.0f}")
    print(f"  Mean/week: ${mean:+,.1f}  Median income: ${median_income:.1f}")
    print(f"  Sharpe(ann): {sharpe:.3f}  Skew: {s.skewness:+.3f}  PSR: {psr:.4f}")
    print(f"  Max single-week loss: ${max_loss:+,.0f}")
    print(f"  Ratio max-loss / ann-median-income: {abs(max_loss)/max(annualized_median_income,1):.2f}x")
    print(f"  Positive years: {sum(1 for v in year_sharpes.values() if v > 0)}/{len(year_sharpes)}")
    print(f"  Year-by-year:")
    for y in sorted(by_year):
        yr = by_year[y]
        pl = [t["net"] for t in yr]
        w = sum(1 for p in pl if p > 0)
        a = sum(1 for t in yr if t["outcome"] == "assigned")
        print(f"    {y}: n={len(pl):>3d}  assigned={a:>2d}  "
              f"WR={100*w/len(pl):>4.1f}%  total=${sum(pl):>+8,.0f}  "
              f"Sharpe={year_sharpes[y]:>+5.2f}")
    return {"sharpe": sharpe, "wr": 100*wins/n, "total": total, "psr": psr,
            "n": n, "assigned_rate": assigned/n, "max_loss": max_loss,
            "positive_years": sum(1 for v in year_sharpes.values() if v > 0),
            "n_years": len(year_sharpes),
            "skew": s.skewness,
            "annualized_median_income": annualized_median_income}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta", type=float, default=0.05)
    args = ap.parse_args()

    print(f"Running backtest with target put delta = -{args.delta}")

    train_start = pd.Timestamp("2010-01-01", tz="UTC")
    train_end = pd.Timestamp("2018-12-31", tz="UTC")
    oos_start = pd.Timestamp("2019-01-01", tz="UTC")
    oos_end = pd.Timestamp("2026-06-30", tz="UTC")

    train_r = backtest(train_start, train_end, args.delta, "TRAINING 2010-2018")
    train_s = summarize(train_r, "TRAINING 2010-2018")

    oos_r = backtest(oos_start, oos_end, args.delta, "OOS 2019-2026")
    oos_s = summarize(oos_r, "OOS 2019-2026")

    if not oos_s:
        return

    # Ship gates (from pre-reg)
    gates = [
        ("1. OOS Sharpe >= 0.60", oos_s["sharpe"] >= 0.60, f"{oos_s['sharpe']:.3f}"),
        ("2. OOS WR >= 75%", oos_s["wr"] >= 75.0, f"{oos_s['wr']:.1f}%"),
        ("3. OOS total > 0", oos_s["total"] > 0, f"${oos_s['total']:+,.0f}"),
        ("4. max-loss / ann-median-income <= 3x",
         abs(oos_s["max_loss"]) / max(oos_s["annualized_median_income"], 1) <= 3.0,
         f"{abs(oos_s['max_loss'])/max(oos_s['annualized_median_income'],1):.2f}x"),
        ("5. OOS n >= 100", oos_s["n"] >= 100, f"{oos_s['n']}"),
        ("6. Skewness > -3.0", oos_s["skew"] > -3.0, f"{oos_s['skew']:.2f}"),
        ("7. Positive-Sharpe years >= 5", oos_s["positive_years"] >= 5,
         f"{oos_s['positive_years']}/{oos_s['n_years']}"),
    ]
    kill = []
    if oos_s["sharpe"] < 0:
        kill.append("negative OOS Sharpe")
    if oos_s["assigned_rate"] > 0.30:
        kill.append(f"assignment rate {100*oos_s['assigned_rate']:.1f}% > 30%")
    if oos_s["annualized_median_income"] > 0:
        ratio = abs(oos_s["max_loss"]) / oos_s["annualized_median_income"]
        if ratio > 10:
            kill.append(f"single-week blowup {ratio:.1f}x annual income")

    print("\n=== SHIP GATES ===")
    passing = sum(1 for _, p, _ in gates if p)
    for label, passed, val in gates:
        print(f"  {'[PASS]' if passed else '[FAIL]'} {label}  actual={val}")
    print(f"\n  {passing}/7 gates pass")
    if kill:
        print(f"  KILL SWITCHES TRIGGERED: {', '.join(kill)}")


if __name__ == "__main__":
    main()
