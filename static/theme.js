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
