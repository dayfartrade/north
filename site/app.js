// Point at the FastAPI backend. Change per environment.
const API = window.API_BASE || "http://localhost:8000";

const fmt = {
  usd: (n) => n === null || n === undefined ? "—" :
              (n >= 0 ? "+" : "") + "$" + Math.abs(n).toLocaleString(undefined, {maximumFractionDigits: 0}),
  pct: (n) => n === null || n === undefined ? "—" : n.toFixed(1) + "%",
  int: (n) => n === null || n === undefined ? "—" : String(n),
  time: (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toISOString().slice(0, 16).replace("T", " ") + "Z";
  },
};

async function fetchJSON(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

function signClass(n) { return n > 0 ? "up" : n < 0 ? "down" : ""; }

function metric(label, value, cls) {
  return `<div class="metric">
    <div class="metric-label">${label}</div>
    <div class="metric-value ${cls || ""}">${value}</div>
  </div>`;
}

async function loadHealth() {
  const dot = document.getElementById("bot-dot");
  const txt = document.getElementById("bot-status");
  try {
    const h = await fetchJSON("/health");
    if (h.bot_online) {
      dot.className = "dot dot-up";
      txt.textContent = `Bot online · last dispatch ${h.last_dispatch_age_min} min ago`;
    } else {
      dot.className = "dot dot-down";
      txt.textContent = `Bot offline · last dispatch ${h.last_dispatch_age_min} min ago`;
    }
  } catch (e) {
    dot.className = "dot dot-down";
    txt.textContent = "Bot status unavailable";
  }
}

async function loadLive() {
  const el = document.getElementById("live");
  try {
    const s = await fetchJSON("/stats/live");
    if (!s.trades_taken) {
      el.innerHTML = `<span class="muted">${s.note || "No live trades yet."}</span>`;
      return;
    }
    el.innerHTML = [
      metric("Trades", fmt.int(s.trades_taken)),
      metric("Win rate", fmt.pct(s.win_rate_pct), signClass(s.win_rate_pct - 50)),
      metric("Net P&L", fmt.usd(s.net_pnl_usd), signClass(s.net_pnl_usd)),
      metric("Trades/day", (s.trades_per_day || 0).toFixed(2)),
    ].join("");
  } catch (e) {
    el.innerHTML = `<span class="muted">Unavailable.</span>`;
  }
}

async function loadHistorical() {
  const el = document.getElementById("historical");
  try {
    const s = await fetchJSON("/stats/historical");
    const verdict = s.verdict === "DEPLOY-READY" ? "up" : "down";
    el.innerHTML = [
      metric("Verdict", s.verdict, verdict),
      metric("Tier", s.size_tag || "—"),
      metric("Backtest n", fmt.int(s.n_trades)),
    ].join("") +
    `<p class="hint" style="margin-top:10px">Last validated ${fmt.time(s.last_run_utc)}</p>`;
  } catch (e) {
    el.innerHTML = `<span class="muted">Unavailable.</span>`;
  }
}

async function loadAlerts() {
  const el = document.getElementById("alerts");
  try {
    const s = await fetchJSON("/alerts/recent?limit=5");
    if (!s.alerts || !s.alerts.length) {
      el.innerHTML = `<span class="muted">${s.note || "No recent PLAN alerts."}</span>`;
      return;
    }
    el.innerHTML = s.alerts.map(a => `
      <div class="alert-row">
        <span class="alert-session">${a.session}</span>
        <span>Trend ${a.trend} · range $${(a.or_range || 0).toFixed(2)} · R:R ${(a.rr_ratio || 0).toFixed(1)}</span>
        <span class="alert-ts">${fmt.time(a.ts_sent_utc)}</span>
      </div>`).join("");
  } catch (e) {
    el.innerHTML = `<span class="muted">Unavailable.</span>`;
  }
}

async function loadDisclaimer() {
  try {
    const d = await fetchJSON("/disclaimer");
    document.getElementById("disclaimer").textContent = d.text;
  } catch (e) { /* leave the loading string */ }
}

loadHealth();
loadLive();
loadHistorical();
loadAlerts();
loadDisclaimer();
setInterval(loadHealth, 60_000);      // heartbeat every 60s
setInterval(loadLive, 5 * 60_000);    // 5-min for stats
setInterval(loadAlerts, 5 * 60_000);
