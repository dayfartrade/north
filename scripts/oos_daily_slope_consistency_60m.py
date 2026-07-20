"""OOS validation of daily_slope_consistency at 60m resolution.

The production filter runs at 5m (session ORB) with a 1h-EMA-50 slope over
5h vs 20d daily slope. We only have 3mo of 5m bars (~32 shadow trades).
This script re-tests the CORE hypothesis at 60m resolution across 2.5 years
of GC 60m data — thousands of observations instead of tens.

Hypothesis: at any 60m bar, if 5-bar EMA-50 slope on 60m closes matches
sign of prior-20d daily slope of GC, the NEXT 3-bar (3-hour) return is
systematically higher than when signs disagree.

Test structure:
  - For each 60m bar with sufficient history:
    - intraday_slope = EMA-50 slope over last 5 bars
    - daily_20d_slope = 20-day GC daily slope as of that bar's date
    - Skip if either is zero (matches production filter)
    - Bucket: ALIGNED if signs match, COUNTER if they oppose
  - Compare fwd 3h return distributions per bucket

This is NOT a validation of the full ORB filter (which involves stop/target
mechanics), but IS a validation of the core directional hypothesis. If
COUNTER bars produce systematically lower forward returns, the filter's
direction-alignment premise is real.

Read-only. Companion to shadow_replay.py.
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GC_60M = ROOT / "data/gc/GC_60m.csv"
GC_1D = ROOT / "data/gc/GC_1d.csv"


def load_60m() -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    with open(GC_60M, newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((r["ts"], float(r["close"])))
            except (ValueError, KeyError):
                continue
    rows.sort()
    return rows


def load_daily() -> dict[str, float]:
    out: dict[str, float] = {}
    with open(GC_1D, newline="") as f:
        for r in csv.DictReader(f):
            try:
                out[r["ts"][:10]] = float(r["close"])
            except (ValueError, KeyError):
                continue
    return out


def daily_20d_slope(daily: dict[str, float], as_of: str, lookback: int = 20) -> float | None:
    prior = [daily[k] for k in sorted(daily.keys()) if k < as_of]
    if len(prior) < lookback:
        return None
    ys = prior[-lookback:]
    n = len(ys); xs = list(range(n))
    mx = sum(xs) / n; my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    return num / den if den else None


def ema50_slope_5(closes: list[float]) -> float | None:
    """EMA-50 over closes, then diff(5). Needs len >= 55."""
    if len(closes) < 55:
        return None
    alpha = 2 / (50 + 1)
    ema = closes[0]
    ema_series = [ema]
    for c in closes[1:]:
        ema = alpha * c + (1 - alpha) * ema
        ema_series.append(ema)
    return ema_series[-1] - ema_series[-6]  # 5-step diff


def stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    m = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    pos = sum(1 for v in vals if v > 0)
    t = m / (sd / len(vals) ** 0.5) if sd else 0
    return {
        "n": len(vals),
        "mean_bps": 10000 * m,
        "sd_bps": 10000 * sd,
        "pos_pct": 100 * pos / len(vals),
        "t_stat": t,
    }


def main() -> None:
    bars = load_60m()
    daily = load_daily()
    print(f"60m bars: {len(bars)}  ({bars[0][0]} -> {bars[-1][0]})")
    print(f"daily bars: {len(daily)}")

    HORIZON_BARS = 3  # 3h forward return

    aligned: list[float] = []
    counter: list[float] = []
    skipped_zero_slope = 0
    skipped_no_daily = 0
    skipped_insufficient = 0

    closes_hist: list[float] = []
    for i, (ts, close) in enumerate(bars):
        closes_hist.append(close)
        if len(closes_hist) < 55:
            skipped_insufficient += 1
            continue
        if i + HORIZON_BARS >= len(bars):
            break

        intra = ema50_slope_5(closes_hist)
        if intra is None or intra == 0:
            skipped_zero_slope += 1
            continue

        date_str = ts[:10]
        dsl = daily_20d_slope(daily, date_str)
        if dsl is None:
            skipped_no_daily += 1
            continue
        if dsl == 0:
            skipped_zero_slope += 1
            continue

        # Forward 3-bar return
        fwd_close = bars[i + HORIZON_BARS][1]
        fwd_ret = (fwd_close - close) / close

        intra_sign = 1 if intra > 0 else -1
        daily_sign = 1 if dsl > 0 else -1

        # In production, direction=sign(intraday). Trade is LONG if intra>0.
        # A LONG trade's expected profit correlates with sign(fwd_ret)==+1.
        # Compute signed return relative to intended trade direction:
        signed_fwd = intra_sign * fwd_ret

        if intra_sign == daily_sign:
            aligned.append(signed_fwd)
        else:
            counter.append(signed_fwd)

    print(f"\nSkipped: {skipped_insufficient} (warmup), "
          f"{skipped_zero_slope} (slope=0), {skipped_no_daily} (no daily context)")
    print(f"Aligned bars: {len(aligned)}   Counter bars: {len(counter)}")

    a = stats(aligned)
    c = stats(counter)
    print()
    print(f"{'bucket':10s} {'n':>6s} {'mean_bps':>10s} {'sd_bps':>9s} {'pos%':>6s} {'t':>7s}")
    print(f"{'ALIGNED':10s} {a['n']:>6d} {a['mean_bps']:>+10.2f} {a['sd_bps']:>9.2f} "
          f"{a['pos_pct']:>5.1f} {a['t_stat']:>+7.2f}")
    print(f"{'COUNTER':10s} {c['n']:>6d} {c['mean_bps']:>+10.2f} {c['sd_bps']:>9.2f} "
          f"{c['pos_pct']:>5.1f} {c['t_stat']:>+7.2f}")

    print()
    delta_bps = a['mean_bps'] - c['mean_bps']
    print(f"ALIGNED - COUNTER mean spread: {delta_bps:+.2f} bps / 3h forward return")
    if delta_bps > 0:
        print("-> Filter's directional premise is SUPPORTED: aligned bars produce "
              "higher signed forward returns than counter.")
    else:
        print("-> Filter's directional premise is NOT SUPPORTED at 60m/3h horizon.")

    # Effect size perspective: at 32 shadow trades we saw huge cherry-pick effect.
    # This test is thousands of bars — should be much more stable.
    print()
    print(f"Sample size ratio vs shadow_replay (n=32): {(a['n']+c['n'])/32:.0f}x larger")
    print()
    print("Caveats:")
    print("- 60m resolution loses OR breakout microstructure detail")
    print("- Signed-forward-return proxy is not the same as actual stop/target hit rate")
    print("- Same regime bias as forward log (2024-2026 GC bull era -> correction)")


if __name__ == "__main__":
    main()
