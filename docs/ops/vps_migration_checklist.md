# VPS migration checklist — Hetzner CX22

**Owner:** Farhad. **Assist:** Knox. **Target date:** 2026-07-13 (post-CPI).
**Reason:** Windows Task Scheduler outages caused 36h dark in last 48h. Public launch 2026-07-30 requires >99% uptime. Per quant framework (2026-07-13): Hetzner CX22 + systemd + healthchecks.io is the retail-quant standard.

## Pre-flight (30 min)

- [ ] Create Hetzner account. Payment: €4.15/mo.
- [ ] Provision **CX22** (2 vCPU / 4 GB RAM / 40 GB SSD), Ubuntu 24.04 LTS.
- [ ] Region: **Nürnberg or Falkenstein** (EU-central; matches trading-session latency profile). Ashburn if user prefers US.
- [ ] SSH key upload during provisioning. Note IPv4/IPv6 addresses.
- [ ] Sign up healthchecks.io free tier. Create one check per timer: `dispatch-30min`, `daily-refresh`, `weekly-validation`.

## OS + Python (20 min)

```bash
ssh root@<vps_ip>
apt update && apt upgrade -y
apt install -y python3.12 python3.12-venv python3-pip git tmux vim ufw fail2ban
useradd -m -s /bin/bash gdt
usermod -aG sudo gdt
# copy SSH key: mkdir /home/gdt/.ssh; cp ~/.ssh/authorized_keys /home/gdt/.ssh/; chown -R gdt:gdt /home/gdt/.ssh; chmod 700 /home/gdt/.ssh
ufw allow OpenSSH
ufw enable
# disable root SSH
sed -i 's/#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh
```

## Repo + secrets (15 min)

```bash
su - gdt
git clone https://<PAT>@github.com/far-reach/golddaytrador.git
cd golddaytrador
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Files to scp from Windows (do NOT commit — user's responsibility):**
- [ ] `.telegram` (bot token + chat IDs)
- [ ] `.github-token` (push access; only if syncing state back)
- [ ] `data/dispatch_state.json` (dedup registry — brings tick history)
- [ ] `data/health.json` (heartbeat state)
- [ ] `data/validation_state.json` (H3 kill-switch state)
- [ ] `data/tracker/orb_forward_log.csv`, `data/tracker/journal.csv`, `data/tracker/forward_log.csv`
- [ ] `data/experiments/registry.json`
- [ ] `data/shadow_decisions.jsonl`
- [ ] `data/alerts_stream.jsonl`
- [ ] `data/gc/*.csv` (initial cache; will refresh on first tick)
- [ ] `data/macro/*.csv` (initial cache)
- [ ] `data/basis/*.csv` (if present)
- [ ] `data/cot/*` (if present)

Command from Windows:
```powershell
scp -r data .telegram .github-token gdt@<vps_ip>:/home/gdt/golddaytrador/
```

## systemd wiring (25 min)

Create `/etc/systemd/system/gdt-dispatch.service`:
```ini
[Unit]
Description=Gold day-trader dispatch tick
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=gdt
WorkingDirectory=/home/gdt/golddaytrador
ExecStart=/home/gdt/golddaytrador/.venv/bin/python -m src.dispatch
Environment=PYTHONPATH=/home/gdt/golddaytrador/src
Environment=GOLDTRADER_TG_CHAT_PUBLIC=<channel_id_if_set>
Environment=GOLDTRADER_STRICT_PUBLIC=1
```

Create `/etc/systemd/system/gdt-dispatch.timer`:
```ini
[Unit]
Description=Fire dispatch every 30 minutes

[Timer]
OnCalendar=*:0/30
Persistent=true
Unit=gdt-dispatch.service

[Install]
WantedBy=timers.target
```

**Enable + start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gdt-dispatch.timer
systemctl list-timers gdt-dispatch.timer
```

## Healthchecks.io wrapper (10 min)

Modify `src/dispatch.py` to ping at start + end (or add a wrapper script):
```bash
# /home/gdt/golddaytrador/scripts/dispatch_with_healthcheck.sh
#!/bin/bash
curl -fsS --retry 3 "https://hc-ping.com/<uuid>/start" > /dev/null
python -m src.dispatch
EXIT=$?
curl -fsS --retry 3 "https://hc-ping.com/<uuid>/$EXIT" > /dev/null
exit $EXIT
```

Update service `ExecStart` to point at wrapper. Test: unplug run, verify healthchecks.io alert fires within grace window.

## Cutover (15 min)

- [ ] On Windows: disable `\GoldDayTrader\Dispatch` scheduled task (`Disable-ScheduledTask`).
- [ ] On VPS: force one manual run: `systemctl start gdt-dispatch.service`. Verify `data/dispatch.log` gets a new entry.
- [ ] Wait for next :30 or :00 tick — confirm timer fires.
- [ ] After 2 clean ticks: cutover complete.

## Verification (ongoing)

- [ ] Watch `journalctl -u gdt-dispatch.service -f` during first 3 dispatches
- [ ] Verify PLAN payloads still fire to Telegram
- [ ] Verify `data/alerts_stream.jsonl` grows
- [ ] Verify healthchecks.io shows green
- [ ] Verify weekly-validation runs Sunday 22:00 UTC

## Rollback plan

If VPS fails within first 6h:
1. Re-enable Windows Task: `Enable-ScheduledTask -TaskName \GoldDayTrader\Dispatch`
2. Kill VPS timer: `systemctl stop gdt-dispatch.timer; systemctl disable gdt-dispatch.timer`
3. Investigate root cause. Do not delete VPS — debug later.

**Estimated total time:** 2h. If bogged, VPS is not a same-day project — hold.

## After cutover: update memory

Replace `hosting_blocker.md` with `hosting_current.md` documenting the VPS setup, systemd units, and healthchecks.io UUIDs.
