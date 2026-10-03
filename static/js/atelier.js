/**
 * ELECTROCART // Atelier Core JavaScript Engine
 * Resilient, accessible, modular interactions with progressive enhancement
 */

(function () {
  'use strict';

  // 1. CSRF Token Helper
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  window.getCookie = getCookie;

  // 2. Toast Notification System
  function showToast(message, type = 'info') {
    let toast = document.getElementById('atelier-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'atelier-toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      toast.className = 'fixed bottom-6 right-6 z-50 transform translate-y-24 opacity-0 transition-all duration-300 bg-umber text-vellum px-5 py-3 rounded-sm font-mono text-xs flex items-center space-x-3 shadow-2xl border border-solarOxide';
      document.body.appendChild(toast);
    }

    toast.innerHTML = `
      <span class="w-2 h-2 rounded-full bg-solarOxide animate-ping"></span>
      <span id="atelier-toast-text">${message}</span>
    `;

    toast.classList.remove('translate-y-24', 'opacity-0');
    toast.classList.add('translate-y-0', 'opacity-100');

    clearTimeout(window._toastTimeout);
    window._toastTimeout = setTimeout(() => {
      toast.classList.add('translate-y-24', 'opacity-0');
      toast.classList.remove('translate-y-0', 'opacity-100');
    }, 3200);
  }
  window.showToast = showToast;

  // 3. Command Suite Drawer Navigation (Accessible)
  function initDrawer() {
    const drawer = document.getElementById('account-drawer');
    const scrim = document.getElementById('account-drawer-scrim');
    const trigger = document.getElementById('account-drawer-trigger');
    const closeBtn = document.getElementById('account-drawer-close');

    if (!drawer || !scrim) return;

    function openDrawer() {
      drawer.classList.remove('-translate-x-full');
      scrim.classList.remove('opacity-0', 'pointer-events-none');
      scrim.classList.add('opacity-100');
      if (trigger) trigger.setAttribute('aria-expanded', 'true');
      if (closeBtn) closeBtn.focus();
    }

    function closeDrawer() {
      drawer.classList.add('-translate-x-full');
      scrim.classList.remove('opacity-100');
      scrim.classList.add('opacity-0', 'pointer-events-none');
      if (trigger) {
        trigger.setAttribute('aria-expanded', 'false');
        trigger.focus();
      }
    }

    if (trigger) trigger.addEventListener('click', openDrawer);
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    if (scrim) scrim.addEventListener('click', closeDrawer);

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !drawer.classList.contains('-translate-x-full')) {
        closeDrawer();
      }
    });
  }

  // 4. Overclock (Dark Mode) Theme Engine
  function initTheme() {
    const toggleBtn = document.getElementById('theme-mode-toggle');
    const label = document.getElementById('theme-mode-label');
    const currentTheme = localStorage.getItem('ec_theme') || 'studio';

    function applyTheme(theme) {
      if (theme === 'overclock') {
        document.body.classList.add('mode-overclock');
        if (label) label.textContent = 'MODE: [OVERCLOCK]';
      } else {
        document.body.classList.remove('mode-overclock');
        if (label) label.textContent = 'MODE: [STUDIO]';
      }
      localStorage.setItem('ec_theme', theme);
    }

    applyTheme(currentTheme);

    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const isDark = document.body.classList.contains('mode-overclock');
        applyTheme(isDark ? 'studio' : 'overclock');
      });
    }
  }

  // 5. Global Search Keyboard Shortcut ('/' or 'Cmd/Ctrl + K')
  function initSearchShortcuts() {
    const searchInput = document.getElementById('global-search-input');
    if (!searchInput) return;

    document.addEventListener('keydown', (e) => {
      if (
        (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') ||
        (e.key === 'k' && (e.metaKey || e.ctrlKey))
      ) {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
    });
  }

  // 6. Progressive Enhancement for Add-to-Cart & Wishlist
  function initAjaxActions() {
    // Intercept forms with data-ajax-cart
    document.addEventListener('submit', async (e) => {
      const form = e.target.closest('[data-ajax-cart]');
      if (!form) return;

      e.preventDefault();
      const submitBtn = form.querySelector('button[type="submit"]') || form.querySelector('button');
      const originalText = submitBtn ? submitBtn.innerHTML : '';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = 'ALLOCATING...';
      }

      try {
        const formData = new FormData(form);
        const resp = await fetch(form.action, {
          method: 'POST',
          body: formData,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': getCookie('csrftoken') || ''
          }
        });

        const data = await resp.json();
        if (resp.ok && data.status === 'success') {
          showToast(data.message || 'Specimen added to bag.');
          const badges = document.querySelectorAll('.nav-cart-badge');
          badges.forEach(b => { b.textContent = data.cart_count; });
          if (submitBtn) submitBtn.innerHTML = 'ALLOCATED ✓';
          setTimeout(() => {
            if (submitBtn) {
              submitBtn.innerHTML = originalText;
              submitBtn.disabled = false;
            }
          }, 1500);
        } else if (data.status === 'warning') {
          showToast(data.message || 'Quantity limit reached.', 'warning');
          if (submitBtn) {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
          }
        } else {
          showToast(data.message || 'Unable to allocate product.', 'error');
          if (submitBtn) {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
          }
        }
      } catch (err) {
        // Fallback to standard HTTP form submission on network/script error
        form.submit();
      }
    });

    // Intercept wishlist toggle forms with data-ajax-wishlist
    document.addEventListener('submit', async (e) => {
      const form = e.target.closest('[data-ajax-wishlist]');
      if (!form) return;

      e.preventDefault();
      const submitBtn = form.querySelector('button[type="submit"]') || form.querySelector('button');

      try {
        const formData = new FormData(form);
        const resp = await fetch(form.action, {
          method: 'POST',
          body: formData,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': getCookie('csrftoken') || ''
          }
        });

        if (resp.status === 401) {
          const data = await resp.json();
          window.location.href = data.redirect_url || '/login/';
          return;
        }

        const data = await resp.json();
        if (resp.ok && data.status === 'success') {
          showToast(data.is_saved ? 'Specimen saved to collection.' : 'Removed from collection.');
          const badges = document.querySelectorAll('.nav-wishlist-badge');
          badges.forEach(b => { b.textContent = data.wishlist_count; });
          if (submitBtn) {
            submitBtn.textContent = data.is_saved ? '♥ IN RESERVE' : '♡ SAVE SPECIMEN';
          }
        }
      } catch (err) {
        form.submit();
      }
    });
  }

  // Initialize all listeners when DOM is loaded
  document.addEventListener('DOMContentLoaded', () => {
    initDrawer();
    initTheme();
    initSearchShortcuts();
    initAjaxActions();
  });
})();

