"""Cost-model calibration — compare modeled entry slippage to observed
Bitget fills over the auto-trader window.

src/cost_model.py bakes in DEFAULT_SLIPPAGE_PCT = 0.0005 (5 bps adverse
per side) as the assumption underlying setups.realized_r_after_costs.
If actual live fills deviate materially, the drag row in the daily
report (shipped 762d88d) is misleading — either overstating or
understating what we're losing to execution.

This script compares:
- Modeled per-side slippage:  DEFAULT_SLIPPAGE_PCT = 5.00 bps
- Observed entry slippage:    bps between setups.entry_price (intended
                              at emit) and auto_trader_orders.fill_price
                              (actual fill), signed per side so adverse
                              is positive.

Reports:
- Aggregate observed mean / median / p90 in bps
- Per-symbol breakdown
- Per-session breakdown
- Comparison line + verdict (modeled matches / underestimates / overestimates)

Read-only. Runnable from Atlas via:
    C:\\bots\\.venv\\Scripts\\python.exe scripts\\cost_model_calibration_2026_07_31.py

Design intent: gives operator + Janus a factual read on whether our cost
model reflects reality. If observed >> modeled, execution is silently
eating more edge than we know. If observed ~ modeled, cost model is
sound and the drag row is trustworthy for capital-scaling decisions.

Exit-side calibration is intentionally out of scope for v1. Requires
Bitget position-history integration (D2 reconciler infrastructure).
Follow-up work if entry-side reveals drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# Window: capital-scaling gate bucket start. Same sample the gate reads.
_BUCKET_START = "2026-07-13T00:00:00+00:00"

# From src/cost_model.py — the baseline we're calibrating.
DEFAULT_SLIPPAGE_BPS = 5.0   # 0.0005 = 5 bps per side


def _connect():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
    import os
    import psycopg
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set")
    return psycopg.connect(url)


from src.analysis_helpers import (  # noqa: E402
    entry_slippage_bps as _entry_slippage_bps,
    percentile as _percentile,
    session_bucket as _session_bucket,
)


def _fetch_fills(cur, since: str = _BUCKET_START) -> list[dict]:
    """Every filled auto-trader entry order since window start, joined
    to the setup's intended entry_price + side + symbol + emit time.

    Excludes orders where fill_price is NULL (never filled) or
    intended entry missing (schema edge case).
    """
    cur.execute("""
        SELECT
            s.symbol,
            s.side,
            s.entry_price   AS intended_entry,
            ao.fill_price   AS actual_fill,
            s.created_at    AS setup_created_at,
            ao.filled_at    AS entry_filled_at,
            ao.submitted_at AS entry_submitted_at
        FROM auto_trader_orders ao
        JOIN setups s ON s.id = ao.setup_id
        WHERE ao.order_type = 'entry'
          AND ao.status IN ('filled', 'partial')
          AND ao.fill_price IS NOT NULL
          AND s.entry_price IS NOT NULL
          AND ao.submitted_at >= %s::timestamptz
        ORDER BY ao.submitted_at ASC
    """, (since,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _verdict_line(observed_mean: float, observed_p90: float, n: int) -> tuple[str, str]:
    """Return (status_word, one-line summary)."""
    if n < 5:
        return "INSUFFICIENT", f"n={n} < 5 fills — sample too thin to calibrate"

    # Discipline: 5bps modeled is "typical adverse fill on majors at
    # small size." Underestimate = observed > modeled means model is
    # too generous; drag row will *understate* real drag.
    delta_mean = observed_mean - DEFAULT_SLIPPAGE_BPS
    # Bands:
    #  |delta| < 2bps         → MATCHES (model is close enough)
    #  observed > modeled+2   → UNDERESTIMATES (real drag > reported)
    #  observed < modeled-2   → OVERESTIMATES (real drag < reported)
    if abs(delta_mean) < 2.0:
        status = "MATCHES"
        note = (
            f"observed mean {observed_mean:+.2f}bps ~ modeled {DEFAULT_SLIPPAGE_BPS:+.2f}bps "
            f"(|delta|={abs(delta_mean):.2f}bps < 2bps threshold). "
            f"Cost model is calibrated for entry side; drag row trustworthy."
        )
    elif delta_mean > 0:
        status = "UNDERESTIMATES"
        note = (
            f"observed mean {observed_mean:+.2f}bps > modeled {DEFAULT_SLIPPAGE_BPS:+.2f}bps "
            f"by {delta_mean:+.2f}bps. Daily-report drag row is UNDERSTATING real drag. "
            f"Capital scaling should discount edge by an extra ~{delta_mean:.1f}bps/side."
        )
    else:
        status = "OVERESTIMATES"
        note = (
            f"observed mean {observed_mean:+.2f}bps < modeled {DEFAULT_SLIPPAGE_BPS:+.2f}bps "
            f"by {abs(delta_mean):.2f}bps. Daily-report drag row is OVERSTATING real drag. "
            f"True edge is a bit better than reported."
        )
    if observed_p90 > 2 * DEFAULT_SLIPPAGE_BPS:
        note += (
            f" NOTE: p90 {observed_p90:+.2f}bps is >2x modeled — tail risk on individual "
            f"fills is materially larger than the mean suggests."
        )
    return status, note


def main() -> int:
    with _connect() as conn, conn.cursor() as cur:
        fills = _fetch_fills(cur)

    print("COST-MODEL CALIBRATION — entry slippage")
    print("=" * 78)
    print(f"Sample window:    {_BUCKET_START} → now")
    print(f"Modeled per-side: {DEFAULT_SLIPPAGE_BPS:+.2f}bps (src/cost_model.py)")
    print(f"n_fills:          {len(fills)}")
    print()

    if not fills:
        print("No filled auto-trader entries in window.")
        return 0

    per_trade: list[dict] = []
    for f in fills:
        bps = _entry_slippage_bps(
            f.get("side"),
            float(f.get("intended_entry") or 0),
            float(f.get("actual_fill") or 0),
        )
        if bps is None:
            continue
        per_trade.append({
            "symbol": f.get("symbol"),
            "side": f.get("side"),
            "bps": bps,
            "session": _session_bucket(f.get("setup_created_at").hour)
                       if f.get("setup_created_at") else "?",
        })

    if not per_trade:
        print("All fills failed slippage computation.")
        return 0

    values = sorted(t["bps"] for t in per_trade)
    n = len(values)
    mean = sum(values) / n
    p50 = _percentile(values, 0.50)
    p90 = _percentile(values, 0.90)
    p10 = _percentile(values, 0.10)
    worst = max(values)
    best = min(values)
    n_adverse = sum(1 for v in values if v > 0)
    pct_adverse = 100.0 * n_adverse / n if n else 0

    print("AGGREGATE (observed entry slippage, bps — positive = adverse)")
    print(f"  n_valid:  {n}")
    print(f"  mean:     {mean:+.2f}bps")
    print(f"  median:   {p50:+.2f}bps")
    print(f"  p10-p90:  [{p10:+.2f}, {p90:+.2f}]bps")
    print(f"  range:    [{best:+.2f}, {worst:+.2f}]bps")
    print(f"  adverse:  {n_adverse}/{n} ({pct_adverse:.1f}%)")
    print()

    # By symbol
    sym_agg: dict = {}
    for t in per_trade:
        rec = sym_agg.setdefault(t["symbol"], [])
        rec.append(t["bps"])
    print("BY SYMBOL (mean bps, n)")
    for sym in sorted(sym_agg, key=lambda k: -sum(sym_agg[k]) / len(sym_agg[k])):
        vals = sym_agg[sym]
        print(f"  {sym:12}  n={len(vals):>2}  mean={sum(vals)/len(vals):+.2f}bps  "
              f"range=[{min(vals):+.2f},{max(vals):+.2f}]")
    print()

    # By session
    sess_agg: dict = {}
    for t in per_trade:
        rec = sess_agg.setdefault(t["session"], [])
        rec.append(t["bps"])
    print("BY SESSION (mean bps, n)")
    for s in ("asia", "eu_am", "us_am", "us_pm"):
        vals = sess_agg.get(s)
        if not vals:
            continue
        print(f"  {s:6}  n={len(vals):>2}  mean={sum(vals)/len(vals):+.2f}bps")
    print()

    status, note = _verdict_line(mean, p90, n)
    print(f"VERDICT: {status}")
    print(f"  {note}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
