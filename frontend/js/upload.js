(() => {
  const api = window.StockoraAPI;
  const ui = window.StockoraUI;
  const form = document.getElementById('upload-form');
  const fileInput = document.getElementById('sales-file');
  const fileLabel = document.getElementById('selected-file');
  const submit = document.getElementById('upload-submit');
  const feedback = document.getElementById('upload-feedback');

  const metric = (label, value) => `<div class="validation-item"><span>${ui.escapeHtml(label)}</span><strong>${ui.escapeHtml(value ?? '—')}</strong></div>`;

  function showReport(data, success, message) {
    const section = document.getElementById('upload-result');
    const badge = document.getElementById('upload-result-status');
    const validation = data.validation || {};
    section.classList.remove('hidden');
    badge.textContent = success ? 'Imported' : 'Needs attention';
    badge.className = `status-badge ${success ? 'reliable' : 'low-reliability'}`;
    const range = validation.date_range ? `${validation.date_range.from} → ${validation.date_range.to}` : '—';
    document.getElementById('validation-grid').innerHTML = [
      metric('Records checked', validation.records ?? '—'),
      metric('Products found', validation.products ?? '—'),
      metric('Date range', range),
      metric('Missing values', validation.missing_values ?? '—'),
      metric('Duplicate rows', validation.duplicate_rows ?? '—'),
      metric('Invalid dates', validation.invalid_dates ?? '—'),
      metric('Invalid quantities', validation.invalid_quantities ?? '—'),
      metric('Unknown product IDs', (validation.unknown_product_ids || data.unknown_product_ids || []).length),
    ].join('');
    const imported = data.imported_daily_records !== undefined ? ` ${ui.number(data.imported_daily_records)} daily product records imported; forecasts refreshed for ${ui.number(data.forecasted_products)} products.` : '';
    document.getElementById('upload-result-message').textContent = `${message || data.message || 'Validation complete.'}${imported}`;
  }

  fileInput.addEventListener('change', () => {
    const file = fileInput.files && fileInput.files[0];
    fileLabel.textContent = file ? `${file.name} · ${ui.number(file.size / 1024, 1)} KB` : 'No file selected';
    feedback.textContent = '';
    feedback.className = 'form-feedback';
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      feedback.textContent = 'Choose a CSV or Excel file first.';
      feedback.className = 'form-feedback error';
      return;
    }
    submit.disabled = true;
    submit.textContent = 'Validating & importing…';
    feedback.textContent = 'Checking columns, dates, product IDs and quantities.';
    feedback.className = 'form-feedback';
    try {
      const result = await api.upload('/api/upload', file);
      showReport(result, true, result.message);
      feedback.textContent = 'Sales data saved. All available product forecasts were refreshed.';
      feedback.className = 'form-feedback success';
      ui.toast('Sales file imported and forecasts refreshed.', 'success');
    } catch (error) {
      const detail = error.detail;
      if (detail && typeof detail === 'object') {
        showReport(detail, false, detail.message || error.message);
      } else {
        showReport({}, false, error.message);
      }
      feedback.textContent = error.message;
      feedback.className = 'form-feedback error';
      ui.toast(error.message, 'error');
    } finally {
      submit.disabled = false;
      submit.innerHTML = 'Validate & import data <span>→</span>';
    }
  });
})();
