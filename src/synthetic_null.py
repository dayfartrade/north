"""Synthetic null test.

If MERS v5 has a real edge, it should:
  - Lose money or break even on a SYNTHETIC random-walk gold series with the
    SAME event timestamps applied (where the event has no real effect).
  - The empirical p-value of the real Sharpe vs the synthetic distribution
    should be small (< 0.05 ideal, < 0.10 acceptable for small n).

We generate N synthetic price paths matching gold's first two moments:
  - Mean log-return, std log-return calibrated from real GC 1h returns.
  - GBM with these stats, same length and timestamps as real GC 1h bars.
  - Convert to OHLC with simulated intra-bar wiggle (proportional to vol).

Then we run MERS v5 against each synthetic path WITH the real event calendar
(events don't move the synthetic price — they just provide timestamps).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v5 import run_v5
from backtest import summarize

RNG = np.random.default_rng(42)


def fit_log_return_stats(bars: pd.DataFrame) -> tuple[float, float]:
    lr = np.log(bars["close"]).diff().dropna()
    return float(lr.mean()), float(lr.std())


def synth_bars_like(bars: pd.DataFrame, mu: float, sigma: float,
                     rng=None) -> pd.DataFrame:
    """Generate a GBM-like OHLC series with same index as `bars`."""
    rng = rng or np.random.default_rng()
    n = len(bars)
    lr = rng.normal(loc=mu, scale=sigma, size=n)
    log_close = np.log(bars["close"].iloc[0]) + np.cumsum(lr)
    close = np.exp(log_close)
    # Intra-bar wiggle proportional to per-bar volatility (sigma scales)
    intra = np.abs(rng.normal(0, sigma * 0.7, size=n))
    high = close * np.exp(intra)
    low = close * np.exp(-intra)
    open_ = np.concatenate([[close[0]], close[:-1]])
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close},
                       index=bars.index.copy())
    # Add a fake volume column for compat
    df["volume"] = 1.0
    df["adj close"] = df["close"]
    return df


def main():
    bars = gc_load("60m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    events = build_all()

    mu, sigma = fit_log_return_stats(bars)
    print(f"Real GC 1h returns: mu={mu:+.6f}, sigma={sigma:.6f}")

    # Real-data benchmark
    real_trades = run_v5(bars, events)
    real_s = summarize(real_trades, label="REAL")
    print(f"\nReal benchmark: n={real_s['n']}, sharpe={real_s['sharpe_per_trade']:+.3f}, "
          f"total_pnl=${real_s['total_net_pnl']:+.0f}, win%={real_s['win_rate']*100:.1f}")

    # Synthetic null distribution
    n_paths = 200
    rng = np.random.default_rng(42)
    sharpes = []
    totals = []
    win_rates = []
    n_trades = []
    print(f"\nRunning {n_paths} synthetic GBM paths with real event timestamps...")
    for p in range(n_paths):
        synth = synth_bars_like(bars, mu, sigma, rng=rng)
        synth_trades = run_v5(synth, events)
        s = summarize(synth_trades, label=f"synth_{p}")
        if s["n"] >= 5:
            sharpes.append(s["sharpe_per_trade"])
            totals.append(s["total_net_pnl"])
            win_rates.append(s["win_rate"])
            n_trades.append(s["n"])
        if (p + 1) % 50 == 0:
            print(f"  {p+1}/{n_paths} done")

    sharpes = np.array(sharpes)
    totals = np.array(totals)
    win_rates = np.array(win_rates)
    n_trades = np.array(n_trades)

    print("\n=== SYNTHETIC NULL DISTRIBUTION ===")
    print(f"Paths used (n_trades >= 5): {len(sharpes)}")
    print(f"  mean trades per path: {n_trades.mean():.1f}")
    print(f"  Sharpe:    mean={sharpes.mean():+.3f}  std={sharpes.std():.3f}  "
          f"q05={np.percentile(sharpes, 5):+.3f}  q95={np.percentile(sharpes, 95):+.3f}")
    print(f"  Total $:   mean=${totals.mean():+.0f}  std=${totals.std():.0f}  "
          f"q05=${np.percentile(totals, 5):+.0f}  q95=${np.percentile(totals, 95):+.0f}")
    print(f"  Win rate:  mean={win_rates.mean()*100:.1f}%  std={win_rates.std()*100:.2f}%")

    # Empirical p-values: fraction of synthetic paths matching/exceeding real result
    real_sharpe = real_s["sharpe_per_trade"]
    real_total = real_s["total_net_pnl"]
    real_winrate = real_s["win_rate"]
    p_sharpe = (sharpes >= real_sharpe).mean()
    p_total = (totals >= real_total).mean()
    p_winrate = (win_rates >= real_winrate).mean()

    print("\n=== EMPIRICAL P-VALUES ===")
    print(f"  P(synth Sharpe   >= real {real_sharpe:+.3f}):  {p_sharpe:.4f}")
    print(f"  P(synth total$   >= real ${real_total:+.0f}):    {p_total:.4f}")
    print(f"  P(synth win-rate >= real {real_winrate*100:.1f}%): {p_winrate:.4f}")

    if p_sharpe < 0.05:
        print("\n  -> Real edge SIGNIFICANT at p<0.05 (strong)")
    elif p_sharpe < 0.10:
        print("\n  -> Real edge SIGNIFICANT at p<0.10 (moderate)")
    elif p_sharpe < 0.20:
        print("\n  -> Real edge marginal (p<0.20)")
    else:
        print("\n  -> Real edge NOT distinguishable from random noise (p>=0.20)")

    # Save results
    out = Path(__file__).resolve().parent.parent / "data" / "backtests" / "synthetic_null.csv"
    pd.DataFrame({
        "sharpe": sharpes, "total_pnl": totals, "win_rate": win_rates, "n_trades": n_trades
    }).to_csv(out, index=False)
    print(f"\nSaved synthetic null distribution -> {out}")


if __name__ == "__main__":
    main()
