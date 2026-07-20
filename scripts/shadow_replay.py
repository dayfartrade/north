"""Shadow-replay: evaluate candidate filters against historical taken trades.

Read-only. Reads data/tracker/orb_forward_log.csv + macro CSVs + GC_1d.csv,
emits data/shadow_decisions_backfill.jsonl and prints a per-candidate summary.

Feature-selection use only. Not a ship gate — DSR discipline unchanged.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FWD_LOG = ROOT / "data" / "tracker" / "orb_forward_log.csv"
GC_1D = ROOT / "data" / "gc" / "GC_1d.csv"
REAL_YIELD = ROOT / "data" / "macro" / "real_yield_10y__DFII10.csv"
DXY = ROOT / "data" / "macro" / "dxy_proxy__DTWEXBGS.csv"
TNX = ROOT / "data" / "macro" / "tnx_10y__DGS10.csv"
OUT = ROOT / "data" / "shadow_decisions_backfill.jsonl"


def load_daily(path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                out[row["date"][:10]] = float(row["value"])
            except (ValueError, KeyError):
                continue
    return out


def load_gc_daily(path: Path) -> dict[str, tuple[float, float, float]]:
    out: dict[str, tuple[float, float, float]] = {}
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                d = row["ts"][:10]
                out[d] = (float(row["high"]), float(row["low"]), float(row["close"]))
            except (ValueError, KeyError):
                continue
    return out


def prior_trading_day(dates_sorted: list[str], d: str) -> str | None:
    for prev in reversed(dates_sorted):
        if prev < d:
            return prev
    return None


def last_value_on_or_before(daily: dict[str, float], d: str) -> float | None:
    key = None
    for k in daily:
        if k <= d:
            if key is None or k > key:
                key = k
    return daily.get(key) if key else None


CANDIDATES = [
    ("real_yield_gt_2_2", "skip LONG when real_yield >= 2.2"),
    ("slope_gt_8", "skip LONG when trend_slope > 8.0"),
    ("prior_day_range_gt_80", "skip when prior-day GC range > 80 pt"),
    ("gap_after_down_day", "skip LONG when prior day closed >= 30pt lower"),
    ("daily_slope_consistency", "skip when intraday direction opposes 20d daily GC slope"),
]


def daily_20d_slope(dates_sorted: list[str], gc: dict[str, tuple[float, float, float]],
                     d: str, lookback: int = 20) -> float | None:
    """Linear-regression slope of last `lookback` daily GC closes strictly before d."""
    prior = [gc[k][2] for k in dates_sorted if k < d]  # gc tuple is (hi, lo, close)
    if len(prior) < lookback:
        return None
    ys = prior[-lookback:]
    n = len(ys)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return None
    return num / den


def evaluate(feats: dict, direction: float) -> dict:
    is_long = direction == 1.0
    d: dict[str, dict] = {}

    ry = feats.get("real_yield")
    d["real_yield_gt_2_2"] = {
        "would_skip": bool(is_long and ry is not None and ry >= 2.2),
        "feature_value": ry,
    }

    slope = feats.get("trend_slope")
    d["slope_gt_8"] = {
        "would_skip": bool(is_long and slope is not None and slope > 8.0),
        "feature_value": slope,
    }

    pdr = feats.get("prior_day_range")
    d["prior_day_range_gt_80"] = {
        "would_skip": bool(pdr is not None and pdr > 80.0),
        "feature_value": pdr,
    }

    gap = feats.get("prior_day_close_change")
    d["gap_after_down_day"] = {
        "would_skip": bool(is_long and gap is not None and gap <= -30.0),
        "feature_value": gap,
    }

    dsl = feats.get("daily_20d_slope")
    intraday_slope = feats.get("trend_slope")
    if dsl is None or intraday_slope is None or dsl == 0 or intraday_slope == 0:
        would_skip_dsc = False
    else:
        dsc_intra_sign = 1 if intraday_slope > 0 else -1
        dsc_daily_sign = 1 if dsl > 0 else -1
        would_skip_dsc = dsc_intra_sign != dsc_daily_sign
    d["daily_slope_consistency"] = {
        "would_skip": would_skip_dsc,
        "feature_value": dsl,
    }

    return d


def main() -> None:
    real_yield = load_daily(REAL_YIELD)
    dxy = load_daily(DXY)
    tnx = load_daily(TNX)
    gc = load_gc_daily(GC_1D)
    gc_dates = sorted(gc.keys())

    out_rows = []
    with open(FWD_LOG, newline="") as f:
        for row in csv.DictReader(f):
            if row["took_trade"] != "True":
                continue
            try:
                entry_ts = row["entry_ts"]
                d = entry_ts[:10]
                direction = float(row["direction"])
                net_pnl = float(row["net_pnl"])
                trend_slope = float(row["trend_slope"])
                or_range = float(row["or_range"])
                session = row["session"]
            except (ValueError, KeyError):
                continue

            prev_d = prior_trading_day(gc_dates, d)
            if prev_d:
                hi, lo, cl = gc[prev_d]
                prior_range = hi - lo
                # entry-day open ≈ prior close proxy; use current-day open if avail
                cur = gc.get(d)
                prior_close_change = (cur[2] - cl) if cur else None
            else:
                prior_range = None
                prior_close_change = None

            feats = {
                "trend_slope": trend_slope,
                "or_range": or_range,
                "real_yield": last_value_on_or_before(real_yield, d),
                "dxy": last_value_on_or_before(dxy, d),
                "tnx": last_value_on_or_before(tnx, d),
                "prior_day_range": prior_range,
                "prior_day_close_change": prior_close_change,
                "daily_20d_slope": daily_20d_slope(gc_dates, gc, d),
            }

            decisions = evaluate(feats, direction)
            out_rows.append(
                {
                    "ts_recorded_utc": datetime.now(timezone.utc).isoformat(),
                    "entry_ts": entry_ts,
                    "session": session,
                    "direction": "LONG" if direction == 1.0 else "SHORT",
                    "net_pnl": net_pnl,
                    "win": net_pnl > 0,
                    "features": feats,
                    "shadow_decisions": decisions,
                }
            )

    OUT.write_text("\n".join(json.dumps(r) for r in out_rows) + "\n")

    # Summary
    total = len(out_rows)
    wins = sum(1 for r in out_rows if r["win"])
    losses = total - wins
    net = sum(r["net_pnl"] for r in out_rows)
    print(f"trades={total}  wins={wins}  losses={losses}  net=${net:,.0f}")
    print(f"{'candidate':30s} {'skips':>6s} {'W_skip':>7s} {'L_skip':>7s} {'net_after':>11s} {'delta':>9s}")
    for key, _desc in CANDIDATES:
        skipped = [r for r in out_rows if r["shadow_decisions"][key]["would_skip"]]
        s_wins = sum(1 for r in skipped if r["win"])
        s_losses = sum(1 for r in skipped if not r["win"])
        net_after = sum(r["net_pnl"] for r in out_rows if not r["shadow_decisions"][key]["would_skip"])
        delta = net_after - net
        print(f"{key:30s} {len(skipped):6d} {s_wins:7d} {s_losses:7d} ${net_after:>10,.0f} ${delta:>+8,.0f}")

    print(f"\nwrote {len(out_rows)} rows -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
