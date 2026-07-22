"""Crabel Gold 3-Day-Pattern ORB feasibility test.

Toby Crabel Ch 28 (Daily Bias — Gold), pages 219-226. Gold 1975-89 data
showed profitable ORB edges filtered by 3-day pattern of daily close vs
open signs. Each day's sign = '+' if close>open else '-'. Best gold setups:

  Pattern  Trade   n    WR    W/L    Gross
  +-+      SELL   189   61%   1.74   $27k     ← Path Z-consistent (SHORT after up bias)
  +++      SELL   193   53%   1.62   $22k
  +--      BUY    255   65%   0.89   $23k
  -++      SELL   241   56%   1.50   $27k

Feasibility question: does the 3DP-based ORB pattern reproduce on modern
gold (Dukascopy XAUUSD 2024-2026)? Would give us a v9 candidate with
different DNA than Path Z (daily-pattern filter vs intraday-slope filter).

Adaptation to modern gold:
- Crabel used "OPEN + 20 TICS" entry — in 1990 that was $2.00 on $400 gold.
- On $2000-2500 gold, $2 is very tight; use 0.5×ATR(10) as adaptive stretch.
- Use 5m bars, NY session open (13:00 UTC) as "the open".
- Hold 24 bars (2h) max, 2×ATR stop.
- 3-day pattern computed from PRIOR 3 daily close-vs-open signs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mers_v3_peb import compute_atr

CSV = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"

CONTRACT_SIZE = 100
RT_COST = 24.0
NY_HOUR_UTC = 13
MAX_HOLD_BARS = 24
ATR_STOP_MULT = 2.0
STRETCH_ATR_MULT = 0.5  # entry = open + 0.5*ATR (adaptive replacement for "20 tics")


def load_bars() -> pd.DataFrame:
    df = pd.read_csv(CSV, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


def build_daily_signs(bars: pd.DataFrame) -> dict:
    """Return dict date -> '+' or '-' for daily close vs open."""
    daily = bars.resample("1D").agg(open=("open", "first"),
                                     close=("close", "last")).dropna()
    signs = {}
    for ts, row in daily.iterrows():
        if row["close"] > row["open"]:
            signs[ts.date()] = "+"
        else:
            signs[ts.date()] = "-"
    return signs


def three_day_pattern(signs: dict, date) -> str | None:
    """Pattern of last 3 days ending on date-1 (exclusive of today)."""
    prev_dates = []
    d = date
    # Walk back to find 3 prior trading days
    while len(prev_dates) < 3:
        d = d - pd.Timedelta(days=1)
        d_date = d.date() if hasattr(d, "date") else d
        if d_date in signs:
            prev_dates.append(d_date)
        if (date - d).days > 10:  # safety
            return None
    prev_dates.reverse()
    return "".join(signs[d] for d in prev_dates)


def simulate_trade(bars: pd.DataFrame, entry_idx: int, entry_price: float,
                   stop_price: float, direction: str,
                   max_hold: int = MAX_HOLD_BARS) -> float:
    dir_sign = 1 if direction == "LONG" else -1
    for k in range(max_hold + 1):
        if entry_idx + k >= len(bars):
            break
        b = bars.iloc[entry_idx + k]
        if direction == "LONG":
            hit_stop = float(b["low"]) <= stop_price
        else:
            hit_stop = float(b["high"]) >= stop_price
        if hit_stop:
            exit_price = stop_price; break
    else:
        end_idx = min(entry_idx + max_hold, len(bars) - 1)
        exit_price = float(bars.iloc[end_idx]["close"])
    return (exit_price - entry_price) * dir_sign * CONTRACT_SIZE - RT_COST


def main() -> None:
    print(f"Loading {CSV.name}...")
    bars = load_bars()
    print(f"  {len(bars):,} bars {bars.index[0].date()} -> {bars.index[-1].date()}\n")

    print("Building daily open/close signs...")
    signs = build_daily_signs(bars)
    print(f"  {len(signs)} trading days\n")

    atr = compute_atr(bars, 10)

    # Iterate NY-open days, compute 3DP, simulate both directions
    from collections import defaultdict
    trades_by_pattern: dict[tuple[str, str], list[float]] = defaultdict(list)

    for date in sorted(set(bars.index.date)):
        d = pd.Timestamp(date, tz="UTC")
        if d.weekday() >= 5:
            continue
        pattern = three_day_pattern(signs, d)
        if pattern is None:
            continue

        # Locate NY open
        open_ts = d + pd.Timedelta(hours=NY_HOUR_UTC)
        # Find first bar at/after open_ts
        try:
            open_idx = bars.index.get_indexer([open_ts], method="bfill")[0]
        except Exception:
            continue
        if open_idx < 0 or open_idx >= len(bars):
            continue
        open_price = float(bars.iloc[open_idx]["open"])
        cur_atr = float(atr.iloc[open_idx])
        if cur_atr <= 0:
            continue

        stretch = STRETCH_ATR_MULT * cur_atr
        buy_stop = open_price + stretch  # buy entry (breakout)
        sell_stop = open_price - stretch  # sell entry

        # Watch WATCH_BARS after open for either breakout
        WATCH = 12
        buy_entry_idx = None; sell_entry_idx = None
        for k in range(1, WATCH + 1):
            i = open_idx + k
            if i >= len(bars): break
            b = bars.iloc[i]
            if buy_entry_idx is None and float(b["high"]) >= buy_stop:
                buy_entry_idx = i
            if sell_entry_idx is None and float(b["low"]) <= sell_stop:
                sell_entry_idx = i
            if buy_entry_idx is not None and sell_entry_idx is not None:
                break

        # Simulate BUY if it fired
        if buy_entry_idx is not None:
            entry_p = buy_stop
            stop_p = entry_p - ATR_STOP_MULT * cur_atr
            pnl = simulate_trade(bars, buy_entry_idx, entry_p, stop_p, "LONG")
            trades_by_pattern[(pattern, "BUY")].append(pnl)

        # Simulate SELL if it fired
        if sell_entry_idx is not None:
            entry_p = sell_stop
            stop_p = entry_p + ATR_STOP_MULT * cur_atr
            pnl = simulate_trade(bars, sell_entry_idx, entry_p, stop_p, "SHORT")
            trades_by_pattern[(pattern, "SELL")].append(pnl)

    # Report
    print(f"{'Pattern':<8s} {'B/S':<5s} {'n':>5s}  {'mean $':>10s}  {'WR':>6s}  "
          f"{'total $':>10s}  {'note':<20s}")
    print("-" * 75)
    # Order: focus on Crabel's high-edge patterns first
    priority = [("+-+","SELL"), ("+++","SELL"), ("-++","SELL"), ("+--","BUY"),
                ("+-+","BUY"),  ("+--","SELL"), ("++-","SELL"), ("--+","BUY"),
                ("---","BUY"),  ("---","SELL"), ("--+","SELL"), ("-+-","SELL"),
                ("-+-","BUY"),  ("-++","BUY"),  ("++-","BUY"),  ("+++","BUY")]
    printed = set()
    for pat, side in priority:
        key = (pat, side)
        if key not in trades_by_pattern:
            continue
        pnls = trades_by_pattern[key]
        n = len(pnls); total = sum(pnls); mean = total / n
        wins = sum(1 for p in pnls if p > 0)
        crabel_note = ""
        if (pat, side) == ("+-+", "SELL"): crabel_note = "Crabel 61% WR 1975-89"
        if (pat, side) == ("+++", "SELL"): crabel_note = "Crabel 53% WR"
        if (pat, side) == ("+--", "BUY"):  crabel_note = "Crabel 65% WR"
        if (pat, side) == ("-++", "SELL"): crabel_note = "Crabel 56% WR"
        print(f"  {pat:<6s} {side:<5s} {n:>5d}  ${mean:>+8,.2f}  "
              f"{100*wins/n:>4.1f}%  ${total:>+8,.0f}  {crabel_note}")
        printed.add(key)

    # Any remaining
    remaining = [k for k in trades_by_pattern if k not in printed]
    if remaining:
        print(f"  (also: {len(remaining)} other pattern×side combos, n small)")


if __name__ == "__main__":
    main()
