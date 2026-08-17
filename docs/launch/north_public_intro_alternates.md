# NORTH public intro - alternate versions

*Three drafts of the pinned intro message. Farhad picks one (or blends) for launch.*
*Each fits in a single Telegram message (~4000 char limit).*
*Current default is `north_public_intro.md` (version A below, exactly).*

---

## Version A - direct (current default)

*Discipline-forward. No hook, no story. Straight into what you get.*
*Best fit if subscribers arrive already knowing what NORTH is.*

**NORTH - weekly gold direction call**

Every Sunday at 22:00 UTC I publish one call for the coming week on gold: LONG, SHORT, or FLAT. Nothing else. No intraday alerts, no push notifications, no urgency theater. If the signal doesn't fire, I say FLAT and we sit out the week.

**What you get in each call:**
- Direction for the week (LONG / SHORT / FLAT)
- Reference entry price at publish
- Stop-loss level (2x the 20-day ATR from entry)
- Time-based exit: Friday close, or stop hit, whichever comes first
- Mid-week position update on Mon-Fri at 12:00 UTC (only when a directional call is open)

[full version in north_public_intro.md]

---

## Version B - story-forward

*Leads with the retirement wall, positions NORTH as "what survived a brutal filter."*
*Best fit if subscribers arrive from a link that already primes them on the strategy.*

**NORTH - the one gold strategy that survived**

I tested 52 strategies for trading gold. Killed 34 of them. This channel publishes what's left.

**Why 34 dead?** Because signals that work in backtest usually don't work forward. Halt criteria fire. Confidence intervals include zero. Regime effects vanish. If you keep pushing publish anyway, you have a signal service. If you stop, you have discipline. We stopped 34 times.

**What survived (NORTH v1):** a 4-condition weekly filter on gold. Momentum agrees short and long, moving averages agree, real-yield direction agrees. All four or nothing. Published every Sunday 22:00 UTC.

**Backtest 2010-2026:** 56% win rate on the weeks it fires directional. +0.23% average per trade. 5% worst drawdown. Sits out about half the time.

**Live since:** 2026-07-22. First trade lost 0.72%. Three FLAT weeks since. That's expected.

**How to use it:** read the Sunday post. If it says LONG or SHORT and you want to trade it, enter at Monday open near the reference price, set the stop the message tells you, exit at Friday close if the stop doesn't hit first. Size for a 1% account drawdown on a full stop-out.

**Every dead strategy, receipts included:**
github.com/dayfartrade/north/blob/main/docs/launch/retirement_wall.md

**Full history, unedited:**
github.com/dayfartrade/north/blob/main/docs/development_story.md

**What NORTH is not:** not a subscription, not a bot, not advice. Free forever. Your trade, your risk, your call.

- Knox, Farhad's Claude coder

---

## Version C - practical

*Leads with the Sunday user experience. Best for people who care about "what will I actually see."*

**NORTH - your Sunday gold post**

Here's what happens every Sunday night at 22:00 UTC in this channel.

**A single post, one of three shapes:**

*LONG week:*
> Direction: LONG. Entry: ~$4350. Stop: $4155 (2x ATR from entry). Exit: Friday 21:00 UTC close, or stop hit, whichever first. Signal state: [4 lines showing the four conditions].

*SHORT week:*
> Same format, direction inverted.

*FLAT week (about half the time):*
> No trade this week. Signal did not clear all four conditions. Sitting out is the correct action, not a missed opportunity. [Signal state shown].

**Mid-week (Mon-Fri 12:00 UTC):**
Only fires when a directional call is open. Shows signal health, open P&L, distance to stop.

**That's the entire product.** No intraday alerts. No push notifications. No premium tier. No copy-trading. No urgency. If you want scalping signals, this isn't it.

**How the signal decides:**
Four conditions on daily gold prices. LONG needs all four bullish (4-week momentum positive, 12-week momentum positive, short MA above long MA, US 10-year real yield falling over 20 days). SHORT needs all four bearish. FLAT otherwise. That's the entire rule. No hidden knobs.

**Backtest 2010-2026:** 55.9% win rate on directional weeks, +0.23% mean return per trade after costs, 5.6% worst drawdown of notional. Passive gold beat NORTH in raw return but with 3x the drawdown. NORTH is designed to sit out the messy weeks.

**Live since 2026-07-22.** Current record: 1 directional call, -0.72%. Full track record:
github.com/dayfartrade/north/blob/main/docs/launch/track_record_current.md

**52 strategies tested, 34 killed:**
github.com/dayfartrade/north/blob/main/docs/launch/retirement_wall.md

**Kill switch:** if live behavior diverges from backtest, I halt publishing. All of this is in the repo and readable: github.com/dayfartrade/north

---

## Recommendation for launch

**Use Version B if the invite list mostly finds NORTH through Farhad personally.** The retirement-wall hook does the work of explaining why NORTH is different in one line.

**Use Version C if the channel might get random discovery traffic.** It answers "what will I see" fastest, which is what scanners want.

**Use Version A if in doubt.** It's the least likely to age poorly.

Do not use multiple versions on the same launch. Pick one, pin it. If subscribers grow past 100, revisit.
