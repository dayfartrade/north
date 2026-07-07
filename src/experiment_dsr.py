"""Persistent experiment registry + one-call DSR for every future experiment.

Fixes the two gaps from the 2026-07-07 DSR audit:

1. Trial count (N) was hardcoded per script. Now stored in
   data/experiments/registry.json; every experiment reads current N.
2. V[SR_n] was assumed to be LdP's default 0.5 because per-variant Sharpes
   weren't recorded at test time. Now every registered trial records its
   per-period Sharpe. When >= 2 trials have recorded SRs, V is computed
   from data; otherwise falls back to 0.5 with a warning.

Bootstrap entry: N=15 backfill from the 2026-07-07 audit, with no SR values
(so variance keeps its default until real trials accumulate).

Typical experiment script use:
    from experiment_dsr import experiment_dsr, register_experiment_result

    result = experiment_dsr(pnl)
    print(f"N={result['n_trials']}, DSR={result['dsr']:.4f}")

    # After the pre-reg gates pass or fail:
    register_experiment_result(
        experiment_id="v7.3_or_range_extreme_skip",
        pnl=pnl,
        layer="session_config",
        verdict="rejected",  # or "shipped" or "shadow_continue"
        notes="rejected at pre-reg gate 3 (permutation p=0.14)",
    )
"""
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from deflated_sharpe import sr_stats, probabilistic_sharpe, deflated_sharpe

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "data" / "experiments" / "registry.json"

# LdP illustrative default when we can't compute V[SR_n] from data
DEFAULT_SR_VARIANCE = 0.5


def _empty_registry() -> dict:
    return {
        "schema_version": 1,
        "notes": (
            "One row per trial ever tested. sr_per_period is the observed "
            "per-trade Sharpe on the trial's evaluation sample. When >=2 rows "
            "have sr_per_period recorded, V[SR_n] is computed from them; "
            "otherwise the LdP default 0.5 is used and a warning printed."
        ),
        "trials": [],
    }


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return _empty_registry()
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_registry(reg: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, sort_keys=False)
    tmp.replace(REGISTRY_PATH)


def _measured_sr_variance(reg: dict) -> tuple[float, int, bool]:
    """Compute V[SR_n] from registered SRs. Returns (variance, n_recorded, used_default)."""
    srs = [t.get("sr_per_period") for t in reg.get("trials", [])
           if t.get("sr_per_period") is not None]
    srs = [s for s in srs if isinstance(s, (int, float)) and np.isfinite(s)]
    if len(srs) >= 2:
        return float(np.var(np.array(srs), ddof=1)), len(srs), False
    return DEFAULT_SR_VARIANCE, len(srs), True


def current_trial_count() -> int:
    """Number of trials on record (Bonferroni / DSR N)."""
    return len(_load_registry().get("trials", []))


def experiment_dsr(pnl: Sequence[float], benchmark_sr: float = 0.0) -> dict:
    """One-call DSR audit for an experiment's PnL series.

    Reads the persistent registry to determine N and V[SR_n], computes
    per-trade Sharpe, PSR, expected max under null (SR*), and DSR.

    Does NOT auto-register the experiment. Call `register_experiment_result`
    separately once the verdict is known — that way rejected experiments
    still add to future Bonferroni denominators, but you decide when.
    """
    pnl_arr = np.asarray(pnl, dtype=float)
    pnl_arr = pnl_arr[np.isfinite(pnl_arr)]

    s = sr_stats(pnl_arr)
    reg = _load_registry()
    n_trials = len(reg.get("trials", []))
    sr_var, n_recorded, used_default = _measured_sr_variance(reg)

    dsr, sr_star = deflated_sharpe(s, n_trials, sr_var) if n_trials >= 2 else (float("nan"), 0.0)
    psr = probabilistic_sharpe(s, benchmark_sr)

    return {
        "n_observations": int(s.n_observations),
        "sr_per_period": float(s.sr_per_period),
        "skewness": float(s.skewness),
        "kurtosis": float(s.kurtosis),
        "n_trials_registry": n_trials,
        "sr_variance": float(sr_var),
        "sr_variance_source": ("measured" if not used_default else "ldp_default_0.5"),
        "sr_variance_n_recorded": n_recorded,
        "sr_star": float(sr_star),
        "psr": float(psr),
        "dsr": float(dsr),
        "benchmark_sr": float(benchmark_sr),
    }


