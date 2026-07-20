#!/bin/bash
# Wrap `python -m src.dispatch` with healthchecks.io ping.
# Requires $HEALTHCHECKS_DISPATCH_UUID env var (set in /home/gdt/golddaytrador/.env.vps).
# systemd EnvironmentFile= directive loads .env.vps before executing.

set -u
cd "$(dirname "$0")/.." || exit 90
VENV_PY=".venv/bin/python"

if [ -z "${HEALTHCHECKS_DISPATCH_UUID:-}" ]; then
    # Fallback: run dispatch without health ping so a config gap doesn't
    # cause a silent outage on the trader itself.
    echo "[dispatch_with_healthcheck] WARN: HEALTHCHECKS_DISPATCH_UUID not set — running unmonitored" 1>&2
    "$VENV_PY" -m src.dispatch
    exit $?
fi

BASE="https://hc-ping.com/${HEALTHCHECKS_DISPATCH_UUID}"

# /start — mark tick begin (retries but non-blocking on failure)
curl -fsS -m 10 --retry 3 --retry-delay 2 "${BASE}/start" > /dev/null 2>&1 || true

"$VENV_PY" -m src.dispatch
EXIT=$?

# /$EXIT — report exit code (0=OK, non-zero=fail)
curl -fsS -m 10 --retry 3 --retry-delay 2 "${BASE}/${EXIT}" > /dev/null 2>&1 || true

exit $EXIT
