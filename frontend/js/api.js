(() => {
  async function request(path, options = {}) {
    let response;
    try {
      response = await fetch(path, options);
    } catch (error) {
      throw new Error('Cannot reach STOCKORA. Check that the backend is running and try again.');
    }
    let payload = {};
    try { payload = await response.json(); } catch (_) { payload = {}; }
    if (!response.ok) {
      const detail = payload.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail && typeof detail === 'object' ? (detail.message || JSON.stringify(detail)) : `Request failed (${response.status}).`);
      const error = new Error(message);
      error.status = response.status;
      error.detail = detail;
      throw error;
    }
    return payload;
  }

  window.StockoraAPI = {
    get(path) { return request(path); },
    post(path, body) {
      return request(path, {
        method: 'POST',
        headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    },
    put(path, body) {
      return request(path, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    },
    upload(path, file) {
      const form = new FormData();
      form.append('file', file);
      return request(path, { method: 'POST', body: form });
    },
  };
})();
