"""Generate a monthly outcome digest from the live calls log.

Feeds the Knox monthly market read (see docs/launch/knox_market_read_template.md).
Not for direct publication - the digest is raw material Knox uses to write
the prose post at the end of each month.

Usage:
    python scripts/monthly_digest.py              # current month
    python scripts/monthly_digest.py --month 2026-08
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CALLS = ROOT / "data" / "far_weekly_calls.jsonl"
V2_SHADOW = ROOT / "data" / "far_weekly_v2_shadow.jsonl"
ENS_SHADOW = ROOT / "data" / "far_weekly_ensemble_shadow.jsonl"


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def in_month(iso_date: str, month: str) -> bool:
    if not iso_date:
        return False
    return iso_date[:7] == month


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=datetime.now(timezone.utc).strftime("%Y-%m"),
                    help="target month, YYYY-MM (default: current month UTC)")
    args = ap.parse_args()
    month = args.month

    calls = load_jsonl(CALLS)
    v2 = load_jsonl(V2_SHADOW)
    ens = load_jsonl(ENS_SHADOW)

    month_calls = [c for c in calls if in_month(c.get("week_of", ""), month)]
    month_v2 = [s for s in v2 if in_month(s.get("week_of", ""), month)]
    month_ens = [s for s in ens if in_month(s.get("week_of", ""), month)]

    print("=" * 66)
    print(f" NORTH monthly digest - {month}")
    print("=" * 66)
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    print()

    print("Weekly calls this month:")
    if not month_calls:
        print("  (none published)")
    else:
        for c in month_calls:
            d = c.get("direction", "?")
            w = c.get("week_of", "?")
            we = c.get("week_end", "?")
            outcome = c.get("outcome", {})
            outcome_str = ""
            if outcome:
                r = outcome.get("result", "?")
                pct = outcome.get("net_return_pct")
                reason = outcome.get("exit_reason", "?")
                if pct is not None:
                    outcome_str = f" -> {r}, {pct:+.2f}% ({reason})"
                else:
                    outcome_str = f" -> {r}"
            print(f"  {w} to {we}: {d}{outcome_str}")

    print()
    directional_this_month = [c for c in month_calls if c.get("direction") in ("LONG", "SHORT")]
    flat_this_month = [c for c in month_calls if c.get("direction") == "FLAT"]
    resolved_this_month = [c for c in directional_this_month
                            if c.get("outcome", {}).get("net_return_pct") is not None]

    print(f"Summary this month:")
    print(f"  Weeks published:     {len(month_calls)}")
    print(f"  Directional calls:   {len(directional_this_month)}")
    print(f"  FLAT calls:          {len(flat_this_month)}")
    print(f"  Resolved this month: {len(resolved_this_month)}")
    if resolved_this_month:
        pnls = [c["outcome"]["net_return_pct"] for c in resolved_this_month]
        wins = sum(1 for p in pnls if p > 0)
        print(f"  Wins:                {wins}/{len(resolved_this_month)}")
        print(f"  Month cum return:    {sum(pnls):+.2f}%")

    print()
    print("Shadow signal disagreements this month (both surfaces):")
    disagreements = 0
    for s in month_v2:
        v1 = s.get("v1_direction")
        v2d = s.get("v2_direction")
        if v1 != v2d:
            disagreements += 1
            print(f"  {s.get('week_of')}: v1={v1} vs v2={v2d} (dxy_chg_20d={s.get('dxy_chg_20d'):+.3f})")
    if disagreements == 0:
        print("  (no v2 disagreements)")

    print()
    ens_disagreements = 0
    for s in month_ens:
        v1 = s.get("v1_direction")
        e = s.get("ensemble_direction")
        if v1 != e:
            ens_disagreements += 1
            print(f"  {s.get('week_of')}: v1={v1} vs ensemble={e} "
                  f"(votes L={s.get('votes_long')} S={s.get('votes_short')} "
                  f"unanimous={s.get('unanimous')})")
    if ens_disagreements == 0:
        print("  (no ensemble disagreements)")

    print()
    print("Cumulative track record (all time, not just this month):")
    all_resolved = [c for c in calls
                     if c.get("outcome", {}).get("net_return_pct") is not None
                     and c.get("direction") in ("LONG", "SHORT")]
    if all_resolved:
        pnls = [c["outcome"]["net_return_pct"] for c in all_resolved]
        wins = sum(1 for p in pnls if p > 0)
        print(f"  Total resolved:      {len(all_resolved)}")
        print(f"  Wins:                {wins} ({100*wins/len(all_resolved):.0f}%)")
        print(f"  Cumulative:          {sum(pnls):+.2f}%")
    else:
        print("  (nothing resolved yet)")

    print()
    print("Retired this month (from data/experiments/registry.json):")
    reg = json.loads((ROOT / "data" / "experiments" / "registry.json").read_text())
    retired_this_month = [t for t in reg["trials"]
                           if (t.get("resolved_utc") or "")[:7] == month
                           and t.get("verdict", "").lower().startswith(("rejected", "retired", "killed"))]
    if not retired_this_month:
        print("  (none)")
    else:
        for t in retired_this_month:
            print(f"  {t.get('id')} - {t.get('verdict')}")


if __name__ == "__main__":
    main()
