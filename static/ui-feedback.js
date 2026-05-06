(function () {
  function ensureToastHost() {
    var host = document.querySelector('[data-toast-host]');
    if (host) return host;
    host = document.createElement('div');
    host.className = 'ielts-toast-host';
    host.setAttribute('data-toast-host', '');
    document.body.appendChild(host);
    return host;
  }

  function toast(message, type) {
    var host = ensureToastHost();
    var item = document.createElement('div');
    item.className = 'ielts-toast ielts-toast--' + (type || 'info');
    item.textContent = message;
    host.appendChild(item);
    setTimeout(function () {
      item.classList.add('is-leaving');
      setTimeout(function () {
        if (item.parentNode) item.parentNode.removeChild(item);
      }, 220);
    }, 2800);
  }

  function setBusy(element, busy, text) {
    if (!element) return;
    element.disabled = !!busy;
    if (busy) {
      element.dataset.originalText = element.textContent;
      element.textContent = text || '处理中...';
    } else if (element.dataset.originalText) {
      element.textContent = element.dataset.originalText;
      delete element.dataset.originalText;
    }
  }

  function formatDate(value) {
    if (!value) return '暂无';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  }

  window.IELTSUI = {
    toast: toast,
    setBusy: setBusy,
    formatDate: formatDate
  };
})();
