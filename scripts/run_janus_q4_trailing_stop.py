"""Pre-registered experiment: janus_q4_trailing_stop

Runs the exact rule locked in docs/experiments/2026-07-07_janus_q4_trailing_stop.md
against the v7.2.1 backtest sample. Fills the Results section per that file.

Do NOT edit the decision rule in the pre-reg file after this script runs.
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

# Cost model per B4 (matches shipped constant)
RT_COST = 24  # $ per contract round-trip


def collect_v72_1_trades():
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
    return bars, took.sort_values('entry_ts').reset_index(drop=True)


def simulate_trailing(entry_ts, direction, entry_price, stop_price, target_price, bars):
    """Apply Janus's Q4 schedule to a single trade.

    Rules (from pre-reg file, locked 2026-07-07T18:35Z):
      0-60 min: original SL, original target
      60-120 min: if MFE > 50% target_dist, move SL to entry (breakeven)
      120-180 min: SL = entry + direction * 0.5 * peak_MFE_dollars/100
      180 min: time exit

    Returns (net_pnl, exit_reason, exit_bar_offset).
    """
    if entry_ts not in bars.index:
        return None, 'no_bar', None
    i_entry = bars.index.get_loc(entry_ts)
    target_dist = abs(target_price - entry_price)

    cur_stop = stop_price
    peak_mfe = 0.0
    # Time-exit at 180 min = 36 bars of 5m
    for k in range(1, 37):
        if i_entry + k >= len(bars):
            break
        b = bars.iloc[i_entry + k]
        mins_since_entry = k * 5

        # Track MFE up to (and including) this bar
        if direction == 1:
            bar_mfe = float(b['high']) - entry_price
        else:
            bar_mfe = entry_price - float(b['low'])
        if bar_mfe > peak_mfe:
            peak_mfe = bar_mfe

        # Trailing schedule — evaluated AT THIS BAR before checking stop/target
        if 60 < mins_since_entry <= 120:
            # Breakeven if MFE > 50% of target distance
            if peak_mfe > 0.5 * target_dist:
                # move stop to entry (only if it's an improvement)
                if direction == 1 and entry_price > cur_stop:
                    cur_stop = entry_price
                elif direction == -1 and entry_price < cur_stop:
                    cur_stop = entry_price
        elif mins_since_entry > 120:
            # Lock 50% of peak MFE
            trail_stop = entry_price + direction * 0.5 * peak_mfe
            if direction == 1 and trail_stop > cur_stop:
                cur_stop = trail_stop
            elif direction == -1 and trail_stop < cur_stop:
                cur_stop = trail_stop

        # Check hit
        if direction == 1:
            hit_stop = float(b['low']) <= cur_stop
            hit_target = float(b['high']) >= target_price
        else:
            hit_stop = float(b['high']) >= cur_stop
            hit_target = float(b['low']) <= target_price

        # Ambiguous: both hit -> conservative (stop wins)
        if hit_stop and hit_target:
            exit_px = cur_stop
            reason = 'stop_or_target_ambiguous'
            return (exit_px - entry_price) * direction * 100 - RT_COST, reason, k
        if hit_stop:
            return (cur_stop - entry_price) * direction * 100 - RT_COST, 'stop', k
        if hit_target:
            return (target_price - entry_price) * direction * 100 - RT_COST, 'target', k

    # Time exit at bar 36 (180 min) — close of that bar
    j = min(i_entry + 36, len(bars) - 1)
    exit_px = float(bars.iloc[j]['close'])
    return (exit_px - entry_price) * direction * 100 - RT_COST, 'time', 36


def main():
    print("=" * 78)
    print("PRE-REGISTERED EXPERIMENT: janus_q4_trailing_stop")
    print("Pre-reg: docs/experiments/2026-07-07_janus_q4_trailing_stop.md")
    print("=" * 78)

    bars, took = collect_v72_1_trades()
    print(f"v7.2.1 trades: n={len(took)}")

    # Baseline (v7.2.1 shipped exits) — from the took dataframe
    baseline = took.copy()
    print(f"\nBaseline v7.2.1:")
    print(f"  n={len(baseline)}  win={baseline['net_pnl'].gt(0).mean()*100:.1f}%  "
          f"mean=${baseline['net_pnl'].mean():+.0f}  total=${baseline['net_pnl'].sum():+.0f}")

    # Trailing (Janus Q4 schedule)
    results = []
    for _, t in took.iterrows():
        net, reason, k = simulate_trailing(
            t['entry_ts'], int(t['direction']),
            float(t['entry_price']), float(t['stop_price']), float(t['target_price']),
            bars,
        )
        if net is None:
            continue
        results.append({
            'entry_ts': t['entry_ts'], 'session': t['session'],
            'net_pnl': net, 'exit_reason': reason, 'exit_bar': k,
        })
    tr = pd.DataFrame(results).sort_values('entry_ts').reset_index(drop=True)
    print(f"\nJanus Q4 trailing:")
    print(f"  n={len(tr)}  win={tr['net_pnl'].gt(0).mean()*100:.1f}%  "
          f"mean=${tr['net_pnl'].mean():+.0f}  total=${tr['net_pnl'].sum():+.0f}")
    print(f"  Exit-reason breakdown:")
    for reason, count in tr['exit_reason'].value_counts().items():
        sub = tr[tr['exit_reason'] == reason]
        print(f"    {reason:30s}: n={count:>3}  win={sub['net_pnl'].gt(0).mean()*100:>4.1f}%  mean=${sub['net_pnl'].mean():+.0f}")

    # Chronological 60/40 OOS split (matches how v7.2.1 was validated)
    cut = int(0.6 * len(tr))
    train_b = baseline.iloc[:cut]; test_b = baseline.iloc[cut:]
    train_t = tr.iloc[:cut]; test_t = tr.iloc[cut:]

    print(f"\n{'':6} {'baseline':>28}{'':4}{'trailing':>28}")
    for setname, dset_b, dset_t in [('TRAIN', train_b, train_t), ('TEST', test_b, test_t)]:
        pb = dset_b['net_pnl']; pt = dset_t['net_pnl']
        print(f"{setname:>6} n={len(pb):>2} win={pb.gt(0).mean()*100:>4.1f}% mean=${pb.mean():>+6.0f}    "
              f"n={len(pt):>2} win={pt.gt(0).mean()*100:>4.1f}% mean=${pt.mean():>+6.0f}")

    # Bootstrap OOS CI on the DIFFERENCE (matched-pair)
    rng = np.random.default_rng(20260707)
    diff = (test_t['net_pnl'].to_numpy() - test_b['net_pnl'].to_numpy())
    boots = rng.choice(diff, size=(10000, len(diff)), replace=True).mean(axis=1)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    print(f"\nMatched-pair OOS mean(trailing - baseline): "
          f"${diff.mean():+.0f}  CI [${lo:+.0f}, ${hi:+.0f}]")

    # Permutation p-value: shuffle sign of the paired difference
    # H0: trailing has no effect => diff is symmetric around 0
    obs_diff_mean = diff.mean()
    n_perm = 10000
    perm_dist = []
    for _ in range(n_perm):
        signs = rng.choice([-1, 1], size=len(diff))
        perm_dist.append(np.mean(diff * signs))
    perm_dist = np.array(perm_dist)
    p_value = (np.abs(perm_dist) >= abs(obs_diff_mean)).mean()

    # Full-sample lift
    fs_lift = tr['net_pnl'].mean() - baseline['net_pnl'].mean()
    fs_win_delta = (tr['net_pnl'].gt(0).mean() - baseline['net_pnl'].gt(0).mean()) * 100

    # Decision rule (LOCKED per pre-reg)
    print("\n" + "=" * 78)
    print("DECISION RULE EVALUATION (Bonferroni N=1 -> alpha=0.05)")
    print("=" * 78)
    g1 = fs_lift >= 50
    g2 = fs_win_delta > -3.0
    g3 = lo >= 0
    g4 = p_value < 0.05

    print(f"  Gate 1: full-sample mean/trade lift >= $50   ->  actual $+{fs_lift:.0f}  {'PASS' if g1 else 'FAIL'}")
    print(f"  Gate 2: win rate delta > -3pp                ->  actual {fs_win_delta:+.1f}pp  {'PASS' if g2 else 'FAIL'}")
    print(f"  Gate 3: OOS CI lower bound >= 0              ->  actual ${lo:+.0f}  {'PASS' if g3 else 'FAIL'}")
    print(f"  Gate 4: permutation p-value < 0.05           ->  actual p={p_value:.4f}  {'PASS' if g4 else 'FAIL'}")

    if g1 and g2 and g3 and g4:
        verdict = "SHIP"
    elif fs_lift > 0 or g3:
        verdict = "SHADOW-CONTINUE"
    else:
        verdict = "REJECT"

    print(f"\n  VERDICT: {verdict}")

    # Print rule for capturing into the results section
    print("\n" + "=" * 78)
    print("Copy the following into the Results section of the pre-reg file:")
    print("=" * 78)
    print(f"""
