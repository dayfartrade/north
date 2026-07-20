"""Knox SPRT activation script — pre-registered dormant until Knox shadow n=50.

Implements the protocol in docs/experiments/2026-07-18_knox_sprt_prereg.md:
  1. Load Knox research-dispatched shadow log entries (engine_b_takes=True with
     resolved outcomes).
  2. Require n >= 50 (or --force to override for testing).
  3. Compute observed win rate, clamp to [0.45, 0.60] to get H0.
  4. H1 = H0 - 0.15, floored at 0.30.
  5. alpha = beta = 0.05, boundaries = +/- 2.944.
  6. Write pre-reg parameters to data/knox_sprt_state.json.
  7. Append a trial entry to data/experiments/registry.json with id="knox_sprt_launch".
  8. Print calibration.

Read-mostly: writes new state files + appends to registry. Never deletes.
Idempotent — refuses to re-activate if knox_sprt_state.json already exists
(prevents post-hoc hypothesis re-fitting per pre-reg discipline).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHADOW_LOG = ROOT / "data/shadow_equity_since_halt.jsonl"
STATE_FILE = ROOT / "data/knox_sprt_state.json"
REGISTRY = ROOT / "data/experiments/registry.json"

MIN_N_ACTIVATE = 50
H0_CLAMP_LO = 0.45
H0_CLAMP_HI = 0.60
H1_MARGIN = 0.15
H1_FLOOR = 0.30
ALPHA = 0.05
BETA = 0.05


def _load_engine_b_taken() -> list[dict]:
    """Rows where Engine B would take AND outcome is resolved."""
    if not SHADOW_LOG.exists():
        return []
    out: list[dict] = []
    with open(SHADOW_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not row.get("engine_b_takes"):
                continue
            outcome = row.get("outcome")
            if outcome is None or outcome.get("net_pnl") is None:
                continue
            out.append(row)
    return out


def _boundaries(alpha: float, beta: float) -> tuple[float, float]:
    a = math.log((1 - beta) / alpha)
    b = math.log(beta / (1 - alpha))
    return a, b


def _activate(force: bool, reason: str) -> int:
    if STATE_FILE.exists() and not force:
        print(f"REFUSE: {STATE_FILE} already exists. Refusing to re-activate "
              "(would allow post-hoc hypothesis re-fitting, violating pre-reg).",
              file=sys.stderr)
        return 3

    rows = _load_engine_b_taken()
    n = len(rows)
    print(f"Engine-B-taken resolved rows: n={n}")

    if n < MIN_N_ACTIVATE and not force:
        print(f"INSUFFICIENT: need n >= {MIN_N_ACTIVATE} to activate. Use --force "
              "to override for testing (state file will be prefixed 'TEST_').",
              file=sys.stderr)
        return 4

    wins = sum(1 for r in rows if r["outcome"]["net_pnl"] > 0)
    observed = wins / n if n else 0.0
    h0 = max(H0_CLAMP_LO, min(H0_CLAMP_HI, observed))
    h1 = max(H1_FLOOR, h0 - H1_MARGIN)
    A_halt, B_safe = _boundaries(ALPHA, BETA)

    state = {
        "activated_utc": datetime.now(timezone.utc).isoformat(),
        "activation_reason": reason,
        "activation_n": n,
        "activation_wins": wins,
        "observed_win_rate": observed,
        "clamp_lo": H0_CLAMP_LO,
        "clamp_hi": H0_CLAMP_HI,
        "h0_used": h0,
        "h0_was_clamped": (observed != h0),
        "h1_used": h1,
        "h1_was_floored": (h1 == H1_FLOOR),
        "alpha": ALPHA,
        "beta": BETA,
        "boundary_A_halt": A_halt,
        "boundary_B_safe": B_safe,
        "force_mode": bool(force),
        "trial_id": "knox_sprt_launch" if not force else "knox_sprt_launch_TEST",
    }

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE_FILE)
    print(f"Wrote {STATE_FILE}")
    print(f"  H0 = {h0:.4f}  (observed {observed:.4f}; clamped={state['h0_was_clamped']})")
    print(f"  H1 = {h1:.4f}  (floored={state['h1_was_floored']})")
    print(f"  boundaries: HALT +{A_halt:.4f}  SAFE {B_safe:.4f}")

    # Append trial to registry (production only, not --force)
    if not force:
        try:
            reg = json.loads(REGISTRY.read_text())
            reg["trials"].append({
                "id": "knox_sprt_launch",
                "registered_utc": state["activated_utc"],
                "layer": "operational_halt",
                "verdict": "pre_registered",
                "sr_per_period": None,
                "n_observations": n,
                "notes": (
                    f"ACTIVATED per pre-reg (docs/experiments/2026-07-18_knox_sprt_prereg.md). "
                    f"Observed win rate {observed:.3f} at n={n}. H0={h0:.3f} "
                    f"(clamped={state['h0_was_clamped']}), H1={h1:.3f} "
                    f"(floored={state['h1_was_floored']}), alpha=beta=0.05, "
                    f"boundaries +/-{A_halt:.3f}. Full state in data/knox_sprt_state.json."
                ),
            })
            tmp = REGISTRY.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(reg, indent=2))
            os.replace(tmp, REGISTRY)
            print(f"Appended trial to {REGISTRY}")
        except Exception as e:
            print(f"WARN: registry append failed: {e}. State file still written.",
                  file=sys.stderr)

    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Activate Knox SPRT per pre-reg protocol.")
    p.add_argument("--force", action="store_true",
                   help="Bypass n>=50 gate and pre-existing state check. TEST ONLY.")
    p.add_argument("--reason", default="",
                   help="Reason to record in state (e.g. 'triggered by n=50 milestone')")
    args = p.parse_args(argv[1:])
    return _activate(args.force, args.reason)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
