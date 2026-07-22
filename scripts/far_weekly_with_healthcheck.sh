#!/bin/bash
# Wrap FAR Weekly Gold Read publisher with healthchecks.io ping.
# Requires $HEALTHCHECKS_FAR_WEEKLY_UUID env var (set in .env.vps).
# systemd EnvironmentFile= directive loads .env.vps before executing.

set -u
cd "$(dirname "$0")/.." || exit 90
VENV_PY=".venv/bin/python"

if [ -z "${HEALTHCHECKS_FAR_WEEKLY_UUID:-}" ]; then
    # Fallback: run publisher without health ping so a config gap
    # doesn't cause silent outage
    echo "[far_weekly_healthcheck] WARN: HEALTHCHECKS_FAR_WEEKLY_UUID not set — running unmonitored" 1>&2
    "$VENV_PY" scripts/far_weekly_gold_read_publish.py
    exit $?
fi

BASE="https://hc-ping.com/${HEALTHCHECKS_FAR_WEEKLY_UUID}"

# /start — mark tick begin (retries but non-blocking)
curl -fsS -m 10 --retry 3 --retry-delay 2 "${BASE}/start" > /dev/null 2>&1 || true

"$VENV_PY" scripts/far_weekly_gold_read_publish.py
EXIT=$?

# /$EXIT — report exit code
curl -fsS -m 10 --retry 3 --retry-delay 2 "${BASE}/${EXIT}" > /dev/null 2>&1 || true

exit $EXIT
