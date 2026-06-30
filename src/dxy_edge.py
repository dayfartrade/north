"""DXY divergence edge prototype.

Hypothesis: GC and DXY normally have a strong negative correlation. Short-term
divergence (DXY breaks structure, GC doesn't move opposite) often resolves
with GC catching down (or DXY catching up). We test:

  - For each rolling window of N hours, compute return(GC), return(DXY)
  - "Divergence" = GC return + DXY return (both in same direction is bad sign)
  - Trade GC opposite to DXY when divergence exceeds a threshold

NOTE: DXY data on yfinance: DX-Y.NYB (ICE futures) or UUP (ETF proxy).
We'll use UUP for hourly data; FRED's DTWEXBGS for daily.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

from data_gc import load as gc_load
from backtest import CONTRACT_SIZE, RT_COST_PER_CONTRACT, summarize, print_summary


def fetch_dxy_1h():
    """DX-Y.NYB = ICE Dollar Index futures, 24h, same bar alignment as GC."""
    df = yf.download("DX-Y.NYB", period="730d", interval="60m",
                     progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    df.index.name = "ts"
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def align_pairs(gc: pd.DataFrame, dxy: pd.DataFrame) -> pd.DataFrame:
    """Merge GC and DXY hourly returns on the SAME aligned bar timestamps."""
    gc_r = np.log(gc["close"]).diff()
    dx_r = np.log(dxy["close"]).diff()
    common = gc_r.index.intersection(dx_r.index)
    df = pd.DataFrame({
        "gc_close": gc["close"].reindex(common),
        "dxy_close": dxy["close"].reindex(common),
        "gc_ret": gc_r.reindex(common),
        "dxy_ret": dx_r.reindex(common),
    }).dropna()
    return df


def divergence_signal(df: pd.DataFrame, lookback=24, z_threshold=2.0) -> pd.DataFrame:
    """For each bar, compute a divergence z-score over lookback hours.
    Divergence_t = corr-residual between GC and DXY returns.

    Simpler approach: rolling sum of (gc_ret + dxy_ret). Normally ≈ 0 (anti-corr).
    When |sum| is large, GC+DXY moved together → divergence from normal.
    Mean-revert hypothesis: trade GC opposite to the persistent direction.
    """
    s = (df["gc_ret"] + df["dxy_ret"]).rolling(lookback).sum()
    z = (s - s.rolling(120).mean()) / s.rolling(120).std()
    df = df.copy()
    df["div_sum"] = s
    df["div_z"] = z
    # Signal: if z > threshold (both up together too much), short GC at next bar.
    # If z < -threshold (both down together), long GC at next bar.
    df["signal"] = 0
    df.loc[df["div_z"] > z_threshold, "signal"] = -1
    df.loc[df["div_z"] < -z_threshold, "signal"] = 1
    return df


def simulate(df: pd.DataFrame, hold=4):
    trades = []
    in_trade = False
    bar_freq = pd.Timedelta(hours=1)
    last_exit_idx = -1
    for i in range(len(df) - hold - 1):
        if i <= last_exit_idx:
            continue
        s = df["signal"].iloc[i]
        if s == 0:
            continue
        entry_ts = df.index[i + 1]
        # Use NEXT bar's open as entry (avoid look-ahead). yfinance bar timestamps are bar start.
        entry_price = df["gc_close"].iloc[i]  # approx — would use next bar open in real
        exit_idx = i + 1 + hold
        exit_price = df["gc_close"].iloc[exit_idx]
        gross = (exit_price - entry_price) * s * CONTRACT_SIZE
        net = gross - RT_COST_PER_CONTRACT
        trades.append({
            "entry_ts": entry_ts, "exit_ts": df.index[exit_idx],
            "direction": int(s), "entry_price": float(entry_price),
            "exit_price": float(exit_price),
            "gross_pnl": float(gross), "net_pnl": float(net),
            "div_z_at_signal": float(df["div_z"].iloc[i]),
        })
        last_exit_idx = exit_idx
    return pd.DataFrame(trades)


def main():
    print("="*100)
    print("DXY divergence edge — prototype")
    print("="*100)
    gc = gc_load("60m")
    print("Fetching DX-Y.NYB (DXY futures 24h)...")
    dxy = fetch_dxy_1h()
    print(f"GC: {len(gc)} bars, DXY: {len(dxy)} bars")

    df = align_pairs(gc, dxy)
    print(f"Aligned: {len(df)} common hourly bars")

    print("\nSweep over lookback / z-threshold / hold:")
    print(f"{'look':>5s} {'z':>4s} {'hold':>4s} {'n':>4s} {'win%':>6s} {'mean_$':>10s} {'total_$':>10s} {'sharpe':>7s}")
    results = []
    for lb in (12, 24, 48, 72):
        for z in (1.0, 1.5, 2.0, 2.5):
            sigdf = divergence_signal(df, lookback=lb, z_threshold=z)
            for hold in (2, 4, 8, 12, 24):
                trades = simulate(sigdf, hold=hold)
                if trades.empty: continue
                s = summarize(trades, label=f"lb={lb}|z={z}|h={hold}")
                if s["n"] >= 10:
                    print(f"{lb:5d} {z:4.1f} {hold:4d} {s['n']:4d} {s['win_rate']*100:6.1f} "
                          f"{s['mean_net_pnl']:+10.2f} {s['total_net_pnl']:+10.0f} {s['sharpe_per_trade']:+7.2f}")
                    results.append(s)

    print(f"\nTotal valid configs: {len(results)}")
    profitable = [r for r in results if r['total_net_pnl'] > 0]
    print(f"Profitable: {len(profitable)}/{len(results)} ({len(profitable)/max(1,len(results))*100:.0f}%)")
    if profitable:
        best = max(profitable, key=lambda r: r['sharpe_per_trade'])
        print(f"\nBest by Sharpe: {best['label']}")
        print_summary(best)


if __name__ == "__main__":
    main()
