"""Property-based tests for strategy_engine filters via hypothesis.

Fuzz the filter surface to catch edge cases the unit tests miss.
Properties expressed as invariants:
  - filter_or_atr: skip iff ratio violates configured max/min/deadzone
  - filter_trend: skip iff slope==0 AND require_trend
  - evaluate_session: would_take implies entry/target/stop set; skip implies None
  - Direction always matches sign of slope (non-flat case)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from strategy_engine import (  # noqa: E402
    Direction,
    OrContext,
    RegimeContext,
    SessionConfig,
    evaluate_session,
    filter_or_atr,
    filter_trend,
)

# Use LON open (avoid London fix window at 14:00 UTC)
_SESSION_OPEN = pd.Timestamp("2026-07-13 07:00", tz="UTC")
_OR_CLOSE = pd.Timestamp("2026-07-13 07:30", tz="UTC")

_regime = RegimeContext(as_of_utc=_OR_CLOSE)


def _mk_ctx(or_range: float, atr: float, slope: float) -> OrContext:
    or_low = 4000.0
    or_high = or_low + or_range
    return OrContext(
        session_open_utc=_SESSION_OPEN,
        or_close_utc=_OR_CLOSE,
        or_high=or_high, or_low=or_low, or_range=or_range,
        atr_at_close=atr, slope_at_close=slope,
        or_bars_df=pd.DataFrame(),
    )


class TestOrAtrProperties:
    @given(
        or_range=st.floats(min_value=0.01, max_value=1000, allow_nan=False),
        atr=st.floats(min_value=0.01, max_value=100, allow_nan=False),
        or_max=st.floats(min_value=0.1, max_value=10, allow_nan=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_max_gate_matches_ratio(self, or_range, atr, or_max):
        """filter_or_atr with or_atr_max=X skips iff ratio > X."""
        cfg = SessionConfig(name="TEST", or_atr_max=or_max)
        ctx = _mk_ctx(or_range, atr, slope=1.0)
        result = filter_or_atr(cfg, ctx, _regime)
        ratio = or_range / atr
        if ratio > or_max:
            assert result is not None and "max" in result
        else:
            assert result is None

    @given(
        or_range=st.floats(min_value=0.01, max_value=1000, allow_nan=False),
        atr=st.floats(min_value=0.01, max_value=100, allow_nan=False),
        or_min=st.floats(min_value=0.1, max_value=10, allow_nan=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_min_gate_matches_ratio(self, or_range, atr, or_min):
        cfg = SessionConfig(name="TEST", or_atr_min=or_min)
        ctx = _mk_ctx(or_range, atr, slope=1.0)
        result = filter_or_atr(cfg, ctx, _regime)
        ratio = or_range / atr
        if ratio < or_min:
            assert result is not None and "min" in result
        else:
            assert result is None

    @given(
        or_range=st.floats(min_value=0.01, max_value=1000, allow_nan=False),
        atr=st.floats(min_value=0.01, max_value=100, allow_nan=False),
        dz_lo=st.floats(min_value=0.1, max_value=5, allow_nan=False),
        dz_hi=st.floats(min_value=0.1, max_value=5, allow_nan=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_deadzone_gate(self, or_range, atr, dz_lo, dz_hi):
        assume(dz_lo < dz_hi)
        cfg = SessionConfig(name="TEST", or_atr_deadzone=(dz_lo, dz_hi))
        ctx = _mk_ctx(or_range, atr, slope=1.0)
        result = filter_or_atr(cfg, ctx, _regime)
        ratio = or_range / atr
        if dz_lo <= ratio <= dz_hi:
            assert result is not None and "dead zone" in result
        else:
            assert result is None

    def test_no_gate_configured_never_skips(self):
        cfg = SessionConfig(name="TEST")  # all Nones
        for ratio in [0.001, 0.5, 1.0, 5.0, 1000]:
            ctx = _mk_ctx(or_range=ratio * 10, atr=10, slope=1)
            assert filter_or_atr(cfg, ctx, _regime) is None


class TestTrendProperties:
    @given(slope=st.floats(min_value=-100, max_value=100, allow_nan=False))
    @settings(max_examples=100, deadline=None)
    def test_require_trend_iff_nonzero(self, slope):
        cfg = SessionConfig(name="TEST", require_trend=True)
        ctx = _mk_ctx(or_range=10, atr=5, slope=slope)
        result = filter_trend(cfg, ctx, _regime)
        if slope == 0:
            assert result == "trend flat"
        else:
            assert result is None

    @given(slope=st.floats(min_value=-100, max_value=100, allow_nan=False))
    @settings(max_examples=100, deadline=None)
    def test_require_trend_off_never_skips(self, slope):
        cfg = SessionConfig(name="TEST", require_trend=False)
        ctx = _mk_ctx(or_range=10, atr=5, slope=slope)
        assert filter_trend(cfg, ctx, _regime) is None


class TestEvaluateSessionProperties:
    @given(
        or_range=st.floats(min_value=0.1, max_value=200, allow_nan=False),
        atr=st.floats(min_value=0.1, max_value=50, allow_nan=False),
        slope=st.floats(min_value=-50, max_value=50, allow_nan=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_would_take_implies_geometry_set(self, or_range, atr, slope):
        """If would_take, entry/target/stop are all non-None."""
        cfg = SessionConfig(name="TEST", or_atr_max=10.0, require_trend=True)
        ctx = _mk_ctx(or_range, atr, slope)
        d = evaluate_session(cfg, ctx, _regime)
        if d.would_take:
            assert d.entry_price is not None
            assert d.target_price is not None
            assert d.stop_price is not None
        else:
            assert d.entry_price is None
            assert d.target_price is None
            assert d.stop_price is None

    @given(
        or_range=st.floats(min_value=0.1, max_value=200, allow_nan=False),
        atr=st.floats(min_value=0.1, max_value=50, allow_nan=False),
        slope=st.floats(min_value=-50, max_value=50, allow_nan=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_direction_matches_slope_sign(self, or_range, atr, slope):
        cfg = SessionConfig(name="TEST", require_trend=False)  # avoid FLAT branch
        ctx = _mk_ctx(or_range, atr, slope)
        d = evaluate_session(cfg, ctx, _regime)
        if slope > 0:
            assert d.direction == Direction.LONG
        elif slope < 0:
            assert d.direction == Direction.SHORT
        else:
            assert d.direction == Direction.FLAT

    @given(
        or_range=st.floats(min_value=0.1, max_value=200, allow_nan=False),
        atr=st.floats(min_value=0.1, max_value=50, allow_nan=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_long_entry_at_or_high(self, or_range, atr):
        cfg = SessionConfig(name="TEST", or_atr_max=10.0, require_trend=True)
        ctx = _mk_ctx(or_range, atr, slope=1.0)
        d = evaluate_session(cfg, ctx, _regime)
        if d.would_take:
            assert d.direction == Direction.LONG
            assert d.entry_price == ctx.or_high
            assert d.stop_price < d.entry_price
            assert d.target_price > d.entry_price

    @given(
        or_range=st.floats(min_value=0.1, max_value=200, allow_nan=False),
        atr=st.floats(min_value=0.1, max_value=50, allow_nan=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_short_entry_at_or_low(self, or_range, atr):
        cfg = SessionConfig(name="TEST", or_atr_max=10.0, require_trend=True)
        ctx = _mk_ctx(or_range, atr, slope=-1.0)
        d = evaluate_session(cfg, ctx, _regime)
        if d.would_take:
            assert d.direction == Direction.SHORT
            assert d.entry_price == ctx.or_low
            assert d.stop_price > d.entry_price
            assert d.target_price < d.entry_price
