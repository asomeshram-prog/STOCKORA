(() => {
  const api = window.StockoraAPI;
  const ui = window.StockoraUI;
  async function init() {
    try {
      const data = await api.get('/api/settings');
      document.getElementById('setting-version').textContent = data.version;
      document.getElementById('setting-database').textContent = `${data.database.database} · ${data.database.file}`;
      document.getElementById('setting-products').textContent = ui.number(data.product_count);
      document.getElementById('setting-sales').textContent = ui.number(data.sales_records);
      document.getElementById('setting-model').textContent = data.forecast_model;
      document.getElementById('setting-synthetic').textContent = data.synthetic_data_notice;
    } catch (error) {
      ui.toast(error.message, 'error');
    }
  }
  document.addEventListener('DOMContentLoaded', init);
})();
