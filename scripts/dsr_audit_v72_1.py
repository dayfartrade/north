"""Deflated Sharpe Ratio audit of v7.2.1 with an HONEST trial count.

Applies López de Prado's DSR (Ch 14.7.3) to our shipped strategy, using
N = 15 trials — matching the number of hypotheses I tested on 2026-07-07.
This is the multi-testing correction Janus asked me to apply.

Reports:
  - Raw per-trade Sharpe (with higher moments)
  - PSR against SR* = 0 (probability strategy beats random)
  - DSR against N=3 (shipped-variants count) — moderate correction
  - DSR against N=15 (all tested variants, honest count) — strict correction
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
from deflated_sharpe import sr_stats, probabilistic_sharpe, deflated_sharpe


def main():
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
    pnl = took['net_pnl'].to_numpy()

    print("=" * 78)
    print("Deflated Sharpe Ratio audit — v7.2.1")
    print("=" * 78)
    print(f"Sample: n={len(pnl)} trades")
    print(f"Mean/trade: ${pnl.mean():+.0f}")
    print(f"Total: ${pnl.sum():+.0f}")

    s = sr_stats(pnl)
    print(f"\nSample Sharpe stats:")
    print(f"  Per-trade Sharpe:   {s.sr_per_period:+.4f}")
    print(f"  Skewness:           {s.skewness:+.3f}")
    print(f"  Kurtosis (non-excess): {s.kurtosis:.3f}")
    print(f"  N observations:     {s.n_observations}")

    # Annualization: strategy sees ~0.66 trades/day per backtest cadence
    # trades_per_year = 0.66 * 252 = ~166
    trades_per_year = len(pnl) / (79 / 365)  # 79-day backtest window
    ann_sr = s.sr_per_period * math.sqrt(trades_per_year)
    print(f"  Annualized Sharpe (per {trades_per_year:.0f} trades/yr): {ann_sr:+.3f}")

    print("\n" + "=" * 78)
    print("Probabilistic Sharpe (PSR) — beats SR=0")
    print("=" * 78)
    psr = probabilistic_sharpe(s, benchmark_sr=0.0)
    print(f"  PSR[SR* = 0]: {psr:.4f}")
    print(f"  Verdict: {'SIGNIFICANT (> 0.95)' if psr > 0.95 else 'NOT SIGNIFICANT (<= 0.95)'}")

    print("\n" + "=" * 78)
    print("Deflated Sharpe (DSR) — corrects for multi-testing selection bias")
    print("=" * 78)

    # Variance of SRs across trials — I don't have the exact SRs of all 15
    # variants tested today, so I estimate. Ch 14 example uses V = 0.5.
    # For a conservative first pass, use V = 0.5 (per LdP illustrative example).
    # Going forward, every experiment records its per-trade SR so this is honest.
    sr_variance = 0.5

    for n_trials, label in [
        (3,  "N=3  (v7.1, v7.2, v7.2.1 shipped)"),
        (15, "N=15 (all hypotheses I tested today, honest)"),
    ]:
        dsr, sr_star = deflated_sharpe(s, n_trials, sr_variance)
        print(f"\n  Trials {label}:")
        print(f"    SR* (expected max under null): {sr_star:+.4f}")
        print(f"    DSR (P[true SR > SR*]):        {dsr:.4f}")
        v = "SIGNIFICANT (> 0.95)" if dsr > 0.95 else "NOT SIGNIFICANT (<= 0.95)"
        print(f"    Verdict: {v}")

    print("\n" + "=" * 78)
    print("Interpretation")
    print("=" * 78)
    print("""
- PSR against SR=0 tells us whether our observed edge is likely non-zero.
- DSR against expected-max-under-null accounts for the fact that I tested
  many variants and picked ones that looked good. This is Janus's Bonferroni
  concern in a finance-specific form.
- V[SR_n] is set to the LdP illustrative default of 0.5. Real value would
  be computed from the SRs of all 15 tested variants — which I did not
  record properly at test time. Going forward every registered experiment
  logs its per-trade SR so this variance can be computed exactly.

Marcos's Third Law: "Every backtest result must be reported in conjunction
with all the trials involved in its production." That's why the N=15 line
matters more than the N=3 line — the honest count is 15, not 3.
""")


if __name__ == "__main__":
    import math
    main()
