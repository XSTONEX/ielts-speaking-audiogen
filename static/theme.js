(function () {
  // iOS Safari 聚焦字号小于 16px 的输入框会把整页放大，放大后还不缩回去。
  // 只在 iOS 上给 viewport 加 maximum-scale=1：iOS 10 起这条不拦双指缩放，只拦聚焦时的自动放大；
  // 安卓会真的禁止缩放，而安卓本来就不自动放大，所以不加。
  var ua = navigator.userAgent || '';
  var isIOS = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var meta = document.querySelector('meta[name="viewport"]');
  if (isIOS && meta && !/maximum-scale/.test(meta.content)) {
    meta.content = meta.content + ', maximum-scale=1';
  }
})();

(function () {
  // 什么时候用手机布局：窄屏（≤820px，手机、竖着拿的平板），或者矮的触摸屏（横着拿的手机，宽 844–932、高不到 540）。
  // 带鼠标的电脑窗口拉得再矮也不算（pointer 是 fine）；iPad 横竖都够高，也不算。
  // CSS 里每个手机媒体查询写的是同一句；页面脚本一律用这里的 IELTSPhone.mq，不再各写一遍。
  // 这个文件不加 defer（页面里的内联脚本一解析就要读它）。
  var QUERY = '(max-width: 820px), (max-height: 540px) and (pointer: coarse)';
  var noop = function () {};
  var mq = window.matchMedia ? window.matchMedia(QUERY) : {
    matches: false, media: QUERY,
    addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop
  };
  window.IELTSPhone = {
    query: QUERY,
    mq: mq,
    matches: function () { return !!mq.matches; },
    // 跨过手机 / 桌面的分界（转屏、拖窗口）时调用 fn(event)，event.matches 是新的状态
    onChange: function (fn) {
      if (typeof mq.addEventListener === 'function') mq.addEventListener('change', fn);
      else if (typeof mq.addListener === 'function') mq.addListener(fn);
    }
  };
})();

(function () {
  var STORAGE_KEY = 'ui-theme';
  var VALID_PREFERENCES = ['system', 'light', 'dark'];
  var mediaQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function normalizePreference(value) {
    return VALID_PREFERENCES.indexOf(value) >= 0 ? value : 'system';
  }

  function getStoredPreference() {
    try {
      return normalizePreference(localStorage.getItem(STORAGE_KEY));
    } catch (error) {
      return 'system';
    }
  }

  function resolveTheme(preference) {
    if (preference === 'light' || preference === 'dark') {
      return preference;
    }
    return mediaQuery && mediaQuery.matches ? 'dark' : 'light';
  }

  function updateSwitcher(preference) {
    var switcher = document.querySelector('.theme-switcher');
    if (!switcher) {
      return;
    }

    switcher.querySelectorAll('[data-theme-option]').forEach(function (button) {
      var isActive = button.getAttribute('data-theme-option') === preference;
      button.classList.toggle('is-active', isActive);
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  function applyTheme(preference, options) {
    var root = document.documentElement;
    var normalizedPreference = normalizePreference(preference);
    var theme = resolveTheme(normalizedPreference);

    root.dataset.themePreference = normalizedPreference;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    root.classList.toggle('dark', theme === 'dark');

    if (!options || options.persist !== false) {
      try {
        localStorage.setItem(STORAGE_KEY, normalizedPreference);
      } catch (error) {
        // Ignore storage errors and keep the runtime theme applied.
      }
    }

    updateSwitcher(normalizedPreference);

    document.dispatchEvent(new CustomEvent('themechange', {
      detail: {
        preference: normalizedPreference,
        theme: theme
      }
    }));
  }

  function handleThemeSelection(event) {
    var button = event.target.closest('[data-theme-option]');
    if (!button) {
      return;
    }
    applyTheme(button.getAttribute('data-theme-option'));
  }

  function injectSwitcher() {
    if (!document.body || document.querySelector('.theme-switcher')) {
      updateSwitcher(getStoredPreference());
      return;
    }

    if (window.location.pathname !== '/') {
      return;
    }

    var mount = document.getElementById('themeSwitcherMount');
    if (!mount) {
      return;
    }

    var switcher = document.createElement('div');
    switcher.className = 'theme-switcher';
    switcher.setAttribute('role', 'group');
    switcher.setAttribute('aria-label', '主题切换');
    switcher.innerHTML = [
      '<button type="button" class="theme-switcher__btn" data-theme-option="system" aria-label="跟随系统">系统</button>',
      '<button type="button" class="theme-switcher__btn" data-theme-option="light" aria-label="浅色模式">浅色</button>',
      '<button type="button" class="theme-switcher__btn" data-theme-option="dark" aria-label="深色模式">深色</button>'
    ].join('');
    switcher.addEventListener('click', handleThemeSelection);
    mount.appendChild(switcher);
    updateSwitcher(getStoredPreference());
  }

  function handleSystemThemeChange() {
    if (getStoredPreference() === 'system') {
      applyTheme('system', { persist: false });
    }
  }

  if (mediaQuery) {
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleSystemThemeChange);
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(handleSystemThemeChange);
    }
  }

  window.addEventListener('storage', function (event) {
    if (event.key === STORAGE_KEY) {
      applyTheme(normalizePreference(event.newValue), { persist: false });
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectSwitcher, { once: true });
  } else {
    injectSwitcher();
  }

  window.IELTSTheme = {
    storageKey: STORAGE_KEY,
    getPreference: getStoredPreference,
    setPreference: function (preference) {
      applyTheme(preference);
    },
    getTheme: function () {
      return document.documentElement.dataset.theme || resolveTheme(getStoredPreference());
    }
  };
})();
