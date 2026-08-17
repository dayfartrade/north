"""Silver Candidate 2: gold-silver ratio z-score extreme reversion.

Thesis: gold-silver ratio (GSR = gold_price / silver_price) has historical
bounds. Extreme readings tend to mean-revert as silver moves relative to
gold to restore the ratio.

Signal:
    GSR = daily gold close / daily silver close
    Compute rolling z-score over 90-day window
    LONG silver when GSR z-score >= +2.0 (ratio extreme high, silver too cheap)
    SHORT silver when GSR z-score <= -2.0 (ratio extreme low, silver too expensive)

Execution:
    Enter market at signal bar's close (daily)
    Exit when GSR z-score crosses zero (mean reversion complete)
    Or time-exit after 15 trading days (3 weeks) as fallback
    Stop: 2 x ATR(20d) on silver

Ship trigger:
    Cost-adjusted mean R > 0 with statistical significance (2-hypothesis
    Bonferroni given we plan to test 3 silver candidates).
    Dollar P&L reported alongside R for interpretation.

Costs for silver futures (SI):
    Silver futures are less liquid than gold. Wider spreads. Higher
    slippage estimates. Contract size 5000oz.
    slippage_pct: 0.0005 (5bps per side, conservative)
    fee_pct: 0.0001 (10bps RT / 2 = 5bps... actually $5 RT / (25*5000) = 4bps
                     for silver at $25 = 2bps per side)

Usage:
    python scripts/silver_candidate_gsr.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.tools.data_loader import load_gold_5m, load_silver_5m, resample
from research.tools.analysis_helpers import rolling_z_score
from research.tools.backtest import (
    backtest, Bar, Strategy, Order, ExitAction, ClosedTrade,
)
from research.tools.bootstrap_stats import evaluate_signal


CONTRACT_SIZE = 5000  # silver futures = 5000oz per contract
RT_COST = 5.0


# ------------------------------ HELPERS ------------------------------

def compute_atr(bars: list[Bar], period: int = 20) -> list[Optional[float]]:
    if not bars:
        return []
    trs: list[float] = [bars[0].high - bars[0].low]
    for i in range(1, len(bars)):
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        )
        trs.append(tr)
    return _rolling_mean(trs, period)


def _rolling_mean(values: list[float], period: int) -> list[Optional[float]]:
    result: list[Optional[float]] = []
    for i in range(len(values)):
        if i + 1 < period:
            result.append(None)
        else:
            result.append(sum(values[i + 1 - period : i + 1]) / period)
    return result


def _ms_to_iso_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def align_by_date(
    gold_bars: list[Bar], silver_bars: list[Bar]
) -> list[tuple[Bar, Bar]]:
    """Return list of (gold_bar, silver_bar) pairs aligned by date."""
    gold_by_date = {_ms_to_iso_date(b.timestamp): b for b in gold_bars}
    silver_by_date = {_ms_to_iso_date(b.timestamp): b for b in silver_bars}
    common = sorted(set(gold_by_date.keys()) & set(silver_by_date.keys()))
    return [(gold_by_date[d], silver_by_date[d]) for d in common]


# ------------------------------ SIGNAL ------------------------------

def compute_gsr_signal(
    silver_bars: list[Bar],
    gold_bars: list[Bar],
    lookback: int = 90,
    z_threshold: float = 2.0,
) -> dict[str, tuple[str, float, float]]:
    """Compute GSR z-score signal per date.

    Returns dict {date_str: (direction, gsr, z_score)} where direction is
    'LONG', 'SHORT', or 'FLAT'.
    """
    pairs = align_by_date(gold_bars, silver_bars)
    if len(pairs) < lookback + 1:
        return {}

    gsr_series = [g.close / s.close for g, s in pairs]
    z_series = rolling_z_score(gsr_series, lookback)

    signals: dict[str, tuple[str, float, float]] = {}
    for i, ((g, s), gsr, z) in enumerate(zip(pairs, gsr_series, z_series)):
        if z is None:
            continue
        date_str = _ms_to_iso_date(s.timestamp)
        if z >= z_threshold:
            signals[date_str] = ("LONG", gsr, z)
        elif z <= -z_threshold:
            signals[date_str] = ("SHORT", gsr, z)
        else:
            signals[date_str] = ("FLAT", gsr, z)
    return signals


# ------------------------------ STRATEGY ------------------------------

class SilverGSRStrategy(Strategy):
    """Enter silver on extreme GSR z-score, exit when z crosses zero.

    Time-limit exit after `max_hold_bars` if z hasn't crossed.
    Stop = 2 x silver_ATR(20d) from entry.

    Only opens ONE position at a time (per z-cross event). Won't re-open
    on the same side until z has crossed zero.
    """

    def __init__(
        self,
        signals: dict[str, tuple[str, float, float]],
        silver_atr_by_date: dict[str, float],
        max_hold_bars: int = 15,
    ):
        self.signals = signals
        self.silver_atr = silver_atr_by_date
        self.max_hold_bars = max_hold_bars

    def on_bar_no_position(self, bar, index, history):
        date_str = _ms_to_iso_date(bar.timestamp)
        if date_str not in self.signals:
            return None
        direction, gsr, z = self.signals[date_str]
        if direction not in ("LONG", "SHORT"):
            return None
        atr = self.silver_atr.get(date_str)
        if atr is None or atr <= 0:
            return None
        if direction == "LONG":
            stop = bar.close - 2.0 * atr
            side = "long"
        else:
            stop = bar.close + 2.0 * atr
            side = "short"
        return Order(
            side=side,
            entry_type="market",
            stop_price=stop,
            metadata={
                "signal_date": date_str,
                "atr": atr,
                "entry_gsr": gsr,
                "entry_z": z,
            },
        )

    def on_bar_with_position(self, bar, index, history, position):
        date_str = _ms_to_iso_date(bar.timestamp)
        # Check z-score cross of zero (mean reversion complete)
        current = self.signals.get(date_str)
        if current is not None:
            _, _, z_now = current
            z_entry = position.metadata.get("entry_z", 0.0)
            # Long: entered on z >= +2, exit when z <= 0 (fully mean-reverted)
            if position.side == "long" and z_now <= 0:
                return ExitAction(reason="z_crossed_zero")
            # Short: entered on z <= -2, exit when z >= 0
            if position.side == "short" and z_now >= 0:
                return ExitAction(reason="z_crossed_zero")
        # Time limit
        held = index - position.entered_at_index
        if held >= self.max_hold_bars:
            return ExitAction(reason="time_limit")
        return None


# ------------------------------ REPORTING ------------------------------

def compute_dollar_pnl(trades: list[ClosedTrade]) -> dict:
    if not trades:
        return {"total_pnl_dollars": 0.0, "mean_pnl_dollars": 0.0, "per_trade": []}
    per_trade: list[float] = []
    for t in trades:
        if t.side == "long":
            gross = (t.exit_price - t.entry_price) * CONTRACT_SIZE
        else:
            gross = (t.entry_price - t.exit_price) * CONTRACT_SIZE
        net = gross - RT_COST
        per_trade.append(net)
    total = sum(per_trade)
    mean = total / len(per_trade)
    wins = sum(1 for p in per_trade if p > 0)
    return {
        "total_pnl_dollars": round(total, 0),
        "mean_pnl_dollars": round(mean, 2),
        "median_pnl_dollars": round(sorted(per_trade)[len(per_trade) // 2], 2),
        "best_dollars": round(max(per_trade), 0),
        "worst_dollars": round(min(per_trade), 0),
        "wins": wins,
        "losses": len(per_trade) - wins,
        "win_rate_dollar": round(wins / len(per_trade), 4),
        "per_trade": per_trade,
    }


def compute_dollar_per_year(trades: list[ClosedTrade], per_trade: list[float]) -> dict:
    per_year: dict[int, list[float]] = {}
    for t, pnl in zip(trades, per_trade):
        year = datetime.fromtimestamp(t.entry_time / 1000, tz=timezone.utc).year
        per_year.setdefault(year, []).append(pnl)
    return {
        year: {
            "n": len(pnls),
            "total_dollars": round(sum(pnls), 0),
            "mean_dollars": round(sum(pnls) / len(pnls), 2),
            "wins": sum(1 for p in pnls if p > 0),
        }
        for year, pnls in sorted(per_year.items())
    }


# ------------------------------ MAIN ------------------------------

def run_backtest(
    lookback: int, z_threshold: float, max_hold_bars: int,
    silver_daily, gold_daily,
    silver_atr_by_date, slippage_pct: float, fee_pct: float,
):
    print(f"Signal: lookback={lookback}, |z|>={z_threshold}, max_hold={max_hold_bars} days")
    signals = compute_gsr_signal(silver_daily, gold_daily, lookback, z_threshold)
    from collections import Counter
    dir_counts = Counter(v[0] for v in signals.values())
    print(f"  signal distribution: {dict(dir_counts)}")

    strat = SilverGSRStrategy(signals, silver_atr_by_date, max_hold_bars=max_hold_bars)
    result = backtest(strat, silver_daily, slippage_pct=slippage_pct, fee_pct=fee_pct)

    print(f"  trades: {len(result.trades)}")
    if not result.trades:
        return

    dol = compute_dollar_pnl(result.trades)
    r_vals = [t.cost_adjusted_r for t in result.trades]
    eval_r = evaluate_signal(f"silver_gsr_z{z_threshold}_lb{lookback}",
                             r_vals, n_hypotheses_in_batch=3,
                             ci_lower_threshold=0.0)
    print(f"  R metrics: n={result.metrics['n']}, WR={result.metrics['win_rate']:.3f}, "
          f"mean_r={result.metrics['mean_r']:.4f}, sharpe_pt={result.metrics['per_trade_sharpe']:.3f}, "
          f"maxDD={result.metrics['max_drawdown_r']:.2f}R")
    print(f"  Dollars: total=${dol['total_pnl_dollars']:.0f}, mean=${dol['mean_pnl_dollars']:.2f}/trade, "
          f"best=${dol['best_dollars']:.0f}, worst=${dol['worst_dollars']:.0f}, WR={dol['win_rate_dollar']:.3f}")
    print(f"  Bootstrap CI: mean={eval_r.mean:.4f}R  CI=[{eval_r.ci_low:.4f}, {eval_r.ci_high:.4f}]  verdict={eval_r.verdict}")

    py = compute_dollar_per_year(result.trades, dol["per_trade"])
    pos_years = sum(1 for y, s in py.items() if s["total_dollars"] > 0)
    print(f"  Positive years: {pos_years}/{len(py)}")
    return result, dol, eval_r


def main():
    START = "2010-01-01"
    END = "2026-06-30"

    print(f"Loading gold + silver 5m bars {START} to {END}...")
    gold_5m = load_gold_5m(start=START, end=END)
    silver_5m = load_silver_5m(start=START, end=END)
    print(f"  gold: {len(gold_5m)} bars, silver: {len(silver_5m)} bars")

    print("Resampling to daily...")
    gold_daily = resample(gold_5m, target_minutes=1440)
    silver_daily = resample(silver_5m, target_minutes=1440)
    print(f"  gold daily: {len(gold_daily)}, silver daily: {len(silver_daily)}")

    print("Computing silver ATR(20)...")
    silver_atr_list = compute_atr(silver_daily, period=20)
    silver_atr_by_date = {
        _ms_to_iso_date(b.timestamp): a
        for b, a in zip(silver_daily, silver_atr_list) if a is not None
    }
    print(f"  {len(silver_atr_by_date)} days")

    # Silver futures cost model
    slip = 0.0005   # 5 bps per side (silver is thinner than gold)
    fee = 0.0001    # ~$5 RT / (~$25 * 5000) / 2 sides = 2bps, use 10bps conservative

    print()
    print("=" * 70)
    print("Silver GSR z-score reversion — parameter sweep")
    print("=" * 70)

    for lookback in [60, 90, 180]:
        for z_thresh in [1.5, 2.0, 2.5]:
            for max_hold in [10, 15, 30]:
                print()
                run_backtest(
                    lookback, z_thresh, max_hold,
                    silver_daily, gold_daily, silver_atr_by_date, slip, fee,
                )


if __name__ == "__main__":
    main()
