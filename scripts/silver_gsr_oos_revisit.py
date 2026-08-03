"""Silver GSR z-score reversion — fresh pre-reg with train/OOS split.

Motivation: original Candidate 2 sweep (silver_candidate_gsr.py) tested
27 configurations (lookback in [60,90,180] x |z|>= in [1.5,2.0,2.5] x
hold in [10,15,30]). All were INDIST after 3-hypothesis Bonferroni.
The next_session_agenda memory noted that lookback=180 configs were
consistently profitable but killed by the 27-way multiple-testing
correction.

This script re-tests the lookback=180 family with a LOCKED train/OOS
split and single-config pre-reg. Discipline mirror of what we did for
gold basis LONG-only.

Pre-registered locks (BEFORE seeing OOS results):
    lookback = 180 (fixed based on memory note about which family was best)
    |z| threshold = 1.5 (widest, most trades)
    max_hold_bars = 10 (shortest, per Kelly-like consideration)
    stop = 2 * silver_ATR(20)
    slip = 0.0005, fee = 0.0001 (silver defaults, unchanged)
    n_hypotheses = 1 (single pre-registered config, not a family sweep;
                      the prior 27-config sweep was informational only)

Train window: 2010-01-01 to 2017-12-31 (design confirmation only)
OOS window:   2018-01-01 to 2026-06-30 (the actual test)

Ship gate (LOCKED):
    OOS mean R ci_low >= 0.005 AND p_adjusted < 0.05
    AND positive years >= 60% of OOS

Usage: python scripts/silver_gsr_oos_revisit.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.silver_candidate_gsr import (
    compute_gsr_signal, SilverGSRStrategy, compute_atr,
    compute_dollar_pnl, compute_dollar_per_year, _ms_to_iso_date,
)
from research.tools.data_loader import load_gold_5m, load_silver_5m, resample
from research.tools.backtest import backtest
from research.tools.bootstrap_stats import evaluate_signal


# LOCKED pre-reg
LOOKBACK = 180
Z_THRESHOLD = 1.5
MAX_HOLD = 10
STOP_ATR_MULT = 2.0
SLIP = 0.0005
FEE = 0.0001
N_HYP = 1
TRAIN_END = "2017-12-31"
OOS_START = "2018-01-01"

# Ship gates
CI_LOW_THRESHOLD = 0.005
POS_YEAR_THRESHOLD = 0.60


def run_window(label, silver_daily, gold_daily, atr_by_date,
               start_date, end_date):
    def in_win(b):
        d = _ms_to_iso_date(b.timestamp)
        return start_date <= d <= end_date
    bars_w = [b for b in silver_daily if in_win(b)]
    print(f"\n--- {label} : {start_date} to {end_date} ---")
    print(f"  silver bars in window: {len(bars_w)}")

    sigs_full = compute_gsr_signal(silver_daily, gold_daily,
                                    LOOKBACK, Z_THRESHOLD)
    sigs_win = {d: v for d, v in sigs_full.items()
                if start_date <= d <= end_date}
    from collections import Counter
    dist = Counter(v[0] for v in sigs_win.values())
    print(f"  signal dist in window: {dict(dist)}")

    strat = SilverGSRStrategy(sigs_win, atr_by_date, max_hold_bars=MAX_HOLD)
    result = backtest(strat, bars_w, slippage_pct=SLIP, fee_pct=FEE)
    print(f"  trades: {len(result.trades)}")
    if not result.trades:
        return None

    dol = compute_dollar_pnl(result.trades)
    r_vals = [t.cost_adjusted_r for t in result.trades]
    ev = evaluate_signal(label, r_vals, n_hypotheses_in_batch=N_HYP,
                         ci_lower_threshold=CI_LOW_THRESHOLD)
    m = result.metrics
    print(f"  R: n={m['n']} WR={m['win_rate']:.3f} mean_r={m['mean_r']:.4f} "
          f"sharpe_pt={m['per_trade_sharpe']:.3f} maxDD={m['max_drawdown_r']:.2f}R")
    print(f"  $: total=${dol['total_pnl_dollars']:.0f} mean=${dol['mean_pnl_dollars']:.2f}/tr "
          f"best=${dol['best_dollars']:.0f} worst=${dol['worst_dollars']:.0f} "
          f"WR$={dol['win_rate_dollar']:.3f}")
    print(f"  Bootstrap: mean={ev.mean:.4f}R CI=[{ev.ci_low:.4f},{ev.ci_high:.4f}] "
          f"p_adj={ev.p_adjusted:.4f} verdict={ev.verdict}")
    py = compute_dollar_per_year(result.trades, dol["per_trade"])
    pos = sum(1 for _, s in py.items() if s["total_dollars"] > 0)
    print(f"  Positive years: {pos}/{len(py)}")
    for y, s in sorted(py.items()):
        print(f"    {y}: n={s['n']} total=${s['total_dollars']:>8.0f} wins={s['wins']}/{s['n']}")
    return {"metrics": m, "dollars": dol, "eval": ev, "per_year": py,
            "pos_years": pos, "n_years": len(py)}


def main():
    START = "2010-01-01"
    END = "2026-06-30"

    print(f"Loading gold + silver 5m {START} to {END}...")
    gold_5m = load_gold_5m(start=START, end=END)
    silver_5m = load_silver_5m(start=START, end=END)
    gold_daily = resample(gold_5m, target_minutes=1440)
    silver_daily = resample(silver_5m, target_minutes=1440)
    print(f"  gold daily: {len(gold_daily)}, silver daily: {len(silver_daily)}")

    print("Computing silver ATR(20)...")
    atr_list = compute_atr(silver_daily, period=20)
    atr_by_date = {_ms_to_iso_date(b.timestamp): a
                   for b, a in zip(silver_daily, atr_list) if a is not None}

    print("\n" + "=" * 70)
    print("SILVER GSR Z-SCORE REVERSION — FRESH PRE-REG (single config, "
          "Bonferroni n=1)")
    print(f"  lookback={LOOKBACK}, |z|>={Z_THRESHOLD}, hold={MAX_HOLD}d, "
          f"stop={STOP_ATR_MULT}*ATR20")
    print("=" * 70)

    train = run_window("TRAIN (informational only)",
                       silver_daily, gold_daily, atr_by_date,
                       START, TRAIN_END)
    oos = run_window("OOS (SHIP GATE)",
                     silver_daily, gold_daily, atr_by_date,
                     OOS_START, END)

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    if oos is None:
        print("OOS: no trades. REJECTED.")
        return

    ev = oos["eval"]
    gate1 = ev.ci_low >= CI_LOW_THRESHOLD and ev.p_adjusted < 0.05
    pos_pct = oos["pos_years"] / oos["n_years"] if oos["n_years"] else 0
    gate2 = pos_pct >= POS_YEAR_THRESHOLD

    print(f"OOS mean R:      {ev.mean:+.4f}")
    print(f"OOS CI:          [{ev.ci_low:+.4f}, {ev.ci_high:+.4f}]")
    print(f"OOS p_adjusted:  {ev.p_adjusted:.4f}")
    print(f"OOS pos years:   {oos['pos_years']}/{oos['n_years']} ({pos_pct:.1%})")
    print()
    print(f"Gate 1 (ci_low >= {CI_LOW_THRESHOLD} AND p_adj < 0.05): {'PASS' if gate1 else 'FAIL'}")
    print(f"Gate 2 (pos years >= {POS_YEAR_THRESHOLD:.0%}):                   {'PASS' if gate2 else 'FAIL'}")
    print()
    if gate1 and gate2:
        print("VERDICT: SHIP CANDIDATE.")
    else:
        print("VERDICT: REJECTED.")


if __name__ == "__main__":
    main()
