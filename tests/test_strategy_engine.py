"""Phase 8.1 test-harness sketch for strategy_engine.

Not a full test suite yet — this is the DESIGN of what tests we need.
Actual test-data fixtures come in Phase 8.2.

Run: `pytest tests/test_strategy_engine.py -v`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Match production import path: strategy_engine runs with src/ on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from strategy_engine import (  # noqa: E402
    Decision,
    Direction,
    OrContext,
    RegimeContext,
    SessionConfig,
    SESSION_CONFIGS_V8_INITIAL,
    SESSION_CONFIGS_V9_Z,
    evaluate_session,
    filter_daily_slope_consistency,
    filter_or_atr,
    filter_path_z,
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
    # Uses LON open (07:00 UTC) to avoid London-fix window firing on the
    # NY session's OR close (14:00 UTC = 15:00 LT DST).
    return OrContext(
        session_open_utc=pd.Timestamp("2026-07-13 07:00", tz="UTC"),
        or_close_utc=pd.Timestamp("2026-07-13 07:30", tz="UTC"),
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


class TestFilterDailySlopeConsistency:
    """Pre-reg: docs/experiments/2026-07-18_daily_slope_consistency_shadow.md"""

    def _cfg_on(self) -> SessionConfig:
        return SessionConfig(name="NY", require_daily_slope_alignment=True)

    def test_shadow_off_by_default(self):
        cfg = SessionConfig(name="NY")
        ctx = _or_ctx(slope=+1.0)
        regime = _regime(daily_20d_slope=-5.0)
        assert filter_daily_slope_consistency(cfg, ctx, regime) is None

    def test_flag_on_long_counter_downtrend_skips(self):
        cfg = self._cfg_on()
        ctx = _or_ctx(slope=+1.0)  # LONG
        regime = _regime(daily_20d_slope=-5.0)
        r = filter_daily_slope_consistency(cfg, ctx, regime)
        assert r is not None and "opposes" in r and "LONG" in r

    def test_flag_on_short_aligned_downtrend_passes(self):
        cfg = self._cfg_on()
        ctx = _or_ctx(slope=-1.0)  # SHORT
        regime = _regime(daily_20d_slope=-5.0)
        assert filter_daily_slope_consistency(cfg, ctx, regime) is None

    def test_flag_on_long_aligned_uptrend_passes(self):
        cfg = self._cfg_on()
        ctx = _or_ctx(slope=+1.0)
        regime = _regime(daily_20d_slope=+5.0)
        assert filter_daily_slope_consistency(cfg, ctx, regime) is None

    def test_missing_daily_slope_passes(self):
        cfg = self._cfg_on()
        ctx = _or_ctx(slope=+1.0)
        regime = _regime(daily_20d_slope=None)
        assert filter_daily_slope_consistency(cfg, ctx, regime) is None

    def test_flat_intraday_slope_passes(self):
        """Flat trend is handled by filter_trend, not this one."""
        cfg = self._cfg_on()
        ctx = _or_ctx(slope=0.0)
        regime = _regime(daily_20d_slope=-5.0)
        assert filter_daily_slope_consistency(cfg, ctx, regime) is None

    def test_zero_daily_slope_passes(self):
        cfg = self._cfg_on()
        ctx = _or_ctx(slope=+1.0)
        regime = _regime(daily_20d_slope=0.0)
        assert filter_daily_slope_consistency(cfg, ctx, regime) is None


class TestFilterPathZ:
    """Pre-reg: docs/experiments/2026-07-20_path_z_ny_short_prereg.md

    Path Z fires ONLY when all 4 conditions hold:
      1. session == "NY"
      2. slope_at_close < 0 (SHORT direction)
      3. efficiency_ratio_5m_20 < 0.30 (noisy prior 20 5m bars)
      4. session_open_utc.weekday() in {0,1,2} (Mon/Tue/Wed)
    """

    NY_MON = pd.Timestamp("2026-07-13 13:00", tz="UTC")   # Monday 13:00 UTC
    NY_THU = pd.Timestamp("2026-07-16 13:00", tz="UTC")   # Thursday
    LON_MON = pd.Timestamp("2026-07-13 07:00", tz="UTC")  # Monday London

    def _cfg_on(self, name: str = "NY") -> SessionConfig:
        return SessionConfig(name=name, require_path_z=True)

    def _ctx(self, session_open, slope: float) -> OrContext:
        return OrContext(
            session_open_utc=session_open,
            or_close_utc=session_open + pd.Timedelta(minutes=30),
            or_high=4100.0, or_low=4090.0, or_range=10.0,
            atr_at_close=5.0, slope_at_close=slope,
            or_bars_df=pd.DataFrame(),
        )

    def test_shadow_off_by_default(self):
        cfg = SessionConfig(name="NY")
        ctx = self._ctx(self.NY_MON, slope=-1.0)
        regime = _regime(efficiency_ratio_5m_20=0.20)
        assert filter_path_z(cfg, ctx, regime) is None

    def test_all_conditions_met_passes(self):
        """NY + SHORT + Low-ER + Monday = take."""
        cfg = self._cfg_on("NY")
        ctx = self._ctx(self.NY_MON, slope=-1.0)
        regime = _regime(efficiency_ratio_5m_20=0.20)
        assert filter_path_z(cfg, ctx, regime) is None

    def test_wrong_session_skips(self):
        cfg = self._cfg_on("LON")
        ctx = self._ctx(self.LON_MON, slope=-1.0)
        regime = _regime(efficiency_ratio_5m_20=0.20)
        r = filter_path_z(cfg, ctx, regime)
        assert r is not None and "LON" in r

    def test_long_direction_skips(self):
        cfg = self._cfg_on("NY")
        ctx = self._ctx(self.NY_MON, slope=+1.0)  # LONG
        regime = _regime(efficiency_ratio_5m_20=0.20)
        r = filter_path_z(cfg, ctx, regime)
        assert r is not None and ("SHORT" in r or "not negative" in r)

    def test_high_er_skips(self):
        cfg = self._cfg_on("NY")
        ctx = self._ctx(self.NY_MON, slope=-1.0)
        regime = _regime(efficiency_ratio_5m_20=0.45)  # above 0.30
        r = filter_path_z(cfg, ctx, regime)
        assert r is not None and "0.30" in r

    def test_thursday_skips(self):
        cfg = self._cfg_on("NY")
        ctx = self._ctx(self.NY_THU, slope=-1.0)
        regime = _regime(efficiency_ratio_5m_20=0.20)
        r = filter_path_z(cfg, ctx, regime)
        assert r is not None and "Thu" in r

    def test_missing_er_skips(self):
        """Path Z is restrictive: no ER data = no trade."""
        cfg = self._cfg_on("NY")
        ctx = self._ctx(self.NY_MON, slope=-1.0)
        regime = _regime(efficiency_ratio_5m_20=None)
        r = filter_path_z(cfg, ctx, regime)
        assert r is not None and "ER" in r

    def test_flat_slope_skips(self):
        cfg = self._cfg_on("NY")
        ctx = self._ctx(self.NY_MON, slope=0.0)
        regime = _regime(efficiency_ratio_5m_20=0.20)
        r = filter_path_z(cfg, ctx, regime)
        assert r is not None

    def test_session_configs_v9_z_all_have_flag(self):
        for name, cfg in SESSION_CONFIGS_V9_Z.items():
            assert cfg.require_path_z is True, f"{name} missing Path Z flag"


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
    """Replays historical trade fixtures through v8 strategy_engine.

    Fixtures are loaded from tests/fixtures/golden_trades.json (generated
    by tests/generate_golden_fixtures.py). Any code change that flips
    a fixture decision must EITHER:
      (a) regenerate the fixtures with a documented rationale (registry entry), or
      (b) fix the code so behavior matches the pinned decision.
    """

    @staticmethod
    def _fixtures():
        import json
        fp = Path(__file__).parent / "fixtures/golden_trades.json"
        if not fp.exists():
            return []
        return json.loads(fp.read_text()).get("trades", [])

    def test_fixtures_loaded(self):
        fx = self._fixtures()
        assert len(fx) > 0, "run tests/generate_golden_fixtures.py to populate"

    @pytest.mark.parametrize("i", range(30))  # covers up to 30 fixtures
    def test_fixture_decision_pinned(self, i):
        fx = self._fixtures()
        if i >= len(fx):
            pytest.skip(f"only {len(fx)} fixtures")
        trade = fx[i]
        cfg = SESSION_CONFIGS_V8_INITIAL[trade["session"]]
        inp = trade["inputs"]
        # Use the fixture's actual timestamp so time-of-day filters (news, fix)
        # evaluate against the same context as generation.
        entry_ts = pd.Timestamp(trade["entry_ts"])
        if entry_ts.tz is None:
            entry_ts = entry_ts.tz_localize("UTC")
        or_close_ts = entry_ts
        session_open_ts = entry_ts - pd.Timedelta(minutes=30)
        ctx = OrContext(
            session_open_utc=session_open_ts,
            or_close_utc=or_close_ts,
            or_high=inp["or_high"],
            or_low=inp["or_low"],
            or_range=inp["or_high"] - inp["or_low"],
            atr_at_close=inp["atr"],
            slope_at_close=inp["slope"],
            or_bars_df=pd.DataFrame(),
        )
        decision = evaluate_session(cfg, ctx, _regime(as_of_utc=or_close_ts))
        expected = trade["v8_decision"]
        assert decision.would_take == expected["would_take"], (
            f"fixture #{i} ({trade['entry_ts']}): would_take flipped "
            f"(got {decision.would_take}, expected {expected['would_take']}; "
            f"reasons={list(decision.would_skip_reasons)})"
        )
        # OR/ATR reason presence (bar-level, stable)
        expected_or_atr = [r for r in expected["would_skip_reasons"] if "OR/ATR" in r]
        actual_or_atr = [r for r in decision.would_skip_reasons if "OR/ATR" in r]
        assert expected_or_atr == actual_or_atr, f"fixture #{i}: OR/ATR reason changed"
        assert decision.direction.name == expected["direction"], f"fixture #{i}: direction flipped"


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
