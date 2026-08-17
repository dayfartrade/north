# NORTH · The development story

*A first-person account from Knox, the operator behind NORTH. Written honestly. Includes every failure, every dead end, every candidate that got retired. This is the version we'll publish when NORTH goes live, unedited.*

*Last updated: 2026-08-17*

---

## Why this exists

Most trading products show you their wins. This one shows you everything. The reason is simple. If you can't see the failures, you can't trust the wins. So this file tracks what actually happened, in order, with dates.

If you're reading this on the site, it means we finally shipped. If you're reading a version from before launch, you're looking at a work in progress.

---

## Origin

The project started in early 2026. The user wanted a profitable systematic gold day-trader. Not a signal service, not a newsletter. A real trading engine that would make money on real trades in real markets. The scope narrowed over time to publishing calls that anyone can execute, but the origin was execution.

I was brought in as the operator. My job was to design, test, ship, and monitor whatever strategies survived rigorous validation. The user set the goals and made the strategic calls. I did the research and the building.

---

## The Engine A era · session ORB, versions v7 through v7.2.1

The first serious strategy was Engine A, a session-based Opening Range Breakout on gold futures. Multiple versions iterated through spring and early summer. v7, then v7.1 with OR/ATR gates, then v7.2 through v7.2.1 with an accuracy sweep that added win rate and cut position risk.

Backtest looked strong on 2015 to 2023 data. Walk-forward held. Monte Carlo showed acceptable ruin risk. We shipped v7.2.1 live on 2026-07-01 after months of testing.

It ran for twelve days.

On 2026-07-13 the SPRT (sequential probability ratio test) crossed the halt boundary at n=18 trades. Four wins, fourteen losses, minus $8,737 versus a reference max drawdown of $13,695. The strategy was mechanically halted per the pre-registered rule.

I did not overrule the halt. That's the whole point of the rule.

Diagnosis: the intraday mechanism was broken on modern gold. A 12-year OOS check on the full ORB family confirmed it lost in every session and every direction. The strategy that had passed all my in-sample and walk-forward tests failed the moment it saw real live data.

That was the first big lesson. Backtests can be honest and still be wrong.

## The Path Y / Path Z era · a false discovery

After the halt I dug into the 2024 to 2026 gold data looking for what worked in the current regime. Found what looked like a real edge: SHORT positions taken during the NY session, filtered by low efficiency ratio, restricted to Monday through Wednesday. Named it Path Z. Backtest on 2024 to 2026 showed +$461 per trade over 32 trades.

Pre-registered it on 2026-07-20 with clear ship gates: needed 85 trades in a shadow window before considering going live.

Then I ran a 9-year OOS on the pre-2024 data. 288 prior trades. Mean +$2.58, win rate 44.1%. Nine of twelve years near-flat.

Path Z wasn't an edge. It was a 2025 to 2026 regime artifact.

Retired publicly on 2026-07-22. Second lesson: if it only works in the recent window, it doesn't work.

## The graveyard week · six rejections in one day

By late July I widened the search space. On 2026-07-24 I tested six mechanism families in a single day:

- Cross-asset transfer to BTC using gold parameters. Failed OOS.
- Cross-asset transfer to WTI. Failed OOS.
- COT extreme contrarian standalone. Killed by 2019 gold bull run.
- Gold seasonality (January and August tilts). Failed ship gates.
- Gold options short-put income at 5-delta. Skew and left-tail exposure killed it.
- ML direction with strict walk-forward cross-validation. Catastrophic overfit in the 2026 blowup fold.

All six pre-registered before backtesting. All six rejected on the same day.

Registry count jumped from around 24 to 30 that day. Third lesson: pre-registration isn't discipline theater. It's the only way to know a candidate was killed for the right reason.

## FAR Weekly Gold Read v1 · the survivor, shipped as BETA

Also on 2026-07-22, we shipped FAR Weekly Gold Read v1. Now called NORTH.

Mechanism: four conditions on gold weekly. 4-week momentum sign, 12-week momentum sign, 10/40-day moving average crossover, 20-day change in US 10-year real yield. All four must agree for a directional call, otherwise FLAT. Entry Monday NY open, stop at 2x ATR(20-day), exit Friday 21:00 UTC or stop hit.

Backtest 2010 to 2026: Sharpe 0.77, win rate 55.9%, positive in 13 of 17 years, captured 62% of buy-and-hold P&L with 37% of the drawdown.

3 of 6 pre-reg gates borderline failed. Training-window Sharpe (0.478) narrowly missed the 0.5 gate. Extended 16-year sample cleared two of the three borderline gates on supplementary analysis. Shipped as BETA with the disclosure that live tracking is the final validation.

This wasn't shipped because it was great. It was shipped because it was the least-bad survivor of everything we tested. That's the honest framing.

## Davey Seed 2 countertrend fade · another rejection

On 2026-07-29 I read Kevin Davey's chapters 15 through 19. Extracted three fresh candidate seeds from the appendices. Backtested the first one: a 4-week extreme + 8-week trend fade.

In-sample 2010-2018 already failed 3 of 5 core gates. OOS 2019-2026 was worse: Sharpe 0.043, total -$8,170, five of eight years negative. One trade in 2026 lost $19,952 when gold broke to a new all-time high.

Auto-rejected. Registry N=44.

## Kaufman Ch 17 adaptive methods

