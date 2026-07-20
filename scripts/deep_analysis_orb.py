"""Deep analysis of ORB entries on any 5m market — fade-test + segmentation.

For a given 5m OHLCV CSV, generate ORB candidates using Path Y logic. For each
`would_take=True` entry, simulate outcome under:

  - forward  (buy the breakout, Path Y baseline)
  - fade     (invert direction — SHORT the LONG breakouts, LONG the SHORT breakouts)

Then partition results across many dimensions:
  - Session (LON/NY/ASIA)
  - Direction (LONG/SHORT)
  - ER band (low/mid/high)
  - OR/ATR ratio (compressed/normal/expanded)
  - Time-of-day UTC (rounded to hour)
  - Day-of-week

Report per-segment: n, win_rate, mean_pnl, total_pnl.

Also emit CSV of raw trades for downstream ML.

Usage:
  python scripts/deep_analysis_orb.py <path_to_5m_csv> [--label MARKET] [--out trades.csv]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OR_BARS = 6
WATCH_BARS = 12
MAX_HOLD_BARS = 36
ER_BARS = 20
ATR_BARS = 20
CONTRACT_SIZE = 100
RT_COST = 24.0

SESSIONS_UTC = {"LON": 6, "NY": 13, "ASIA": 22}


def load_bars(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df


def efficiency_ratio(closes: np.ndarray, n: int = ER_BARS) -> float | None:
    if len(closes) < n + 1:
        return None
    seg = closes[-(n + 1):]
    numer = abs(seg[-1] - seg[0])
    denom = np.sum(np.abs(np.diff(seg)))
    if denom == 0:
        return None
    return float(numer / denom)


def atr_at(bars: pd.DataFrame, up_to_idx: int, n: int = ATR_BARS) -> float | None:
    if up_to_idx < n:
        return None
    seg = bars.iloc[up_to_idx - n:up_to_idx]
    tr = pd.concat([
        seg["high"] - seg["low"],
        (seg["high"] - seg["close"].shift()).abs(),
        (seg["low"] - seg["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return float(tr.mean())


def slope_5h(closes_1h: pd.Series) -> float:
    if len(closes_1h) < 55:
        return 0.0
    ema = closes_1h.ewm(span=50, adjust=False).mean()
    return float(ema.iloc[-1] - ema.iloc[-6])


def simulate(bars: pd.DataFrame, entry_idx: int, entry: float,
             stop: float, target: float, direction: str) -> float:
    dir_sign = 1 if direction == "LONG" else -1
    exit_price = None
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
            exit_price = stop
            break
        if hit_stop:
            exit_price = stop
            break
        if hit_tp:
            exit_price = target
            break
    if exit_price is None:
        end_idx = min(entry_idx + MAX_HOLD_BARS, len(bars) - 1)
        exit_price = float(bars.iloc[end_idx]["close"])
    gross = (exit_price - entry) * dir_sign * CONTRACT_SIZE
    return gross - RT_COST


def find_and_simulate(bars: pd.DataFrame) -> list[dict]:
    bars_1h = bars["close"].resample("1h").last().dropna()
    trades: list[dict] = []
    for date in sorted(set(bars.index.date)):
        if pd.Timestamp(date).weekday() == 5:
            continue
        for sess_name, sess_hour in SESSIONS_UTC.items():
            open_ts = pd.Timestamp(date, tz="UTC") + pd.Timedelta(hours=sess_hour)
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

            closes_5m_pre = bars.iloc[:or_close_idx + 1]["close"].values
            er = efficiency_ratio(closes_5m_pre)
            if er is None:
                continue
            cur_atr = atr_at(bars, or_close_idx + 1)
            if cur_atr is None or cur_atr <= 0:
                continue
            closes_1h_pre = bars_1h[bars_1h.index <= or_close_actual]
            slope = slope_5h(closes_1h_pre)
            if slope == 0:
                continue
            direction_fwd = "LONG" if slope > 0 else "SHORT"

            entry_idx = None
            for k in range(WATCH_BARS):
                i = or_close_idx + 1 + k
                if i >= len(bars):
                    break
                b = bars.iloc[i]
                if direction_fwd == "LONG" and b["high"] >= or_high:
                    entry_idx = i
                    entry_price = or_high
                    break
                if direction_fwd == "SHORT" and b["low"] <= or_low:
                    entry_idx = i
                    entry_price = or_low
                    break
            if entry_idx is None:
                continue

            stop_dist = or_range
            target_dist = or_range

            # FORWARD: Path Y direction
            if direction_fwd == "LONG":
                stop_fwd = entry_price - stop_dist
                target_fwd = entry_price + target_dist
            else:
                stop_fwd = entry_price + stop_dist
                target_fwd = entry_price - target_dist
            pnl_fwd = simulate(bars, entry_idx, entry_price, stop_fwd, target_fwd, direction_fwd)

            # FADE: opposite direction, same entry price
            direction_fade = "SHORT" if direction_fwd == "LONG" else "LONG"
            if direction_fade == "LONG":
                stop_fade = entry_price - stop_dist
                target_fade = entry_price + target_dist
            else:
                stop_fade = entry_price + stop_dist
                target_fade = entry_price - target_dist
            pnl_fade = simulate(bars, entry_idx, entry_price, stop_fade, target_fade, direction_fade)

            trades.append({
                "date": str(date),
                "hour_utc": bars.index[entry_idx].hour,
                "dow": pd.Timestamp(date).day_name()[:3],
                "session": sess_name,
                "direction_fwd": direction_fwd,
                "or_range": or_range,
                "atr": cur_atr,
                "or_atr_ratio": or_range / cur_atr,
                "er": er,
                "pnl_forward": pnl_fwd,
                "pnl_fade": pnl_fade,
            })
    return trades


def summarize(trades: list[dict], key: str, side: str = "forward") -> None:
    """Print per-segment stats grouped by key. side = 'forward' or 'fade'."""
    df = pd.DataFrame(trades)
    if df.empty:
        print("no trades")
        return
    pnl_col = f"pnl_{side}"
    grp = df.groupby(key)[pnl_col].agg(["count", "mean", "sum", lambda x: (x > 0).mean()])
    grp.columns = ["n", "mean_pnl", "total_pnl", "win_rate"]
    grp = grp.reset_index().sort_values("total_pnl", ascending=False)
    print(f"  {'segment':16s}  {'n':>4s}  {'win_rate':>8s}  {'mean/trade':>11s}  {'total':>10s}")
    for _, row in grp.iterrows():
        print(f"  {str(row[key]):16s}  {int(row['n']):>4d}  "
              f"{100*row['win_rate']:>7.1f}%  ${row['mean_pnl']:>+10.2f}  ${row['total_pnl']:>+9,.0f}")


def er_band(er: float) -> str:
    if er < 0.30: return "low"
    if er < 0.60: return "mid"
    return "high"


def or_atr_band(r: float) -> str:
    if r < 0.5: return "compressed"
    if r < 1.5: return "normal"
    return "expanded"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("csv_path")
    p.add_argument("--label", default=None)
    p.add_argument("--out", default=None, help="Write raw trades CSV")
    args = p.parse_args()

    label = args.label or Path(args.csv_path).stem
    print(f"\n=========== {label} ===========\n")

    bars = load_bars(args.csv_path)
    print(f"Loaded {len(bars):,} bars: {bars.index[0].date()} -> {bars.index[-1].date()}")

    trades = find_and_simulate(bars)
    if not trades:
        print("no entries found")
        return

    for t in trades:
        t["er_band"] = er_band(t["er"])
        t["or_atr_band"] = or_atr_band(t["or_atr_ratio"])

    df = pd.DataFrame(trades)
    if args.out:
        df.to_csv(args.out, index=False)
        print(f"Wrote {len(df)} rows to {args.out}\n")

    # Overall
    print(f"n = {len(df)}")
    print(f"FORWARD (Path Y):  total ${df['pnl_forward'].sum():+,.0f}  mean ${df['pnl_forward'].mean():+.2f}/trade  win {100*(df['pnl_forward']>0).mean():.1f}%")
    print(f"FADE  (invert):    total ${df['pnl_fade'].sum():+,.0f}  mean ${df['pnl_fade'].mean():+.2f}/trade  win {100*(df['pnl_fade']>0).mean():.1f}%")

    # Segmentation on FORWARD side
    for key in ["session", "direction_fwd", "er_band", "or_atr_band", "dow"]:
        print(f"\n--- FORWARD by {key} ---")
        summarize(trades, key, "forward")

    # Segmentation on FADE side
    for key in ["session", "direction_fwd", "er_band", "or_atr_band", "dow"]:
        print(f"\n--- FADE by {key} ---")
        summarize(trades, key, "fade")

    # Session × Direction cross-tab (forward)
    print("\n--- FORWARD: session × direction ---")
    ct = df.pivot_table(index="session", columns="direction_fwd", values="pnl_forward",
                         aggfunc=["count", "mean", "sum"])
    print(ct)


if __name__ == "__main__":
    main()
