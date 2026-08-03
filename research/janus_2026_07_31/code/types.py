"""Setup candidate type — THE shared contract between signal generation,
Pythia (TG surface), and the auto-trader.

## Role in the codebase

`SetupCandidate` is the single value type that flows from the shared
signal core out to BOTH consuming surfaces:

    src/setups/*.py (detectors)
        │
        ▼  emits SetupCandidate
    src/filters/*.py + src/scoring.py (filter + score)
        │
        ▼  passes SetupCandidate + score to
    src/jobs/scanner.py (orchestrator)
        │
        ├──► src/tg/bot.py (renders card)
        └──► src/auto_trader/integration.py (routes capital)

Pythia (src/tg/) and the auto-trader (src/auto_trader/) MUST NOT
import from each other at module scope — enforced by
tests/test_module_boundaries.py. They only meet at the orchestrator
layer (src/jobs/scanner.py), which reads SetupCandidate + delivers it
to each surface independently.

## Change-management

Because SetupCandidate is the ONE shared contract:
  * Adding a field is safe (both surfaces ignore unknown fields at
    call-site — they read what they need).
  * Removing or renaming a field is a breaking change to BOTH surfaces
    simultaneously. Do it deliberately.
  * Optional fields default to None to preserve back-compat with older
    detectors that don't populate them.

## Field categories

Universal (all detectors set these):
  symbol, side, source_phase, bias_tf, trigger_tf,
  entry_price, sl_price, tp1_price, tp2_price,
  atr_at_setup, bias_alignment, volume_confirmed, reasons

Specialist-specific optional annotations:
  funding_extremity_percentile — funding_extreme_revert only
  entry_shadow_* — funding_extreme_revert only (as of 2026-07-09)

Pre-scoring: `confidence_score` / `confidence_tier` are assigned in
src/scoring.py AFTER the filter chain runs. The detector only fills
the geometry + reasoning fields here; scoring layers on the score
downstream.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SetupCandidate:
    symbol: str
    side: str                        # 'long' / 'short'
    source_phase: str                # 'grimes_pullback'
    bias_tf: str                     # '1D' / '4H'
    trigger_tf: str                  # '1H' / '15m'

    entry_price: float
    sl_price: float
    tp1_price: float
    tp2_price: float

    atr_at_setup: float
    bias_alignment: str              # 'aligned' / 'mixed' / 'counter'
    volume_confirmed: bool

    reasons: list[str] = field(default_factory=list)

    # Quality Option C component 1 (added 2026-06-24): the percentile rank
    # of the current funding rate within the 90d funding history. Only
    # populated by funding_extreme_revert detector. Used by scoring when
    # QUALITY_C1_ENABLED env flag is set; falls back to binary
    # +2 funding_at_extreme_percentile when None or flag off.
    funding_extremity_percentile: Optional[float] = None

    # Entry-discount SHADOW (added 2026-07-09 per pre-reg
    # entry_discount_prereg_2026_07_09.md middle path):
    # what the ENTRY_DISCOUNT path WOULD have proposed as entry.
    # None when the specialist's live entry already IS the shadow (e.g.,
    # grimes_pullback already uses structural entry), when ATR is
    # unavailable, or when the buffer collapses to trigger_price.
    # Persisted to setups.entry_shadow_price for post-hoc analysis.
    entry_shadow_price: Optional[float] = None
    entry_shadow_method: Optional[str] = None            # 'structural' / 'atr_buffered' / 'bounded' / 'no_discount'
    entry_shadow_discount_pct: Optional[float] = None    # signed fraction vs entry_price

    @property
    def risk(self) -> float:
        return abs(self.entry_price - self.sl_price)

    @property
    def rr_to_tp1(self) -> float:
        r = self.risk
        return round(abs(self.tp1_price - self.entry_price) / r, 3) if r > 0 else 0.0

    @property
    def rr_to_tp2(self) -> float:
        r = self.risk
        return round(abs(self.tp2_price - self.entry_price) / r, 3) if r > 0 else 0.0
