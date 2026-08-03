"""Gold basis extreme-percentile transplant of Janus's funding-rate signal.

Structural analog: Janus SHORTS crypto perps when funding hits its rolling
95th-percentile extreme. The transplant candidate for gold is the FUTURES
BASIS (GC_close - XAUUSD_spot_close), which measures positioning-driven
premium of paper vs physical. Extreme high basis = crowded long-futures
positioning; extreme low basis (deep discount) = physical stress.

Direction convention:
    basis >= p_high  =>  SHORT gold (crowded premium unwinds)
    basis <= p_low   =>  LONG gold  (deep discount = physical stress reversal)

Pre-registered baseline (LOCKED BEFORE SEEING RESULTS):
    lookback = 180 days (Janus: gold cycles slower than crypto 90d)
    p_high = 95th percentile, p_low = 5th percentile
    cold-start floor: require full 180 days of aligned basis history
    degenerate-distribution guard: require (p95 - p5) >= 0.5 USD/oz
    stop = 2 * ATR(20) on XAUUSD
    time exit = 7 trading days (Janus: 3-7d for gold)
    fill = next-bar open
    costs: slip=0.0002, fee=0.0001 (GC is liquid, thin spread)
    Bonferroni: n_hypotheses = 1 (this is one pre-registered candidate,
    not a family sweep). Robustness runs afterward are informational only.

Ship trigger:
    cost-adjusted mean R with ci_low >= 0.005 (0.5% per trade)
    AND p_adjusted < 0.05
    AND positive years >= 60% of sample

Usage: python scripts/gold_basis_janus_transplant.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.tools.data_loader import load_gold_5m, resample
from research.tools.backtest import (
    backtest, Bar, Strategy, Order, ExitAction, ClosedTrade,
)
from research.tools.bootstrap_stats import evaluate_signal


CONTRACT_SIZE = 100  # GC futures = 100 oz per contract
RT_COST = 3.0


def _ms_to_iso_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def compute_atr(bars: list[Bar], period: int = 20) -> list[Optional[float]]:
    if not bars:
        return []
    trs = [bars[0].high - bars[0].low]
    for i in range(1, len(bars)):
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        )
        trs.append(tr)
    result: list[Optional[float]] = []
    for i in range(len(trs)):
        if i + 1 < period:
            result.append(None)
        else:
            result.append(sum(trs[i + 1 - period : i + 1]) / period)
    return result


def load_gc_daily() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "gc" / "GC_1d.csv", parse_dates=["ts"])
    df["date"] = pd.to_datetime(df["ts"], utc=True).dt.strftime("%Y-%m-%d")
    return df[["date", "close"]].rename(columns={"close": "gc_close"})


def build_basis_series(xau_daily: list[Bar], gc_df: pd.DataFrame) -> pd.DataFrame:
    """Align XAUUSD (spot from Dukascopy) with GC (futures from yfinance) by date."""
    xau_rows = [
        {"date": _ms_to_iso_date(b.timestamp), "xau_close": b.close}
        for b in xau_daily
    ]
    xau_df = pd.DataFrame(xau_rows)
    merged = xau_df.merge(gc_df, on="date", how="inner")
    merged["basis"] = merged["gc_close"] - merged["xau_close"]
    return merged.sort_values("date").reset_index(drop=True)


def compute_basis_signal(
    basis_df: pd.DataFrame,
    lookback: int = 180,
    p_high: float = 0.95,
    p_low: float = 0.05,
    min_spread_usd: float = 0.5,
) -> dict[str, tuple[str, float, float, float]]:
    """Return {date: (direction, basis, p_high_val, p_low_val)}."""
    signals: dict[str, tuple[str, float, float, float]] = {}
    basis = basis_df["basis"].tolist()
    dates = basis_df["date"].tolist()

    for i in range(len(basis)):
        if i + 1 < lookback:
            continue
        window = sorted(basis[i + 1 - lookback : i + 1])
        # linear interpolation percentile
        def pct(p):
            idx = p * (len(window) - 1)
            lo = int(idx); hi = min(lo + 1, len(window) - 1)
            frac = idx - lo
            return window[lo] * (1 - frac) + window[hi] * frac

        ph = pct(p_high); pl = pct(p_low)
        if (ph - pl) < min_spread_usd:
            signals[dates[i]] = ("FLAT", basis[i], ph, pl)
            continue
        b = basis[i]
        if b >= ph:
            signals[dates[i]] = ("SHORT", b, ph, pl)
        elif b <= pl:
            signals[dates[i]] = ("LONG", b, ph, pl)
        else:
            signals[dates[i]] = ("FLAT", b, ph, pl)
    return signals


class BasisStrategy(Strategy):
    def __init__(self, signals, atr_by_date, max_hold_bars=7):
        self.signals = signals
        self.atr = atr_by_date
        self.max_hold_bars = max_hold_bars

    def on_bar_no_position(self, bar, index, history):
        date_str = _ms_to_iso_date(bar.timestamp)
        sig = self.signals.get(date_str)
        if sig is None:
            return None
        direction, basis, ph, pl = sig
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
            metadata={"signal_date": date_str, "basis": basis, "atr": atr},
        )

    def on_bar_with_position(self, bar, index, history, position):
        held = index - position.entered_at_index
        if held >= self.max_hold_bars:
            return ExitAction(reason="time_limit")
        return None


def dollar_pnl(trades: list[ClosedTrade]) -> dict:
    if not trades:
        return {"total": 0.0, "mean": 0.0, "per_trade": []}
    per: list[float] = []
    for t in trades:
        if t.side == "long":
            gross = (t.exit_price - t.entry_price) * CONTRACT_SIZE
        else:
            gross = (t.entry_price - t.exit_price) * CONTRACT_SIZE
        per.append(gross - RT_COST)
    wins = sum(1 for p in per if p > 0)
    return {
        "total": round(sum(per), 0),
        "mean": round(sum(per) / len(per), 2),
        "best": round(max(per), 0),
        "worst": round(min(per), 0),
        "wins": wins,
        "losses": len(per) - wins,
        "wr": round(wins / len(per), 4),
        "per_trade": per,
    }


def per_year(trades, per_trade):
    by = {}
    for t, p in zip(trades, per_trade):
        y = datetime.fromtimestamp(t.entry_time / 1000, tz=timezone.utc).year
        by.setdefault(y, []).append(p)
    return {
        y: {"n": len(v), "total": round(sum(v), 0),
            "mean": round(sum(v) / len(v), 2),
            "wins": sum(1 for p in v if p > 0)}
        for y, v in sorted(by.items())
    }


def run_config(label, xau_daily, atr_by_date, basis_df, slip, fee,
               lookback, p_high, p_low, min_spread, hold, n_hyp):
    print(f"\n--- {label} ---")
    print(f"  lookback={lookback}, p_high={p_high}, p_low={p_low}, "
          f"min_spread=${min_spread:.2f}, hold={hold}")
    sigs = compute_basis_signal(basis_df, lookback, p_high, p_low, min_spread)
    from collections import Counter
    dist = Counter(v[0] for v in sigs.values())
    print(f"  signal dist: {dict(dist)}")

    strat = BasisStrategy(sigs, atr_by_date, hold)
    result = backtest(strat, xau_daily, slippage_pct=slip, fee_pct=fee)
    print(f"  trades: {len(result.trades)}")
    if not result.trades:
        return None

    dol = dollar_pnl(result.trades)
    r_vals = [t.cost_adjusted_r for t in result.trades]
    ev = evaluate_signal(label, r_vals,
                         n_hypotheses_in_batch=n_hyp,
                         ci_lower_threshold=0.005)
    m = result.metrics
    print(f"  R: n={m['n']} WR={m['win_rate']:.3f} mean_r={m['mean_r']:.4f} "
          f"sharpe_pt={m['per_trade_sharpe']:.3f} maxDD={m['max_drawdown_r']:.2f}R")
    print(f"  $: total=${dol['total']:.0f} mean=${dol['mean']:.2f}/tr "
          f"best=${dol['best']:.0f} worst=${dol['worst']:.0f} WR$={dol['wr']:.3f}")
    print(f"  Bootstrap: mean={ev.mean:.4f}R CI=[{ev.ci_low:.4f},{ev.ci_high:.4f}] "
          f"p_adj={ev.p_adjusted:.4f} verdict={ev.verdict}")
    py = per_year(result.trades, dol["per_trade"])
    pos = sum(1 for _, s in py.items() if s["total"] > 0)
    print(f"  Positive years: {pos}/{len(py)}")
    return {"metrics": m, "dollars": dol, "eval": ev, "per_year": py}


def main():
    START = "2010-01-01"
    END = "2026-06-30"

    print(f"Loading XAUUSD 5m {START} to {END}...")
    xau_5m = load_gold_5m(start=START, end=END)
    xau_daily = resample(xau_5m, target_minutes=1440)
    print(f"  {len(xau_daily)} XAUUSD daily bars")

    print("Loading GC=F daily (local CSV)...")
    gc_df = load_gc_daily()
    print(f"  {len(gc_df)} GC daily bars, {gc_df['date'].min()} to {gc_df['date'].max()}")

    print("Building basis series (GC - XAUUSD aligned by date)...")
    basis_df = build_basis_series(xau_daily, gc_df)
    print(f"  {len(basis_df)} aligned days")
    print(f"  basis stats: mean={basis_df['basis'].mean():.2f}, "
          f"std={basis_df['basis'].std():.2f}, "
          f"min={basis_df['basis'].min():.2f}, max={basis_df['basis'].max():.2f}")
    print(f"  basis percentiles: p5={basis_df['basis'].quantile(0.05):.2f}, "
          f"p50={basis_df['basis'].quantile(0.5):.2f}, "
          f"p95={basis_df['basis'].quantile(0.95):.2f}")

    print("Computing XAUUSD ATR(20)...")
    atr = compute_atr(xau_daily, 20)
    atr_by_date = {_ms_to_iso_date(b.timestamp): a
                   for b, a in zip(xau_daily, atr) if a is not None}

    slip, fee = 0.0002, 0.0001

    print("\n" + "=" * 70)
    print("GOLD BASIS — JANUS FUNDING-EXTREME TRANSPLANT")
    print("=" * 70)

    print("\n### PRE-REGISTERED BASELINE (Bonferroni n=1) ###")
    run_config("baseline_lb180_p95_5_hold7", xau_daily, atr_by_date, basis_df,
               slip, fee, 180, 0.95, 0.05, 0.5, 7, 1)

    print("\n\n### POST-HOC ROBUSTNESS (informational only) ###")
    for lb in [90, 365]:
        run_config(f"lookback_{lb}", xau_daily, atr_by_date, basis_df,
                   slip, fee, lb, 0.95, 0.05, 0.5, 7, 1)
    for ph, pl in [(0.90, 0.10), (0.975, 0.025)]:
        run_config(f"pct_{ph}_{pl}", xau_daily, atr_by_date, basis_df,
                   slip, fee, 180, ph, pl, 0.5, 7, 1)
    for h in [3, 15]:
        run_config(f"hold_{h}", xau_daily, atr_by_date, basis_df,
                   slip, fee, 180, 0.95, 0.05, 0.5, h, 1)

    print("\n\n### DIRECTION SPLIT (informational only) ###")
    # Long-only and short-only cuts
    sigs_full = compute_basis_signal(basis_df, 180, 0.95, 0.05, 0.5)
    sigs_long = {d: v if v[0] == "LONG" else ("FLAT",) + v[1:]
                 for d, v in sigs_full.items()}
    sigs_short = {d: v if v[0] == "SHORT" else ("FLAT",) + v[1:]
                  for d, v in sigs_full.items()}

    for label, sig_subset in [("long_only", sigs_long), ("short_only", sigs_short)]:
        strat = BasisStrategy(sig_subset, atr_by_date, 7)
        result = backtest(strat, xau_daily, slippage_pct=slip, fee_pct=fee)
        if not result.trades:
            print(f"  {label}: 0 trades"); continue
        r_vals = [t.cost_adjusted_r for t in result.trades]
        ev = evaluate_signal(label, r_vals, n_hypotheses_in_batch=1,
                             ci_lower_threshold=0.005)
        dol = dollar_pnl(result.trades)
        print(f"  {label}: n={len(result.trades)} mean_r={ev.mean:.4f} "
              f"CI=[{ev.ci_low:.4f},{ev.ci_high:.4f}] verdict={ev.verdict} "
              f"total=${dol['total']:.0f}")


if __name__ == "__main__":
    main()
