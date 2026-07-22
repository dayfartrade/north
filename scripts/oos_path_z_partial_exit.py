"""Path Z partial-take exit simulation (v10 candidate).

For each of the n=85 Path Z in-sample trades, re-walk the 5m bars and
simulate alternative exit rules. Compare to the original 1xOR stop /
1.5xOR target all-in-all-out baseline.

Rules tested (each independent):
  A. 50% off at 0.5xOR MFE, remaining 50% has stop moved to entry (BE),
     runs to original 1.5xOR target or MAX_HOLD.
  B. 50% off at 1.0xOR MFE, remaining 50% BE-stop, runs to target.
  C. Full position, stop moves to entry after MFE >= 1.0xOR
     (risk-off, no partial). Sanity: matches path_z_mfe_mae logic.
  D. 50% off at 0.5xOR MFE, remaining 50% original stop (no BE trail).

Bar priority when both stop and target hit inside a single 5m bar:
same conservative rule as backfill / mfe_mae — assume stop hit first.

Assumes: same contract sizing (100), same RT cost ($24) split
proportionally per leg (so a 50% partial costs $12 + closing 50%
costs $12).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

XAU = ROOT / "data" / "external" / "dukascopy" / "XAUUSD_5m.csv"
PATH_Z_LOG = ROOT / "data" / "shadow_equity_path_z.jsonl"

CONTRACT_SIZE = 100
RT_COST = 24.0
MAX_HOLD_BARS = 36
WATCH_BARS = 12


def load_bars() -> pd.DataFrame:
    df = pd.read_csv(XAU, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df


def load_trades() -> list[dict]:
    with open(PATH_Z_LOG) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def find_entry_idx(bars: pd.DataFrame, tr: dict) -> int | None:
    or_close_ts = pd.Timestamp(tr["or_close_utc"])
    if or_close_ts.tz is None:
        or_close_ts = or_close_ts.tz_localize("UTC")
    or_close_idx = bars.index.get_loc(bars.index[bars.index <= or_close_ts][-1])
    entry_price = float(tr["entry_price"])
    direction = tr["direction_bias"]
    for k in range(WATCH_BARS):
        i = or_close_idx + 1 + k
        if i >= len(bars):
            return None
        b = bars.iloc[i]
        if direction == "LONG" and b["high"] >= entry_price:
            return i
        if direction == "SHORT" and b["low"] <= entry_price:
            return i
    return None


def simulate_rule(bars: pd.DataFrame, tr: dict, entry_idx: int,
                  rule: str) -> float:
    """Return net P&L in dollars under given rule."""
    entry = float(tr["entry_price"])
    or_range = float(tr["or_range"])
    direction = tr["direction_bias"]
    dir_sign = 1 if direction == "LONG" else -1

    original_stop = float(tr["stop_price"])
    original_target = float(tr["target_price"])

    # Rule-specific parameters
    if rule == "A":
        leg1_take_at_pts = 0.5 * or_range
        use_partial = True
        use_be_trail = True
    elif rule == "B":
        leg1_take_at_pts = 1.0 * or_range
        use_partial = True
        use_be_trail = True
    elif rule == "C":
        leg1_take_at_pts = None
        use_partial = False
        use_be_trail = True  # trail only (BE after 1xOR MFE)
        be_trigger_pts = 1.0 * or_range
    elif rule == "D":
        leg1_take_at_pts = 0.5 * or_range
        use_partial = True
        use_be_trail = False
    else:
        raise ValueError(f"unknown rule {rule}")

    leg1_taken = False
    leg1_pnl = 0.0
    current_stop = original_stop
    leg2_pnl = None  # None until leg2 exits

    for k in range(MAX_HOLD_BARS + 1):
        if entry_idx + k >= len(bars):
            break
        b = bars.iloc[entry_idx + k]
        hi = float(b["high"])
        lo = float(b["low"])

        # Compute MFE this bar (max favorable move relative to entry)
        if direction == "LONG":
            bar_mfe_pts = hi - entry
            bar_mae_pts = lo - entry  # (negative when adverse)
            bar_hit_stop = lo <= current_stop
            bar_hit_target = hi >= original_target
            bar_hit_leg1 = (leg1_take_at_pts is not None
                            and hi >= entry + leg1_take_at_pts)
        else:  # SHORT
            bar_mfe_pts = entry - lo
            bar_mae_pts = entry - hi
            bar_hit_stop = hi >= current_stop
            bar_hit_target = lo <= original_target
            bar_hit_leg1 = (leg1_take_at_pts is not None
                            and lo <= entry - leg1_take_at_pts)

        # Rule C: check if we should trail to BE this bar
        if rule == "C" and current_stop != entry:
            if bar_mfe_pts >= be_trigger_pts:
                current_stop = entry
                # Recompute bar_hit_stop under new stop
                if direction == "LONG":
                    bar_hit_stop = lo <= current_stop
                else:
                    bar_hit_stop = hi >= current_stop

        # Partial take (leg1) — must happen before checking full-position stop
        if use_partial and not leg1_taken and bar_hit_leg1:
            leg1_price = entry + dir_sign * leg1_take_at_pts
            leg1_pnl = (leg1_price - entry) * dir_sign * (CONTRACT_SIZE / 2)
            leg1_pnl -= RT_COST / 2  # half of RT cost for closing half
            leg1_taken = True
            if use_be_trail:
                current_stop = entry
                if direction == "LONG":
                    bar_hit_stop = lo <= current_stop
                else:
                    bar_hit_stop = hi >= current_stop

        # Now resolve leg2 (or full position if !use_partial)
        remaining_size = (CONTRACT_SIZE / 2) if leg1_taken else CONTRACT_SIZE
        # For rule C, no partial: remaining_size = CONTRACT_SIZE always
        if not use_partial:
            remaining_size = CONTRACT_SIZE

        if bar_hit_stop and bar_hit_target:
            # Conservative: stop first
            exit_price = current_stop
        elif bar_hit_stop:
            exit_price = current_stop
        elif bar_hit_target:
            exit_price = original_target
        else:
            continue

        leg2_pnl = (exit_price - entry) * dir_sign * remaining_size
        leg2_pnl -= RT_COST / 2 if leg1_taken else RT_COST
        break

    if leg2_pnl is None:
        # Time exit
        end_idx = min(entry_idx + MAX_HOLD_BARS, len(bars) - 1)
        exit_price = float(bars.iloc[end_idx]["close"])
        remaining_size = (CONTRACT_SIZE / 2) if leg1_taken else CONTRACT_SIZE
        if not use_partial:
            remaining_size = CONTRACT_SIZE
        leg2_pnl = (exit_price - entry) * dir_sign * remaining_size
        leg2_pnl -= RT_COST / 2 if leg1_taken else RT_COST

    return leg1_pnl + leg2_pnl


def summarize(label: str, pnls: list[float]) -> None:
    import statistics
    n = len(pnls)
    total = sum(pnls)
    mean = total / n
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    flat = n - wins - losses
    med = statistics.median(pnls)
    stdev = statistics.stdev(pnls) if n > 1 else 0.0
    print(f"  {label:35s}  n={n:>3d}  total=${total:>+8,.0f}  mean=${mean:>+7,.2f}  "
          f"WR={100*wins/n:>4.1f}%  med=${med:>+7,.0f}  stdev=${stdev:>6,.0f}")


def bootstrap_ci(pnls: list[float], n_boot: int = 5000, seed: int = 42) -> tuple[float, float]:
    import random
    rng = random.Random(seed)
    means = []
    n = len(pnls)
    for _ in range(n_boot):
        sample = [pnls[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot)]
    return lo, hi


def main() -> None:
    print("Loading bars...")
    bars = load_bars()
    print("Loading trades...")
    trades = load_trades()
    print(f"  {len(trades)} in-sample trades")

    baseline_pnls = []
    rule_pnls: dict[str, list[float]] = {"A": [], "B": [], "C": [], "D": []}

    skipped = 0
    for tr in trades:
        entry_idx = find_entry_idx(bars, tr)
        if entry_idx is None:
            skipped += 1
            continue
        baseline_pnls.append(float(tr["outcome"]["net_pnl"]))
        for r in ("A", "B", "C", "D"):
            rule_pnls[r].append(simulate_rule(bars, tr, entry_idx, r))

    if skipped:
        print(f"  (skipped {skipped} trades — entry bar not found)")

    print(f"\n=== Baseline vs partial-take rules ===\n")
    print(f"{'Rule':<8s}{'Description':<40s}")
    print(f"  {'baseline':35s}  all-in-all-out, 1xOR stop, 1.5xOR target")
    print(f"  {'A':35s}  50%@0.5xOR MFE + BE trail on rest")
    print(f"  {'B':35s}  50%@1.0xOR MFE + BE trail on rest")
    print(f"  {'C':35s}  full pos, BE stop after 1.0xOR MFE")
    print(f"  {'D':35s}  50%@0.5xOR MFE, keep original stop")
    print()
    summarize("baseline", baseline_pnls)
    for r in ("A", "B", "C", "D"):
        summarize(f"rule {r}", rule_pnls[r])

    print(f"\n=== Lift vs baseline (mean/trade $) ===")
    base_mean = sum(baseline_pnls) / len(baseline_pnls)
    for r in ("A", "B", "C", "D"):
        m = sum(rule_pnls[r]) / len(rule_pnls[r])
        delta = m - base_mean
        pct = 100 * delta / abs(base_mean) if base_mean else 0.0
        print(f"  rule {r}: mean=${m:+7,.2f}  d=${delta:+7,.2f}  ({pct:+.1f}% vs baseline)")

    print(f"\n=== Bootstrap 95% CI on mean/trade (5000 resamples) ===")
    lo, hi = bootstrap_ci(baseline_pnls)
    print(f"  baseline: [${lo:+,.0f}, ${hi:+,.0f}]")
    for r in ("A", "B", "C", "D"):
        lo, hi = bootstrap_ci(rule_pnls[r])
        print(f"  rule {r}:  [${lo:+,.0f}, ${hi:+,.0f}]")


if __name__ == "__main__":
    main()
