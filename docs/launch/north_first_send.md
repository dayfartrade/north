# NORTH soft-launch - two-stage sequence

*Farhad decision 2026-08-17: Option C, warm-up launch.*
*Stage 1 is intro + onboarding this Sunday 2026-08-24 regardless of signal direction.*
*Stage 2 is the first directional call whenever it fires (could be same day, could be weeks later).*

---

## Stage 1: warm-up launch (Sunday 2026-08-24 22:15 UTC)

Posts land AFTER the automated weekly-publish workflow has fired at 22:00 UTC (which will publish whatever direction the signal says - probably FLAT again).

**Message 1: intro (pinned)**
Use `docs/launch/north_public_intro.md` verbatim (currently Version C - practical).

Operator step:
- Copy contents of `north_public_intro.md`
- Post to public channel via bot
- If bot has pin permission (per pre-launch step 2): it will pin automatically
- If not: tap "pin" in the Telegram app after the bot posts

**Message 2: warm-up welcome (unpinned, posted right after intro)**

```
This channel is now live for a small invite list. Welcome.

Here is where we are:

- Last three weeks were FLAT (2026-08-03, 08-10, 08-17). That is the
  signal doing exactly what it is supposed to do when the four
  conditions disagree. Not a bug, not a miss.
- The one directional call resolved so far (2026-07-27 SHORT) lost
  0.72%. Documented, unedited, on the track record page.
- The very first automated Sunday post has now hit this channel just
  above (see 22:00 UTC).

What happens next:

- Every Sunday 22:00 UTC: one call, three possible shapes (LONG,
  SHORT, or FLAT). No push, no urgency.
- The next few weeks may keep being FLAT. When conditions align, a
  directional call will fire and you will see the mid-week updates
  too.

If you were invited by Farhad and want to give feedback: just DM him.
Everything is under active development and honest bad news is welcome.

Repo: github.com/dayfartrade/north
Track record: github.com/dayfartrade/north/blob/main/docs/launch/track_record_current.md
Retirement wall: github.com/dayfartrade/north/blob/main/docs/launch/retirement_wall.md
```

**Message 3: no manual action**
The Sunday 22:00 UTC weekly-publish already fired ~15 minutes earlier. Its post is above Messages 1 and 2 in the channel scroll. Subscribers see, from top to bottom (newest first when they open the channel):
1. Message 2 (warm-up welcome)
2. Message 1 (intro, also pinned at the very top)
3. The automated Sunday weekly card

## Stage 2: first directional launch (whenever it fires)

Automatic. The first Sunday the weekly-publish workflow emits a LONG or SHORT (not FLAT), the following happens:
- Automated post lands at 22:00 UTC with the directional card
- Automated mid-week updates fire Mon-Fri 12:00 UTC while the position is open
- Automated resolve post lands the following weekend

**Manual step (Farhad):**
Post one short note to the channel after the directional card lands:

```
First directional call is live. Take it or watch. Full mechanics in the
post above. Reference entry, stop, exit rule all shown. Mid-week
updates will fire Mon-Fri 12:00 UTC while this position is open.

If you trade it, size for less than 1% account loss on a full stop-out.
This is not advice. Full risk statement in the pinned message.
```

Then DM the invite list separately with a heads-up ("first live call fired, check the channel").

## Order of operations on Stage 1 day (Sunday 2026-08-24)

**T-24 hours (Saturday 2026-08-23 night)**
1. `git pull` locally to sync any workflow auto-commits.
2. `python scripts/launch_readiness.py`. Confirm 8/0/0.
3. Confirm the two pre-launch one-time steps are done:
   - Public Telegram channel renamed to "NORTH"
   - Bot has "Pin Messages" permission
4. Read `docs/launch/north_public_intro.md` one more time.

**T-2 hours (Sunday 2026-08-24 20:00 UTC)**
5. Wait for the pre-publish preview at 21:00 UTC to the private channel. Verify it renders cleanly.

**T+0 (Sunday 2026-08-24 22:00 UTC)**
6. Weekly-publish workflow fires. Watch the public channel - the automated Sunday post should appear.

**T+15 min (Sunday 2026-08-24 22:15 UTC)**
7. Post Message 1 (intro). Verify pin fires (bot should auto-pin).
8. Post Message 2 (warm-up welcome).
9. Copy the public channel link. DM the invite list per `docs/launch/invite_message.md`.

**T+2 hours (Monday 2026-08-25 00:00 UTC)**
10. Check channel for any early DM feedback. Respond via DM (do not publicly reply to feedback).

## Rollback if Stage 1 goes badly

Halt the automated pipelines:
- `touch data/far_weekly_paused` (halts BOTH weekly-publish and daily-brief)
- Commit and push, or create the file directly via GitHub web UI

Post an honest halt notice to the public channel using `docs/launch/halt_notice.md`.

## Pre-launch punchlist (must all be true before Message 1 on Stage 1)

- [x] `docs/launch/north_public_intro.md` locked to Version C
- [x] `docs/launch/retirement_wall.md` regenerates auto on every publish
- [x] `docs/launch/track_record_current.md` regenerates auto on every publish
- [ ] Public Telegram channel renamed to "NORTH" (Farhad step, one-time)
- [ ] Bot has "Pin Messages" permission on the channel (Farhad step, one-time)
- [x] `GOLDTRADER_TG_CHAT_PUBLIC` GitHub secret matches the channel ID (verified via successful publish on 2026-08-16 and later runs)
- [x] Kill switch removed if present (`data/far_weekly_paused` does not exist)
- [x] Halt notice template written at `docs/launch/halt_notice.md`
- [ ] Farhad has invite list ready for Stage 1 DMs
