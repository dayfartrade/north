# Experiment: janus_q4_trailing_stop

**Registered UTC:** 2026-07-07T18:35:00Z
**Blinded until:** results section fills after backtest, same session
**Layer:** strategy_engine (this WOULD change the exit rules embedded in run_orb_v7 if shipped)
**Owner:** Knox

## Hypothesis

An MFE-locking trailing stop schedule (rules from Janus's 2026-07-07 Q4 reply)
improves mean/trade AND holds within 3pp of baseline win rate on the v7.2.1
sample. Reference for rule: winners peak at median 87 min per our MFE analysis
2026-07-07 — locking 50% MFE captures the tail without giving all back.

## Rationale

MFE analysis on the 52 shipped trades showed:
- Winners peak at median 87 min (MFE 2.03R)
- Losers reveal early: MAE median 50 min (MAE 1.84R by loser exit)
- 54% of trades touch 1R; 68% of those keep going to target

The current v7.2.1 rule is fixed target + fixed stop + 180-min time exit. If
we could capture some of the winner tail without giving back MFE, we should
see mean/trade lift with win rate roughly held.

## Data

- **Window:** 2026-04-13 → 2026-07-01 (v7.2.1 sample as of this session)
- **Expected sample size:** n=52 (unchanged from baseline — same signals, different exits)
- **Split:** chronological 60/40 (train first 31, test last 21)

## Method

For each of the 52 trades:

1. Reconstruct minute-by-minute trajectory from 5m bars (using
   `src/trajectory_snapshot.reconstruct_from_bars`)
2. Simulate the trailing schedule:
   - **0-60 min from entry:** original stop_price, original target_price
   - **60-120 min:** if MFE-so-far > 0.5 × target_dist_from_entry, move stop to entry (breakeven)
   - **120-180 min:** stop = entry + direction × 0.5 × peak_MFE_seen_so_far
   - **180 min:** time exit at close of that bar
3. Detect the earliest bar that hits the (possibly moving) stop or the target
4. Compute net P&L using existing $24 RT cost

## Decision rule — LOCKED

**Ship** if ALL of:

1. Full-sample mean/trade increases by ≥ $50 vs v7.2.1 baseline (+$812)
2. Full-sample win rate is NOT lower than baseline (69.2%) by more than 3pp
3. OOS test-set mean/trade CI lower bound ≥ 0 (bootstrap, n_boot=10,000)
4. Permutation p-value on OOS lift < 0.05 / N (Bonferroni)

**Shadow-continue** if:

- Mean/trade lift is +$0 to +$50, or win rate drops 1-3pp: log and wait for more data
- OOS CI includes zero but full-sample is positive

**Reject** if any of:

1. Full-sample mean/trade drops
2. Win rate drops > 3pp
3. Both train and test collapse (both means < baseline)

## Bonferroni denominator

Registered hypotheses this calendar month (2026-07):

1. janus_q4_trailing_stop (this one)
2. vol_ratio_ge_1_0 (shadow-mode only — does not consume budget)

- Current N of live-decision experiments: 1
- Adjusted α: 0.05 / 1 = 0.05

(N=1 because vol_ratio is shadow-only. Future filter promotions would raise N.)

## Results (fill AFTER running — do not edit above)

- **Ran on:** 2026-07-07
- **Sample size:** n=52
- **In-sample (baseline):** win=69.2%  mean=$+812  total=$+42,222
- **In-sample (trailing):** win=63.5%  mean=$+778  total=$+40,472
- **OOS test-set (baseline):** win=81.0%  mean=$+1262
- **OOS test-set (trailing):** win=71.4%  mean=$+1117
- **Matched-pair OOS mean lift:** -$145  95% CI [-$658, +$450]
- **Permutation p-value:** 0.6543
- **Bonferroni threshold:** 0.05 (N=1)
- **Gates:** G1=FAIL  G2=FAIL  G3=FAIL  G4=FAIL
- **Verdict:** **REJECT**

### Notes

The trailing stop is systematically exiting would-be target winners at
breakeven or small profit. Exit-reason breakdown reveals it:

- Trailed-stop exits: n=32, 40.6% win, mean +$76
- Target exits: n=19, 100% win, mean +$1,936
- Time exits: n=1

The 40.6% win rate at trailed-stop exits shows the schedule is triggering
on transient pullbacks. Under baseline v7.2.1 those pullbacks recover to
target; under this schedule they cash out flat.

Janus's rule is directionally right for his domain (crypto perps with
frequent noise and 1-2 bps spread). GC gold's ORB winners have deeper
pullbacks after MFE and recover — the "peak MFE lock" cuts them off.

Reject as-designed. Do NOT re-tune the 50% threshold post-hoc on the same
data — that would be textbook p-hacking. If a variant is tested, it needs
a fresh pre-registration and Bonferroni bump.

Pipeline validation: this experiment run was the first through the
pre-registration + shadow + trajectory infrastructure. Verdict was honored
without tuning. Discipline held.
