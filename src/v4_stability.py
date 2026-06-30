"""Parameter stability for MERS v4.

If v4's edge is real, small perturbations to (TREND_N, WATCH, HOLD, B_ATR)
should produce qualitatively similar results — not a sharp spike at one
config. We sweep and look at the distribution of Sharpe across configs.
"""
import numpy as np
import pandas as pd

import mers_v4_final as v4
from data_gc import load as gc_load
from calendar_events import build_all
from backtest import summarize, print_summary


def main():
    events = build_all()
    gc1h = gc_load("60m")

    rows = []
    for trend_n in (20, 30, 50, 80, 120):
        for watch in (1, 2, 3):
            for hold in (2, 3, 4, 6):
                for b in (0.05, 0.10, 0.20, 0.40):
                    # monkey-patch module globals
                    v4.TREND_N = trend_n
                    v4.WATCH = watch
                    v4.HOLD = hold
                    v4.B_ATR = b
                    trades = v4.run_v4(gc1h, events)
                    s = summarize(trades, label=f"trend={trend_n}|w={watch}|h={hold}|b={b}")
                    s["params"] = (trend_n, watch, hold, b)
                    rows.append(s)

    df = pd.DataFrame(rows)
    df = df[df["n"] >= 20].copy()  # require minimum sample
    print(f"Configs with n>=20: {len(df)}")
    print(f"  fraction profitable: {(df['total_net_pnl'] > 0).mean()*100:.1f}%")
    print(f"  fraction Sharpe > 1: {(df['sharpe_per_trade'] > 1).mean()*100:.1f}%")
    print(f"  fraction Sharpe > 2: {(df['sharpe_per_trade'] > 2).mean()*100:.1f}%")
    print(f"  median sharpe: {df['sharpe_per_trade'].median():+.2f}")
    print(f"  median total_net_pnl: ${df['total_net_pnl'].median():+.0f}")
    print(f"  median win_rate: {df['win_rate'].median()*100:.1f}%")

    print("\nTop 10 by total P&L:")
    for _, r in df.sort_values("total_net_pnl", ascending=False).head(10).iterrows():
        print_summary(r.to_dict())

    print("\nBottom 10 by total P&L:")
    for _, r in df.sort_values("total_net_pnl").head(10).iterrows():
        print_summary(r.to_dict())


if __name__ == "__main__":
    main()
