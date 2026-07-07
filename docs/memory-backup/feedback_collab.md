---
name: How to collaborate on golddaytrader
description: User's explicit feedback on working style — sanity checks, full effort, no docs
type: feedback
originSessionId: 1ac19be5-b4ac-4956-bb4b-a7b8b1790204
---
**1. Sanity-check periodically — don't drift from the single goal.**
Why: User explicitly noted prior Claude sessions "drifted" away from the goal. Every few steps, restate: "GOAL = profitable GC day-trader signals. Am I serving it?"
How to apply: At natural breakpoints in long work sessions, insert one-line goal restatement.

**2. Do 100% effort BEFORE the first live test — not after.**
Why: User explicitly said "do as little or as much research and preparations" up front, then later "100% effort before we test." They want all elevation work done pre-deploy.
How to apply: Don't ship v1, then add filters/risk-mgmt/null-tests. Do all of that BEFORE deploy. Synthetic null + inverse null + walk-forward + DSR are minimum standards before claiming "ready."

**3. No documentation files (.md) unless explicitly requested.**
Why: Default Claude behavior creates README/STATUS.md files; user finds these noisy.
How to apply: Communicate via Telegram + conversation. Code comments only when WHY is non-obvious. Do not create *.md project files.

**4. Fresh perspective — don't anchor on user's prior approaches.**
Why: User has tried many approaches and will share them AFTER initial work. Anchoring early would defeat the purpose of "fresh perspective."
How to apply: Continue producing independent work until user shares prior context. Then integrate.

**5. Honest negative results are valuable — don't sugarcoat.**
Why: User explicitly approved when I shipped v5 with the honest Sharpe-0.59 / DSR-4% rather than overselling the headline 2.30.
How to apply: When validation fails, report it clearly. Don't paper over weaknesses with stronger language than the data supports.

**6. When asked for an audit, do MULTIPLE passes — first pass misses things.**
Why: In the v6 deploy, I declared "audit complete" after one pass. User asked for another audit and we found 3 more bugs (D1: tracker importing wrong strategy version; D2: DST not propagated; D10: stale cost constant). The second pass paid off.
How to apply: When user requests an audit, plan for at least two passes covering different angles (logic, data flow, downstream-constant-propagation, edge cases). Read modules not touched in the obvious flow.

**7. When changing a deployed constant, grep ALL downstream files.**
Why: Cost model went from $0.24 → $0.19 in backtest.py but `position_sizing.py` and indirectly the trackers kept stale copies. Same for strategy version (v4 → v5) and session times (fixed UTC → DST-aware).
How to apply: After ANY change to a shared constant (cost, strategy version, frozen params, schedules), grep for the OLD value across `src/` and update or import from a single source of truth.
