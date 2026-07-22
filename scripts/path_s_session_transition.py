"""Path S variant: London close → NY open transition edge on 1m gold.

Theoretical basis: London 16:00 UTC close creates temporary
imbalance as European positions unwind before NY takes over at
13:00 UTC (same trading day). This produces a persistent
directional bias in the 12:55-13:15 UTC window on gold.

Config (fixed):
  - Signal window: last 15 minutes of London (15:45-16:00 UTC daily)
  - Trigger: sign of net London-session return (15:45 close vs 15:00 close)
  - Entry: 12:55 UTC (5 min before NY session open next day? No — same day)
  - Actually: London close is 16:00 UTC, London already ended. Re-check.

Actually let me be more careful. Gold trades 24/5. Session convention:
  ASIA:   22:00 - 06:00 UTC
  LONDON: 06:00 - 15:00 UTC (per our SESSION_UTC)
  NY:     13:00 - 21:00 UTC (overlaps London 13-15)

The "London close" as European positioning shift happens ~15:00-15:30 UTC.
The "NY momentum" that fades this is 13:00-14:30 UTC (before it).

Better hypothesis: **fade the London morning direction going into NY**.
If London went up 06:00-13:00 UTC, sell at 13:00 UTC NY open; and vice
versa. This is a classical "fade the pre-market bias" trade.

Config:
  - Signal window: London 06:00 UTC open to NY 13:00 UTC open (7 hours)
  - Trigger: sign of London-session return
  - Entry: NY 13:00 UTC open bar close
  - Direction: OPPOSITE of London-session return
  - Hold: 60 minutes (until 14:00 UTC)
  - Stop: 1.5x ATR(60min)
  - Cost: $3 RT (GC futures)

Retire criteria: Sharpe < 0.5 or WR < 45% on 2019-2023 -> retire.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from collections import defaultdict

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS_1M = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_1m_historical.csv"

CONTRACT_SIZE = 100
RT_COST = 3.0
HOLD_MIN = 60
STOP_ATR_MULT = 1.5
ATR_BARS = 60  # 60 1m bars = 60 min


def load_bars() -> pd.DataFrame:
    df = pd.read_csv(BARS_1M, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


def compute_atr_1m(bars: pd.DataFrame, n: int) -> pd.Series:
    high = bars["high"]; low = bars["low"]; close_prev = bars["close"].shift(1)
    tr = pd.concat([high - low, (high - close_prev).abs(),
                    (low - close_prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def bar_at_or_after(bars: pd.DataFrame, ts: pd.Timestamp) -> int | None:
    if ts < bars.index[0] or ts > bars.index[-1]:
        return None
    idx = bars.index.searchsorted(ts, side="left")
    return int(idx) if idx < len(bars) else None


def main() -> None:
    print(f"Loading 1m bars from {BARS_1M.name}...")
    bars = load_bars()
    print(f"  {len(bars):,} bars {bars.index[0].date()} -> {bars.index[-1].date()}")

    atr = compute_atr_1m(bars, ATR_BARS)

    dates = sorted(set(bars.index.date))
    trades = []
    for date in dates:
        d = pd.Timestamp(date, tz="UTC")
        if d.weekday() >= 5:
            continue

        london_open_ts = d + pd.Timedelta(hours=6)
        ny_open_ts = d + pd.Timedelta(hours=13)

        lon_idx = bar_at_or_after(bars, london_open_ts)
        ny_idx = bar_at_or_after(bars, ny_open_ts)
        if lon_idx is None or ny_idx is None:
            continue
        if ny_idx - lon_idx < 300:  # too little London activity
            continue

        lon_open_price = float(bars.iloc[lon_idx]["open"])
        ny_open_price = float(bars.iloc[ny_idx]["open"])
        london_ret = ny_open_price - lon_open_price

        # Skip near-zero London moves
        cur_atr = float(atr.iloc[ny_idx])
        if cur_atr <= 0 or pd.isna(cur_atr):
            continue
        if abs(london_ret) < 0.5 * cur_atr:
            continue

        # Fade: enter opposite direction
        direction = "SHORT" if london_ret > 0 else "LONG"
        dir_sign = 1 if direction == "LONG" else -1
        entry_price = ny_open_price
        stop_price = entry_price - dir_sign * STOP_ATR_MULT * cur_atr

        # Hold HOLD_MIN bars
        exit_price = None; exit_reason = None
        for k in range(HOLD_MIN):
            i = ny_idx + 1 + k
            if i >= len(bars):
                break
            b = bars.iloc[i]
            if direction == "LONG":
                hit_stop = float(b["low"]) <= stop_price
            else:
                hit_stop = float(b["high"]) >= stop_price
            if hit_stop:
                exit_price = stop_price; exit_reason = "stop"; break
        if exit_price is None:
            end_idx = min(ny_idx + HOLD_MIN, len(bars) - 1)
            exit_price = float(bars.iloc[end_idx]["close"])
            exit_reason = "time"

        gross = (exit_price - entry_price) * dir_sign * CONTRACT_SIZE
        net = gross - RT_COST
        trades.append({
            "date": str(date), "direction": direction,
            "london_ret_pts": round(london_ret, 3),
            "atr": round(cur_atr, 3),
            "entry": entry_price, "exit": exit_price, "exit_reason": exit_reason,
            "net_pnl": net,
        })

    print(f"\nTotal trades: {len(trades)}")
    if not trades:
        return

    pnls = [t["net_pnl"] for t in trades]
    n = len(pnls); total = sum(pnls); mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    print(f"  Total P&L:    ${total:+,.0f}")
    print(f"  Mean $/trade: ${mean:+,.2f}")
    print(f"  WR:           {100*wins/n:.1f}%")

    # By year
    print(f"\nBy year:")
    by_yr = defaultdict(list)
    for t in trades:
        by_yr[t["date"][:4]].append(t)
    for y in sorted(by_yr):
        tr = by_yr[y]
        pl = [t["net_pnl"] for t in tr]
        n_y = len(pl); w = sum(1 for p in pl if p > 0)
        print(f"  {y}: n={n_y:>3d}  mean=${sum(pl)/n_y:>+7,.0f}  "
              f"WR={100*w/n_y:>4.1f}%  total=${sum(pl):>+7,.0f}")

    # By direction
    print(f"\nBy direction:")
    by_dir = defaultdict(list)
    for t in trades:
        by_dir[t["direction"]].append(t)
    for d in sorted(by_dir):
        tr = by_dir[d]
        pl = [t["net_pnl"] for t in tr]
        n_d = len(pl); w = sum(1 for p in pl if p > 0)
        print(f"  {d}: n={n_d:>3d}  mean=${sum(pl)/n_d:>+7,.0f}  "
              f"WR={100*w/n_d:>4.1f}%")


if __name__ == "__main__":
    main()
