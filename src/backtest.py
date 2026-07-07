"""Minimal cost-aware backtester for event-conditioned GC trades.

Model assumptions for GC futures (realistic — see audit 2026-07-07):
  contract_size : 100 troy oz
  tick_size     : 0.10 USD/oz  ($10 P&L per tick)
  spread_cost   : 1 tick RT = $0.10 per oz round-trip (bid-ask on entry)
  slippage      : 1 tick RT = $0.10 per oz round-trip (stop/limit fill drift)
  commission    : $4 round-trip = $0.04 per oz round-trip
  Total RT cost : $0.24 per oz = $24 per contract

Position semantics:
  direction = +1 -> long  (enter at entry_price, exit at exit_price)
  direction = -1 -> short (enter at entry_price, exit at exit_price)
  P&L per contract = (exit - entry) * direction * 100 - cost_per_contract
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "backtests"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Cost model -----------------------------------------------------------------
CONTRACT_SIZE = 100  # oz per GC contract
# Realistic RT: 1-tick spread ($0.10) + 1-tick slippage ($0.10) + commission ($0.04)
# = $0.24/oz RT = $24/contract. Prior value of $0.19 was optimistic (audit 2026-07-07).
RT_COST_PER_OZ = 0.24
RT_COST_PER_CONTRACT = RT_COST_PER_OZ * CONTRACT_SIZE  # = $24


@dataclass
class Trade:
    event_ts: pd.Timestamp
    event_type: str
    direction: int
    entry_ts: pd.Timestamp
    entry_price: float
    exit_ts: pd.Timestamp
    exit_price: float
    bars_held: int
    surprise_z: float
    gross_pnl: float        # per contract, before costs
    cost: float
    net_pnl: float          # per contract, after costs
    ret_pct: float          # gross return % on entry price

    def as_row(self):
        return {**self.__dict__}


@dataclass
class BacktestConfig:
    hold_bars: int = 1
    cost_per_contract: float = RT_COST_PER_CONTRACT
    enter_offset_bars: int = 1   # 1 = enter at OPEN of bar after event bar
    require_dir: bool = True     # only trade when expected_dir != 0
    surprise_z_min: float = 0.0  # |z| threshold; 0 means take all
    event_filter: tuple = None   # tuple of event types to include; None = all


def _floor_to_bar(ts: pd.Timestamp, freq: pd.Timedelta) -> pd.Timestamp:
    return pd.Timestamp(ts).floor(freq)


def run(bars: pd.DataFrame, events: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    """Run MERS-style backtest.

    bars   : DatetimeIndex (UTC), columns: open/high/low/close
    events : columns ts_utc, event, expected_dir, surprise_z, ...
    """
    bars = bars.sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")

    # Infer bar frequency
    deltas = np.diff(bars.index.values)
    freq = pd.Timedelta(np.median(deltas))

    trades = []
    for _, ev in events.iterrows():
        if cfg.require_dir and (ev["expected_dir"] == 0 or pd.isna(ev["expected_dir"])):
            continue
        if cfg.event_filter and ev["event"] not in cfg.event_filter:
            continue
        if pd.notna(ev.get("surprise_z")) and abs(float(ev["surprise_z"])) < cfg.surprise_z_min:
            continue

        ev_ts = pd.Timestamp(ev["ts_utc"]).tz_convert("UTC")
        bar_ts = _floor_to_bar(ev_ts, freq)

        # Need: event bar + enter_offset bars exist + hold_bars more bars exist
        if bar_ts not in bars.index:
            continue
        idx = bars.index.get_loc(bar_ts)
        entry_idx = idx + cfg.enter_offset_bars
        exit_idx = entry_idx + cfg.hold_bars
        if exit_idx >= len(bars):
            continue

        entry_bar = bars.iloc[entry_idx]
        exit_bar = bars.iloc[exit_idx]
        direction = int(ev["expected_dir"])

        gross_pnl = (exit_bar["close"] - entry_bar["open"]) * direction * CONTRACT_SIZE
        net_pnl = gross_pnl - cfg.cost_per_contract
        ret_pct = (exit_bar["close"] - entry_bar["open"]) / entry_bar["open"] * 100 * direction

        trades.append(Trade(
            event_ts=ev_ts,
            event_type=ev["event"],
            direction=direction,
            entry_ts=bars.index[entry_idx],
            entry_price=float(entry_bar["open"]),
            exit_ts=bars.index[exit_idx],
            exit_price=float(exit_bar["close"]),
            bars_held=cfg.hold_bars,
            surprise_z=float(ev["surprise_z"]) if pd.notna(ev["surprise_z"]) else np.nan,
            gross_pnl=float(gross_pnl),
            cost=cfg.cost_per_contract,
            net_pnl=float(net_pnl),
            ret_pct=float(ret_pct),
        ).as_row())

    return pd.DataFrame(trades)


def summarize(trades: pd.DataFrame, label: str = "") -> dict:
    if trades.empty:
        return {"label": label, "n": 0}
    g = trades["gross_pnl"]
    n = trades["net_pnl"]
    wins = (n > 0).sum()
    losses = (n <= 0).sum()
    sharpe = (n.mean() / n.std() * np.sqrt(252)) if n.std() > 0 else np.nan
    profit_factor = (n[n > 0].sum() / -n[n < 0].sum()) if (n < 0).any() else np.inf
    return {
        "label": label,
        "n": len(trades),
        "win_rate": wins / len(trades),
        "mean_net_pnl": n.mean(),
        "median_net_pnl": n.median(),
        "total_net_pnl": n.sum(),
        "mean_gross_pnl": g.mean(),
        "std_net_pnl": n.std(),
        "sharpe_per_trade": sharpe,
        "max_win": n.max(),
        "max_loss": n.min(),
        "profit_factor": profit_factor,
    }


def print_summary(summary: dict):
    if summary["n"] == 0:
        print(f"  [{summary['label']}] no trades")
        return
    print(f"  [{summary['label']:30s}] n={summary['n']:4d} "
          f"win%={summary['win_rate']*100:5.1f} "
          f"mean_net=${summary['mean_net_pnl']:+8.2f} "
          f"total=${summary['total_net_pnl']:+10.0f} "
          f"sharpe={summary['sharpe_per_trade']:+.2f} "
          f"pf={summary['profit_factor']:.2f}")
