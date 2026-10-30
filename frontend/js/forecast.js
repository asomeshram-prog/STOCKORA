(() => {
  const api = window.StockoraAPI;
  const ui = window.StockoraUI;
  const select = document.getElementById('forecast-product');
  const button = document.getElementById('generate-forecast');
  const feedback = document.getElementById('forecast-feedback');

  const dateLabel = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });

  async function render(data) {
    document.getElementById('forecast-results').classList.remove('hidden');
    document.getElementById('forecast-product-name').textContent = `· ${data.product_name}`;
    document.getElementById('forecast-average').textContent = ui.number(data.historical_average, 1);
    document.getElementById('forecast-total').textContent = ui.number(data.forecast_total, 1);
    document.getElementById('forecast-mae').textContent = ui.number(data.mae, 2);
    document.getElementById('forecast-rmse').textContent = ui.number(data.rmse, 2);
    const badge = document.getElementById('forecast-reliability-badge');
    badge.textContent = data.reliability;
    badge.className = `status-badge ${ui.statusClass(data.reliability)}`;
    document.getElementById('reliability-title').textContent = `${data.reliability} forecast`;
    document.getElementById('reliability-reason').textContent = data.reliability_reason;
    document.getElementById('forecast-days').innerHTML = data.forecast.map((item, index) => `
      <article class="forecast-day-card"><span>DAY ${index + 1}</span><strong>${ui.number(item.predicted_quantity, 1)}</strong><small>${dateLabel(item.date)}</small><span class="unit">${ui.escapeHtml(data.unit)}</span></article>`).join('');
    document.getElementById('forecast-date-range').textContent = `${dateLabel(data.forecast[0].date)} – ${dateLabel(data.forecast[data.forecast.length - 1].date)}`;
    await ui.renderForecastChart('forecastChart', data, 'Unable to load forecast chart.');
    const stock = data.inventory;
    document.getElementById('forecast-reorder-text').textContent = stock.reorder_quantity > 0
      ? `${stock.product_name}: ${ui.number(stock.reorder_quantity)} ${stock.unit} recommended. ${stock.recommendation}.`
      : `${stock.product_name}: no reorder is currently required. Available stock covers forecast demand plus the safety buffer.`;
    document.getElementById('forecast-inventory-link').href = `/inventory`;
  }

  async function loadExisting(productId) {
    try {
      const data = await api.get(`/api/forecast/${encodeURIComponent(productId)}`);
      await render(data);
      feedback.textContent = 'Showing the latest saved forecast. Generate again to retrain the model on current sales history.';
      feedback.className = 'form-feedback';
    } catch (error) {
      const results = document.getElementById('forecast-results');
      const chart = document.getElementById('forecastChart');
      results.classList.remove('hidden');
      chart.style.minHeight = '280px';
      chart.innerHTML = '<div class="empty-state">Unable to load forecast chart.</div>';
      console.error(error);
      feedback.textContent = error.message;
      feedback.className = 'form-feedback error';
    }
  }

  async function generate() {
    if (!select.value) return;
    button.disabled = true;
    button.textContent = 'Training model…';
    feedback.textContent = 'Evaluating historical demand and fitting the model.';
    feedback.className = 'form-feedback';
    try {
      const data = await api.post(`/api/forecast/${encodeURIComponent(select.value)}`);
      await render(data);
      feedback.textContent = `Forecast generated using ${data.training_days} training days and ${data.evaluation_days} chronological holdout days.`;
      feedback.className = 'form-feedback success';
      ui.toast(`Forecast updated for ${data.product_name}.`, 'success');
    } catch (error) {
      feedback.textContent = error.message;
      feedback.className = 'form-feedback error';
      ui.toast(error.message, 'error');
    } finally {
      button.disabled = false;
      button.innerHTML = 'Generate forecast <span>→</span>';
    }
  }

  async function init() {
    try {
      const data = await api.get('/api/products');
      select.innerHTML = data.products.map((product) => `<option value="${ui.escapeHtml(product.product_id)}">${ui.escapeHtml(product.product_name)} · ${ui.escapeHtml(product.category)}</option>`).join('');
      const requested = new URLSearchParams(window.location.search).get('product');
      if (requested && data.products.some((product) => product.product_id === requested)) select.value = requested;
      button.addEventListener('click', generate);
      select.addEventListener('change', () => loadExisting(select.value));
      if (select.value) await loadExisting(select.value);
    } catch (error) {
      feedback.textContent = error.message;
      feedback.className = 'form-feedback error';
    }
  }
  document.addEventListener('DOMContentLoaded', init);
})();
