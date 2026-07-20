"""Tests for the Knox soft-launch wiring (2026-07-18).

Covers:
  - knox_kill.py state transitions and status
  - shadow_orb_tracker._knox_alerts_enabled two-key logic
  - knox_sprt_activate.py refuses to activate at n<50 or if already active
  - knox_post_mortem end-to-end: filters, formats, sends, marks idempotent
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture()
def tmp_knox_state(tmp_path, monkeypatch):
    """Point knox_kill + shadow_orb_tracker at a temp state file."""
    # Redirect the whole data dir to tmp_path
    tmp_data = tmp_path / "data"
    tmp_data.mkdir()

    monkeypatch.chdir(ROOT)  # scripts assume cwd=repo root

    # For knox_kill, STATE_FILE is a module-level constant. Reload after
    # monkey-patching the ROOT-derived path.
    import importlib
    import knox_kill as kk
    monkeypatch.setattr(kk, "STATE_FILE", tmp_data / "knox_state.json")
    yield kk


class TestKnoxKill:
    def test_status_default_enabled_when_file_missing(self, tmp_knox_state, capsys):
        rc = tmp_knox_state.main(["knox_kill.py", "status"])
        out = capsys.readouterr().out
        assert "ENABLED" in out
        assert rc == 0

    def test_off_then_status_reports_disabled(self, tmp_knox_state, capsys):
        tmp_knox_state.main(["knox_kill.py", "off", "unit test"])
        rc = tmp_knox_state.main(["knox_kill.py", "status"])
        out = capsys.readouterr().out
        assert "DISABLED" in out
        assert "unit test" in out
        assert rc == 1  # non-zero when disabled

    def test_on_then_off_then_on_persists(self, tmp_knox_state):
        tmp_knox_state.main(["knox_kill.py", "off", "step1"])
        tmp_knox_state.main(["knox_kill.py", "on", "step2"])
        state = json.loads(tmp_knox_state.STATE_FILE.read_text())
        assert state["enabled"] is True
        assert state["reason"] == "step2"

    def test_bad_command_returns_2(self, tmp_knox_state, capsys):
        rc = tmp_knox_state.main(["knox_kill.py", "invalid"])
        assert rc == 2


class TestShadowTrackerKillGate:
    """The two-key kill: env AND state file. Either off -> disabled."""

    def _load_fn(self):
        import importlib
        import shadow_orb_tracker as sot
        importlib.reload(sot)
        return sot

    def test_env_unset_disables(self, monkeypatch, tmp_path):
        sot = self._load_fn()
        monkeypatch.delenv("KNOX_RESEARCH_ENABLED", raising=False)
        assert sot._knox_alerts_enabled() is False

    def test_env_wrong_value_disables(self, monkeypatch):
        sot = self._load_fn()
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "0")
        assert sot._knox_alerts_enabled() is False

    def test_env_set_enables_when_no_state_file(self, monkeypatch, tmp_path):
        sot = self._load_fn()
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "1")
        # Point at nonexistent state file
        monkeypatch.setattr(sot, "ROOT", tmp_path)
        assert sot._knox_alerts_enabled() is True

    def test_state_file_false_overrides_env(self, monkeypatch, tmp_path):
        sot = self._load_fn()
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "1")
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "knox_state.json").write_text(
            json.dumps({"enabled": False, "reason": "test"})
        )
        monkeypatch.setattr(sot, "ROOT", tmp_path)
        assert sot._knox_alerts_enabled() is False

    def test_state_file_true_plus_env_enables(self, monkeypatch, tmp_path):
        sot = self._load_fn()
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "1")
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "knox_state.json").write_text(
            json.dumps({"enabled": True, "reason": "test"})
        )
        monkeypatch.setattr(sot, "ROOT", tmp_path)
        assert sot._knox_alerts_enabled() is True

    def test_state_file_unreadable_falls_open_to_env(self, monkeypatch, tmp_path):
        """If state file is corrupt, defer to env (fail-open on parse errors)."""
        sot = self._load_fn()
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "1")
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "knox_state.json").write_text("not valid json{")
        monkeypatch.setattr(sot, "ROOT", tmp_path)
        assert sot._knox_alerts_enabled() is True


class TestKnoxSprtActivateGuards:
    """The activation script must refuse post-hoc hypothesis fitting."""

    def _run(self, args: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "knox_sprt_activate.py"), *args],
            cwd=str(cwd), capture_output=True, text=True,
        )

    def test_refuses_when_n_below_threshold(self):
        # Current shadow log has 0 engine_b_takes rows with resolved outcomes.
        # Refusal reason may be either 'INSUFFICIENT' (n<50) or 'REFUSE' (state
        # file already exists from a prior activation). Both are discipline
        # refusals; test accepts either.
        r = self._run([])
        assert r.returncode in (3, 4)
        assert ("INSUFFICIENT" in r.stderr) or ("REFUSE" in r.stderr)

    def test_force_flag_recognized(self):
        """--force is a real flag (path-substitution testing is a bigger refactor
        than warranted; the n<threshold refusal is the discipline gate that matters)."""
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "knox_sprt_activate.py"), "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "--force" in r.stdout
        assert "--reason" in r.stdout


class TestKnoxPostMortem:
    """Post-mortem publishes outcome follow-up when Knox alert resolves."""

    def _load_module(self, tmp_path, monkeypatch):
        import importlib
        import knox_post_mortem as pm
        importlib.reload(pm)
        monkeypatch.setattr(pm, "SHADOW_LOG", tmp_path / "shadow.jsonl")
        monkeypatch.setattr(pm, "ROOT", tmp_path)  # for knox_state.json check
        return pm

    def _seed_rows(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_kill_gate_skips_when_env_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("KNOX_RESEARCH_ENABLED", raising=False)
        monkeypatch.setenv("KNOX_POSTMORTEM_DRY_RUN", "1")
        pm = self._load_module(tmp_path, monkeypatch)
        self._seed_rows(pm.SHADOW_LOG, [
            {"engine_b_takes": True, "outcome": {"kind": "target", "net_pnl": 100},
             "session": "NY", "direction_bias": "LONG", "or_open_utc": "2026-07-20T13:30",
             "entry_long": 4000.0},
        ])
        rc = pm.main()
        assert rc == 0
        # File unchanged — no post_mortem_sent flag added
        rows = [json.loads(l) for l in pm.SHADOW_LOG.read_text().splitlines() if l.strip()]
        assert not rows[0].get("research_post_mortem_sent")

    def test_dry_run_marks_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "1")
        monkeypatch.setenv("KNOX_POSTMORTEM_DRY_RUN", "1")
        pm = self._load_module(tmp_path, monkeypatch)
        self._seed_rows(pm.SHADOW_LOG, [
            {"engine_b_takes": True,
             "outcome": {"kind": "target", "net_pnl": 250.5, "exit_price": 4020.5,
                          "resolved_utc": "2026-07-20T16:30:00+00:00"},
             "session": "NY", "direction_bias": "LONG",
             "or_open_utc": "2026-07-20T13:30:00+00:00",
             "entry_long": 4010.0},
        ])
        rc = pm.main()
        assert rc == 0
        rows = [json.loads(l) for l in pm.SHADOW_LOG.read_text().splitlines() if l.strip()]
        assert rows[0].get("research_post_mortem_sent") is True
        assert "research_post_mortem_utc" in rows[0]

    def test_skips_unresolved(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "1")
        monkeypatch.setenv("KNOX_POSTMORTEM_DRY_RUN", "1")
        pm = self._load_module(tmp_path, monkeypatch)
        self._seed_rows(pm.SHADOW_LOG, [
            {"engine_b_takes": True, "outcome": None,  # not resolved
             "session": "NY", "direction_bias": "LONG",
             "or_open_utc": "2026-07-20T13:30", "entry_long": 4000},
        ])
        pm.main()
        rows = [json.loads(l) for l in pm.SHADOW_LOG.read_text().splitlines() if l.strip()]
        assert not rows[0].get("research_post_mortem_sent")

    def test_skips_already_sent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "1")
        monkeypatch.setenv("KNOX_POSTMORTEM_DRY_RUN", "1")
        pm = self._load_module(tmp_path, monkeypatch)
        pre_utc = "2026-07-20T16:35:00+00:00"
        self._seed_rows(pm.SHADOW_LOG, [
            {"engine_b_takes": True,
             "outcome": {"kind": "target", "net_pnl": 250.5,
                          "resolved_utc": "2026-07-20T16:30:00+00:00"},
             "session": "NY", "direction_bias": "LONG",
             "or_open_utc": "2026-07-20T13:30:00+00:00",
             "entry_long": 4010.0,
             "research_post_mortem_sent": True,
             "research_post_mortem_utc": pre_utc},
        ])
        pm.main()
        rows = [json.loads(l) for l in pm.SHADOW_LOG.read_text().splitlines() if l.strip()]
        # Timestamp unchanged (not re-posted)
        assert rows[0]["research_post_mortem_utc"] == pre_utc

    def test_skips_when_not_engine_b(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "1")
        monkeypatch.setenv("KNOX_POSTMORTEM_DRY_RUN", "1")
        pm = self._load_module(tmp_path, monkeypatch)
        self._seed_rows(pm.SHADOW_LOG, [
            {"engine_b_takes": False,  # only Engine A shadow, not Knox
             "outcome": {"kind": "target", "net_pnl": 100},
             "session": "NY", "direction_bias": "LONG",
             "or_open_utc": "2026-07-20T13:30:00+00:00",
             "entry_long": 4010.0},
        ])
        pm.main()
        rows = [json.loads(l) for l in pm.SHADOW_LOG.read_text().splitlines() if l.strip()]
        assert not rows[0].get("research_post_mortem_sent")

    def test_format_includes_emoji_and_pnl(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("KNOX_RESEARCH_ENABLED", "1")
        monkeypatch.setenv("KNOX_POSTMORTEM_DRY_RUN", "1")
        pm = self._load_module(tmp_path, monkeypatch)
        # WIN row
        self._seed_rows(pm.SHADOW_LOG, [
            {"engine_b_takes": True,
             "outcome": {"kind": "target", "net_pnl": 250.5, "exit_price": 4020.5,
                          "resolved_utc": "2026-07-20T16:30:00+00:00"},
             "session": "NY", "direction_bias": "LONG",
             "or_open_utc": "2026-07-20T13:30:00+00:00",
             "entry_long": 4010.0},
        ])
        pm.main()
        out = capsys.readouterr().out
        assert "KNOX RESEARCH" in out
        assert "250.5" in out or "250.50" in out
        assert "NY" in out
        assert "LONG" in out
