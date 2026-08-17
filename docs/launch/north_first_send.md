# NORTH soft-launch - first send sequence

*The exact messages to publish when the soft-launch trigger fires. Ordered.*
*Post each to the public Telegram channel (`GOLDTRADER_TG_CHAT_PUBLIC`).*

---

## Message 1: pin this first (before any weekly call)

Use `docs/launch/north_public_intro.md` verbatim (currently Version C - practical). Post it, then pin it in the channel. This is the "what NORTH is" message every new subscriber sees at the top.

**Operator step:** if bot has pin permission (pre-launch step 2), it will pin automatically after posting. If not, tap "pin" in the Telegram app after the bot posts.

## Message 2: current state snapshot (unpinned, posted right after intro)

```
📊 Current state - NORTH v1

Week of 2026-08-17 to 2026-08-21: FLAT
(third consecutive FLAT week; signal has not cleared all four conditions since 2026-07-27)

Live since: 2026-07-22
Directional calls to date: 1
  2026-07-27 SHORT → -0.72% (Friday close exit)
Cumulative net: -0.72%

Next publish: Sunday 2026-08-24 22:00 UTC

Retirement wall (52 strategies tested, 34 dead):
github.com/dayfartrade/north/blob/main/docs/launch/retirement_wall.md
```

**Operator step:** regenerate this block from `python scripts/render_track_record.py` on the day of launch, then copy the relevant chunk. Do not send the full markdown file verbatim, only the readable state snapshot.

## Message 3: first weekly call (Sunday 22:00 UTC after launch)

Already automated via `.github/workflows/weekly-publish.yml`. No manual step. The weekly card format is the one live-tested on 2026-08-10 (message_id 148). Subscribers will see it at Sunday 22:00 UTC as normal.

## Order of operations on launch day

1. Confirm `data/far_weekly_paused` does NOT exist (kill switch off).
2. `python scripts/north_status.py --github` - confirm all workflows green.
3. Post Message 1 (intro). Pin it.
4. Post Message 2 (current state). Do not pin.
5. Wait for Sunday 22:00 UTC weekly-publish workflow to fire the first live call to the public channel.
6. Monitor Telegram delivery for the first 5 minutes.
7. If all clean: soft launch is live. Announce to invite list separately.
8. If anything looks wrong: `touch data/far_weekly_paused` immediately, then debug.

## Rollback if the first launch goes badly

- `touch data/far_weekly_paused` halts BOTH weekly-publish and daily-brief.
- Post an honest halt message to the public channel using the template in
  `docs/launch/halt_notice.md` (needs to be written before launch - see punchlist below).

## Pre-launch punchlist (must all be true before Message 1)

- [ ] `docs/launch/north_public_intro.md` reviewed by Farhad, wording final
- [ ] `docs/launch/retirement_wall.md` regenerated fresh (`python scripts/build_retirement_wall.py`)
- [ ] `docs/launch/track_record_current.md` regenerated fresh (`python scripts/render_track_record.py`)
- [ ] Public Telegram channel exists and bot has admin+pin permissions on it
- [ ] `GOLDTRADER_TG_CHAT_PUBLIC` env is set on GitHub Actions secrets and matches the public channel ID
- [ ] Kill switch removed if present
- [ ] Halt notice template written at `docs/launch/halt_notice.md`
- [ ] Farhad has invite list ready for personal announce after Message 2
