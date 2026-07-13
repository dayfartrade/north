"""Shadow-equity dashboard — running summary of Path Q shadow tracker.

Reads data/shadow_equity_since_halt.jsonl, computes:
  - Total shadow decisions (took vs skipped)
  - Running equity curve for resolved take-trades
  - Per-session breakdown
  - Skip-precision by candidate filter (if any registered)
  - Optional PNG plot (matplotlib) if available

Called manually or from a scheduled task. Read-only.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHADOW_LOG = ROOT / "data/shadow_equity_since_halt.jsonl"
PLOT_OUT = ROOT / "data/shadow_equity_curve.png"


def _load_rows() -> list[dict]:
    if not SHADOW_LOG.exists():
        return []
    rows = []
    with open(SHADOW_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _summarize_session(rows: list[dict]) -> dict:
    resolved = [r for r in rows if r.get("outcome")]
    took = [r for r in resolved if not r.get("would_skip") and r["direction_bias"] != "FLAT"]
    wins = [r for r in took if r["outcome"]["net_pnl"] > 0]
    total_pnl = sum(r["outcome"]["net_pnl"] for r in took)
    return {
        "n_decisions": len(rows),
        "n_resolved": len(resolved),
        "n_pending": len(rows) - len(resolved),
        "n_took": len(took),
        "n_wins": len(wins),
        "win_rate": len(wins) / len(took) if took else None,
        "total_pnl": total_pnl,
        "mean_pnl": total_pnl / len(took) if took else 0.0,
    }


def _plot_equity(rows: list[dict]) -> Path | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime
    except Exception:
        return None

    took = [r for r in rows if r.get("outcome") and not r.get("would_skip") and r["direction_bias"] != "FLAT"]
    if not took:
        return None
    took_sorted = sorted(took, key=lambda r: r["or_close_utc"])
    ts = [datetime.fromisoformat(r["or_close_utc"].replace("Z", "+00:00")) for r in took_sorted]
    equity = []
    cum = 0.0
    for r in took_sorted:
        cum += r["outcome"]["net_pnl"]
        equity.append(cum)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ts, equity, marker="o", markersize=3)
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.5)
    ax.set_title(f"Shadow equity curve (n={len(took)}, final ${equity[-1]:,.0f})")
    ax.set_xlabel("OR close UTC")
    ax.set_ylabel("Cumulative net P&L ($)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOT_OUT, dpi=90)
    plt.close(fig)
    return PLOT_OUT


def main() -> None:
    rows = _load_rows()
    print(f"SHADOW-EQUITY DASHBOARD  ({SHADOW_LOG.relative_to(ROOT)})")
    print("=" * 62)
    if not rows:
        print("  No shadow decisions yet. Tracker fires each dispatch tick;")
        print("  first entry expected at next session's OR close.")
        return

    total = _summarize_session(rows)
    print(f"  Total decisions:   {total['n_decisions']}")
    print(f"  Resolved:          {total['n_resolved']}  Pending: {total['n_pending']}")
    print(f"  Would-take:        {total['n_took']}")
    if total["n_took"] > 0:
        print(f"  Wins:              {total['n_wins']} ({100 * total['win_rate']:.1f}%)")
        print(f"  Total shadow P&L:  ${total['total_pnl']:+,.2f}")
        print(f"  Mean per trade:    ${total['mean_pnl']:+,.2f}")

    # Per-session
    sessions = sorted(set(r["session"] for r in rows))
    if sessions:
        print("\n  Per-session:")
        for sess in sessions:
            sub = [r for r in rows if r["session"] == sess]
            s = _summarize_session(sub)
            if s["n_took"] > 0:
                print(f"    {sess:5s}  n_took={s['n_took']:3d}  wins={s['n_wins']:3d}  "
                      f"({100 * s['win_rate']:5.1f}%)  net=${s['total_pnl']:+8,.0f}")
            else:
                print(f"    {sess:5s}  n_took=0  (skipped {s['n_decisions']} decisions)")

    plot = _plot_equity(rows)
    if plot:
        print(f"\n  Equity curve plot: {plot.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
