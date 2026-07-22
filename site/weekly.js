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

async function init() {
  const [current, history] = await Promise.all([
    loadJSON(CURRENT_URL),
    loadJSON(HISTORY_URL),
  ]);
  renderCurrentCall(current);
  renderSignalDrivers(current);
  renderTrackSummary(history);
  renderHistory(history);
}

init();
