"""Two robustness tests:

  A. Bootstrap CI on Sharpe / total P&L (resample trades with replacement).
  B. Inverse-strategy null: flip the direction filter (long when EMA slope < 0,
     short when slope > 0). If the inverse strategy is ALSO profitable, our
     trend filter is noise, not edge.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

from data_gc import load as gc_load
from calendar_events import build_all
from mers_v5 import run_v5, peb_event_v5, dedupe_co_released, TOP_EVENTS_V5, TREND_N
from mers_v3_peb import compute_atr
from backtest import summarize, print_summary

# ---- A. Bootstrap CI ----

def bootstrap_sharpe_ci(trades: pd.DataFrame, n_boot=5000, alpha=0.05, rng=None):
    rng = rng or np.random.default_rng(123)
    n = len(trades)
    pnl = trades["net_pnl"].values
    boot_sharpes = []
    boot_totals = []
    boot_winrates = []
    for _ in range(n_boot):
        sample = rng.choice(pnl, size=n, replace=True)
        std = sample.std()
        s = (sample.mean() / std * np.sqrt(252)) if std > 0 else np.nan
        boot_sharpes.append(s)
        boot_totals.append(sample.sum())
        boot_winrates.append((sample > 0).mean())
    boot_sharpes = np.array(boot_sharpes)
    boot_totals = np.array(boot_totals)
    boot_winrates = np.array(boot_winrates)
    return {
        "sharpe_mean": np.nanmean(boot_sharpes),
        "sharpe_lo": np.nanpercentile(boot_sharpes, alpha/2*100),
        "sharpe_hi": np.nanpercentile(boot_sharpes, (1 - alpha/2)*100),
        "total_lo": np.nanpercentile(boot_totals, alpha/2*100),
        "total_hi": np.nanpercentile(boot_totals, (1 - alpha/2)*100),
        "winrate_lo": np.nanpercentile(boot_winrates, alpha/2*100),
        "winrate_hi": np.nanpercentile(boot_winrates, (1 - alpha/2)*100),
        "p_sharpe_positive": (boot_sharpes > 0).mean(),
        "p_total_positive": (boot_totals > 0).mean(),
    }


# ---- B. Inverse strategy (flip trend filter) ----

def peb_event_v5_inverse(bars, ev_ts, freq, atr, ema_slope, **kw):
    """Identical to peb_event_v5 but with INVERTED trend filter.
    Long only when slope < 0, short only when slope > 0.
    """
    # We re-implement by calling base then flipping condition.
    # Simpler: monkey-patch the slope sign by inverting the slope series in caller.
    pass  # handled via slope inversion in run_inverse below


def run_inverse(bars, events, event_filter=TOP_EVENTS_V5):
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=TREND_N, adjust=False).mean()
    slope = ema.diff(5)
    inv_slope = -slope  # flip the trend filter direction

    events = dedupe_co_released(events)
    rows = []
    for _, ev in events.iterrows():
        if ev["event"] not in event_filter:
            continue
        t = peb_event_v5(bars, ev["ts_utc"], freq, atr, inv_slope)
        if t is None:
            continue
        t["event_type"] = ev["event"]
        rows.append(t)
    return pd.DataFrame(rows)


def main():
    bars = gc_load("60m").sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    events = build_all()

    # Real
    real = run_v5(bars, events)
    real_s = summarize(real, label="REAL v5")
    print("="*100)
    print("A. BOOTSTRAP CI (real trades)")
    print("="*100)
    print_summary(real_s)

    ci = bootstrap_sharpe_ci(real, n_boot=5000)
    print(f"\n  Sharpe   95% CI: [{ci['sharpe_lo']:+.3f}, {ci['sharpe_hi']:+.3f}]  "
          f"mean={ci['sharpe_mean']:+.3f}")
    print(f"  Total $  95% CI: [${ci['total_lo']:+,.0f}, ${ci['total_hi']:+,.0f}]")
    print(f"  Win rate 95% CI: [{ci['winrate_lo']*100:.1f}%, {ci['winrate_hi']*100:.1f}%]")
    print(f"  P(bootstrap Sharpe > 0): {ci['p_sharpe_positive']*100:.1f}%")
    print(f"  P(bootstrap total$ > 0): {ci['p_total_positive']*100:.1f}%")

    print("\n" + "="*100)
    print("B. INVERSE-STRATEGY NULL (flip trend filter)")
    print("="*100)
    inv = run_inverse(bars, events)
    inv_s = summarize(inv, label="INVERSE v5")
    print_summary(real_s)
    print_summary(inv_s)

    # Comparison
    if real_s["n"] and inv_s["n"]:
        print(f"\n  Real:    n={real_s['n']:3d}, sharpe={real_s['sharpe_per_trade']:+.2f}, "
              f"total=${real_s['total_net_pnl']:+,.0f}, win%={real_s['win_rate']*100:.1f}")
        print(f"  Inverse: n={inv_s['n']:3d}, sharpe={inv_s['sharpe_per_trade']:+.2f}, "
              f"total=${inv_s['total_net_pnl']:+,.0f}, win%={inv_s['win_rate']*100:.1f}")
        if inv_s["total_net_pnl"] < 0 and real_s["total_net_pnl"] > 0:
            print("\n  -> Trend filter is a REAL edge: inverse loses, real wins.")
        elif abs(inv_s["total_net_pnl"]) < real_s["total_net_pnl"] * 0.5:
            print("\n  -> Trend filter HELPS: real significantly beats inverse.")
        else:
            print("\n  -> Trend filter is WEAK: inverse comparable to real.")


if __name__ == "__main__":
    main()
