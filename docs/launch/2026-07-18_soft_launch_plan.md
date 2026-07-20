# Knox soft-launch plan — 2026-07-18

**Decision:** run Engine A (v7 Path Y, halted) and Engine B (Knox, v8 + daily_slope_consistency) as TWO permanent engines. Engine A stays halted per pre-registered discipline. Engine B soft-launches to a `Knox research/beta` Telegram channel with explicit unvalidated disclosure.

## Channels

| Channel | Purpose | Audience |
|---|---|---|
| `GOLDTRADER_TG_CHAT_PUBLIC` (existing) | Engine A honest-halt status + weekly research diary | Public / subscribers |
| **`GOLDTRADER_TG_CHAT_RESEARCH`** (NEW) | Knox live shadow signals + weekly ship-gate report | Small beta group, no monetization |
| `GOLDTRADER_TG_CHAT` (existing) | Private operator alerts | Farhad only |

## What Engine B publishes to the research channel

**PLAN alert** — on OR-close, when both:
- Engine A OR/ATR filter passes (would_take=True)
- Engine B daily_slope_consistency passes (would_skip=False)

Format at `scripts/shadow_orb_tracker.py:_try_send_research_alert`. Every alert has the disclosure banner as the first two lines:

```
🧪 KNOX RESEARCH ALERT — UNVALIDATED
Shadow-gate n/100 · CI on P&L lift still includes zero
Do NOT trade this with money you can't lose.
```

**Post-mortem follow-up** — once outcome resolves (target hit, stop hit, or 3h time-out), `scripts/knox_post_mortem.py` posts a follow-up to the same channel:

```
🧪 KNOX RESEARCH — Alert resolved
🟢/🔴/⚪ NY LONG @ 2026-07-20 13:30Z
Entry: `4010.00` -> Exit: `4020.50` (target)
P&L: `$+250.50` (1 contract, RT cost $24)
Resolved: 2026-07-20 16:30Z

Cumulative Knox gate: n=X/100, precision Y%, CI [lo, hi], STATUS
```

Idempotent — row marked `research_post_mortem_sent=True` after successful send. Runs every 30 min via `ops/systemd/knox-post-mortem.timer` (offset :05, :35 to align with dispatch's :00, :30).

## Halt discipline for Engine B

Engine B has its OWN kill switch:
- Environment variable `KNOX_RESEARCH_ENABLED=1` on the dispatch host enables alerts.
- Setting `KNOX_RESEARCH_ENABLED=0` (or unsetting) instantly disables without redeploy.
- Engine B's own SPRT will be pre-registered when its shadow reaches n=50, using Knox-specific win rates from the shadow log — NOT the Path Y hypothesis.
- If Engine B's SPRT halts, Engine B pauses. Engine A remains independently halted.

## Weekly ship-gate report

Every Sunday 22:15 UTC (15 min after weekly validation), post `scripts/shadow_ship_gate_report.py` output to BOTH channels:
- Public channel gets the summary line ("Knox: n=X/100, precision Y%, CI [lo, hi], gate=STATUS")
- Research channel gets the full breakdown

If Engine B ever posts a "READY-TO-SHIP" gate status: Knox does NOT auto-promote to public. Human decision required. Public promotion requires:
1. Ship gate cleared (n≥100, precision≥60%, CI clear of zero)
2. Knox-specific DSR audit passed
3. Knox-specific SPRT pre-registered
4. VPS hosting confirmed stable for 30 consecutive days
5. Explicit user go-ahead

## Timeline

| Step | Owner | Time | Status |
|---|---|---|---|
| Wire Engine B in strategy_engine | Knox | 30 min | ✅ done 2026-07-18 |
| Wire research audience in telegram_bot | Knox | 15 min | ✅ done 2026-07-18 |
| Wire research-alert path in shadow tracker | Knox | 30 min | ✅ done 2026-07-18 |
| Create Telegram research channel | Farhad | 5 min | ⏸ pending |
| Get channel chat_id, set GOLDTRADER_TG_CHAT_RESEARCH in .telegram | Farhad | 5 min | ⏸ pending |
| Pin disclosure post to research channel | Farhad | 2 min | ⏸ pending |
| Post halt-honesty announcement to public channel | Farhad | 2 min | ⏸ pending |
| VPS migration | Farhad | ~1h | ⏸ pending |
| Set KNOX_RESEARCH_ENABLED=1 on VPS | Farhad | 30 sec | ⏸ pending |
| Weekly ship-gate report to both channels | Knox | wire as systemd timer | ⏸ pending |
| Knox SPRT pre-reg at n=50 | Knox + Farhad review | 1h | ⏸ pending (~4 weeks out) |
| Public promotion decision at n=100 | Farhad | — | ⏸ pending (~8 weeks out) |
| Hard-stop review | Farhad | 2026-10-13 | ⏸ pending |

## What could go wrong

- **Knox loses publicly.** Research channel sees a losing streak. Discipline: publish the losses transparently, reference the pre-reg, don't move goalposts. If Knox halts on its own SPRT: post it, honor it. This is the risk of soft launch and it's how credibility gets built.
- **Small beta group leaks signals to a broader audience.** Users treat "unvalidated research" as tradeable. Mitigation: the disclosure banner is on EVERY alert, not just the pin. Weekly report reinforces gate status.
- **Engine B accidentally publishes when I've toggled the env off.** Mitigation: `KNOX_RESEARCH_ENABLED=1` gate is checked at send time, not import time. Toggling takes effect within one tick.

## What this is NOT

- Not a paid signals service.
- Not a beta version of Engine A with a "sign up early" pitch.
- Not a bet that Knox will succeed — it's a bet that transparent unvalidated research is a legitimate product-line even if the strategy fails.
