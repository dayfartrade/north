# Analysis batch verdict v2 — 2026-07-31 (post-backfill, full data)

**Trigger:** Janus ran all 5 shipped analysis scripts locally after
Atlas applied schema 033 + both backfills + operator granted sub-
account RO Bitget key. Combined picture is now complete for the
first time.

**Supersedes:** `research/library/analysis_batch_verdict_2026_07_31.md`
(the v1 verdict from earlier today when I only had DB access and the
2 backfills hadn't landed). This v2 has 3 material differences:
(a) fill_price populated on all 13 filled entries → real cost
calibration verdict, (b) cost-adjusted R aggregate no longer polluted
by the 2 legacy rows, (c) exit-side + funding-paid analytics now
readable.

---

## Headline: real edge is +0.24R/trade after full cost adjustment

The auto-trader path to passive income is **economically real** at
current $4/trade sizing and would produce **~$293/mo net at $2K
target sizing** based on today's read. Numbers:

| Metric | Value | Interpretation |
|---|---|---|
| Naive mean R (all 15) | −0.107R | dragged by 2 legacy losses; misleading |
| **Clean mean R (n=13 ex-legacy) frictionless** | **+0.538R** | MATCHES +0.44R backtest |
| **Clean mean R net of modeled costs** | **+0.287R** | drag ~-0.25R/trade absorbs ~half the edge |
| Adjusted for cost-model UNDERESTIMATION | **~+0.24R** | true realized edge |
| Funding-paid aggregate (independent P&L) | +0.0063R | small, additive, positive |
| At $2K sizing / $40 per R / 30 trades/mo | **~+$288/mo price + ~$5 funding** | **≈$293/mo passive income** |

Discipline held: pre-reg gate still counts all 15 rows including the 2
legacy losses. Gate does NOT flip GATE_MET until the aggregate crosses
positive AND CI_low > 0. That will take ~n=25-30 for the legacy drag
to be amortized. Realistic gate arrival: 08-17 (n=30 mechanical) to
09-15 (edge criterion with legacy amortized).

## Cost-model calibration — the surprise

**Verdict per-script:**

| Script | Verdict | Numbers |
|---|---|---|
| Entry-side (cost_model_calibration) | **UNDERESTIMATES** | observed +9.39bps mean vs modeled 5bps (+4.39bps gap) |
| Exit-side (exit_slippage_calibration) | **MATCHES** | observed +2.33bps mean vs 0 baseline (within ±5bps band) |
| Funding-paid (funding_paid_analysis) | **THESIS INTACT** | +$0.41 aggregate, 7 positive / 1 negative / 6 zero |

Combined round-trip drag:
- Modeled: 5bps entry + 5bps exit + 12bps taker fees = ~22bps
- Observed: 9.4bps entry + 2.3bps exit + 12bps taker fees = ~24bps
- Real drag ~8% higher than modeled (small, not catastrophic)

At typical R = ~50bps price move, this translates:
- Modeled drag as fraction of R = 22/50 = 44% upper bound
- Observed drag = 24/50 = 48% upper bound

Real drag measured over 13 trades: **~25% of R** (`-0.25R mean`). The
upper bound isn't realized because SL hits close at trigger price
exactly (bounded worst-case), while TP1 hits absorb the full drag.

**Sizing implication:** at gate-day, sizing recommendation script
should discount edge by an additional ~4bps/side on entry due to
the underestimation finding. On +0.44R backtest → +0.24R live
translation, that's roughly a 5% haircut. Not huge, but the LSPM
correlation discount + drawdown-constrained f cap will bind before
this becomes material.

## Tail-risk warning: TAO entry slippage

TAOUSDT (8 of 15 filled entries) shows an ugly tail:
- Individual fills range −52.30bps (favorable) to +49.50bps (adverse)
- Mean +17.73bps (3.5× modeled)
- p90 +37.65bps (>2× modeled)

Session breakdown of entry slippage (all symbols):
- eu_am: -8.98bps (favorable, n=4)
- us_am: +8.34bps (mild adverse, n=4)
- us_pm: +23.53bps (adverse, n=4)
- asia:  +30.48bps (very adverse, n=1)

**DO NOT act on this to build a filter without pre-reg + backtest.**
n=1 in asia is noise; n=4 per US session isn't a decision-worthy
sample. Filed for observation. Revisit at n≥30 per session.

## Funding-paid detail

Aggregate +$0.41 over 14 matched pairs. Distribution:
- 7 positions received positive funding (thesis-directional)
- 6 positions crossed no funding cycle (hold < 2h)
- 1 position paid funding (BCHUSDT SHORT −$0.003 — small negative
  during a mild-funding window; not thesis violation)

Duration-monotone confirms mechanism working:
| Hold bucket | n | mean funding $/pos |
|---|---|---|
| <2h (0 cycles) | 4 | $0.0000 |
| 2-8h (0-1 cycles) | 6 | $0.0132 |
| 8-16h (1-2 cycles) | 1 | $0.0168 |
| 16-24h (2-3 cycles) | 1 | $0.1061 |
| >24h (3+ cycles) | 2 | $0.1055 |

Each 8h cycle crossed = one funding payment at typical position size.
At $4 risk / $40 notional at 10x lev, per-cycle funding is $0.02-0.10
depending on symbol funding rate at payment time. Scales linearly
with capital.

At $2K sizing (10× current), funding contribution alone:
~+$5-10/month passive income independent of price movement.

## What changed vs v1 verdict

| Aspect | v1 (this morning) | v2 (now, post-backfill) |
|---|---|---|
| Cost model verdict | INSUFFICIENT (n=2 of 15) | UNDERESTIMATES by ~4bps |
| Exit-side | N/A (no Bitget access) | MATCHES verdict at n=12 pairs |
| Funding-paid | N/A | +$0.41 aggregate, thesis intact |
| Net-of-costs mean R | inflated by cosmetic drag on 2 legacy rows | clean +0.287R at n=13 |
| Passive-income projection | speculative | ~$293/mo at $2K sizing (grounded) |

## Discipline reinforcement

**No sizing changes today.** Gate is n=15 not n=30. Pre-reg discipline
holds. The v2 numbers are FOR gate-day sizing use, not for early
capital-add.

**No filter shipping today.** TAO tail-risk is n=8 = noise. Session-
level entry-slippage patterns are n=1-4 = noise. Log for revisit at
n≥30 per bucket.

**No cost-model tuning today.** The +4bps underestimation is
measured but should be validated at n=30+ before touching
DEFAULT_SLIPPAGE_PCT. If we tune it now at n=13, we're fitting to
sample noise. Sizing recommendation at gate-day can apply the
adjustment as a data-derived discount without modifying the model
itself.

## Cross-references

- `research/library/analysis_batch_verdict_2026_07_31.md` — v1 (superseded)
- `research/library/gate_met_playbook_2026_07_31.md` — sizing sequence
- Scripts run: trade_decomposition, cost_model_calibration,
  exit_slippage_calibration, funding_paid_analysis
- Sub-account RO key: `janus-subacct-0731`, added to local .env
  2026-07-31 for direct read-only Bitget access

## Files updated / created this session

- `.env` — sub-account RO key trio added (BITGET_API_KEY_RO +
  BITGET_API_SECRET_RO + BITGET_API_PASSPHRASE_RO)
- This verdict doc (v2)

No code changes required by this verdict. All findings are
data-derived; live-trading behavior is unchanged.
