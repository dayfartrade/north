"""Silver Candidate 3: volatility regime signal.

Thesis: silver has distinct volatility regimes. Different mechanisms have
edge in different regimes. In LOW-vol regimes, mean-reversion works. In
HIGH-vol regimes, breakouts have follow-through.

Pre-registered baseline (locked BEFORE seeing results):
    vol_lookback = 20d realized vol (annualized from log returns)
    vol_low  threshold = 25% (below = LOW regime)
    vol_high threshold = 40% (above = HIGH regime; between = MEDIUM = flat)
    LOW  + close > MA20  -> SHORT silver (mean-revert)
    HIGH + close crosses above MA10 (yesterday <=, today >) -> LONG silver
    Everything else -> FLAT
    Stop = 2 * ATR(20). Time exit = 15 bars. Fill = next-bar open.

Costs (matches Candidate 2 for comparability):
    slippage_pct = 0.0005 (silver book thinner than gold)
    fee_pct      = 0.0001

Bonferroni: 3-hypothesis correction (this is one of 3 pre-registered silver
candidates). Ship trigger: cost-adjusted mean R with ci_low >= 0.005
(0.5% per trade) AND p_adjusted < 0.05.

Post-baseline robustness sweep: report only, does NOT get its own
Bonferroni credit (that's why baseline is locked first).

Usage: python scripts/silver_candidate_vol_regime.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.tools.data_loader import load_silver_5m, resample
from research.tools.backtest import (
    backtest, Bar, Strategy, Order, ExitAction, ClosedTrade,
)
from research.tools.bootstrap_stats import evaluate_signal


CONTRACT_SIZE = 5000
RT_COST = 5.0


def _ms_to_iso_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


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


def realized_vol_annualized(closes: list[float], lookback: int) -> list[Optional[float]]:
    """Annualized realized vol from log returns over rolling window."""
    logrets: list[float] = [0.0]
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            logrets.append(math.log(closes[i] / closes[i - 1]))
        else:
            logrets.append(0.0)
    result: list[Optional[float]] = []
    for i in range(len(closes)):
        if i + 1 < lookback + 1:
            result.append(None)
            continue
        window = logrets[i + 1 - lookback : i + 1]
        m = sum(window) / lookback
        var = sum((x - m) ** 2 for x in window) / (lookback - 1)
        result.append(math.sqrt(var) * math.sqrt(252))
    return result


def compute_vol_regime_signal(
    silver_daily: list[Bar],
    vol_low: float = 0.25,
    vol_high: float = 0.40,
    vol_lookback: int = 20,
    rev_ma: int = 20,
    brk_ma: int = 10,
) -> dict[str, tuple[str, float, str]]:
    """Return {date_str: (direction, vol_ann, regime)}."""
    closes = [b.close for b in silver_daily]
    vol = realized_vol_annualized(closes, vol_lookback)
    ma_rev = _rolling_mean(closes, rev_ma)
    ma_brk = _rolling_mean(closes, brk_ma)

    signals: dict[str, tuple[str, float, str]] = {}
    for i in range(len(silver_daily)):
        v = vol[i]
        mr = ma_rev[i]
        mb = ma_brk[i]
        if v is None or mr is None or mb is None or i == 0:
            continue
        mb_prev = ma_brk[i - 1]
        if mb_prev is None:
            continue

        date_str = _ms_to_iso_date(silver_daily[i].timestamp)
        c = silver_daily[i].close
        c_prev = silver_daily[i - 1].close

        if v < vol_low:
            regime = "LOW"
            if c > mr:
                signals[date_str] = ("SHORT", v, regime)
            else:
                signals[date_str] = ("FLAT", v, regime)
        elif v > vol_high:
            regime = "HIGH"
            crossed_up = (c_prev <= mb_prev) and (c > mb)
            if crossed_up:
                signals[date_str] = ("LONG", v, regime)
            else:
                signals[date_str] = ("FLAT", v, regime)
        else:
            signals[date_str] = ("FLAT", v, "MED")
    return signals


class SilverVolRegimeStrategy(Strategy):
    """Enter on regime signal. Exit on stop, time, or regime change."""

    def __init__(
        self,
        signals: dict[str, tuple[str, float, str]],
        atr_by_date: dict[str, float],
        max_hold_bars: int = 15,
        exit_on_regime_change: bool = False,
    ):
        self.signals = signals
        self.atr = atr_by_date
        self.max_hold_bars = max_hold_bars
        self.exit_on_regime_change = exit_on_regime_change

    def on_bar_no_position(self, bar, index, history):
        date_str = _ms_to_iso_date(bar.timestamp)
        sig = self.signals.get(date_str)
        if sig is None:
            return None
        direction, _, regime = sig
        if direction not in ("LONG", "SHORT"):
            return None
        atr = self.atr.get(date_str)
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
            entry_type="market_next_open",
            stop_price=stop,
            metadata={"signal_date": date_str, "entry_regime": regime, "atr": atr},
        )

    def on_bar_with_position(self, bar, index, history, position):
        held = index - position.entered_at_index
        if held >= self.max_hold_bars:
            return ExitAction(reason="time_limit")
        if self.exit_on_regime_change:
            date_str = _ms_to_iso_date(bar.timestamp)
            cur = self.signals.get(date_str)
            if cur is not None:
                _, _, regime = cur
                if regime != position.metadata.get("entry_regime"):
                    return ExitAction(reason="regime_change")
        return None


def compute_dollar_pnl(trades: list[ClosedTrade]) -> dict:
    if not trades:
        return {"total_pnl_dollars": 0.0, "mean_pnl_dollars": 0.0, "per_trade": []}
    per_trade: list[float] = []
    for t in trades:
        if t.side == "long":
            gross = (t.exit_price - t.entry_price) * CONTRACT_SIZE
        else:
            gross = (t.entry_price - t.exit_price) * CONTRACT_SIZE
        per_trade.append(gross - RT_COST)
    total = sum(per_trade)
    wins = sum(1 for p in per_trade if p > 0)
    return {
        "total_pnl_dollars": round(total, 0),
        "mean_pnl_dollars": round(total / len(per_trade), 2),
        "median_pnl_dollars": round(sorted(per_trade)[len(per_trade) // 2], 2),
        "best_dollars": round(max(per_trade), 0),
        "worst_dollars": round(min(per_trade), 0),
        "wins": wins,
        "losses": len(per_trade) - wins,
        "win_rate_dollar": round(wins / len(per_trade), 4),
        "per_trade": per_trade,
    }


def per_year_dollars(trades: list[ClosedTrade], per_trade: list[float]) -> dict:
    by_year: dict[int, list[float]] = {}
    for t, p in zip(trades, per_trade):
        y = datetime.fromtimestamp(t.entry_time / 1000, tz=timezone.utc).year
        by_year.setdefault(y, []).append(p)
    return {
        y: {"n": len(v), "total": round(sum(v), 0), "mean": round(sum(v) / len(v), 2),
            "wins": sum(1 for p in v if p > 0)}
        for y, v in sorted(by_year.items())
    }


def run_config(
    label: str, silver_daily, atr_by_date, slip, fee,
    vol_low, vol_high, vol_lookback, rev_ma, brk_ma, max_hold,
    exit_regime, n_hypotheses,
):
    print(f"\n--- {label} ---")
    print(f"  vol_low={vol_low}, vol_high={vol_high}, vol_lb={vol_lookback}, "
          f"rev_ma={rev_ma}, brk_ma={brk_ma}, hold={max_hold}, "
          f"exit_regime={exit_regime}")
    sigs = compute_vol_regime_signal(silver_daily, vol_low, vol_high,
                                     vol_lookback, rev_ma, brk_ma)
    from collections import Counter
    dist = Counter(v[0] for v in sigs.values())
    reg = Counter(v[2] for v in sigs.values())
    print(f"  direction dist: {dict(dist)}")
    print(f"  regime dist:    {dict(reg)}")

    strat = SilverVolRegimeStrategy(sigs, atr_by_date, max_hold, exit_regime)
    result = backtest(strat, silver_daily, slippage_pct=slip, fee_pct=fee)
    print(f"  trades: {len(result.trades)}")
    if not result.trades:
        return None

    dol = compute_dollar_pnl(result.trades)
    r_vals = [t.cost_adjusted_r for t in result.trades]
    ev = evaluate_signal(label, r_vals, n_hypotheses_in_batch=n_hypotheses,
                         ci_lower_threshold=0.005)
    m = result.metrics
    print(f"  R: n={m['n']} WR={m['win_rate']:.3f} mean_r={m['mean_r']:.4f} "
          f"sharpe_pt={m['per_trade_sharpe']:.3f} maxDD={m['max_drawdown_r']:.2f}R")
    print(f"  $: total=${dol['total_pnl_dollars']:.0f} mean=${dol['mean_pnl_dollars']:.2f}/tr "
          f"best=${dol['best_dollars']:.0f} worst=${dol['worst_dollars']:.0f} "
          f"WR$={dol['win_rate_dollar']:.3f}")
    print(f"  Bootstrap: mean={ev.mean:.4f}R CI=[{ev.ci_low:.4f},{ev.ci_high:.4f}] "
          f"p_adj={ev.p_adjusted:.4f} verdict={ev.verdict}")
    py = per_year_dollars(result.trades, dol["per_trade"])
    pos = sum(1 for _, s in py.items() if s["total"] > 0)
    print(f"  Positive years: {pos}/{len(py)}")
    return {"metrics": m, "dollars": dol, "eval": ev, "per_year": py}


def main():
    START = "2010-01-01"
    END = "2026-06-30"

    print(f"Loading silver 5m {START} to {END}...")
    silver_5m = load_silver_5m(start=START, end=END)
    print(f"  {len(silver_5m)} bars")

    print("Resampling to daily...")
    silver_daily = resample(silver_5m, target_minutes=1440)
    print(f"  {len(silver_daily)} daily bars")

    print("Computing ATR(20)...")
    atr_list = compute_atr(silver_daily, period=20)
    atr_by_date = {_ms_to_iso_date(b.timestamp): a
                   for b, a in zip(silver_daily, atr_list) if a is not None}
    print(f"  {len(atr_by_date)} days")

    slip, fee = 0.0005, 0.0001

    print("\n" + "=" * 70)
    print("SILVER CANDIDATE 3 — VOLATILITY REGIME")
    print("=" * 70)

    print("\n### PRE-REGISTERED BASELINE (Bonferroni n=3) ###")
    run_config("baseline_25_40_ma20_10_hold15", silver_daily, atr_by_date,
               slip, fee, 0.25, 0.40, 20, 20, 10, 15, False, 3)

    print("\n\n### POST-HOC ROBUSTNESS (no Bonferroni credit) ###")
    print("Report only. If baseline fails, these do NOT rescue it.")

    for vl, vh in [(0.20, 0.35), (0.30, 0.45), (0.20, 0.40)]:
        run_config(f"vol_thresh_{vl}_{vh}", silver_daily, atr_by_date,
                   slip, fee, vl, vh, 20, 20, 10, 15, False, 3)

    for rm, bm in [(10, 5), (40, 20), (20, 20)]:
        run_config(f"ma_{rm}_{bm}", silver_daily, atr_by_date,
                   slip, fee, 0.25, 0.40, 20, rm, bm, 15, False, 3)

    for h in [10, 30]:
        run_config(f"hold_{h}", silver_daily, atr_by_date,
                   slip, fee, 0.25, 0.40, 20, 20, 10, h, False, 3)

    run_config("baseline_with_regime_exit", silver_daily, atr_by_date,
               slip, fee, 0.25, 0.40, 20, 20, 10, 15, True, 3)


if __name__ == "__main__":
    main()
