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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHADOW_LOG = ROOT / "data/shadow_equity_since_halt.jsonl"

# Ship gates from docs/experiments/2026-07-18_daily_slope_consistency_shadow.md
CANDIDATES: dict[str, dict] = {
    "daily_slope_consistency": {
        "n_ship": 100,
        "precision_ship": 0.60,
        "precision_reject": 0.55,
        "skip_rate_max": 0.40,
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
    """Return per-candidate report dict."""
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


def gate_status(name: str, r: dict) -> str:
    gates = CANDIDATES[name]
    n = r["n"]
    if n < 5:
        return "INSUFFICIENT_DATA"

    p = r.get("precision_on_losers", 0.0)
    sr = r.get("skip_rate", 0.0)
    ci_lo = r.get("pnl_lift_ci95_lo_mean", 0.0)
    n_ship = gates["n_ship"]

    # Reject checks
    if n >= n_ship and p < gates["precision_reject"]:
        return "REJECT (precision below floor)"
    if n >= n_ship and sr > gates["skip_rate_max"]:
        return "REJECT (skip-rate above ceiling)"

    # Ship check
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
