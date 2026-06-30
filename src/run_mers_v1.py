"""V1 MERS backtest: trade gold around scheduled macro events using the
asymmetric directional bias from literature.

Sweeps event types, hold periods, surprise-z thresholds, and bar resolution.
Outputs a leaderboard so we can see which configurations actually have edge
after costs.
"""
from __future__ import annotations
from pathlib import Path
import itertools

import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from backtest import BacktestConfig, run, summarize, print_summary, OUT_DIR

ALL_EVENTS = ("FOMC", "NFP", "UNRATE", "CPI", "PPI", "RETAIL", "CLAIMS")


def sweep(bars: pd.DataFrame, events: pd.DataFrame, bar_label: str):
    rows = []
    detail = {}
    # First: each event type individually, sweep hold horizons
    for ev_type in ALL_EVENTS:
        for hold in (1, 2, 3, 4):
            for z_min in (0.0, 0.5, 1.0):
                cfg = BacktestConfig(
                    hold_bars=hold, enter_offset_bars=1,
                    surprise_z_min=z_min, event_filter=(ev_type,),
                )
                trades = run(bars, events, cfg)
                if trades.empty:
                    continue
                s = summarize(trades, label=f"{ev_type}|hold={hold}|z>={z_min}")
                rows.append(s)
                detail[s["label"]] = trades

    # Then: combined event set (the practical signal)
    for hold in (1, 2, 3, 4):
        for z_min in (0.0, 0.5, 1.0):
            for events_inc in [
                ("FOMC", "NFP", "CPI", "PPI", "RETAIL", "UNRATE", "CLAIMS"),
                ("FOMC", "NFP", "CPI", "PPI"),
                ("NFP", "CPI", "PPI", "RETAIL"),
                ("CLAIMS",),
            ]:
                tag = "+".join(events_inc)
                cfg = BacktestConfig(hold_bars=hold, enter_offset_bars=1,
                                     surprise_z_min=z_min, event_filter=events_inc)
                trades = run(bars, events, cfg)
                if trades.empty:
                    continue
                s = summarize(trades, label=f"{tag}|hold={hold}|z>={z_min}")
                rows.append(s)
                detail[s["label"]] = trades

    df = pd.DataFrame(rows)
    df["bar_label"] = bar_label
    return df, detail


def main():
    print("="*100)
    print("MERS v1 backtest — GC futures, macro-event directional bias")
    print("="*100)

    events = build_all()

    # Run on 1h bars (2-year window) — primary
    print("\n--- 1-HOUR BARS (~2-year window) ---")
    gc1h = gc_load("60m")
    res_1h, detail_1h = sweep(gc1h, events, "1h")

    # Run on 5m bars (~60-day window) — recency check
    print("\n--- 5-MIN BARS (~60-day window) ---")
    gc5 = gc_load("5m")
    res_5m, detail_5m = sweep(gc5, events, "5m")

    all_res = pd.concat([res_1h, res_5m], ignore_index=True)

    # Save leaderboard
    out = OUT_DIR / "mers_v1_leaderboard.csv"
    all_res.to_csv(out, index=False)
    print(f"\nSaved full leaderboard -> {out}\n")

    # Filter to meaningful sample sizes and print best
    for bar_label in ["1h", "5m"]:
        sub = all_res[all_res["bar_label"] == bar_label].copy()
        if sub.empty:
            continue
        sub = sub[sub["n"] >= 15]
        print(f"\n*** Top by total_net_pnl (n>=15) — {bar_label} ***")
        for _, r in sub.sort_values("total_net_pnl", ascending=False).head(12).iterrows():
            print_summary(r.to_dict())
        print(f"\n*** Worst (sanity / inverse-edge check) — {bar_label} ***")
        for _, r in sub.sort_values("total_net_pnl").head(5).iterrows():
            print_summary(r.to_dict())


if __name__ == "__main__":
    main()
