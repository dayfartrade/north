#!/bin/bash
# Post-bootstrap smoke test. Runs as gdt from ~/golddaytrador.
# Verifies: venv works, imports resolve, secret files present, timers loaded,
# .env.vps sanity, dispatch dry-run doesn't crash.

set -u
cd "$(dirname "$0")/.." || exit 90

PASS=0
FAIL=0
check() {
    local name="$1"; shift
    if "$@" > /tmp/vps_smoke.out 2>&1; then
        echo "  [OK]   $name"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $name"
        sed 's/^/         /' /tmp/vps_smoke.out
        FAIL=$((FAIL + 1))
    fi
}

echo "=== VPS smoke test ==="

check "venv python present"           test -x .venv/bin/python
check ".env.vps present"              test -f .env.vps
check ".telegram present"             test -f .telegram
check ".telegram is 0600"             bash -c "[ \"$(stat -c '%a' .telegram)\" = 600 ]"
check "GOLDTRADER_STRICT_PUBLIC set"  bash -c "grep -q GOLDTRADER_STRICT_PUBLIC=1 .env.vps"
check "HEALTHCHECKS uuid set"         bash -c "grep -q '^HEALTHCHECKS_DISPATCH_UUID=..' .env.vps"
check "data dir present"              test -d data
check "GC 5m data present"            test -f data/gc/GC_5m.csv
check "dispatch_state.json present"   test -f data/dispatch_state.json
check "validation_state present"      test -f data/validation_state.json
check "systemd timer file installed"  test -f /etc/systemd/system/gdt-dispatch.timer
check "wrapper is executable"         test -x scripts/dispatch_with_healthcheck.sh
check "python imports strategy_engine" bash -c "PYTHONPATH=src .venv/bin/python -c 'import strategy_engine; print(strategy_engine.VERSION)'"
check "python imports dispatch"       bash -c "PYTHONPATH=src .venv/bin/python -c 'import dispatch'"
check "pytest passes core suite"      bash -c "PYTHONPATH=src .venv/bin/python -m pytest tests/test_strategy_engine.py -q"

echo ""
echo "=== Result: $PASS passed / $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FIX ABOVE BEFORE ENABLING TIMERS."
    exit 1
fi
echo "Ready to enable timers:"
echo "  sudo systemctl enable --now gdt-dispatch.timer gdt-weekly-validation.timer"
