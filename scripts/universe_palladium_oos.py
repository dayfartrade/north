"""OOS discipline test for palladium LONG.

The universe probe (scripts/universe_v1_probe.py) surfaced palladium
LONG (gold v1 signal, LONG-only) as promising on the full 2010-2026
sample. Full-sample results are contaminated by 8-way multiple testing.
This script applies the standard discipline:

  Train:  2010-01-01 to 2017-12-31 (baseline pattern must exist)
  OOS:    2018-01-01 to 2026-08-14 (edge must hold out-of-sample)

  Gates for Ship (would become a shadow-log candidate):
    Gate 1: OOS bootstrap CI on mean R must clear 0 at 95% (Bonferroni n=8)
    Gate 2: OOS positive years >= 60% of years traded
    Gate 3: OOS mean R > 0.5% per trade (matches gold v1 ship floor)

  Anything less strict would be re-litigating the discipline that
  killed silver GSR and gold basis.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))

spec = importlib.util.spec_from_file_location(
    "universe", str(ROOT / "scripts" / "universe_v1_probe.py")
)
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

from tools.bootstrap_stats import evaluate_signal

N_HYPOTHESES = 8  # 4 assets x 2 directions in the probe


def run_window(start: str, end: str, label: str) -> dict:
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC")
    r = u.backtest("palladium", s, e)
    long_trades = [t for t in r["trades"] if t["direction"] == "LONG"]
    rets = [t["return_pct"] for t in long_trades]
    n = len(rets)
    if n == 0:
        return {"label": label, "n": 0}
    wins = sum(1 for x in rets if x > 0)
    mean = sum(rets) / n
    total = sum(rets)
    by_year = defaultdict(list)
    for t in long_trades:
        by_year[str(t["week_start"])[:4]].append(t["return_pct"])
    pos_years = sum(1 for _, tp in by_year.items() if sum(tp) > 0)
    boot = evaluate_signal(label, rets, n_hypotheses_in_batch=N_HYPOTHESES, ci_lower_threshold=0.0)
    return {
        "label": label,
        "n": n,
        "wins": wins,
        "win_rate": wins / n,
        "mean_return_pct": mean,
        "total_cum_pct": total,
        "years_traded": len(by_year),
        "positive_years": pos_years,
        "bootstrap_mean": boot.mean,
        "ci_low": boot.ci_low,
        "ci_high": boot.ci_high,
        "p_raw": boot.p_raw,
        "p_adjusted": boot.p_adjusted,
        "verdict": boot.verdict,
    }


def print_summary(s: dict) -> None:
    if s["n"] == 0:
        print(f"  {s['label']}: no trades")
        return
    print(f"  {s['label']}:  n={s['n']}  WR={100*s['win_rate']:.1f}%")
    print(f"    mean R:           {100*s['mean_return_pct']:+.3f}%")
    print(f"    total cum R:      {100*s['total_cum_pct']:+.2f}%")
    print(f"    positive years:   {s['positive_years']}/{s['years_traded']}")
    print(f"    bootstrap 95% CI: [{100*s['ci_low']:+.3f}%, {100*s['ci_high']:+.3f}%]")
    print(f"    p_raw:            {s['p_raw']:.4f}")
    print(f"    p_adj (n={N_HYPOTHESES}):     {s['p_adjusted']:.4f}")
    print(f"    verdict:          {s['verdict']}")


def gate_check(oos: dict) -> None:
    print(f"\n{'='*68}\n GATE VERDICT (Bonferroni n={N_HYPOTHESES})\n{'='*68}")
    if oos["n"] == 0:
        print("  No OOS trades. Reject.")
        return
    gate1 = oos["ci_low"] > 0 and oos["p_adjusted"] < 0.05
    gate2 = oos["positive_years"] / max(oos["years_traded"], 1) >= 0.60
    gate3 = oos["mean_return_pct"] > 0.005
    print(f"  Gate 1 (CI clears 0 AND p_adj<0.05): {'PASS' if gate1 else 'FAIL'}")
    print(f"      ci_low={100*oos['ci_low']:+.3f}%   p_adj={oos['p_adjusted']:.4f}")
    print(f"  Gate 2 (OOS positive years >= 60%):  {'PASS' if gate2 else 'FAIL'}")
    print(f"      {oos['positive_years']}/{oos['years_traded']} = "
          f"{100*oos['positive_years']/max(oos['years_traded'],1):.0f}%")
    print(f"  Gate 3 (OOS mean R > 0.5% per trade): {'PASS' if gate3 else 'FAIL'}")
    print(f"      mean R = {100*oos['mean_return_pct']:+.3f}%")
    if gate1 and gate2 and gate3:
        print("\n  VERDICT: ACCEPT as shadow-log candidate.")
    else:
        print("\n  VERDICT: REJECT.")


def main() -> None:
    print("PALLADIUM LONG-ONLY OOS DISCIPLINE TEST")
    print("Signal: gold v1 rules (M20/M60/MA10-40/RY_chg), long side only.")
    print("Prior probe surfaced this on full sample (data snooping across 8 hypotheses).")
    print("This is the honest OOS check.\n")

    train = run_window("2010-01-01", "2017-12-31", "TRAIN 2010-2017")
    oos = run_window("2018-01-01", "2026-08-14", "OOS   2018-2026")

    print_summary(train)
    print()
    print_summary(oos)
    gate_check(oos)


if __name__ == "__main__":
    main()
