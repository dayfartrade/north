"""Test: do NY ORB entries inside the London 15:00 fix window actually lose?

Empirical test before deploying a stand-down rule.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from datetime import datetime
import pytz

from data_gc import load as gc_load
from edge_session_orb_v7_final import run_orb_v7, SESSION_CONFIG
from edge_session_orb import session_utc_time_on
from stand_down import is_london_fix_window, is_news_window, _load_calendar


def main():
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    cal = _load_calendar()

    all_trades = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        if not df.empty:
            all_trades.append(df)
    trades = pd.concat(all_trades, ignore_index=True)
    taken = trades[trades["took_trade"] == True].copy()

    # Tag each trade with fix/news status at ENTRY time
    fix_status = []; news_status = []
    for _, r in taken.iterrows():
        ets = pd.Timestamp(r["entry_ts"])
        if ets.tz is None: ets = ets.tz_localize("UTC")
        fw, fr = is_london_fix_window(ets)
        nw, nr = is_news_window(ets, cal)
        fix_status.append(fw)
        news_status.append(nw)
    taken["in_fix"] = fix_status
    taken["in_news"] = news_status

    print("=== Entry-time stand-down empirical test ===\n")

    print("--- Overall ---")
    in_either = taken[taken["in_fix"] | taken["in_news"]]
    out_both = taken[~(taken["in_fix"] | taken["in_news"])]
    print(f"  IN fix OR news:  n={len(in_either):3d}  win%={(in_either['net_pnl']>0).mean()*100 if not in_either.empty else 0:.1f}  mean=${in_either['net_pnl'].mean() if not in_either.empty else 0:+.2f}  total=${in_either['net_pnl'].sum():+.0f}")
    print(f"  CLEAN:           n={len(out_both):3d}  win%={(out_both['net_pnl']>0).mean()*100:.1f}  mean=${out_both['net_pnl'].mean():+.2f}  total=${out_both['net_pnl'].sum():+.0f}")
    print()

    print("--- By session ---")
    for sess in sorted(taken["session"].unique()):
        sub = taken[taken["session"] == sess]
        in_f = sub[sub["in_fix"]]
        in_n = sub[sub["in_news"]]
        out = sub[~sub["in_fix"] & ~sub["in_news"]]
        print(f"  {sess:5s}: total n={len(sub)}")
        print(f"    in_fix:  n={len(in_f):3d}  win%={(in_f['net_pnl']>0).mean()*100 if not in_f.empty else 0:5.1f}  mean=${in_f['net_pnl'].mean() if not in_f.empty else 0:+8.2f}  total=${in_f['net_pnl'].sum():+8.0f}")
        print(f"    in_news: n={len(in_n):3d}  win%={(in_n['net_pnl']>0).mean()*100 if not in_n.empty else 0:5.1f}  mean=${in_n['net_pnl'].mean() if not in_n.empty else 0:+8.2f}  total=${in_n['net_pnl'].sum():+8.0f}")
        print(f"    clean:   n={len(out):3d}  win%={(out['net_pnl']>0).mean()*100 if not out.empty else 0:5.1f}  mean=${out['net_pnl'].mean() if not out.empty else 0:+8.2f}  total=${out['net_pnl'].sum():+8.0f}")
    print()

    print("--- Detail: in-fix NY entries ---")
    ny_fix = taken[(taken["session"] == "NY") & (taken["in_fix"])]
    for _, r in ny_fix.iterrows():
        print(f"  {str(r['entry_ts'])[:16]} dir={int(r['direction']):+d}  exit_reason={r['exit_reason']:6s}  net_pnl=${r['net_pnl']:+8.2f}")


if __name__ == "__main__":
    main()
