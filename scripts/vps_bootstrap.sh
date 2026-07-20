#!/bin/bash
# One-shot VPS bootstrap for Hetzner CX22 (Ubuntu 24.04 LTS).
#
# Assumes you have already:
#   1) Provisioned CX22 with SSH key
#   2) SSH'd in as root
#   3) Copied THIS repo to /root/golddaytrador temporarily (or clone below)
#
# Then run: bash /root/golddaytrador/scripts/vps_bootstrap.sh <github_pat>
#
# What it does:
#   - Installs OS packages, creates gdt user, hardens SSH
#   - Clones repo into /home/gdt/golddaytrador as gdt
#   - Sets up Python 3.12 venv + requirements
#   - Installs systemd units from ops/systemd/
#   - Leaves .env.vps + secret files as MANUAL steps (user must scp)

set -euo pipefail

PAT="${1:-}"
if [ -z "$PAT" ]; then
    echo "usage: bash vps_bootstrap.sh <github_pat>" 1>&2
    exit 2
fi

echo "[bootstrap] apt update + install"
apt update
# Detect Python 3 minor version available on this Ubuntu (24.04 = 3.12, 26.04 = 3.14, etc.)
PY_MINOR=$(apt-cache pkgnames | grep -E '^python3\.[0-9]+$' | sort -V | tail -1 | cut -d. -f2)
if [ -z "$PY_MINOR" ]; then
    echo "[bootstrap] ERROR: no python3.X package found in apt" 1>&2
    exit 3
fi
PY_BIN="python3.${PY_MINOR}"
echo "[bootstrap] using ${PY_BIN}"
DEBIAN_FRONTEND=noninteractive apt install -y \
    ${PY_BIN} ${PY_BIN}-venv python3-pip git tmux vim ufw fail2ban curl

echo "[bootstrap] create gdt user + passwordless sudo"
if ! id gdt >/dev/null 2>&1; then
    useradd -m -s /bin/bash gdt
    usermod -aG sudo gdt
fi
# Passwordless sudo so re-runs / recovery don't get locked out
echo 'gdt ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-gdt
chmod 440 /etc/sudoers.d/90-gdt

echo "[bootstrap] mirror root's authorized_keys to gdt"
mkdir -p /home/gdt/.ssh
if [ -f /root/.ssh/authorized_keys ]; then
    cp /root/.ssh/authorized_keys /home/gdt/.ssh/authorized_keys
fi
chown -R gdt:gdt /home/gdt/.ssh
chmod 700 /home/gdt/.ssh
chmod 600 /home/gdt/.ssh/authorized_keys 2>/dev/null || true

echo "[bootstrap] firewall (SSH-safe order)"
ufw allow OpenSSH
ufw --force enable

echo "[bootstrap] clone repo as gdt"
sudo -u gdt bash -c "
    cd /home/gdt
    if [ ! -d golddaytrador ]; then
        git clone https://${PAT}@github.com/far-reach/golddaytrador.git
    else
        cd golddaytrador && git pull
    fi
"

echo "[bootstrap] python venv + requirements"
sudo -u gdt bash -c "
    cd /home/gdt/golddaytrador
    if [ ! -d .venv ]; then
        ${PY_BIN} -m venv .venv
    fi
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
"

echo "[bootstrap] install systemd units"
install -m 644 /home/gdt/golddaytrador/ops/systemd/gdt-dispatch.service /etc/systemd/system/
install -m 644 /home/gdt/golddaytrador/ops/systemd/gdt-dispatch.timer /etc/systemd/system/
install -m 644 /home/gdt/golddaytrador/ops/systemd/gdt-weekly-validation.service /etc/systemd/system/
install -m 644 /home/gdt/golddaytrador/ops/systemd/gdt-weekly-validation.timer /etc/systemd/system/
chmod +x /home/gdt/golddaytrador/scripts/dispatch_with_healthcheck.sh
systemctl daemon-reload

echo "[bootstrap] harden SSH (LAST — do not fail earlier and lock out)"
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

cat <<EOF

============================================================
[bootstrap] DONE. Next MANUAL steps (cannot be automated):

1) scp .env.vps to /home/gdt/golddaytrador/.env.vps
   Minimum contents:
     GOLDTRADER_TG_CHAT_PUBLIC=<channel_id_or_leave_empty>
     GOLDTRADER_STRICT_PUBLIC=1
     HEALTHCHECKS_DISPATCH_UUID=<uuid_from_healthchecks.io>

2) scp secret files:
     .telegram              -> /home/gdt/golddaytrador/.telegram
     .github-token          -> /home/gdt/golddaytrador/.github-token
   Then: chown gdt:gdt /home/gdt/golddaytrador/.telegram /home/gdt/golddaytrador/.github-token
         chmod 600      /home/gdt/golddaytrador/.telegram /home/gdt/golddaytrador/.github-token

3) scp state files (bring history):
     data/dispatch_state.json
     data/health.json
     data/validation_state.json
     data/halt_state.json
     data/tracker/orb_forward_log.csv
     data/tracker/journal.csv
     data/tracker/forward_log.csv
     data/experiments/registry.json
     data/shadow_decisions.jsonl
     data/shadow_equity_since_halt.jsonl
     data/alerts_stream.jsonl
     data/gc/
     data/macro/

4) Smoke test:
     bash /home/gdt/golddaytrador/scripts/vps_smoke_test.sh

5) Enable timers:
     systemctl enable --now gdt-dispatch.timer
     systemctl enable --now gdt-weekly-validation.timer
     systemctl list-timers gdt-dispatch.timer gdt-weekly-validation.timer

6) On Windows: Disable-ScheduledTask -TaskName \\\\GoldDayTrader\\\\Dispatch

============================================================
EOF
