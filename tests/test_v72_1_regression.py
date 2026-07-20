"""Regression tests: lock in v7.2.1 backtest numbers as the golden reference.

Fails loudly if strategy code is accidentally modified in a way that changes
the shipped-backtest results. Combines fast config assertions (millisecond
scale) with a full-window Phase-7-equivalent backtest (30s scale).

Run:
    python tests/test_v72_1_regression.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


# =============================================================================
# Fast: SESSION_CONFIG contract
# =============================================================================

def test_session_config_locked():
    """Path Y baseline (2026-07-13): all sessions use or_vs_atr_max=2.0.
    v7.1 min/deadzone gates never shipped to live per commit history;
    backtest config synced to match live behavior.
    """
    from edge_session_orb_v7_final import SESSION_CONFIG, TP_MULT_DEFAULT

    # NY: Path Y - or_vs_atr_max=2.0 (no min gate, tp reverted 1.0->1.5)
    ny = SESSION_CONFIG["NY"]
    assert ny["use_or_filter"] is True, "NY OR filter must be ON"
    assert ny["or_vs_atr_max"] == 2.0, f"NY or_vs_atr_max expected 2.0, got {ny.get('or_vs_atr_max')}"
    assert "or_vs_atr_min" not in ny, "Path Y: NY should not have or_vs_atr_min"
    assert ny["tp_mult"] == 1.5, f"NY tp_mult expected 1.5 (Path Y revert), got {ny['tp_mult']}"

    # ASIA: Path Y - or_vs_atr_max=2.0 (no deadzone)
    asia = SESSION_CONFIG["ASIA"]
    assert asia["or_vs_atr_max"] == 2.0
    assert "or_atr_deadzone" not in asia, "Path Y: ASIA should not have or_atr_deadzone"
    assert asia["tp_mult"] == 1.5

    # LON unchanged since v7 baseline
    lon = SESSION_CONFIG["LON"]
    assert lon["or_vs_atr_max"] == 2.0
    assert lon["fixed_stop_price"] == 13.0
    assert lon["stop_mode"] == "fixed"
    assert lon["target_mode"] == "stop_x_tp"
    assert lon["tp_mult"] == 1.5

    assert TP_MULT_DEFAULT == 1.5
    print("  test_session_config_locked PASSED (Path Y baseline)")


def test_run_orb_v7_max_hold_v72_1():
    """v7.2.1 default max_hold is 36 bars = 180min."""
    import inspect
    from edge_session_orb_v7_final import run_orb_v7
    sig = inspect.signature(run_orb_v7)
    max_hold = sig.parameters["max_hold"].default
    assert max_hold == 36, f"max_hold expected 36 (180min = v7.2.1), got {max_hold}"
    print("  test_run_orb_v7_max_hold_v72_1 PASSED")


def test_backtest_cost_model_locked():
    """B4 cost model must remain at $24 (honest realistic RT)."""
    from backtest import RT_COST_PER_OZ, RT_COST_PER_CONTRACT
    assert RT_COST_PER_OZ == 0.24, f"RT_COST_PER_OZ regressed: {RT_COST_PER_OZ}"
    assert RT_COST_PER_CONTRACT == 24.0
    from position_sizing import recommend  # noqa
    # inline check on the sizing constants
    src = (ROOT / "src" / "position_sizing.py").read_text()
    assert "rt_cost = 24 if vehicle.name" in src, "position_sizing MGC/GC cost regressed"
    print("  test_backtest_cost_model_locked PASSED")


def test_dispatch_orb_hold_v72_1():
    """dispatch_orb HOLD constant must match strategy's max_hold (both 36)."""
    import dispatch_orb
    assert dispatch_orb.HOLD == 36, f"dispatch_orb.HOLD regressed: {dispatch_orb.HOLD}"
    print("  test_dispatch_orb_hold_v72_1 PASSED")


# =============================================================================
# Slow: full-window backtest (Phase-7 equivalent)
# =============================================================================

