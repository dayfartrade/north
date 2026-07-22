"""Meyers Adaptive Intraday Breakout System — gold feasibility test.

Kaufman Ch 17 p.796 (Dennis Meyers, "Range Roving", Active Trader March 2003).

Signal:
  HR_t = H_t - L_{t-n}    (today's high vs low of bar n ago; asymmetric)
  LR_t = L_t - H_{t-n}
  NHR = HR / (n^a * ATR(n))
  NLR = LR / (n^a * ATR(n))
  HR_max = rolling max NHR over last n bars
  LR_max = rolling max NLR over last n bars

  BUY  when HR_max > threshold_high AND LR_max < threshold_low
  SELL when LR_max > threshold_high AND HR_max < threshold_low

Kaufman's QQQ-fit defaults: n=6, a=0.75, threshold_high=0.50, threshold_low=1.05.
Adapting to gold 5m — 6-bar lookback = 30 min (matches Path Z's OR window).

Position management (Meyers' book rule was "exit 5 min before market close"
which doesn't fit 24/5 gold; adapting to MAX_HOLD_BARS + optional 2xATR stop):
  - Entry at close of signal bar
  - Exit at whichever comes first:
    (a) MAX_HOLD_BARS (default 24 bars = 2h)
    (b) 2xATR stop from entry
    (c) opposite signal fires
  - No re-entry while position open

Goal: does the ASYMMETRIC-RANGE framework carry any edge on XAUUSD? If yes,
proceed to formal pre-reg. If not, retire candidate. This is exploratory — no
pre-reg yet.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mers_v3_peb import compute_atr

CONTRACT_SIZE = 100
RT_COST = 24.0


def load_bars(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()


def simulate(bars: pd.DataFrame, n: int, a: float,
             threshold_high: float, threshold_low: float,
             max_hold_bars: int = 24, atr_stop_mult: float = 2.0,
             verbose: bool = False) -> dict:
    """Walk bars, generate Meyers signals, simulate P&L."""
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()
    atr = compute_atr(bars, n).to_numpy()

    n_bars = len(bars)
    # Precompute HR, LR arrays
    hr = [0.0] * n_bars
    lr = [0.0] * n_bars
    nhr = [0.0] * n_bars
    nlr = [0.0] * n_bars
    factor = (n ** a)
    for t in range(n, n_bars):
        hr[t] = highs[t] - lows[t - n]
        lr[t] = lows[t] - highs[t - n]  # can be negative or positive
        # LR is defined as L - H_prev; when uptrend, LR is negative (low is above prev high)
        # For "big down move", we want LR to be very negative → use -LR as the "down range"
        # But per book: NLR = LR / (n^a * ATR), then LR_max = highest(NLR, n)
        # This means we're looking at max VALUE of LR, which is the LEAST negative (or most positive).
        # Re-reading: "L_t - H_{t-n}" — this is negative when today's low is BELOW n-bars-ago high
        # (normal). The LARGER (less negative or positive) it is, the WEAKER the downside.
        # Then Buy requires HR_max > 0.5 AND LR_max < 1.05.
        # Hmm — LR_max < 1.05 with LR being usually negative, is almost always true.
        # This suggests the original convention is that LR is measured as a MAGNITUDE.
        # Simpler interpretation: |negative range| — take abs of the downward move.
        # Following the book literally as HR positive for up, LR positive for down:
        # LR_t = H_{t-n} - L_t   (positive when today's low is below n-bars-ago high — normal downmove)
        # HR_t = H_t - L_{t-n}   (positive when today's high is above n-bars-ago low — upmove)
        # This makes NHR and NLR both positive magnitudes.
        # Overriding the book's LR sign (it appears to have a typo):
        lr[t] = highs[t - n] - lows[t]  # positive magnitude of downward range
        if atr[t] > 0:
            nhr[t] = hr[t] / (factor * atr[t])
            nlr[t] = lr[t] / (factor * atr[t])

    # Rolling max
    hr_max = [0.0] * n_bars
    lr_max = [0.0] * n_bars
    for t in range(n, n_bars):
        lo = max(0, t - n + 1)
        hr_max[t] = max(nhr[lo:t + 1])
        lr_max[t] = max(nlr[lo:t + 1])

    # Walk and simulate
    position = None  # (direction, entry_idx, entry_price, stop_price)
    pnls = []
    signals_ignored = 0

    for t in range(n * 2, n_bars):
        # Manage open position first
        if position is not None:
            direction, entry_idx, entry_price, stop_price = position
            bars_held = t - entry_idx
            b = bars.iloc[t]
            if direction == "LONG":
                stopped = float(b["low"]) <= stop_price
            else:
                stopped = float(b["high"]) >= stop_price

            timed_out = bars_held >= max_hold_bars

            # Opposite signal? Check for exit
            hr_ok_buy = hr_max[t] > threshold_high and lr_max[t] < threshold_low
            lr_ok_sell = lr_max[t] > threshold_high and hr_max[t] < threshold_low
            opposite_fired = ((direction == "LONG" and lr_ok_sell) or
                              (direction == "SHORT" and hr_ok_buy))

            if stopped or timed_out or opposite_fired:
                exit_price = stop_price if stopped else float(b["close"])
                dir_sign = 1 if direction == "LONG" else -1
                gross = (exit_price - entry_price) * dir_sign * CONTRACT_SIZE
                net = gross - RT_COST
                pnls.append(net)
                if verbose and len(pnls) <= 5:
                    print(f"  {bars.index[entry_idx].isoformat()} {direction} "
                          f"entry={entry_price:.2f} exit={exit_price:.2f} "
                          f"held={bars_held}bars net=${net:+.2f}")
                position = None
                # If opposite signal, can re-enter this bar
                if opposite_fired:
                    new_dir = "SHORT" if direction == "LONG" else "LONG"
                    entry = float(b["close"])
                    dir_sign_new = 1 if new_dir == "LONG" else -1
                    stop_dist = atr_stop_mult * atr[t]
                    stop_price_new = entry - dir_sign_new * stop_dist
                    position = (new_dir, t, entry, stop_price_new)
                continue

        # No open position — check for entry signal
        if position is None:
            buy_signal = hr_max[t] > threshold_high and lr_max[t] < threshold_low
            sell_signal = lr_max[t] > threshold_high and hr_max[t] < threshold_low
            if buy_signal and not sell_signal:
                entry = float(bars.iloc[t]["close"])
                stop_dist = atr_stop_mult * atr[t]
                position = ("LONG", t, entry, entry - stop_dist)
            elif sell_signal and not buy_signal:
                entry = float(bars.iloc[t]["close"])
                stop_dist = atr_stop_mult * atr[t]
                position = ("SHORT", t, entry, entry + stop_dist)
            elif buy_signal and sell_signal:
                signals_ignored += 1  # both fire — ambiguous

    if position is not None:
        # Force-close final position at last bar close
        direction, entry_idx, entry_price, _ = position
        exit_price = float(bars.iloc[-1]["close"])
        dir_sign = 1 if direction == "LONG" else -1
        gross = (exit_price - entry_price) * dir_sign * CONTRACT_SIZE
        pnls.append(gross - RT_COST)

    return {
        "n_trades": len(pnls),
        "pnls": pnls,
        "signals_ignored": signals_ignored,
    }


def report(label: str, result: dict) -> None:
    pnls = result["pnls"]
    n = result["n_trades"]
    if n == 0:
        print(f"  {label:35s}  NO TRADES")
        return
    total = sum(pnls)
    mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    med = sorted(pnls)[n // 2]
    print(f"  {label:35s}  n={n:>4d}  total=${total:>+9,.0f}  mean=${mean:>+7,.2f}  "
          f"WR={100*wins/n:>4.1f}%  med=${med:>+7,.0f}  amb={result['signals_ignored']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--a", type=float, default=0.75)
    ap.add_argument("--thigh", type=float, default=0.50)
    ap.add_argument("--tlow", type=float, default=1.05)
    ap.add_argument("--max-hold", type=int, default=24)
    ap.add_argument("--atr-stop", type=float, default=2.0)
    ap.add_argument("--sweep", action="store_true",
                    help="run a small param sweep")
    args = ap.parse_args()

    csv_path = ROOT / "data" / "external" / "dukascopy" / f"{args.symbol}_5m.csv"
    print(f"Loading {csv_path.name}...")
    bars = load_bars(csv_path)
    print(f"  {len(bars):,} bars {bars.index[0].date()} -> {bars.index[-1].date()}\n")

    if not args.sweep:
        print(f"Meyers HR-ORB feasibility: n={args.n} a={args.a} "
              f"thigh={args.thigh} tlow={args.tlow} max_hold={args.max_hold}b "
              f"atr_stop={args.atr_stop}x")
        r = simulate(bars, args.n, args.a, args.thigh, args.tlow,
                     args.max_hold, args.atr_stop, verbose=True)
        report(f"{args.symbol} default", r)
        return

    print("Param sweep on {}".format(args.symbol))
    print(f"  Baseline (Kaufman QQQ defaults): n=6 a=0.75 thigh=0.50 tlow=1.05\n")

    configs = [
        # (n, a, thigh, tlow, max_hold, label)
        (6,  0.75, 0.50, 1.05, 24, "n=6 QQQ defaults (24b hold)"),
        (6,  0.75, 0.50, 1.05, 12, "n=6 QQQ defaults (12b hold)"),
        (6,  0.75, 0.75, 1.05, 24, "n=6 higher thigh=0.75"),
        (6,  0.75, 1.00, 1.50, 24, "n=6 stricter thresholds"),
        (12, 0.75, 0.50, 1.05, 24, "n=12 (1h lookback)"),
        (24, 0.75, 0.50, 1.05, 36, "n=24 (2h lookback)"),
        (6,  1.00, 0.50, 1.05, 24, "n=6 a=1.0 (linear norm)"),
    ]
    for cfg in configs:
        n, a, thigh, tlow, max_hold, label = cfg
        r = simulate(bars, n, a, thigh, tlow, max_hold, 2.0)
        report(label, r)


if __name__ == "__main__":
    main()
