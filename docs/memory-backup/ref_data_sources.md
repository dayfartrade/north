---
name: Free data sources & limits
description: What yfinance/FRED give us and where the gaps are
type: reference
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
**yfinance free GC=F intraday delay:** ~15 hours during the trading day. The most recent bar we get on a Friday afternoon is from late Thursday night. Set `STALE_BAR_HOURS = 24` in src/health.py to suppress false-positive stale warnings; for true real-time we'd need a broker feed (user has not specified).

**yfinance free GC=F historical depth:**
- 1m: rolling 7 days
- 5m: 60 days
- 1h (60m): **730 days** (the primary backtest dataset)
- 1d: ~26 years

**FRED CSV (no API key needed):** `https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES_ID}` — used in data_fred.py to pull CPI, NFP, claims, real yields, DXY proxy, etc. Returns daily/weekly/monthly observation dates, NOT release timestamps. Release timestamps are reconstructed from documented schedules in calendar_events.py.

**FOMC dates:** authoritative, hardcoded in src/calendar_events.py from federalreserve.gov.

**DXY 24h intraday:** ticker `DX-Y.NYB` on yfinance gives 14k hourly bars aligned with GC. UUP (ETF) is regular-session only and bar timestamps don't align with GC — avoid for intraday cross-asset work.

**Cross-asset validation:** GLD ETF ticker on yfinance, but only regular-session bars (13:30-20:00 UTC summer). Use only for FOMC tests; CPI/NFP at 12:30 UTC are pre-market for GLD.
