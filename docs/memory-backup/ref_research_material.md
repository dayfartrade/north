---
name: Research material library
description: 5 books/papers at C:\golddaytrador\research material — reference when applying discipline, halt rules, filter design, or ORB-specific analysis.
type: reference
originSessionId: 8c5c29bc-8414-4021-bbca-1894ba8135a7
---
**Path:** `C:\golddaytrador\research material\`

**Contents (verified 2026-07-13):**

| File | Use case |
|---|---|
| `Advances_in_Financial_Machine_Learning_-_Marcos_Lopez_de_Prado.pdf` | DSR, meta-labeling, purged CV, sample-weight schemes. Already applied to strategy. Re-read for regime-conditioned N. |
| `deflated-sharpe.pdf` | Formal DSR treatment (Bailey & López de Prado 2014). Ground truth for the DSR>0.95 gate. |
| `Trading_Systems_n_Methods__Website_5th_Ed_-_Perry_J_Kaufman.pdf` | Reference on regime-conditional strategies. Ch. 24 "Adaptive Techniques" directly applies to real-yield regime finding. |
| `Building_Winning_Algorithmic_Trading_Systems_-_Kevin_J_Davey.pdf` | Practical retail-quant framework: walk-forward, live-testing discipline, drawdown-based halt rules. |
| `Day_Trading_with_Short_Term_Price_Patterns_and_Opening_Range_Breakout_-_Toby_Crabel.pdf` | THE ORB reference (Crabel 1990). Session-open behavior, NRD patterns. Directly applicable to v7.2.1. |

**How to apply:** cite specific sections when justifying strategy changes. For example: "Kaufman Ch. 24 supports regime-conditioned position sizing" or "Crabel's NRD-inside-day pattern (p. 42) predicts a specific ORB outcome we don't currently filter for."
