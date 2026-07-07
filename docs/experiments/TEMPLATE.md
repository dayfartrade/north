# Experiment: <name>

**Registered UTC:** <timestamp when this file was frozen — before looking at any results>
**Blinded until:** <when results will be looked at>
**Layer:** strategy_engine | session_config | calendar_audit
**Owner:** Knox

## Hypothesis

<one crisp sentence — the claim we're testing>

## Rationale

<why we think it works, referencing prior data or a specific source>

## Data

- **Window:** <start> to <end>
- **Expected sample size:** n≈<N>
- **Split:** <in-sample/out-of-sample partition>

## Method

<procedure to run, referencing which script>

## Decision rule — LOCKED

**Ship** if ALL of:

1. <gate 1: quantitative>
2. <gate 2>
3. p-value < 0.05 / N_hypotheses_this_month  (Bonferroni-corrected)
4. Out-of-sample verdict: <specific>

**Shadow-continue** if:

- p-value between 0.05/N and 0.05 (some evidence but not enough to ship)
- Sample size below threshold

**Reject** if any of:

1. <kill criterion 1>
2. <kill criterion 2>
3. In-sample and OOS diverge by more than <threshold>

## Bonferroni denominator

Registered hypotheses this calendar month: <list them here>

- Current N: <count>
- Adjusted α: <0.05 / N>

## Results (fill AFTER running — do not edit above)

- **Ran on:** <date>
- **Sample size:** n=<actual>
- **In-sample statistics:** <summary>
- **Out-of-sample statistics:** <summary>
- **p-value:** <raw>
- **Bonferroni threshold:** <0.05/N>
- **Verdict:** SHIP | REJECT | SHADOW-CONTINUE
- **Notes:** <observations>
