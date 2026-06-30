"""User-config loader. Sane defaults; user edits config.json to override."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"

DEFAULTS = {
    "account_equity": 25000,
    "risk_pct_per_trade": 0.01,
    "sizing_mode": "fixed_frac",            # or "fixed_$" or "kelly_half"
    "fixed_risk_dollars": 250,
    "vehicles_enabled": ["GC", "MGC", "GLD"],
    "telegram_quiet_hours_et": [22, 7],     # [start, end] in ET; if start<end => quiet [start,end], else quiet (start..24]+[0..end]
    "min_trend_strength": 0.0,
}


def load() -> dict:
    if CONFIG_FILE.exists():
        try:
            user = json.loads(CONFIG_FILE.read_text())
            return {**DEFAULTS, **user}
        except Exception as e:
            print(f"[config] failed to load {CONFIG_FILE}: {e}. Using defaults.")
    return dict(DEFAULTS)
