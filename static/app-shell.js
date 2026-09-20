(function () {
  // 主题切换：一个图标循环三态，顺序 暗色 → 亮色 → 系统默认。
  // 图标画的是「当前是哪一档」，点一下走到下一档。
  var THEME_CYCLE = ['dark', 'light', 'system'];
  var THEME_META = {
    dark:   { name: '暗色', next: '亮色',
              icon: '<path d="M16.4 12.4A7.1 7.1 0 0 1 7.6 3.6a7.3 7.3 0 1 0 8.8 8.8Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>' },
    light:  { name: '亮色', next: '系统默认',
              icon: '<circle cx="10" cy="10" r="3.7" fill="none" stroke="currentColor" stroke-width="1.6"/>'
                  + '<path d="M10 1.9v2.1M10 16v2.1M18.1 10H16M4 10H1.9M15.7 4.3l-1.5 1.5M5.8 14.2l-1.5 1.5M15.7 15.7l-1.5-1.5M5.8 5.8 4.3 4.3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' },
    system: { name: '系统默认', next: '暗色',
              icon: '<circle cx="10" cy="10" r="6.9" fill="none" stroke="currentColor" stroke-width="1.6"/>'
                  + '<path d="M10 3.1a6.9 6.9 0 0 1 0 13.8Z" fill="currentColor"/>' }
  };

  function currentPreference() {
    return (window.IELTSTheme && window.IELTSTheme.getPreference)
      ? window.IELTSTheme.getPreference() : 'system';
  }

  function paintThemeBtn(btn) {
    var pref = currentPreference();
    var meta = THEME_META[pref] || THEME_META.system;
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true">' + meta.icon + '</svg>';
    var label = '主题：' + meta.name + ' · 点一下切到' + meta.next;
    btn.setAttribute('aria-label', label);
    btn.setAttribute('title', label);
  }

  function createThemeBtn() {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'app-shell-theme';
    paintThemeBtn(btn);
    btn.addEventListener('click', function () {
      if (!window.IELTSTheme || !window.IELTSTheme.setPreference) return;
      var idx = THEME_CYCLE.indexOf(currentPreference());
      window.IELTSTheme.setPreference(THEME_CYCLE[(idx + 1) % THEME_CYCLE.length]);
    });
    // theme.js 换主题后会派发 themechange，图标跟着走（含另一个标签页改偏好的情况）
    document.addEventListener('themechange', function () { paintThemeBtn(btn); });
    return btn;
  }

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
    var userBox = nav.querySelector('.app-shell-user');
    if (userBox) userBox.insertBefore(createThemeBtn(), userBox.firstChild);
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
