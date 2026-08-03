# tier=medium expansion verdict — 2026-07-29 (recheck)

**Pre-reg:** `research/library/tier_medium_expansion_prereg_2026_07_18.md`
**Prior verdict:** `research/library/tier_medium_verdict_2026_07_27.md` (INSUFFICIENT-SAMPLE at n=188)
**Recheck relay:** `research/library/atlas_relay_tier_medium_recheck_2026_07_29.md`
**Trigger:** n_medium_clean crossed 200 within ~2 days of 07-27 first look.

## Verdict: PARK

Do NOT expand routing. `AUTO_TRADER_FUNDING_REVERT_ALLOWED_TIERS`
remains `low`. Per pre-reg: "PASS sample floor, FAIL edge criterion:
PARK. Document. Do NOT re-tune the +0.15R threshold. Reconsider at
next major perf cut (~2026-09-01) if regime changes."

## Numbers vs locked 4-criterion rule

Post-fix window (`created_at ≥ 2026-07-15 14:00:00+00`):

| tier | n | mean R | CI95 | win % |
|---|---|---|---|---|
| high | 10 | −0.500R | [−1.102, +0.102] | 10.0% |
| low | 12 | +0.500R | [−0.012, +1.012] | 75.0% |
| **medium** | **204** | **+0.192R** | **[+0.051, +0.333]** | **57.4%** |

| # | Criterion | Threshold | Observed | Result |
|---|---|---|---|---|
| 1 | n_medium_clean ≥ 200 | ≥200 | **204** | **PASS** |
| 2 | CI95 LCB ≥ +0.15R | ≥+0.15R | **+0.051R** | **FAIL** |
| 3 | Mean R ≥ +0.15R | ≥+0.15R | +0.192R | PASS |
| 4 | No single symbol >40% of positive edge | <40% | FET 16.6% top | PASS |

Sample floor cleared. Point estimate improved slightly (+0.154R → +0.192R)
and CI narrowed as n grew, but LCB is still well below the pre-reg's
+0.15R meaningful-edge threshold.

## Direction check (informational)

Compared to 07-27:
- n: 188 → 204 (+16, ~1 day of adds)
- mean: +0.154R → +0.192R (+0.038R)
- LCB: +0.005R → +0.051R (+0.046R)
- UCB: +0.303R → +0.333R (+0.030R)

Both bounds shifted up modestly. If cadence + edge hold, LCB could
clear +0.15R within a few weeks — but that's a projection, not a
license to expand now.

## Per-symbol concentration

**Positive-sum symbols totalling +54.08R:**

- FET 9.00 (16.6%), PEPE 6.12 (11.3%), SHIB 5.82 (10.8%), DOGE 5.00 (9.2%), SUI 4.50 (8.3%)
- NEAR 4.00, TAO 3.00, APT 3.00, LINK 2.15, ATOM 2.00, WIF 2.00, HBAR 2.00, XRP 1.50, ETH 1.00, TRX 1.00, ICP 1.00, INJ 1.00

No single symbol dominates — criterion 4 passes cleanly.

**Memecoin watch (07-27 set: FET, PEPE, DOGE, SHIB, SUI):**
- 30.43R / 54.08R = **56.3%** (was 59% at 07-27)

Concentration essentially flat. Not a growth pattern. Continue watching
but no regime-conditional flag warranted today.

**Losing symbols (informational):** LTC (-6.0), BCH (-4.0), AVAX (-2.0),
SOL (-2.0), OP (-1.0). LTC and BCH are the notable drags — 6 setups
each at -1.0R and -0.67R mean respectively. Not yet at SUPPRESS-review
thresholds but worth watching if the pattern persists at n≥15.

## Do NOT

- Expand routing on this read. LCB failed the locked threshold.
- Re-tune the +0.15R threshold to make CI clear a lower bar.
- Add a "confidence trend up" heuristic that overrides the pre-reg.
- Split into per-symbol expansion (would need fresh pre-reg).
- Re-run the query weekly hoping the LCB drifts up. Next look is
  2026-09-01 major-perf-cut trigger unless a regime shift is
  independently observed.

## Kill switch (moot)

N/A — no routing change made. Env stays `low`.

## Next revisit

- **Calendar:** ~2026-09-01 major perf cut (per pre-reg)
- **Trigger:** independent regime-shift signal (e.g. tier=medium
  cadence shifts materially, memecoin regime reversal)

Do NOT schedule a weekly poke — that IS re-fishing.
