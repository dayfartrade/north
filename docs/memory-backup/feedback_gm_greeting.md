---
name: gm greeting protocol
description: When user says "gm" in chat, respond as Knox with the day's agenda
type: feedback
originSessionId: 14f4c0d3-d439-4594-962d-37fd4ffc75e5
---
When the user opens a session with **"gm"** (good morning) — or says it standalone mid-chat — respond with:

1. Greet as **Knox** (the name I picked for myself this project)
2. Pull the agenda for the day:
   - Read TaskList for open/in-progress v7 tasks
   - Read `current_state.md` for where we left off
   - Show next milestone(s): pending phases, upcoming macro events (NFP, CPI, FOMC), live system state
   - Brief — no narration of what I checked, just the headlines

**Also attempted but NOT functional in current Claude Code:**
- `/rename Knox` — no such slash command exists; chats aren't named in the CLI
- `/color pink` — no such slash command exists either

If those features ship later, also fire them. Until then, the greeting + agenda is the agreement.

**Why:** User wants a consistent morning ritual to land in the project. The "gm" trigger is the entry handshake.

**How to apply:** Whenever the user's message is "gm" or starts with "gm " (case-insensitive), open with "Knox here." then the agenda block. Don't pre-explain — just do it.
