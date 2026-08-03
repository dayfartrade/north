"""Exit-side slippage calibration — compares intended TP1/SL to actual
Bitget close_avg_price.

Complements entry-side cost_model_calibration_2026_07_31.py (which
INSUFFICIENT'd at n=2 because 11/13 filled entries had NULL fill_price
pre-backfill). This one queries Bitget position-history for actual
close prices and compares to the setup's intended exit prices.

Signed bps of adverse exit slippage (positive = worse for us):
- SHORT tp1_hit: adverse = close_avg > tp1 (covered higher than target)
- SHORT sl_hit:  adverse = close_avg > sl  (stop filled at worse price)
- LONG  tp1_hit: adverse = close_avg < tp1 (sold at worse TP1)
- LONG  sl_hit:  adverse = close_avg < sl  (stop filled at worse price)
- expired: no reference exit price → skip (closed at market on expiry)

Read-only. Requires SUPABASE_DB_URL + BITGET_API_KEY_RO trio (same
env as reconcile_auto_trader.py).

Atlas-runnable:
    C:\\bots\\.venv\\Scripts\\python.exe scripts\\exit_slippage_calibration_2026_07_31.py

Verdict thresholds (locked pre-run to prevent post-hoc tuning):
    |mean bps| < 5    → MATCHES        (execution near intended prices)
    mean > +5         → UNDERESTIMATES  (real drag > cost model expects)
    mean < -5         → OVERESTIMATES  (real drag < cost model expects)
    n < 5             → INSUFFICIENT   (sample too thin to interpret)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_BUCKET_START_ISO = "2026-07-13T00:00:00+00:00"
_MATCH_WINDOW_MIN = 10       # ±10 minutes around setup.created_at
_MODELED_EXIT_SLIPPAGE_BPS = 5.0   # from src/cost_model.py per-side


def _connect_db():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
    import os
    import psycopg
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set")
    return psycopg.connect(url, prepare_threshold=None)


def exit_slippage_bps(
    side: str | None,
    status: str | None,
    tp1: float | None,
    sl: float | None,
    close_avg: float | None,
) -> Optional[float]:
    """Signed bps of adverse exit slippage.

    - Positive: adverse (worse fill than intended exit).
    - Negative: favorable (better fill than intended exit).
    - Returns None for 'expired' or missing inputs (no intended-exit
      reference to compare).
    """
    if not close_avg or close_avg <= 0:
        return None
    if side not in ("long", "short"):
        return None
    if status == "tp1_hit":
        intended = tp1
    elif status == "sl_hit":
        intended = sl
    else:
        return None  # expired / tp2 / etc. — no clean reference
    if not intended or intended <= 0:
        return None
    if side == "short":
        # Adverse = close_avg > intended (covered higher). Sign: positive
        # bps = worse for us.
        return (close_avg - intended) / intended * 10_000.0
    # LONG: adverse = close_avg < intended (sold lower).
    return (intended - close_avg) / intended * 10_000.0


def verdict_line(
    observed_mean: float, n: int,
) -> tuple[str, str]:
    """Return (status_word, one-line summary). Locked thresholds."""
    if n < 5:
        return "INSUFFICIENT", f"n={n} < 5 pairs — sample too thin to calibrate"
    delta = observed_mean - 0.0  # zero baseline = intended-exact
    if abs(delta) < 5.0:
        return "MATCHES", (
            f"observed mean {observed_mean:+.2f}bps ~ 0 baseline "
            f"(|delta|={abs(delta):.2f}bps < 5bps threshold). "
            f"Exit-side execution near intended prices."
        )
    if delta > 0:
        return "UNDERESTIMATES", (
            f"observed mean {observed_mean:+.2f}bps > 0 by {delta:+.2f}bps. "
            f"Real exit-side drag exceeds modeled — realized_r_after_costs "
            f"understates the true drag. Sizing should discount edge by "
            f"~{delta:.1f}bps/side on the exit."
        )
    return "OVERESTIMATES", (
        f"observed mean {observed_mean:+.2f}bps < 0 by {abs(delta):.2f}bps. "
        f"Real exit-side execution FAVORS us on average — either the SL/TP "
        f"triggers fire at slightly better prices than the exact trigger, "
        f"or Bitget's fill quality on our size is high."
    )


def _fetch_resolved_setups(conn) -> list[dict]:
    """Auto-traded setups since 07-13 with tp1_hit or sl_hit status
    (the only classes with a clean intended-exit price to compare)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT
                s.id::text                                      AS setup_id,
                s.symbol,
                s.side,
                EXTRACT(EPOCH FROM s.created_at) * 1000         AS created_at_ms,
                s.entry_price, s.sl_price, s.tp1_price,
                s.status
              FROM setups s
              JOIN auto_trader_orders ao
                ON ao.setup_id = s.id AND ao.order_type = 'entry'
             WHERE s.created_at >= %s::timestamptz
               AND s.status IN ('tp1_hit', 'sl_hit')
             ORDER BY created_at_ms ASC
        """, (_BUCKET_START_ISO,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _match_setup_to_position(setup: dict, positions: list) -> Optional[object]:
    """Return the Bitget PositionRecord whose (symbol, side, opened_at_ms)
    matches this setup within ±_MATCH_WINDOW_MIN. None if no match."""
    window_ms = _MATCH_WINDOW_MIN * 60_000
    best = None
    best_delta = float("inf")
    for p in positions:
        if p.symbol != setup["symbol"]:
            continue
        if p.side != setup["side"]:
            continue
        delta = abs(p.opened_at_ms - setup["created_at_ms"])
        if delta <= window_ms and delta < best_delta:
            best_delta = delta
            best = p
    return best


def main() -> int:
    from src.data.bitget_positions import fetch_position_history_since

    with _connect_db() as conn:
        setups = _fetch_resolved_setups(conn)

    if not setups:
        print("No tp1_hit/sl_hit setups in window.")
        return 0

    since_ms = int(setups[0]["created_at_ms"]) - 30 * 60_000
    positions = fetch_position_history_since(since_ms)

    pairs: list[dict] = []
    for s in setups:
        p = _match_setup_to_position(s, positions)
        if p is None:
            continue
        slip = exit_slippage_bps(
            side=s["side"],
            status=s["status"],
            tp1=float(s["tp1_price"]) if s.get("tp1_price") else None,
            sl=float(s["sl_price"]) if s.get("sl_price") else None,
            close_avg=p.close_avg_price,
        )
        if slip is None:
            continue
        pairs.append({
            "symbol": s["symbol"],
            "side": s["side"],
            "status": s["status"],
            "intended": s["tp1_price"] if s["status"] == "tp1_hit" else s["sl_price"],
            "close_avg": p.close_avg_price,
            "slip_bps": slip,
        })

    print("EXIT-SIDE SLIPPAGE CALIBRATION")
    print("=" * 90)
    print(f"Sample window:    {_BUCKET_START_ISO} → now")
    print(f"Baseline (0bps):  intended TP1/SL prices exactly")
    print(f"Modeled per-side: {_MODELED_EXIT_SLIPPAGE_BPS:+.2f}bps (src/cost_model.py)")
    print(f"n_setups:         {len(setups)}")
    print(f"n_matched_pairs:  {len(pairs)}")
    print()

    if not pairs:
        print("No matched setup×position pairs in window.")
        return 0

    # Per-trade table (sorted by slip descending — worst first)
    pairs.sort(key=lambda x: -x["slip_bps"])
    print(f"{'symbol':10} {'side':5} {'status':8} "
          f"{'intended':>12} {'close_avg':>12} {'slip_bps':>10}")
    print("-" * 90)
    for p in pairs:
        print(
            f"{p['symbol']:10} {p['side']:5} {p['status']:8} "
            f"{float(p['intended']):>12.6f} {float(p['close_avg']):>12.6f} "
            f"{p['slip_bps']:>+10.2f}"
        )
    print("-" * 90)
    print()

    # Aggregates
    values = [p["slip_bps"] for p in pairs]
    n = len(values)
    mean = sum(values) / n
    worst = max(values)
    best = min(values)
    n_adverse = sum(1 for v in values if v > 0)

    print("AGGREGATE (observed exit slippage, bps — positive = adverse)")
    print(f"  n_pairs:  {n}")
    print(f"  mean:     {mean:+.2f}bps")
    print(f"  range:    [{best:+.2f}, {worst:+.2f}]bps")
    print(f"  adverse:  {n_adverse}/{n} ({100.0 * n_adverse / n:.1f}%)")
    print()

    # Split by resolution class
    tp1_slips = [p["slip_bps"] for p in pairs if p["status"] == "tp1_hit"]
    sl_slips = [p["slip_bps"] for p in pairs if p["status"] == "sl_hit"]
    print("BY RESOLUTION")
    if tp1_slips:
        print(f"  tp1_hit  n={len(tp1_slips):>2}  mean={sum(tp1_slips)/len(tp1_slips):+.2f}bps")
    if sl_slips:
        print(f"  sl_hit   n={len(sl_slips):>2}  mean={sum(sl_slips)/len(sl_slips):+.2f}bps")
    print()

    status, note = verdict_line(mean, n)
    print(f"VERDICT: {status}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