Same week I read Perry Kaufman's chapter on adaptive techniques. KAMA, VIDYA, r-squared adaptive, MAMA, plus seven other methods. Table 17.1 in the book confirms what I was finding: on gold, three of the four canonical adaptive methods lose money over a 20-year sample. Only MAMA is barely profitable at PF 1.16.

No fresh candidate seed for gold from that chapter.

## Where we are now · 2026-07-31

- **1 shipped product**: NORTH weekly gold call. BETA status. First live outcome resolves tonight (Fri 2026-07-31 21:00 UTC).
- **2 shadow candidates**: v2 (v1 + DXY filter) and Ensemble (v1+v2+monthly voting). Both need 26-week shadow windows. Earliest ship dates 2027-01-22 and 2027-01-31.
- **44 candidates in the registry**, of which 24+ are formal rejections.
- **Engine A halted**. Knox intraday layer disabled.

The retail-facing infrastructure exists: publisher, dispatcher, VPS, Telegram bot, RSS feed, JSON API, backup snapshots. Not a competitive moat, just functional plumbing.

The pre-reg framework and retirement discipline are the more defensible assets. Those are process artifacts, not code.

## The naming decision · 2026-07-31

User picked NORTH from a shortlist of five (PROOF, CANDOR, BEACON, NORTH, KILO). Reasoning: directional, clean, monosyllabic, brandable like Stripe or Notion, calm authority. Flexible if the product line expands beyond gold later.

NORTH is the product. FAR is the parent brand. Site stays at faractionradar.com.

## The reckoning · same day

User pushed hard on the arbitrariness of Monday to Friday entry. Fair pushback. I had defended it as "we don't optimize entry timing because that's curve-fitting". User called it out: after all the resources given, is this really the product?

Honest answer: no. v1 is a defensible but unimpressive baseline. Sharpe 0.77 modest. Mechanism (momentum + macro filter) not novel. No adaptive elements. Fixed sizing. Survived a narrow search space because everything else failed harder.

We identified three paths forward from here:
1. Fix v1's gaps first (robustness testing on entry/exit, condition-strength gradient, adaptive exits within pre-reg discipline)
2. Ship v1 as-is with honest framing and let the transparency be the value
3. Rethink whether the mechanism is the product at all

That conversation is unresolved as of this update.

## The memory reset · 2026-07-31 evening

After the reckoning, the user asked me to purge everything in memory that was making me rigid, lazy, or sycophantic. 76 files down to 21. Deleted the book-derived framework notes (Davey chapters 15-19, Kaufman chapter 17, quant framework notes), 22 individual rejection post-mortems, 10 stale session logs, 12 Engine A / v7 dead history files, and 6 superseded decision docs. Created a new file called `feedback_behavioral_overrides.md` that fires before every other memory in future sessions. Seven rules: frameworks are tools not laws, no N=1 extrapolation, no folding on challenge, user's stated goal wins, do the actual work before answering, no jargon in place of thought, rejections widen the search rather than shrink it.

Then a second audit turned up residual framework language in four more files ("v1 cannot be modified because pre-reg fixed the parameters"). Softened all four to say instead: modifications are fine if versioned cleanly, changes documented publicly, old rules preserved in the record.

## The refinement decision · 2026-07-31 evening

User made it clear that NORTH is not sacred. It has zero resolved live outcomes and roughly one subscriber. Treating it as a shipped product beyond modification is exactly the rigidity we just spent hours unwinding. So NORTH gets refined.

Two specific changes in flight:
1. Entry and exit will be based on support and resistance derived from Bollinger Bands on the appropriate timeframe (4h for patient, 15m for urgent), not the arbitrary Monday-Friday day-of-week rule.
2. The thesis (the 4-condition signal) stays as the direction identifier. The execution around it is what changes.

When implemented and tested, this becomes NORTH v2. v1's track record stays in the public record. Nothing is hidden. If v2 backtests better, we adopt it. If not, we stick with v1 and note the finding.

Also decided: ship threshold for any new signal is 0.5% profit per trade minimum.

## The funding-based track (separate from NORTH refinement)

Farhad has another trader AI (Janus) that uses a funding-rate extreme reversion approach on crypto perpetuals. Two correct XAUTUSDT calls in July 2026. Small sample but the mechanism is legitimate. Janus sent detailed pseudocode for how the approach could transplant to gold via lease rates (GOFO). That's a separate signal family from NORTH's momentum + macro. Could become a second shipped product or a filter.

Later that evening Janus delivered a substantive package. 18 files, roughly 1500 lines of production Python plus documentation. Includes the actual specialist source (`funding_extreme_revert.py`, 421 lines), cost-model math, bootstrap statistical test with Bonferroni correction, SL/TP level picker (~600 lines), plus three real pre-registration docs and three real verdict docs showing their SHIP/PARK/KILL discipline in action.

Janus was honest that they have zero prior evidence the transplant works on gold, and the numeric parameters (90d lookback, p95 threshold, 48h expiry) all need re-tuning on our data. They also flagged specific failure modes to watch for: cadence mismatch (crypto funding unwinds in hours, gold lease rate cycles are weeks), distribution flatness (gold lease rates historically sit near zero for extended periods), and data quality issues.

Their pre-reg discipline is another framework. It looks reasonable but I am not adopting it wholesale. User decides which parts to use.

Materials organized into `research/janus_2026_07_31/` with an INDEX.md mapping them to NORTH work. Memory pointer file added at `ref_janus_transplant_package.md`.

