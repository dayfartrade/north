"""Phase 8.1 test-harness sketch for strategy_engine.

Not a full test suite yet — this is the DESIGN of what tests we need.
Actual test-data fixtures come in Phase 8.2.

Run: `pytest tests/test_strategy_engine.py -v`
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.strategy_engine import (
    Decision,
    Direction,
    OrContext,
    RegimeContext,
    SessionConfig,
    SESSION_CONFIGS_V8_INITIAL,
    evaluate_session,
    filter_or_atr,
    filter_trend,
)


# ---------------------------------------------------------------------------
# Helper: build test contexts
# ---------------------------------------------------------------------------

def _regime(**overrides) -> RegimeContext:
    base = dict(as_of_utc=pd.Timestamp("2026-07-13 14:00", tz="UTC"))
    base.update(overrides)
    return RegimeContext(**base)


def _or_ctx(or_high=4100.0, or_low=4090.0, atr=5.0, slope=1.0) -> OrContext:
    return OrContext(
        session_open_utc=pd.Timestamp("2026-07-13 13:30", tz="UTC"),
        or_close_utc=pd.Timestamp("2026-07-13 14:00", tz="UTC"),
        or_high=or_high,
        or_low=or_low,
        or_range=or_high - or_low,
        atr_at_close=atr,
        slope_at_close=slope,
        or_bars_df=pd.DataFrame(),
    )


# ---------------------------------------------------------------------------
# UNIT TESTS — one per filter
# ---------------------------------------------------------------------------

class TestFilterOrAtr:
    def test_or_atr_max_pass(self):
        """or_atr_max=2.0, ratio=1.5 → pass."""
        cfg = SessionConfig(name="LON", or_atr_max=2.0)
        ctx = _or_ctx(or_high=100, or_low=90, atr=8.0)  # ratio 1.25
        assert filter_or_atr(cfg, ctx, _regime()) is None

    def test_or_atr_max_skip(self):
        """or_atr_max=2.0, ratio=3.0 → skip."""
        cfg = SessionConfig(name="LON", or_atr_max=2.0)
        ctx = _or_ctx(or_high=100, or_low=90, atr=3.0)  # ratio 3.33
        assert "> max 2.0" in filter_or_atr(cfg, ctx, _regime())

    def test_or_atr_min_skip(self):
        """or_atr_min=2.5, ratio=1.5 → skip."""
        cfg = SessionConfig(name="NY-v71", or_atr_min=2.5)
        ctx = _or_ctx(or_high=100, or_low=90, atr=8.0)  # ratio 1.25
        assert "< min 2.5" in filter_or_atr(cfg, ctx, _regime())

    def test_or_atr_deadzone_skip(self):
        """deadzone (2.0, 2.5), ratio=2.25 → skip."""
        cfg = SessionConfig(name="ASIA-v71", or_atr_deadzone=(2.0, 2.5))
        ctx = _or_ctx(or_high=100, or_low=90, atr=4.5)  # ratio 2.22
        assert "dead zone" in filter_or_atr(cfg, ctx, _regime())

    def test_or_atr_none_no_gate(self):
        """No OR/ATR keys set → filter passes always."""
        cfg = SessionConfig(name="TEST")  # all Optional keys default None
        ctx = _or_ctx(or_high=100, or_low=90, atr=0.1)  # ratio 100
        assert filter_or_atr(cfg, ctx, _regime()) is None


class TestFilterTrend:
    def test_flat_trend_skips(self):
        cfg = SessionConfig(name="LON", require_trend=True)
        ctx = _or_ctx(slope=0)
        assert filter_trend(cfg, ctx, _regime()) == "trend flat"

    def test_non_flat_passes(self):
        cfg = SessionConfig(name="LON", require_trend=True)
        assert filter_trend(cfg, _or_ctx(slope=1), _regime()) is None
        assert filter_trend(cfg, _or_ctx(slope=-1), _regime()) is None

    def test_require_trend_off(self):
        cfg = SessionConfig(name="LON", require_trend=False)
        ctx = _or_ctx(slope=0)
        assert filter_trend(cfg, ctx, _regime()) is None


# ---------------------------------------------------------------------------
# INTEGRATION TESTS — evaluate_session end-to-end
# ---------------------------------------------------------------------------

class TestEvaluateSession:
    def test_pass_takes_long(self):
        cfg = SESSION_CONFIGS_V8_INITIAL["LON"]
        ctx = _or_ctx(or_high=100, or_low=90, atr=8.0, slope=1.0)  # ratio 1.25 < 2.0
        decision = evaluate_session(cfg, ctx, _regime())
        assert decision.would_take
        assert decision.direction == Direction.LONG
        assert decision.entry_price == 100
        assert decision.stop_price == 100 - 13  # fixed stop $13 for LON

    def test_pass_takes_short(self):
        cfg = SESSION_CONFIGS_V8_INITIAL["NY"]
        ctx = _or_ctx(or_high=100, or_low=90, atr=8.0, slope=-1.0)
        decision = evaluate_session(cfg, ctx, _regime())
        assert decision.would_take
        assert decision.direction == Direction.SHORT
        assert decision.entry_price == 90

    def test_skip_or_atr(self):
        cfg = SESSION_CONFIGS_V8_INITIAL["NY"]
        ctx = _or_ctx(or_high=100, or_low=50, atr=8.0)  # ratio 6.25 > 2.0
        decision = evaluate_session(cfg, ctx, _regime())
        assert not decision.would_take
        assert any("> max 2.0" in r for r in decision.would_skip_reasons)

    def test_skip_flat_trend(self):
        cfg = SESSION_CONFIGS_V8_INITIAL["LON"]
        ctx = _or_ctx(or_high=100, or_low=90, atr=8.0, slope=0.0)
        decision = evaluate_session(cfg, ctx, _regime())
        assert not decision.would_take
        assert "trend flat" in decision.would_skip_reasons


# ---------------------------------------------------------------------------
# GOLDEN-FILE TESTS — Phase 8.2 populates these
# ---------------------------------------------------------------------------

class TestGoldenFiles:
    """Replays specific historical trades from orb_forward_log.csv through
    the v8 strategy_engine and asserts the decision matches what was
    recorded at trade time (or a documented behavior change).

    Each entry pins one trade's decision. If any v8 change flips this
    without a matching documented rationale, the test fails.

    Phase 8.2 will populate golden_trades.json fixtures.
    """

    @pytest.mark.xfail(reason="Phase 8.2 populates fixtures")
    def test_2026_07_13_ny_skip_or_atr(self):
        """Today's NY: OR 21.90, ATR 5.32, ratio 4.12. Path Y config skips (>2.0 max)."""
        cfg = SESSION_CONFIGS_V8_INITIAL["NY"]
        ctx = _or_ctx(or_high=4071.80, or_low=4049.90, atr=5.32, slope=-11.94)
        decision = evaluate_session(cfg, ctx, _regime())
        assert not decision.would_take
        assert any("> max 2.0" in r for r in decision.would_skip_reasons)


# ---------------------------------------------------------------------------
# PROPERTY-BASED TESTS — Phase 8.2 adds hypothesis
# ---------------------------------------------------------------------------

class TestProperties:
    """Property tests over the filter surface. Phase 8.2 adds `hypothesis` lib.

    Examples:
      - For any cfg with or_atr_max=X, evaluate_session skip <=> OR/ATR > X
      - Direction is always sign of slope (when not flat)
      - would_take implies entry/target/stop all set; would_skip implies all None
    """
    pass
