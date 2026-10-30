(() => {
  const api = window.StockoraAPI;
  const ui = window.StockoraUI;
  const select = document.getElementById('detail-product-select');
  const target = document.getElementById('product-detail');
  let activeData = null;

  function render(data) {
    activeData = data;
    const product = data.product;
    const forecast = data.forecast;
    const stock = data.inventory;
    const currency = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(product.price));
    target.className = '';
    target.innerHTML = `
      <section class="product-hero panel"><div><p class="eyebrow">${ui.escapeHtml(product.category.toUpperCase())} · ${ui.escapeHtml(product.product_id)}</p><h2>${ui.escapeHtml(product.product_name)}</h2><p class="muted small">Unit price ${currency} · sold in ${ui.escapeHtml(product.unit)}</p></div><span class="status-badge ${ui.statusClass(forecast.reliability)}">${ui.escapeHtml(forecast.reliability)} forecast</span></section>
      <section class="product-detail-grid">
        <article class="panel product-stats"><p class="eyebrow">DEMAND PERFORMANCE</p><h3>Forecast summary</h3><div class="detail-stat-grid"><div><span>Historical average</span><strong>${ui.number(forecast.historical_average, 1)}</strong></div><div><span>7-day forecast</span><strong>${ui.number(forecast.forecast_total, 1)}</strong></div><div><span>MAE</span><strong>${ui.number(forecast.mae, 2)}</strong></div><div><span>RMSE</span><strong>${ui.number(forecast.rmse, 2)}</strong></div></div><p class="fine-print">${ui.escapeHtml(forecast.reliability_reason)}</p><a class="text-link" href="/forecast?product=${encodeURIComponent(product.product_id)}">Open forecast page →</a></article>
        <article class="panel product-stats"><p class="eyebrow">INVENTORY POSITION</p><h3>${ui.escapeHtml(stock.recommendation)}</h3><div class="detail-stat-grid"><div><span>Current stock</span><strong>${ui.number(stock.current_stock)}</strong></div><div><span>Safety stock</span><strong>${ui.number(stock.safety_stock)}</strong></div><div><span>Incoming stock</span><strong>${ui.number(stock.incoming_stock)}</strong></div><div><span>Forecast demand</span><strong>${ui.number(stock.forecast_demand)}</strong></div></div><div class="detail-reorder"><span>Recommended reorder</span><strong>${ui.number(stock.reorder_quantity)} <small>${ui.escapeHtml(stock.unit)}</small></strong></div><button class="button button-secondary" id="product-why">Why this recommendation?</button></article>
      </section>
      <article class="panel chart-panel product-chart"><div class="panel-heading"><div><p class="eyebrow">SALES HISTORY + FORECAST</p><h2>${ui.escapeHtml(product.product_name)} demand timeline</h2></div></div><div id="product-demand-chart" class="chart-area"></div></article>`;
    ui.renderForecastChart('product-demand-chart', forecast);
    document.getElementById('product-why').addEventListener('click', () => ui.showWhy(stock));
  }

  async function load(productId) {
    if (!productId) return;
    target.className = 'loading-state panel';
    target.textContent = 'Loading product details…';
    try {
      const data = await api.get(`/api/product/${encodeURIComponent(productId)}`);
      render(data);
      select.value = productId;
    } catch (error) {
      target.className = 'panel empty-state';
      target.textContent = error.message;
      ui.toast(error.message, 'error');
    }
  }

  async function init() {
    try {
      const data = await api.get('/api/products');
      select.innerHTML = data.products.map((product) => `<option value="${ui.escapeHtml(product.product_id)}">${ui.escapeHtml(product.product_name)}</option>`).join('');
      const requested = new URLSearchParams(window.location.search).get('id');
      const initial = requested && data.products.some((product) => product.product_id === requested) ? requested : (data.products[0] && data.products[0].product_id);
      select.addEventListener('change', () => load(select.value));
      await load(initial);
    } catch (error) {
      target.textContent = error.message;
      ui.toast(error.message, 'error');
    }
  }
  document.addEventListener('DOMContentLoaded', init);
})();