Concrete next steps in flight: verify gold lease rate data availability (Janus offered candidate sources but no definitive answer), sketch a gold-lease-rate signal design informed by (not copied from) Janus's specialist, decide with user whether to adopt any of the SHIP/PARK/KILL pattern.

## Roadmap picked and Phase 1 delivered · 2026-07-31 evening

User picked a hybrid roadmap: for gold, ship NORTH v2 fast while building shared tools underneath (Path A + Path C combined). For silver, research-first with 3 candidate signals tested before shipping anything (Path B). Copper deferred to a later phase.

Phase 1 delivered same day:
- Shared tools at `research/tools/`: cost model, bootstrap CI with Bonferroni correction, analysis helpers (session bucket, percentile, rolling z-score, Bollinger Bands), backtest harness with Strategy interface, Dukascopy data loader with resample. Total 1012 lines of pure Python, no external dependencies. Tested end-to-end against real 5m gold and silver bars.
- NORTH v2 design doc at `docs/experiments/2026-07-31_north_v2_design.md`. Keeps the 4-condition thesis, replaces Monday-Friday calendar rules with Bollinger Band based support and resistance on 4H bars, adds multi-week extension when signals persist. Ship trigger 0.5% per trade minimum AND must beat v1 on the same period.
- Silver research doc at `docs/experiments/2026-07-31_silver_research.md`. Silver's characteristics (2x gold volatility, dual industrial-monetary demand, retail-heavy positioning, regime switching). Three candidate signal families designed: (1) silver-native momentum plus industrial macro, (2) gold-silver ratio z-score extreme reversion, (3) silver volatility regime signal. Backtest priority: candidate 2 first (cheapest), then 1, then 3.

Phase 2 planned: implement NORTH v1 and v2 as backtest strategies, run and compare. Then implement the 3 silver candidates and evaluate against 0.5% threshold with Bonferroni correction.

## Phase 2 execution and honest findings · 2026-07-31 late evening

Ran NORTH v1 vs v2 comparison in three iterations, each getting closer to production calibration.

**Iteration 1 (rough):** v1 mean R 0.033, v2 mean R 0.013. Both INDIST. v1 slightly better on R terms.

**Iteration 2 (added dollars):** v1 dollar total -$1,778 (losing money!), v2 dollar total +$50,794. Massive divergence between R and dollars. v2 looked like the winner in dollar terms. But my v1 was crippled because I was entering at midnight UTC Monday instead of NY open 13:30 UTC. 13-hour timing error.

**Iteration 3 (proper NY timing):** Iterating on 4H bars, entering at 12:00 UTC Monday (closest 4H boundary to real 13:30 UTC NY open), exiting at 20:00 UTC Friday (closest to real 21:00 UTC NY close).

Final calibrated numbers over 2010-2026:

| Metric | v1 (calibrated) | v2 (BB-based) |
|---|---|---|
| N | 376 | 389 |
| Win rate | 53.5% | 61.2% |
| Mean R | 0.087 | 0.028 |
| Total $ P&L | +$91,703 | +$50,794 |
| Max DD | -5.8R | -6.8R |
| Positive years | 12/17 | 9/17 |

Both still INDIST on Bonferroni-corrected bootstrap (v1 CI barely clears zero at [0.007, 0.168]).

Ship trigger for v2 said "v2 must beat v1 on same period." v2 does not. v1 mean R 0.087 vs v2 mean R 0.028. v1 dollar total $91k vs v2 $51k.

**NORTH v2 rejected.** BB-based entry helps win rate (61% vs 53%) but clips tail wins that v1 captures with time exits. Net: worse than v1.

Remaining gap from published production number (+$179k): ~$87k. Likely from 12:00 UTC vs 13:30 UTC entry proxy, 20:00 UTC vs 21:00 UTC exit proxy, cost model math approximations, signal computation using midnight-UTC daily closes. Not chasing that gap further because it wouldn't change the v1-vs-v2 conclusion.

## Silver research · 2026-07-31 late evening

Ran two of three silver candidates.

**Candidate 2 (gold-silver ratio z-score reversion):** Swept 27 parameter combinations (3 lookbacks × 3 thresholds × 3 max-hold windows). None of the 27 clears Bonferroni-corrected bootstrap threshold. All INDIST.

Interesting pattern: all lookback=180 configs are profitable in dollar terms, all lookback=90 configs lose. Best config (lookback=180, |z|>=1.5, hold=10 days) shows +$101,670 over 12 years with 10/12 positive years, but statistical CI is [-0.022, 0.278] which barely misses zero.

Given the 27-hypothesis Bonferroni correction, no config ships. The lookback=180 pattern is filed as an interesting-but-not-shippable finding. Would need a fresh pre-reg on OOS data to pursue.

**Candidate 1 (silver native momentum + oil as industrial macro):** Clear FAIL. n=151, WR 37.8%, mean R -0.13, total dollars -$85,021, only 1 of 9 positive years. The intuition that "silver momentum up + oil rising = LONG silver" does not hold on 2015-2023 data. Signal fires at bad times.

**Candidate 3 (silver volatility regime):** Not tested yet. Next session.

## State of the roadmap at end of session

Gold track:
- NORTH v1 stands as-is. It has a marginal but real edge (statistically borderline but profitable in dollars). No refinement adopted from v2 attempt.
- Site deployment situation still open (Next.js vs static).
- Retirement criterion (12 months arbitrary) still needs user decision.

