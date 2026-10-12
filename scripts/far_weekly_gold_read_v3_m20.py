"""FAR Weekly v3-m20 backtest. VOIDED 2026-10-12.

The pre-reg this script implements was VOIDED after a discipline
violation by the author. See:
    docs/experiments/2026-10-12_far_weekly_v3_m20_extremity_prereg.md

The script is retained in the repo for the record but will refuse to
run against the pre-reg. Any future test of the extreme-M20-LONG
hypothesis must be done under a fresh pre-reg against fresh data.

If you believe this script should run anyway, you are the person
pre-reg discipline exists to stop. Read the violation addendum in the
pre-reg doc. Do not add a bypass flag.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "far", str(ROOT / "scripts" / "far_weekly_gold_read.py"))
far = importlib.util.module_from_spec(spec)
spec.loader.exec_module(far)

DXY = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"
PRE_REG = ROOT / "docs" / "experiments" / "2026-10-12_far_weekly_v3_m20_extremity_prereg.md"
SIGNOFF = ROOT / "data" / "experiments" / "v3_m20_signoff.json"

M20_LONG_CEILING = 0.07  # locked pre-reg threshold


def assert_signoff() -> None:
    """Enforce pre-reg cooling-off + signoff requirement in code.

    Refuses to run unless SIGNOFF file exists and is at least 24 hours
    AFTER the pre-reg's own commit timestamp. The pre-reg explicitly
    forbids running the backtest in the same session as the pre-reg draft.
    """
    if not SIGNOFF.exists():
        print(
            "REFUSED: pre-reg cooling-off not satisfied.\n"
            "\n"
            f"To run this backtest, create {SIGNOFF.relative_to(ROOT)} with:\n"
            "  {\n"
            "    \"signed_off_by\": \"<name>\",\n"
            "    \"signed_off_utc\": \"<ISO 8601 UTC timestamp>\",\n"
            "    \"pre_reg_sha\": \"<git short SHA of the pre-reg commit>\",\n"
            "    \"note\": \"<optional comment>\"\n"
            "  }\n"
            "\n"
            "signed_off_utc must be at least 24 hours after the pre-reg\n"
            "commit timestamp. This is the pre-reg's own discipline, not\n"
            "a technical limitation. See the pre-reg doc.\n"
        )
        sys.exit(2)

    try:
        meta = json.loads(SIGNOFF.read_text())
    except json.JSONDecodeError as exc:
        print(f"REFUSED: {SIGNOFF} is not valid JSON: {exc}")
        sys.exit(2)

    required = {"signed_off_by", "signed_off_utc", "pre_reg_sha", "note"}
    missing = required - set(meta)
    if missing:
        print(f"REFUSED: signoff file missing fields: {missing}")
        sys.exit(2)

    try:
        signed_at = datetime.fromisoformat(meta["signed_off_utc"].replace("Z", "+00:00"))
        if signed_at.tzinfo is None:
            signed_at = signed_at.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        print(f"REFUSED: signed_off_utc not ISO 8601: {exc}")
        sys.exit(2)

    # The pre-reg itself has a registered_utc declared at the top.
    # Enforce >= 24h gap. (Hard-coded to the actual pre-reg timestamp.)
    pre_reg_utc = datetime(2026, 10, 12, 20, 0, 0, tzinfo=timezone.utc)
    if signed_at - pre_reg_utc < timedelta(hours=24):
        print(
            "REFUSED: cooling-off period not satisfied.\n"
            f"  Pre-reg registered: {pre_reg_utc.isoformat()}\n"
            f"  Signoff timestamp:  {signed_at.isoformat()}\n"
            f"  Delta required:     >= 24h\n"
            f"  Delta observed:     {signed_at - pre_reg_utc}\n"
            "\n"
            "This gap enforces the pre-reg's own 'at least one additional\n"
            "session has passed' requirement. Backdating the signoff is\n"
            "self-defeating. See the pre-reg doc."
        )
        sys.exit(2)

    print(f"Signoff accepted: signed by {meta['signed_off_by']} at "
          f"{meta['signed_off_utc']} (pre-reg sha {meta['pre_reg_sha']}).")
    if meta.get("note"):
        print(f"Note: {meta['note']}")
    print()


def build_v3_m20_signals(daily: pd.DataFrame, ry: pd.Series, dxy: pd.Series) -> pd.DataFrame:
    """v2 signals (v1 AND DXY_chg aligns) PLUS LONG requires M20 < 7.00%."""
    df = far.build_signals(daily, ry)
    dxy_daily = dxy.reindex(
        df.index.tz_localize(None) if df.index.tz else df.index, method="ffill")
    dxy_daily.index = df.index
    df["DXY"] = dxy_daily
    df["DXY_chg"] = df["DXY"].diff(far.RY_LAG)

    v1_dir = df["direction"]
    long_ok = ((v1_dir == "LONG")
               & (df["DXY_chg"] < 0)
               & (df["M20"] < M20_LONG_CEILING))
    short_ok = (v1_dir == "SHORT") & (df["DXY_chg"] > 0)
    df["direction"] = np.where(long_ok, "LONG",
                                 np.where(short_ok, "SHORT", "FLAT"))
    return df


def backtest(start: pd.Timestamp, end: pd.Timestamp,
             strategy: str = "v3_m20") -> dict:
    """strategy in {'v3_m20', 'v2'}; v2 provided for matched-pair comparison."""
    daily = far.load_daily_bars(start, end)
    ry = far.load_macro_series(far.RY, "real_yield_10y")
    dxy = far.load_macro_series(DXY, "dxy")

    if strategy == "v3_m20":
        df = build_v3_m20_signals(daily, ry, dxy)
    elif strategy == "v2":
        from importlib import import_module  # local shim; replicate v2 logic
        df = far.build_signals(daily, ry)
        dxy_daily = dxy.reindex(
            df.index.tz_localize(None) if df.index.tz else df.index, method="ffill")
        dxy_daily.index = df.index
        df["DXY"] = dxy_daily
        df["DXY_chg"] = df["DXY"].diff(far.RY_LAG)
        v1_dir = df["direction"]
        long_ok = (v1_dir == "LONG") & (df["DXY_chg"] < 0)
        short_ok = (v1_dir == "SHORT") & (df["DXY_chg"] > 0)
        df["direction"] = np.where(long_ok, "LONG",
                                     np.where(short_ok, "SHORT", "FLAT"))
    else:
        raise ValueError(f"Unknown strategy {strategy}")

    df = df[(df.index >= start) & (df.index <= end)]
    weeks = far.week_indices(df)
    trades = []
    flat = 0
    for signal_date, mon, fri in weeks:
        if signal_date not in df.index:
            continue
        sig = df.loc[signal_date]
        d = str(sig["direction"])
        if d == "FLAT":
            flat += 1
            continue
        if pd.isna(sig["ATR"]) or pd.isna(sig["M60"]) or pd.isna(sig.get("DXY_chg")):
            continue
        if mon not in df.index:
            continue
        entry = float(df.loc[mon]["open"])
        atr = float(sig["ATR"])
        if atr <= 0:
            continue
        stop = (entry - 2.0 * atr) if d == "LONG" else (entry + 2.0 * atr)
        r = far.simulate_week(df.loc[mon:fri], mon, fri, d, entry, stop)
        if not r:
            continue
        trades.append({
            "signal_date": signal_date, "week_start": mon,
            "direction": d, "entry": entry, "exit": r["exit"],
            "exit_reason": r["exit_reason"], "net": r["net"],
            "M20": float(sig["M20"]), "ret": r["net"] / (entry * 100),
        })
    return {"trades": trades, "flat": flat, "total_weeks": len(weeks)}


def sharpe_ann(returns: list[float]) -> float:
    if len(returns) < 2:
        return float("nan")
    m = sum(returns) / len(returns)
    s = (sum((r - m) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5
    return (m / s) * math.sqrt(52) if s > 0 else 0.0


def summary(res: dict, label: str) -> dict:
    trades = res["trades"]
    n = len(trades)
    if n == 0:
        print(f"{label}: no trades.")
        return {"n": 0}
    pnls = [t["net"] for t in trades]
    rets = [t["ret"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    sh = sharpe_ann(rets)
    print(f"\n=== {label} ===")
    print(f"  n={n}  WR={100*wins/n:.1f}%  cum=${total:+,.0f}  "
          f"mean $/week=${total/n:+,.0f}  Sharpe={sh:.3f}")
    return {"n": n, "wins": wins, "cum": total, "sharpe": sh, "rets": rets, "trades": trades}


def matched_pair_perm_test(v2_trades: list[dict], v3_trades: list[dict],
                            iters: int = 10000, seed: int = 42) -> dict:
    """Matched-pair test: on common signal dates, compare v2 vs v3 return.
    For dates v3 skips, v3 return = 0 (sat FLAT)."""
    import random
    rng = random.Random(seed)
    v2_by_date = {t["signal_date"]: t for t in v2_trades}
    v3_by_date = {t["signal_date"]: t for t in v3_trades}
    all_dates = sorted(set(v2_by_date) | set(v3_by_date))
    pairs = []
    for d in all_dates:
        v2r = v2_by_date[d]["ret"] if d in v2_by_date else 0.0
        v3r = v3_by_date[d]["ret"] if d in v3_by_date else 0.0
        pairs.append((v2r, v3r))
    diffs = [v3r - v2r for v2r, v3r in pairs]
    if not diffs:
        return {"n_pairs": 0, "mean_lift": 0, "p_one_sided": float("nan")}
    mean_lift = sum(diffs) / len(diffs)
    # Permutation: flip signs of each pair randomly, observe null distribution
    ge = 0
    for _ in range(iters):
        null_mean = sum(d_ * (1 if rng.random() < 0.5 else -1) for d_ in diffs) / len(diffs)
        if null_mean >= mean_lift:
            ge += 1
    p = (ge + 1) / (iters + 1)  # one-sided, right tail
    return {
        "n_pairs": len(diffs),
        "mean_lift": mean_lift,
        "p_one_sided": p,
    }


def report_gates(train_v2: dict, train_v3: dict, oos_v2: dict, oos_v3: dict,
                  full_v3: dict, mp: dict) -> None:
    print("\n=== Pre-reg ship gates (ALL must pass) ===")
    checks = []
    g1 = (oos_v3["sharpe"] - oos_v2["sharpe"]) >= 0.05
    print(f"  [1] OOS Sharpe gate: v3_m20 {oos_v3['sharpe']:.3f} >= "
          f"v2 {oos_v2['sharpe']:.3f} + 0.05 ? {'PASS' if g1 else 'FAIL'}")
    checks.append(g1)
    g2 = oos_v3["cum"] >= 0.85 * oos_v2["cum"] if oos_v2["cum"] > 0 else False
    print(f"  [2] OOS P&L gate: v3_m20 ${oos_v3['cum']:+,.0f} >= 85% of "
          f"v2 ${oos_v2['cum']:+,.0f} (${0.85*oos_v2['cum']:+,.0f})? "
          f"{'PASS' if g2 else 'FAIL'}")
    checks.append(g2)
    g3 = train_v3["sharpe"] >= train_v2["sharpe"]
    print(f"  [3] TRAIN gate: v3_m20 TRAIN Sharpe {train_v3['sharpe']:.3f} >= "
          f"v2 TRAIN {train_v2['sharpe']:.3f}? {'PASS' if g3 else 'FAIL'}")
    checks.append(g3)
    g4 = full_v3["n"] >= 200
    print(f"  [4] Trade count gate: n={full_v3['n']} >= 200? "
          f"{'PASS' if g4 else 'FAIL'}")
    checks.append(g4)
    alpha_bonf = 0.05 / 9
    g5 = mp["p_one_sided"] < alpha_bonf
    print(f"  [5] Matched-pair perm test: p={mp['p_one_sided']:.5f} < "
          f"{alpha_bonf:.5f} (Bonferroni N=9)? {'PASS' if g5 else 'FAIL'}")
    checks.append(g5)
    print(f"\n  Retrospective verdict: {'PASS all 5 gates' if all(checks) else 'FAIL at least one gate'}")

    print("\n=== Reject gates (ANY fail = reject immediately) ===")
    rejects = []
    r1 = oos_v3["sharpe"] < oos_v2["sharpe"]
    if r1:
        rejects.append(f"OOS Sharpe {oos_v3['sharpe']:.3f} < v2 {oos_v2['sharpe']:.3f}")
    r2 = oos_v3["cum"] < 0.80 * oos_v2["cum"] if oos_v2["cum"] > 0 else False
    if r2:
        rejects.append(f"OOS P&L ${oos_v3['cum']:+,.0f} < 80% of v2")
    r3 = full_v3["n"] < 150
    if r3:
        rejects.append(f"Full-sample trade count {full_v3['n']} < 150")
    if train_v3["sharpe"] > 0 and oos_v3["sharpe"] > 0:
        ratio_gap = abs(train_v3["sharpe"] - oos_v3["sharpe"]) / max(train_v3["sharpe"], oos_v3["sharpe"])
        r4 = ratio_gap > 0.50
        if r4:
            rejects.append(f"TRAIN/OOS Sharpe gap {ratio_gap:.1%} > 50%")
    r5 = mp["p_one_sided"] >= 0.05 / 9
    if r5:
        rejects.append(f"Matched-pair p {mp['p_one_sided']:.5f} >= Bonferroni α")
    if rejects:
        print("  REJECT reasons:")
        for r in rejects:
            print(f"    - {r}")
    else:
        print("  No reject conditions triggered.")


def main() -> None:
    print(
        "VOIDED. The pre-reg this script implements was voided on 2026-10-12\n"
        "after an author discipline violation. This script refuses to run.\n"
        "\n"
        "See docs/experiments/2026-10-12_far_weekly_v3_m20_extremity_prereg.md\n"
        "for the full violation addendum."
    )
    sys.exit(2)

    # Dead code path below retained only to document the originally intended
    # ship-gate structure. Execution is prevented above.
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2026-07-20")
    ap.add_argument("--split-sample", action="store_true",
                     help="Produce TRAIN/OOS results + ship-gate report")
    args = ap.parse_args()

    assert_signoff()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")

    if args.split_sample:
        split = pd.Timestamp("2019-01-01", tz="UTC")
        print(f"Split-sample mode: TRAIN [{start.date()}, {split.date()}) / "
              f"OOS [{split.date()}, {end.date()}]")
        train_v2 = summary(backtest(start, split, "v2"), "v2 TRAIN")
        train_v3 = summary(backtest(start, split, "v3_m20"), "v3_m20 TRAIN")
        oos_v2 = summary(backtest(split, end, "v2"), "v2 OOS")
        oos_v3 = summary(backtest(split, end, "v3_m20"), "v3_m20 OOS")
        full_v3 = summary(backtest(start, end, "v3_m20"), "v3_m20 FULL (TRAIN+OOS)")
        mp = matched_pair_perm_test(
            oos_v2["trades"] if "trades" in oos_v2 else [],
            oos_v3["trades"] if "trades" in oos_v3 else [])
        print(f"\n=== Matched-pair test (OOS, v2 vs v3_m20) ===")
        print(f"  n_pairs: {mp['n_pairs']}  mean_lift: {mp['mean_lift']:+.5f}  "
              f"one-sided p: {mp['p_one_sided']:.5f}")
        report_gates(train_v2, train_v3, oos_v2, oos_v3, full_v3, mp)
    else:
        summary(backtest(start, end, "v3_m20"), f"v3_m20 full sample {args.start} to {args.end}")


if __name__ == "__main__":
    main()
