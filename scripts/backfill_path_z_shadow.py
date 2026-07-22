"""Path Z-specific shadow backfill.

Runs the ORB pipeline on a Dukascopy 5m CSV using SESSION_CONFIGS_V9_Z
(no or_atr_max on NY), applies filter_path_z, and simulates outcomes for
Path Z-taken entries.

Default symbol: XAUUSD (canonical Path Z in-sample). Pass --symbol to
run on silver / FX for cross-market confirmation of the NY-SHORT-Low-ER
sub-edge. Output goes to data/shadow_equity_path_z_{SYMBOL}.jsonl
(XAUUSD keeps the historical filename data/shadow_equity_path_z.jsonl).

Usage:
  python scripts/backfill_path_z_shadow.py [--symbol XAUUSD|XAGUSD|EURUSD|GBPUSD|USDJPY]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mers_v3_peb import compute_atr
from regime_context import _efficiency_ratio, build_regime_context
from strategy_engine import (
    Direction,
    OrContext,
    SESSION_CONFIGS_V9_Z,
    evaluate_session,
)

# Per-market contract sizing + round-trip cost.
# XAUUSD: GC-equivalent (100 oz × $1/point, ~$24 RT).
# XAGUSD: SI-equivalent (5000 oz × $1/point, ~$16 RT).
# FX: standard lot = 100,000 units of base currency. RT ~$7 (IB).
# All values chosen so 1 "point" (1 unit of price) × contract_size = dollar P&L.
# The absolute $ figures are approximate — the R-multiple report is the
# apples-to-apples cross-market comparison. This is exploratory, not a
# ship-gate rerun.
MARKET_SPECS = {
    "XAUUSD": {"contract_size": 100,    "rt_cost": 24.0},
    "XAGUSD": {"contract_size": 5000,   "rt_cost": 16.0},
    "EURUSD": {"contract_size": 100000, "rt_cost": 7.0},
    "GBPUSD": {"contract_size": 100000, "rt_cost": 7.0},
    "USDJPY": {"contract_size": 100000, "rt_cost": 7.0},
}

OR_BARS = 6
WATCH_BARS = 12
MAX_HOLD_BARS = 36
ER_LOOKBACK = 20

# Session UTC opens matching production
SESSIONS_UTC = {"LON": 6, "NY": 13, "ASIA": 22}


def load_bars(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["ts"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df


def slope_5h(bars_1h: pd.Series, up_to_ts) -> float:
    seg = bars_1h[bars_1h.index <= up_to_ts]
    if len(seg) < 55:
        return 0.0
    ema = seg.ewm(span=50, adjust=False).mean()
    return float(ema.iloc[-1] - ema.iloc[-6])


def simulate(bars: pd.DataFrame, entry_idx: int, entry: float,
             stop: float, target: float, direction: str,
             contract_size: float, rt_cost: float) -> dict:
    dir_sign = 1 if direction == "LONG" else -1
    exit_price = None
    exit_reason = None
    for k in range(MAX_HOLD_BARS + 1):
        if entry_idx + k >= len(bars):
            break
        b = bars.iloc[entry_idx + k]
        if direction == "LONG":
            hit_stop = b["low"] <= stop
            hit_tp = b["high"] >= target
        else:
            hit_stop = b["high"] >= stop
            hit_tp = b["low"] <= target
        if hit_stop and hit_tp:
            exit_price = stop; exit_reason = "stop_conservative"; break
        if hit_stop:
            exit_price = stop; exit_reason = "stop"; break
        if hit_tp:
            exit_price = target; exit_reason = "target"; break
    if exit_price is None:
        end_idx = min(entry_idx + MAX_HOLD_BARS, len(bars) - 1)
        exit_price = float(bars.iloc[end_idx]["close"])
        exit_reason = "time"
    gross = (exit_price - entry) * dir_sign * contract_size
    net = gross - rt_cost
    return {"kind": exit_reason, "exit_price": float(exit_price),
            "gross_pnl": float(gross), "net_pnl": float(net)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD", choices=list(MARKET_SPECS))
    args = ap.parse_args()
    symbol = args.symbol
    spec = MARKET_SPECS[symbol]
    contract_size = spec["contract_size"]
    rt_cost = spec["rt_cost"]

    csv_path = ROOT / "data" / "external" / "dukascopy" / f"{symbol}_5m.csv"
    # Preserve historical XAUUSD filename; new symbols get suffixed files.
    if symbol == "XAUUSD":
        out_path = ROOT / "data" / "shadow_equity_path_z.jsonl"
    else:
        out_path = ROOT / "data" / f"shadow_equity_path_z_{symbol}.jsonl"

    print(f"Symbol: {symbol}  contract={contract_size} RT_cost=${rt_cost}")
    print(f"Loading bars from {csv_path.name} ...")
    bars = load_bars(csv_path)
    print(f"  {len(bars):,} bars {bars.index[0].date()} -> {bars.index[-1].date()}")

    atr = compute_atr(bars, 20)
    bars_1h = bars["close"].resample("1h").last().dropna()

    # We only care about NY session for Path Z (filter blocks other sessions)
    sess_name = "NY"
    cfg = SESSION_CONFIGS_V9_Z[sess_name]
    sess_hour = SESSIONS_UTC[sess_name]

    all_rows = []
    path_z_taken = 0
    path_z_skipped = 0
    for date in sorted(set(bars.index.date)):
        d = pd.Timestamp(date, tz="UTC")
        if d.weekday() == 5:  # Saturday
            continue
        open_ts = d + pd.Timedelta(hours=sess_hour)
        or_close_ts = open_ts + pd.Timedelta(minutes=30)

        or_slice = bars[(bars.index >= open_ts) & (bars.index < or_close_ts)]
        if len(or_slice) < OR_BARS:
            continue
        or_slice = or_slice.iloc[:OR_BARS]
        or_high = float(or_slice["high"].max())
        or_low = float(or_slice["low"].min())
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        or_close_actual = or_slice.index[-1]
        or_close_idx = bars.index.get_loc(or_close_actual)

        cur_atr = float(atr.iloc[or_close_idx])
        if cur_atr <= 0:
            continue

        cur_slope = slope_5h(bars_1h, or_close_actual)

        # ER on last 21 5m closes
        closes_pre = bars.iloc[max(0, or_close_idx - 20): or_close_idx + 1]["close"].tolist()
        er = _efficiency_ratio(closes_pre, n=20)

        # Build OrContext + evaluate under V9_Z config
        or_ctx = OrContext(
            session_open_utc=open_ts,
            or_close_utc=or_close_actual,
            or_high=or_high, or_low=or_low, or_range=or_range,
            atr_at_close=cur_atr, slope_at_close=cur_slope,
            or_bars_df=or_slice,
        )
        regime = build_regime_context(or_close_actual, efficiency_ratio_5m_20=er)
        decision = evaluate_session(cfg, or_ctx, regime)

        if not decision.would_take:
            path_z_skipped += 1
            continue

        # Simulate breakout in watch window
        entry_idx = None
        entry_price = None
        for k in range(WATCH_BARS):
            i = or_close_idx + 1 + k
            if i >= len(bars):
                break
            b = bars.iloc[i]
            if decision.direction == Direction.LONG and b["high"] >= or_high:
                entry_idx = i; entry_price = or_high; break
            if decision.direction == Direction.SHORT and b["low"] <= or_low:
                entry_idx = i; entry_price = or_low; break
        if entry_idx is None:
            # No breakout — Path Z doesn't fire this session
            path_z_skipped += 1
            continue

        outcome = simulate(bars, entry_idx, entry_price,
                          decision.stop_price, decision.target_price,
                          decision.direction.name,
                          contract_size, rt_cost)

        # R-multiple = net P&L expressed as fraction of initial risk (1×OR).
        # Cross-market comparable. Positive R > 0.
        risk_dollars = or_range * contract_size
        r_multiple = outcome["net_pnl"] / risk_dollars if risk_dollars > 0 else 0.0

        row = {
            "ts_recorded_utc": datetime.utcnow().isoformat() + "Z",
            "symbol": symbol,
            "session": sess_name,
            "or_open_utc": open_ts.isoformat(),
            "or_close_utc": or_close_actual.isoformat(),
            "or_high": or_high, "or_low": or_low, "or_range": or_range,
            "atr": cur_atr,
            "or_atr_ratio": or_range / cur_atr,
            "trend_slope": cur_slope,
            "direction_bias": decision.direction.name,
            "would_skip": False,
            "skip_reason": None,
            "entry_price": entry_price,
            "target_price": decision.target_price,
            "stop_price": decision.stop_price,
            "outcome": outcome,
            "r_multiple": r_multiple,
            "strategy_version": "v9-path-z-backfill",
            "candidate_shadows": {
                "path_z": {
                    "would_skip": False,
                    "would_take": True,
                    "skip_reason": None,
                    "er_5m_20": er,
                    "dow": ("Mon","Tue","Wed","Thu","Fri","Sat","Sun")[open_ts.weekday()],
                }
            },
        }
        all_rows.append(row)
        path_z_taken += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, default=str) + "\n")

    print(f"\nPath Z taken:   {path_z_taken}")
    print(f"Path Z skipped: {path_z_skipped}")
    print(f"Wrote {len(all_rows)} rows to {out_path.name}")

    if all_rows:
        pnls = [r["outcome"]["net_pnl"] for r in all_rows]
        rs = [r["r_multiple"] for r in all_rows]
        wins = sum(1 for p in pnls if p > 0)
        total = sum(pnls)
        r_total = sum(rs)
        print(f"\nTotal P&L    = ${total:+,.0f}")
        print(f"Mean/trade   = ${total/len(pnls):+,.2f}")
        print(f"Win rate     = {100*wins/len(pnls):.1f}%")
        print(f"Total R      = {r_total:+.2f}")
        print(f"Mean R/trade = {r_total/len(rs):+.3f}")


if __name__ == "__main__":
    main()
