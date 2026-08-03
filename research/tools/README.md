# Shared signal-analysis tools

Pure Python utilities for backtesting and signal evaluation. Adapted from Janus's bluechipsignal codebase and generalized to work with any asset.

## What's here

| File | Purpose |
|---|---|
| `cost_model.py` | Adjust theoretical R for slippage and fees. Suggested defaults for gold futures, GLD, silver futures, and crypto perps. |
| `bootstrap_stats.py` | Bootstrap CI, bootstrap p-value, Bonferroni-corrected signal evaluation. Statistical test at every ship or park decision. |
| `analysis_helpers.py` | Session bucketing, entry slippage bps, percentile, rolling z-score, Bollinger Bands. Small pure functions used across backtest and reporting. |
| `backtest.py` | Minimal backtest harness. Strategy interface + one loop over bars + closed-trade records with cost-adjusted R + summary metrics + per-year breakdown. |
| `data_loader.py` | Load Dukascopy 5m CSVs into Bar lists. Concatenate multi-file histories. Resample to any timeframe. Convenience loaders for gold and silver. |

## Design principles

1. **No I/O outside data_loader.** Pure functions and dataclasses elsewhere. Import safely.
2. **Asset-agnostic.** Nothing hardcoded to gold or crypto. Slippage and fee defaults are caller-provided.
3. **Defensive.** Bad inputs return safe defaults rather than raising.
4. **Stdlib only.** No numpy, no pandas dependency. Fast enough for our scale (n < 10k trades typically).

## Usage pattern for a full signal test

```python
from research.tools.data_loader import load_gold_5m, resample
from research.tools.analysis_helpers import bollinger_bands
from research.tools.backtest import backtest, Strategy, Order, ExitAction
from research.tools.bootstrap_stats import evaluate_signal

# 1. Load and resample data
bars_5m = load_gold_5m(start="2015-01-01", end="2026-06-30")
bars_4h = resample(bars_5m, target_minutes=240)

# 2. Define a strategy (subclass Strategy)
class MySignal(Strategy):
    def on_bar_no_position(self, bar, index, history):
        # Return an Order to open a position, or None
        return None
    def on_bar_with_position(self, bar, index, history, position):
        # Return an ExitAction to close, or None
        return None

# 3. Run backtest
result = backtest(
    MySignal(),
    bars_4h,
    slippage_pct=0.0002,   # gold futures GC realistic
    fee_pct=0.00003,       # IBKR
)

print(result.metrics)      # win_rate, mean_r, std_r, per_trade_sharpe, max_dd, etc.
print(result.per_year)     # per-year breakdown

# 4. Statistical evaluation against ship threshold
verdict = evaluate_signal(
    label="my_signal_v1",
    returns=[t.cost_adjusted_r for t in result.trades],
    n_hypotheses_in_batch=1,        # single candidate
    ci_lower_threshold=0.005,       # 0.5% per trade minimum
)
print(verdict.verdict)              # 'positive', 'negative', 'indist', or 'empty'
```

## Not included (intentional)

- Live-trading credentials
- Exchange-specific auth
- Database persistence layer
- Signal-specific logic (lives per-signal in `scripts/` or `research/experiments/`)

## Source attribution

Adapted from `research/janus_2026_07_31/code/*.py`. Original files preserved unchanged in that directory for reference.