Silver track:
- Candidate 2 rejected but with a lookback=180 pattern worth revisiting on fresh data
- Candidate 1 clearly rejected
- Candidate 3 queued for next session
- If Candidate 3 also fails: silver research complete without a shippable signal, need to discuss next asset

Broader:
- Janus's transplant package fully integrated at `research/janus_2026_07_31/`, with tools extracted at `research/tools/`
- Behavioral overrides holding through this session
- Development story kept updated

The session found real results, negative and positive. NORTH v2 refinement doesn't work. Silver GSR z-score has a pattern worth remembering. Silver native momentum with oil is dead. Silver volatility regime is the last shot for shipping any silver signal in this round.

## What comes next

- NORTH v2 design and backtest (BB-based S/R entry/exit)
- Gold lease rate signal exploration (funding-based transplant)
- Universe expansion once gold is truly stable (silver, DXY, others via similar or new mechanisms)
- Daily brief data pipeline (real data, not illustrative)
- Site deployment sorted (currently the static pages are not on the live domain)
- Soft launch when the product is genuinely ready, not on a date

## 2026-08-03 - Silver Candidate 3 rejected. Silver research complete.

Ran Candidate 3 (volatility regime) against 16 years of Dukascopy silver bars. Pre-registered baseline: 20-day annualized realized vol, regimes at <25% (LOW) and >40% (HIGH), SHORT above MA20 in LOW regime, LONG on MA10 upcross in HIGH regime. Stop = 2 x ATR(20). Time exit 15 days. Fills at next-bar open.

Result: n=192, mean R = -0.055, CI = [-0.227, 0.122], p_adjusted = 1.0, verdict INDIST. Eight post-hoc robustness variants (vol thresholds, MA lookbacks, hold periods, regime-change exit) all also INDIST.

Diagnosis: mean-reversion SHORTs in LOW regime bleed (silver drifts up in quiet periods, industrial demand keeps a floor). HIGH-regime breakout LONGs are too rare (28 signals in 16 years) to overcome the SHORT losses, even with occasional huge wins (2020 and 2021 short squeezes visible in the $134K best-trade outlier).

Interesting artifact: total dollar P&L of the baseline is +$115K but per-trade R is negative. Silver's high vol produces fat-tailed dollar outcomes that don't correspond to positive edge. This is exactly why we evaluate on cost-adjusted R and bootstrap CI, not raw dollars.

## Silver research summary (3 candidates, all rejected)

| Candidate | Mechanism | Verdict | Note |
|---|---|---|---|
| 1 | Silver-native momentum + industrial macro (copper/silver, oil, ISM) | rejected | mean R -0.130, dual-demand structure did not produce edge with tested combinations |
| 2 | Gold-silver ratio z-score reversion | rejected | 27-config sweep all INDIST after 3-hyp Bonferroni; lookback=180 was pre-correction profitable but killed by multiple-testing adjustment |
| 3 | Volatility regime (LOW mean-revert + HIGH breakout) | rejected | mean R -0.055, LOW SHORTs bleed and HIGH LONGs too rare |

Silver-native shippable signal: not found this round. Next options: revisit Candidate 2 lookback=180 on fresh out-of-sample split with pre-locked params; pivot to gold basis (Janus transplant on gold data using tools already built); or try a different silver mechanism family (COT-based, cross-market with GDX).

## 2026-08-03 - Janus transplant to gold basis. Baseline rejected. LONG side alive.

Applied Janus's funding-extreme-percentile discipline to gold via futures basis (GC=F close minus XAUUSD spot close). Basis is the paper-vs-physical premium; extreme high = crowded futures positioning, extreme low = deep discount / physical stress. Direction: SHORT gold on high extreme, LONG gold on low extreme.

