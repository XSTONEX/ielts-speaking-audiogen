(function () {
  async function verifyStoredToken(options) {
    var opts = options || {};
    var token = window.IELTSApi && window.IELTSApi.getToken ? window.IELTSApi.getToken() : '';
    if (!token) {
      if (opts.redirect !== false) redirectToLogin();
      return { valid: false };
    }

    try {
      var response = await fetch('/verify_token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token })
      });
      var data = await response.json();
      if (!data.valid) {
        logout({ redirect: opts.redirect !== false });
        return { valid: false };
      }
      if (data.user) {
        localStorage.setItem('currentUser', JSON.stringify(data.user));
      }
      return { valid: true, token: token, user: data.user || getUser() };
    } catch (error) {
      logout({ redirect: opts.redirect !== false });
      return { valid: false, error: error };
    }
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
