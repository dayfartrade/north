"""Walk-forward + permutation-null validation for the current shipped strategy.

Complements the single-split Phase 7 gate (`scripts/validate_v7_phase7.py`)
by verifying the edge holds across MULTIPLE rolling windows AND beats a
random-shuffle null distribution.

Motivation: after a session of hypothesis testing, single 80/20 OOS pass
alone doesn't rule out Type-I error. Walk-forward + permutation gives
a real p-value.

Run:
    python scripts/walk_forward_validation.py
    python scripts/walk_forward_validation.py --n-boot 2000
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
from datetime import datetime
import pytz


def run_full_backtest():
    from data_gc import load as gc_load
    from edge_session_orb import session_utc_time_on
    from edge_session_orb_v7_final import run_orb_v7, SESSION_CONFIG
    bars = gc_load('5m').sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize('UTC')
    frames = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        df['session'] = sess_name
        if not df.empty:
            frames.append(df)
    took = pd.concat(frames, ignore_index=True)
    took = took[took['took_trade'] == True].copy()
    took['entry_ts'] = pd.to_datetime(took['entry_ts'], utc=True)
    return took.sort_values('entry_ts').reset_index(drop=True)


def walk_forward(took, train_size=20, test_size=10, step=5):
    """Return list of (train_slice, test_slice) DataFrames."""
    windows = []
    for start in range(0, len(took) - train_size - test_size + 1, step):
        train = took.iloc[start:start + train_size]
        test = took.iloc[start + train_size:start + train_size + test_size]
        windows.append((train, test))
    return windows


def evaluate(df):
    if len(df) == 0:
        return None
    pnl = df['net_pnl'].to_numpy()
    return {
        'n': len(pnl),
        'win_pct': (pnl > 0).mean() * 100,
        'mean': pnl.mean(),
        'total': pnl.sum(),
    }


def permutation_null_p_value(took, train_size, test_size, step, n_boot=500, seed=20260707):
    """Shuffle net_pnl labels and re-run walk-forward. Return distribution of
    average test-mean across N bootstraps, and the p-value that actual >= null."""
    rng = np.random.default_rng(seed)
    pnl = took['net_pnl'].to_numpy()
    dist = []
    for _ in range(n_boot):
        shuffled = rng.permutation(pnl)
        test_means = []
        for start in range(0, len(shuffled) - train_size - test_size + 1, step):
            test_slice = shuffled[start + train_size:start + train_size + test_size]
            test_means.append(test_slice.mean())
        dist.append(np.mean(test_means))
    return np.array(dist)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-size", type=int, default=20)
    parser.add_argument("--test-size", type=int, default=10)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--n-boot", type=int, default=500)
    args = parser.parse_args()

    print("=" * 78)
    print("Walk-forward + permutation-null validation")
    print("=" * 78)

    took = run_full_backtest()
    print(f"Total trades: {len(took)}")
    print(f"Window: {took['entry_ts'].min().date()} to {took['entry_ts'].max().date()}")

    windows = walk_forward(took, args.train_size, args.test_size, args.step)
    if len(windows) < 3:
        print(f"\nOnly {len(windows)} walk-forward windows possible with train={args.train_size}, "
              f"test={args.test_size}. Need more trades.")
        return 1

    print(f"\nWalk-forward: train={args.train_size}, test={args.test_size}, step={args.step}, "
          f"{len(windows)} windows")
    print("-" * 78)
    print(f"{'#':>2} {'train dates':>22} {'train n':>8} {'train w%':>9} "
          f"{'test dates':>22} {'test w%':>8} {'test $':>10}")

    test_means = []
    test_wins = []
    for i, (train, test) in enumerate(windows):
        tr = evaluate(train); te = evaluate(test)
        if tr and te:
            test_means.append(te['mean'])
            test_wins.append(te['win_pct'])
            print(f"{i:>2} "
                  f"{train['entry_ts'].min().date()} to {train['entry_ts'].max().date()} "
                  f"{tr['n']:>4} {tr['win_pct']:>7.1f}% "
                  f"{test['entry_ts'].min().date()} to {test['entry_ts'].max().date()} "
                  f"{te['win_pct']:>6.1f}% ${te['mean']:>+7.0f}")

    print("\n== Aggregate ==")
    print(f"  Test win rates:  min={min(test_wins):>4.0f}%  median={np.median(test_wins):>4.0f}%  "
          f"mean={np.mean(test_wins):>4.1f}%  max={max(test_wins):>4.0f}%")
    print(f"  Test mean/trade: min=${min(test_means):>+5.0f}  mean=${np.mean(test_means):>+5.0f}  "
          f"max=${max(test_means):>+5.0f}")
    print(f"  Windows with test mean > 0:  {sum(1 for m in test_means if m > 0)}/{len(test_means)}")
    print(f"  Windows with test win% >= 60: {sum(1 for w in test_wins if w >= 60)}/{len(test_wins)}")

    print(f"\n== Permutation-null p-value (n_boot={args.n_boot}) ==")
    null = permutation_null_p_value(took, args.train_size, args.test_size, args.step,
                                     n_boot=args.n_boot)
    actual = np.mean(test_means)
    p_value = (null >= actual).mean()
    print(f"  Actual avg test mean:   ${actual:+.0f}")
    print(f"  Null distribution: p5=${np.percentile(null,5):+.0f}, "
          f"p50=${np.percentile(null,50):+.0f}, p95=${np.percentile(null,95):+.0f}")
    print(f"  p-value:                {p_value:.4f}")
    print()
    if p_value < 0.01:
        print("  VERDICT: SIGNAL HIGHLY SIGNIFICANT (p < 0.01)")
    elif p_value < 0.05:
        print("  VERDICT: SIGNAL SIGNIFICANT (p < 0.05) — safe to ship")
    elif p_value < 0.10:
        print("  VERDICT: MARGINAL (0.05 <= p < 0.10) — hold for more data")
    else:
        print("  VERDICT: NOT SIGNIFICANT (p >= 0.10) — do not ship")

    return 0 if p_value < 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
