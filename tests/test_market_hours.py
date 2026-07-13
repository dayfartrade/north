"""Tests for market_likely_open — session-aware daemon guards.

Verifies:
  - Weekday during trading hours -> open
  - Saturday all day -> closed
  - Friday after 17:00 ET -> closed
  - Sunday before 18:00 ET -> closed
  - Weekday during COMEX close (17:00-18:00 ET) -> closed
  - DST-aware (EDT vs EST)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from health import market_likely_open  # noqa: E402


def _et(y, m, d, hh, mm=0) -> pd.Timestamp:
    """Build a US/Eastern-aware Timestamp for a wall-clock time."""
    return pd.Timestamp(f"{y}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}", tz="America/New_York").tz_convert("UTC")


class TestMarketHours:
    def test_weekday_trading_open(self):
        """Tuesday 14:00 ET (during trading) -> open."""
        assert market_likely_open(_et(2026, 7, 14, 14)) is True

    def test_saturday_closed(self):
        assert market_likely_open(_et(2026, 7, 11, 14)) is False
        assert market_likely_open(_et(2026, 7, 11, 3)) is False

    def test_friday_before_close_open(self):
        assert market_likely_open(_et(2026, 7, 10, 16, 55)) is True

    def test_friday_after_close(self):
        assert market_likely_open(_et(2026, 7, 10, 17, 5)) is False
        assert market_likely_open(_et(2026, 7, 10, 22)) is False

    def test_sunday_before_open(self):
        assert market_likely_open(_et(2026, 7, 12, 12)) is False
        assert market_likely_open(_et(2026, 7, 12, 17, 55)) is False

    def test_sunday_after_open(self):
        assert market_likely_open(_et(2026, 7, 12, 18, 5)) is True
        assert market_likely_open(_et(2026, 7, 12, 22)) is True

    def test_weekday_comex_close_hour(self):
        """Tuesday 17:15 ET (COMEX close 17:00-18:00) -> closed."""
        assert market_likely_open(_et(2026, 7, 14, 17)) is False
        assert market_likely_open(_et(2026, 7, 14, 17, 30)) is False
        assert market_likely_open(_et(2026, 7, 14, 17, 59)) is False

    def test_weekday_after_comex_close(self):
        """Tuesday 18:05 ET -> back open (new trading day)."""
        assert market_likely_open(_et(2026, 7, 14, 18, 5)) is True

    def test_dst_summer(self):
        """July 2026: EDT (UTC-4). Weekday 14:00 EDT = 18:00 UTC -> open."""
        ts = pd.Timestamp("2026-07-14 18:00", tz="UTC")
        assert market_likely_open(ts) is True

    def test_dst_winter(self):
        """January 2026: EST (UTC-5). Weekday 14:00 EST = 19:00 UTC -> open."""
        ts = pd.Timestamp("2026-01-14 19:00", tz="UTC")
        assert market_likely_open(ts) is True

    def test_dst_transition_comex_close_summer(self):
        """July 2026 (EDT): 17:00 ET = 21:00 UTC -> closed."""
        assert market_likely_open(pd.Timestamp("2026-07-14 21:30", tz="UTC")) is False

    def test_dst_transition_comex_close_winter(self):
        """January 2026 (EST): 17:00 ET = 22:00 UTC -> closed."""
        assert market_likely_open(pd.Timestamp("2026-01-14 22:30", tz="UTC")) is False
