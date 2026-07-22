"""Ship-gate progress reporter for pre-registered v8 shadow candidates.

Reads data/shadow_equity_since_halt.jsonl and reports per-candidate:
  n_shadow           — count of resolved shadow decisions where filter had valid decision
  skip_rate          — fraction of taken-by-strategy trades the filter would have skipped
  precision_on_losers— of trades filter would skip that DID lose, out of all filter-skips
  pnl_lift           — [P&L without filter] − [P&L with filter applied]
  bootstrap 95% CI on pnl_lift — non-parametric, N=2000

Reports ship-gate + reject-gate status per candidate. Read-only.
Uses `candidate_shadows.<name>.would_skip` field seeded by shadow_orb_tracker
+ scripts/backfill_daily_slope_consistency.py.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from deflated_sharpe import sr_stats, probabilistic_sharpe
    _HAS_PSR = True
except Exception:
    _HAS_PSR = False

SHADOW_LOG = ROOT / "data/shadow_equity_since_halt.jsonl"

# Ship gates from candidate pre-reg docs
CANDIDATES: dict[str, dict] = {
    "daily_slope_consistency": {
        "n_ship": 100,
        "precision_ship": 0.60,
        "precision_reject": 0.55,
        "skip_rate_max": 0.40,
        "hard_stop_utc": "2026-10-13",
    },
    # Path Z: NY-SHORT + ER<0.30 + Mon-Wed. Restrictive-take filter.
    # Ship gate is different from dsc — measured on TAKEN trades, not skips.
    # See docs/experiments/2026-07-20_path_z_ny_short_prereg.md.
    # Gate #5 amended 2026-07-22 (DSR -> PSR) — see
    # docs/experiments/2026-07-22_path_z_ship_gate_amendment.md.
    "path_z": {
        "n_ship": 100,           # of TAKEN (would_take=True) trades
        "mean_ship": 0.0,        # mean per-trade P&L > 0 required
        "win_rate_ship": 0.55,   # of taken trades, >= 55% winners
        "ci_lo_ship": 0.0,       # bootstrap 95% CI lower bound clears zero
        "psr_ship": 0.95,        # PSR vs SR=0 > 0.95 (gate #5, amended)
        "hard_stop_utc": "2026-10-13",
    },
}


def load_rows() -> list[dict]:
    if not SHADOW_LOG.exists():
        return []
    out: list[dict] = []
    with open(SHADOW_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _bootstrap_ci(diffs: list[float], n: int = 2000, alpha: float = 0.05) -> tuple[float, float]:
    if len(diffs) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(20260718)
    means: list[float] = []
    N = len(diffs)
    for _ in range(n):
        sample = [diffs[rng.randrange(N)] for _ in range(N)]
        means.append(sum(sample) / N)
    means.sort()
    lo_idx = int(alpha / 2 * n)
    hi_idx = int((1 - alpha / 2) * n)
    return (means[lo_idx], means[hi_idx])


def analyze_candidate(rows: list[dict], name: str) -> dict:
    """Return per-candidate report dict.

    Two candidate types with different semantics:
      - "skip filter" (e.g. daily_slope_consistency): filter SKIPS bad entries.
        Measure lift = (baseline P&L) - (baseline P&L on kept only), and
        precision-on-losers of the skips.
      - "take filter" (e.g. path_z): filter TAKES only in a restrictive subset.
        Measure mean/CI/win-rate on the WOULD-TAKE rows directly.
    """
    if name == "path_z":
        return _analyze_take_filter(rows, name)

    # Only rows where:
    #   - strategy actually took (would_skip=False)
    #   - outcome resolved (net_pnl present)
    #   - candidate has valid decision (would_skip is not None)
    taken = []
    for r in rows:
        if r.get("would_skip"):
            continue
        outcome = r.get("outcome")
        if outcome is None or outcome.get("net_pnl") is None:
            continue
        cs = (r.get("candidate_shadows") or {}).get(name)
        if not cs or cs.get("would_skip") is None:
            continue
        taken.append({
            "would_skip": bool(cs["would_skip"]),
            "net_pnl": float(outcome["net_pnl"]),
            "session": r.get("session"),
            "direction": r.get("direction_bias"),
            "date": r.get("or_open_utc", "")[:10],
        })

    n = len(taken)
    if n == 0:
        return {"n": 0}

    skips = [t for t in taken if t["would_skip"]]
    keeps = [t for t in taken if not t["would_skip"]]
    n_skips = len(skips)
    n_wins_skipped = sum(1 for t in skips if t["net_pnl"] > 0)
    n_losses_skipped = n_skips - n_wins_skipped

    total_no_filter = sum(t["net_pnl"] for t in taken)
    total_with_filter = sum(t["net_pnl"] for t in keeps)
    pnl_lift = total_with_filter - total_no_filter

    # Per-trade diffs: if trade would have been skipped, gain 0-pnl (filter removed it)
    diffs = [(-t["net_pnl"] if t["would_skip"] else 0.0) for t in taken]
    ci_lo, ci_hi = _bootstrap_ci(diffs)

    precision = n_losses_skipped / n_skips if n_skips else float("nan")
    skip_rate = n_skips / n

    return {
        "n": n,
        "n_skips": n_skips,
        "skips_won": n_wins_skipped,
        "skips_lost": n_losses_skipped,
        "precision_on_losers": precision,
        "skip_rate": skip_rate,
        "pnl_no_filter": total_no_filter,
        "pnl_with_filter": total_with_filter,
        "pnl_lift_total": pnl_lift,
        "pnl_lift_mean_per_trade": pnl_lift / n,
        "pnl_lift_ci95_lo_mean": ci_lo,
        "pnl_lift_ci95_hi_mean": ci_hi,
    }


def _analyze_take_filter(rows: list[dict], name: str) -> dict:
    """For take-filters (Path Z): measure P&L/CI/win-rate on TAKEN trades.

    Path Z is a filter ON TOP of Path Y. A row counts only if BOTH:
      - Parent row was taken by Path Y (would_skip=False)
      - Candidate would_take=True (i.e. candidate.would_skip=False)
      - Outcome resolved with valid net_pnl

    Path-Y-skipped rows have net_pnl=0 by convention (no trade simulated),
    so they must be excluded — otherwise they'd bias the mean toward 0.
    """
    taken = []
    for r in rows:
        # Parent Path Y must have taken this candidate
        if r.get("would_skip"):
            continue
        outcome = r.get("outcome")
        if outcome is None or outcome.get("net_pnl") is None:
            continue
        # Skip no-entry outcomes (breakout never triggered in watch window)
        kind = outcome.get("kind")
        if kind in ("no_breakout", "flat_no_entry", "skipped"):
            continue
        cs = (r.get("candidate_shadows") or {}).get(name)
        if not cs:
            continue
        # Candidate must have said would_take=True (i.e., NOT would_skip)
        if cs.get("would_skip") is not False:
            continue
        taken.append({
            "net_pnl": float(outcome["net_pnl"]),
            "session": r.get("session"),
            "direction": r.get("direction_bias"),
            "date": r.get("or_open_utc", "")[:10],
        })

    n = len(taken)
    if n == 0:
        return {"n": 0}

    pnls = [t["net_pnl"] for t in taken]
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    mean = total / n
    ci_lo, ci_hi = _bootstrap_ci(pnls)

    # Ship-gate #5 (amended 2026-07-22): PSR vs SR=0 > 0.95
    psr = float("nan")
    if _HAS_PSR and n >= 5:
        try:
            s = sr_stats(pnls)
            psr = probabilistic_sharpe(s, benchmark_sr=0.0)
        except Exception:
            pass

    return {
        "n": n,
        "n_wins": wins,
        "n_losses": n - wins,
        "win_rate": wins / n,
        "total_pnl": total,
        "mean_pnl_per_trade": mean,
        "ci95_lo": ci_lo,
        "ci95_hi": ci_hi,
        "psr": psr,
    }


def gate_status(name: str, r: dict) -> str:
    gates = CANDIDATES[name]
    n = r["n"]
    if n < 5:
        return "INSUFFICIENT_DATA"

    n_ship = gates["n_ship"]

    # Path Z: take-filter gates
    if name == "path_z":
        wr = r.get("win_rate", 0.0)
        mean = r.get("mean_pnl_per_trade", 0.0)
        ci_lo = r.get("ci95_lo", 0.0)
        psr = r.get("psr", float("nan"))
        psr_ship = gates.get("psr_ship", 0.95)
        if n >= n_ship and mean <= gates["mean_ship"]:
            return "REJECT (mean P&L not positive)"
        if n >= n_ship and ci_lo <= gates["ci_lo_ship"]:
            return "REJECT (CI includes zero)"
        if n >= n_ship and not (psr > psr_ship):
            return f"REJECT (PSR {psr:.4f} <= {psr_ship} — amended gate #5)"
        if (n >= n_ship
                and mean > gates["mean_ship"]
                and wr >= gates["win_rate_ship"]
                and ci_lo > gates["ci_lo_ship"]
                and psr > psr_ship):
            return "READY-TO-SHIP"
        return f"IN-PROGRESS ({n}/{n_ship} taken)"

    # Skip-filter gates (dsc-style)
    p = r.get("precision_on_losers", 0.0)
    sr = r.get("skip_rate", 0.0)
    ci_lo = r.get("pnl_lift_ci95_lo_mean", 0.0)

    if n >= n_ship and p < gates["precision_reject"]:
        return "REJECT (precision below floor)"
    if n >= n_ship and sr > gates["skip_rate_max"]:
        return "REJECT (skip-rate above ceiling)"

    if (n >= n_ship
            and p >= gates["precision_ship"]
            and sr <= gates["skip_rate_max"]
            and ci_lo > 0):
        return "READY-TO-SHIP"

    return f"IN-PROGRESS ({n}/{n_ship} sample)"


def main() -> None:
    rows = load_rows()
    print(f"Shadow log rows: {len(rows)}")
    print()

    for name in CANDIDATES:
        print("=" * 72)
        print(f"Candidate: {name}")
        print("=" * 72)
        r = analyze_candidate(rows, name)
        if r["n"] == 0:
            print("  no resolved shadow decisions with valid candidate signal yet")
            continue

        if name == "path_z":
            # Take-filter reporting
            print(f"  n TAKEN by candidate:                {r['n']}")
            print(f"  wins / losses:                       {r['n_wins']} / {r['n_losses']}")
            print(f"  win rate:                            {100 * r['win_rate']:.1f}%")
            print(f"  total P&L:                           ${r['total_pnl']:+,.0f}")
            print(f"  mean/trade:                          ${r['mean_pnl_per_trade']:+,.2f}")
            print(f"  Bootstrap 95% CI on mean:            [${r['ci95_lo']:+,.2f}, ${r['ci95_hi']:+,.2f}]")
            psr_val = r.get("psr", float("nan"))
            if psr_val == psr_val:  # not NaN
                print(f"  PSR vs SR=0 (amended gate #5):       {psr_val:.4f}   "
                      f"{'PASS' if psr_val > 0.95 else 'FAIL'}")
            else:
                print(f"  PSR vs SR=0 (amended gate #5):       n/a (need n>=5)")
            print()
            print(f"  GATE STATUS: {gate_status(name, r)}")
            continue

        print(f"  n resolved (with candidate signal):  {r['n']}")
        print(f"  candidate skip rate:                 {100 * r['skip_rate']:.1f}%")
        print(f"  skips: W={r['skips_won']}  L={r['skips_lost']}  precision-on-losers={100 * r['precision_on_losers']:.1f}%")
        print(f"  P&L (no filter):                     ${r['pnl_no_filter']:,.0f}")
        print(f"  P&L (with filter applied):           ${r['pnl_with_filter']:,.0f}")
        print(f"  P&L lift (total):                    ${r['pnl_lift_total']:+,.0f}")
        print(f"  P&L lift (mean/trade):               ${r['pnl_lift_mean_per_trade']:+,.2f}")
        print(f"  Bootstrap 95% CI on mean lift:       [${r['pnl_lift_ci95_lo_mean']:+,.2f}, "
              f"${r['pnl_lift_ci95_hi_mean']:+,.2f}]")
        print()
        print(f"  GATE STATUS: {gate_status(name, r)}")


if __name__ == "__main__":
    main()