- **Ran on:** 2026-07-07
- **Sample size:** n={len(tr)}
- **In-sample statistics (baseline):** win={baseline['net_pnl'].gt(0).mean()*100:.1f}%  mean=${baseline['net_pnl'].mean():+.0f}  total=${baseline['net_pnl'].sum():+.0f}
- **In-sample statistics (trailing):** win={tr['net_pnl'].gt(0).mean()*100:.1f}%  mean=${tr['net_pnl'].mean():+.0f}  total=${tr['net_pnl'].sum():+.0f}
- **OOS test-set (baseline):** win={test_b['net_pnl'].gt(0).mean()*100:.1f}%  mean=${test_b['net_pnl'].mean():+.0f}
- **OOS test-set (trailing):** win={test_t['net_pnl'].gt(0).mean()*100:.1f}%  mean=${test_t['net_pnl'].mean():+.0f}
- **Matched-pair OOS mean lift:** ${diff.mean():+.0f}  95% CI [${lo:+.0f}, ${hi:+.0f}]
- **Permutation p-value:** {p_value:.4f}
- **Bonferroni threshold:** 0.05 (N=1)
- **Gates PASS/FAIL:** G1={'P' if g1 else 'F'} G2={'P' if g2 else 'F'} G3={'P' if g3 else 'F'} G4={'P' if g4 else 'F'}
- **Verdict:** {verdict}
""")


if __name__ == "__main__":
    main()
