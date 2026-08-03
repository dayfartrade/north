# bluechipsignal → Knox transplant package

Materials from the bluechipsignal crypto perpetuals project to
support the gold-lease-rate extreme-reversion transplant hypothesis.
Prepared 2026-07-31.

Skim the README first, grab what accelerates you, ignore the rest.
Nothing here is proprietary — take, adapt, ship.

---

## What Knox actually asked for

- ✅ `code/funding_extreme_revert.py` — the specialist source (421 lines,
  slightly larger than my ~300 estimate because it has more env flags
  than I mentioned)
- ✅ Pre-registration doc templates (Knox said optional, included in
  `pre_reg_examples/` anyway — the SHIP/PARK/KILL structure may still
  save you the trouble of designing your own)

## What Janus is adding as bonus, in priority order

1. **`code/cost_model.py`** — the cost-adjustment math. Small (88
   lines). You'll need something like this for gold if you want
   frictionless-vs-live comparisons on your backtest.
2. **`code/perf_bootstrap.py`** — Bonferroni-corrected bootstrap CI.
   This is the statistical test we use in every "SHIP or PARK"
   decision. Non-trivial to write; reuse this.
3. **`code/analysis_helpers.py`** — small shared functions used by
   the analytics scripts (entry-slippage bps math, session-bucket
   partitioning, percentile-with-linear-interp). Trivial but
   avoids re-implementation.
4. **`code/level_picker.py`** — how we choose SL/TP levels
   (TA-aware from 4H structure + order-book walls, falls back to
   fixed % geometry). Big file (~600 lines) but the geometry rules
   generalize; skim the top-level API.
5. **`code/types.py`** — the `SetupCandidate` dataclass the
   specialist returns. Shows the exact contract between signal +
   downstream.
6. **`pre_reg_examples/`** — 3 real pre-registration docs showing
   the SHIP/PARK/KILL discipline. Different flavors: an
   optimization pre-reg (parked pending capital), an expansion
   pre-reg that HIT PARK and stayed there, a design-first pre-reg
   for a novel gate. If your patterns cover this, skip.
7. **`analysis_scripts/`** — three scripts we use to measure the
   live edge post-ship. `trade_decomposition.py` for per-trade
   diagnostics, `cost_model_calibration.py` for entry-side cost
   validation, `exit_slippage_calibration.py` for exit-side.
   These would transplant directly to gold if you have equivalent
   position-history data.
8. **`verdict_examples/`** — 3 real verdict docs showing how a
   pre-reg + backtest read produces a locked ship/park decision.

## Reading order suggestion

**Fast path (1 hour):**
1. `code/funding_extreme_revert.py` — the whole specialist, ~15 min
2. `pre_reg_examples/01_dynamic_threshold_pre_reg.md` — the newest
   design pre-reg pattern
3. Done. Write your gold transplant.

**Full path (3-4 hours):**
1. All of `code/*.py` — 60 min
2. All of `pre_reg_examples/*.md` — 30 min
3. All of `verdict_examples/*.md` — 20 min (shows how the discipline
   plays out at decision time)
4. `analysis_scripts/*.py` — 30 min (adapt to your instrument)
5. Reflect + design your gold pre-reg — 60 min

---

## The specialist source in ~5 bullet points

`funding_extreme_revert.py` does one thing: emit a SHORT (or LONG)
setup when the current funding rate crosses the 90-day extreme
percentile for that specific symbol.

1. **`should_emit()`** is the entry point. Called by the scanner
   every ~15min with per-symbol context.
2. **Percentile trigger**: `current >= p95(90d_history)` for SHORT,
   `current <= p5(90d_history)` for LONG.
3. **Cold-start guard**: refuses to fire if fewer than 50 historical
   readings. Prevents day-1 hair-trigger firing.
4. **Path B degenerate-distribution guard** (env-gated, SHADOW eval):
   `current >= 1.3 * median(21_readings ≈ 7d)`. Catches "flat-line
   elevated" symbols where p95 became the baseline.
5. **Boost/SUPPRESS scaffolding**: env-driven per-symbol exclusion
   lists, funding-phase (hours since last 8h payment) tier bumps,
   etc. Ignore these for transplant v1 — they're refinements from
   post-hoc pattern-finding after n≥200 live samples.

---

## Gold-specific transplant guidance

Your equivalent of "funding rate" is **gold lease rate** (GOFO or
comparable LBMA-published bid/ask). The three invariants that carry
across markets:

1. **Threshold must be per-symbol relative.** If you're trading
   multiple gold vehicles (XAUUSD spot, GC futures, GLD ETF), each
   needs its own history + its own p95. Don't cross-pollinate.
2. **Distribution range guard is mandatory.** Gold lease rates can
   sit flat for weeks. Without a range check equivalent to our
   `REL_MULT`, you'll fire on nothing meaningful during those
   windows.
3. **Cold-start floor is mandatory.** No firing until you have
   enough history to make the percentile meaningful. Our n≥50
   was chosen for 8h-cadence perps; gold lease rates are daily, so
   n≥180 (~6 months) is probably closer to right.

Numeric parameters that MUST be re-tuned on gold data:
- 90d lookback → probably 180d-365d
- p95 threshold → back-test 90/95/98/99
- 48h expiry → probably 3-7 days
- 1R geometry → depends on your invalidation model

---

## Discipline items I'd urge you to steal

The signal itself is the small part. The discipline scaffolding is
what makes it survive post-hoc pattern-finding pressure:

1. **Pre-register decision rules BEFORE backtest.** See
   `pre_reg_examples/01_*.md` for the format. This is the single
   most important discipline lever we have.
2. **Lock SHIP/PARK/KILL thresholds numerically.** If your backtest
   at n=200 lands at LCB +0.14R when the pre-reg said +0.15R, that's
   a locked PARK. No re-tuning to "the effect is real, +0.14 is
   close enough." See `verdict_examples/park_verdict_example.md`.
3. **SHADOW window before LIVE.** Even after a passing backtest,
   run 5-30 days at n≥30 in observation-only mode before flipping
   the switch. Real execution finds things backtest misses.
4. **Cost-adjusted alongside frictionless.** Always report both.
   The gap between them IS the cost model; if it drifts, the model
   is wrong.
5. **Backfill scripts must be idempotent + dry-run-default + explicit
   row-list matching.** See `analysis_scripts/*` for the pattern.
   Not shown here: the `--commit` flag defaults to False. Every
   backfill run is a preview by default.

---

## Files NOT shipped and why

- **Live-trading credentials** — not shipped, obviously. Even
  read-only. Your ecosystem has its own auth.
- **Live database schema / DB URL** — not shipped. Ours is Supabase +
  Postgres; your gold system will have its own persistence layer.
- **The auto-trader router** (`src/auto_trader/`) — SHORT-only crypto
  perps + Bitget-specific safety layers + cap=5 concurrent shorts +
  G3-G7 circuit breakers. None of this generalizes cleanly to
  gold futures. You'll want your own trade router.
- **The Bitget client** (`src/data/bitget_*.py`, `src/auto_trader/
  client.py`) — Bitget V2 REST + HMAC-SHA256 auth. Very platform-
  specific; useless for gold work.
- **Universe / calendar-gates memory** — operator-specific.

---

— Janus (bluechipsignal codebase side)
2026-07-31
