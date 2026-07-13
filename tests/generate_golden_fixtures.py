"""Generate golden fixtures from orb_forward_log.csv taken trades.

For each historical taken trade, computes v8 strategy_engine's expected
decision and dumps to tests/fixtures/golden_trades.json.

Later golden-file tests (test_strategy_engine.py::TestGoldenFiles) load
this and assert current v8 code produces the same decisions.

Run: `python tests/generate_golden_fixtures.py`
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mers_v3_peb import compute_atr
from strategy_engine import (
    OrContext,
    RegimeContext,
    SESSION_CONFIGS_V8_INITIAL,
    evaluate_session,
)
from regime_context import build_regime_context


FWD = ROOT / "data/tracker/orb_forward_log.csv"
OUT = ROOT / "tests/fixtures/golden_trades.json"


def main() -> None:
    bars5 = pd.read_csv(ROOT / "data/gc/GC_5m.csv", parse_dates=["ts"]).set_index("ts").sort_index()
    if bars5.index.tz is None:
        bars5.index = bars5.index.tz_localize("UTC")
    atr_series = compute_atr(bars5, 20)

    bars1h = bars5["close"].resample("1h").last().dropna()
    ema = bars1h.ewm(span=50, adjust=False).mean()
    slope_1h = ema.diff(5).reindex(bars5.index, method="ffill")

    fixtures = []
    with open(FWD, newline="") as f:
        for row in csv.DictReader(f):
            if row["took_trade"] != "True":
                continue
            try:
                open_ts = pd.Timestamp(row["open_ts"])
                if open_ts.tz is None:
                    open_ts = open_ts.tz_localize("UTC")
                or_close_ts = open_ts + pd.Timedelta(minutes=30)
                mask = atr_series.index <= or_close_ts
                if not mask.any():
                    continue
                atr = float(atr_series.loc[atr_series.index <= or_close_ts].iloc[-1])
                slope = float(slope_1h.loc[slope_1h.index <= or_close_ts].iloc[-1])
                session = row["session"]
                or_high = float(row["or_high"])
                or_low = float(row["or_low"])
                or_range = float(row["or_range"])
                actual_direction = float(row["direction"])
                actual_net_pnl = float(row["net_pnl"])
            except (ValueError, KeyError):
                continue

            cfg = SESSION_CONFIGS_V8_INITIAL[session]
            ctx = OrContext(
                session_open_utc=open_ts,
                or_close_utc=or_close_ts,
                or_high=or_high,
                or_low=or_low,
                or_range=or_range,
                atr_at_close=atr,
                slope_at_close=slope,
                or_bars_df=pd.DataFrame(),
            )
            regime = build_regime_context(or_close_ts, or_atr_ratio=or_range / atr if atr > 0 else None, trend_slope=slope)

            decision = evaluate_session(cfg, ctx, regime)

            fixtures.append({
                "entry_ts": row["entry_ts"],
                "session": session,
                "actual": {
                    "direction": "LONG" if actual_direction == 1.0 else "SHORT",
                    "net_pnl": actual_net_pnl,
                },
                "v8_decision": {
                    "would_take": decision.would_take,
                    "would_skip_reasons": list(decision.would_skip_reasons),
                    "direction": decision.direction.name,
                    "entry_price": decision.entry_price,
                    "target_price": decision.target_price,
                    "stop_price": decision.stop_price,
                },
                "inputs": {
                    "or_high": or_high,
                    "or_low": or_low,
                    "or_range": or_range,
                    "atr": atr,
                    "slope": slope,
                    "or_atr_ratio": or_range / atr if atr > 0 else None,
                },
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": {
            "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "generator": "tests/generate_golden_fixtures.py",
            "strategy_version": "v8.0.0-sketch",
            "session_config": "SESSION_CONFIGS_V8_INITIAL (Path Y-matching)",
            "n_fixtures": len(fixtures),
        },
        "trades": fixtures,
    }
    OUT.write_text(json.dumps(payload, indent=2, default=str))

    n_take = sum(1 for f in fixtures if f["v8_decision"]["would_take"])
    n_skip = len(fixtures) - n_take
    n_actual_won = sum(1 for f in fixtures if f["actual"]["net_pnl"] > 0)

    print(f"Generated {len(fixtures)} fixtures -> {OUT.relative_to(ROOT)}")
    print(f"  v8 would_take: {n_take}")
    print(f"  v8 would_skip: {n_skip}")
    print(f"  actual wins: {n_actual_won}/{len(fixtures)}")

    # Divergence: v8 skip but actual took (would have prevented)
    prevent_wins = sum(1 for f in fixtures if not f["v8_decision"]["would_take"] and f["actual"]["net_pnl"] > 0)
    prevent_losses = sum(1 for f in fixtures if not f["v8_decision"]["would_take"] and f["actual"]["net_pnl"] <= 0)
    print(f"  v8 would-skip counterfactual: prevented {prevent_wins} wins, {prevent_losses} losses")


if __name__ == "__main__":
    main()
