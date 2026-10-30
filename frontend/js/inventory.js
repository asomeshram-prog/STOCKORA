(() => {
  const api = window.StockoraAPI;
  const ui = window.StockoraUI;
  let items = [];
  const tbody = document.getElementById('inventory-body');
  const search = document.getElementById('inventory-search');
  const filter = document.getElementById('inventory-filter');

  function productCell(item) {
    return `<a class="product-cell" href="/product?id=${encodeURIComponent(item.product_id)}"><span class="product-token">${ui.escapeHtml(item.product_id.slice(-2))}</span><span><strong class="inventory-product-name">${ui.escapeHtml(item.product_name)}</strong><small>${ui.escapeHtml(item.category)}</small></span></a>`;
  }

  function render() {
    const query = search.value.trim().toLowerCase();
    const risk = filter.value;
    const filtered = items.filter((item) => item.product_name.toLowerCase().includes(query) || item.product_id.toLowerCase().includes(query))
      .filter((item) => risk === 'all' || item.risk === risk);
    if (!filtered.length) {
      tbody.innerHTML = '<tr><td colspan="10" class="empty-cell">No products match this filter.</td></tr>';
      return;
    }
    tbody.innerHTML = filtered.map((item) => `
      <tr>
        <td>${productCell(item)}</td><td class="numeric quantity-strong">${ui.number(item.current_stock)}</td>
        <td class="numeric">${ui.number(item.safety_stock)}</td><td class="numeric">${ui.number(item.incoming_stock)}</td>
        <td class="numeric">${ui.number(item.forecast_demand)}</td><td class="numeric">${ui.number(item.required_stock)}</td>
        <td class="numeric ${item.reorder_quantity > 0 ? 'risk-value' : 'positive-value'}">${ui.number(item.reorder_quantity)}</td>
        <td><span class="status-badge ${ui.statusClass(item.forecast_reliability)}">${ui.escapeHtml(item.forecast_reliability || '—')}</span></td>
        <td><span class="recommendation-text ${item.risk}">${ui.escapeHtml(item.recommendation)}</span></td>
        <td><div style="display:flex;gap:5px"><button class="action-link" data-why="${ui.escapeHtml(item.product_id)}">Why?</button><button class="action-link" data-edit="${ui.escapeHtml(item.product_id)}">Edit stock</button></div></td>
      </tr>`).join('');
  }

  function updateSummary() {
    const count = items.length;
    const reorder = items.filter((item) => item.reorder_quantity > 0).length;
    const high = items.filter((item) => item.risk === 'high').length;
    document.getElementById('inventory-summary').innerHTML = `
      <div class="mini-stat"><span>Products tracked</span><strong>${ui.number(count)}</strong></div>
      <div class="mini-stat"><span>Reorders needed</span><strong>${ui.number(reorder)}</strong></div>
      <div class="mini-stat"><span>High risk</span><strong>${ui.number(high)}</strong></div>`;
  }

  function editStock(item) {
    const modal = ui.showModal(`Update ${item.product_name}`, `
      <p class="modal-copy">Adjust on-hand stock and the safety-stock buffer. Reorder quantities and risk alerts will recalculate from the saved values.</p>
      <form id="edit-stock-form">
        <div class="field-grid">
          <label class="field-label">Current stock (${ui.escapeHtml(item.unit)})<input id="edit-current-stock" type="number" min="0" step="0.01" required value="${item.current_stock}"></label>
          <label class="field-label">Safety stock (${ui.escapeHtml(item.unit)})<input id="edit-safety-stock" type="number" min="0" step="0.01" required value="${item.safety_stock}"></label>
        </div>
        <div class="modal-actions"><button type="button" class="button button-quiet" id="cancel-edit">Cancel</button><button type="submit" class="button button-primary" id="save-stock">Save stock levels</button></div>
      </form>`, { eyebrow: 'INVENTORY INPUT' });
    modal.root.querySelector('#cancel-edit').addEventListener('click', modal.close);
    modal.root.querySelector('#edit-stock-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const save = modal.root.querySelector('#save-stock');
      save.disabled = true;
      save.textContent = 'Saving…';
      try {
        await api.put(`/api/inventory/${encodeURIComponent(item.product_id)}`, {
          current_stock: Number(modal.root.querySelector('#edit-current-stock').value),
          safety_stock: Number(modal.root.querySelector('#edit-safety-stock').value),
        });
        modal.close();
        ui.toast(`${item.product_name} stock levels updated.`, 'success');
        await load();
      } catch (error) {
        ui.toast(error.message, 'error');
        save.disabled = false;
        save.textContent = 'Save stock levels';
      }
    });
  }

  async function load() {
    tbody.innerHTML = '<tr><td colspan="10" class="empty-cell">Refreshing inventory…</td></tr>';
    try {
      const data = await api.get('/api/inventory');
      items = data.inventory || [];
      updateSummary();
      render();
    } catch (error) {
      tbody.innerHTML = `<tr><td colspan="10" class="empty-cell">${ui.escapeHtml(error.message)}</td></tr>`;
      ui.toast(error.message, 'error');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    search.addEventListener('input', render);
    filter.addEventListener('change', render);
    tbody.addEventListener('click', (event) => {
      const why = event.target.closest('[data-why]');
      const edit = event.target.closest('[data-edit]');
      if (why) {
        const item = items.find((entry) => entry.product_id === why.dataset.why);
        if (item) ui.showWhy(item);
      }
      if (edit) {
        const item = items.find((entry) => entry.product_id === edit.dataset.edit);
        if (item) editStock(item);
      }
    });
    load();
  });
})();
