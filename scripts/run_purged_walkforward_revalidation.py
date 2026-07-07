"""Pre-registered experiment: purged_walkforward_revalidation

Adapts LdP Ch 7.4 Purged K-Fold to our slice-based backtest to check
whether v7.2.1's earlier walk-forward result holds under proper CV
methodology (embargo + purging).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
from datetime import datetime
import pytz

from data_gc import load as gc_load
from edge_session_orb import session_utc_time_on
from edge_session_orb_v7_final import run_orb_v7, SESSION_CONFIG
from deflated_sharpe import sr_stats, probabilistic_sharpe


def collect_trades():
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
    took['exit_ts'] = pd.to_datetime(took['exit_ts'], utc=True)
    return took.sort_values('entry_ts').reset_index(drop=True)


def purged_kfold_indices(n_samples: int, k: int, embargo_pct: float):
    """Yield (train_idx, test_idx) for each of k folds.
    Purge: remove training samples whose exit_ts overlaps test window.
      For non-overlapping session trades this is a no-op.
    Embargo: remove training samples in the `embargo_pct * n_samples` slots
      immediately AFTER the test window (defeats serial correlation).
    """
    fold_size = n_samples // k
    embargo = max(1, int(round(embargo_pct * n_samples)))
    for i in range(k):
        test_start = i * fold_size
        test_end = (i + 1) * fold_size if i < k - 1 else n_samples
        test_idx = np.arange(test_start, test_end)
        train_idx = np.concatenate([
            np.arange(0, test_start),
            np.arange(min(test_end + embargo, n_samples), n_samples),
        ])
        yield train_idx, test_idx


def main():
    print("=" * 78)
    print("PRE-REGISTERED VALIDATION: purged_walkforward_revalidation")
    print("Pre-reg: docs/experiments/2026-07-07_purged_walkforward_revalidation.md")
    print("=" * 78)

    trades = collect_trades()
    print(f"v7.2.1 trades: n={len(trades)}")

    K = 5
    EMBARGO = 0.01
    print(f"Purged K-Fold: k={K}, embargo={EMBARGO} ({int(len(trades)*EMBARGO)} trades between test and next train)")

    fold_results = []
    all_test_pnl = []
    for i, (train_idx, test_idx) in enumerate(purged_kfold_indices(len(trades), K, EMBARGO)):
        train_pnl = trades.iloc[train_idx]['net_pnl'].to_numpy()
        test_pnl = trades.iloc[test_idx]['net_pnl'].to_numpy()
        all_test_pnl.extend(test_pnl.tolist())
        w_test = (test_pnl > 0).mean() * 100 if len(test_pnl) else 0
        fold_results.append({
            'fold': i,
            'n_train': len(train_idx),
            'n_test': len(test_idx),
            'test_win_pct': w_test,
            'test_mean': test_pnl.mean() if len(test_pnl) else 0.0,
            'test_total': test_pnl.sum() if len(test_pnl) else 0.0,
        })

    print(f"\n{'Fold':>4} {'n_train':>8} {'n_test':>7} {'test_win%':>10} {'test_mean$':>12} {'test_total$':>12}")
    print("-" * 62)
    for r in fold_results:
        print(f"{r['fold']:>4} {r['n_train']:>8} {r['n_test']:>7} "
              f"{r['test_win_pct']:>9.1f}% ${r['test_mean']:>+10.0f} ${r['test_total']:>+10.0f}")

    positive_folds = sum(1 for r in fold_results if r['test_mean'] > 0)
    median_win = float(np.median([r['test_win_pct'] for r in fold_results]))

    # Aggregate permutation p-value on pooled test PnL
    all_test_pnl = np.array(all_test_pnl)
    rng = np.random.default_rng(20260707)
    n_perm = 10000
    obs_mean = all_test_pnl.mean()
    signs = rng.choice([-1, 1], size=(n_perm, len(all_test_pnl)))
    perm_means = (signs * all_test_pnl[None, :]).mean(axis=1)
    p_value = (np.abs(perm_means) >= abs(obs_mean)).mean()

    # DSR on pooled test set (no annualization, just per-trade)
    s = sr_stats(all_test_pnl)
    dsr_partial = probabilistic_sharpe(s, benchmark_sr=0.0)  # PSR against 0 as partial-credit

    print("\n" + "=" * 78)
    print("DECISION RULE EVALUATION")
    print("=" * 78)
    g1 = positive_folds >= 4
    g2 = median_win >= 60.0
    g3 = p_value < 0.05
    g4 = dsr_partial > 0.50

    print(f"  Gate 1: >= 4 of 5 folds positive-mean  ->  {positive_folds}/5  {'PASS' if g1 else 'FAIL'}")
    print(f"  Gate 2: median fold test-win% >= 60    ->  {median_win:.1f}%  {'PASS' if g2 else 'FAIL'}")
    print(f"  Gate 3: aggregate permutation p<0.05   ->  p={p_value:.4f}  {'PASS' if g3 else 'FAIL'}")
    print(f"  Gate 4: PSR on pooled tests > 0.50     ->  {dsr_partial:.4f}  {'PASS' if g4 else 'FAIL'}")

    if g1 and g2 and g3 and g4:
        verdict = "RE-VALIDATED"
    elif positive_folds <= 2 and p_value > 0.20:
        verdict = "LEAKAGE-FLAGGED"
    else:
        verdict = "INCONCLUSIVE"
    print(f"\n  VERDICT: {verdict}")

    print("\n" + "=" * 78)
    print("Copy to Results section of pre-reg file:")
    print("=" * 78)
    print(f"""
- **Ran on:** 2026-07-07
- **Sample size per fold:** train ~{fold_results[2]['n_train']} test ~{fold_results[2]['n_test']}
- **Fold-level positive-mean count:** {positive_folds}/5
- **Median fold test-win%:** {median_win:.1f}%
- **Aggregate p-value:** {p_value:.4f}
- **PSR (pooled tests):** {dsr_partial:.4f}
- **Gates:** G1={'P' if g1 else 'F'} G2={'P' if g2 else 'F'} G3={'P' if g3 else 'F'} G4={'P' if g4 else 'F'}
- **Verdict:** {verdict}
""")


if __name__ == "__main__":
    main()
