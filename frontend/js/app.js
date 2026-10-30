(() => {
  const page = document.body.dataset.page || 'dashboard';
  const content = document.getElementById('page-content');
  if (!content) return;

  const nav = [
    ['dashboard', 'Dashboard', '▦', '/dashboard'],
    ['forecast', 'Forecast', '⌁', '/forecast'],
    ['inventory', 'Inventory', '▤', '/inventory'],
    ['upload', 'Upload data', '⇧', '/upload'],
    ['alerts', 'Alerts', '⚑', '/alerts'],
    ['analytics', 'Analytics', '◷', '/analytics'],
  ];
  const pageTitle = {
    dashboard: 'Dashboard', forecast: 'Forecast', inventory: 'Inventory', upload: 'Upload data',
    alerts: 'Alerts', analytics: 'Analytics', product: 'Product detail', settings: 'Settings',
  }[page] || 'Dashboard';

  const shell = document.createElement('div');
  shell.className = 'app-shell';
  shell.innerHTML = `
    <aside class="sidebar" id="sidebar">
      <a class="brand-lockup" href="/dashboard" aria-label="STOCKORA dashboard">
        <span class="brand-symbol">S</span><span><span class="brand-name">STOCKORA</span><small class="brand-sub">DEMAND INTELLIGENCE</small></span>
      </a>
      <div class="nav-section-label">WORKSPACE</div>
      <nav class="side-nav" aria-label="Main navigation">
        ${nav.map(([key, label, icon, href]) => `<a href="${href}" class="${page === key ? 'active' : ''}" ${page === key ? 'aria-current="page"' : ''}><span class="nav-icon">${icon}</span><span>${label}</span>${key === 'alerts' ? '<span class="nav-spacer"></span>' : ''}</a>`).join('')}
        <a href="/settings" class="${page === 'settings' ? 'active' : ''}"><span class="nav-icon">⚙</span><span>Settings</span></a>
      </nav>
      <div class="sidebar-bottom"><div class="workspace-card"><small>WORKSPACE STATUS</small><strong><i></i> Forecast engine online</strong></div><div class="workspace-footer">STOCKORA · Adaptive planning</div></div>
    </aside>
    <div class="main-area">
      <header class="topbar"><div class="topbar-left"><button id="sidebar-toggle" class="mobile-menu" aria-label="Toggle navigation">☰</button><span class="breadcrumb">Workspace</span><span class="topbar-divider"></span><strong class="breadcrumb">${pageTitle}</strong></div>
        <div class="topbar-right"><span class="topbar-date" id="topbar-date"></span><span class="topbar-divider"></span><span class="owner-chip"><span class="owner-avatar">OW</span> Owner workspace</span></div>
      </header>
      <main class="page-content" id="main-content"></main>
    </div>
    <div class="toast-region" id="toast-region" aria-live="polite"></div>
    <div id="modal-root"></div>
  `;
  document.body.prepend(shell);
  shell.querySelector('#main-content').appendChild(content);

  const dateNode = shell.querySelector('#topbar-date');
  if (dateNode) dateNode.textContent = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date());
  shell.querySelector('#sidebar-toggle').addEventListener('click', () => shell.querySelector('#sidebar').classList.toggle('open'));
  shell.querySelector('#main-content').addEventListener('click', (event) => {
    if (event.target.closest('a')) shell.querySelector('#sidebar').classList.remove('open');
  });

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const number = (value, digits = 0) => Number(value ?? 0).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const statusClass = (status) => String(status || '').toLowerCase().replace(/\s+/g, '-');
  const statusPill = (status) => `<span class="status-pill ${statusClass(status)}">${escapeHtml(status)}</span>`;

  function toast(message, type = 'info') {
    const region = document.getElementById('toast-region');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    region.appendChild(el);
    window.setTimeout(() => el.remove(), 4300);
  }

  function showModal(title, bodyHtml, options = {}) {
    const root = document.getElementById('modal-root');
    root.innerHTML = `<div class="modal-backdrop" id="modal-backdrop"><section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-head"><div><p class="eyebrow">${escapeHtml(options.eyebrow || 'STOCKORA')}</p><h3 id="modal-title">${escapeHtml(title)}</h3></div><button class="modal-close" id="modal-close" aria-label="Close dialog">×</button></div><div>${bodyHtml}</div></section></div>`;
    const close = () => { root.innerHTML = ''; };
    root.querySelector('#modal-close').addEventListener('click', close);
    root.querySelector('#modal-backdrop').addEventListener('click', (event) => { if (event.target.id === 'modal-backdrop') close(); });
    return { root, close };
  }

  function showWhy(item) {
    const unit = escapeHtml(item.unit || 'units');
    const metrics = `
      <div class="modal-metrics">
        <div><span>7-day forecast demand</span><strong>${number(item.forecast_demand)} ${unit}</strong></div>
        <div><span>Safety stock</span><strong>${number(item.safety_stock)} ${unit}</strong></div>
        <div><span>Available stock</span><strong>${number(item.available_stock)} ${unit}</strong></div>
        <div><span>Recommended reorder</span><strong>${number(item.reorder_quantity)} ${unit}</strong></div>
      </div>`;
    showModal(`Why ${item.product_name}?`, `<p class="modal-copy">${escapeHtml(item.why)}</p>${metrics}<p class="fine-print">Formula: max(0, forecast demand + safety stock − current stock − outstanding incoming stock). Only pending, ordered and in-transit deliveries count as incoming stock. Forecast reliability (${escapeHtml(item.forecast_reliability || 'Not evaluated')}) is shown as decision context and does not change the quantity formula.</p>`, { eyebrow: 'EXPLAINABLE RECOMMENDATION' });
  }

  let plotlyLoadPromise;
  function ensurePlotly() {
    if (window.Plotly && typeof window.Plotly.newPlot === 'function') return Promise.resolve();
    if (!plotlyLoadPromise) {
      plotlyLoadPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/static/js/plotly.min.js';
        script.async = true;
        const timeout = window.setTimeout(() => {
          script.remove();
          reject(new Error('Timed out while loading Plotly.js.'));
        }, 10000);
        script.onload = () => {
          window.clearTimeout(timeout);
          if (window.Plotly && typeof window.Plotly.newPlot === 'function') resolve();
          else reject(new Error('Plotly.js loaded without its chart API.'));
        };
        script.onerror = () => {
          window.clearTimeout(timeout);
          reject(new Error('Could not load Plotly.js.'));
        };
        document.head.appendChild(script);
      }).catch((error) => {
        plotlyLoadPromise = null;
        throw error;
      });
    }
    return plotlyLoadPromise;
  }

  async function renderForecastChart(targetId, data, errorMessage = 'Unable to load chart.') {
    const target = document.getElementById(targetId);
    if (!target) return false;
    target.style.minHeight = '280px';
    const history = data.history || [];
    const forecast = data.forecast || [];
    if (!history.length || !forecast.length) {
      target.innerHTML = '<div class="empty-state">Not enough data to draw this forecast.</div>';
      return false;
    }
    const last = history[history.length - 1];
    const futureX = [last.date, ...forecast.map((item) => item.date)];
    const futureY = [Number(last.quantity_sold), ...forecast.map((item) => Number(item.predicted_quantity))];
    const forecastStart = forecast[0].date;
    const layout = {
      autosize: true, height: target.clientWidth < 520 ? 260 : 315,
      margin: { l: 43, r: 18, t: 20, b: 44 },
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'DM Sans, sans-serif', color: '#6B7280', size: 10 },
      xaxis: { gridcolor: 'rgba(229,231,235,.8)', linecolor: '#E5E7EB', tickfont: { size: 9 }, tickformat: '%b %d', zeroline: false },
      yaxis: { title: { text: `Quantity (${data.unit || 'units'})`, font: { size: 9, color: '#6B7280' } }, gridcolor: 'rgba(229,231,235,.8)', linecolor: '#E5E7EB', tickfont: { size: 9 }, rangemode: 'tozero', zeroline: false },
      legend: { orientation: 'h', x: 0, y: 1.14, font: { size: 9 } },
      shapes: [{ type: 'line', x0: forecastStart, x1: forecastStart, y0: 0, y1: 1, yref: 'paper', line: { color: '#EA580C', width: 1, dash: 'dot' } }],
      annotations: [{ x: forecastStart, y: 1, yref: 'paper', text: 'FORECAST START', showarrow: false, xanchor: 'left', yanchor: 'bottom', font: { size: 8, color: '#EA580C' }, xshift: 5 }],
      hovermode: 'x unified',
    };
    const traces = [
      { x: history.map((item) => item.date), y: history.map((item) => Number(item.quantity_sold)), type: 'scatter', mode: 'lines', name: 'Actual demand', line: { color: '#166534', width: 2.1 }, hovertemplate: '%{x|%b %d}<br>Actual: %{y:.1f}<extra></extra>' },
      { x: futureX, y: futureY, type: 'scatter', mode: 'lines+markers', name: '7-day forecast', line: { color: '#EA580C', width: 2.2, dash: 'dash' }, marker: { size: 5, color: '#EA580C' }, hovertemplate: '%{x|%b %d}<br>Forecast: %{y:.1f}<extra></extra>' },
    ];
    try {
      target.replaceChildren();
      await ensurePlotly();
      await window.Plotly.newPlot(target, traces, layout, { responsive: true, displayModeBar: false, scrollZoom: false });
      return true;
    } catch (error) {
      console.error(error);
      target.innerHTML = `<div class="empty-state">${escapeHtml(errorMessage)}</div>`;
      return false;
    }
  }

  window.StockoraUI = { escapeHtml, number, statusPill, statusClass, toast, showModal, showWhy, ensurePlotly, renderForecastChart };
})();
