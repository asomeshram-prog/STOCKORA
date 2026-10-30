(() => {
  const api = window.StockoraAPI;
  const ui = window.StockoraUI;
  let inventoryItems = new Map();

  function renderInventoryRows(items) {
    const tbody = document.getElementById('dashboard-inventory');
    inventoryItems = new Map(items.map((item) => [item.product_id, item]));
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No inventory records found.</td></tr>';
      return;
    }
    tbody.innerHTML = items.map((item) => `
      <tr>
        <td><a class="product-cell" href="/product?id=${encodeURIComponent(item.product_id)}"><span class="product-token">${ui.escapeHtml(item.product_id.slice(-2))}</span><span><strong>${ui.escapeHtml(item.product_name)}</strong><small>${ui.escapeHtml(item.category)}</small></span></a></td>
        <td class="numeric">${ui.number(item.current_stock)}</td><td class="numeric">${ui.number(item.incoming_stock)}</td>
        <td class="numeric">${ui.number(item.forecast_demand)}</td><td class="numeric ${item.reorder_quantity > 0 ? 'risk-value' : 'positive-value'}">${ui.number(item.reorder_quantity)}</td>
        <td>${ui.statusPill(item.risk)}</td><td><button class="action-link" data-why="${ui.escapeHtml(item.product_id)}">Why?</button></td>
      </tr>`).join('');
  }

  function renderAttention(items) {
    const target = document.getElementById('dashboard-attention');
    const atRisk = items.filter((item) => item.risk !== 'normal').slice(0, 5);
    if (!atRisk.length) {
      target.innerHTML = '<div class="empty-state">All tracked products currently have enough stock cover.</div>';
      return;
    }
    target.className = 'insight-list';
    target.innerHTML = atRisk.map((item) => `
      <div class="attention-item"><span class="attention-symbol ${item.risk}">${item.risk === 'high' ? '!' : '↗'}</span>
        <div class="attention-copy"><strong>${ui.escapeHtml(item.product_name)}</strong><small>${item.risk === 'high' ? 'Critical stock gap' : 'Reorder recommended'}</small></div>
        <div class="attention-qty">${ui.number(item.reorder_quantity)}<small style="display:block;color:#6B7280;font:9px 'DM Sans'">to order</small></div>
      </div>`).join('');
  }

  async function loadChart(productId) {
    const data = await api.get(`/api/forecast/${encodeURIComponent(productId)}`);
    ui.renderForecastChart('demandChart', data);
    document.getElementById('chart-average').textContent = `${ui.number(data.historical_average, 1)} / day`;
    document.getElementById('chart-total').textContent = `${ui.number(data.forecast_total, 1)} units`;
    document.getElementById('chart-mae').textContent = ui.number(data.mae, 2);
    document.getElementById('chart-rmse').textContent = ui.number(data.rmse, 2);
    const reliability = document.getElementById('chart-reliability');
    reliability.textContent = data.reliability;
    reliability.className = `status-text ${ui.statusClass(data.reliability)}`;
  }

  async function init() {
    try {
      const [dashboard, productsData] = await Promise.all([api.get('/api/dashboard'), api.get('/api/products')]);
      document.getElementById('kpi-products').textContent = ui.number(dashboard.total_products);
      document.getElementById('kpi-forecasted').textContent = ui.number(dashboard.forecasted_products);
      document.getElementById('kpi-risk').textContent = ui.number(dashboard.products_at_risk);
      document.getElementById('kpi-reorder').textContent = ui.number(dashboard.reorder_required);
      document.getElementById('kpi-performance').textContent = dashboard.overall_forecast_performance === null ? '—' : `${ui.number(dashboard.overall_forecast_performance, 1)}%`;
      document.getElementById('kpi-performance-note').textContent = dashboard.overall_forecast_performance === null ? 'Generate forecasts to evaluate' : 'Error-based accuracy estimate';
      renderInventoryRows(dashboard.inventory_preview || []);
      renderAttention(dashboard.inventory_preview || []);

      const select = document.getElementById('dashboard-product-select');
      select.innerHTML = productsData.products.map((p) => `<option value="${ui.escapeHtml(p.product_id)}">${ui.escapeHtml(p.product_name)}</option>`).join('');
      if (productsData.products.length) {
        await loadChart(productsData.products[0].product_id);
      }
      select.addEventListener('change', () => loadChart(select.value).catch((error) => ui.toast(error.message, 'error')));
      document.getElementById('dashboard-inventory').addEventListener('click', (event) => {
        const button = event.target.closest('[data-why]');
        if (button) {
          const item = inventoryItems.get(button.dataset.why);
          if (item) ui.showWhy(item);
        }
      });
    } catch (error) {
      ui.toast(error.message, 'error');
      document.getElementById('dashboard-attention').innerHTML = `<div class="empty-state">${ui.escapeHtml(error.message)}</div>`;
    }
  }
  document.addEventListener('DOMContentLoaded', init);
})();
