"""Minimal backtest harness for signal evaluation.

Design goals:
- Strategy owns its own signal-generation state (pending signals, waiting
  for entry triggers, etc). Harness stays simple.
- Harness owns position management: entry, exit checks, stop hits,
  trade recording, cost-adjusted R computation.
- One clean loop over bars. No lookahead. Signal at bar N only sees bars
  0 through N.
- Returns per-trade records plus summary metrics.
- Not a fancy framework. Just enough to test a signal honestly against
  historical bars.

Interface for strategies:
    class Strategy:
        def on_bar_no_position(bar, index, history) -> Optional[Order]:
            "Called each bar when no position is open. Return Order to
             open a trade at this bar's close price (or per Order's rule)."

        def on_bar_with_position(bar, index, history, position) -> Optional[ExitAction]:
            "Called each bar when a position is open. Return ExitAction
             to close at this bar's close (or per ExitAction's rule)."

Both methods default to returning None so strategies only need to
implement what they care about.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Callable

from .cost_model import compute_cost_adjusted_r


# ------------------------------ TYPES ------------------------------

@dataclass(frozen=True)
class Bar:
    """OHLCV bar. Timestamp is unix milliseconds."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class Order:
    """Request to enter a position.

    entry_type:
      'market'           = fill at this bar's close
      'market_next_open' = fill at the OPEN of the next bar (matches
                           real-world "signal Friday, execute Monday open")
      'limit'            = fill only if limit_price is touched by the next
                           bar's low/high (long: bar.low <= limit_price;
                           short: bar.high >= limit_price). Filled at
                           limit_price.

    stop_price: hard stop, applied from actual entry price. Required.

    metadata: free-form dict for strategy annotations (BB level, signal source, etc).
    """
    side: str
    entry_type: str = "market"
    limit_price: Optional[float] = None
    stop_price: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class Position:
    """An open position tracked by the harness."""
    side: str
    entry_time: int
    entry_price: float
    entered_at_index: int
    stop_price: float
    metadata: dict = field(default_factory=dict)


@dataclass
class ExitAction:
    """Request to close the current position.

    reason: text label recorded on the trade
    price: if provided, that's the exit price. If None, exits at bar close.
    """
    reason: str
    price: Optional[float] = None


@dataclass
class ClosedTrade:
    """A completed round-trip trade with cost accounting."""
    side: str
    entry_time: int
    entry_price: float
    exit_time: int
    exit_price: float
    stop_price: float
    exit_reason: str
    duration_bars: int
    theoretical_r: float
    cost_adjusted_r: float
    metadata: dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    trades: list[ClosedTrade]
    total_bars: int
    metrics: dict
    per_year: dict


class Strategy:
    """Default strategy: does nothing. Override on_bar_* methods."""

    def on_bar_no_position(
        self, bar: Bar, index: int, history: list[Bar],
    ) -> Optional[Order]:
        return None

    def on_bar_with_position(
        self, bar: Bar, index: int, history: list[Bar], position: Position,
    ) -> Optional[ExitAction]:
        return None


# ------------------------------ HARNESS ------------------------------

