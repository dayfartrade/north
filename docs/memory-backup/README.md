# Memory backup

Point-in-time snapshot of Claude Code's auto-memory for this project. Not
the live source (memory lives at
`C:\Users\farha\.claude\projects\C--golddaytrador\memory\` and updates
in-conversation). This directory is a durable backup in case the local
machine fails.

**Excluded from backup** (contain references to secrets, even though the
secrets themselves live in gitignored files):
- `ref_telegram.md` — bot handle + local chat_id
- `ref_github.md` — token file location

**Last snapshot:** 2026-07-08 ~00:35 UTC after 13-commit polish sprint
(range `4a43a7c..f2d55d8`).

**To restore:** copy files back to the memory directory. `MEMORY.md` is the
index. Read `next_gm_agenda.md` first for the current-state briefing.
