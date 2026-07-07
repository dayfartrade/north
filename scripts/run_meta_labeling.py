"""Pre-registered experiment: meta_labeling_v72_1

Runs the meta-labeler per docs/experiments/2026-07-08_meta_labeling_v72_1.md.
The decision rule was LOCKED before this file was executed.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import pytz
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_gc import load as gc_load
from edge_session_orb import session_utc_time_on
from edge_session_orb_v7_final import run_orb_v7, SESSION_CONFIG
from mers_v3_peb import compute_atr
from experiment_dsr import experiment_dsr, register_experiment_result


THRESHOLD = 0.5
K = 5
EMBARGO = 0.01

BASELINE_WIN_PCT = 69.2
BASELINE_MEAN_PNL = 812.0

# Gates from the pre-reg (locked)
GATE1_WIN_PCT   = 74.2   # baseline + 5pp
GATE2_MEAN_PNL  = 912.0  # baseline + $100
GATE3_KEEP_FRAC = 0.60
GATE4_DSR       = 0.50


def collect_trades_with_features() -> pd.DataFrame:
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    frames = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        df["session"] = sess_name
        if df.empty:
            continue
        frames.append(df)
    took = pd.concat(frames, ignore_index=True)
    took = took[took["took_trade"] == True].copy()

    # Features are already computed inside run_orb_v7 — no lookup needed.
    took["or_atr_ratio"] = took["or_range"].astype(float) / took["atr"].astype(float)
    took["trend_slope_abs"] = took["trend_slope"].astype(float).abs()
    took["entry_ts"] = pd.to_datetime(took["entry_ts"], utc=True)
    took = took.sort_values("entry_ts").reset_index(drop=True)
    took = took.dropna(subset=["or_atr_ratio", "trend_slope_abs", "net_pnl"])
    return took


def build_feature_matrix(trades: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X = pd.get_dummies(trades[["session", "or_atr_ratio", "trend_slope_abs"]],
                        columns=["session"], drop_first=True).to_numpy(dtype=float)
    y = (trades["net_pnl"].to_numpy() > 0).astype(int)
    return X, y


def purged_kfold_indices(n: int, k: int, embargo_pct: float):
    fold_size = n // k
    embargo = max(1, int(round(embargo_pct * n)))
    for i in range(k):
        test_start = i * fold_size
        test_end = (i + 1) * fold_size if i < k - 1 else n
        test_idx = np.arange(test_start, test_end)
        train_idx = np.concatenate([
            np.arange(0, test_start),
            np.arange(min(test_end + embargo, n), n),
        ])
        yield train_idx, test_idx


def main():
    print("=" * 78)
    print("PRE-REGISTERED EXPERIMENT: meta_labeling_v72_1")
    print("Pre-reg: docs/experiments/2026-07-08_meta_labeling_v72_1.md")
    print("=" * 78)

    trades = collect_trades_with_features()
    print(f"Sample: n={len(trades)}  (baseline win={BASELINE_WIN_PCT}%, mean=${BASELINE_MEAN_PNL:.0f})")
    X, y = build_feature_matrix(trades)
    print(f"Features shape: {X.shape}")

    oos_probs = np.full(len(trades), np.nan)
    for i, (train_idx, test_idx) in enumerate(purged_kfold_indices(len(trades), K, EMBARGO)):
        clf = LogisticRegression(C=1.0, max_iter=500)
        clf.fit(X[train_idx], y[train_idx])
        oos_probs[test_idx] = clf.predict_proba(X[test_idx])[:, 1]
        print(f"  Fold {i}: train={len(train_idx)}, test={len(test_idx)}, "
              f"test_mean_prob={oos_probs[test_idx].mean():.3f}")

    kept_mask = oos_probs >= THRESHOLD
    kept_pnl = trades.loc[kept_mask, "net_pnl"].to_numpy()
    n_kept = int(kept_mask.sum())
    keep_frac = n_kept / len(trades)
    kept_win_pct = float((kept_pnl > 0).mean() * 100) if n_kept else 0.0
    kept_mean = float(kept_pnl.mean()) if n_kept else 0.0

    print()
    print("=" * 78)
    print("RESULTS")
    print("=" * 78)
    print(f"  Kept trades: {n_kept}/{len(trades)}  (keep_frac={keep_frac:.2%})")
    print(f"  Kept-trade OOS win-rate: {kept_win_pct:.1f}%   (gate ≥ {GATE1_WIN_PCT:.1f}%)")
    print(f"  Kept-trade OOS mean/tr:  ${kept_mean:+.0f}   (gate ≥ ${GATE2_MEAN_PNL:.0f})")
    print(f"  Keep fraction:            {keep_frac:.2%}   (gate ≥ {GATE3_KEEP_FRAC:.0%})")

    if n_kept >= 2:
        dsr_result = experiment_dsr(kept_pnl)
        dsr = dsr_result["dsr"]
        psr = dsr_result["psr"]
        sr_star = dsr_result["sr_star"]
        n_trials = dsr_result["n_trials_registry"]
    else:
        dsr = float("nan"); psr = float("nan"); sr_star = float("nan"); n_trials = 0

    print(f"  DSR (N={n_trials}, V=0.5): {dsr:.4f}   (gate > {GATE4_DSR:.2f})")
    print(f"  PSR vs SR=0:              {psr:.4f}")
    print(f"  SR* (expected max):       {sr_star:+.4f}")

    g1 = kept_win_pct >= GATE1_WIN_PCT
    g2 = kept_mean >= GATE2_MEAN_PNL
    g3 = keep_frac >= GATE3_KEEP_FRAC
    g4 = dsr > GATE4_DSR

    print()
    print(f"  G1 win >= {GATE1_WIN_PCT:.1f}%:  {'PASS' if g1 else 'FAIL'}")
    print(f"  G2 mean >= ${GATE2_MEAN_PNL:.0f}:  {'PASS' if g2 else 'FAIL'}")
    print(f"  G3 keep >= {GATE3_KEEP_FRAC:.0%}:  {'PASS' if g3 else 'FAIL'}")
    print(f"  G4 DSR > {GATE4_DSR:.2f}:      {'PASS' if g4 else 'FAIL'}")

    all_pass = g1 and g2 and g3 and g4
    any_hard_fail_with_worse_mean = (
        (not g1 or not g2 or not g3) and kept_mean < BASELINE_MEAN_PNL
    )

    if all_pass:
        verdict = "SHIPPABLE-SIGNAL"
    elif any_hard_fail_with_worse_mean:
        verdict = "REJECT"
    else:
        verdict = "INCONCLUSIVE"

    print()
    print("=" * 78)
    print(f"  VERDICT: {verdict}")
    print("=" * 78)

    register_experiment_result(
        experiment_id="meta_labeling_v72_1",
        pnl=kept_pnl if n_kept >= 2 else None,
        layer="session_config",
        verdict=verdict.lower(),
        notes=(f"3-feature logistic (session, or_atr_ratio, trend_slope_abs). "
               f"Purged 5-fold, embargo=1%, threshold=0.5. "
               f"kept_win={kept_win_pct:.1f}% mean=${kept_mean:+.0f} "
               f"keep_frac={keep_frac:.2%} DSR={dsr:.4f} PSR={psr:.4f}"),
    )
    print(f"\n  Registered in experiment registry (N is now current after this trial).")

    print("\n\nCopy to Results section of pre-reg file:")
    print("=" * 78)
    print(f"""
- **Ran on:** 2026-07-08
- **Sample size:** n={len(trades)}
- **Kept fraction:** {keep_frac:.2%} ({n_kept}/{len(trades)})
- **Kept-trade OOS win-rate:** {kept_win_pct:.1f}%
- **Kept-trade OOS mean/trade:** ${kept_mean:+.0f}
- **DSR (N={n_trials}, V=0.5):** {dsr:.4f}
- **PSR vs SR=0:** {psr:.4f}
- **Gates:** G1={'P' if g1 else 'F'} G2={'P' if g2 else 'F'} G3={'P' if g3 else 'F'} G4={'P' if g4 else 'F'}
- **Verdict:** {verdict}
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
