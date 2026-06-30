"""Validate Session ORB with frozen params + random-timestamp null test.

Frozen params (chosen for robustness, not maxed):
  or_bars = 6  (30-min opening range)
  watch = 12   (60-min breakout window)
  hold = 24    (2-hour max hold)
  tp_mult = 1.5
  stop_mult = 1.0
  require_trend = True

Null test: instead of using true session-open times, draw random 5m timestamps
matching the count of real sessions. If the edge persists at random times, the
session-open structure isn't doing the work.
"""
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from backtest import summarize, print_summary, CONTRACT_SIZE, RT_COST_PER_CONTRACT
from edge_session_orb import run_orb, SESSIONS, find_session_starts, fetch_higher_tf_trend
from mers_v3_peb import compute_atr

FROZEN = dict(or_bars=6, watch_bars=12, max_hold=24,
              tp_mult=1.5, stop_mult=1.0, require_trend=True)


def run_orb_with_starts(bars, starts: list, label: str, **kw):
    """Variant that takes explicit start timestamps (for null test)."""
    bars = bars.sort_index()
    if bars.index.tz is None: bars.index = bars.index.tz_localize("UTC")
    atr = compute_atr(bars, 20)
    trend_slope = fetch_higher_tf_trend(bars)
    rows = []
    or_bars = kw.get("or_bars", 6)
    watch_bars = kw.get("watch_bars", 12)
    max_hold = kw.get("max_hold", 24)
    stop_mult = kw.get("stop_mult", 1.0)
    tp_mult = kw.get("tp_mult", 1.5)
    require_trend = kw.get("require_trend", True)

    for s_ts in starts:
        if s_ts not in bars.index:
            continue
        s_idx = bars.index.get_loc(s_ts)
        if s_idx + or_bars + watch_bars + max_hold + 1 >= len(bars):
            continue
        or_window = bars.iloc[s_idx: s_idx + or_bars]
        or_high = float(or_window["high"].max())
        or_low = float(or_window["low"].min())
        or_range = or_high - or_low
        if or_range <= 0:
            continue
        slope = float(trend_slope.iloc[s_idx + or_bars - 1])
        if not np.isfinite(slope):
            continue
        entry_dir = 0
        entry_idx = None
        entry_price = None
        for k in range(watch_bars):
            i = s_idx + or_bars + k
            b = bars.iloc[i]
            hit_long = b["high"] >= or_high
            hit_short = b["low"] <= or_low
            if hit_long and hit_short:
                continue
            if hit_long:
                if not require_trend or slope > 0:
                    entry_dir = 1; entry_idx = i; entry_price = or_high
                break
            if hit_short:
                if not require_trend or slope < 0:
                    entry_dir = -1; entry_idx = i; entry_price = or_low
                break
        if entry_dir == 0:
            continue
        stop_lvl = entry_price - stop_mult * or_range * entry_dir
        target_lvl = entry_price + tp_mult * or_range * entry_dir
        exit_price = None; exit_idx = None
        for k in range(max_hold + 1):
            if entry_idx + k >= len(bars): break
            b = bars.iloc[entry_idx + k]
            if entry_dir == 1:
                hit_stop = b["low"] <= stop_lvl
                hit_tp = b["high"] >= target_lvl
            else:
                hit_stop = b["high"] >= stop_lvl
                hit_tp = b["low"] <= target_lvl
            if hit_stop and hit_tp:
                exit_price = stop_lvl; exit_idx = entry_idx + k; break
            if hit_stop:
                exit_price = stop_lvl; exit_idx = entry_idx + k; break
            if hit_tp:
                exit_price = target_lvl; exit_idx = entry_idx + k; break
        if exit_price is None:
            exit_idx = min(entry_idx + max_hold, len(bars) - 1)
            exit_price = float(bars.iloc[exit_idx]["close"])
        gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
        net = gross - RT_COST_PER_CONTRACT
        rows.append({"session": label, "entry_ts": bars.index[entry_idx],
                     "exit_ts": bars.index[exit_idx], "direction": entry_dir,
                     "entry_price": float(entry_price), "exit_price": float(exit_price),
                     "gross_pnl": float(gross), "net_pnl": float(net)})
    return pd.DataFrame(rows)


