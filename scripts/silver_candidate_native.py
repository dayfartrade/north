"""Silver Candidate 1: silver-native momentum + oil as industrial macro.

Structural analog of NORTH v1 but tuned for silver's dual-demand nature.

Signal (all 4 must agree):
    LONG if:
        - 4-week silver momentum > 0
        - 12-week silver momentum > 0
        - silver MA10 > MA40
        - 20-day oil price change > 0 (industrial demand rising)
    SHORT if all inverted.
    FLAT otherwise.

Rationale for using oil as industrial macro:
    - Silver is roughly 55% industrial demand
    - Oil is a broad industrial-activity proxy
    - We have oil 5m data (LIGHT.CMDUSD Dukascopy)
    - Copper would be a better direct proxy but we don't have it yet

Execution: same as NORTH v1 calibrated (4H bars, Monday 12:00 UTC entry,
Friday 20:00 UTC exit, 2 x ATR(20d) silver stop).

Ship trigger: cost-adjusted mean R > 0 with statistical significance
after 3-hypothesis Bonferroni correction (3 silver candidates total).

Costs: silver futures SI, slippage 5bps per side, fee ~2bps per side.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.tools.data_loader import load_silver_5m, load_dukascopy_multi, resample
from research.tools.backtest import (
    backtest, Bar, Strategy, Order, ExitAction, ClosedTrade,
)
from research.tools.bootstrap_stats import evaluate_signal

DUKASCOPY_ROOT = ROOT / "data" / "external" / "dukascopy"
OIL_FILES = [DUKASCOPY_ROOT / "LIGHT.CMDUSD_5m_historical.csv"]

CONTRACT_SIZE = 5000  # silver futures contract size (oz)
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


def _ms_to_utc_weekday(ts_ms: int) -> int:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).weekday()


# ------------------------------ SIGNAL ------------------------------

def compute_silver_native_signal(
    silver_daily: list[Bar],
    oil_daily: list[Bar],
) -> dict[str, str]:
    """Compute Candidate 1 signal per date.

    Returns dict {date_str: 'LONG' | 'SHORT' | 'FLAT'}.
    """
    if len(silver_daily) < 61:
        return {}

    silver_closes = [b.close for b in silver_daily]
    ma10 = _rolling_mean(silver_closes, 10)
    ma40 = _rolling_mean(silver_closes, 40)

    # Build oil close by date for alignment
    oil_by_date = {_ms_to_iso_date(b.timestamp): b.close for b in oil_daily}

    signals: dict[str, str] = {}
    for i in range(60, len(silver_daily)):
        if ma10[i] is None or ma40[i] is None:
            continue

        # Silver momentum
        s_m20 = (silver_closes[i] - silver_closes[i - 20]) / silver_closes[i - 20]
        s_m60 = (silver_closes[i] - silver_closes[i - 60]) / silver_closes[i - 60]

        # MA cross
        ma_bullish = ma10[i] > ma40[i]

        # Oil 20-day change (industrial macro)
        date_str = _ms_to_iso_date(silver_daily[i].timestamp)
        date_20_ago = _ms_to_iso_date(silver_daily[i - 20].timestamp)
        oil_now = _lookup_or_backfill(oil_by_date, date_str)
        oil_then = _lookup_or_backfill(oil_by_date, date_20_ago)
        if oil_now is None or oil_then is None:
            continue
        oil_change = (oil_now - oil_then) / oil_then  # fractional change

        long_all = s_m20 > 0 and s_m60 > 0 and ma_bullish and oil_change > 0
        short_all = s_m20 < 0 and s_m60 < 0 and not ma_bullish and oil_change < 0

        if long_all:
            signals[date_str] = "LONG"
        elif short_all:
            signals[date_str] = "SHORT"
        else:
            signals[date_str] = "FLAT"

    return signals


def _lookup_or_backfill(series: dict[str, float], date_str: str) -> Optional[float]:
    if date_str in series:
        return series[date_str]
    from datetime import timedelta
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    for offset in range(1, 6):
        candidate = (dt - timedelta(days=offset)).strftime("%Y-%m-%d")
        if candidate in series:
            return series[candidate]
    return None


# ------------------------------ STRATEGY (NORTH v1 style on silver 4H) ------------------------------

class SilverNativeStrategy(Strategy):
    """Weekly silver: signal from daily, enter ~12:00 UTC Mon, exit ~20:00 UTC Fri.

    Stop = 2 x silver ATR(20d) from Friday close.
    """

    def __init__(self, signals: dict[str, str], atr_by_date: dict[str, float]):
        self.signals = signals
        self.atr = atr_by_date

    def on_bar_no_position(self, bar, index, history):
        weekday = _ms_to_utc_weekday(bar.timestamp)
        dt = datetime.fromtimestamp(bar.timestamp / 1000, tz=timezone.utc)
        if weekday == 0 and dt.hour == 8:  # Monday 08:00-12:00 UTC bar
            date_str = dt.strftime("%Y-%m-%d")
            friday_date = self._most_recent_friday(date_str)
            if friday_date and friday_date in self.signals:
                sig = self.signals[friday_date]
                if sig in ("LONG", "SHORT"):
                    atr_val = self.atr.get(friday_date)
                    if atr_val is not None and atr_val > 0:
                        if sig == "LONG":
                            stop = bar.close - 2.0 * atr_val
                        else:
                            stop = bar.close + 2.0 * atr_val
                        return Order(
                            side="long" if sig == "LONG" else "short",
                            entry_type="market_next_open",
                            stop_price=stop,
                            metadata={"signal_date": friday_date, "atr": atr_val},
                        )
        return None

    def on_bar_with_position(self, bar, index, history, position):
        weekday = _ms_to_utc_weekday(bar.timestamp)
        dt = datetime.fromtimestamp(bar.timestamp / 1000, tz=timezone.utc)
        if weekday == 4 and dt.hour == 16:  # Friday 16:00-20:00 UTC bar
            return ExitAction(reason="friday_close")
        return None

    def _most_recent_friday(self, date_str: str) -> Optional[str]:
        from datetime import timedelta
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        for offset in range(1, 8):
            candidate = dt - timedelta(days=offset)
            if candidate.weekday() == 4:
                return candidate.strftime("%Y-%m-%d")
        return None


# ------------------------------ REPORTING (shared with GSR script) ------------------------------

def compute_dollar_pnl(trades: list[ClosedTrade]) -> dict:
    if not trades:
        return {"total_pnl_dollars": 0.0, "per_trade": []}
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

def main():
    START = "2010-01-01"
    END = "2026-06-30"

    print(f"Loading silver + oil 5m bars {START} to {END}...")
    silver_5m = load_silver_5m(start=START, end=END)
    oil_5m = load_dukascopy_multi(OIL_FILES, start=START, end=END)
    print(f"  silver: {len(silver_5m)} bars, oil: {len(oil_5m)} bars")

    print("Resampling to daily and 4H (silver)...")
    silver_daily = resample(silver_5m, target_minutes=1440)
    silver_4h = resample(silver_5m, target_minutes=240)
    oil_daily = resample(oil_5m, target_minutes=1440)
    print(f"  silver daily: {len(silver_daily)}, silver 4H: {len(silver_4h)}, oil daily: {len(oil_daily)}")

    print("Computing signal...")
    signals = compute_silver_native_signal(silver_daily, oil_daily)
    from collections import Counter
    dir_counts = Counter(signals.values())
    print(f"  distribution: {dict(dir_counts)}")

    print("Computing silver ATR(20)...")
    atr_list = compute_atr(silver_daily, period=20)
    silver_atr_by_date = {
        _ms_to_iso_date(b.timestamp): a
        for b, a in zip(silver_daily, atr_list) if a is not None
    }

    slip = 0.0005
    fee = 0.0001

    print()
    print("=" * 70)
    print("Running silver native momentum + oil backtest...")
    strat = SilverNativeStrategy(signals, silver_atr_by_date)
    result = backtest(strat, silver_4h, slippage_pct=slip, fee_pct=fee)

    dol = compute_dollar_pnl(result.trades)
    r_vals = [t.cost_adjusted_r for t in result.trades]
    eval_r = evaluate_signal("silver_native", r_vals,
                             n_hypotheses_in_batch=3,
                             ci_lower_threshold=0.0)

    print()
    print("R metrics:")
    for k in ["n", "win_rate", "mean_r", "median_r", "std_r",
              "per_trade_sharpe", "max_drawdown_r", "total_r",
              "long_trades", "short_trades"]:
        print(f"  {k:<25} {result.metrics.get(k, 0):>15}")

    print()
    print(f"Dollar P&L (5000oz silver contract, $5 RT):")
    for k in ["total_pnl_dollars", "mean_pnl_dollars", "median_pnl_dollars",
              "best_dollars", "worst_dollars", "wins", "losses", "win_rate_dollar"]:
        print(f"  {k:<25} {dol.get(k, 0):>15}")

    print()
    print(f"Bootstrap CI (3-hypothesis Bonferroni):")
    print(f"  mean={eval_r.mean:.4f}R  CI=[{eval_r.ci_low:.4f}, {eval_r.ci_high:.4f}]  verdict={eval_r.verdict}")

    print()
    print("Per year:")
    py = compute_dollar_per_year(result.trades, dol["per_trade"])
    pos_years = 0
    for y, s in py.items():
        marker = "+" if s["total_dollars"] > 0 else "-"
        if s["total_dollars"] > 0:
            pos_years += 1
        print(f"  {y}: n={s['n']:>3} total=${s['total_dollars']:>10} mean=${s['mean_dollars']:>7} {marker}")
    print(f"  Positive years: {pos_years}/{len(py)}")


if __name__ == "__main__":
    main()
