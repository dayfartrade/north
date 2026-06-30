"""Performance dashboard for live MERS v5 forward-test.

Reads data/tracker/forward_log.csv and produces:
  - Markdown summary (printable + Telegram-postable)
  - Comparison vs backtest expectation
  - Per-event breakdown
  - Equity curve (text-based sparkline)
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v5 import run_v5
from backtest import summarize


ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "tracker" / "forward_log.csv"
BACKTEST_EXPECTATION = {
    "mean_pnl_per_trade": 468.20,
    "win_rate": 0.553,
    "sharpe_per_trade": 0.147,         # honest per-trade Sharpe
    "sharpe_annualized": 0.59,         # ×√(16 trades/yr) — realistic
    "sharpe_naive_daily": 2.30,        # ×√252 — published convention, not realistic
    "quarters_profitable_pct": 5/9,    # walk-forward quarterly
    "events_per_month": 3,
    "dsr_50trials": 0.103,
    "dsr_200trials": 0.040,
    "note": "Backtest n=38. Wide CI; expect variance. DSR moderate.",
}


def sparkline(values, width=40):
    if len(values) == 0:
        return ""
    chars = "▁▂▃▄▅▆▇█"
    lo, hi = float(min(values)), float(max(values))
    if hi == lo:
        return chars[len(chars)//2] * min(len(values), width)
    out = []
    for v in values[-width:]:
        idx = int((v - lo) / (hi - lo) * (len(chars) - 1))
        out.append(chars[idx])
    return "".join(out)


def build_dashboard() -> str:
    out = ["*GoldDayTrader — Live Forward Performance*",
           f"_Generated {datetime.now(timezone.utc).isoformat(timespec='minutes')}_\n"]

    if not LOG.exists():
        out.append("No forward trades yet — forward log empty.")
        return "\n".join(out)

    df = pd.read_csv(LOG, parse_dates=["event_ts", "entry_ts", "exit_ts"])
    taken = df[df["took_trade"] == True].copy()
    skipped = df[df["took_trade"] == False]

    out.append(f"Events resolved: *{len(df)}*  (took *{len(taken)}*, skipped {len(skipped)})")

    if taken.empty:
        out.append("\nNo trades taken yet.")
        return "\n".join(out)

    n = len(taken)
    wins = (taken["net_pnl"] > 0).sum()
    win_rate = wins / n
    total = taken["net_pnl"].sum()
    mean = taken["net_pnl"].mean()
    std = taken["net_pnl"].std()
    sharpe = mean / std * np.sqrt(252) if std > 0 else float("nan")
    pf_num = taken.loc[taken["net_pnl"] > 0, "net_pnl"].sum()
    pf_den = -taken.loc[taken["net_pnl"] < 0, "net_pnl"].sum()
    pf = pf_num / pf_den if pf_den > 0 else float("inf")

    out.append(f"\n*Aggregate*")
    out.append(f"  trades: *{n}*  ·  wins: *{wins}/{n}* ({win_rate*100:.1f}%)")
    out.append(f"  total P&L (per contract): *${total:+,.0f}*")
    out.append(f"  mean / trade: *${mean:+,.2f}*  ·  std: ${std:,.2f}")
    out.append(f"  Sharpe (ann.): *{sharpe:+.2f}*  ·  Profit Factor: *{pf:.2f}*")

    out.append(f"\n*Backtest expectation (n=38 over 2y, walk-fwd by quarter)*")
    e = BACKTEST_EXPECTATION
    out.append(f"  Sharpe (annualized, realistic) ~ *{e['sharpe_annualized']:+.2f}*")
    out.append(f"  Win rate ~ *{e['win_rate']*100:.1f}%*  ·  Mean/trade ~ *${e['mean_pnl_per_trade']:+.0f}*")
    out.append(f"  Quarters profitable: *{int(e['quarters_profitable_pct']*9)}/9*")
    out.append(f"  Deflated Sharpe Prob (200 trials): {e['dsr_200trials']*100:.0f}%")
    out.append(f"  _{e['note']}_")
    out.append(f"  Expected ~{e['events_per_month']} trades/month")

    out.append("\n*Equity curve (last 40 trades)*")
    eq = taken["net_pnl"].cumsum().values
    out.append("`" + sparkline(eq, 40) + "`  (final " + f"${eq[-1]:+,.0f}" + ")")

    # Per event
    out.append("\n*Per event*")
    for ev_type, g in taken.groupby("event_type"):
        ng = len(g)
        wn = (g["net_pnl"] > 0).sum()
        tot = g["net_pnl"].sum()
        out.append(f"  {ev_type:5s} n={ng:3d}  win={wn}/{ng}  total=${tot:+,.0f}")

    # Last 5 trades
    out.append("\n*Last 5 trades*")
    last = taken.sort_values("entry_ts").tail(5)
    for _, r in last.iterrows():
        dir_s = "LONG" if r["direction"] == 1 else "SHORT"
        out.append(f"  {pd.Timestamp(r['entry_ts']).strftime('%m-%d %H:%M')}  "
                   f"{r['event_type']:5s} {dir_s:5s}  "
                   f"@${r['entry_price']:.2f} → ${r['exit_price']:.2f}  "
                   f"${r['net_pnl']:+,.0f}")

    # Drift check: are we matching backtest expectation?
    out.append("\n*Drift check vs backtest*")
    deltas = []
    if abs(win_rate - e["win_rate"]) > 0.15:
        deltas.append(f"Win rate {win_rate*100:.1f}% vs expected {e['win_rate']*100:.1f}%")
    if mean < 0 and e["mean_pnl_per_trade"] > 0 and n >= 5:
        deltas.append(f"Mean is NEGATIVE (${mean:+.0f}) vs expected $+{e['mean_pnl_per_trade']:.0f}")
    if n >= 10 and abs(sharpe - e["sharpe"]) > 4:
        deltas.append(f"Sharpe {sharpe:+.2f} drifts > 4 from expected {e['sharpe']:+.2f}")
    if not deltas:
        out.append("  ✅ within expected range (or sample too small)")
    else:
        for d in deltas:
            out.append(f"  ⚠️ {d}")

    return "\n".join(out)


if __name__ == "__main__":
    print(build_dashboard())