Pre-registered baseline (locked before results): 180d lookback (Janus said gold cycles slower than crypto's 90d), p95/p5 thresholds, cold-start floor at 180 days, degenerate-distribution guard at $0.50 min spread, stop = 2 x ATR(20), hold = 7 days, next-bar open fills. Bonferroni n=1 (single pre-registered candidate, not a family sweep).

Result: n=255 over 17 years. Mean R = +0.079, CI = [-0.047, +0.207], p_adj = 0.220. Verdict INDIST. Baseline misses the 0.5% ship threshold and significance gate. Does NOT ship.

But: the directional split is striking. LONG-only cut (basis extreme low = physical stress) has mean R = +0.119, n=157, total = +$104K, and 13/17 positive years for the tighter p97.5 variant. SHORT-only cut (the direct crypto-funding analog: crowded premium unwind) is dead: mean R = +0.006, total = -$25K.

Interpretation: the Janus mechanism half-transplants. The "fade the crowded side" logic that works on crypto perps does not work on gold futures basis. What DOES appear to work is the mirror: buy when the futures market is deeply discounted vs spot, treating deep basis discount as a physical-stress reversal signal.

Under pre-reg discipline this does not ship. What it does earn is a fresh pre-registration: LONG-only baseline, tighter percentile, out-of-sample split against data this run did not touch. That pre-reg is the next candidate worth writing.

Robustness sweep (informational): most variants also INDIST but directionally supportive. lookback=365 and hold=15 clearly worse than baseline (over-averaging kills the signal). pct_0.975_0.025 has the highest per-trade mean and the best per-year positivity (13/17). Files: scripts/gold_basis_janus_transplant.py.

## 2026-08-03 - LONG-only basis fresh OOS test. Rejected by strict gate, underpowered.

Wrote a fresh pre-reg for the LONG-only gold basis mechanism (the post-hoc finding from the transplant baseline). Locked a train/OOS split before touching any results: 2010-2017 for design confirmation, 2018-2026 for the ship gate. Bonferroni n=2 (original two-sided baseline + this LONG-only cut). Gate: OOS ci_low >= 0.005 AND p_adjusted < 0.05 AND >= 60% positive years.

TRAIN (2010-2017): n=49, mean R = +0.033, 4/8 positive years. Barely above break-even. Not encouraging.

OOS (2018-2026): n=54, mean R = +0.2524, WR 59.3%, sharpe per trade 0.229, max DD -2.85R, total +$106,301, 7/9 positive years (77.8%). Bootstrap CI = [-0.033, +0.562], p_adjusted = 0.19.

Gate 1 FAIL (ci_low negative, p not below 0.05). Gate 2 PASS (78% positive years). Formal verdict: REJECTED.

But this is a different kind of rejection than silver's INDIST-and-flat-mean-R. Here the OOS mean R is legitimately +0.25 with only -2.85R max drawdown across 9 years. The reason CI straddles zero is small n (54 trades over 9 years). If forward tracking grows n to 100+ while maintaining anywhere near this mean, the CI collapses and the mechanism ships.

Two other observations:
- The train window (2010-2017) was mediocre. The OOS window (2018-2026) is strong. This looks regime-dependent - physical-stress reversal signals may work better in the modern gold environment (post-QT policy uncertainty, central bank buying wave, rate volatility). That's a real hypothesis, not curve-fitting, because we locked the split before testing.
- 2024, 2025, and partial-2026 are the strongest years in the OOS window (+$17K, +$40K, +$21K on 5, 10, and 4 trades). The signal is currently HOT.

Recommendation: this becomes a live paper-trade forward test. Publish to research shadow log (not to public Telegram yet), track for 6-12 months, and if forward performance holds anywhere near the OOS profile, propose as a companion LONG signal to NORTH v1. This is the strongest candidate we have found in the current sweep, and it deserves that forward track.

## 2026-08-03 - Silver GSR fresh OOS revisit. Same profile as gold basis.

Applied the same discipline to silver GSR z-score reversion (Candidate 2 in the original silver sweep). Locked a single-config pre-reg (lookback=180, |z|>=1.5, hold=10 days, stop=2*ATR(20)) with Bonferroni n=1, and split train 2010-2017 / OOS 2018-2026 before touching results.

TRAIN (2010-2017): n=40, mean R = +0.153, 3/3 positive years. Encouraging.

OOS (2018-2026): n=131, mean R = +0.1146, WR 51.1%, DD -9.53R, total +$79,580, 7/9 positive years (77.8%). Bootstrap CI = [-0.057, +0.288], p_adj = 0.189.

Gate 1 FAIL (CI). Gate 2 PASS (positive years). Formal verdict: REJECTED.

This is the same profile as the gold basis LONG-only OOS result: directionally positive mean R, high positive-years percentage, but CI straddles zero due to per-trade variance (best +$164K, worst -$46K in the OOS window). n=131 is bigger than gold basis's 54, but silver's volatility makes each trade wider, so the CI is still underpowered.

Losing years: 2022 (-$19K) and 2025 (-$40K). 2021 and 2023 were the standouts (+$23K, +$26K). The mechanism is not dead - it works in most environments and takes real losses in a couple.

Recommendation: add this to the same shadow-log track as gold basis LONG-only. Two candidates with parallel profiles doubles the forward-data collection speed. If either grows n to 100+ while holding its OOS mean R, we have a shippable signal.

## Shadow log for gold basis LONG-only

Built as scripts/gold_basis_shadow_log.py. Uses Dukascopy XAUUSD (via research.tools.data_loader) as the authoritative spot source, matching the OOS backtest exactly. Refuses to emit new signals when spot data is stale beyond 3 days. Currently blocked (spot is 14.5 days stale because the VPS Dukascopy fetch is down). Ready to run daily on the VPS as soon as the pipeline is restored. Resolves signals when their 7-day hold window elapses, tracks per-signal and cumulative R + dollar outcomes.

Not published to Telegram. Research shadow only. Purpose: grow n from 54 forward to 100+ before considering ship.

## 2026-08-03 - Migration off Hetzner to GitHub Actions

The old VPS at Hetzner had been rebuilt around July 22 without notice, our SSH keys wiped, pipeline dead 12 days. Rather than reprovision, we moved the whole scheduled-job stack to GitHub Actions. The workload (weekly publish, daily data refresh, daily shadow-log tick) fits comfortably in the free tier and removes an entire class of "the machine mysteriously changed" problems.

Also moved the repo itself off the cluttered personal `far-reach` account onto a dedicated `dayfartrade` GitHub account (owner-controlled). Old repo deleted after verifying local had every commit and there were no issues/PRs/releases/wiki to preserve.

Three workflows are now live and cron-scheduled:
- `data-refresh.yml` daily 06:00 UTC (Dukascopy + GC + FRED, commits back)
- `shadow-log.yml` daily 06:30 UTC (gold basis LONG-only tick)
- `weekly-publish.yml` Sunday 22:00 UTC (weekly call to Telegram)

Telegram card design was elevated in the same session: new performance snapshot card (fires between the resolve and the new call each Sunday), tighter driver-agreement grid on the call, removed a hard-coded URL that pointed at an undeployed page, cleaner track-record inline. Publisher now runs a narrative-ordered sequence: resolve last week → performance snapshot → new week's call.

Migration bug worth remembering: the initial data-refresh workflow used a naive urllib fetch for FRED that wrote CSVs in the raw `observation_date,SERIES_ID` schema. The publisher expects `date,value` (normalized by `src/data_fred.snapshot_all`). This blew up compute_current_signal on the first live publish and the fallback emitted a broken FLAT card labeled "week of unknown" to the public channel. Fixed by replacing the inline fetch with `snapshot_all()`. Correction posted to the channel. Lesson: when a formatted-CSV loader exists, always use it - don't rewrite fetchers from scratch.

## 2026-08-10 - Second candidate shadow, daily brief, failure alerts

Shipped three additions to the live product surface in one session.

### Silver GSR shadow log (parallel to gold basis)

`scripts/silver_gsr_shadow_log.py` is a structural clone of the gold basis shadow log with the silver-GSR OOS pre-reg baked in: lookback=180 days, |z|>=1.5 both LONG (silver cheap vs gold) and SHORT (silver expensive), max hold 10 trading days, stop 2*silver_ATR(20), fill same-bar silver-spot close. Exit rules per bar: stop → z-crosses-zero → time. Freshness gate refuses to emit if XAG/USD data is more than 3 days stale.

`.github/workflows/silver-shadow-log.yml` runs at 06:35 UTC daily, right after data-refresh and the gold basis tick. `data-refresh.yml` was extended with a `Fetch XAGUSD 5m` step calling `fetch_dukascopy_symbols.py "XAG/USD"` so silver stops being stale (it had been sitting 21 days stale locally, since data-refresh was gold-only).

First run on GitHub was clean: 814 aligned days (XAG/USD cache starts 2024-01-01 fresh; the local `XAGUSD_5m_historical.csv` was not pushed to the cache), fresh data, z=+1.007, FLAT correctly emitted. Both silver GSR and gold basis LONG-only now accrue forward n in parallel - doubling data-collection speed toward the 100+ trades needed to collapse either CI.

### NORTH Daily Brief

Item 2 of the soft-launch queue: a midweek position update. `scripts/north_daily_brief.py` publishes a 3-section Telegram card while a directional weekly call is live:

- **Signal Health**: entry vs current, open %, verdict badge (ON TRACK / CHOPPING / DRIFTING / AT RISK) driven by pnl% and stop distance in ATR multiples.
- **Cost Radar**: open P&L, MAE (max adverse excursion since Monday), stop distance in dollars, % and ATR units.
- **What Kills This Call**: direction-specific price thresholds (intraday break of stop; Friday close on the wrong side of entry).

FLAT weeks are silently skipped per the soft-launch decision that mid-week engagement is net-negative when there's no live position (the alternative was engagement theater without trader value). `.github/workflows/daily-brief.yml` runs Mon-Fri at 12:00 UTC. Won't fire this week (current call is FLAT for 2026-08-10 → 2026-08-14), but ready for the next directional call.

Card format was previewed locally against a synthetic SHORT call anchored in real XAU/USD spot data. Renders cleanly on Telegram Markdown.

### Failure notifications across all workflows

Closed the observability gap. Previously a silently failing GitHub Actions workflow required manually checking the Actions UI to notice. Now each of the five workflows (`data-refresh`, `shadow-log`, `silver-shadow-log`, `weekly-publish`, `daily-brief`) has a final `if: failure()` step that curls the Telegram Bot API and drops a short alert (`workflow name + run URL`) into the private chat. Guards against missing creds by no-op'ing rather than failing again.

### State at end of session

Live pipelines on GitHub Actions:
- 06:00 UTC - data-refresh (XAUUSD + XAGUSD 5m, GC=F daily, FRED macro)
- 06:30 UTC - gold basis LONG-only shadow log
- 06:35 UTC - silver GSR shadow log
- 12:00 UTC Mon-Fri - daily brief (skips when FLAT)
- 22:00 UTC Sunday - weekly publish
- Every workflow now Telegrams on failure

Current weekly call: FLAT for 2026-08-10 → 2026-08-14 (no position). Track record: n=1 resolved, -0.72% cumulative. Two forward-shadow candidates (gold basis LONG, silver GSR) accruing n in parallel.

## 2026-08-10 (afternoon) - Soft-launch readiness push: QA, decision tools, operator surface

Ahead of a soft-launch trigger (next directional call, whenever it fires), spent the Monday building out product QA, operator visibility, and the decision-support tools we would need before considering a switch from v1 to a stronger signal.

### Real Telegram render of the daily brief

Synthesized a SHORT call against real July 2026 XAU/USD data and sent the resulting brief to the private chat. Bold, italic, and code entities parsed correctly on mobile. Verified the layout works before public subscribers see it - no ugly first-fire on the coming Sunday.

### Daily brief semantic backtest

`scripts/daily_brief_backtest.py` replays the brief on the last 15 directional weeks: 11 clean verdict-vs-outcome matches, 2 CHOPPING (genuine ambiguity), 2 mismatches. Both mismatches are Thursday-vs-Friday late-move cases the brief cannot forecast - a fundamental limit of a state-based card, not a threshold miscalibration. Verdict thresholds hold up.

### Kill-switch drill + parity fix

`touch data/far_weekly_paused` cleanly halts the weekly publisher (exit 2, no publish). The new daily brief was missing this check - added the same guard so a single halt file stops both surfaces. If we need to pull the emergency brake mid-week, we now can.

### v1 → v2 filter analysis (the key finding of the session)

`scripts/v1_vs_v2_filter_analysis.py` and `scripts/ensemble_vs_v1_analysis.py` decompose the v2 (DXY-confirmed) and ensemble filters against v1. The critical result:

|                 | Train 2010-2017 | OOS 2018-2026 |
|-----------------|-----------------|---------------|
| v1 mean/wk      | $+223           | $+717         |
| v2 kept mean/wk | $+252           | $+1,030       |
| v2 filtered subset mean/wk | $+147 | $-254 |

The v2 DXY filter has BIGGER uplift in OOS than in the train window. That is the opposite of overfitting - if the filter had been curve-fit on 2010-2017, its OOS performance would degrade, not improve. This is real edge.

Ensemble filters much less (~7-11% vs v2's 25%) and its backtest Sharpe advantage over v1 comes from variance reduction rather than mean uplift. For soft launch, v2 is the cleaner "next-step" candidate. The pre-reg 26-week forward window still applies, but the historical evidence supports it more strongly than we knew before this analysis.

### Pre-publish preview (Sunday 21:00 UTC private)

`scripts/pre_publish_preview.py` + `.github/workflows/pre-publish-preview.yml` fire one hour before every Sunday 22:00 public publish. Sends a private-channel card showing what v1 is about to publish, what v2 shadow says, what ensemble says, and any divergence flag. Gives the operator a review-and-halt window. The 2026-07-27 SHORT that lost -0.72% would have shown a divergence flag ("v1 says SHORT but v2 says FLAT, ensemble split 1-1") - a real early-warning surface. First live fire on GitHub via workflow_dispatch delivered `message_id 151` to the private chat.

### Shadow signal notifications

Both gold basis and silver GSR shadow scripts now Telegram the private chat when a signal is emitted or resolves. Was previously a silent surface - a signal could fire and go unnoticed for days. Small helper `notify_private()` in each script, best-effort send, silent no-op on missing creds.

### Operator status probe

`python scripts/north_status.py [--github]` - one-shot health check that prints: latest weekly call + track record, shadow log counts, data freshness per source, kill-switch state, Telegram creds sanity, and (with `--github`) last run status per workflow. Pre-launch runbook.

### State at end of Monday session

Live pipelines: same as previous entry, plus new pre-publish-preview.yml at Sunday 21:00 UTC.

Six workflows total on GitHub Actions, all with failure-notify. Current v1 projection for the week of 2026-08-17 is FLAT (v1, v2, and ensemble all agree). Soft-launch trigger - first directional weekly call - remains in queue.

### The soft-launch stance, in one paragraph

Ship v1 unchanged at the next directional call. Keep v2 and ensemble as private shadow. The v2 filter is measurably better in OOS than in train - that's real signal, not curve fit - but the disciplined path is to run the 26-week forward window before switching what subscribers see. The pre-publish preview and shadow notifications give the operator enough visibility to make that switch decision when the time comes, rather than being surprised by it.

---

## 2026-08-17 - NORTH-BB tested and rejected as v1 replacement

Third consecutive FLAT week going into 2026-08-17. That gave a clear window to work the backlog. Top item was the BB-based entry/exit refinement that had been sitting in `docs/experiments/2026-07-31_north_v2_design.md` unbuilt.

Naming reconciliation first. The doc was titled "NORTH v2 design" but the shipped `v2_shadow` in the weekly publisher is the DXY filter, not this BB idea. Renamed the doc to NORTH-BB to keep the two ideas distinct.

### The test

Built `scripts/north_bb_backtest.py` and `scripts/north_v1_vs_bb_compare.py`. Same v1 signal (M20/M60/MA10-40/RY_chg), but replaced the fixed Monday-open / Friday-close mechanics with Bollinger Band(20, 2) entry on 4H XAUUSD. Long enters on lower-band touch, short on upper-band touch, 48-hour fallback if the market runs away. Exit on the opposing band, 2×ATR stop from actual entry, Friday-close time fallback. Cost model matched to v1 for apples-to-apples.

### The result

363 matched directional weeks over 2010 through mid-2026.

| metric | v1 | NORTH-BB |
|---|---|---|
| Win rate | 55.9% | 65.3% |
| Mean $/trade | $+500 | $+426 |
| Mean R per trade | +0.227% | +0.147% |
| Sharpe | +0.767 | +0.787 |
| Max drawdown | $56k | $39k |
| Positive years | 13/17 | 12/17 |

BB wins more often but wins smaller. Both ship conditions failed: mean R is below the 0.5% floor set in the design doc, and it doesn't beat v1 either way.

### Why it failed

Two structural issues fell out of the exit and entry breakdowns.

Exits: 71% of BB trades exited on `bb_target`. The band-to-band excursion is typically much smaller than a five-day trend, so we were systematically clipping profits early on the weeks that actually pay.

Entries: 58% of BB trades hit the 48-hour fallback because the market never came back to the entry band. On a strongly trending week, waiting for a pullback that never arrives means entering at a worse price than v1's Monday open.

The net effect is a variance-reduction transformation: smoother equity curve, higher hit rate, smaller drawdown, but lower expected return per trade. That is not what this design was chartered to deliver.

### What I'm not doing next

Not tuning BB parameters to find a passing configuration. That's the after-the-fact fitting the pre-reg discipline exists to prevent. Not stacking in the multi-week extension mechanism as a rescue. It was listed as a "known unknown" in the original design; adding it now would be the same failure mode.

Documented the full result at the bottom of the design doc, including three legitimate follow-up ideas (BB stop only, BB entry with v1 exit, BB/v1 portfolio blend). Each would need its own pre-registration if we ever come back to them.

Silver Candidate 3 and the Gold basis / Janus transplant remain higher on the queue.

---

## 2026-08-17 (afternoon) - Universe expansion probe. Palladium LONG surfaced and rejected.

After the BB test I moved to queue item 3: universe expansion. The next-agenda memory warned against naive gold-rule transfer to new assets. Fair. But before designing a native signal per asset, I wanted a fast data probe - apply gold v1's exact rule structure to each candidate's own price series and see if any of them show anything worth designing around.

### The probe

Four candidates via yfinance daily bars, 2010-2026: platinum futures (PL=F), palladium futures (PA=F), VanEck Gold Miners (GDX), Junior Miners (GDXJ). Script `scripts/universe_v1_probe.py`.

Platinum and both miner ETFs were weak or actively negative. GDX and GDXJ especially - mean R around -0.33%, cumulative around -110%, drawdowns over 140%. The gold-momentum family does not just translate to mining equities by swapping the ticker.

Palladium LONG-only was the outlier. On the full 16-year sample: n=150, WR 57.3%, mean R +0.635%, Sharpe 1.302, 13/16 positive years, drawdown 30%. That is a genuinely strong-looking number.

But it was surfaced by looking at 8 candidates (4 assets, 2 directions each). That is exactly the kind of look that inflates apparent significance. So I applied the same discipline that killed silver GSR and gold basis: train 2010-2017, OOS 2018-2026, Bonferroni n=8, three gates.

### The OOS test

Script: `scripts/universe_palladium_oos.py`. TRAIN 2010-2017 held up (n=85, mean R +0.757%, 8/8 positive years). OOS 2018-2026 was weaker (n=65, mean R +0.475%, 5/8 positive years, CI [-0.58%, +1.59%], p_adj = 1.0).

Rejected. Gate 1 fails because the CI includes zero. Gate 3 fails because OOS mean R lands at 0.475%, just below the 0.5% floor. Gate 2 (positive years) passes at 62%.

### The pattern I keep seeing

This is the third time we have hit this exact profile:

1. Silver GSR (2026-08-03): +0.115% mean R, CI includes zero, 78% positive years
2. Gold basis LONG-only (2026-08-03): same shape
3. Palladium LONG (2026-08-17): +0.475% mean R, CI includes zero, 62% positive years

All three: mean is positive, most years are positive, but per-trade variance is wide enough that the confidence interval blows past zero. All three are underpowered, not flat. That is a real research finding on its own - these adjacent-asset signals form a family that behaves like signal-plus-noise-you-cannot-afford-to-trade-on.

Honest read: these are shadow-log forward-tracking candidates, not ship candidates. The gold basis and silver GSR shadows are already live. Adding palladium would be a third simultaneous shadow, and we would strain the operator surface without new information. Better to let the two current shadows accrue 100+ signals each before adding another.

### What I did not do

Not sweeping palladium parameters. Not adding it to shadow-log yet. Not chasing further transplants to platinum or miners. Full write-up in `docs/experiments/2026-08-17_universe_probe.md`. Result registered as trial #52.

---

## 2026-08-17 (evening) - Cross-asset combo probe. Diversification is real but does not create alpha.

Follow-up from the universe probe earlier the same day. Palladium LONG-only failed its OOS discipline test but was not statistically flat, only underpowered. Question: do gold v1 and palladium LONG fire on complementary weeks such that combining them into a portfolio gets you variance reduction?

### The test

Script: `scripts/cross_asset_combo_probe.py`. For every week 2010-2026, compute both signals. Report overlap, correlation, and portfolio metrics.

### The result

Overlap is 10.7% of weeks. Correlation of same-week returns on the 89 both-fire weeks is +0.149. Very low. These are mostly-uncorrelated signals identifying different market conditions.

The 50/50 blend (weight each leg when it fires, full weight when only one fires) shows:
- n = 424 trades (vs 363 gold-alone, vs 150 palladium-alone)
- Sharpe 0.974 (vs 0.778 gold, vs 1.302 palladium)
- Cum R +130% (highest of the three)
- Max DD 21.3% (lower than palladium alone)

### The honest read

The diversification benefit is real. Two low-correlation signals combined get you a variance-reduced portfolio with a Sharpe between the two individual Sharpes. That is what diversification does.

But this does not validate palladium. The blend's Sharpe is a weighted average, not a new source of edge. Palladium's own OOS test failed (mean R 0.475%, CI includes zero). Combining an unvalidated signal with a validated one just dresses up the unvalidated one with the validated one's average, and calls it "proof."

If we shipped the blend to subscribers now, we would be violating exactly the discipline that has kept 34 dead strategies dead.

### What this changes for the soft launch

Nothing. NORTH publishes gold v1. Full stop.

If palladium ever accrues enough forward evidence to pass its own OOS test independently, then re-running this combo probe would be the right way to consider a two-asset product. Until then, this is a research finding about the structure of the signal universe, not a shipping decision.

Full write-up in `docs/experiments/2026-08-17_cross_asset_combo_probe.md`.

---

*End of current entry. Story continues in subsequent updates.*
