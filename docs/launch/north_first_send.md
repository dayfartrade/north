# NORTH soft-launch - two-stage sequence

*Farhad decision 2026-08-17: Option C, warm-up launch.*
*Stage 1 is intro + onboarding this Sunday 2026-08-23 regardless of signal direction.*
*Stage 2 is the first directional call whenever it fires (could be same day, could be weeks later).*

---

## Actual status (updated 2026-08-24)

The Sunday 2026-08-23 22:51 UTC auto-publish signaled **LONG** (first
directional call after three weeks FLAT). The Telegram post landed
successfully in the public channel. The workflow's git-push failed
(separate bug, tracked). Farhad did NOT execute the manual Stage 1 or
Stage 2 steps that night.

**Both stages now execute together on 2026-08-24** using the catch-up
sequence at the bottom of this document. The Stage 1 and Stage 2
sections below are preserved as the reference for future launches.

---

## Stage 1: warm-up launch (Sunday 2026-08-23 22:15 UTC)

Posts land AFTER the automated weekly-publish workflow has fired at 22:00 UTC (which will publish whatever direction the signal says - probably FLAT again).

**Message 1: intro (pinned)**

The source of truth is `docs/launch/north_public_intro.md` but that file is GitHub Markdown (**bold**), which Telegram does not render correctly. Use one of these two paths on launch day:

Path A (Telegram Markdown, best for copy-paste from phone):
- `python scripts/render_intro_for_telegram.py --format telegram > /tmp/intro.txt`
- Copy the contents of /tmp/intro.txt into a new Telegram post to the NORTH channel
- Telegram detects the *bold* markers and renders them properly

Path B (HTML mode, only if sending via bot API programmatically):
- `python scripts/render_intro_for_telegram.py --format html > /tmp/intro.html`
- Send via curl/API with `parse_mode=HTML`

Path C (plain, guaranteed to work, no formatting):
- `python scripts/render_intro_for_telegram.py --format plain > /tmp/intro.txt`
- Paste as-is; no bold, but no risk of parse error either

Then: tap and hold the message > tap "Pin". Channels do not have a separate bot pin permission, so this manual step is required regardless of send path.

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

## Order of operations on Stage 1 day (Sunday 2026-08-23)

**T-24 hours (Saturday 2026-08-22 night)**
1. `git pull` locally to sync any workflow auto-commits.
2. `python scripts/launch_readiness.py`. Confirm 8/0/0.
3. Confirm the two pre-launch one-time steps are done:
   - Public Telegram channel renamed to "NORTH"
   - Bot has "Pin Messages" permission
4. Read `docs/launch/north_public_intro.md` one more time.

**T-2 hours (Sunday 2026-08-23 20:00 UTC)**
5. Wait for the pre-publish preview at 21:00 UTC to the private channel. Verify it renders cleanly.

**T+0 (Sunday 2026-08-23 22:00 UTC)**
6. Weekly-publish workflow fires. Watch the public channel - the automated Sunday post should appear.

**T+15 min (Sunday 2026-08-23 22:15 UTC)**
7. Post Message 1 (intro). Tap and hold > Pin (~3 seconds).
8. Post Message 2 (warm-up welcome) - do NOT pin.
9. Copy the public channel link. DM the invite list per `docs/launch/invite_message.md`.

**T+2 hours (Monday 2026-08-24 00:00 UTC)**
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
- [ ] Public Telegram channel renamed to "NORTH" (Farhad step, one-time, in Telegram app)
- [x] Bot pin permission: N/A for channels (not a separate permission); Farhad pins Message 1 manually on launch day
- [x] `GOLDTRADER_TG_CHAT_PUBLIC` GitHub secret matches the channel ID (verified via successful publish on 2026-08-16 and later runs)
- [x] Kill switch removed if present (`data/far_weekly_paused` does not exist)
- [x] Halt notice template written at `docs/launch/halt_notice.md`
- [ ] Farhad has invite list ready for Stage 1 DMs

