# NORTH soft-launch plan (as of 2026-08-24)

*Written the morning after the first directional call fired. Public repo
just flipped. Farhad has the intro + welcome + Stage 2 note ready to
post plus DMs to send.*

---

## 1. Where we are right now

- **Product:** NORTH v1, weekly gold direction call (LONG/SHORT/FLAT).
- **Backtest 2010-2026:** 55.9% win rate on directional weeks, +0.23%
  mean return per trade after costs, Sharpe 0.77, $56,043 max drawdown
  over 17 years on one contract per week (5.6% of $1M account).
- **Live since:** 2026-07-22.
- **Live track record:** 1 SHORT resolved -0.72%. 1 LONG open this week
  (2026-08-24 to 08-28, entry ~$4602, stop $4401).
- **Public surface:** Telegram channel "NORTH" (renamed 2026-08-17).
  Auto-post fires every Sunday 22:00 UTC. Mid-week updates fire
  Mon-Fri 12:00 UTC while a position is open.
- **Repo:** github.com/dayfartrade/north, PUBLIC (flipped 2026-08-24).
- **Kit ready:** intro + welcome + Stage 2 note in `north_first_send.md`,
  DM copy in `invite_message.md`, halt notice template ready.

## 2. Today (2026-08-24)

Blocking on Farhad only:

1. Post Message 1 (intro) to NORTH channel. Long-press > Pin.
2. Post Message 2 (welcome) unpinned right after.
3. Post Message 3 (mechanics + sizing note) right after.
4. DM 5-10 people from invite list using `invite_message.md` Version A
   (for traders) or Version B (for feedback-only friends).
5. Check the channel for early DM feedback in the evening.

Everything is copy-paste. Total time: 15-20 minutes.

## 3. This week (2026-08-24 to 2026-08-28) - LONG position open

**Automated:**
- Mon-Fri 12:00 UTC: daily brief posts to channel with signal health,
  open P&L, distance to stop. This is the FIRST live daily-brief run
  with an open position, so watch how it renders.
- Fri 21:00 UTC: position exits automatically at Friday close, or the
  stop hits earlier and posts a resolve.
- Sun 22:00 UTC: next weekly call publishes (LONG/SHORT/FLAT). This is
  also the first Sunday after the workflow-push fix landed, so
  verify the auto-commit reaches the repo cleanly.

**Farhad's attention:**
- Read every daily brief when it lands. If formatting looks bad on
  mobile Telegram, note it, fix in code by Wednesday, redeploy for
  Thursday's brief.
- Watch for early subscriber questions in DMs. Do NOT publicly reply to
  feedback in the channel. Keep the channel signal-only.
- Do NOT change the intro or pinned message this week under any
  circumstance. Pinned content becomes stale fast if edited mid-cycle.

**Kill switch conditions this week:**
- Bot stops responding: verify with `curl "https://api.telegram.org/bot${GOLDTRADER_TG_TOKEN}/getMe"`.
- Weekly-publish workflow fails to post on Sunday: check Actions log,
  manually publish via `python scripts/far_weekly_gold_read_publish.py --force`.
- Signal state diverges wildly from backtest (drift monitor fires
  Sunday 23:00 UTC on private channel): investigate before next
  publish. Halt if unexplained.

## 4. First 30 days (2026-08-24 to 2026-09-23)

**Cadence:**
- 5 weekly calls in this window (08-24, 08-31, 09-07, 09-14, 09-21).
- Expected directional distribution based on backtest: ~2-3 directional,
  ~2-3 FLAT. LONG regime looks bullish right now so the base rate might
  tilt LONG-heavier, but the honest expectation is close to base.

**Milestones:**
- **Sample size:** at end of 30 days, expect 3-4 resolved directional
  calls. Still not statistically meaningful. Live-tracking is validation
  of process, not signal quality.
- **First Knox monthly market read:** end of August (2026-08-31). Long-
  form post per `knox_market_read_template.md`. Anchor to what NORTH
  actually saw and what gold actually did. No prediction, no
  jargon. Signed "Knox, Farhad's Claude coder."
- **Retirement wall growth:** any new experiments run + rejected during
  this window auto-append to the wall on next Sunday publish.

**Subscriber growth:**
- Cap invite list at 15-20 by end of month. This is a soft launch, not
  an audience play. The point is honest early feedback, not scale.
- No public promotion. No Twitter, no LinkedIn, no forum posts.
- Feedback loop: whenever a subscriber DMs Farhad, log a one-line note
  in `data/subscriber_feedback.jsonl` (new file, add on first use) with
  timestamp + what they said + what changed as a result.

**Decision points during this window:**
- If 2+ subscribers report the same UX issue: fix it that week.
- If 0 subscribers engage after 2 weeks: don't panic. Small list, no
  push, low touch. Not a signal about the product.
- If a subscriber asks "can I trade this?" - respond in DM, do not
  scale up the product for them.

## 5. Success + failure criteria (60-day gate)

By 2026-10-24, evaluate the product on:

