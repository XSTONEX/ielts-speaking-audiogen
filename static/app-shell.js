(function () {
  // 手机上 7 个模块横排放不下：以前是一条横滑的链接带，实宽 166px 装 379px 的内容，
  // 后 4 个模块既看不见也没有可滑的提示。窄屏改成「字标 + 当前模块 ▾ + 主题 + 头像」，
  // 模块列表收进一个下拉面板，一屏全见。宽屏仍然是原来的七个链接平铺。
  var ICON = {
    home: '<path d="M2.5 7.5 8 3l5.5 4.5V13h-3.5V9.5h-4V13H2.5z"></path>',
    speaking: '<rect x="6" y="2" width="4" height="7" rx="2"></rect><path d="M3.5 7.5a4.5 4.5 0 0 0 9 0M8 12v2"></path>',
    reading: '<path d="M2.5 3.5h4A1.5 1.5 0 0 1 8 5v8a1.5 1.5 0 0 0-1.5-1.5h-4zM13.5 3.5h-4A1.5 1.5 0 0 0 8 5v8a1.5 1.5 0 0 1 1.5-1.5h4z"></path>',
    vocab: '<path d="M3 4.5h10M3 8h10M3 11.5h6"></path>',
    writing: '<path d="M11 2.5 13.5 5 5.5 13H3v-2.5z"></path>',
    listening: '<path d="M3 9.5V8a5 5 0 0 1 10 0v1.5"></path><path d="M3 9.8h1.6a.7.7 0 0 1 .7.7v2a.7.7 0 0 1-.7.7H3.6a.7.7 0 0 1-.6-.7zM13 9.8h-1.6a.7.7 0 0 0-.7.7v2a.7.7 0 0 0 .7.7h1a.7.7 0 0 0 .6-.7z"></path>',
    board: '<path d="M13.5 8.5c0 2.5-2.5 4.5-5.5 4.5-.8 0-1.5-.1-2.2-.4L2.5 13.5l1-2.6C2.6 10 2.5 9.3 2.5 8.5c0-2.5 2.5-4.5 5.5-4.5s5.5 2 5.5 4.5z"></path>'
  };

  var MOON = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 9.5A6 6 0 0 1 6.5 2.5a6 6 0 1 0 7 7z"></path></svg>';
  var SUN = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="3.2"></circle><path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1"></path></svg>';
  var CARET = '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 6 8 10.5 12.5 6"></path></svg>';

  var moduleLinks = [
    { label: '首页', href: '/', match: ['/'], icon: ICON.home },
    { label: '口语', href: '/speaking', match: ['/speaking', '/combined'], icon: ICON.speaking },
    { label: '阅读', href: '/reading', match: ['/reading', '/intensive', '/vocab_summary'], icon: ICON.reading },
    { label: '词汇', href: '/vocabulary', match: ['/vocabulary'], icon: ICON.vocab },
    { label: '写作', href: '/writing_practice', match: ['/writing_practice'], icon: ICON.writing },
    { label: '听力', href: '/listening_review', match: ['/listening_review'], icon: ICON.listening },
    { label: '交流', href: '/message_board', match: ['/message_board'], icon: ICON.board }
  ];

  function isActive(link) {
    var path = window.location.pathname;
    return link.match.some(function (prefix) {
      return prefix === '/' ? path === '/' : path.indexOf(prefix) === 0;
    });
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function currentModule() {
    for (var i = 0; i < moduleLinks.length; i++) {
      if (isActive(moduleLinks[i])) return moduleLinks[i];
    }
    return null;
  }

  function iconSvg(path) {
    return '<svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" ' +
      'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + path + '</svg>';
  }

  function createShell() {
    if (!document.body || document.querySelector('.app-shell-nav') || document.body.dataset.appShell === 'off') {
      return;
    }
    var user = window.IELTSAuth && window.IELTSAuth.getUser ? window.IELTSAuth.getUser() : null;
    var displayName = (user && user.display_name) || '学习者';
    // 有的账号 display_name 和 username 是同一个串，重复显示两行没有意义
    var rawName = (user && user.username) || '';
    var userName = rawName === displayName ? '' : rawName;
    var initial = displayName.trim().charAt(0) || '学';
    var active = currentModule();
    // 首页自己有一整排「系统/浅色/深色」开关，栏上就不再放一个月亮重复了
    var wantsTheme = !!window.IELTSTheme && window.location.pathname !== '/';

    var nav = document.createElement('nav');
    nav.className = 'app-shell-nav';
    nav.setAttribute('aria-label', '全局导航');
    nav.innerHTML = [
      '<a class="app-shell-mark" href="/" aria-label="回首页">IL</a>',
      '<a class="app-shell-brand" href="/">IELTS Lab</a>',
      '<button type="button" class="app-shell-current" aria-expanded="false" aria-controls="appShellPanel" aria-haspopup="true">',
      '<span class="app-shell-current__name">' + escapeHtml(active ? active.label : 'IELTS Lab') + '</span>',
      '<span class="app-shell-current__caret">' + CARET + '</span>',
      '</button>',
      '<div class="app-shell-links">',
      moduleLinks.map(function (link) {
        return '<a class="app-shell-link ' + (isActive(link) ? 'is-active' : '') + '" href="' + link.href + '">' + escapeHtml(link.label) + '</a>';
      }).join(''),
      '</div>',
      wantsTheme ? '<button type="button" class="app-shell-theme" aria-label="切换深浅色"></button>' : '',
      '<div class="app-shell-user">',
      '<span class="app-shell-user__name">' + escapeHtml(displayName) + '</span>',
      '<button type="button" class="app-shell-logout">退出</button>',
      '</div>',
      '<button type="button" class="app-shell-avatar" aria-expanded="false" aria-controls="appShellPanel" aria-haspopup="true" aria-label="账号与模块">' + escapeHtml(initial) + '</button>'
    ].join('');

    var scrim = document.createElement('div');
    scrim.className = 'app-shell-scrim';
    scrim.hidden = true;

    var panel = document.createElement('div');
    panel.className = 'app-shell-panel';
    panel.id = 'appShellPanel';
    panel.hidden = true;
    panel.innerHTML = [
      '<nav class="app-shell-panel__grid" aria-label="模块切换">',
      moduleLinks.map(function (link) {
        var on = isActive(link);
        return '<a class="app-shell-tile ' + (on ? 'is-active' : '') + '" href="' + link.href + '"' +
          (on ? ' aria-current="page"' : '') + '>' +
          '<span class="app-shell-tile__icon">' + iconSvg(link.icon) + '</span>' +
          '<span class="app-shell-tile__label">' + escapeHtml(link.label) + '</span>' +
          (on ? '<span class="app-shell-tile__dot"></span>' : '') +
          '</a>';
      }).join(''),
      '</nav>',
      '<div class="app-shell-panel__sep"></div>',
      '<div class="app-shell-panel__foot">',
      '<span class="app-shell-panel__avatar">' + escapeHtml(initial) + '</span>',
      '<span class="app-shell-panel__who">',
      '<span class="app-shell-panel__name">' + escapeHtml(displayName) + '</span>',
      userName ? '<span class="app-shell-panel__account">' + escapeHtml(userName) + '</span>' : '',
      '</span>',
      '<button type="button" class="app-shell-logout app-shell-logout--panel">退出</button>',
      '</div>'
    ].join('');

    document.body.insertBefore(panel, document.body.firstChild);
    document.body.insertBefore(scrim, document.body.firstChild);
    document.body.insertBefore(nav, document.body.firstChild);
    document.body.classList.add('has-app-shell');

    var triggers = [nav.querySelector('.app-shell-current'), nav.querySelector('.app-shell-avatar')];

    function setPanel(open) {
      panel.hidden = !open;
      scrim.hidden = !open;
      nav.classList.toggle('is-panel-open', open);
      triggers.forEach(function (btn) {
        if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    }

    triggers.forEach(function (btn) {
      if (!btn) return;
      btn.addEventListener('click', function () { setPanel(panel.hidden); });
    });
    scrim.addEventListener('click', function () { setPanel(false); });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !panel.hidden) setPanel(false);
    });
    // 转到宽屏时面板没有位置可放，直接收掉
    if (window.matchMedia) {
      var wide = window.matchMedia('(min-width: 821px)');
      var onWide = function (e) { if (e.matches) setPanel(false); };
      if (typeof wide.addEventListener === 'function') wide.addEventListener('change', onWide);
      else if (typeof wide.addListener === 'function') wide.addListener(onWide);
    }

    nav.querySelectorAll('.app-shell-logout').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (window.IELTSAuth) window.IELTSAuth.logout();
      });
    });
    panel.querySelectorAll('.app-shell-logout').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (window.IELTSAuth) window.IELTSAuth.logout();
      });
    });

    var themeBtn = nav.querySelector('.app-shell-theme');
    if (themeBtn) {
      var paintTheme = function () {
        themeBtn.innerHTML = document.documentElement.dataset.theme === 'dark' ? SUN : MOON;
      };
      paintTheme();
      themeBtn.addEventListener('click', function () {
        window.IELTSTheme.setPreference(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
      });
      document.addEventListener('themechange', paintTheme);
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