---

## Catch-up sequence for 2026-08-24 (Stage 1 + Stage 2 combined)

Context: the Sunday 2026-08-23 22:51 UTC auto-publish sent a LONG call
to the public channel. The channel is renamed to "NORTH". No pinned
intro, no welcome, no invite DMs went out that night. Anyone landing in
the channel right now sees a bare directional card with no context.

Three posts, in this order. All plain text (Telegram Markdown may be
used for `*bold*` per `scripts/render_intro_for_telegram.py`).

### Post 1 - intro (pinned)

Render and paste, then pin manually:

```
python scripts/render_intro_for_telegram.py --format telegram > /tmp/intro.txt
```

Copy `/tmp/intro.txt` contents into a new post in the NORTH channel.
Then tap and hold the message > "Pin" > "Notify all members" is optional.

### Post 2 - warm-up welcome (unpinned, posted right after Post 1)

Copy verbatim:

```
This channel is now live for a small invite list. Welcome.

Where we are:

- Last night's automated Sunday post is a LONG call on gold for this
  week (2026-08-24 to 08-28). It is the first directional call from
  NORTH v1 in about a month. The four signal conditions all lined up
  bullish. Full mechanics (entry, stop, exit rule) are in the automated
  post further down in the channel.
- The two published weeks before that (2026-08-10 and 2026-08-17) were
  both FLAT. That is the signal doing exactly what it is supposed to
  do when the four conditions disagree.
- The only prior directional call (2026-07-27 SHORT) resolved at
  -0.72%. Documented on the track record page.

What happens next:

- Mid-week updates fire Mon-Fri around 12:00 UTC while this LONG
  position is open. They show signal health, open P&L, and distance to
  the stop.
- Friday close: the position exits automatically at 21:00 UTC, or the
  stop hits earlier.
- The following Sunday 22:00 UTC: the next call publishes (LONG, SHORT,
  or FLAT again).

If you were invited by Farhad and want to give feedback: DM him.
Everything is under active development and honest bad news is welcome.

Repo: github.com/dayfartrade/north
Track record: github.com/dayfartrade/north/blob/main/docs/launch/track_record_current.md
Retirement wall: github.com/dayfartrade/north/blob/main/docs/launch/retirement_wall.md
```

### Post 3 - Stage 2 mechanics + sizing note (unpinned, right after Post 2)

Copy verbatim:

```
Quick mechanics + sizing note on the LONG call above.

Direction: LONG gold, this week only (2026-08-24 to 08-28).
Reference entry: ~$4602 (Monday NY open).
Stop: $4401 (2x the 20-day ATR from entry, ~4.4% below entry).
Exit: Friday 21:00 UTC close, or the stop hits earlier.

If you trade it, size for less than 1% account loss on a full
stop-out. That means position size = account / 4.4 or smaller.

This is not advice. Full risk disclaimer in the pinned intro above.
```

### Post-post: DM the invite list

Use `docs/launch/invite_message.md` Version A (updated 2026-08-24 to
reference the LONG going out). Send one-to-one, not broadcast.

### Order of operations checklist (do in this order)

1. `git pull` locally to make sure track_record and retirement_wall are current.
2. `python scripts/render_intro_for_telegram.py --format telegram > /tmp/intro.txt`.
3. Open NORTH channel in Telegram app.
4. Post 1 (intro). Tap and hold > Pin.
5. Post 2 (welcome).
6. Post 3 (Stage 2 mechanics note).
7. DM invite list per `invite_message.md`.
8. Check channel for early feedback via DM later today.

### Rollback if anything looks wrong

If after posting you notice a factual error or a formatting break:
- Edit the post in Telegram (long-press > Edit) rather than deleting.
- If it is worse than that, do NOT keep publishing. Halt with
  `touch data/far_weekly_paused` and post the halt notice from
  `docs/launch/halt_notice.md`.
