"""Phase 7 - v7 validation gates.

Runs v7-hybrid + stand_down across the full 5m history, then:

  1. Bootstrap CI on per-trade mean net PnL (10,000 resamples, 95% CI).
     Verdict: PASS if CI lower bound > 0.
  2. Chronological 80/20 holdout. Compute holdout-period stats and check
     they don't collapse vs the train period.
     Verdict: PASS if holdout mean > 0 AND |holdout - train| within 1 SE.
  3. Sample-size threshold check.
     n < 20  : insufficient (no claim)
     n < 100 : weak (directional only)
     n >= 100: usable
     n >= 250: strong

Prints a single verdict block at the end so the launch/no-launch call
is unambiguous.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
from datetime import datetime
import pytz

from data_gc import load as gc_load
from edge_session_orb import SESSIONS_LOCAL, session_utc_time_on
from edge_session_orb_v7_final import run_orb_v7, SESSION_CONFIG


RNG_SEED = 20260630
N_BOOTSTRAP = 10_000
HOLDOUT_FRAC = 0.20


def run_full_backtest() -> pd.DataFrame:
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    frames = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out[out["took_trade"] == True].copy()
    out["entry_ts"] = pd.to_datetime(out["entry_ts"], utc=True)
    out = out.sort_values("entry_ts").reset_index(drop=True)
    return out


def bootstrap_mean_ci(pnl: np.ndarray, n_boot: int, alpha: float = 0.05,
                       rng: np.random.Generator | None = None) -> tuple[float, float, float]:
    rng = rng or np.random.default_rng(RNG_SEED)
    if len(pnl) == 0:
        return (float("nan"),) * 3
    samples = rng.choice(pnl, size=(n_boot, len(pnl)), replace=True).mean(axis=1)
    lo = float(np.quantile(samples, alpha / 2))
    hi = float(np.quantile(samples, 1 - alpha / 2))
    return float(pnl.mean()), lo, hi


def split_chronological(trades: pd.DataFrame, frac: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(trades)
    cut = int(np.floor(n * (1 - frac)))
    return trades.iloc[:cut].copy(), trades.iloc[cut:].copy()


def session_breakdown(trades: pd.DataFrame) -> list[tuple[str, int, int, float, float]]:
    rows = []
    for sess in sorted(trades["session"].unique()):
        sub = trades[trades["session"] == sess]
        n = len(sub); wins = int((sub["net_pnl"] > 0).sum())
        rows.append((sess, n, wins, float(sub["net_pnl"].sum()), float(sub["net_pnl"].mean())))
    return rows


def fmt_block(title: str, trades: pd.DataFrame, rng: np.random.Generator) -> str:
    if trades.empty:
        return f"{title}: NO TRADES\n"
    pnl = trades["net_pnl"].to_numpy()
    n = len(pnl); wins = int((pnl > 0).sum())
    mean, lo, hi = bootstrap_mean_ci(pnl, N_BOOTSTRAP, rng=rng)
    sd = pnl.std(ddof=1) if n > 1 else 0.0
    sharpe_pt = mean / sd if sd > 0 else 0.0
    lines = [
        f"{title}: n={n}  win={wins}/{n} ({wins/n*100:5.1f}%)  total=${pnl.sum():+,.0f}",
        f"  mean=${mean:+,.2f}/trade  95% CI [${lo:+,.2f}, ${hi:+,.2f}]  sharpe(pt)={sharpe_pt:+.3f}",
    ]
    for sess, ns, sw, st, sm in session_breakdown(trades):
        lines.append(f"  {sess:5s} n={ns:3d}  win={sw}/{ns} ({sw/ns*100:5.1f}%)  total=${st:+,.0f}  mean=${sm:+,.2f}")
    return "\n".join(lines) + "\n"


def main():
    rng = np.random.default_rng(RNG_SEED)
    print("=" * 78)
    print("Phase 7 — v7-hybrid + stand_down validation")
    print("=" * 78)
    trades = run_full_backtest()
    if trades.empty:
        print("FAIL: no trades produced. Check data/calendar/v7 modules.")
        return 1

    bars_start = trades["entry_ts"].min(); bars_end = trades["entry_ts"].max()
    print(f"Window: {bars_start.date()} -> {bars_end.date()}  ({(bars_end - bars_start).days} days)")
    print()

    # ---- Full sample bootstrap
    print(fmt_block("FULL SAMPLE", trades, rng))

    # ---- Holdout split
    train, holdout = split_chronological(trades, HOLDOUT_FRAC)
    print(fmt_block(f"TRAIN ({int((1-HOLDOUT_FRAC)*100)}%)", train, rng))
    print(fmt_block(f"HOLDOUT ({int(HOLDOUT_FRAC*100)}%)", holdout, rng))

    # ---- Verdicts
    pnl_all = trades["net_pnl"].to_numpy()
    _, lo_all, _ = bootstrap_mean_ci(pnl_all, N_BOOTSTRAP, rng=np.random.default_rng(RNG_SEED))

    pnl_hold = holdout["net_pnl"].to_numpy() if not holdout.empty else np.array([])
    train_mean = train["net_pnl"].mean() if not train.empty else 0.0
    hold_mean = holdout["net_pnl"].mean() if not holdout.empty else 0.0
    hold_se = holdout["net_pnl"].std(ddof=1) / np.sqrt(len(holdout)) if len(holdout) > 1 else float("inf")
    drift = hold_mean - train_mean
    drift_se_ratio = abs(drift) / hold_se if hold_se > 0 else float("inf")

    print("-" * 78)
    print("VERDICT")
    print("-" * 78)
    n = len(trades)
    if n >= 250:
        size_tag = "STRONG  (n≥250)"
    elif n >= 100:
        size_tag = "USABLE  (n≥100)"
    elif n >= 20:
        size_tag = "WEAK    (n≥20, directional only)"
    else:
        size_tag = "INSUFFICIENT (n<20, no claim)"
    print(f"Sample size:       {n:4d}   {size_tag}")
    print(f"Full-sample CI:    {'PASS' if lo_all > 0 else 'FAIL'}   (lower bound ${lo_all:+,.2f}/trade)")
    if len(pnl_hold) >= 5:
        hold_pass = hold_mean > 0
        drift_pass = drift_se_ratio <= 1.0
        print(f"Holdout > 0:       {'PASS' if hold_pass else 'FAIL'}   (mean ${hold_mean:+,.2f}/trade, n={len(pnl_hold)})")
        print(f"Drift within 1 SE: {'PASS' if drift_pass else 'FAIL'}   (Δ=${drift:+,.2f}, |Δ|/SE={drift_se_ratio:.2f})")
        overall = lo_all > 0 and hold_pass and drift_pass and n >= 20
    else:
        print(f"Holdout n={len(pnl_hold)} < 5: CANNOT EVALUATE holdout")
        overall = False
    print()
    print(f"OVERALL: {'DEPLOY-READY' if overall else 'NOT READY (see failed gates above)'}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
