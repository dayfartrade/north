# VPS migration checklist — Hetzner CX22

**Owner:** Farhad. **Assist:** Knox. **Target date:** 2026-07-13 (post-CPI).
**Reason:** Windows Task Scheduler outages caused 36h dark in last 48h. 23h gap 07-17→07-18 confirmed same root cause on 2026-07-18. Public launch requires >99% uptime. Per quant framework (2026-07-13): Hetzner CX22 + systemd + healthchecks.io is the retail-quant standard.

**Pre-staged (2026-07-18) — reduces hands-on time to ~1h:**
- Systemd units: `ops/systemd/gdt-dispatch.{service,timer}`, `ops/systemd/gdt-weekly-validation.{service,timer}`
- Healthcheck wrapper: `scripts/dispatch_with_healthcheck.sh`
- One-shot bootstrap: `scripts/vps_bootstrap.sh <github_pat>`
- Smoke test: `scripts/vps_smoke_test.sh`

## Pre-flight (30 min)

- [ ] Create Hetzner account. Payment: €4.15/mo.
- [ ] Provision **CX22** (2 vCPU / 4 GB RAM / 40 GB SSD), Ubuntu 24.04 LTS.
- [ ] Region: **Nürnberg or Falkenstein** (EU-central; matches trading-session latency profile). Ashburn if user prefers US.
- [ ] SSH key upload during provisioning. Note IPv4/IPv6 addresses.
- [ ] Sign up healthchecks.io free tier. Create one check per timer: `dispatch-30min`, `daily-refresh`, `weekly-validation`.

## OS + Python + repo (5 min — automated)

Single command replaces the OS/Python/repo/systemd steps:

```bash
ssh root@<vps_ip>
# Clone once temporarily (bootstrap will re-clone as gdt)
git clone https://<PAT>@github.com/far-reach/golddaytrador.git /root/golddaytrador
bash /root/golddaytrador/scripts/vps_bootstrap.sh <PAT>
```

The bootstrap script performs all of:
- OS package install (python3.12, git, ufw, fail2ban, curl, tmux)
- gdt user creation + SSH key mirror + root SSH disable + firewall
- Repo clone to /home/gdt/golddaytrador as gdt
- venv + requirements.txt install
- systemd units installed to /etc/systemd/system/ (not enabled yet)
- `daemon-reload` executed

**Files to scp from Windows (do NOT commit — user's responsibility):**

Secrets (chmod 600):
- [ ] `.telegram` (bot token + chat IDs)
- [ ] `.github-token` (push access; only if syncing state back)

Create `.env.vps` on the VPS (not scp'd — write it in with `vim`):
```
GOLDTRADER_TG_CHAT_PUBLIC=<channel_id_or_leave_empty>
GOLDTRADER_STRICT_PUBLIC=1
GOLDTRADER_TG_CHAT_RESEARCH=<knox_beta_channel_id>
KNOX_RESEARCH_ENABLED=1
HEALTHCHECKS_DISPATCH_UUID=<uuid_from_healthchecks.io>
```

`GOLDTRADER_TG_CHAT_RESEARCH` + `KNOX_RESEARCH_ENABLED=1` activate the Knox soft-launch (Engine B). Set `KNOX_RESEARCH_ENABLED=0` to instantly disable Knox alerts without redeploy — see `docs/launch/2026-07-18_soft_launch_plan.md`.

State + data:
- [ ] `data/dispatch_state.json` (dedup registry — brings tick history)
- [ ] `data/health.json` (heartbeat state)
- [ ] `data/validation_state.json` (H3 kill-switch state)
- [ ] `data/halt_state.json` (SPRT halt state — 2026-07-18: HALT verdict active)
- [ ] `data/shadow_equity_since_halt.jsonl` (shadow accumulation since halt)
- [ ] `data/tracker/orb_forward_log.csv`, `data/tracker/journal.csv`, `data/tracker/forward_log.csv`
- [ ] `data/experiments/registry.json`
- [ ] `data/shadow_decisions.jsonl`
- [ ] `data/alerts_stream.jsonl`
- [ ] `data/gc/*.csv` (initial cache; will refresh on first tick)
- [ ] `data/macro/*.csv` (initial cache)
- [ ] `data/basis/*.csv` (if present)
- [ ] `data/cot/*` (if present)

Command from Windows (Git Bash / WSL):
```bash
scp -r data .telegram .github-token gdt@<vps_ip>:/home/gdt/golddaytrador/
ssh gdt@<vps_ip> 'chmod 600 golddaytrador/.telegram golddaytrador/.github-token'
```

## systemd wiring — pre-staged (0 min)

Systemd unit files ALREADY committed at `ops/systemd/`:
- `gdt-dispatch.service` — one-shot wrapper call with EnvironmentFile=.env.vps
- `gdt-dispatch.timer` — every 30 min
- `gdt-weekly-validation.service` — kill-switch refresh
- `gdt-weekly-validation.timer` — Sun 22:00 UTC
- `knox-weekly-report.service` — Knox ship-gate report to both Telegram channels
- `knox-weekly-report.timer` — Sun 22:15 UTC (15 min after weekly-validation)
- `knox-post-mortem.service` — outcome follow-ups for dispatched Knox alerts
- `knox-post-mortem.timer` — every 30 min at :05 and :35 (offset from dispatch)

The bootstrap script installs them; no manual editing needed.

**Enable Knox timers alongside main timers:**
```bash
sudo systemctl enable --now knox-weekly-report.timer knox-post-mortem.timer
```

**Knox instant kill (defense-in-depth beyond env var):**
```bash
sudo -u gdt bash -c 'cd /home/gdt/golddaytrador && python scripts/knox_kill.py off "reason here"'
# re-enable:
sudo -u gdt bash -c 'cd /home/gdt/golddaytrador && python scripts/knox_kill.py on "reason here"'
# check state:
sudo -u gdt bash -c 'cd /home/gdt/golddaytrador && python scripts/knox_kill.py status'
```

## Healthchecks.io wrapper — pre-staged (0 min)

`scripts/dispatch_with_healthcheck.sh` ALREADY committed. Reads `HEALTHCHECKS_DISPATCH_UUID` from `.env.vps`. Retries the ping 3× with 2s backoff and never blocks the actual dispatch if the ping fails (fail-open on monitor, not on trader).

## Smoke test (5 min)

```bash
sudo -u gdt bash /home/gdt/golddaytrador/scripts/vps_smoke_test.sh
```

Checks: venv, secret files present, .env.vps has required keys, systemd units installed, wrapper executable, Python imports resolve, `pytest tests/test_strategy_engine.py` passes. Refuses to green-light if any fail.

## Cutover (10 min)

- [ ] On Windows PowerShell: `Disable-ScheduledTask -TaskName \GoldDayTrader\Dispatch`
- [ ] On VPS: `sudo systemctl enable --now gdt-dispatch.timer gdt-weekly-validation.timer`
- [ ] Force one manual run: `sudo systemctl start gdt-dispatch.service`
- [ ] Verify: `sudo journalctl -u gdt-dispatch.service -n 50`
- [ ] Wait for next :00 or :30 tick — confirm timer fires: `systemctl list-timers gdt-dispatch.timer`
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

**Estimated total time (with pre-staging as of 2026-07-18):** ~1h. Breakdown: 30m pre-flight (account, provisioning, healthchecks.io signup) + 5m bootstrap + 15m scp secrets/state + 5m smoke test + 10m cutover. If bogged, VPS is not a same-day project — hold.

## After cutover: update memory

Replace `hosting_blocker.md` with `hosting_current.md` documenting the VPS setup, systemd units, and healthchecks.io UUIDs.
