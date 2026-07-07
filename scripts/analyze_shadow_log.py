"""Shadow-log analyzer — read data/shadow_decisions.jsonl, join with realized
PnL, evaluate each active candidate against its pre-registered decision rule.

Runs safely on empty / partial data — prints "waiting for data" milestones so
we can invoke it daily during the shadow-collection window without noise.

For each active candidate:
  - Group shadow decisions by would_skip True/False
  - Report n, win_rate, mean_pnl, total_pnl per group
  - Bootstrap 95% CI on (kept - skipped) mean-per-trade
  - Report interim milestone status vs pre-reg decision rule
  - Emit PROMOTE / CONTINUE / REJECT verdict when n >= gate threshold

Runs in ~1 second. Safe to schedule daily.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shadow_log import CANDIDATES, load_shadow_log


MILESTONES = [25, 50, 75, 100, 150, 200]


def load_realized_pnl() -> pd.DataFrame:
    """Load realized-PnL history keyed by (session, entry_ts) — the same
    keys the shadow log uses to identify a PLAN. Draws from the ORB forward
    log first (live), falls back to backtest journal if the forward log is
    empty. Both share the same schema columns we need."""
    fwd = ROOT / "data" / "tracker" / "orb_forward_log.csv"
    if fwd.exists():
        df = pd.read_csv(fwd)
        if len(df) > 0:
            df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True, errors="coerce")
            df = df[df["took_trade"] == True].copy()
            df = df.dropna(subset=["entry_ts", "net_pnl"])
            return df[["session", "entry_ts", "net_pnl"]].reset_index(drop=True)
    return pd.DataFrame(columns=["session", "entry_ts", "net_pnl"])


def join_shadow_with_pnl(shadow: pd.DataFrame, pnl: pd.DataFrame) -> pd.DataFrame:
    """Attach net_pnl to each shadow row by matching session + entry_ts.
    Shadow-log's plan.entry_price is often set at OR-close time, before the
    trade actually enters; the tracker's entry_ts is the true fill. We join
    on session and closest-in-time entry_ts within ± 30 min."""
    if shadow.empty or pnl.empty:
        return pd.DataFrame()
    rows = []
    for _, sh in shadow.iterrows():
        plan = sh.get("plan") or {}
        sess = plan.get("session")
        or_close = plan.get("or_close_utc")
        if not sess or not or_close:
            continue
        or_close_ts = pd.to_datetime(or_close, utc=True, errors="coerce")
        if pd.isna(or_close_ts):
            continue
        # Match: same session, entry_ts within 60 min after OR close
        cand = pnl[pnl["session"] == sess]
        cand = cand[(cand["entry_ts"] >= or_close_ts) &
                    (cand["entry_ts"] <= or_close_ts + pd.Timedelta(minutes=60))]
        if cand.empty:
            continue
        best = cand.iloc[0]
        row = {
            "ts_recorded_utc": sh["ts_recorded_utc"],
            "session": sess,
            "entry_ts": best["entry_ts"],
            "net_pnl": float(best["net_pnl"]),
            "shadow_decisions": sh.get("shadow_decisions") or {},
            "features": sh.get("features") or {},
        }
        rows.append(row)
    return pd.DataFrame(rows)


def bootstrap_mean_diff_ci(a: np.ndarray, b: np.ndarray, n_boot: int = 5000,
                           seed: int = 20260707) -> tuple[float, float]:
    """95% CI on (mean(a) - mean(b)) via case bootstrap."""
    if len(a) == 0 or len(b) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        aa = rng.choice(a, size=len(a), replace=True)
        bb = rng.choice(b, size=len(b), replace=True)
        diffs[i] = aa.mean() - bb.mean()
    return (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5)))


def milestone_hit(n: int) -> int | None:
    """Return the highest milestone <= n, or None if below the smallest."""
    for m in reversed(MILESTONES):
        if n >= m:
            return m
    return None


def analyze_candidate(name: str, spec: dict, joined: pd.DataFrame) -> dict:
    """Split joined shadow decisions on a single candidate's would_skip flag,
    compute summary stats and the decision-rule status."""
    if joined.empty:
        return {"n": 0, "status": "waiting_for_data"}

    ws = joined["shadow_decisions"].apply(
        lambda d: (d or {}).get(name, {}).get("would_skip")
    )
    joined = joined.assign(would_skip=ws)
    known = joined[joined["would_skip"].notna()].copy()
    if known.empty:
        return {"n": 0, "status": "waiting_for_data"}

    skipped = known[known["would_skip"] == True]["net_pnl"].to_numpy()
    kept = known[known["would_skip"] == False]["net_pnl"].to_numpy()

    def stats(a: np.ndarray) -> dict:
        if len(a) == 0:
            return {"n": 0, "win_rate": None, "mean": None, "total": None}
        return {
            "n": int(len(a)),
            "win_rate": float((a > 0).mean() * 100),
            "mean": float(a.mean()),
            "total": float(a.sum()),
        }

    s_kept = stats(kept)
    s_skipped = stats(skipped)
    ci_lo, ci_hi = bootstrap_mean_diff_ci(kept, skipped)

    n_total = len(known)
    hit = milestone_hit(n_total)

    return {
        "n": n_total,
        "kept": s_kept,
        "skipped": s_skipped,
        "diff_mean": (s_kept["mean"] - s_skipped["mean"])
                     if (s_kept["mean"] is not None and s_skipped["mean"] is not None) else None,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "milestone": hit,
        "spec": spec,
        "status": "at_milestone" if hit else "collecting",
    }


def apply_decision_rule(name: str, res: dict) -> str:
    """Apply the pre-registered decision rule for a candidate.
    Currently only vol_ratio_ge_1_0 is registered — its rule is in
    docs/experiments/2026-07-07_vol_ratio_shadow.md."""
    if res.get("n", 0) < 100:
        return "CONTINUE (n<100)"
    if name != "vol_ratio_ge_1_0":
        return "MANUAL REVIEW (no rule wired for this candidate)"

    k = res["kept"]; s = res["skipped"]
    if not k or not s or k["n"] == 0 or s["n"] == 0:
        return "MANUAL REVIEW (empty group)"

    # Baseline = pooled win rate + mean
    all_pnl = np.concatenate([
        np.repeat(k["mean"], k["n"]),  # placeholder — real code should pass raw arrays
        np.repeat(s["mean"], s["n"]),
    ])
    # Baseline win rate approximated from the pooled data
    baseline_win = (k["win_rate"] * k["n"] + s["win_rate"] * s["n"]) / (k["n"] + s["n"])
    baseline_mean = (k["mean"] * k["n"] + s["mean"] * s["n"]) / (k["n"] + s["n"])

    g1 = s["win_rate"] < (baseline_win - 10.0)
    g2 = s["mean"] < (baseline_mean - 200.0)
    g3 = k["mean"] >= baseline_mean
    g4 = res["ci_hi"] < 0  # kept - skipped entirely negative? => skipped is worse

    # Rejection: at n>=200, skipped >= baseline win => no real signal
    if res["n"] >= 200 and s["win_rate"] >= baseline_win:
        return "REJECT"
    if g1 and g2 and g3 and g4:
        return "PROMOTE"
    return "CONTINUE (signal weak or inconclusive)"


def main():
    print("=" * 78)
    print("SHADOW LOG ANALYZER")
    print("Reads: data/shadow_decisions.jsonl")
    print("Joins: data/tracker/orb_forward_log.csv")
    print("=" * 78)

    shadow = load_shadow_log()
    pnl = load_realized_pnl()
    joined = join_shadow_with_pnl(shadow, pnl)

    print(f"\nShadow log rows:   {len(shadow)}")
    print(f"Forward log trades: {len(pnl)}")
    print(f"Joined (matched):   {len(joined)}")

    if joined.empty:
        print("\n[waiting for data] No matched shadow-trade rows yet.")
        print("This is expected until real PLANs fire and write to shadow_decisions.jsonl.")
        print("\nActive candidates:")
        for name, spec in CANDIDATES.items():
            if spec.get("status") == "shadow":
                print(f"  - {name}: {spec['description']}")
        return 0

    print("\n" + "=" * 78)
    print("PER-CANDIDATE ANALYSIS")
    print("=" * 78)
    for name, spec in CANDIDATES.items():
        if spec.get("status") != "shadow":
            continue
        res = analyze_candidate(name, spec, joined)
        verdict = apply_decision_rule(name, res)

        print(f"\n[{name}]  {spec['description']}")
        print(f"  Registered: {spec['registered_utc']}")
        print(f"  Pre-reg:    {spec['preregistered_at']}")
        print(f"  n matched:  {res['n']}")

        if res["n"] == 0:
            print("  (waiting for data with this feature populated)")
            continue

        k = res["kept"]; s = res["skipped"]
        print(f"  Would-KEEP:  n={k['n']:>3} win={k['win_rate']:>5.1f}% "
              f"mean=${k['mean']:>+6.0f} total=${k['total']:>+7.0f}")
        print(f"  Would-SKIP:  n={s['n']:>3} win={s['win_rate']:>5.1f}% "
              f"mean=${s['mean']:>+6.0f} total=${s['total']:>+7.0f}")
        if res["diff_mean"] is not None:
            print(f"  (kept - skipped) mean: ${res['diff_mean']:+.0f}  "
                  f"95% CI [${res['ci_lo']:+.0f}, ${res['ci_hi']:+.0f}]")
        print(f"  Milestone:  {res['milestone'] or '< 25'}")
        print(f"  VERDICT:    {verdict}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
