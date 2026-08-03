"""Gold basis LONG-only — fresh pre-reg with train/OOS split.

Motivation: the full-sample two-sided baseline (gold_basis_janus_transplant.py)
was INDIST, but the LONG-only cut (basis at extreme low = physical stress
= mean-revert LONG on gold) had mean R = +0.119 with n=157 and 13/17
positive years for the p97.5 variant. That was a POST-HOC finding.

This script re-tests LONG-only as a PRE-REGISTERED candidate with a
locked train/OOS split. The whole point is to test whether the post-hoc
finding survives a discipline gate.

Pre-registered locks (BEFORE seeing OOS results):
    mechanism: LONG XAUUSD when basis (GC - XAU) hits its rolling 180d
               p_low percentile (p97.5 mirror -> p_low = 0.025)
    lookback = 180d
    p_low = 0.025 (basis <= 2.5th percentile of trailing 180d)
    cold-start floor: 180d
    degenerate-distribution guard: (p_high - p_low) >= $0.50
    stop = 2 x ATR(20)
    hold = 7 days
    fill = next-bar open
    costs: slip=0.0002, fee=0.0001
    n_hypotheses = 2 (Bonferroni: original baseline + this LONG-only cut)

Train window: 2010-01-01 to 2017-12-31 (design confirmation only)
OOS window:   2018-01-01 to 2026-06-30 (the actual test)

Ship gate (LOCKED):
    OOS mean R with ci_low >= 0.005 AND p_adjusted < 0.05
    AND >= 60% positive years in OOS window
    Train result is INFORMATIONAL ONLY — does not override OOS.

If OOS fails: LONG-only is rejected, mechanism is dead, note it.
If OOS passes: pre-reg a live paper trade for N weeks before ship.

Usage: python scripts/gold_basis_long_only_oos.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.gold_basis_janus_transplant import (
    load_gc_daily, build_basis_series, compute_basis_signal,
    BasisStrategy, compute_atr, dollar_pnl, per_year, _ms_to_iso_date,
)
from research.tools.data_loader import load_gold_5m, resample
from research.tools.backtest import backtest
from research.tools.bootstrap_stats import evaluate_signal


def filter_long_only(sigs):
    return {d: (v[0], *v[1:]) if v[0] == "LONG" else ("FLAT", *v[1:])
            for d, v in sigs.items()}


def run_window(label, xau_daily, atr_by_date, basis_df, start_date, end_date,
               slip, fee, n_hyp):
    # Filter bars to window
    def bar_in_window(b):
        d = _ms_to_iso_date(b.timestamp)
        return start_date <= d <= end_date
    bars_w = [b for b in xau_daily if bar_in_window(b)]
    print(f"\n--- {label} : {start_date} to {end_date} ---")
    print(f"  bars in window: {len(bars_w)}")

    sigs_full = compute_basis_signal(basis_df, 180, 0.975, 0.025, 0.5)
    sigs_long = filter_long_only(sigs_full)
    # Restrict signals to window (strategy still checks by date lookup)
    sigs_win = {d: v for d, v in sigs_long.items() if start_date <= d <= end_date}
    from collections import Counter
    dist = Counter(v[0] for v in sigs_win.values())
    print(f"  signal dist in window: {dict(dist)}")

    strat = BasisStrategy(sigs_win, atr_by_date, 7)
    result = backtest(strat, bars_w, slippage_pct=slip, fee_pct=fee)
    print(f"  trades: {len(result.trades)}")
    if not result.trades:
        return None

    dol = dollar_pnl(result.trades)
    r_vals = [t.cost_adjusted_r for t in result.trades]
    ev = evaluate_signal(label, r_vals, n_hypotheses_in_batch=n_hyp,
                         ci_lower_threshold=0.005)
    m = result.metrics
    print(f"  R: n={m['n']} WR={m['win_rate']:.3f} mean_r={m['mean_r']:.4f} "
          f"sharpe_pt={m['per_trade_sharpe']:.3f} maxDD={m['max_drawdown_r']:.2f}R")
    print(f"  $: total=${dol['total']:.0f} mean=${dol['mean']:.2f}/tr "
          f"best=${dol['best']:.0f} worst=${dol['worst']:.0f} WR$={dol['wr']:.3f}")
    print(f"  Bootstrap: mean={ev.mean:.4f}R CI=[{ev.ci_low:.4f},{ev.ci_high:.4f}] "
          f"p_adj={ev.p_adjusted:.4f} verdict={ev.verdict}")
    py = per_year(result.trades, dol["per_trade"])
    pos = sum(1 for _, s in py.items() if s["total"] > 0)
    print(f"  Positive years: {pos}/{len(py)}  ({sorted(py.keys())})")
    for y, s in sorted(py.items()):
        print(f"    {y}: n={s['n']} total=${s['total']:>7.0f} wins={s['wins']}/{s['n']}")
    return {"metrics": m, "dollars": dol, "eval": ev, "per_year": py, "pos_years": pos, "n_years": len(py)}


def main():
    START = "2010-01-01"
    END = "2026-06-30"
    TRAIN_END = "2017-12-31"
    OOS_START = "2018-01-01"

    print(f"Loading XAUUSD 5m {START} to {END}...")
    xau_5m = load_gold_5m(start=START, end=END)
    xau_daily = resample(xau_5m, target_minutes=1440)
    print(f"  {len(xau_daily)} daily bars")

    print("Loading GC=F daily...")
    gc_df = load_gc_daily()

    basis_df = build_basis_series(xau_daily, gc_df)
    print(f"Basis series: {len(basis_df)} aligned days")

    atr = compute_atr(xau_daily, 20)
    atr_by_date = {_ms_to_iso_date(b.timestamp): a
                   for b, a in zip(xau_daily, atr) if a is not None}

    slip, fee = 0.0002, 0.0001

    print("\n" + "=" * 70)
    print("GOLD BASIS LONG-ONLY — FRESH PRE-REG WITH TRAIN/OOS SPLIT")
    print("Bonferroni n=2 (original baseline + this LONG-only cut)")
    print("=" * 70)

    train = run_window("TRAIN (informational only)", xau_daily, atr_by_date,
                       basis_df, START, TRAIN_END, slip, fee, 2)
    oos = run_window("OOS (SHIP GATE)", xau_daily, atr_by_date,
                     basis_df, OOS_START, END, slip, fee, 2)

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    if oos is None:
        print("OOS: NO TRADES. REJECTED.")
        return

    ev = oos["eval"]
    ships_r = ev.ci_low >= 0.005 and ev.p_adjusted < 0.05
    pos_pct = oos["pos_years"] / oos["n_years"] if oos["n_years"] else 0
    ships_years = pos_pct >= 0.60

    print(f"OOS mean R:      {ev.mean:.4f}")
    print(f"OOS CI:          [{ev.ci_low:.4f}, {ev.ci_high:.4f}]")
    print(f"OOS p_adjusted:  {ev.p_adjusted:.4f}")
    print(f"OOS pos years:   {oos['pos_years']}/{oos['n_years']} ({pos_pct:.1%})")
    print(f"")
    print(f"Gate 1 (ci_low >= 0.005 AND p_adj < 0.05): {'PASS' if ships_r else 'FAIL'}")
    print(f"Gate 2 (pos years >= 60%):                  {'PASS' if ships_years else 'FAIL'}")
    print(f"")
    if ships_r and ships_years:
        print("VERDICT: SHIP CANDIDATE. Pre-register live paper trade next.")
    else:
        print("VERDICT: REJECTED. Mechanism does not survive OOS discipline.")


if __name__ == "__main__":
    main()
