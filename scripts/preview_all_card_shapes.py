"""Render sample LONG / SHORT / FLAT weekly cards without publishing.

Used to visually verify format changes before a real Sunday publish.
Reads the current track record (from far_weekly_calls.jsonl) and uses
plausible signal component numbers for the LONG and SHORT examples,
and the current live FLAT numbers for the FLAT example.

Usage:
    python scripts/preview_all_card_shapes.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from far_weekly_telegram import format_weekly_call


def load_track() -> dict:
    calls_p = ROOT / "data" / "far_weekly_calls.jsonl"
    if not calls_p.exists():
        return {"resolved_calls": 0}
    rows = [json.loads(l) for l in calls_p.read_text().splitlines() if l.strip()]
    resolved = [r for r in rows
                if r.get("outcome", {}).get("net_return_pct") is not None
                and r.get("direction") in ("LONG", "SHORT")]
    if not resolved:
        return {"resolved_calls": 0}
    pnls = [r["outcome"]["net_return_pct"] for r in resolved]
    wins = sum(1 for p in pnls if p > 0)
    return {
        "resolved_calls": len(resolved),
        "win_rate_pct": 100 * wins / len(resolved),
        "cumulative_return_pct": sum(pnls),
    }


def load_latest_flat() -> dict | None:
    calls_p = ROOT / "data" / "far_weekly_calls.jsonl"
    if not calls_p.exists():
        return None
    rows = [json.loads(l) for l in calls_p.read_text().splitlines() if l.strip()]
    for r in reversed(rows):
        if r.get("direction") == "FLAT":
            return r
    return None


def main() -> None:
    track = load_track()
    latest_flat = load_latest_flat()

    ref_price = 4374.20
    ref_atr = 90.78

    long_call = {
        "direction": "LONG",
        "week_of": "2026-08-24",
        "week_end": "2026-08-28",
        "entry_approx": ref_price,
        "stop_price": ref_price - 2 * ref_atr,
        "atr_20d": ref_atr,
        "signal_components": {
            "M20_pct": 8.974,
            "M60_pct": 1.5,
            "MA10_above_MA40": True,
            "RY_chg_20d_bps": -5.0,
        },
    }

    short_call = {
        "direction": "SHORT",
        "week_of": "2026-08-24",
        "week_end": "2026-08-28",
        "entry_approx": ref_price,
        "stop_price": ref_price + 2 * ref_atr,
        "atr_20d": ref_atr,
        "signal_components": {
            "M20_pct": -3.5,
            "M60_pct": -8.2,
            "MA10_above_MA40": False,
            "RY_chg_20d_bps": 12.0,
        },
    }

    header = "=" * 68

    print(f"\n{header}\n SIMULATED LONG CALL (plausible hypothetical)\n{header}")
    print(format_weekly_call(long_call, track))

    print(f"\n{header}\n SIMULATED SHORT CALL (plausible hypothetical)\n{header}")
    print(format_weekly_call(short_call, track))

    if latest_flat:
        print(f"\n{header}\n LATEST ACTUAL FLAT (from far_weekly_calls.jsonl)\n{header}")
        print(format_weekly_call(latest_flat, track))
    else:
        print("\n(no FLAT call on record yet)")

    print(f"\n{header}\n NOTE\n{header}")
    print(" These are LOCAL renders only. Nothing was sent to any Telegram channel.")
    print(" To send: rely on the automated Sunday 22:00 UTC weekly-publish workflow.")


if __name__ == "__main__":
    main()
