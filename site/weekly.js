// FAR Weekly Gold Read — client for the weekly page.
// Loads data/far_weekly_current.json and data/far_weekly_history.json,
// renders current call + track record + history.

const CURRENT_URL = './data/far_weekly_current.json';
const HISTORY_URL = './data/far_weekly_history.json';

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child == null) continue;
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

function metric(label, value, cls = '') {
  return el('div', { class: 'metric' },
    el('div', { class: 'metric-label' }, label),
    el('div', { class: `metric-value ${cls}` }, value)
  );
}

function directionClass(direction) {
  if (direction === 'LONG') return 'up';
  if (direction === 'SHORT') return 'down';
  return '';
}

function directionDotClass(direction) {
  if (direction === 'LONG') return 'dot-up';
  if (direction === 'SHORT') return 'dot-down';
  return 'dot-unknown';
}

async function loadJSON(url) {
  try {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
}

function renderCurrentCall(call) {
  const container = document.getElementById('current-call');
  const weekHint = document.getElementById('call-week-hint');
  const statusEl = document.getElementById('signal-status');
  const dotEl = document.getElementById('signal-dot');

  if (!call || !call.direction) {
    container.innerHTML = '<span class="muted">No call published yet. Publisher fires Sunday 22:00 UTC.</span>';
    return;
  }

  weekHint.textContent = `Week of ${call.week_of} → ${call.week_end} · published ${call.published_utc?.slice(0,10) || 'N/A'}`;

  statusEl.textContent = call.direction === 'FLAT'
    ? 'FLAT — no position this week'
    : `${call.direction} — entry ~${call.entry_approx}, stop ${call.stop_price}`;
  dotEl.className = `dot ${directionDotClass(call.direction)}`;

  container.innerHTML = '';
  const metrics = el('div', { class: 'metrics' });

  metrics.appendChild(metric('Direction', call.direction, directionClass(call.direction)));

  if (call.direction !== 'FLAT') {
    metrics.appendChild(metric('Entry (approx)', `$${call.entry_approx}`));
    metrics.appendChild(metric('Stop', `$${call.stop_price}`, 'down'));
    metrics.appendChild(metric('Exit', 'Friday close'));
    metrics.appendChild(metric('ATR(20d)', `$${call.atr_20d}`));
  } else {
    metrics.appendChild(metric('Reason', call.message || 'Signal filters disagreed'));
  }

  container.appendChild(metrics);

  if (call.confidence_disclaimer) {
    container.appendChild(el('p', { class: 'hint', style: 'margin-top:18px;' }, call.confidence_disclaimer));
  }
}

function renderSignalDrivers(call) {
  const container = document.getElementById('signal-drivers');
  if (!call || !call.signal_components) {
    container.innerHTML = '<span class="muted">no signal data</span>';
    return;
  }
  const sc = call.signal_components;
  container.innerHTML = '';

  const m20 = sc.M20_pct == null ? '—' : `${sc.M20_pct >= 0 ? '+' : ''}${sc.M20_pct}%`;
  const m60 = sc.M60_pct == null ? '—' : `${sc.M60_pct >= 0 ? '+' : ''}${sc.M60_pct}%`;
  const macross = sc.MA10_above_MA40 == null ? '—' : (sc.MA10_above_MA40 ? '10d > 40d' : '10d < 40d');
  const rybps = sc.RY_chg_20d_bps == null ? '—' : `${sc.RY_chg_20d_bps >= 0 ? '+' : ''}${sc.RY_chg_20d_bps} bps`;

  container.appendChild(metric('4-week momentum', m20, sc.M20_pct >= 0 ? 'up' : 'down'));
  container.appendChild(metric('12-week momentum', m60, sc.M60_pct >= 0 ? 'up' : 'down'));
  container.appendChild(metric('MA trend', macross, sc.MA10_above_MA40 ? 'up' : 'down'));
  container.appendChild(metric('Real yield Δ 4w', rybps, sc.RY_chg_20d_bps < 0 ? 'up' : 'down'));
}

function renderTrackSummary(history) {
  const container = document.getElementById('track-summary');
  if (!history) {
    container.innerHTML = '<span class="muted">no track record yet</span>';
    return;
  }
  container.innerHTML = '';
  const n = history.resolved_calls || 0;
  container.appendChild(metric('Resolved calls', String(n)));
  container.appendChild(metric('Win rate', n ? `${history.win_rate_pct}%` : '—',
    (history.win_rate_pct >= 50) ? 'up' : (n ? 'down' : '')));
  container.appendChild(metric('Cumulative return',
    n ? `${history.cumulative_return_pct >= 0 ? '+' : ''}${history.cumulative_return_pct}%` : '—',
    (history.cumulative_return_pct >= 0) ? 'up' : 'down'));
  container.appendChild(metric('Wins / Losses', n ? `${history.wins} / ${history.losses}` : '—'));
}

function renderHistory(history) {
  const container = document.getElementById('call-history');
  if (!history || !history.history || history.history.length === 0) {
    container.innerHTML = '<span class="muted">No calls published yet — first call fires next Sunday.</span>';
    return;
  }

  container.innerHTML = '';
  const rows = [...history.history].reverse();
  for (const call of rows) {
    const row = el('div', { class: 'alert-row' });

    const dirCls = directionClass(call.direction);
    row.appendChild(el('div', { class: 'alert-session' }, call.direction || '—'));

    const summary = el('div', {},
      `Week ${call.week_of} → ${call.week_end}`,
      call.entry_approx ? el('span', { class: 'muted' }, ` · entry $${call.entry_approx} · stop $${call.stop_price}`) : null,
    );
    row.appendChild(summary);

    const outcome = call.outcome;
    if (outcome && outcome.result === 'resolved') {
      const ret = outcome.net_return_pct;
      const cls = ret >= 0 ? 'up' : 'down';
      row.appendChild(el('div', { class: `alert-ts ${cls}` },
        `${ret >= 0 ? '+' : ''}${ret}% (${outcome.exit_reason})`));
    } else if (outcome && outcome.result === 'FLAT_no_position') {
      row.appendChild(el('div', { class: 'alert-ts muted' }, 'FLAT'));
    } else {
      row.appendChild(el('div', { class: 'alert-ts muted' }, 'pending'));
    }
    container.appendChild(row);
  }
}

function renderYearTable(curve) {
  const container = document.getElementById('year-table');
  if (!container || !curve || !curve.year_stats) return;
  container.innerHTML = '';
  const maxAbs = Math.max(...curve.year_stats.map(y => Math.abs(y.total_pnl)));

  const header = el('div', { class: 'year-row muted' },
    el('div', {}, 'Year'),
    el('div', {}, 'Calls'),
    el('div', {}, 'Win %'),
    el('div', {}, 'P&L'),
    el('div', {}, ''),
  );
  container.appendChild(header);

  for (const y of curve.year_stats) {
    const cls = y.total_pnl >= 0 ? 'up' : 'down';
    const barPct = maxAbs > 0 ? Math.abs(y.total_pnl) / maxAbs * 100 : 0;
    const barFillStyle = y.total_pnl >= 0
      ? `left: 50%; width: ${barPct/2}%;`
      : `right: 50%; width: ${barPct/2}%;`;

    const row = el('div', { class: 'year-row' },
      el('div', { class: 'year-year' }, y.year),
      el('div', {}, String(y.trades)),
      el('div', {}, `${y.win_rate}%`),
      el('div', { class: cls }, `${y.total_pnl >= 0 ? '+' : ''}$${y.total_pnl.toLocaleString()}`),
      el('div', { class: 'year-bar' },
        el('div', { class: `year-bar-fill ${cls}`, style: barFillStyle }),
      ),
    );
    container.appendChild(row);
  }
}

function renderEquityChart(curve) {
  const canvas = document.getElementById('equity-chart');
  if (!canvas || !curve || !curve.equity_curve || curve.equity_curve.length === 0) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const w = Math.floor(rect.width * dpr);
  const h = Math.floor(360 * dpr);
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const padding = { top: 20, right: 40, bottom: 30, left: 60 };
  const W = rect.width;
  const H = 360;

  const eq = curve.equity_curve;
  const cums = eq.map(p => p.cum_pct);
  const minY = Math.min(...cums, 0);
  const maxY = Math.max(...cums, 0);
  const rangeY = maxY - minY || 1;

  // Grid lines
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
  for (let g = 0; g <= 4; g++) {
    const y = padding.top + (H - padding.top - padding.bottom) * g / 4;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(W - padding.right, y);
    ctx.stroke();
  }

  // Zero line
  const zeroY = padding.top + (maxY / rangeY) * (H - padding.top - padding.bottom);
  ctx.strokeStyle = 'rgba(255,255,255,0.2)';
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(padding.left, zeroY);
  ctx.lineTo(W - padding.right, zeroY);
  ctx.stroke();
  ctx.setLineDash([]);

  // Equity line
  ctx.strokeStyle = '#f2c94c';
  ctx.lineWidth = 2;
  ctx.beginPath();
  const chartW = W - padding.left - padding.right;
  const chartH = H - padding.top - padding.bottom;
  for (let i = 0; i < eq.length; i++) {
    const x = padding.left + (i / (eq.length - 1)) * chartW;
    const y = padding.top + ((maxY - eq[i].cum_pct) / rangeY) * chartH;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Fill under line
  ctx.lineTo(padding.left + chartW, zeroY);
  ctx.lineTo(padding.left, zeroY);
  ctx.closePath();
  ctx.fillStyle = 'rgba(242,201,76,0.08)';
  ctx.fill();

  // Y-axis labels
  ctx.fillStyle = '#8a8f99';
  ctx.font = '12px system-ui';
  ctx.textAlign = 'right';
  for (let g = 0; g <= 4; g++) {
    const v = maxY - (rangeY * g / 4);
    const y = padding.top + (H - padding.top - padding.bottom) * g / 4;
    ctx.fillText(`${v >= 0 ? '+' : ''}${v.toFixed(1)}%`, padding.left - 8, y + 4);
  }

  // X-axis labels — first, middle, last year
  ctx.textAlign = 'center';
  const positions = [0, Math.floor(eq.length / 2), eq.length - 1];
  for (const idx of positions) {
    const x = padding.left + (idx / (eq.length - 1)) * chartW;
    ctx.fillText(eq[idx].date.slice(0, 4), x, H - 10);
  }
}

function updatePositionCalc(call) {
  const out = document.getElementById('pos-output');
  if (!out || !call) return;
  const accountEl = document.getElementById('pos-account');
  const riskEl = document.getElementById('pos-risk-pct');
  if (!accountEl || !riskEl) return;
  const account = parseFloat(accountEl.value) || 0;
  const riskPct = parseFloat(riskEl.value) || 0;
  const riskDollars = account * riskPct / 100;

  if (call.direction === 'FLAT') {
    out.innerHTML = '<span class="muted">FLAT call this week — no position to size.</span>';
    return;
  }
  if (!call.entry_approx || !call.stop_price) {
    out.innerHTML = '<span class="muted">Insufficient signal data.</span>';
    return;
  }
  const entry = call.entry_approx;
  const stop = call.stop_price;
  const perOzRisk = Math.abs(entry - stop);
  const gcRiskPerContract = perOzRisk * 100;
  const mgcRiskPerContract = perOzRisk * 10;
  const gldPricePerShare = entry / 10;  // ~$400/share at $4000 gold
  const gldRiskPerShare = perOzRisk / 10;

  const gcContracts = Math.floor(riskDollars / gcRiskPerContract);
  const mgcContracts = Math.floor(riskDollars / mgcRiskPerContract);
  const gldShares = Math.floor(riskDollars / gldRiskPerShare);
  const gldCost = gldShares * gldPricePerShare;

  const notionalGc = gcContracts * entry * 100;
  const notionalMgc = mgcContracts * entry * 10;

  out.innerHTML = `
    <div class="metrics">
      <div class="metric">
        <div class="metric-label">Risk per oz</div>
        <div class="metric-value">$${perOzRisk.toFixed(2)}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Risk budget</div>
        <div class="metric-value">$${riskDollars.toLocaleString(undefined, {maximumFractionDigits: 0})}</div>
      </div>
    </div>
    <div style="margin-top: 20px;">
      <div class="pos-row">
        <span class="pos-inst">GC futures</span>
        <span class="pos-count">${gcContracts} contract${gcContracts !== 1 ? 's' : ''}</span>
        <span class="muted">notional $${notionalGc.toLocaleString(undefined, {maximumFractionDigits: 0})} · risk $${(gcContracts * gcRiskPerContract).toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
      </div>
      <div class="pos-row">
        <span class="pos-inst">MGC micro</span>
        <span class="pos-count">${mgcContracts} contract${mgcContracts !== 1 ? 's' : ''}</span>
        <span class="muted">notional $${notionalMgc.toLocaleString(undefined, {maximumFractionDigits: 0})} · risk $${(mgcContracts * mgcRiskPerContract).toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
      </div>
      <div class="pos-row">
        <span class="pos-inst">GLD ETF</span>
        <span class="pos-count">${gldShares} share${gldShares !== 1 ? 's' : ''}</span>
        <span class="muted">notional $${gldCost.toLocaleString(undefined, {maximumFractionDigits: 0})} · risk $${(gldShares * gldRiskPerShare).toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
      </div>
    </div>
    ${gcContracts < 1 && mgcContracts < 1 ? '<p class="hint" style="margin-top: 12px; color: var(--down);">Account too small even for MGC micro at this risk %. Consider GLD ETF or higher risk % (max 2% recommended).</p>' : ''}
  `;
}

let _currentCall = null;
function attachCalcListeners() {
  ['pos-account', 'pos-risk-pct'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', () => updatePositionCalc(_currentCall));
  });
}

async function init() {
  const [current, history, curve] = await Promise.all([
    loadJSON(CURRENT_URL),
    loadJSON(HISTORY_URL),
    loadJSON('./data/far_weekly_backtest_curve.json'),
  ]);
  _currentCall = current;
  renderCurrentCall(current);
  renderSignalDrivers(current);
  renderTrackSummary(history);
  renderHistory(history);
  renderYearTable(curve);
  renderEquityChart(curve);
  updatePositionCalc(current);
  attachCalcListeners();
}

init();
window.addEventListener('resize', () => {
  loadJSON('./data/far_weekly_backtest_curve.json').then(renderEquityChart);
});
