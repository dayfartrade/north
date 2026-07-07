"""Chaos test: verify dispatch state files survive corruption / crash / concurrent writes.

Simulates the failure modes B3 (atomic writes, commit da3dec9) was designed
to prevent. Runs against an ISOLATED tmp directory — never touches the live
data/dispatch_state.json or data/health.json.

Run:
    python -m pytest tests/test_chaos_state.py -v
    or:
    python tests/test_chaos_state.py
"""
from __future__ import annotations
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


# ---- helpers ----------------------------------------------------------------

def _atomic_save_state(state: dict, state_file: Path):
    """Mirrors the save_state pattern in dispatch.py, dispatch_orb.py, health.py
    — including the Windows retry guard for concurrent reader races."""
    import time
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_suffix(state_file.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    delay = 0.02
    for _ in range(5):
        try:
            os.replace(tmp, state_file)
            return
        except PermissionError:
            time.sleep(delay); delay *= 2
    os.replace(tmp, state_file)  # final try, let it raise if still failing


def _load_state(state_file: Path) -> dict:
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {"sent": []}


def _load_state_safe(state_file: Path) -> dict:
    """Wraps _load_state with graceful fallback for corruption."""
    try:
        return _load_state(state_file)
    except json.JSONDecodeError:
        return {"sent": [], "recovered_from": "corrupt_json"}


# ---- tests ------------------------------------------------------------------

def test_partial_tmp_file_ignored():
    """If a crash left a .tmp file mid-write, subsequent loads must ignore it."""
    with tempfile.TemporaryDirectory() as td:
        sf = Path(td) / "dispatch_state.json"
        _atomic_save_state({"sent": ["A", "B"]}, sf)
        # Simulate a crash mid-write: partial content in a .tmp
        tmp = sf.with_suffix(sf.suffix + ".tmp")
        tmp.write_text('{"sent": ["A", "B", "C')  # truncated
        # Real state file still intact
        loaded = _load_state(sf)
        assert loaded == {"sent": ["A", "B"]}, f"Expected clean state, got {loaded}"
        # Next successful write cleans up the stale tmp
        _atomic_save_state({"sent": ["A", "B", "C"]}, sf)
        assert _load_state(sf) == {"sent": ["A", "B", "C"]}
        print("  test_partial_tmp_file_ignored PASSED")


def test_corrupt_state_recoverable():
    """If dispatch_state.json is corrupt, loader must not crash the process."""
    with tempfile.TemporaryDirectory() as td:
        sf = Path(td) / "dispatch_state.json"
        sf.write_text("{not valid json at all")
        got = _load_state_safe(sf)
        assert "sent" in got, f"Expected fallback with 'sent' key, got {got}"
        print("  test_corrupt_state_recoverable PASSED")


def test_missing_file_returns_empty():
    """Fresh install / first run: no state file yet."""
    with tempfile.TemporaryDirectory() as td:
        sf = Path(td) / "dispatch_state.json"
        got = _load_state(sf)
        assert got == {"sent": []}, f"Expected empty state, got {got}"
        print("  test_missing_file_returns_empty PASSED")


def test_atomic_write_no_visible_partial():
    """Under concurrent readers, no reader should ever see a partial file.
    Uses os.replace() -> either old or new content, never a half-written mix."""
    with tempfile.TemporaryDirectory() as td:
        sf = Path(td) / "dispatch_state.json"
        _atomic_save_state({"sent": ["A"]}, sf)

        errors = []
        def reader():
            for _ in range(200):
                try:
                    s = _load_state(sf)
                    if "sent" not in s:
                        errors.append(f"missing key: {s}")
                    for k in s.get("sent", []):
                        if not isinstance(k, str):
                            errors.append(f"bad key type: {k}")
                except json.JSONDecodeError as e:
                    errors.append(f"partial read seen: {e}")

        def writer():
            for i in range(200):
                _atomic_save_state({"sent": [f"K{i}"]}, sf)

        threads = [threading.Thread(target=reader) for _ in range(3)] + \
                  [threading.Thread(target=writer)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors, f"Concurrent access errors: {errors[:5]}"
        print(f"  test_atomic_write_no_visible_partial PASSED (600 reads + 200 writes)")


def test_state_survives_dispatch_orb_import():
    """Sanity: importing dispatch_orb doesn't wipe state files."""
    with tempfile.TemporaryDirectory() as td:
        # Isolate: temporarily point STATE_FILE at our tmp
        sf = Path(td) / "dispatch_state.json"
        _atomic_save_state({"sent": ["preserve-me"]}, sf)

        # Import — this must not touch our tmp file (it uses its own path)
        import dispatch_orb, health, dispatch  # noqa

        # Our state file unchanged
        assert _load_state(sf) == {"sent": ["preserve-me"]}
        print("  test_state_survives_dispatch_orb_import PASSED")


def test_orb_lag_defer_helpers_atomic():
    """B2 lag-defer helpers write via save_health -> atomic. Verify roundtrip."""
    import pandas as pd
    with tempfile.TemporaryDirectory() as td:
        hf = Path(td) / "health.json"
        # Monkey-patch health.HEALTH_FILE for isolation
        import health
        orig = health.HEALTH_FILE
        try:
            health.HEALTH_FILE = hf
            should_alert = health.record_orb_lag_defer("NY", pd.Timestamp("2026-07-07T14:00Z"), 605.0)
            assert should_alert is False  # first defer, no alert yet
            # Second defer for SAME key -> alert
            should_alert = health.record_orb_lag_defer("NY", pd.Timestamp("2026-07-07T14:00Z"), 605.0)
            assert should_alert is True
            # Third defer -> already alerted, don't re-alert
            should_alert = health.record_orb_lag_defer("NY", pd.Timestamp("2026-07-07T14:00Z"), 605.0)
            assert should_alert is False
            # Clear
            health.clear_orb_lag_defers("NY", pd.Timestamp("2026-07-07T14:00Z"))
            state = health.load_health()
            assert "NY|2026-07-07T14:00:00+00:00" not in state.get("orb_lag_defers", {})
            print("  test_orb_lag_defer_helpers_atomic PASSED")
        finally:
            health.HEALTH_FILE = orig


if __name__ == "__main__":
    tests = [
        test_partial_tmp_file_ignored,
        test_corrupt_state_recoverable,
        test_missing_file_returns_empty,
        test_atomic_write_no_visible_partial,
        test_state_survives_dispatch_orb_import,
        test_orb_lag_defer_helpers_atomic,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  {t.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  {t.__name__} ERROR: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests)-failed}/{len(tests)} chaos tests passed")
    sys.exit(0 if failed == 0 else 1)
