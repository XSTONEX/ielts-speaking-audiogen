(function () {
  function getToken() {
    try {
      return localStorage.getItem('authToken') || '';
    } catch (error) {
      return '';
    }
  }

  function getCurrentUser() {
    try {
      var raw = localStorage.getItem('currentUser');
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      return null;
    }
  }

  function clearSession() {
    try {
      localStorage.removeItem('authToken');
      localStorage.removeItem('currentUser');
    } catch (error) {
      // Storage can fail in private contexts; runtime state still clears.
    }
  }

  function headers(extra) {
    var result = Object.assign({}, extra || {});
    var token = getToken();
    if (token) {
      result.Authorization = 'Bearer ' + token;
    }
    return result;
  }

  async function parseResponse(response) {
    var contentType = response.headers.get('content-type') || '';
    var isJson = contentType.indexOf('application/json') >= 0;
    var body = isJson ? await response.json() : await response.text();
    if (response.status === 401) {
      clearSession();
      var error = new Error((body && body.error) || '登录已失效，请重新登录');
      error.status = response.status;
      error.body = body;
      throw error;
    }
    if (!response.ok) {
      var message = isJson ? (body.error || body.message || '请求失败') : (body || '请求失败');
      var requestError = new Error(message);
      requestError.status = response.status;
      requestError.body = body;
      throw requestError;
    }
    return body;
  }

  async function request(url, options) {
    var opts = Object.assign({}, options || {});
    opts.headers = headers(opts.headers);
    return parseResponse(await fetch(url, opts));
  }

  async function get(url) {
    return request(url);
  }

  async function post(url, body) {
    return request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    });
  }

  async function del(url) {
    return request(url, { method: 'DELETE' });
  }

  window.IELTSApi = {
    getToken: getToken,
    getCurrentUser: getCurrentUser,
    clearSession: clearSession,
    headers: headers,
    request: request,
    get: get,
    post: post,
    del: del
  };
})();