def register_experiment_result(
    experiment_id: str,
    pnl: Sequence[float] | None,
    layer: str,
    verdict: str,
    notes: str = "",
    sr_per_period_override: float | None = None,
) -> dict:
    """Append a trial to the registry so future experiments correct against it.

    pnl: raw per-trade PnL. If None, provide sr_per_period_override.
    layer: "strategy_engine" | "session_config" | "calendar_audit"
    verdict: "shipped" | "rejected" | "shadow_continue" | "backfill"

    Marcos's Third Law: EVERY trial that was tested must land here, whether
    it shipped or not. Rejected trials still contribute to the Bonferroni
    denominator for future experiments.
    """
    if pnl is not None:
        pnl_arr = np.asarray(pnl, dtype=float)
        pnl_arr = pnl_arr[np.isfinite(pnl_arr)]
        s = sr_stats(pnl_arr)
        sr = float(s.sr_per_period)
        n_obs = int(s.n_observations)
    else:
        sr = sr_per_period_override
        n_obs = None

    reg = _load_registry()
    row = {
        "id": experiment_id,
        "registered_utc": pd.Timestamp.utcnow().tz_localize(None).isoformat() + "Z",
        "layer": layer,
        "verdict": verdict,
        "sr_per_period": sr,
        "n_observations": n_obs,
        "notes": notes,
    }
    reg.setdefault("trials", []).append(row)
    _save_registry(reg)
    return row


def bootstrap_from_dsr_audit() -> None:
    """One-time seed: if registry is empty, populate with the honest N=15
    backfill from the 2026-07-07 DSR audit. Idempotent — skips if already
    seeded (any entry with id starting 'backfill_2026_07_07_')."""
    reg = _load_registry()
    if any(t.get("id", "").startswith("backfill_2026_07_07_") for t in reg.get("trials", [])):
        return

    reg = _empty_registry()
    # The 3 that shipped
    for i, ident in enumerate(["v7", "v7.1", "v7.2.1"]):
        reg["trials"].append({
            "id": f"backfill_2026_07_07_{ident}",
            "registered_utc": "2026-07-07T20:00:00Z",
            "layer": "session_config",
            "verdict": "shipped",
            "sr_per_period": None,
            "n_observations": None,
            "notes": (
                "Backfilled from 2026-07-07 DSR audit — per-variant SR not "
                "recorded at test time. Counts toward N; does not contribute "
                "to measured V[SR_n]."
            ),
        })
    # 12 rejected hypotheses tested that day (2026-07-07 sweep)
    for i in range(12):
        reg["trials"].append({
            "id": f"backfill_2026_07_07_rejected_{i+1:02d}",
            "registered_utc": "2026-07-07T20:00:00Z",
            "layer": "session_config",
            "verdict": "rejected",
            "sr_per_period": None,
            "n_observations": None,
            "notes": (
                "Backfilled from 2026-07-07 sweep — 12 hypotheses tested "
                "and rejected without per-variant SR recording. Contributes "
                "to Bonferroni N, not V[SR_n]."
            ),
        })
    _save_registry(reg)


if __name__ == "__main__":
    # `python src/experiment_dsr.py` prints current registry state.
    bootstrap_from_dsr_audit()
    reg = _load_registry()
    var, n_rec, used_default = _measured_sr_variance(reg)
    print(f"Registry:     {REGISTRY_PATH}")
    print(f"Trials:       {len(reg.get('trials', []))}")
    print(f"With SR data: {n_rec}")
    print(f"V[SR_n]:      {var}  ({'measured' if not used_default else 'LdP default'})")
    print(f"\nBy verdict:")
    verdicts = {}
    for t in reg.get("trials", []):
        v = t.get("verdict", "unknown")
        verdicts[v] = verdicts.get(v, 0) + 1
    for v, n in sorted(verdicts.items()):
        print(f"  {v}: {n}")
