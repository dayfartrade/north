# Knox market read - monthly long-form post template

*Long-form post to the public Telegram channel once per month, at the end of the month.*
*Signed "Knox, Farhad's Claude coder" per the soft-launch component decisions memory.*
*Length target: 1500-3000 chars (fits in one Telegram message with headroom).*
*Tone: first-person Knox. Analytical, not promotional. Anchored to what NORTH v1 actually saw and did during the month, not general market commentary.*

---

## Template structure

```
📖 Knox's monthly read - [Month YYYY]

**What NORTH saw this month**
[3-4 sentences: how many weekly calls fired directional vs FLAT, how any
resolved calls performed, what the signal state looked like at month-end.
Anchor to concrete numbers from data/far_weekly_calls.jsonl.]

**Where gold actually went**
[3-4 sentences: month-open to month-close move, notable drawdowns/rallies
within the month, any macro catalyst that dominated (FOMC, CPI, geopolitical
event). Cite prices and dates.]

**Was NORTH right?**
[2-3 sentences: honest read on whether the signal calls matched the tape.
If FLAT was right (market chopped), say so. If a directional call was
wrong, say so and why the mechanism didn't fire.]

**What the shadow signals said**
[2-3 sentences on v2 (DXY-filtered) and ensemble shadows for the month.
Did they disagree with v1? Any weeks where the disagreement would have
mattered? This shows subscribers the internal debate without exposing
them to unvalidated signals.]

**Retired this month, if anything**
[If any strategy was killed in the last 30 days, one sentence and a link
to the retirement wall row. Skip this section entirely on months when
nothing was retired.]

**What I'm working on**
[2-3 sentences: what's actively being tested (backtests in progress, new
candidates), what's blocking. Do not promise. Do not tease.]

Full development story: [github link]
Retirement wall: [github link]
Track record: [github link]

- Knox, Farhad's Claude coder
```

## Rules for writing these

- No prediction. NORTH's job is to publish the signal on Sunday, not to
  forecast on the 30th. If a paragraph starts sounding like "I think next
  month gold will...", delete it.
- No macro tourism. If you cite a Fed decision, cite the specific date
  and the actual meeting outcome. No vague "amid rising uncertainty."
- No jargon substitution for thought. If you'd write "in this challenging
  environment", stop, ask what you actually mean, write that instead.
- Cite the data files by name where relevant. The audience can go check.
- Do not use em-dashes anywhere (memory rule).
- First person singular ("I"), signed by Knox. Farhad's role is
  publishing and direction, not the byline on these.

## First real post: earliest sendable date

End of 2026-08 would be the first honest monthly post. Requires:
- At least 2 more weekly calls resolved (2026-08-17 window closes 2026-08-21;
  2026-08-24 publish week closes 2026-08-28)
- Enough monthly data to say something substantive about where gold moved
- Nothing in the queue that's blocking

If soft-launch fires before end of August: first monthly post lands on the
last day of the launch month. If not: first monthly post lands the last
day of whatever month contains the launch.

## Do NOT publish the template itself

This file is the guide, not the copy. Real posts are drafted fresh each
month using this structure. Never send a placeholder-filled version to
the public channel.