**Ship-forward criteria (any 2 of 3):**
- 8+ resolved directional calls with cumulative net return > -1% (i.e.,
  not systematically failing, even if noisy)
- Positive subscriber feedback signal (at least 2 people who found
  the channel useful for reasons other than "nice to see the discipline")
- No unresolved bugs in the publishing pipeline (drift monitor clean,
  weekly-publish push clean, daily-brief format clean)

**Retire-or-revise criteria (any of these):**
- 8+ resolved calls with cumulative net < -3%: reconsider mechanism,
  do a formal drift analysis, decide whether to halt for a re-review
  or accept the drawdown as sample noise
- Any pre-registered halt gate fires (SPRT, drawdown, drift): honor
  the halt, post the notice, investigate before resuming
- Subscribers actively confused by the format or the disclaimers: fix
  the copy, don't blame the reader

**Neither:** stay soft-launched. Do not push growth just because time
passed. The invitation to widen the audience needs positive evidence,
not a calendar tick.

## 6. Widening the audience (if 60-day gate is passed)

Only after passing the ship-forward criteria:

1. Website activation (`website_activation.md` Option 1: GitHub Pages).
   Deploy `site/` to `dayfartrade.github.io/north/weekly.html`. Update
   intro to include the URL.
2. Announce publicly, once, in a way that matches the discipline.
   Suggested surfaces: a low-key Twitter thread from Farhad's account
   linking the retirement wall, a Reddit post to a trading community
   that tolerates honesty, a mention in the Knox monthly read.
3. Do NOT switch to a paid tier. Free forever is a product decision,
   not a marketing gimmick.

## 7. Kill switches (any of these fire regardless of the plan)

- SPRT pre-reg halt condition triggers on live data
- Data pipeline breaks (Dukascopy XAUUSD or FRED DFII10 unreachable
  for >48 hours)
- Bot loses access to Telegram (channel deletion, token revocation, etc.)
- Farhad is genuinely unavailable for >1 week without a designated
  fallback (currently no fallback exists - not a real risk yet)
- Any signal drift the drift monitor cannot explain within 48 hours

Halt procedure is in `docs/launch/halt_notice.md`. Kill switch is
`touch data/far_weekly_paused` + commit + push. Halts BOTH the weekly
publish and the daily brief.

## 8. Communication cadence

**Public channel (NORTH):**
- Sunday 22:00 UTC: weekly call (auto)
- Mon-Fri 12:00 UTC when position open: daily brief (auto)
- End of month: Knox market read (manual, drafted from template)
- On any halt event: honest halt notice (manual, from template)

**Farhad's DMs:**
- One reply per DM per day, max. Do not spend all day chatting about
  gold. This is a signal service, not a discussion forum.
- All feedback funnels through DM. No public replies in the channel.

**Private ops channel:**
- Continues to receive drift monitor, pre-publish previews, failure
  notifications from all workflows. Farhad only.

## 9. Metrics to track

**Weekly (auto in `track_record_current.md`):**
- Weeks published, directional vs FLAT split
- Directional win rate, cumulative net return
- Latest resolved outcome + reason
- 8 most recent calls

**Monthly (Farhad checks manually first of month):**
- Subscriber count in NORTH channel (Telegram admin panel)
- DM feedback log entries
- Retirement wall size (auto)
- Any drift monitor red flags (private channel scroll)

## 10. Explicit decision points ahead

Chronologically, in order they're likely to hit:

- **Fri 2026-08-28 21:00 UTC:** first LONG resolves. Reaction: check
  outcome, watch how the resolve post lands, do not comment.
- **Sun 2026-08-30 22:00 UTC:** next weekly call. First test that the
  workflow push fix works. Do not force-run if it fails - just note it
  and investigate.
- **Sun 2026-08-31 (last day of Aug):** first Knox monthly market read.
  Farhad drafts + posts.
- **~Week 4 (mid-September):** decide whether to open the invite list
  to a second batch of 5-10 (or hold at first batch).
- **2026-10-24:** 60-day ship-forward gate evaluation.

## 11. What NOT to do during soft launch

- Do not add features. NORTH v1 rules are frozen.
- Do not change the pinned intro copy. Edit only if there is a factual
  error that misleads subscribers.
- Do not run experiments that would touch the public channel until
  after the 60-day gate.
- Do not respond to public reactions in the channel. All feedback via
  DM only.
- Do not benchmark against other signal services or trader Twitter.
  The retirement wall is the differentiator; do not defend it in
  arguments.
- Do not push more strategies into v1's pipeline. Universe expansion,
  BB-hybrid, ensemble ship - all wait until v1 has 25+ resolved
  directional trades.

## 12. Owners

- Farhad: publishing decisions, direction, DMs, subscriber experience,
  monthly market read final draft.
- Knox (Claude): code, research, drafts, pipeline maintenance, monthly
  market read first pass.

The one durable rule: any change to what subscribers see requires
Farhad's explicit sign-off. Knox does not push to the public channel
without it.