def main():
    print("="*100)
    print(f"ORB validation — FROZEN params: {FROZEN}")
    print("="*100)
    bars = gc_load("5m").sort_index()
    if bars.index.tz is None: bars.index = bars.index.tz_localize("UTC")

    print("\nReal session results:")
    all_trades = []
    for name, t in SESSIONS.items():
        trades = run_orb(bars, t, name, **FROZEN)
        print_summary(summarize(trades, label=name))
        all_trades.append(trades)
    combined = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    real_s = summarize(combined, label="ALL sessions combined")
    print_summary(real_s)

    # Real start count for null sizing
    real_starts_count = sum(len(find_session_starts(bars, t)) for t in SESSIONS.values())
    print(f"\nReal session starts: {real_starts_count}")

    # Null: random 5m timestamps, NOT at session-open times
    sess_times = set(SESSIONS.values())
    valid = bars.index[25:-50]
    avoid = set()
    for ts in valid:
        if ts.time() in sess_times:
            avoid.add(ts)
    candidates = [t for t in valid if t not in avoid]

    n_paths = 200
    rng = np.random.default_rng(42)
    sharpes, totals, win_rates, n_trades = [], [], [], []
    print(f"\nRunning {n_paths} random-timestamp nulls...")
    for p in range(n_paths):
        random_starts = list(rng.choice(candidates, size=real_starts_count, replace=False))
        random_starts = [pd.Timestamp(t) for t in random_starts]
        trades = run_orb_with_starts(bars, random_starts, "RND", **FROZEN)
        s = summarize(trades, label=f"null_{p}")
        if s["n"] >= 5:
            sharpes.append(s["sharpe_per_trade"])
            totals.append(s["total_net_pnl"])
            win_rates.append(s["win_rate"])
            n_trades.append(s["n"])
        if (p + 1) % 50 == 0:
            print(f"  {p+1}/{n_paths}  last n={s['n']} sharpe={s['sharpe_per_trade']:+.2f}")

    sharpes = np.array(sharpes); totals = np.array(totals); win_rates = np.array(win_rates)

    print("\n=== Random-timestamp NULL distribution ===")
    print(f"Paths used: {len(sharpes)}")
    print(f"Sharpe:    mean={sharpes.mean():+.2f}  q05={np.percentile(sharpes, 5):+.2f}  q95={np.percentile(sharpes, 95):+.2f}")
    print(f"Total $:   mean=${totals.mean():+.0f}  q05=${np.percentile(totals, 5):+.0f}  q95=${np.percentile(totals, 95):+.0f}")
    print(f"Win rate:  mean={win_rates.mean()*100:.1f}%  q95={np.percentile(win_rates, 95)*100:.1f}%")

    p_sharpe = (sharpes >= real_s["sharpe_per_trade"]).mean()
    p_total = (totals >= real_s["total_net_pnl"]).mean()
    p_winrate = (win_rates >= real_s["win_rate"]).mean()
    print("\n=== P-values ===")
    print(f"  P(null sharpe >= real {real_s['sharpe_per_trade']:+.2f}):    {p_sharpe:.4f}")
    print(f"  P(null total$ >= real ${real_s['total_net_pnl']:+.0f}):    {p_total:.4f}")
    print(f"  P(null win%  >= real {real_s['win_rate']*100:.1f}%): {p_winrate:.4f}")

    if p_total < 0.05:
        print("\n  -> Session-open timing IS the edge (p<0.05)")
    elif p_total < 0.20:
        print("\n  -> Session timing MAY matter (p<0.20)")
    else:
        print("\n  -> Session timing NOT the source of edge — generic 5m PEB works just as well at random times")


if __name__ == "__main__":
    main()
