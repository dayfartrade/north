"""Trade-by-trade decomposition — 07-31 read of the 15 tier=low sample.

Reads the same sample the capital-scaling gate reads (07-13-forward
tier=low funding_extreme_revert auto-trader resolutions) but decomposes
each trade individually: theoretical R vs cost-adjusted R vs actual
Bitget fill price. Sorted by drag (biggest cost drag first) so outliers
surface.

Why: the daily-report drag row (shipped 2026-07-31 in 762d88d) shows
aggregate drag. This script shows the per-trade breakdown — is the drag
uniform or dominated by 1-2 high-cost outliers? If outliers dominate,
we may have a filter opportunity (skip setups with likely-high drag).
If uniform, cost model is broadly correct and the honest read is that
+0.44R backtest → +0.39R live is the reality; scale sizing accordingly.

Run:
    python scripts/trade_decomposition_2026_07_31.py

Reads SUPABASE_DB_URL. READ-ONLY — no writes.

Atlas-runnable via:
    C:\\bots\\.venv\\Scripts\\python.exe scripts\\trade_decomposition_2026_07_31.py
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


_BUCKET_START = "2026-07-13T00:00:00+00:00"
_ALLOWED_TIER = "low"
_ALLOWED_SPECIALIST = "funding_extreme_revert"


def _connect():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
    import os
    import psycopg
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL not set")
    return psycopg.connect(url)


def _fetch_trades(cur) -> list[dict]:
    """Per-trade fields: intended vs actual + cost decomposition."""
    cur.execute("""
        SELECT
            s.id                                     AS setup_id,
            s.symbol,
            s.side,
            s.confidence_tier,
            s.status,
            s.entry_price                            AS intended_entry,
            s.sl_price                               AS intended_sl,
            s.tp1_price                              AS intended_tp1,
            s.realized_r,
            s.realized_r_after_costs,
            s.slippage_pct,
            s.fee_pct,
            s.created_at,
            COALESCE(s.tp1_hit_at, s.tp2_hit_at,
                     s.sl_hit_at, s.expired_at)     AS resolved_at,
            ao.fill_price                            AS actual_entry_fill,
            ao.fill_size                             AS actual_fill_size,
            ao.submitted_at                          AS entry_submit_at,
            ao.filled_at                             AS entry_filled_at
        FROM setups s
        JOIN auto_trader_orders ao
             ON ao.setup_id = s.id AND ao.order_type = 'entry'
        WHERE s.status IN ('tp1_hit', 'tp2_hit', 'sl_hit', 'expired')
          AND s.realized_r IS NOT NULL
          AND s.source_phase = %s
          AND s.confidence_tier = %s
          AND ao.submitted_at >= %s::timestamptz
        ORDER BY s.created_at ASC
    """, (_ALLOWED_SPECIALIST, _ALLOWED_TIER, _BUCKET_START))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


from src.analysis_helpers import entry_slippage_bps as _shared_slippage_bps  # noqa: E402
from src.analysis_helpers import session_bucket as _session_bucket  # noqa: E402


def _entry_slippage_bps(row: dict) -> float | None:
    """Row-adapter around shared entry_slippage_bps helper. Extracts
    the 3 fields from a psycopg row dict and delegates."""
    intended = row.get("intended_entry")
    actual = row.get("actual_entry_fill")
    side = row.get("side")
    return _shared_slippage_bps(
        side,
        float(intended) if intended is not None else None,
        float(actual) if actual is not None else None,
    )


def _fmt_dur(td) -> str:
    if td is None:
        return "  n/a"
    total_h = td.total_seconds() / 3600
    if total_h < 1:
        return f"{int(td.total_seconds() / 60):>3}m"
    return f"{total_h:>5.1f}h"


def main() -> int:
    with _connect() as conn, conn.cursor() as cur:
        trades = _fetch_trades(cur)

    print("TIER=LOW AUTO-TRADER TRADE DECOMPOSITION")
    print("=" * 118)
    print(f"Sample bucket:  {_BUCKET_START} → now")
    print(f"Specialist:     {_ALLOWED_SPECIALIST}")
    print(f"Tier:           {_ALLOWED_TIER}")
    print(f"n_resolved:     {len(trades)}")
    print()

    if not trades:
        print("No trades in window.")
        return 0

    # Per-trade table — sorted by drag (biggest cost drag first).
    def _drag(t):
        r = t.get("realized_r")
        rc = t.get("realized_r_after_costs")
        if r is None or rc is None:
            return 0.0
        return float(rc) - float(r)

    trades_by_drag = sorted(trades, key=_drag)

    header = (
        f"{'idx':>3}  {'symbol':10}  {'side':5}  {'session':6}  "
        f"{'status':9}  {'R':>7}  {'R_net':>7}  {'drag':>7}  "
        f"{'entry_slip_bps':>15}  {'duration':>9}  {'setup_id':8}"
    )
    print(header)
    print("-" * 118)
    for i, t in enumerate(trades_by_drag, 1):
        r = float(t.get("realized_r") or 0)
        rc_raw = t.get("realized_r_after_costs")
        rc = float(rc_raw) if rc_raw is not None else 0.0
        drag = rc - r if rc_raw is not None else 0.0
        slip = _entry_slippage_bps(t)
        slip_str = f"{slip:+.2f}" if slip is not None else "  n/a"
        created = t.get("created_at")
        resolved = t.get("resolved_at")
        session = _session_bucket(created.hour) if created else "?"
        duration = None
        if created and resolved:
            duration = resolved - created
        drag_str = f"{drag:+.3f}R" if rc_raw is not None else "  n/a"
        rc_str = f"{rc:+.3f}R" if rc_raw is not None else "  n/a"
        setup_id_short = str(t.get("setup_id"))[:8]
        print(
            f"{i:>3}  {t.get('symbol','?'):10}  "
            f"{(t.get('side') or '?'):5}  {session:6}  "
            f"{(t.get('status') or '?'):9}  "
            f"{r:+.3f}R  {rc_str}  {drag_str}  "
            f"{slip_str:>15}  {_fmt_dur(duration):>9}  {setup_id_short}"
        )

    print("-" * 118)
    print()

    # ── Aggregate footer ──
    n = len(trades)
    sum_r = sum(float(t.get("realized_r") or 0) for t in trades)
    mean_r = sum_r / n if n else 0

    with_cost = [t for t in trades if t.get("realized_r_after_costs") is not None]
    n_c = len(with_cost)
    if n_c:
        sum_rc = sum(float(t["realized_r_after_costs"]) for t in with_cost)
        mean_rc = sum_rc / n_c
        sum_r_matched = sum(float(t.get("realized_r") or 0) for t in with_cost)
        mean_drag = (sum_rc - sum_r_matched) / n_c
    else:
        sum_rc = mean_rc = mean_drag = 0.0

    slip_values = [_entry_slippage_bps(t) for t in trades]
    slip_values = [s for s in slip_values if s is not None]
    if slip_values:
        mean_slip = sum(slip_values) / len(slip_values)
        max_slip = max(slip_values)
        min_slip = min(slip_values)
    else:
        mean_slip = max_slip = min_slip = 0.0

    print("AGGREGATE")
    print(f"  Frictionless:   n={n}   sum_R={sum_r:+.3f}R   mean_R={mean_r:+.3f}R")
    if n_c:
        print(f"  Net of costs:   n={n_c}   sum_R={sum_rc:+.3f}R   mean_R={mean_rc:+.3f}R")
        print(f"  Cost drag:      mean {mean_drag:+.4f}R per trade  "
              f"(total {sum_rc - sum(float(t.get('realized_r') or 0) for t in with_cost):+.3f}R over {n_c} trades)")
    if slip_values:
        print(f"  Entry slippage: mean {mean_slip:+.2f}bps  "
              f"range [{min_slip:+.2f}, {max_slip:+.2f}]bps  n={len(slip_values)}")

    # ── Session bucket summary ──
    session_agg: dict = {}
    for t in trades:
        created = t.get("created_at")
        if not created:
            continue
        s = _session_bucket(created.hour)
        rec = session_agg.setdefault(s, {"n": 0, "sum_r": 0.0})
        rec["n"] += 1
        rec["sum_r"] += float(t.get("realized_r") or 0)
    if session_agg:
        print()
        print("BY SESSION")
        for s in ("asia", "eu_am", "us_am", "us_pm"):
            r = session_agg.get(s)
            if not r:
                continue
            m = r["sum_r"] / r["n"] if r["n"] else 0
            print(f"  {s:6}  n={r['n']:>2}  sum={r['sum_r']:+.3f}R  mean={m:+.3f}R")

    # ── Symbol summary ──
    sym_agg: dict = {}
    for t in trades:
        sym = t.get("symbol") or "?"
        rec = sym_agg.setdefault(sym, {"n": 0, "sum_r": 0.0})
        rec["n"] += 1
        rec["sum_r"] += float(t.get("realized_r") or 0)
    print()
    print("BY SYMBOL")
    for sym in sorted(sym_agg, key=lambda k: sym_agg[k]["sum_r"]):
        r = sym_agg[sym]
        m = r["sum_r"] / r["n"] if r["n"] else 0
        print(f"  {sym:10}  n={r['n']:>2}  sum={r['sum_r']:+.3f}R  mean={m:+.3f}R")

    print()
    print("READ NOTES")
    print("  1. High-drag outliers at top of table → candidates for pre-fire filter")
    print("     (e.g. skip setups with known-high-slippage symbols during known windows)")
    print("  2. If drag is uniform across trades, cost model is broadly correct")
    print("     and the +0.44R backtest → live delta IS the execution cost — scale accordingly")
    print("  3. Big BTC 07-13 loss (-7.36R) is the naked-expiry legacy — see calendar-gates")

    return 0


if __name__ == "__main__":
    sys.exit(main())
