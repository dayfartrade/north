# Crabel Ch 2 + Ch 28 findings — actionable v8 shadow candidates

**Written:** 2026-07-13 (Task 6 research)
**Source:** Toby Crabel, "Day Trading with Short Term Price Patterns and Opening Range Breakout" (1990), Chapters 2 (Early Entry) and 28 (Daily Bias GOLD 1975-1989)

## Chapter 2 — Early Entry (pp. 9-14)

### Core concept: EE Failure

Crabel defines "Early Entry" as large price movement in one direction within first 5 min of session open. Two types:
- **Type 1 EE:** first 5m has larger-than-normal range (norm = 10-day avg); open on one extreme, close on opposite extreme; second 5m shows equal thrust same direction.
- **Type 2 EE:** excessively large first 5m (bigger than previous 20 days); general drift likely.

**EE Failure signature (directly applicable to our 07-13 losses):**
- Counter-move bar with RANGE > breakout bar range = FAILURE WARNING
- "Any 5-min bar against EE that is relatively large compared to previous bars that confirmed EE, will imply a shift in momentum and possibly EE failure."
- "Neutral or confirming price action is crucial just after the EE indication."

### Applicable rules

1. **Break-even stop at 60 min after entry.** "In general stops should be moved to break even within one hour after entry. A market that displays greater tendency to trend should be given less than an hour."
2. **Cancel if ideal action doesn't occur within first 5-10 min.**
3. **Counter-move detection:** if any bar against position has range > breakout bar range within N bars, exit or halt.

## Chapter 28 — Daily Bias GOLD 1975-1989 (pp. 219-226)

### Framework

Crabel classifies each day by prior-day range and 3-day directional pattern:
- **Range classes:** NR7 (narrowest 7d), NR4, NR, CONTROL, WS, WS4, WS7 (widest 7d)
- **3-day pattern:** direction of prev-2 close, prev-1 close, today's open (--- to +++)

### Standout gold-ORB combinations (15-year sample)

| Pattern | Prior | Direction | n | Win% | W/L | Gross |
|---|---|---|---|---|---|---|
| +-- | WS | BUY | 114 | **76%** | 0.86:1 | **+$19,889** |
| -++ | WS | SELL | 94 | 68% | 1.58:1 | +$22,450 |
| +-+ | WS | SELL | 85 | 68% | 2.12:1 | +$14,169 |
| --+ | NR | SELL | 65 | **64%** | 1.34:1 | +$1,620 |
| +-- | NR | BUY | 122 | **61%** | 0.70:1 | +$1,700 |
| ++- | WS4 | BUY | 45 | 71% | 0.52:1 | +$1,750 |
| -++ | WS | SELL | 22 | 77% | 3.91:1 | +$10,729 |
| +-+ | WS4 | SELL | 48 | 73% | 2.60:1 | +$10,260 |

Central finding: **prior-day range magnitude (NR/WS) combined with 3-day directional pattern produces 60-77% win rates on gold ORB. This is a canonical structural edge across 15 years.**

## Cross-validation from our Task 7 (LON n=8 backtest)

- **NR7 prior day + LON: 2/2 wins, +$3,852** — matches Crabel's canonical NR7 setup
- **WS prior day + LON: 2/2 wins, +$3,192**
- **++- 3-day pattern + LON: 3/4 wins (75%), +$3,794**
- **7 of 8 LON trades SHORT** — LON edge appears direction-biased

n=2 in each Crabel-cell is small, but the direction of the effect matches 15-year Crabel data.

## Recommended v8 shadow candidates (pre-registration below)

Add SessionConfig fields:
- `min_prior_day_narrow_days` — only take when prior day range is minimum of last N days (Crabel NR pattern)
- `require_prior_ws` — only when prior day is a WS (wider than yesterday)
- `three_day_pattern_whitelist` — only take when 3-day pattern in a specified set

Add filter functions:
- `filter_prior_day_nr7`: skip unless prior day was narrowest 7d
- `filter_three_day_pattern`: skip unless 3-day pattern in whitelist
- `filter_ee_failure`: post-entry, exit if counter-move bar range > breakout bar range (requires trajectory tracking, not just OR-close snapshot)

## Pre-registration for shadow

New shadow candidates (to add to REGISTERED_FILTERS in strategy_engine.py, thresholds=None until data justifies):

1. `filter_prior_day_nr7_lon` — LON-only, skip unless prior day is narrowest 7. Pre-reg: `2026-07-13T16:00:00Z`. Ship gate: n>=100 shadow decisions AND >=65% precision on kept-wins.

2. `filter_lon_short_only` — LON-only, skip LONG entries. Pre-reg: `2026-07-13T16:00:00Z`. Ship gate: n>=50 shadow LONG signals AND LONG win rate < 40%.

3. `filter_crabel_3day_pattern` — session-agnostic; require 3-day pattern in ("+--", "-++", "+-+", "++-", "--+") — the Crabel high-probability set. Pre-reg: `2026-07-13T16:00:00Z`. Ship gate: n>=100 shadow AND >=60% win rate on kept trades.

4. **Break-even stop at 60 min after entry** — execution-level, not filter. Requires modification to trade simulator + live executor. Pre-register: `2026-07-13T16:00:00Z`. Test on backtest first; ship gate: DSR pass on modified simulation.

## Rejection conditions

Any candidate that:
- Skips >40% of PLANs while <5% total P&L improvement → REJECT
- Fails ship gate by 2026-10-13 → REJECT
- Contradicts a stronger downstream candidate → REJECT

## Ownership

Knox. Sync with next-session gm.
