"""Generate RSS feed + JSON API from FAR Weekly call history.

Consumed by:
  - RSS readers / aggregators (site/feed.xml)
  - API clients (site/api/calls.json)
  - Discord/Slack bots via IFTTT or direct RSS

Output files (regenerated on every publish tick):
  - site/feed.xml (RSS 2.0)
  - site/api/calls.json (public API: latest + N most recent)
  - site/api/latest.json (single-call convenience endpoint)
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
CALLS_LOG = ROOT / "data" / "far_weekly_calls.jsonl"
FEED_XML = ROOT / "site" / "feed.xml"
API_CALLS = ROOT / "site" / "api" / "calls.json"
API_LATEST = ROOT / "site" / "api" / "latest.json"

SITE_URL = "https://faractionradar.com"
PRODUCT_URL = f"{SITE_URL}/track-record"


def load_calls() -> list[dict]:
    if not CALLS_LOG.exists():
        return []
    return [json.loads(l) for l in open(CALLS_LOG, encoding="utf-8") if l.strip()]


def _rfc822(iso: str) -> str:
    """Convert ISO timestamp to RFC-822 for RSS pubDate."""
    if not iso:
        return ""
    try:
        # handle both Z and +00:00 formats
        clean = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    except Exception:
        return ""


def call_to_rss_item(call: dict) -> str:
    direction = call.get("direction", "FLAT")
    week_of = call.get("week_of", "?")
    week_end = call.get("week_end", "?")
    published = call.get("published_utc", "")
    entry = call.get("entry_approx")
    stop = call.get("stop_price")
    atr = call.get("atr_20d")
    outcome = call.get("outcome") or {}

    title_parts = [f"Week {week_of}: {direction}"]
    if direction != "FLAT":
        if entry:
            title_parts.append(f"entry ${entry:,.2f}")
    if outcome.get("result") == "resolved":
        pct = outcome.get("net_return_pct", 0)
        title_parts.append(f"resolved {pct:+.2f}%")
    title = " · ".join(title_parts)

    body_lines = [
        f"Direction: {direction}",
        f"Week: {week_of} to {week_end}",
    ]
    if direction != "FLAT":
        if entry: body_lines.append(f"Entry (approx): ${entry:,.2f}")
        if stop: body_lines.append(f"Stop: ${stop:,.2f}")
        if atr: body_lines.append(f"ATR(20d): ${atr:.2f}")
    sc = call.get("signal_components", {})
    if sc:
        body_lines.append(f"Signal drivers: M20={sc.get('M20_pct')}%, "
                          f"M60={sc.get('M60_pct')}%, "
                          f"RY_chg={sc.get('RY_chg_20d_bps')}bps")
    if outcome.get("result") == "resolved":
        body_lines.append("")
        body_lines.append(f"OUTCOME: {outcome.get('net_return_pct'):+.3f}% "
                          f"({outcome.get('exit_reason')})")
    body_lines.append("")
    body_lines.append(f"Full details, backtest, position calculator: {PRODUCT_URL}")

    description = "\n".join(body_lines)
    guid = f"{PRODUCT_URL}#{week_of}"

    return (
        "    <item>\n"
        f"      <title>{escape(title)}</title>\n"
        f"      <link>{PRODUCT_URL}</link>\n"
        f"      <guid isPermaLink=\"false\">{escape(guid)}</guid>\n"
        f"      <pubDate>{_rfc822(published)}</pubDate>\n"
        f"      <description>{escape(description)}</description>\n"
        "    </item>"
    )


def generate_rss(calls: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    # Newest first
    sorted_calls = sorted(calls, key=lambda c: c.get("published_utc", ""),
                          reverse=True)
    items = "\n".join(call_to_rss_item(c) for c in sorted_calls[:100])
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>FAR Weekly Gold Read</title>\n"
        f"    <link>{PRODUCT_URL}</link>\n"
        '    <atom:link href="https://faractionradar.com/feed.xml" '
        'rel="self" type="application/rss+xml"/>\n'
        "    <description>One directional gold call per week. Long, short, "
        "or flat. Published Sunday · resolved Friday close. By Knox.</description>\n"
        "    <language>en-us</language>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        "    <ttl>1440</ttl>\n"
        f"{items}\n"
        "  </channel>\n"
        "</rss>\n"
    )


def generate_json_api(calls: list[dict]) -> dict:
    sorted_calls = sorted(calls, key=lambda c: c.get("published_utc", ""),
                          reverse=True)
    resolved = [c for c in sorted_calls
                if c.get("outcome", {}).get("result") == "resolved"]
    wins = sum(1 for c in resolved
               if c.get("outcome", {}).get("net_return_pct", 0) > 0)
    cum_return = sum(c.get("outcome", {}).get("net_return_pct", 0)
                     for c in resolved)

    return {
        "product": "FAR Weekly Gold Read",
        "operator": "Knox",
        "status": "BETA",
        "url": PRODUCT_URL,
        "docs": f"{PRODUCT_URL}",
        "feed_url": f"{SITE_URL}/feed.xml",
        "api_url": f"{SITE_URL}/api/calls.json",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_calls": len(sorted_calls),
            "resolved_calls": len(resolved),
            "wins": wins,
            "losses": len(resolved) - wins,
            "win_rate_pct": round(100 * wins / len(resolved), 2) if resolved else None,
            "cumulative_return_pct": round(cum_return, 3),
        },
        "latest": sorted_calls[0] if sorted_calls else None,
        "recent": sorted_calls[:20],
    }


def main() -> None:
    calls = load_calls()

    # RSS
    FEED_XML.parent.mkdir(parents=True, exist_ok=True)
    FEED_XML.write_text(generate_rss(calls), encoding="utf-8")
    print(f"[wrote] {FEED_XML.relative_to(ROOT)} ({len(calls)} items)")

    # JSON API
    API_CALLS.parent.mkdir(parents=True, exist_ok=True)
    payload = generate_json_api(calls)
    with open(API_CALLS, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"[wrote] {API_CALLS.relative_to(ROOT)}")

    # Latest convenience endpoint
    latest = payload.get("latest") or {}
    with open(API_LATEST, "w", encoding="utf-8") as f:
        json.dump(latest, f, indent=2, default=str)
    print(f"[wrote] {API_LATEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
