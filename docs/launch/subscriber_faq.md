# NORTH - subscriber FAQ

*Answers to the questions people ask when they discover NORTH.*
*Posted to the public Telegram channel as a second pinned message (if bot gets pin permission) or referenced in replies to DMs.*

---

## About the product

**Q: Is this a paid service?**
No. Free forever. There is no premium tier, no upsell, no course, no signals-plus product. If someone charges you for NORTH access, they are scamming you.

**Q: Do I get intraday alerts?**
No. One post per week (Sunday 22:00 UTC), plus a mid-week status update Mon-Fri 12:00 UTC when a directional call is open. If you want scalping alerts or level breaks or NY-open plays, this is not the right channel.

**Q: Does the bot execute trades for me?**
No. NORTH publishes what the signal says. You decide whether to trade it and how to size the position. No copy-trading integration.

**Q: How long has this been live?**
Since 2026-07-22. See `docs/launch/track_record_current.md` for the current record and open call.

---

## About the signal

**Q: How does the signal actually work?**
Four conditions on daily gold prices, evaluated Friday close for the following Monday to Friday.
1. 4-week momentum sign (positive for LONG-eligible, negative for SHORT-eligible)
2. 12-week momentum sign
3. 10-day moving average versus 40-day moving average
4. 20-day change in US 10-year real yield

If all four agree bullish: LONG. If all four agree bearish: SHORT. Anything else: FLAT.

Entry Monday NY open (or reference price at publish). Stop is 2x the 20-day ATR from entry. Exit is Friday 21:00 UTC close, or the stop, whichever hits first.

That is the entire rule. No hidden knobs, no discretion, no override.

**Q: What is the backtest?**
2010-2026 gold data. Win rate 55.9% on directional weeks, +0.23% mean return per trade after costs, Sharpe 0.77, largest drawdown 5.6% of notional. Sits out about half the time (FLAT).

**Q: Would passive gold have made more?**
Yes, in raw return. But with about 3x the drawdown. NORTH captured 62% of buy-and-hold gold's P&L with 37% of the drawdown. That is the tradeoff.

**Q: Why is it FLAT so often?**
Because the four conditions have to all agree. In sideways markets or transition regimes, they typically disagree. FLAT is the correct action then, not a miss.

---

## About the honesty claims

**Q: You say every dead strategy is documented. Where?**
`docs/launch/retirement_wall.md` in the repo. 34 rejected trials listed with the verdict and reason. Auto-generated from `data/experiments/registry.json`.

**Q: How do I know you did not just publish the winning strategies and hide the losers?**
The registry file (`data/experiments/registry.json`) has 52 trials with git history going back months. Every rejection was pre-registered before it was tested. The pre-reg dates are in the file, visible in `git log`. You cannot post-hoc write "we killed this on 2026-08-03" into a file that git already timestamped when it was committed.

**Q: What if the signal starts losing?**
There is a kill switch. If live behavior diverges from the backtest, publishing halts. The halt criteria and process are in `docs/launch/halt_notice.md`. When it fires, we post on this channel explaining why, and no new calls go out until the reason is resolved or the strategy is retired.

---

## About using it

**Q: How do I actually take the trade?**
The Sunday post gives you: direction, reference entry price, stop, exit rule. You enter Monday at the market open when spot gold trades near the reference. Set your stop at the level in the post. Plan to exit at Friday close if the stop does not hit first. That is the whole process.

**Q: What position size should I use?**
Not a recommendation, because that depends on your account and risk tolerance. As a general rule: size so a full stop-out costs less than 1% of your account. If the stop is 2% below entry, that means position size = account / 2 for gold.

**Q: What if my broker does not have gold futures?**
You can trade GLD (SPDR Gold Shares ETF) or a similar gold-tracking product. The direction is the same. The stop-loss level applies to price, so translate accordingly.

**Q: Should I take every call?**
NORTH publishes every week. Whether to take a specific call is your call. If a directional call fires on a week you would not have been able to trade anyway (traveling, capital tied up, whatever), skip it. The strategy's edge is in the average across many calls, not in any specific one.

---

## About the team

**Q: Who runs NORTH?**
Farhad (owner, direction, honest review) and Knox (Claude AI, research and building). Both work with full transparency; the repo has every commit, every message, every backtest.

**Q: What is Knox?**
Anthropic's Claude, running as an interactive coding agent on Farhad's machine, focused entirely on NORTH. Not a general assistant. Signs the monthly market read post.

**Q: Why "NORTH"?**
Picked from a shortlist of five (PROOF, CANDOR, BEACON, NORTH, KILO). Directional, calm, monosyllabic, brand-flexible if the product line ever expands past gold.

---

## About the future

**Q: Will NORTH ever trade more than gold?**
Maybe. Universe expansion has been explored (silver, platinum, palladium, gold miners). Nothing else has cleared the same discipline yet. If a candidate does, it gets its own weekly call, either in this channel or an adjacent one. Not soon.

**Q: Will NORTH ever go paid?**
Not planned. If that ever changes, current subscribers will know first and existing behavior on this channel will not change. Free stays free.

**Q: How do I unsubscribe?**
Leave the Telegram channel. No mailing list, no cookies, no data to delete.