def backtest(
    strategy: Strategy,
    bars: list[Bar],
    *,
    slippage_pct: float,
    fee_pct: float,
    close_open_position_at_end: bool = True,
) -> BacktestResult:
    """Run strategy against bars. Return closed trades and summary metrics.

    Slippage and fee defaults live in cost_model.py. Pass values appropriate
    to your asset (see suggested defaults in cost_model docstrings).
    """
    if not bars:
        return BacktestResult(
            trades=[], total_bars=0, metrics={}, per_year={},
        )

    trades: list[ClosedTrade] = []
    position: Optional[Position] = None
    pending_order: Optional[Order] = None

    for i, bar in enumerate(bars):
        history = bars[: i + 1]

        # Step 1: if a limit order is pending from a prior bar, check for fill.
        if pending_order is not None and position is None:
            filled_price = _check_limit_fill(pending_order, bar)
            if filled_price is not None:
                position = Position(
                    side=pending_order.side,
                    entry_time=bar.timestamp,
                    entry_price=filled_price,
                    entered_at_index=i,
                    stop_price=pending_order.stop_price,
                    metadata=dict(pending_order.metadata),
                )
                pending_order = None

        # Step 2: if we have an open position, check the hard stop first
        # (stops take priority over strategy exit signals).
        if position is not None:
            stop_hit = _check_stop_hit(position, bar)
            if stop_hit:
                trade = _close_position(
                    position, bar, exit_price=position.stop_price,
                    exit_reason="stop", index=i,
                    slippage_pct=slippage_pct, fee_pct=fee_pct,
                )
                trades.append(trade)
                position = None
                continue

            # Then ask the strategy if it wants to exit.
            action = strategy.on_bar_with_position(bar, i, history, position)
            if action is not None:
                exit_price = action.price if action.price is not None else bar.close
                trade = _close_position(
                    position, bar, exit_price=exit_price,
                    exit_reason=action.reason, index=i,
                    slippage_pct=slippage_pct, fee_pct=fee_pct,
                )
                trades.append(trade)
                position = None

        # Step 3: if no position, ask strategy for new orders.
        if position is None:
            new_order = strategy.on_bar_no_position(bar, i, history)
            if new_order is not None:
                if new_order.entry_type == "market":
                    # Fill at this bar's close.
                    position = Position(
                        side=new_order.side,
                        entry_time=bar.timestamp,
                        entry_price=bar.close,
                        entered_at_index=i,
                        stop_price=new_order.stop_price,
                        metadata=dict(new_order.metadata),
                    )
                    pending_order = None
                elif new_order.entry_type == "market_next_open":
                    # Fill at the OPEN of the NEXT bar. Model this by
                    # queuing an order that fills unconditionally on next tick.
                    # Use a sentinel: limit_price = None with a special flag.
                    pending_order = new_order  # handled in _check_limit_fill via type check
                elif new_order.entry_type == "limit":
                    # Queue the order for next bar's price check.
                    pending_order = new_order
                else:
                    raise ValueError(f"Unknown entry_type: {new_order.entry_type}")

    # Step 4: end of data. Close any open position at last bar's close.
    if position is not None and close_open_position_at_end and bars:
        last = bars[-1]
        trade = _close_position(
            position, last, exit_price=last.close,
            exit_reason="end_of_data", index=len(bars) - 1,
            slippage_pct=slippage_pct, fee_pct=fee_pct,
        )
        trades.append(trade)

    metrics = compute_metrics(trades)
    per_year = compute_per_year(trades)
    return BacktestResult(
        trades=trades, total_bars=len(bars), metrics=metrics, per_year=per_year,
    )


def _check_limit_fill(order: Order, bar: Bar) -> Optional[float]:
    """Return fill price if the order fills on this bar, else None.

    For 'market_next_open' orders, always fills at this bar's open.
    For 'limit' orders, fills only if limit_price is touched.
    """
    if order.entry_type == "market_next_open":
        return bar.open
    if order.limit_price is None:
        return None
    if order.side == "long" and bar.low <= order.limit_price:
        return order.limit_price
    if order.side == "short" and bar.high >= order.limit_price:
        return order.limit_price
    return None


def _check_stop_hit(position: Position, bar: Bar) -> bool:
    """Return True if the bar's range triggered the stop."""
    if position.side == "long":
        return bar.low <= position.stop_price
    return bar.high >= position.stop_price


def _close_position(
    position: Position, bar: Bar, *, exit_price: float, exit_reason: str,
    index: int, slippage_pct: float, fee_pct: float,
) -> ClosedTrade:
    """Compute R metrics and create a ClosedTrade."""
    risk = abs(position.entry_price - position.stop_price)
    if risk == 0:
        theoretical_r = 0.0
    elif position.side == "long":
        theoretical_r = (exit_price - position.entry_price) / risk
    else:
        theoretical_r = (position.entry_price - exit_price) / risk
    theoretical_r = round(theoretical_r, 4)

    cost_r = compute_cost_adjusted_r(
        side=position.side,
        entry=position.entry_price,
        exit_price=exit_price,
        sl=position.stop_price,
        slippage_pct=slippage_pct,
        fee_pct=fee_pct,
    )

    return ClosedTrade(
        side=position.side,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        exit_time=bar.timestamp,
        exit_price=exit_price,
        stop_price=position.stop_price,
        exit_reason=exit_reason,
        duration_bars=index - position.entered_at_index,
        theoretical_r=theoretical_r,
        cost_adjusted_r=cost_r,
        metadata=dict(position.metadata),
    )


