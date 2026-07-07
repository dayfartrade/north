---
name: Accelerate; never waste time
description: When work is ready to move forward, move it forward. Don't propose caution defaults that add delay for no reason.
type: feedback
originSessionId: bb75b257-d83d-4c28-b913-c3fc4a842a01
---
When a task is at a natural next step (commit, run, ship, deploy), **just do it** — don't propose "wait and see" defaults. The user's operating tempo is aggressive: launches are on tight windows and every delay compounds against the deadline.

**Why:** User explicitly said "commit them now, why wait? ... never waste time." Was reacting to my suggestion to hold uncommitted patches in the working tree until we'd watched a live session run against them. That kind of caution adds a session of latency for a diff we can already revert with `git revert`.

**How to apply:**
- If code changes are complete and tests/imports pass, commit immediately unless the user has asked to gate on something specific.
- If a plan is agreed, start executing — don't restate it or ask for a further green light.
- Prefer parallel tool calls to serial. Prefer running the thing over describing the thing.
- Don't sandbag deadlines. If a 20-day plan can compress to 15, propose the compression, not the buffer.
- Reversibility is the guardrail — for reversible actions (commits, restarts, temp files), lean toward action. For irreversible ones (destructive git ops, external sends), still confirm first.
- Applies broadly across this project — this is a durable tempo preference, not a one-off.
