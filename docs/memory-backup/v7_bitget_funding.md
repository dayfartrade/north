---
name: Bitget XAU/USDT funding signal — first-check passed
description: Bitget gold perp is liquid enough for funding-extreme filter; setup details
type: project
originSessionId: 14f4c0d3-d439-4594-962d-37fd4ffc75e5
---
**Verified 2026-06-30:** Bitget XAUUSDT perp passes the OI/depth test. Real venue, not thin-book.

**Liquidity (snapshot):**
- 24h volume: $148-154M
- Open interest: ~11,000 oz = $43.9M
- Bid-ask spread: 0.0 bps (sub-cent)
- Three gold perps exist (XAUUSDT > XAUTUSDT > PAXGUSDT). Use XAUUSDT (most liquid, direct gold).

**Funding rate (8H cycle):**
- 540 rows of history available from Bitget API (~180 days, NOT 365 — Bitget caps history)
- 58.5% of periods non-zero (sparse but not all-zero)
- P85 threshold: 0.0082% per 8H = 9% annualized
- P99: 0.054%
- Max: 0.15%

**Code:**
- `src/data_bitget.py` — fetcher + cache (data/bitget/funding_XAUUSDT.csv, candles_XAUUSDT_5m.csv)
- `src/funding_filter.py` — percentile-based regime tilt (-1 / 0 / +1)
- `src/basis_tracker.py` — Bitget vs COMEX GC basis log
- Bitget API is public, no auth needed.

**How to apply:**
- Private feed (Bitget price reference) uses funding-extreme regime tilt as 4-box gate.
- Public feed (COMEX price) still gets the regime tilt (gold market is one market) but quotes in GC terms.
- Basis ~$2 right now. Track for drift; flag if > $20 (stress signal).

**Pending validation:** Does fading the crowded side actually win in backtest? Need to align funding history with price moves and test. Defer until Phase 2 validation.
