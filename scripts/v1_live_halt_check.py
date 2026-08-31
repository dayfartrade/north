"""SPRT halt check on v1's current live record.

The Engine A halt (2026-07-20) fired when SPRT log-LR crossed 2.944
with p0=0.57, p1=0.35 at n=18 (4 wins). Same math applied to v1's
current 0/2 tells us: is 0-2 in the halt zone, safe zone, or
inconclusive?

Uses the standard 2-sided SPRT:
  H0: true WR = p0 (backtest baseline, 0.559 for v1)
  H1: true WR = p1 (degraded, pick a plausible failure threshold)
  boundaries:
    A_halt = log((1-beta)/alpha) where alpha=0.05, beta=0.20 -> 2.944
    B_safe = log(beta/(1-alpha))                              -> -2.944

Log-likelihood ratio increments:
  win:  log(p1/p0)
  loss: log((1-p1)/(1-p0))

Compute LR at every possible (n, wins) combination up to n=26 (the
pre-reg forward window). Also plot the halt boundary in trades
terms: how many losses in a row before halt for various starting
win counts.

Usage: python scripts/v1_live_halt_check.py
"""
from __future__ import annotations

import math
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"

# Same SPRT parameters as Engine A halt
P0 = 0.559  # v1 backtest baseline WR
P1 = 0.35   # degraded WR (same as Engine A's p1)
ALPHA = 0.05
BETA = 0.20

A_HALT = math.log((1 - BETA) / ALPHA)     # accept H1 (degraded)
B_SAFE = math.log(BETA / (1 - ALPHA))     # accept H0 (baseline)

WIN_INC = math.log(P1 / P0)
LOSS_INC = math.log((1 - P1) / (1 - P0))


def current_live_state() -> dict:
    """Read calls log, count resolved directional wins/losses."""
    if not CALLS_LOG.exists():
        return {"n": 0, "wins": 0, "losses": 0}
    resolved = []
    for line in open(CALLS_LOG, encoding="utf-8"):
        if not line.strip():
            continue
        c = json.loads(line)
        if c.get("direction") not in ("LONG", "SHORT"):
            continue
        outcome = c.get("outcome") or {}
        if outcome.get("result") != "resolved":
            continue
        resolved.append({
            "week_of": c["week_of"],
            "direction": c["direction"],
            "net_return_pct": outcome.get("net_return_pct", 0),
            "won": outcome.get("net_return_pct", 0) > 0,
        })
    n = len(resolved)
    wins = sum(1 for r in resolved if r["won"])
    return {"n": n, "wins": wins, "losses": n - wins, "trades": resolved}


def log_lr(wins: int, losses: int) -> float:
    return wins * WIN_INC + losses * LOSS_INC


def sprt_verdict(wins: int, losses: int) -> str:
    lr = log_lr(wins, losses)
    if lr >= A_HALT:
        return "HALT"
    if lr <= B_SAFE:
        return "SAFE (continue confidently)"
    return "CONTINUE (not enough evidence yet)"


def main() -> None:
    print(f"SPRT parameters (matching Engine A halt):")
    print(f"  H0 (baseline WR): {P0}")
    print(f"  H1 (degraded WR): {P1}")
    print(f"  alpha={ALPHA}, beta={BETA}")
    print(f"  A_HALT boundary: log-LR >= {A_HALT:.3f}")
    print(f"  B_SAFE boundary: log-LR <= {B_SAFE:.3f}")
    print(f"  per-loss increment: {LOSS_INC:+.4f}")
    print(f"  per-win  increment: {WIN_INC:+.4f}")
    print()

    state = current_live_state()
    print(f"=== v1 live state ===")
    print(f"  resolved directional trades: {state['n']}")
    print(f"  wins/losses: {state['wins']}W-{state['losses']}L")
    for t in state.get("trades", []):
        mark = "W" if t["won"] else "L"
        print(f"    [{mark}] {t['week_of']}  {t['direction']}  {t['net_return_pct']:+.2f}%")
    lr = log_lr(state['wins'], state['losses'])
    print(f"  current log-LR: {lr:+.4f}")
    print(f"  SPRT verdict: {sprt_verdict(state['wins'], state['losses'])}")
    print()

    print(f"=== Loss-only trajectory (starting from current) ===")
    print(f"How many additional consecutive losses before HALT fires:")
    w = state['wins']; l = state['losses']
    for extra in range(0, 20):
        cur_l = l + extra
        cur_lr = log_lr(w, cur_l)
        verdict = sprt_verdict(w, cur_l)
        print(f"  +{extra} more losses: {w}W-{cur_l}L  log-LR={cur_lr:+.3f}  {verdict}")
        if "HALT" in verdict:
            break
    print()

    print(f"=== Full grid: SPRT verdict at various (n, wins) ===")
    print(f"  n\\wins   " + "  ".join(f"{w:>4d}" for w in range(0, 15)))
    for n in range(0, 26):
        row = f"  n={n:>2}     "
        for wins in range(0, min(15, n + 1)):
            losses = n - wins
            verdict = sprt_verdict(wins, losses)
            mark = "H" if verdict == "HALT" else "S" if "SAFE" in verdict else "."
            row += f"  {mark:>4}"
        print(row)
    print()
    print("Legend: H=halt, S=safe (accept H0 baseline), . = continue")


if __name__ == "__main__":
    main()