# Path Y baseline (2026-07-13): synced backtest config to live-actual filter.
# n dropped from v7.2.1's 52 (phantom-v7.1 numbers) to Path Y's 25 (honest).
# Wide tolerances because news filter application is bar-timing-sensitive.
# Data-window cap: golden pinned against bars <= 2026-07-08. Cap in the test
# keeps the golden invariant to future data accumulation.
V721_GOLDEN = {
    "n": 25,
    "wins": 13,
    "win_pct_pm_tol": (50.0, 55.0),
    "total_usd_min": 8000,
    "total_usd_max": 14000,
    "mean_per_trade_min": 350,
    "mean_per_trade_max": 500,
    "data_end_utc": "2026-07-09 23:59:59",
}


def test_v72_1_full_backtest_golden():
    """Run full Phase-7-equivalent backtest, compare to shipped golden numbers.
    Slow (~30s) but catches any strategy-code change that alters shipping behavior."""
    import pandas as pd
    from data_gc import load as gc_load
    from edge_session_orb import session_utc_time_on
    from edge_session_orb_v7_final import run_orb_v7, SESSION_CONFIG
    from datetime import datetime
    import pytz

    bars = gc_load('5m').sort_index()
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize('UTC')
    # Cap bars at golden pin-date so the assertion is invariant to data drift
    cap = pd.Timestamp(V721_GOLDEN["data_end_utc"], tz="UTC")
    bars = bars[bars.index <= cap]

    frames = []
    for sess_name in SESSION_CONFIG:
        sess_t = session_utc_time_on(datetime.now(pytz.UTC).date(), sess_name)
        df = run_orb_v7(bars, sess_t, sess_name)
        df['session'] = sess_name
        if not df.empty:
            frames.append(df)
    took = pd.concat(frames, ignore_index=True)
    took = took[took['took_trade'] == True]

    n = len(took)
    wins = int((took['net_pnl'] > 0).sum())
    win_pct = wins / n * 100 if n else 0
    total = float(took['net_pnl'].sum())
    mean = float(took['net_pnl'].mean()) if n else 0

    assert n == V721_GOLDEN["n"], f"trade count regressed: {n} vs {V721_GOLDEN['n']}"
    assert wins == V721_GOLDEN["wins"], f"win count regressed: {wins} vs {V721_GOLDEN['wins']}"
    assert V721_GOLDEN["win_pct_pm_tol"][0] <= win_pct <= V721_GOLDEN["win_pct_pm_tol"][1], \
        f"win rate regressed: {win_pct:.1f}%"
    assert V721_GOLDEN["total_usd_min"] <= total <= V721_GOLDEN["total_usd_max"], \
        f"total P&L regressed: ${total:.0f}"
    assert V721_GOLDEN["mean_per_trade_min"] <= mean <= V721_GOLDEN["mean_per_trade_max"], \
        f"mean/trade regressed: ${mean:.0f}"

    print(f"  test_v72_1_full_backtest_golden PASSED  "
          f"(n={n}, win={win_pct:.1f}%, mean=${mean:.0f}, total=${total:.0f})")


if __name__ == "__main__":
    fast = [
        test_session_config_locked,
        test_run_orb_v7_max_hold_v72_1,
        test_backtest_cost_model_locked,
        test_dispatch_orb_hold_v72_1,
    ]
    slow = [
        test_v72_1_full_backtest_golden,
    ]
    failed = 0
    print("== Fast regression tests ==")
    for t in fast:
        try:
            t()
        except AssertionError as e:
            print(f"  {t.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  {t.__name__} ERROR: {type(e).__name__}: {e}")
            failed += 1
    print("\n== Slow (golden backtest) ==")
    for t in slow:
        try:
            t()
        except AssertionError as e:
            print(f"  {t.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  {t.__name__} ERROR: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(fast)+len(slow)-failed}/{len(fast)+len(slow)} regression tests passed")
    sys.exit(0 if failed == 0 else 1)
