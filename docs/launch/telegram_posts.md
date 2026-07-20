# Telegram posts — copy/paste to publish

## 1) Public channel — halt honesty (post + pin)

Copy this to `GOLDTRADER_TG_CHAT_PUBLIC` and pin it:

---

📊 *Gold Day Trader — status update, 2026-07-18*

The live-trading engine (v7 Path Y) hit its pre-registered halt on 2026-07-13.

*What that means:* the SPRT — a formal statistical test the strategy agreed to before launch — crossed the threshold that says "reject the null that this is working." 4 wins in 18 trades. Kill switch is on. No new alerts to subscribers until re-entry gates fire.

*Why we're telling you:* because pre-registered halts only work if you honor them, and because the honest version of this business is being straight about what the numbers say.

*What happens next:*
1. Engine A (v7 Path Y) stays halted. Three re-entry paths are pre-registered:
   • Shadow recovery to +$27,390 with 5 consec ≥60% wins, OR
   • Real yield <2.0 for 30 consecutive days AND shadow ≥ 0, OR
   • A new strategy passes DSR + new SPRT pre-reg.
2. Engine B (Knox) — a new strategy candidate with a daily-trend consistency filter — soft-launches to a research channel today with explicit unvalidated disclosure. It might work. It might fail publicly.
3. Weekly ship-gate report every Sunday 22:15 UTC.
4. If no re-entry path fires by 2026-10-13: honest retirement.

*What you should do:* nothing right now. If you were paper-following the signals, keep the money on the sidelines. If you want to watch the Knox soft launch: link to research channel below (unvalidated, don't trade it with money you can't lose).

Research channel: [link Farhad fills in]

Full pre-reg + halt analysis: [github link]

---

## 2) Research channel — first pin (Knox disclosure)

Copy this to `GOLDTRADER_TG_CHAT_RESEARCH` as first post, then pin:

---

🧪 *KNOX RESEARCH / BETA — please read before anything else*

This channel publishes live shadow decisions from **Engine B (Knox)**, an unvalidated v8 candidate strategy for gold day-trading. It exists so we can transparently watch a candidate live-trade its way through pre-registered ship gates.

*What you'll see here:*
- ORB PLAN alerts (session-open breakout entries with stop + target)
- Each alert prefixed with 🧪 KNOX RESEARCH ALERT — UNVALIDATED
- Weekly ship-gate report every Sunday 22:15 UTC

*What you should NOT do:*
- Do not trade these signals with money you can't lose
- Do not treat this as a subscription service (it isn't, and it's free)
- Do not assume "beta" means "almost ready" — it means "we don't know if it works"

*How Knox differs from Engine A (halted):*
- Same OR breakout mechanic + Path Y session configs
- Adds ONE filter: skip breakouts that oppose the 20-day daily slope of gold
- Motivation: all 6 losing LONG trades in the Engine A launch went counter to the daily trend

*Current ship-gate status (as of 2026-07-18):*
- Shadow decisions: 16 / 100 required
- Precision on skipped losers: 66.7% (need ≥60%)
- P&L lift: +$17/trade with 95% CI [−$251, +$287]  ← INCLUDES ZERO
- Verdict: IN-PROGRESS. Not tradeable.

*What triggers Knox getting promoted to the public channel:*
1. Shadow n ≥ 100
2. Precision ≥ 60%
3. Bootstrap CI on mean P&L lift clears zero
4. Knox-specific DSR audit passes
5. Knox-specific SPRT gets pre-registered and doesn't halt in first 10 trades
6. Explicit human go-ahead

*What triggers Knox getting killed:*
- Precision drops below 55% at n≥100
- Skip-rate exceeds 40% without decisive P&L improvement
- Doesn't clear gates by 2026-10-13 (hard stop)
- Knox's own SPRT (registered at n=50) halts

Pre-registration: docs/experiments/2026-07-18_daily_slope_consistency_shadow.md
Full soft-launch plan: docs/launch/2026-07-18_soft_launch_plan.md

---

## 3) Both channels — weekly ship-gate report (template)

Post this every Sunday 22:15 UTC to BOTH channels (short version to public, full to research):

### Short (public):

```
📈 Knox week N: n=X/100 shadow, precision Y%, P&L lift $Z/trade, CI [lo, hi]. Gate = STATUS.
Engine A halt: unchanged (path A/B/C progress: [line]).
Full report: [link to research channel]
```

### Full (research):

```
📊 Knox weekly ship-gate report — YYYY-MM-DD

Shadow decisions:   n = X / 100
Skips this week:    S (of Y total decisions)
Skips cumulative:   T / U taken (skip-rate V%)
Precision on losers (cumulative): P%
P&L lift this week: $ΔW
P&L lift cumulative: $ΔT (mean $A/trade)
Bootstrap 95% CI on mean lift: [$lo, $hi]

Gate status: STATUS
  ✅/❌ n ≥ 100
  ✅/❌ precision ≥ 60%
  ✅/❌ CI clears zero
  ✅/❌ skip-rate ≤ 40%
  ✅/❌ pre-2026-10-13 hard stop

Engine A halt: unchanged. Path A/B/C progress: [line]

Full raw data: [git commit link]
```
