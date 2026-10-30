(() => {
  const api = window.StockoraAPI;
  const ui = window.StockoraUI;
  async function init() {
    const counts = document.getElementById('alert-counts');
    const list = document.getElementById('alert-list');
    try {
      const data = await api.get('/api/alerts');
      counts.innerHTML = `
        <div class="alert-count high"><span>High risk</span><strong>${ui.number(data.high)}</strong></div>
        <div class="alert-count medium"><span>Medium risk</span><strong>${ui.number(data.medium)}</strong></div>
        <div class="alert-count normal"><span>Normal</span><strong>${ui.number(data.normal)}</strong></div>`;
      if (!data.alerts.length) {
        list.innerHTML = '<div class="panel empty-state">No product alerts are available yet. Generate forecasts to assess stock risk.</div>';
        return;
      }
      list.innerHTML = data.alerts.map((item) => `
        <article class="alert-card ${ui.escapeHtml(item.risk)}">
          <div class="alert-card-icon">${item.risk === 'high' ? '!' : item.risk === 'medium' ? '↗' : '✓'}</div>
          <div class="alert-card-copy"><h3>${ui.escapeHtml(item.product_name)} <span class="status-pill ${ui.escapeHtml(item.risk)}">${ui.escapeHtml(item.risk)} risk</span></h3>
            <p>${ui.escapeHtml(item.message)}</p><div class="alert-card-meta"><span>7-day demand: ${ui.number(item.forecast_demand)} ${ui.escapeHtml(item.unit)}</span><span>Reorder: ${ui.number(item.reorder_quantity)} ${ui.escapeHtml(item.unit)}</span><span>Forecast: ${ui.escapeHtml(item.forecast_reliability || '—')}</span></div>
          </div><a class="action-link" href="/product?id=${encodeURIComponent(item.product_id)}">Details</a>
        </article>`).join('');
    } catch (error) {
      list.innerHTML = `<div class="panel empty-state">${ui.escapeHtml(error.message)}</div>`;
      ui.toast(error.message, 'error');
    }
  }
  document.addEventListener('DOMContentLoaded', init);
})();
