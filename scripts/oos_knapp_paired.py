"""OOS paired-lift test for Knapp ER-adaptive stops.

For a given 5m OHLCV CSV, generate ORB candidates using Path Y config, then for
each `would_take=True` entry, simulate outcome BOTH under:
  - baseline: stop_dist = or_range (Path Y default)
  - Knapp treatment: stop_dist = or_range * mod(ER, direction)

Where ER is Efficiency Ratio on 20 bars of 5m closes ending at OR close.
Modulation table (adapted from Knapp 2010 for ORB scaling):
  ER < 0.30:            LONG: 1.0    SHORT: 1.0
  0.30 <= ER < 0.60:    LONG: 0.9    SHORT: 0.5
  ER >= 0.60:           LONG: 0.8    SHORT: 0.9

Output: paired-lift summary + bootstrap 95% CI.

Usage:
  python scripts/oos_knapp_paired.py <path_to_5m_csv> [--label MARKET]
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Constants matching backfill_shadow_log.py
OR_BARS = 6  # 30-min OR on 5m
WATCH_BARS = 12  # 60-min watch for breakout
MAX_HOLD_BARS = 36  # 180-min max hold
ER_BARS = 20  # 100-min ER window
CONTRACT_SIZE = 100  # gold contract; approx for other markets
RT_COST = 24.0

# Session opens (UTC) — same as SESSIONS_LOCAL
SESSIONS_UTC = {
    "LON": 6,   # 07:00 London ~ 06:00 UTC in summer  (approx)
    "NY":  13,  # 08:30 NY ~ 13:30 UTC
    "ASIA": 22, # 00:00 Tokyo ~ 22:00 UTC prev day  (approx)
}


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


def knapp_mod(er: float, direction: str) -> float:
    """Multiplier applied to baseline stop_dist based on ER + direction."""
    if er < 0.30:
        return 1.0
    if er < 0.60:
        return 0.9 if direction == "LONG" else 0.5
    return 0.8 if direction == "LONG" else 0.9


def slope_5h(closes_1h: pd.Series) -> float:
    """EMA-50 slope over last 5 hours (matches fetch_higher_tf_trend approach)."""
    if len(closes_1h) < 55:
        return 0.0
    ema = closes_1h.ewm(span=50, adjust=False).mean()
    return float(ema.iloc[-1] - ema.iloc[-6])


def simulate_outcome(bars: pd.DataFrame, entry_idx: int, entry: float,
                     stop: float, target: float, direction: str) -> float:
    """Bar-by-bar simulation of outcome; returns net P&L (contract=100, cost=24)."""
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
            exit_price = stop  # conservative
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


def find_entries(bars: pd.DataFrame) -> list[dict]:
    """Return list of candidate dicts (session, or_high, or_low, or_range, direction, entry_idx, entry_price, er)."""
    bars_1h = bars["close"].resample("1h").last().dropna()
    entries: list[dict] = []
    days_seen = 0
    for date in sorted(set(bars.index.date)):
        days_seen += 1
        if pd.Timestamp(date).weekday() == 5:  # skip Saturday
            continue
        for sess_name, sess_hour in SESSIONS_UTC.items():
            open_ts = pd.Timestamp(date, tz="UTC") + pd.Timedelta(hours=sess_hour)
            or_close_ts = open_ts + pd.Timedelta(minutes=30)
            # Take first 6 bars from open_ts
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
            # 5m closes up to and including OR close for ER
            closes_5m_pre = bars[bars.index <= or_close_actual]["close"].values
            er = efficiency_ratio(closes_5m_pre)
            if er is None:
                continue
            # slope from 1h EMA-50 over 5h ending at or_close_actual
            closes_1h_pre = bars_1h[bars_1h.index <= or_close_actual]
            slope = slope_5h(closes_1h_pre)
            if slope == 0:
                continue
            direction = "LONG" if slope > 0 else "SHORT"

            # Find breakout within WATCH_BARS
            post_or_idx = bars.index.get_loc(or_close_actual) + 1
            entry_idx = None
            for k in range(WATCH_BARS):
                i = post_or_idx + k
                if i >= len(bars):
                    break
                b = bars.iloc[i]
                if direction == "LONG" and b["high"] >= or_high:
                    entry_idx = i
                    entry_price = or_high
                    break
                if direction == "SHORT" and b["low"] <= or_low:
                    entry_idx = i
                    entry_price = or_low
                    break
            if entry_idx is None:
                continue

            entries.append({
                "date": str(date),
                "session": sess_name,
                "or_high": or_high, "or_low": or_low, "or_range": or_range,
                "er": er,
                "direction": direction,
                "entry_idx": entry_idx,
                "entry_price": entry_price,
            })
    return entries


def bootstrap_ci(diffs: list[float], n: int = 2000) -> tuple[float, float]:
    if len(diffs) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(20260720)
    N = len(diffs)
    means = []
    for _ in range(n):
        sample = [diffs[rng.randrange(N)] for _ in range(N)]
        means.append(sum(sample) / N)
    means.sort()
    return (means[int(0.025 * n)], means[int(0.975 * n)])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("csv_path", help="Path to 5m OHLCV CSV")
    p.add_argument("--label", default=None, help="Market label for report")
    args = p.parse_args()

    label = args.label or Path(args.csv_path).stem
    print(f"=== {label} ===")
    bars = load_bars(args.csv_path)
    print(f"Loaded {len(bars):,} bars: {bars.index[0].date()} -> {bars.index[-1].date()}")

    entries = find_entries(bars)
    print(f"Found {len(entries):,} entries")
    if len(entries) < 30:
        print("insufficient entries for meaningful test")
        return

    baseline_pnls = []
    knapp_pnls = []
    diffs = []
    for e in entries:
        # Baseline: stop_dist = or_range
        stop_dist_base = e["or_range"]
        # Knapp: modulated
        stop_dist_knapp = e["or_range"] * knapp_mod(e["er"], e["direction"])
        # Target unchanged (tp_mult=1.0 * or_range as Path Y default)
        target_dist = e["or_range"]

        if e["direction"] == "LONG":
            stop_base = e["entry_price"] - stop_dist_base
            stop_knapp = e["entry_price"] - stop_dist_knapp
            target = e["entry_price"] + target_dist
        else:
            stop_base = e["entry_price"] + stop_dist_base
            stop_knapp = e["entry_price"] + stop_dist_knapp
            target = e["entry_price"] - target_dist

        pnl_base = simulate_outcome(bars, e["entry_idx"], e["entry_price"],
                                    stop_base, target, e["direction"])
        pnl_knapp = simulate_outcome(bars, e["entry_idx"], e["entry_price"],
                                     stop_knapp, target, e["direction"])
        baseline_pnls.append(pnl_base)
        knapp_pnls.append(pnl_knapp)
        diffs.append(pnl_knapp - pnl_base)

    total_base = sum(baseline_pnls)
    total_knapp = sum(knapp_pnls)
    mean_diff = np.mean(diffs)
    ci_lo, ci_hi = bootstrap_ci(diffs)

    print(f"\nn                        = {len(entries)}")
    print(f"Total P&L (baseline)     = ${total_base:+,.0f}")
    print(f"Total P&L (Knapp)        = ${total_knapp:+,.0f}")
    print(f"Total lift               = ${total_knapp - total_base:+,.0f}")
    print(f"Mean paired lift         = ${mean_diff:+,.2f}/trade")
    print(f"Bootstrap 95% CI on mean = [${ci_lo:+,.2f}, ${ci_hi:+,.2f}]")

    # Direction-partitioned
    longs = [d for e, d in zip(entries, diffs) if e["direction"] == "LONG"]
    shorts = [d for e, d in zip(entries, diffs) if e["direction"] == "SHORT"]
    if longs:
        print(f"  LONG  n={len(longs)}  mean_diff=${np.mean(longs):+,.2f}/trade")
    if shorts:
        print(f"  SHORT n={len(shorts)} mean_diff=${np.mean(shorts):+,.2f}/trade")

    # ER-band partitioned
    for band_name, band_lo, band_hi in [("ER<0.30", 0, 0.30), ("0.30-0.60", 0.30, 0.60), ("ER>=0.60", 0.60, 1.01)]:
        band = [d for e, d in zip(entries, diffs) if band_lo <= e["er"] < band_hi]
        if band:
            print(f"  {band_name:12s} n={len(band):3d}  mean_diff=${np.mean(band):+,.2f}/trade")


if __name__ == "__main__":
    main()
