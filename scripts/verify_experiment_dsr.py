"""Round-trip check: does src/experiment_dsr.py reproduce the numbers in
memory/dsr_audit_2026_07_07.md for v7.2.1?

Expected numbers from that audit:
  n=52, mean=+$812/trade, per-trade Sharpe=0.4479, PSR vs SR=0 = 0.9965,
  DSR with N=15 (V=0.5) = 0.0000
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import pytz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from data_gc import load as gc_load
from edge_session_orb import session_utc_time_on
from edge_session_orb_v7_final import run_orb_v7, SESSION_CONFIG
from experiment_dsr import experiment_dsr, current_trial_count


def main():
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    frames = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        df["session"] = sess_name
        if not df.empty:
            frames.append(df)
    took = pd.concat(frames, ignore_index=True)
    took = took[took["took_trade"] == True].copy()
    pnl = took["net_pnl"].to_numpy()

    print(f"Round-trip verify vs memory/dsr_audit_2026_07_07.md")
    print(f"Expected: n=52, mean=+$812, sr=0.4479, PSR=0.9965, DSR(N=15)=0.0000")
    print(f"Registry N = {current_trial_count()}\n")

    result = experiment_dsr(pnl)
    print(f"n:              {result['n_observations']}")
    print(f"mean/trade:     ${pnl.mean():+.0f}")
    print(f"sr_per_period:  {result['sr_per_period']:+.4f}")
    print(f"skew:           {result['skewness']:+.3f}")
    print(f"kurtosis:       {result['kurtosis']:.3f}")
    print(f"N (trials):     {result['n_trials_registry']}")
    print(f"V[SR_n]:        {result['sr_variance']}  ({result['sr_variance_source']})")
    print(f"SR*:            {result['sr_star']:+.4f}")
    print(f"PSR:            {result['psr']:.4f}")
    print(f"DSR:            {result['dsr']:.4f}")

    tol = 0.005
    ok = (
        result["n_observations"] == 52
        and abs(result["sr_per_period"] - 0.4479) < tol
        and abs(result["psr"] - 0.9965) < tol
        and abs(result["dsr"]) < tol
    )
    print(f"\nMatches audit within tolerance: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
