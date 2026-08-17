# NORTH halt notice - template

*Post this to the public Telegram channel when the kill switch is activated.*
*Fill in the bracketed fields, keep the tone the same.*

---

## Standard halt notice

```
⛔ NORTH - publishing halted [YYYY-MM-DD HH:MM UTC]

The kill switch is on. No new weekly calls or daily briefs will publish
until this halt clears.

Reason: [one sentence - what triggered the halt]
Trigger: [manual / drift monitor / data pipeline failure / other]

What this means for anyone in the live position (if applicable):
[free text - usually "the trade that's currently open stays open on its
original stop and time exit; we just aren't publishing new calls after it"]

What has to happen for publishing to resume:
[list the specific gates - e.g., "review the drift analysis and confirm
the strategy still matches its backtest", "resolve the data source
issue and re-run the last publish preview", "fix the identified bug
and re-test the pipeline end-to-end"]

Next update: [date/time you commit to posting an update by]

Repo audit trail:
- Kill switch file: data/far_weekly_paused
- Last publish: [link to jsonl commit]
- Drift monitor last run: [link]

- Farhad + Knox
```

## What NOT to say in a halt notice

- Do not blame the market ("gold was too volatile"). The strategy accounts for volatility.
- Do not speculate on when it will resume unless you have a concrete gate.
- Do not soften the language. "Halted" is the correct word.
- Do not delete or hide prior calls. The record stays intact.

## How to lift the halt

1. Resolve the underlying reason. If drift: analyze and decide whether to accept.
   If data: fix and verify. If code: fix, test, deploy.
2. Delete `data/far_weekly_paused`.
3. Post a resume notice on the same public channel:
   - Reason halt was triggered (past tense)
   - What was fixed / verified / accepted
   - Confirm next scheduled publish will fire on schedule
