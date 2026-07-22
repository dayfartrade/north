"""FX fade test — is NY-LONG-Low-ER-Mon-Wed a mirror edge on dollar-smile FX?

Path Z (NY-SHORT-Low-ER-Mon-Wed) fails on EUR/GBP/JPY. Question: does the
opposite direction (NY-LONG under same regime filter) show a positive edge
on those markets? If yes, we may have a market-conditioned parallel v9
candidate — Path Z on gold, Path Z-inverse on FX.

Approach: replicate Path Z filter (session=NY, ER_5m_20<0.30, Mon-Wed) but
force direction=LONG regardless of slope sign. Simulate under same
NY-Z config (no or_atr cap, 1xOR stop, 1.5xOR target).

Rules to catch: same filter, but direction determined by test not by slope.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mers_v3_peb import compute_atr
from regime_context import _efficiency_ratio

MARKET_SPECS = {
    "XAUUSD": {"contract_size": 100,    "rt_cost": 24.0},
    "XAGUSD": {"contract_size": 5000,   "rt_cost": 16.0},
    "EURUSD": {"contract_size": 100000, "rt_cost": 7.0},
    "GBPUSD": {"contract_size": 100000, "rt_cost": 7.0},
    "USDJPY": {"contract_size": 100000, "rt_cost": 7.0},
}

OR_BARS = 6
WATCH_BARS = 12
MAX_HOLD_BARS = 36
NY_SESSION_HOUR_UTC = 13
ER_LOOKBACK = 20
TP_MULT = 1.5
ER_MAX = 0.30
DOW_ALLOW = {0, 1, 2}  # Mon Tue Wed


def load_bars(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


def simulate(bars: pd.DataFrame, entry_idx: int, entry: float,
             stop: float, target: float, direction: str,
             contract_size: float, rt_cost: float) -> float:
    dir_sign = 1 if direction == "LONG" else -1
    for k in range(MAX_HOLD_BARS + 1):
        if entry_idx + k >= len(bars):
            break
        b = bars.iloc[entry_idx + k]
        if direction == "LONG":
            hit_stop = b["low"] <= stop
            hit_tp = b["high"] >= target
        else:
            hit_stop = b["high"] >= stop
            hit_tp = b["low"] <= target
        if hit_stop and hit_tp:
            exit_price = stop; break
        if hit_stop:
            exit_price = stop; break
        if hit_tp:
            exit_price = target; break
    else:
        end_idx = min(entry_idx + MAX_HOLD_BARS, len(bars) - 1)
        exit_price = float(bars.iloc[end_idx]["close"])
    return (exit_price - entry) * dir_sign * contract_size - rt_cost


def run(symbol: str, direction: str) -> None:
    spec = MARKET_SPECS[symbol]
    csv_path = ROOT / "data" / "external" / "dukascopy" / f"{symbol}_5m.csv"
    bars = load_bars(csv_path)
    atr = compute_atr(bars, 20)

    pnls = []
    for date in sorted(set(bars.index.date)):
        d = pd.Timestamp(date, tz="UTC")
        if d.weekday() not in DOW_ALLOW:
            continue
        open_ts = d + pd.Timedelta(hours=NY_SESSION_HOUR_UTC)
        or_close_ts = open_ts + pd.Timedelta(minutes=30)
        or_slice = bars[(bars.index >= open_ts) & (bars.index < or_close_ts)]
        if len(or_slice) < OR_BARS:
            continue
        or_slice = or_slice.iloc[:OR_BARS]
        or_high = float(or_slice["high"].max())
        or_low = float(or_slice["low"].min())
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        or_close_actual = or_slice.index[-1]
        or_close_idx = bars.index.get_loc(or_close_actual)
        cur_atr = float(atr.iloc[or_close_idx])
        if cur_atr <= 0:
            continue

        # ER filter
        closes = bars.iloc[max(0, or_close_idx - 20): or_close_idx + 1]["close"].tolist()
        er = _efficiency_ratio(closes, n=20)
        if er >= ER_MAX:
            continue

        # Geometry
        if direction == "LONG":
            entry = or_high
            target = entry + TP_MULT * or_range
            stop = entry - or_range
        else:  # SHORT
            entry = or_low
            target = entry - TP_MULT * or_range
            stop = entry + or_range

        # Find breakout in watch window
        entry_idx = None
        for k in range(WATCH_BARS):
            i = or_close_idx + 1 + k
            if i >= len(bars):
                break
            b = bars.iloc[i]
            if direction == "LONG" and b["high"] >= entry:
                entry_idx = i; break
            if direction == "SHORT" and b["low"] <= entry:
                entry_idx = i; break
        if entry_idx is None:
            continue

        pnl = simulate(bars, entry_idx, entry, stop, target, direction,
                       spec["contract_size"], spec["rt_cost"])
        risk = or_range * spec["contract_size"]
        pnls.append((pnl, pnl / risk if risk > 0 else 0.0))

    if not pnls:
        print(f"{symbol:8s} {direction:5s}  no trades matched filter")
        return
    dollars = [p for p, _ in pnls]
    rs = [r for _, r in pnls]
    n = len(pnls)
    total = sum(dollars)
    mean = total / n
    wins = sum(1 for p in dollars if p > 0)
    r_mean = sum(rs) / n
    print(f"{symbol:8s} {direction:5s}  n={n:>3d}  mean=${mean:>+9,.2f}  "
          f"WR={100*wins/n:>4.1f}%  R_mean={r_mean:>+.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", choices=list(MARKET_SPECS), default=None,
                    help="run one symbol; default runs all")
    args = ap.parse_args()

    symbols = [args.symbol] if args.symbol else list(MARKET_SPECS)
    print("Filter: NY session, ER_5m_20 < 0.30, Mon/Tue/Wed only")
    print("Config: 1xOR stop, 1.5xOR target, forced direction")
    print()
    print(f"{'SYMBOL':<8s} {'DIR':<5s}  {'STATS':<40s}")
    print("-" * 60)
    for sym in symbols:
        run(sym, "SHORT")
        run(sym, "LONG")
        print()


if __name__ == "__main__":
    main()
