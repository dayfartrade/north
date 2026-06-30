"""MERS v5 — Elevated: dedup co-released events + ATR risk management.

Changes from v4:
  1. Co-released events (NFP & UNRATE at same timestamp) are collapsed to ONE
     trade. We label it "JOBS" for the combined event.
  2. Exit logic: ATR stop-loss + ATR take-profit + time-based backstop.
     Bar-by-bar simulation: whichever hits first.
     Conservative tie-breaking when both stop and target inside same bar:
       - if direction is favorable (high before low for longs), assume stop hit
         first (worst case for us). This avoids look-ahead optimism.
  3. Returns full trade record including exit_reason.

Frozen v5 params (decided BEFORE the new robustness sweep):
  watch_bars   = 2
  max_hold     = 6  (slightly longer — let target run if no stop)
  b_atr        = 0.10
  stop_atr     = 1.5
  tp_atr       = 2.5  (positive expected R = 1.67 on winners)
  trend_n      = 50
  events       = ("FOMC", "JOBS", "CPI")    # JOBS = NFP/UNRATE combo
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from data_gc import load as gc_load
from calendar_events import build_all
from backtest import CONTRACT_SIZE, RT_COST_PER_CONTRACT, summarize, print_summary, OUT_DIR
from mers_v3_peb import compute_atr

# ---- Frozen v5 parameters ----
WATCH = 2
MAX_HOLD = 6
B_ATR = 0.10
STOP_MULT = 1.0    # stop = 1.0 * event-bar range below/above entry
TP_MULT = 2.0      # target = 2.0 * event-bar range (R:R = 2:1)
TREND_N = 50
TOP_EVENTS_V5 = ("FOMC", "JOBS", "CPI")


def dedupe_co_released(events: pd.DataFrame) -> pd.DataFrame:
    """Collapse same-timestamp NFP and UNRATE rows into a single JOBS row."""
    df = events.copy()
    nfp_unrate_mask = df["event"].isin(("NFP", "UNRATE"))
    # rows at same ts_utc with NFP+UNRATE: collapse to JOBS
    keys = df.loc[nfp_unrate_mask].groupby("ts_utc").size()
    coreleased_ts = keys[keys >= 2].index
    if len(coreleased_ts) == 0:
        return df

    keep_mask = ~((df["event"].isin(("NFP", "UNRATE"))) & (df["ts_utc"].isin(coreleased_ts)))
    out = df[keep_mask].copy()
    jobs_rows = []
    for ts in coreleased_ts:
        sub = df[(df["ts_utc"] == ts) & nfp_unrate_mask]
        # Use NFP's surprise as primary; if missing, UNRATE's negated
        row = {"ts_utc": ts, "event": "JOBS"}
        nfp = sub[sub["event"] == "NFP"]
        if not nfp.empty and pd.notna(nfp["surprise_z"].iloc[0]):
            row["surprise_z"] = nfp["surprise_z"].iloc[0]
        else:
            unr = sub[sub["event"] == "UNRATE"]
            row["surprise_z"] = -unr["surprise_z"].iloc[0] if not unr.empty and pd.notna(unr["surprise_z"].iloc[0]) else np.nan
        row["expected_dir"] = 0
        row["value"] = pd.NA; row["prior"] = pd.NA; row["delta"] = pd.NA
        row["trailing_mean"] = pd.NA; row["trailing_std"] = pd.NA
        jobs_rows.append(row)
    jobs_df = pd.DataFrame(jobs_rows)
    out = pd.concat([out, jobs_df], ignore_index=True).sort_values("ts_utc").reset_index(drop=True)
    return out


def peb_event_v5(bars, ev_ts, freq, atr, ema_slope,
                  watch=WATCH, max_hold=MAX_HOLD, b_atr=B_ATR,
                  stop_mult=1.0, tp_mult=2.0):
    """Stop = stop_mult * event-bar range (natural, adapts to event vol).
    Target = tp_mult * event-bar range (R:R = tp_mult/stop_mult).
    """
    ts = pd.Timestamp(ev_ts).tz_convert("UTC")
    # Find the bar whose [start, start+freq) contains ts. Works for any alignment.
    mask = (bars.index <= ts) & (bars.index + freq > ts)
    matches = bars.index[mask]
    if len(matches) == 0:
        return None
    bar_ts = matches[-1]
    i = bars.index.get_loc(bar_ts)
    if i < max(25, TREND_N + 2) or i + watch + max_hold + 1 >= len(bars):
        return None
    pre_atr = float(atr.iloc[i - 1])
    if not np.isfinite(pre_atr) or pre_atr <= 0:
        return None
    slope = float(ema_slope.iloc[i - 1])
    if not np.isfinite(slope):
        return None

    ev_bar = bars.iloc[i]
    ev_range = float(ev_bar["high"] - ev_bar["low"])
    buffer = b_atr * pre_atr
    long_trig = ev_bar["high"] + buffer
    short_trig = ev_bar["low"] - buffer

    # Find entry trigger
    entry_dir = 0
    entry_idx = None
    entry_price = None
    for k in range(1, watch + 1):
        b = bars.iloc[i + k]
        hit_long = b["high"] >= long_trig
        hit_short = b["low"] <= short_trig
        if hit_long and hit_short:
            return None  # ambiguous
        if hit_long:
            if slope > 0:
                entry_dir = 1
                entry_idx = i + k
                entry_price = long_trig
            break
        if hit_short:
            if slope < 0:
                entry_dir = -1
                entry_idx = i + k
                entry_price = short_trig
            break

    if entry_dir == 0:
        return None

    # Stop = stop_mult * event-bar range on the OPPOSITE side; target = tp_mult * event-bar range in our favor
    stop_lvl = entry_price - stop_mult * ev_range * entry_dir
    target_lvl = entry_price + tp_mult * ev_range * entry_dir
    exit_price = None
    exit_idx = None
    exit_reason = None
    for k in range(0, max_hold + 1):
        if entry_idx + k >= len(bars):
            break
        b = bars.iloc[entry_idx + k]
        if entry_dir == 1:
            hit_stop = b["low"] <= stop_lvl
            hit_tp = b["high"] >= target_lvl
        else:
            hit_stop = b["high"] >= stop_lvl
            hit_tp = b["low"] <= target_lvl
        if hit_stop and hit_tp:
            # Conservative: assume stop hit first
            exit_price = stop_lvl
            exit_reason = "stop_conservative"
            exit_idx = entry_idx + k
            break
        if hit_stop:
            exit_price = stop_lvl
            exit_reason = "stop"
            exit_idx = entry_idx + k
            break
        if hit_tp:
            exit_price = target_lvl
            exit_reason = "target"
            exit_idx = entry_idx + k
            break
    if exit_price is None:
        exit_idx = min(entry_idx + max_hold, len(bars) - 1)
        exit_price = bars.iloc[exit_idx]["close"]
        exit_reason = "time"

    gross = (exit_price - entry_price) * entry_dir * CONTRACT_SIZE
    net = gross - RT_COST_PER_CONTRACT
    return {
        "event_ts": pd.Timestamp(ev_ts).tz_convert("UTC"),
        "event_bar_ts": bars.index[i],
        "entry_ts": bars.index[entry_idx],
        "exit_ts": bars.index[exit_idx],
        "direction": entry_dir,
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "stop_price": float(stop_lvl),
        "target_price": float(target_lvl),
        "trend_slope": slope,
        "pre_atr": pre_atr,
        "gross_pnl": float(gross),
        "net_pnl": float(net),
        "exit_reason": exit_reason,
    }


def run_v5(bars, events, event_filter=TOP_EVENTS_V5, **kwargs):
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    freq = pd.Timedelta(np.median(np.diff(bars.index.values)))
    atr = compute_atr(bars, 20)
    ema = bars["close"].ewm(span=TREND_N, adjust=False).mean()
    slope = ema.diff(5)
    events = dedupe_co_released(events)
    rows = []
    for _, ev in events.iterrows():
        if ev["event"] not in event_filter:
            continue
        t = peb_event_v5(bars, ev["ts_utc"], freq, atr, slope, **kwargs)
        if t is None:
            continue
        t["event_type"] = ev["event"]
        rows.append(t)
    return pd.DataFrame(rows)


def main():
    print("="*100)
    print("MERS v5 — Dedup co-released + event-bar-range risk-managed exit")
    print(f"Params: watch={WATCH}, max_hold={MAX_HOLD}, buf={B_ATR}*ATR, "
          f"stop={STOP_MULT}*ev_range, tp={TP_MULT}*ev_range, trend_n={TREND_N}")
    print(f"Events: {TOP_EVENTS_V5}")
    print("="*100)

    events = build_all()
    gc1h = gc_load("60m")
    trades = run_v5(gc1h, events)
    if trades.empty:
        print("No trades.")
        return
    trades = trades.sort_values("entry_ts").reset_index(drop=True)
    trades["year"] = pd.to_datetime(trades["entry_ts"]).dt.year

    print_summary(summarize(trades, label="ALL"))
    print("\n[Per year]")
    for y, g in trades.groupby("year"):
        print_summary(summarize(g, label=f"year={y}"))
    print("\n[Half-split]")
    mid = len(trades) // 2
    print_summary(summarize(trades.iloc[:mid], label="first-half"))
    print_summary(summarize(trades.iloc[mid:], label="second-half"))
    print("\n[Per event]")
    for ev_type in TOP_EVENTS_V5:
        g = trades[trades["event_type"] == ev_type]
        if g.empty:
            continue
        print_summary(summarize(g, label=ev_type))
    print("\n[Exit reasons]")
    for r, g in trades.groupby("exit_reason"):
        n_pos = (g["net_pnl"] > 0).sum()
        print(f"  {r:20s} n={len(g):3d}  pos={n_pos}  mean=${g['net_pnl'].mean():+.2f}  total=${g['net_pnl'].sum():+.0f}")
    print("\n[Direction]")
    for d in (1, -1):
        g = trades[trades["direction"] == d]
        if g.empty: continue
        print_summary(summarize(g, label="longs" if d==1 else "shorts"))

    n = trades["net_pnl"]
    topk = max(1, len(n)//10)
    print(f"\n[Concentration]  top-10% / total = {n.nlargest(topk).sum()/n.sum()*100:.1f}%")


if __name__ == "__main__":
    main()
