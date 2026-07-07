---
name: Memory use caution for this project
description: User observed prior sessions drifted by over-relying on memory; verify before applying
type: feedback
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
At the start of the very first session, user said: "I don't think you should read from memory, cause your 2 predecessors got so confused, kept drifting." They later changed course and asked me to save memory ONCE the v5 system was working end-to-end ("update your memory").

**How to apply:**
- At session START on this project, READ MEMORY.md first for context, but don't blindly apply remembered claims. Verify against current code state before acting on memory.
- Specifically: if memory claims a file/function/parameter exists, grep for it before recommending it to user. The codebase moves; memory can lag.
- If the user asks for "fresh perspective" on a new sub-problem, downweight memory-based suggestions and re-research.
- If outdated memory contradicts current code, trust the code and update or delete the stale memory.