# ------------------------------ METRICS ------------------------------

def compute_metrics(trades: list[ClosedTrade]) -> dict:
    """Standard summary metrics. Empty dict if no trades."""
    if not trades:
        return {"n": 0}
    n = len(trades)
    wins = [t for t in trades if t.cost_adjusted_r > 0]
    losses = [t for t in trades if t.cost_adjusted_r < 0]
    all_r = [t.cost_adjusted_r for t in trades]
    all_r_theo = [t.theoretical_r for t in trades]

    mean_r = sum(all_r) / n
    mean_r_theo = sum(all_r_theo) / n
    win_rate = len(wins) / n

    # Standard deviation of R (per-trade)
    var = sum((r - mean_r) ** 2 for r in all_r) / n if n > 1 else 0.0
    std_r = var ** 0.5

    # Sharpe: annualization requires knowing trade frequency; skip for now,
    # report only per-trade Sharpe.
    per_trade_sharpe = (mean_r / std_r) if std_r > 0 else 0.0

    # Max drawdown on cumulative R equity curve
    equity_curve = []
    cum = 0.0
    for t in trades:
        cum += t.cost_adjusted_r
        equity_curve.append(cum)
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = eq - peak
        if dd < max_dd:
            max_dd = dd

    return {
        "n": n,
        "win_rate": round(win_rate, 4),
        "mean_r": round(mean_r, 4),
        "mean_r_theoretical": round(mean_r_theo, 4),
        "median_r": round(sorted(all_r)[n // 2], 4),
        "best_trade_r": round(max(all_r), 4),
        "worst_trade_r": round(min(all_r), 4),
        "std_r": round(std_r, 4),
        "per_trade_sharpe": round(per_trade_sharpe, 4),
        "max_drawdown_r": round(max_dd, 4),
        "total_r": round(sum(all_r), 4),
        "long_trades": sum(1 for t in trades if t.side == "long"),
        "short_trades": sum(1 for t in trades if t.side == "short"),
        "cost_drag": round(mean_r_theo - mean_r, 4),
    }


def compute_per_year(trades: list[ClosedTrade]) -> dict:
    """Per-year breakdown of trade count and mean R.

    Year is determined by entry_time (unix ms). Uses UTC.
    """
    from datetime import datetime, timezone

    per_year: dict[int, list[float]] = {}
    for t in trades:
        year = datetime.fromtimestamp(t.entry_time / 1000, tz=timezone.utc).year
        per_year.setdefault(year, []).append(t.cost_adjusted_r)

    return {
        year: {
            "n": len(rs),
            "mean_r": round(sum(rs) / len(rs), 4),
            "total_r": round(sum(rs), 4),
            "wins": sum(1 for r in rs if r > 0),
        }
        for year, rs in sorted(per_year.items())
    }


# ------------------------------ SIMPLE DEMO STRATEGY ------------------------------

class BuyAndHoldEveryNBars(Strategy):
    """Trivial demo strategy: opens a long every N bars, exits after M bars.

    Only used to sanity-check the harness. Not a real strategy.
    """

    def __init__(self, n_bars_between_entries: int, hold_bars: int, stop_pct: float):
        self.n = n_bars_between_entries
        self.hold_bars = hold_bars
        self.stop_pct = stop_pct
        self._last_entry_bar = -10 ** 9

    def on_bar_no_position(self, bar, index, history):
        if index - self._last_entry_bar < self.n:
            return None
        self._last_entry_bar = index
        return Order(
            side="long",
            entry_type="market",
            stop_price=bar.close * (1 - self.stop_pct),
            metadata={"opened_at": bar.timestamp},
        )

    def on_bar_with_position(self, bar, index, history, position):
        if index - position.entered_at_index >= self.hold_bars:
            return ExitAction(reason="time_exit")
        return None
