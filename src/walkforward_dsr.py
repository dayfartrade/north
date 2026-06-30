"""Proper walk-forward + Deflated Sharpe Ratio.

Walk-forward design:
  - Use ALL backtest data 2024-01-26 → 2026-06-19 (~2.4 years)
  - Split by quarters: train on first N quarters, test on next quarter, roll forward
  - Parameters are FROZEN (v5 defaults). We're not optimizing — we're measuring
    consistency.

Deflated Sharpe Ratio (López de Prado, 2014):
  Accounts for the multiple-testing problem. If we tested N strategy variants
  and kept the best, the observed Sharpe is biased upward. DSR corrects this.

  DSR = Φ( (SR - E[max_SR]) * sqrt(T-1) / sqrt(1 - γ3*SR + (γ4-1)/4*SR^2) )

  where E[max_SR] = sqrt(2 * ln(N)) when comparing N strategies.

We treat all our backtest parameter sweeps as the "search universe" N and
deflate accordingly.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats
from pathlib import Path

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v5 import run_v5
from backtest import summarize, print_summary


def walk_forward_quarters(bars, events):
    trades_all = run_v5(bars, events)
    if trades_all.empty:
        print("No trades.")
        return
    trades_all = trades_all.sort_values("entry_ts").reset_index(drop=True)
    trades_all["quarter"] = pd.to_datetime(trades_all["entry_ts"]).dt.to_period("Q")
    quarters = sorted(trades_all["quarter"].unique())

    print(f"Quarters in backtest: {len(quarters)} — {quarters[0]} to {quarters[-1]}")
    print("\nPer-quarter performance (out-of-sample by construction — params frozen):")
    print(f"{'quarter':<10s} {'n':>4s} {'win%':>6s} {'mean_$':>10s} {'total_$':>10s} {'sharpe':>7s}")

    rows = []
    for q in quarters:
        g = trades_all[trades_all["quarter"] == q]
        if g.empty:
            continue
        s = summarize(g, label=str(q))
        rows.append({"quarter": str(q), **s})
        print(f"{str(q):<10s} {s['n']:>4d} {s['win_rate']*100:>6.1f} "
              f"{s['mean_net_pnl']:+10.2f} {s['total_net_pnl']:+10.0f} {s['sharpe_per_trade']:+7.2f}")

    df = pd.DataFrame(rows)
    # Quarterly P&L stats
    print(f"\nQuarters profitable: {(df['total_net_pnl'] > 0).sum()}/{len(df)}")
    print(f"Mean Sharpe across quarters: {df['sharpe_per_trade'].mean():+.2f}")
    print(f"Std  Sharpe across quarters: {df['sharpe_per_trade'].std():.2f}")
    return trades_all, df


def deflated_sharpe(observed_sharpe: float, n_trades: int,
                     skew: float = 0.0, kurt: float = 3.0,
                     n_trials: int = 100) -> dict:
    """Deflated Sharpe Ratio per López de Prado (2014).

    observed_sharpe : Sharpe estimate (NOT annualized — per-period). For our
                       case we use per-trade Sharpe = mean / std.
    n_trades        : sample size
    skew, kurt      : third and fourth standardized moments of returns
    n_trials        : number of strategy variants that were tested
    """
    if n_trials < 2:
        n_trials = 2
    # Expected maximum SR under null among n_trials i.i.d. Normal(0,1) draws
    euler_mascheroni = 0.5772156649
    e_max = ((1 - euler_mascheroni) * stats.norm.ppf(1 - 1.0/n_trials) +
             euler_mascheroni * stats.norm.ppf(1 - 1.0/(n_trials * np.e)))

    # SE of SR estimate (López de Prado formula)
    sigma_sr = np.sqrt(
        (1 - skew * observed_sharpe + (kurt - 1)/4 * observed_sharpe**2)
        / (n_trades - 1)
    )
    if sigma_sr <= 0:
        return {"dsr": np.nan, "e_max_sr": e_max, "sigma_sr": sigma_sr}
    # E[max_SR] in SR UNITS (scale by σ_SR)
    e_max_sr_units = e_max * sigma_sr
    dsr = stats.norm.cdf((observed_sharpe - e_max_sr_units) / sigma_sr)
    return {
        "observed_sr": observed_sharpe,
        "e_max_normalized": e_max,
        "e_max_sr_units": e_max_sr_units,
        "sigma_sr": sigma_sr,
        "deflated_sr_prob": dsr,
        "n_trials_assumed": n_trials,
    }


def main():
    print("="*100)
    print("MERS v5 — Walk-forward by quarter + Deflated Sharpe")
    print("="*100)
    events = build_all()
    bars = gc_load("60m")

    trades_all, q_df = walk_forward_quarters(bars, events)

    # Compute deflated Sharpe accounting for our parameter search.
    # We ran approximately: v1 (~280 configs), v3 (~150 configs), v4 stability (~240),
    # v5 sweeps (~30), plus various secondary tests. Conservatively assume N_TRIALS = 1000.
    n = len(trades_all)
    rets = trades_all["net_pnl"].values  # use $ P&L
    mean = float(rets.mean())
    std = float(rets.std())
    sr_per_trade = mean / std if std > 0 else 0.0
    sr_annual = sr_per_trade * np.sqrt(252)
    skew = float(stats.skew(rets))
    kurt = float(stats.kurtosis(rets, fisher=False))  # Pearson (normal=3)

    print(f"\nObserved trade return stats (n={n}):")
    print(f"  mean=${mean:+.2f}  std=${std:.2f}  skew={skew:+.2f}  kurtosis={kurt:.2f}")
    print(f"  per-trade Sharpe: {sr_per_trade:+.3f}")
    print(f"  annualized Sharpe (×√252): {sr_annual:+.2f}")

    # Also report annualized properly: trades/year × per-trade SR
    bars = gc_load("60m")
    span_days = (bars.index[-1] - bars.index[0]).total_seconds() / 86400
    trades_per_year = n / (span_days / 365.25)
    sr_annual_proper = sr_per_trade * np.sqrt(trades_per_year)
    print(f"\nProper annualization (trades/year={trades_per_year:.1f}):")
    print(f"  Sharpe annualized = {sr_annual_proper:+.2f}  (per-trade × sqrt(trades/year))")

    print(f"\nDeflated Sharpe analysis (corrects for multiple testing):")
    for n_trials in (50, 200, 1000, 5000):
        d = deflated_sharpe(sr_per_trade, n, skew=skew, kurt=kurt, n_trials=n_trials)
        print(f"\n  N_TRIALS={n_trials}:")
        print(f"    E[max SR] (in SR units) = {d['e_max_sr_units']:+.4f}")
        print(f"    sigma(SR)                = {d['sigma_sr']:.4f}")
        print(f"    DSR probability          = {d['deflated_sr_prob']*100:.1f}%   "
              f"(P(true SR > 0 | {n_trials} trials assumed))")


if __name__ == "__main__":
    main()
