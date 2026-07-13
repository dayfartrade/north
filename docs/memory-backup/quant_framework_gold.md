---
name: Quant framework for gold-focused agent — halt rules, macro discipline, hosting
description: External-quant guidance received 2026-07-13. Halt on 2× backtest max DD (gold-specific), Bonferroni-6 WGC macro vars, IB Gateway + Hetzner + systemd + healthchecks.io.
type: project
originSessionId: 8c5c29bc-8414-4021-bbca-1894ba8135a7
---
**Source:** Answered by an experienced quant on 2026-07-13. Treat as high-quality external prior when making halt/filter/hosting decisions.

## Halt vs wait-for-n=100

- Do NOT wait for n=100 during active drawdown — n=100 is a **validation window**, not a survival window.
- Halt whichever fires first:
  - **Realized DD > 2× backtest max DD** (gold uses 2×, not 1.5× — gold has 3 known regime-crucibles: 2011-13 grinding bear, 2022 real-yield shock, 2020 pandemic physical-demand break; if backtest doesn't cover all three, its max DD is optimistic)
  - **Realized DD > 20-25% of capital** (behavioral floor)
- When halted: keep the signal in **SHADOW (paper)**. If shadow-equity recovers when live would have, halt was correct + re-enter mechanically. If shadow keeps bleeding, edge is dead. This decouples "should I trade" from "does edge exist."
- Distinguish **illiquidity-DD from regime-DD** (gold-specific): losses at London fix, COMEX open, or Sydney thin hours are execution artifacts, not signal breaks. Halt on regime-DD, not session-DD.
- **Sequential probability test matters more for gold than crypto** — gold's effective sample rate is 10-20× slower; waiting for n=100 can mean years.

## Macro conditioner discipline

Four rules to avoid hindsight-fitting:
1. **Pre-register** the candidate variable list from theory/literature BEFORE looking at losing regime.
2. **Bonferroni across everything considered**, not just what kept. Looked at 5 macros, kept 1 → p_adj = p × 5.
3. **OOS test on pre-regime data.** If a filter conditions edge, it should show signal in periods before it "obviously" mattered.
4. **The 3-months-ago test.** Would you have named this variable 3 months ago? If not, treat it as suspect.

**Gold-specific pre-registerable candidates (Bonferroni × 6):**
- 10y TIPS real yield (Erb & Harvey 2013 — canonical, NOT hindsight)
- DXY (dollar index)
- CB net purchases (WGC monthly)
- CFTC managed-money net long %
- GLD holdings delta
- Shanghai-COMEX premium

**Key insight:** 2022 broke the "gold = inflation hedge" naive prior. The correct causal story ("gold competes with real yields for real-asset allocation") was already in the literature — losing in 2022 exposed operator's framework gap, not a market anomaly. **Don't confuse "gold is monetary" narrative with tradeable edge.**

## Minimum viable reliability stack (retail/solo)

Total ~$4-8/month, ~2-4h setup.

- **VPS:** Hetzner CX22 (~€4/mo) or DigitalOcean droplet ($6/mo). Ubuntu 24.04, 2 vCPU / 4GB.
- **Scheduler:** systemd timers (NOT cron — better logging, retry, healthcheck integration). One service per daemon, one timer per job.
- **Dead-man's switch:** healthchecks.io free tier. Every job pings; if pings stop, alert fires. **Single biggest reliability win over Task Scheduler.**
- **DB:** Supabase (managed Postgres, free tier fits solo scale for years).
- **Deploy:** git push + shell script + systemctl restart. No K8s, no Docker unless already known.
- **Observability:** journald + logrotate + nightly digest (existing pattern).

**Broker (gold-specific):** IBKR via REST/FIX or Oanda for CFD, CME futures via prop-firm broker. IB Gateway on Linux VPS + systemd + keepalive wrapper (needs weekly 2FA re-login, automate the wrapper). **Session-aware daemons required** — gold has real closed hours (COMEX 17:00-18:00 ET daily, weekend gap). Jobs must reason about market state, not wall-clock time.

**Colocation NOT needed for gold** — session-based signals (funding, ORB) fire on hour+ cycles, not tick. Colo is 5-figure setup for a strategy that doesn't need it.

## How to apply

- **Halt trigger check:** every weekly validation should compute current realized DD vs backtest max DD. If ratio > 2×, halt-and-shadow decision goes to user.
- **New filter proposals:** must be pre-registerable from literature, Bonferroni-corrected against all candidates considered, OOS-tested on pre-regime data. `real_yield_gt_2_2` is legit (canonical since 2013) but Bonferroni ÷ 6 applies.
- **Hosting migration:** Hetzner CX22 + systemd + healthchecks.io is the target stack for pre-launch. Not "figure out later."
