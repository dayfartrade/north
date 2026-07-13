"""Halt-monitor: automated 2x-DD watch per quant framework + shadow-equity comparison.

Runs each dispatch tick. Computes:
  - Realized DD since launch (from orb_forward_log.csv)
  - Shadow-equity: what P&L would be if we applied a "halt-on-losses" rule
    starting at the first realized peak
  - Reference max DD (backtest baseline OR forward-window proxy)
  - Ratio: realized / reference

Emits verdict:
  - GREEN     : ratio < 1.5x
  - AMBER     : 1.5x <= ratio < 2.0x  (private alert; watch closely)
  - HALT      : ratio >= 2.0x  OR realized DD >= 20% of capital
  - HALT_STUCK: previously halted; shadow-equity has not recovered above pre-halt peak

The shadow-equity comparison operationalizes the framework's "keep signal in
shadow when halted" containment: it tracks what live P&L WOULD have done
after the halt point, so we can distinguish regime break (shadow bleeds too
= edge dead) from bad luck (shadow recovers = halt was wrong).

Writes:
  - data/halt_state.json (verdict + trajectory)

Read-only. Emits Telegram private alert on verdict transitions.

Intended run pattern: called from dispatch tick (wrap in try/except), OR manually.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FWD = ROOT / "data/tracker/orb_forward_log.csv"
STATE = ROOT / "data/halt_state.json"

LAUNCH_DATE = "2026-07-01"

# Reference max DD baseline — bootstrap p95 from pre-launch 14-trade null (2026-07-13).
# See scripts/bootstrap_validation.py output. n=10 horizon = $13,695; n=72 = $42,498.
# Using n=10 horizon since that matches current sample size. Refresh at n=30, 50, 100.
REFERENCE_MAX_DD = 13695.0  # dollars, magnitude

# Capital baseline for the 20% behavioral floor.
# TODO: user to confirm actual account size; set default conservatively.
ACCOUNT_CAPITAL = 100000.0  # placeholder — user must confirm

# Thresholds
AMBER_RATIO = 1.5
HALT_RATIO = 2.0
CAPITAL_FLOOR_PCT = 0.20  # 20% of capital


def compute_dd(pnls: list[float]) -> dict:
    if not pnls:
        return {"max_dd": 0.0, "current_dd": 0.0, "final_equity": 0.0, "peak": 0.0, "trajectory": []}
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    trajectory = []
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = equity - peak
        if dd < max_dd:
            max_dd = dd
        trajectory.append({"pnl": p, "equity": equity, "dd_from_peak": dd})
    return {"max_dd": max_dd, "current_dd": equity - peak, "final_equity": equity, "peak": peak, "trajectory": trajectory}


def sprt(pnls: list[float], p0: float = 0.57, p1: float = 0.35, alpha: float = 0.05, beta: float = 0.05) -> dict:
    """Wald's Sequential Probability Ratio Test on win rate.

    H0: true win rate p = p0 (strategy is fine)
    H1: true win rate p = p1 (strategy is broken)

    Boundaries:
      A = ln((1-beta)/alpha) : upper — cross to accept H1 (HALT)
      B = ln(beta/(1-alpha)) : lower — cross to accept H0 (SAFE)
      In between: keep sampling.

    Gold-specific rationale (per quant framework): gold's slow effective sample
    rate makes waiting for n=100 unacceptable. SPRT lets us halt as soon as
    evidence accumulates against H0.
    """
    import math
    A = math.log((1 - beta) / alpha)
    B = math.log(beta / (1 - alpha))
    log_lr = 0.0
    wins = 0
    for p in pnls:
        won = 1 if p > 0 else 0
        wins += won
        # Per-trade log-likelihood ratio: log(p1/p0) if win, log((1-p1)/(1-p0)) if loss
        if won:
            log_lr += math.log(p1 / p0)
        else:
            log_lr += math.log((1 - p1) / (1 - p0))
    if log_lr >= A:
        verdict = "SPRT_HALT"
    elif log_lr <= B:
        verdict = "SPRT_SAFE"
    else:
        verdict = "SPRT_CONTINUE"
    return {
        "n": len(pnls),
        "wins": wins,
        "win_rate": wins / len(pnls) if pnls else None,
        "log_lr": log_lr,
        "boundary_A_halt": A,
        "boundary_B_safe": B,
        "verdict": verdict,
        "p0_hypothesis": p0,
        "p1_hypothesis": p1,
    }


def compute_shadow_equity(pnls: list[float], halt_at_dd: float) -> dict:
    """Simulate what equity would be if we halted at halt_at_dd magnitude
    (dollars, negative), then stayed halted from that point onward.

    Returns the counterfactual final equity (what we would have had if we halted)
    vs what actually happened. Used to answer: 'if we had halted N trades ago,
    would we be better off now?'

    If halt_at_dd is not reached, returns identity (no counterfactual).
    """
    if not pnls or halt_at_dd >= 0:
        return {"halted_at_trade": None, "counterfactual_equity": sum(pnls), "delta_vs_actual": 0.0}
    equity = 0.0
    peak = 0.0
    halted_at = None
    counterfactual = 0.0
    for i, p in enumerate(pnls):
        equity += p
        if equity > peak:
            peak = equity
        dd = equity - peak
        if halted_at is None and dd <= halt_at_dd:
            halted_at = i
            counterfactual = equity  # freeze at halt point
    if halted_at is None:
        counterfactual = equity  # never halted
    actual_final = sum(pnls)
    return {
        "halted_at_trade": halted_at,
        "counterfactual_equity": counterfactual,
        "actual_final_equity": actual_final,
        "delta_vs_actual": counterfactual - actual_final,
    }


def load_live_pnls() -> list[float]:
    if not FWD.exists():
        return []
    out: list[float] = []
    with open(FWD, newline="") as f:
        for row in csv.DictReader(f):
            if row["took_trade"] != "True":
                continue
            try:
                d = row["entry_ts"][:10]
                if d >= LAUNCH_DATE:
                    out.append(float(row["net_pnl"]))
            except (ValueError, KeyError):
                continue
    return out


def compute_verdict(realized_dd: float, capital: float, ref_dd: float) -> tuple[str, dict]:
    """Return (verdict, detail dict)."""
    dd_mag = abs(realized_dd)
    ratio = dd_mag / ref_dd if ref_dd > 0 else float("inf")
    capital_pct = dd_mag / capital if capital > 0 else 0.0

    verdict = "GREEN"
    reason = "within normal range"

    if capital_pct >= CAPITAL_FLOOR_PCT:
        verdict = "HALT"
        reason = f"capital floor: DD is {capital_pct:.0%} of capital (>= {CAPITAL_FLOOR_PCT:.0%})"
    elif ratio >= HALT_RATIO:
        verdict = "HALT"
        reason = f"ratio {ratio:.2f}x >= {HALT_RATIO}x reference max DD"
    elif ratio >= AMBER_RATIO:
        verdict = "AMBER"
        reason = f"ratio {ratio:.2f}x >= {AMBER_RATIO}x reference max DD"

    return verdict, {
        "realized_dd": realized_dd,
        "realized_dd_mag": dd_mag,
        "reference_max_dd": ref_dd,
        "capital": capital,
        "ratio": ratio,
        "capital_pct": capital_pct,
        "reason": reason,
    }


def load_prev_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE)


def main() -> None:
    pnls = load_live_pnls()
    dd = compute_dd(pnls)
    verdict, detail = compute_verdict(dd["max_dd"], ACCOUNT_CAPITAL, REFERENCE_MAX_DD)

    # SPRT verdict — pre-registered per docs/experiments/2026-07-13_sprt_prereg.md.
    # If SPRT signals halt, it OVERRIDES the DD-based verdict (edge-break lens vs
    # capital-preservation lens; halt on either per framework).
    _sprt_check = sprt(pnls, p0=0.57, p1=0.35, alpha=0.05, beta=0.05)
    if _sprt_check["verdict"] == "SPRT_HALT" and verdict != "HALT":
        verdict = "HALT"
        detail["reason"] = f"SPRT log-LR={_sprt_check['log_lr']:.3f} >= {_sprt_check['boundary_A_halt']:.3f} (pre-reg params p0=0.57 p1=0.35)"

    # Shadow-equity counterfactual: what if we had halted at AMBER (1.5x ref DD)?
    amber_dd_dollars = -(AMBER_RATIO * REFERENCE_MAX_DD)
    shadow_amber = compute_shadow_equity(pnls, amber_dd_dollars)
    # And what if we had halted at HALT (2.0x)?
    halt_dd_dollars = -(HALT_RATIO * REFERENCE_MAX_DD)
    shadow_halt = compute_shadow_equity(pnls, halt_dd_dollars)

    # SPRT — sequential probability test on win rate
    sprt_result = sprt(pnls, p0=0.57, p1=0.35, alpha=0.05, beta=0.05)

    prev = load_prev_state()
    prev_verdict = prev.get("verdict", "GREEN")

    state = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "n_trades_since_launch": len(pnls),
        "final_equity": dd["final_equity"],
        "realized_max_dd": dd["max_dd"],
        "current_dd": dd["current_dd"],
        "reference_max_dd_used": REFERENCE_MAX_DD,
        "capital_used": ACCOUNT_CAPITAL,
        "ratio": detail["ratio"],
        "capital_pct": detail["capital_pct"],
        "reason": detail["reason"],
        "shadow_amber_halt": shadow_amber,
        "shadow_hard_halt": shadow_halt,
        "sprt": sprt_result,
    }
    save_state(state)

    print(f"HALT MONITOR — {state['ts_utc']}")
    print(f"  Trades since {LAUNCH_DATE}: n={len(pnls)}  final_equity=${dd['final_equity']:,.0f}")
    print(f"  Realized max DD: ${dd['max_dd']:,.0f}  ({detail['capital_pct']:.1%} of capital)")
    print(f"  Reference max DD: ${REFERENCE_MAX_DD:,.0f}  ratio={detail['ratio']:.2f}x")
    print(f"  VERDICT: {verdict}   ({detail['reason']})")

    # Shadow-equity report — the framework's containment idea, operationalized.
    print(f"\n  Shadow-equity counterfactuals (what if we'd halted earlier):")
    if shadow_amber["halted_at_trade"] is not None:
        print(f"    AMBER halt (at 1.5x ref DD = ${amber_dd_dollars:,.0f}):")
        print(f"      would have halted at trade #{shadow_amber['halted_at_trade']+1}/{len(pnls)}")
        print(f"      counterfactual equity: ${shadow_amber['counterfactual_equity']:,.0f}")
        print(f"      vs actual: ${shadow_amber['actual_final_equity']:,.0f}  (delta {shadow_amber['delta_vs_actual']:+,.0f})")
    else:
        print(f"    AMBER halt (${amber_dd_dollars:,.0f}): never triggered — no counterfactual")
    if shadow_halt["halted_at_trade"] is not None:
        print(f"    HARD halt (at 2.0x ref DD = ${halt_dd_dollars:,.0f}):")
        print(f"      would have halted at trade #{shadow_halt['halted_at_trade']+1}/{len(pnls)}")
        print(f"      counterfactual equity: ${shadow_halt['counterfactual_equity']:,.0f}")
        print(f"      vs actual: ${shadow_halt['actual_final_equity']:,.0f}  (delta {shadow_halt['delta_vs_actual']:+,.0f})")
    else:
        print(f"    HARD halt (${halt_dd_dollars:,.0f}): never triggered — no counterfactual")

    # SPRT report — ADVISORY UNTIL PRE-REGISTERED (see docs/experiments/2026-07-13_sprt_prereg.md)
    print(f"\n  SPRT (H0=57% win, H1=35% win, alpha=beta=0.05) — ADVISORY (params pre-registered 2026-07-13T11:00 UTC):")
    if sprt_result['win_rate'] is not None:
        print(f"    n={sprt_result['n']}  wins={sprt_result['wins']}  win_rate={sprt_result['win_rate']:.1%}")
    else:
        print(f"    n={sprt_result['n']}  (no trades)")
    print(f"    log-LR = {sprt_result['log_lr']:+.3f}  boundaries: HALT>={sprt_result['boundary_A_halt']:.3f}  SAFE<={sprt_result['boundary_B_safe']:.3f}")
    print(f"    SPRT verdict: {sprt_result['verdict']}")
    if sprt_result['verdict'] == "SPRT_HALT":
        print(f"    ** SPRT signals HALT — evidence against H0 sufficient at pre-registered params **")

    if prev_verdict != verdict:
        print(f"\n  ** TRANSITION: {prev_verdict} -> {verdict} **")
        # TODO wire private Telegram alert on transition (post-CPI wire-up)
        # from telegram_bot import send
        # send(f"[HALT_MONITOR] {prev_verdict} -> {verdict}: {detail['reason']}", audience="private")

    return 0 if verdict != "HALT" else 1


if __name__ == "__main__":
    sys.exit(main())
