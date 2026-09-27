(function () {
  async function verifyStoredToken(options) {
    var opts = options || {};
    var token = window.IELTSApi && window.IELTSApi.getToken ? window.IELTSApi.getToken() : '';
    if (!token) {
      if (opts.redirect !== false) redirectToLogin();
      return { valid: false };
    }

    var data = null;
    try {
      var response = await fetch('/verify_token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token })
      });
      data = await response.json();
    } catch (error) {
      // 断网、弱网，或服务器重启时 nginx 回的 502 页面：这些都说明不了凭证是否失效，
      // 保留登录状态，按已登录继续（真失效的话，之后的请求会拿到 401）
      return { valid: true, unverified: true, token: token, user: getUser(), error: error };
    }

    // 只有服务器明确回答"无效"才清掉登录状态
    if (data && data.valid === false) {
      logout({ redirect: opts.redirect !== false });
      return { valid: false };
    }
    if (!data || data.valid !== true) {
      // 比如服务器暂时读不了凭证库时回的 503 {error: ...}
      return { valid: true, unverified: true, token: token, user: getUser() };
    }
    if (data.user) {
      try {
        localStorage.setItem('currentUser', JSON.stringify(data.user));
      } catch (error) {
        // 存储不可用时只影响缓存的用户信息
      }
    }
    return { valid: true, token: token, user: data.user || getUser() };
  }

  function getUser() {
    return window.IELTSApi && window.IELTSApi.getCurrentUser ? window.IELTSApi.getCurrentUser() : null;
  }

  function redirectToLogin() {
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
  }

  function logout(options) {
    if (window.IELTSApi && window.IELTSApi.clearSession) {
      window.IELTSApi.clearSession();
    }
    if (!options || options.redirect !== false) {
      redirectToLogin();
    }
  }

  function requireAuth(callback) {
    return verifyStoredToken().then(function (result) {
      if (result.valid && typeof callback === 'function') {
        callback(result);
      }
      return result;
    });
  }

  window.IELTSAuth = {
    verifyStoredToken: verifyStoredToken,
    requireAuth: requireAuth,
    logout: logout,
    getUser: getUser
  };
})();
