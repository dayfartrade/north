# NORTH operator runbook - launch day, weekly maintenance, incidents

*One-pager for Farhad. Not for subscribers.*
*Use as a checklist. Everything here has a script or a filepath, not a "figure it out."*

---

## Pre-launch one-time steps (2026-08-17 pending)

1. Rename the public Telegram channel from "Gold Day Trader - Live Alerts" to "NORTH". Farhad-only via Telegram app (channel > tap name > Edit > save). Bot cannot rename.
2. Grant bot pin permission: Telegram app > channel > Administrators > @GOLDDAYTARDER_bot > toggle "Pin Messages" on. After this, bot auto-pins Message 1 on launch day.

## Sunday launch day - operator sequence

Do these in order. Do not skip steps.

**T-24 hours (Saturday night)**
1. `git pull` locally to sync any workflow auto-commits.
2. `python scripts/launch_readiness.py`. Confirm 8/0/0.
3. Read `docs/launch/north_public_intro.md` (or pick from alternates). Edit if needed.
4. Read `docs/launch/subscriber_faq.md`. Edit if needed.

**T-2 hours (Sunday 20:00 UTC)**
5. Wait for the pre-publish preview to fire at Sunday 21:00 UTC to the private channel. Verify it renders cleanly and the direction matches your expectation.

**T+0 (Sunday 22:00 UTC decision)**
6. If preview showed a directional call: this is the launch window. Proceed to step 7.
7. If preview showed FLAT: decide whether to launch FLAT anyway or wait one more week. See "Launch on FLAT?" section below.

**Message 1 (intro, pinned)**
8. Copy contents of `docs/launch/north_public_intro.md` (the version you picked).
9. Post to public channel via bot. Bot cannot pin, so pin manually via the Telegram app.

**Message 2 (current state, unpinned)**
10. Regenerate the state block: `python scripts/render_track_record.py --stdout | head -20`.
11. Copy the concise state block (not the whole markdown) into a new post to the public channel.

**Message 3 (first weekly call)**
12. Sunday 22:00 UTC weekly-publish workflow fires automatically. No manual step. Watch the channel.
13. If message does not appear within 5 minutes: check `.github/workflows` Actions tab, and Telegram private channel for the failure notification.

**T+15 min post-launch**
14. Copy the public channel link and send it to the invite list (`docs/launch/invite_message.md`).
15. Do NOT post to Twitter, LinkedIn, or any broadcast surface yet. This is a soft launch.

## Launch decision - LOCKED 2026-08-17

Two-stage warm-up (Option C per `docs/launch/north_first_send.md`):
- **Stage 1** on Sunday 2026-08-23 22:15 UTC: intro + warm-up welcome, regardless of that Sunday's signal direction.
- **Stage 2** whenever: first automated directional call fires + Farhad posts a short manual heads-up.

No further decision needed. Follow the sequence in `north_first_send.md`.

## Weekly maintenance (Sunday nights)

After every weekly-publish (auto):
1. Verify the call landed on Telegram (check the channel).
2. If a directional call resolved during the past week: verify the outcome post landed.
3. Check the private-channel drift monitor alert (Sunday 23:00 UTC). If it fires, investigate before next publish.
4. `python scripts/north_status.py` weekly, just to sanity-check.

## Incident response - the halt sequence

If something is wrong (drift alert fires, bug found, data source dies):

1. `touch data/far_weekly_paused` locally. Commit. Push.
   OR: create the file directly in a GitHub commit via web UI.
2. This halts BOTH weekly-publish and daily-brief. Verified in `daily_brief.py` and `far_weekly_gold_read_publish.py`.
3. Post a halt notice to the public channel using `docs/launch/halt_notice.md` template. Fill in the bracketed fields.
4. Post the same halt notice to the private channel.
5. Diagnose the root cause. Do not lift the halt until the specific gate defined in the halt notice is satisfied.

## Incident response - lifting the halt

1. Verify the underlying cause is resolved (data fixed, bug patched, drift explained).
2. Delete `data/far_weekly_paused`. Commit. Push.
3. Post a resume notice on the public channel:
   - What was wrong (past tense)
   - What was fixed or verified
   - Next scheduled publish will fire on schedule
4. Watch the next publish carefully.

## Monthly rhythm

- **1st of the month:** publish the Knox monthly market read using `docs/launch/knox_market_read_template.md`.
- Bump the version-count numbers in `north_public_intro.md` if the retirement wall passes a milestone (e.g., first 100 rejections).

## What is NOT in this runbook

- Trading advice. NORTH publishes signals. What you personally do with them is your own risk decision.
- Marketing. Soft launch is DM-only. Broad marketing is a separate playbook to be written before full launch.
- Legal disclosures. Depending on jurisdiction, publishing calls to a wider audience may trigger disclosure requirements. Not scoped here.

## Emergency contact

If the bot stops responding entirely (Telegram side, not workflow side):
1. Check bot status via `curl -sS "https://api.telegram.org/bot${GOLDTRADER_TG_TOKEN}/getMe"`.
2. If down, halt the workflows and post a manual notice via your personal Telegram account.
3. Do not rotate the token unless it is definitively compromised. Rotating requires updating GitHub secrets.
