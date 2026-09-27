/*
 * 给发往本站的 fetch 请求自动带上登录凭证（Authorization: Bearer <token>）。
 *
 * 服务端默认所有接口都要登录（见 app.py 的 _guard_request），而页面里上百处 fetch
 * 是各自手写的，并不都带了这个头。这个脚本必须在页面其它脚本之前同步执行
 * （放在 <head> 里、不加 defer），否则页面一打开就发出的请求会漏掉。
 *
 * 只处理同源请求：发往外站（CDN、第三方接口）的请求绝不附带 token。
 * 调用方自己带了有效的 Authorization 头时原样保留。
 */
(function () {
  'use strict';
  if (typeof window.fetch !== 'function' || window.fetch.__ieltsAuthFetch) return;

  var nativeFetch = window.fetch;
  // 页面变量还没赋值时拼出来的 "Bearer null"、"Bearer undefined"，等于没带
  var EMPTY_AUTH = /^Bearer\s*(null|undefined)?\s*$/i;

  function readToken() {
    try {
      return localStorage.getItem('authToken') || '';
    } catch (e) {
      return '';
    }
  }

  function requestUrl(input) {
    if (typeof input === 'string') return input;
    if (input && typeof input.url === 'string') return input.url; // Request
    return String(input); // URL 对象
  }

  function isSameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  function authFetch(input, init) {
    var token = readToken();
    if (!token) return nativeFetch.call(window, input, init);

    var nextInit;
    try {
      if (!isSameOrigin(requestUrl(input))) return nativeFetch.call(window, input, init);

      var source = init && init.headers !== undefined
        ? init.headers
        : (typeof Request !== 'undefined' && input instanceof Request ? input.headers : undefined);
      var headers = new Headers(source);
      var current = headers.get('Authorization');
      if (current && !EMPTY_AUTH.test(current)) return nativeFetch.call(window, input, init);

      headers.set('Authorization', 'Bearer ' + token);
      nextInit = Object.assign({}, init, { headers: headers });
    } catch (e) {
      // 组装请求头出了意外（比如调用方的头里有非法字符）：原样交给浏览器，行为和没有这个脚本时一致
      return nativeFetch.call(window, input, init);
    }
    return nativeFetch.call(window, input, nextInit);
  }

  authFetch.__ieltsAuthFetch = true;
  window.fetch = authFetch;
})();
