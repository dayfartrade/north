"""Path Z Deflated Sharpe Ratio audit at N=32 (ship-gate #5).

Applies López de Prado's DSR to Path Z n=85 in-sample using the current
registry trial count. Registry has 32 entries (was ~25 at Path Z pre-reg
time; grew during 2026-07-22 session with Meyers, Crabel, and multiple
Path Z variant tests).

Reports:
  - Sample Sharpe (per-trade, non-annualized) with skew/kurtosis
  - PSR vs SR=0
  - DSR at N=32 with V[SR_n] = 0.5 (LdP illustrative default, matches
    prior sprt_v72_1 audit convention)
  - Also DSR at N=25 (pre-reg-time count) and N=50 (defensive upper bound)

Path Z ship-gate #5 requires DSR > 0.95 at "elevated N". This audit
establishes the current benchmark; forward accumulation may improve
per-trade SR as sample grows.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from deflated_sharpe import sr_stats, probabilistic_sharpe, deflated_sharpe

PATH_Z_LOG = ROOT / "data" / "shadow_equity_path_z.jsonl"
REGISTRY = ROOT / "data" / "experiments" / "registry.json"


def load_pnls() -> list[float]:
    with open(PATH_Z_LOG) as f:
        return [float(json.loads(l)["outcome"]["net_pnl"])
                for l in f if l.strip()]


def registry_trial_count() -> int:
    reg = json.load(open(REGISTRY))
    return len(reg["trials"])


def main() -> None:
    pnls = load_pnls()
    n = len(pnls)
    total = sum(pnls); mean = total / n

    n_trials = registry_trial_count()

    print("=" * 78)
    print(f"Path Z Deflated Sharpe Ratio audit — ship-gate #5")
    print("=" * 78)
    print(f"Sample: n={n} Path Z-taken trades (2024-01-08 to 2026-07-13)")
    print(f"Total P&L: ${total:+,.0f}   mean/trade: ${mean:+,.2f}")

    s = sr_stats(pnls)
    print(f"\nPer-trade Sharpe statistics:")
    print(f"  Sharpe (per-trade):    {s.sr_per_period:+.4f}")
    print(f"  Skewness:              {s.skewness:+.3f}")
    print(f"  Kurtosis (non-excess): {s.kurtosis:.3f}   "
          f"(Gaussian=3.0; higher = fatter tails)")

    # Annualization: Path Z fires ~2.83 trades/month = ~34/yr in current regime
    trades_per_year = 34
    ann_sr = s.sr_per_period * math.sqrt(trades_per_year)
    print(f"  Annualized (34 trades/yr): {ann_sr:+.3f}")

    print("\n" + "=" * 78)
    print("Probabilistic Sharpe (PSR) — beats SR=0")
    print("=" * 78)
    psr = probabilistic_sharpe(s, benchmark_sr=0.0)
    verdict = "PASS (> 0.95)" if psr > 0.95 else "FAIL (<= 0.95)"
    print(f"  PSR[SR* = 0]: {psr:.4f}   {verdict}")

    print("\n" + "=" * 78)
    print("Deflated Sharpe (DSR) — multi-testing selection-bias correction")
    print("=" * 78)
    print("V[SR_n] = 0.5 (LdP illustrative default; matches sprt_v72_1 audit)")
    print()

    sr_variance = 0.5
    for N, label in [
        (25, "N=25  (registry at Path Z pre-reg time)"),
        (n_trials, f"N={n_trials}  (registry NOW, ship-gate authoritative)"),
        (50, "N=50  (defensive upper bound)"),
    ]:
        dsr, sr_star = deflated_sharpe(s, N, sr_variance)
        v = "PASS (> 0.95)" if dsr > 0.95 else "FAIL (<= 0.95)"
        print(f"  {label}:")
        print(f"    SR* (expected max under null): {sr_star:+.4f}")
        print(f"    DSR (P[true SR > SR*]):        {dsr:.4f}   {v}")
        print()

    # Ship-gate #5 verdict
    dsr_authoritative, sr_star_auth = deflated_sharpe(s, n_trials, sr_variance)
    print("=" * 78)
    print("Ship-gate #5 verdict")
    print("=" * 78)
    print(f"  Required: DSR > 0.95 at registry N = {n_trials}")
    print(f"  Observed: DSR = {dsr_authoritative:.4f}")
    if dsr_authoritative > 0.95:
        print(f"  Status: ship-gate #5 PASSES at current n={n}")
    else:
        # How much larger sample or how much higher SR would we need?
        target_sr_star = sr_star_auth
        needed_sr = target_sr_star * 1.5  # rough
        gap = target_sr_star - s.sr_per_period
        print(f"  Status: ship-gate #5 FAILS. Gap to SR*={target_sr_star:.4f}: "
              f"{gap:+.4f} SR/trade")
        print(f"          Path Z per-trade SR must rise above SR* on forward n>=100 sample")
        print(f"          OR sample-based moments (skew/kurt) improve")

    print("\n" + "=" * 78)
    print("Notes on interpretation")
    print("=" * 78)
    print(f"""
- Path Z per-trade SR = {s.sr_per_period:+.4f} is MODEST because the strategy
  has extreme fat right tail (top-10 trades = 103% of P&L). Standard deviation
  is inflated by the huge winners, dragging Sharpe down even though total
  P&L is strongly positive.

- Bootstrap CI on mean/trade [+$30, +$925] clears zero (per path_z_monte_carlo.py).
  Bootstrap P(terminal>0) = 98.4%. These are complementary evidence.

- DSR is HARSHER than PSR because SR* > 0 under multi-testing. Path Z's
  discovery process involved segmenting on session/direction/ER/dow —
  each is a hypothesis. Being conservative on N is honest.

- If ship-gate #5 fails at n=85 in-sample, the pre-reg says forward
  accumulation to n>=100 is the primary evidence. DSR will be re-audited
  at ship-time with the full forward sample.
""")


if __name__ == "__main__":
    main()
