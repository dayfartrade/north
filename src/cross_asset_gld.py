"""Cross-asset validation on GLD ETF.

If MERS v5 captures a real news-driven edge in gold, it should partially
transfer to GLD (same fundamental driver, different microstructure: ETF on
NYSE, regular-session only, no overnight gap continuation).

We expect:
  - GLD only trades 9:30-16:00 ET, so events outside this window are missed.
  - The CPI/NFP/UNRATE events (8:30 ET) are PRE-OPEN — these are missed entirely.
  - The FOMC (14:00 ET) lands inside the GLD session — these are the cleanest test.
  - Expected: edge survives on FOMC subset for GLD.

If FOMC edge doesn't transfer to GLD at all, that's a worry. If it transfers
even partially, that's confirmation.
"""
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

from calendar_events import build_all
from mers_v5 import run_v5, dedupe_co_released, TOP_EVENTS_V5
from backtest import summarize, print_summary, CONTRACT_SIZE, RT_COST_PER_CONTRACT


ROOT = Path(__file__).resolve().parent.parent


def fetch_gld_1h():
    df = yf.download("GLD", period="730d", interval="60m",
                     progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    df.index.name = "ts"
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def main():
    print("Fetching GLD 1h bars (2y)...")
    gld = fetch_gld_1h()
    if gld.empty:
        print("Empty GLD data — abort.")
        return
    print(f"GLD bars: {len(gld)} rows, range {gld.index.min()} .. {gld.index.max()}")

    # For GLD as a stock, we need to redefine the cost model (no $24 per contract).
    # Approximate: 100 shares of GLD ≈ 1 oz exposure × ~spot/10. P&L per share = price change.
    # Cost: ~$0.01 per share spread + slippage + $0 commission = ~$0.02 per share RT
    # We'll keep the backtest in $/100-share units to be comparable: equivalent of 1 GC contract.

    # Use the v5 runner — but rewrite cost since GLD is much cheaper per "unit".
    # Easier: run v5 with normal cost, but interpret results in % terms.
    events = build_all()
    trades = run_v5(gld, events)
    if trades.empty:
        print("No trades on GLD.")
        return

    # Recompute P&L in % terms (cost-free) for comparison
    trades["ret_pct"] = (trades["exit_price"] - trades["entry_price"]) / trades["entry_price"] * trades["direction"] * 100
    print(f"\n[GLD] Total trades: {len(trades)}")
    print(trades["event_type"].value_counts())

    print("\n[GLD] By event:")
    for ev in TOP_EVENTS_V5:
        sub = trades[trades["event_type"] == ev]
        if sub.empty:
            print(f"  {ev:6s} n=0")
            continue
        n = len(sub)
        win = (sub["ret_pct"] > 0).sum()
        mean_r = sub["ret_pct"].mean()
        total_r = sub["ret_pct"].sum()
        sharpe = (sub["ret_pct"].mean() / sub["ret_pct"].std() * np.sqrt(252)) if sub["ret_pct"].std() > 0 else np.nan
        print(f"  {ev:6s} n={n:3d}  win={win}/{n} ({win/n*100:5.1f}%)  "
              f"mean_ret={mean_r:+.3f}%  total={total_r:+.2f}%  sharpe={sharpe:+.2f}")

    # GC comparison on the same events
    from data_gc import load as gc_load
    gc1h = gc_load("60m")
    gc_trades = run_v5(gc1h, events)
    gc_trades["ret_pct"] = (gc_trades["exit_price"] - gc_trades["entry_price"]) / gc_trades["entry_price"] * gc_trades["direction"] * 100

    print("\n[GC for comparison] By event:")
    for ev in TOP_EVENTS_V5:
        sub = gc_trades[gc_trades["event_type"] == ev]
        if sub.empty:
            continue
        n = len(sub)
        win = (sub["ret_pct"] > 0).sum()
        mean_r = sub["ret_pct"].mean()
        total_r = sub["ret_pct"].sum()
        sharpe = (sub["ret_pct"].mean() / sub["ret_pct"].std() * np.sqrt(252)) if sub["ret_pct"].std() > 0 else np.nan
        print(f"  {ev:6s} n={n:3d}  win={win}/{n} ({win/n*100:5.1f}%)  "
              f"mean_ret={mean_r:+.3f}%  total={total_r:+.2f}%  sharpe={sharpe:+.2f}")

    # Save
    trades.to_csv(ROOT / "data" / "backtests" / "gld_v5.csv", index=False)


if __name__ == "__main__":
    main()
