"""Null test 2: real GC bars, randomized event timestamps.

If MERS v5 truly captures news-driven moves, then randomizing event timestamps
to non-news times should collapse the edge. If profits persist, our "edge" is
just PEB-on-momentum, not news-specific.

We generate N null sets by shuffling each top-tier event to a random bar in
the GC window. Then compare real performance to the null distribution.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v5 import run_v5, dedupe_co_released, TOP_EVENTS_V5
from backtest import summarize


def make_random_events(real_events: pd.DataFrame, bars: pd.DataFrame,
                        n_top_events: int, rng) -> pd.DataFrame:
    """Generate a set of randomized 'events' at random bar timestamps,
    matching the count of real top-tier events. Keeps the same event-type
    distribution."""
    real = dedupe_co_released(real_events)
    real_top = real[real["event"].isin(TOP_EVENTS_V5)]
    # Sample random bars (must be 25 bars in + 7 bars out from edges for trade resolution)
    valid_idx = bars.index[25:-15]
    # Avoid picking timestamps near actual event hours (within 1 day) to keep null clean
    real_top_hours = set(pd.Timestamp(t).floor("1h") for t in real_top["ts_utc"])
    # Build exclusion set: +/- 1 day around each real top event
    excl = set()
    for t in real_top_hours:
        for dh in range(-24, 25):
            excl.add(t + pd.Timedelta(hours=dh))
    cand = [t for t in valid_idx if t not in excl]
    if len(cand) < n_top_events:
        return pd.DataFrame()
    chosen = rng.choice(cand, size=n_top_events, replace=False)

    # Reproduce event-type ratios
    type_counts = real_top["event"].value_counts(normalize=True)
    types = rng.choice(list(type_counts.index), size=n_top_events,
                        p=list(type_counts.values))
    df = pd.DataFrame({
        "ts_utc": [pd.Timestamp(t).tz_convert("UTC") for t in chosen],
        "event": types,
        "value": pd.NA, "prior": pd.NA, "delta": pd.NA,
        "trailing_mean": pd.NA, "trailing_std": pd.NA,
        "surprise_z": np.nan, "expected_dir": 0,
    })
    return df.sort_values("ts_utc").reset_index(drop=True)


def main():
    bars = gc_load("60m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    real_events = build_all()
    real_trades = run_v5(bars, real_events)
    real_s = summarize(real_trades, label="REAL")
    print(f"Real benchmark: n={real_s['n']}, sharpe={real_s['sharpe_per_trade']:+.3f}, "
          f"total_pnl=${real_s['total_net_pnl']:+.0f}, win%={real_s['win_rate']*100:.1f}")

    real_top = dedupe_co_released(real_events)
    real_top = real_top[real_top["event"].isin(TOP_EVENTS_V5)]
    n_top = len(real_top[(real_top["ts_utc"] >= bars.index[0]) & (real_top["ts_utc"] <= bars.index[-1])])
    print(f"Real top-tier events in bar window: {n_top}")

    rng = np.random.default_rng(42)
    n_paths = 300
    sharpes, totals, win_rates, n_trades = [], [], [], []
    print(f"\nGenerating {n_paths} random-timestamp null sets...")
    for p in range(n_paths):
        rand_events = make_random_events(real_events, bars, n_top, rng)
        if rand_events.empty:
            continue
        # Hijack the v5 runner: it expects events with `event` column matching TOP_EVENTS_V5
        trades = run_v5(bars, rand_events)
        s = summarize(trades, label=f"null_{p}")
        if s["n"] >= 5:
            sharpes.append(s["sharpe_per_trade"])
            totals.append(s["total_net_pnl"])
            win_rates.append(s["win_rate"])
            n_trades.append(s["n"])
        if (p + 1) % 50 == 0:
            print(f"  {p+1}/{n_paths} done  (cur n: {s['n']}, sharpe: {s['sharpe_per_trade']:+.2f})")

    sharpes = np.array(sharpes); totals = np.array(totals)
    win_rates = np.array(win_rates); n_trades = np.array(n_trades)

    print("\n=== RANDOM-TIMESTAMP NULL DISTRIBUTION ===")
    print(f"Paths used (n>=5): {len(sharpes)}")
    print(f"  mean trades per path: {n_trades.mean():.1f}")
    print(f"  Sharpe:    mean={sharpes.mean():+.3f}  std={sharpes.std():.3f}  "
          f"q05={np.percentile(sharpes, 5):+.3f}  q95={np.percentile(sharpes, 95):+.3f}")
    print(f"  Total $:   mean=${totals.mean():+.0f}  q05=${np.percentile(totals, 5):+.0f}  "
          f"q95=${np.percentile(totals, 95):+.0f}")
    print(f"  Win rate:  mean={win_rates.mean()*100:.1f}%  q95={np.percentile(win_rates, 95)*100:.1f}%")

    p_sharpe = (sharpes >= real_s["sharpe_per_trade"]).mean()
    p_total = (totals >= real_s["total_net_pnl"]).mean()
    p_winrate = (win_rates >= real_s["win_rate"]).mean()
    print("\n=== EMPIRICAL P-VALUES (real vs random-timestamp null) ===")
    print(f"  P(null Sharpe   >= real {real_s['sharpe_per_trade']:+.3f}):  {p_sharpe:.4f}")
    print(f"  P(null total$   >= real ${real_s['total_net_pnl']:+.0f}):    {p_total:.4f}")
    print(f"  P(null win-rate >= real {real_s['win_rate']*100:.1f}%): {p_winrate:.4f}")

    if p_sharpe < 0.05:
        print("\n  -> News-event edge SIGNIFICANT (p<0.05)")
    elif p_sharpe < 0.10:
        print("\n  -> News-event edge MODERATE (p<0.10)")
    elif p_sharpe < 0.20:
        print("\n  -> News-event edge MARGINAL (p<0.20)")
    else:
        print("\n  -> Edge NOT specific to news events (likely just PEB-on-momentum)")

    out = Path(__file__).resolve().parent.parent / "data" / "backtests" / "null_random_ts.csv"
    pd.DataFrame({"sharpe": sharpes, "total_pnl": totals,
                   "win_rate": win_rates, "n_trades": n_trades}).to_csv(out, index=False)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
