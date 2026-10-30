(() => {
  const api = window.StockoraAPI;
  const ui = window.StockoraUI;
  async function renderBar(targetId, rows, key, label, color, errorMessage, suffix = '') {
    const el = document.getElementById(targetId);
    el.style.minHeight = '250px';
    try {
      if (!Array.isArray(rows)) throw new Error(`Analytics response did not include data for ${targetId}.`);
      if (!rows.length) {
        el.innerHTML = '<div class="empty-state">No data available yet.</div>';
        return;
      }
      const ordered = rows.slice().reverse();
      const trace = {
        type: 'bar', orientation: 'h',
        y: ordered.map((item) => item.product_name),
        x: ordered.map((item) => Number(item[key])),
        marker: { color, opacity: 0.88, line: { width: 0 } },
        text: ordered.map((item) => `${ui.number(item[key], 1)}${suffix}`),
        textposition: 'outside', cliponaxis: false,
        hovertemplate: `%{y}<br>${label}: %{x:.1f}${suffix}<extra></extra>`,
      };
      el.replaceChildren();
      await ui.ensurePlotly();
      await window.Plotly.newPlot(el, [trace], {
        autosize: true, height: 275, margin: { l: 95, r: 42, t: 10, b: 35 },
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: 'DM Sans, sans-serif', color: '#6B7280', size: 9 },
        xaxis: { gridcolor: 'rgba(229,231,235,.8)', zeroline: false, ticksuffix: suffix },
        yaxis: { gridcolor: 'rgba(0,0,0,0)', automargin: true },
        showlegend: false,
      }, { responsive: true, displayModeBar: false });
    } catch (error) {
      console.error(error);
      el.innerHTML = `<div class="empty-state">${ui.escapeHtml(errorMessage)}</div>`;
    }
  }

  function renderRankList(id, rows, mode) {
    const target = document.getElementById(id);
    if (!rows.length) {
      target.innerHTML = '<div class="empty-state">No matching products.</div>';
      return;
    }
    target.innerHTML = rows.slice(0, 5).map((item, index) => `
      <div class="rank-row"><span class="rank-number">${index + 1}</span><div class="rank-copy"><strong>${ui.escapeHtml(item.product_name)}</strong><small>${ui.escapeHtml(item.category)}</small></div>
      <span class="rank-value">${mode === 'reorder' ? ui.number(item.reorder_quantity) + ' to order' : ui.number(item.historical_average, 1) + ' / day'}</span></div>`).join('');
  }

  async function init() {
    try {
      const data = await api.get('/api/analytics');
      const demandChart = renderBar(
        'analytics-demand-chart',
        data.highest_demand,
        'historical_average',
        'Average daily demand',
        '#166534',
        'Unable to load analytics.'
      );
      const performance = data.forecast_performance.slice().sort((a, b) => a.forecast_accuracy - b.forecast_accuracy).slice(-7);
      const performanceChart = renderBar(
        'analytics-performance-chart',
        performance,
        'forecast_accuracy',
        'Forecast accuracy estimate',
        '#EA580C',
        'Unable to load forecast performance.',
        '%'
      );
      renderRankList('highest-demand', data.highest_demand, 'demand');
      renderRankList('analytics-reorder', data.reorder_required, 'reorder');
      await Promise.all([demandChart, performanceChart]);
    } catch (error) {
      console.error(error);
      ui.toast(error.message, 'error');
      document.getElementById('analytics-demand-chart').innerHTML = '<div class="empty-state">Unable to load analytics.</div>';
      document.getElementById('analytics-performance-chart').innerHTML = '<div class="empty-state">Unable to load forecast performance.</div>';
      document.getElementById('highest-demand').innerHTML = `<div class="empty-state">${ui.escapeHtml(error.message)}</div>`;
    }
  }
  document.addEventListener('DOMContentLoaded', init);
})();
