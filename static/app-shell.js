(function () {
  var moduleLinks = [
    { label: '首页', href: '/', match: ['/'] },
    { label: '口语', href: '/speaking', match: ['/speaking', '/combined'] },
    { label: '阅读', href: '/reading', match: ['/reading', '/intensive', '/vocab_summary'] },
    { label: '词汇', href: '/vocabulary', match: ['/vocabulary'] },
    { label: '写作', href: '/writing_practice', match: ['/writing_practice'] },
    { label: '听力', href: '/listening_review', match: ['/listening_review'] },
    { label: '交流', href: '/message_board', match: ['/message_board'] }
  ];

  function isActive(link) {
    var path = window.location.pathname;
    return link.match.some(function (prefix) {
      return prefix === '/' ? path === '/' : path.indexOf(prefix) === 0;
    });
  }

  function createShell() {
    if (!document.body || document.querySelector('.app-shell-nav') || document.body.dataset.appShell === 'off') {
      return;
    }
    var user = window.IELTSAuth && window.IELTSAuth.getUser ? window.IELTSAuth.getUser() : null;
    var nav = document.createElement('nav');
    nav.className = 'app-shell-nav';
    nav.setAttribute('aria-label', '全局导航');
    nav.innerHTML = [
      '<a class="app-shell-brand" href="/">IELTS Lab</a>',
      '<div class="app-shell-links">',
      moduleLinks.map(function (link) {
        return '<a class="app-shell-link ' + (isActive(link) ? 'is-active' : '') + '" href="' + link.href + '">' + link.label + '</a>';
      }).join(''),
      '</div>',
      '<div class="app-shell-user">',
      '<span class="app-shell-user__name">' + ((user && user.display_name) || '学习者') + '</span>',
      '<button type="button" class="app-shell-logout">退出</button>',
      '</div>'
    ].join('');
    document.body.insertBefore(nav, document.body.firstChild);
    document.body.classList.add('has-app-shell');
    var logout = nav.querySelector('.app-shell-logout');
    if (logout) {
      logout.addEventListener('click', function () {
        if (window.IELTSAuth) window.IELTSAuth.logout();
      });
    }
  }

  function init() {
    if (window.location.pathname === '/login') return;
    if (!window.IELTSAuth) return;
    window.IELTSAuth.verifyStoredToken({ redirect: false }).then(function (result) {
      if (result.valid) createShell();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
