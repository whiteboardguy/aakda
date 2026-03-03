/* ============================================================
   main.js — Aakda client-side interactions
   Only handles what HTMX cannot: theme, sidebar, textarea resize,
   keyboard shortcuts, markdown rendering, form helpers.
   ============================================================ */

/* ── Markdown setup ── */
if (typeof marked !== 'undefined') {
  marked.setOptions({
    breaks: true,
    gfm: true,
  });
}

/* ── Render all unprocessed [data-markdown] elements ── */
function renderMarkdown() {
  if (typeof marked === 'undefined') return;

  document.querySelectorAll('[data-markdown]:not([data-rendered])').forEach(el => {
    const raw = el.textContent || el.innerText || '';
    if (!raw.trim()) return;
    el.innerHTML = (typeof DOMPurify !== 'undefined')
      ? DOMPurify.sanitize(marked.parse(raw))
      : marked.parse(raw);
    el.setAttribute('data-rendered', 'true');
  });

  /* Apply highlight.js to any new code blocks */
  if (typeof hljs !== 'undefined') {
    document.querySelectorAll('pre code:not([data-highlighted])').forEach(block => {
      hljs.highlightElement(block);
    });
  }
}

/* ── Scroll the messages area to the bottom ── */
function scrollToBottom() {
  const area = document.getElementById('messages-scroll');
  if (area) {
    area.scrollTop = area.scrollHeight;
  }
}

/* ── Active sidebar conversation tracking ── */
let _activeConvId = null;

function _setActiveSidebarItem(convId) {
  /* Remove active class from all items */
  document.querySelectorAll('.sidebar-item.active').forEach(el => {
    el.classList.remove('active');
  });
  if (!convId) return;
  const el = document.getElementById(`sidebar-conv-${convId}`);
  if (el) el.classList.add('active');
}

/* ── Update chat-form action to continue a specific conversation ── */
window.updateFormAction = function(convId) {
  const form = document.getElementById('chat-form');
  if (!form) return;
  form.setAttribute('hx-post', `/conversations/continue/${convId}`);
  htmx.process(form);
  _activeConvId = convId;
  _setActiveSidebarItem(convId);
};

/* ── Reset chat-form back to /conversations/new ── */
window.resetFormToNew = function() {
  const form = document.getElementById('chat-form');
  if (!form) return;
  form.setAttribute('hx-post', '/conversations/new');
  htmx.process(form);
  _activeConvId = null;
  _setActiveSidebarItem(null);
};

/* ── Toast notification ── */
window.showToast = function(message, durationMs = 3500) {
  const container = document.getElementById('ak-toast');
  if (!container) return;

  const item = document.createElement('div');
  item.className = 'ak-toast-item';
  item.innerHTML =
    `<span class="ak-toast-icon">` +
      `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" ` +
           `stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">` +
        `<polyline points="20 6 9 17 4 12"/>` +
      `</svg>` +
    `</span>` +
    `<span>${message}</span>`;
  container.appendChild(item);

  const remove = () => {
    item.classList.add('ak-toast-out');
    item.addEventListener('animationend', () => item.remove(), { once: true });
  };
  setTimeout(remove, durationMs);
};

/* ── Auth page: handle login/register response ── */
window.handleAuthResponse = function(event, successRedirect) {
  const detail = event.detail;
  if (detail.successful) {
    window.location = successRedirect;
  } else {
    const errEl  = document.getElementById('auth-error');
    const errTxt = document.getElementById('auth-error-text');
    if (errEl && errTxt) {
      errEl.classList.add('visible');
      try {
        const body = JSON.parse(detail.xhr.responseText);
        errTxt.textContent = body.detail || 'Invalid credentials.';
      } catch {
        errTxt.textContent = 'Something went wrong. Please try again.';
      }
    }
  }
};

/* ============================================================
   INLINE DELETE CONFIRMATION
   Intercepts clicks on [data-delete-btn]: first click arms the
   button ("Confirm?"), second click fires the htmx request
   (hx-trigger="confirmed"). Clicking outside or pressing Escape
   resets any armed buttons back to "Delete".
   ============================================================ */

function resetDeleteButtons() {
  document.querySelectorAll('[data-delete-btn][data-armed]').forEach(btn => {
    btn.removeAttribute('data-armed');
    btn.textContent = 'Delete';
  });
}

document.addEventListener('click', function(e) {
  const btn = e.target.closest('[data-delete-btn]');
  if (!btn) {
    resetDeleteButtons();
    return;
  }
  if (btn.hasAttribute('data-armed')) {
    /* Second click — fire the htmx request */
    htmx.trigger(btn, 'confirmed');
  } else {
    /* First click — arm: reset others, then arm this one */
    resetDeleteButtons();
    btn.setAttribute('data-armed', '');
    btn.textContent = 'Confirm?';
  }
});

/* ============================================================
   DOM READY
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {

  /* 1. Theme ------------------------------------------------ */
  /* Migrate legacy 'night' value to 'dark' */
  if (localStorage.getItem('ak-theme') === 'night') {
    localStorage.setItem('ak-theme', 'dark');
  }
  const savedTheme = localStorage.getItem('ak-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);

  const themeToggleBtn = document.getElementById('theme-toggle');
  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', () => {
      const cur  = document.documentElement.getAttribute('data-theme');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('ak-theme', next);
      updateThemeIcon(next);
    });
    updateThemeIcon(savedTheme);
  }

  function updateThemeIcon(theme) {
    const icon = document.getElementById('theme-icon');
    if (!icon) return;
    if (theme === 'light') {
      /* moon icon */
      icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
    } else {
      /* sun icon */
      icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
    }
  }

  /* 1b. Font ------------------------------------------------ */
  const FONT_CYCLE = ['serif', 'sans', 'mono'];
  const FONT_LABELS = { serif: 'Serif (Merriweather)', sans: 'Sans-serif', mono: 'Monospace' };

  const savedFont = localStorage.getItem('ak-font') || 'serif';
  _applyFont(savedFont);

  const fontToggleBtn = document.getElementById('font-toggle');
  if (fontToggleBtn) {
    fontToggleBtn.addEventListener('click', () => {
      const cur  = document.documentElement.getAttribute('data-font') || 'serif';
      const idx  = FONT_CYCLE.indexOf(cur);
      const next = FONT_CYCLE[(idx + 1) % FONT_CYCLE.length];
      _applyFont(next);
      localStorage.setItem('ak-font', next);
    });
  }

  function _applyFont(font) {
    if (font === 'serif') {
      document.documentElement.removeAttribute('data-font');
    } else {
      document.documentElement.setAttribute('data-font', font);
    }
    const btn = document.getElementById('font-toggle');
    if (btn) btn.setAttribute('title', 'Font: ' + (FONT_LABELS[font] || font));
  }

  /* 2. Sidebar collapse ------------------------------------ */
  const sidebar = document.getElementById('sidebar');
  const savedCollapsed = localStorage.getItem('ak-sidebar') === 'collapsed';
  if (sidebar && savedCollapsed) {
    sidebar.classList.add('collapsed');
  }

  window.toggleSidebar = function() {
    if (!sidebar) return;
    sidebar.classList.toggle('collapsed');
    localStorage.setItem('ak-sidebar',
      sidebar.classList.contains('collapsed') ? 'collapsed' : 'open');
  };

  /* 2b. Sidebar dropdown — position fixed to escape overflow clipping ------- */
  /* Uses mousedown so position is set before :focus-within shows the menu.   */
  document.addEventListener('mousedown', e => {
    const btn = e.target.closest('.sidebar-item-menu-btn');
    if (!btn) return;
    const menu = btn.closest('.dropdown')?.querySelector('.dropdown-content');
    if (!menu) return;
    const rect = btn.getBoundingClientRect();
    // Prefer opening below; if too close to bottom, open above
    const menuHeight = 96; // approx height of 2-item menu
    const spaceBelow = window.innerHeight - rect.bottom;
    if (spaceBelow >= menuHeight) {
      menu.style.top  = (rect.bottom + 4) + 'px';
    } else {
      menu.style.top  = (rect.top - menuHeight - 4) + 'px';
    }
    menu.style.left = rect.left + 'px';
  });

  /* 3. Textarea auto-resize -------------------------------- */
  function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }

  document.body.addEventListener('input', e => {
    if (e.target.classList.contains('chat-textarea')) {
      autoResize(e.target);
    }
  });

  /* 4. Ctrl+K / Cmd+K — focus input ---------------------- */
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      const input = document.getElementById('query-input');
      if (input) { input.focus(); input.select(); }
    }
    /* Esc — reset any pending delete confirmation, then blur input */
    if (e.key === 'Escape') {
      closeDeleteAllModal();
      resetDeleteButtons();
      document.activeElement?.blur?.();
    }
  });

  /* 5. Enter to submit (Shift+Enter = newline) ------------ */
  document.body.addEventListener('keydown', e => {
    if (e.target.id === 'query-input' && e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const form = document.getElementById('chat-form');
      if (form) htmx.trigger(form, 'submit');
    }
  });

  /* 6. Initial markdown render + scroll ------------------- */
  renderMarkdown();
  scrollToBottom();
});

/* ============================================================
   DELETE-ALL CONVERSATIONS MODAL
   ============================================================ */

window.openDeleteAllModal = function() {
  const modal = document.getElementById('delete-all-modal');
  if (!modal) return;
  /* Reset to initial state */
  const execBtn = document.getElementById('delete-all-execute');
  if (execBtn) { execBtn.textContent = 'Delete'; execBtn.removeAttribute('data-armed'); execBtn.disabled = false; }
  const cancelBtn = document.getElementById('delete-all-cancel');
  if (cancelBtn) cancelBtn.disabled = false;
  modal.classList.add('open');
};

window.closeDeleteAllModal = function() {
  const modal = document.getElementById('delete-all-modal');
  if (modal) modal.classList.remove('open');
};

window.handleDeleteAllConfirm = function(btn) {
  if (!btn.hasAttribute('data-armed')) {
    /* First click — arm */
    btn.setAttribute('data-armed', '');
    btn.textContent = 'Confirm?';
    return;
  }
  /* Second click — execute */
  btn.disabled = true;
  const cancelBtn = document.getElementById('delete-all-cancel');
  if (cancelBtn) cancelBtn.disabled = true;

  fetch('/conversations/delete-all', {
    method: 'POST',
    credentials: 'same-origin',
  }).finally(() => {
    const list = document.getElementById('sidebar-history-list');
    if (list) list.innerHTML = '';
    window.resetFormToNew();
    closeDeleteAllModal();
  });
};

/* Close on backdrop click */
document.addEventListener('click', function(e) {
  const modal = document.getElementById('delete-all-modal');
  if (modal && modal.classList.contains('open') && e.target === modal) {
    closeDeleteAllModal();
  }
});

/* ============================================================
   HTMX EVENT HOOKS
   ============================================================ */

/* After any HTMX swap settles: render markdown + scroll + restore active sidebar */
document.body.addEventListener('htmx:afterSettle', (evt) => {
  renderMarkdown();
  scrollToBottom();
  /* If the sidebar list just reloaded, re-apply the active item indicator */
  const target = evt.detail && evt.detail.target;
  if (target && target.id === 'sidebar-history-list') {
    _setActiveSidebarItem(_activeConvId);
  }
});

/* After HTMX request on #chat-form: reset textarea */
document.body.addEventListener('htmx:afterRequest', evt => {
  const elt = evt.detail.elt;

  /* Reset form after successful message submission */
  if (elt && elt.id === 'chat-form' && evt.detail.successful) {
    const textarea = document.getElementById('query-input');
    if (textarea) {
      textarea.value = '';
      textarea.style.height = 'auto';
      textarea.blur();
    }
  }

  /* Share conversation — copy link + show toast */
  if (!evt.detail.successful) return;
  const shareLink = evt.detail.xhr.getResponseHeader('X-Share-Link');
  if (!shareLink) return;
  const url = window.location.origin + '/conversations/s/' + shareLink;
  const notify = () => window.showToast('Share link copied to clipboard');
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(url).then(notify).catch(notify);
  } else {
    /* Non-HTTPS fallback: still show the toast even if clipboard is unavailable */
    try {
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    } catch (_) {}
    notify();
  }
});

/* Web search option toggle */
window.toggleWebSearch = function(btn) {
  btn.classList.toggle('active');
  const input = document.getElementById('opt-web-input');
  if (input) {
    input.value = btn.classList.contains('active') ? 'true' : 'false';
  }
};

/* ── Password visibility toggle (auth pages) ── */
window.toggleAuthPassword = function(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const isHidden = input.type === 'password';
  input.type = isHidden ? 'text' : 'password';
  btn.classList.toggle('revealed', isHidden);
  btn.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
};
window.addEventListener('message', function(e) {
  if (e.origin !== window.location.origin) return;
  if (!e.data || e.data.type !== 'ak-chart-resize') return;
  const iframes = document.querySelectorAll('.chart-iframe');
  for (const iframe of iframes) {
    try {
      if (iframe.contentWindow === e.source) {
        iframe.style.height = e.data.height + 'px';
        break;
      }
    } catch (_) {}
  }
});

/* ============================================================
   CHART MODAL
   ============================================================ */

window.expandChart = function(btn) {
  const container = btn.closest('.chart-container');
  if (!container) return;
  const inlineIframe = container.querySelector('.chart-iframe');
  if (!inlineIframe) return;

  const modal      = document.getElementById('chart-modal');
  const modalFrame = document.getElementById('chart-modal-iframe');
  const loader     = document.getElementById('chart-modal-loader');
  if (!modal || !modalFrame) return;

  /* If already open, clear previous content first */
  if (modal.classList.contains('open')) {
    modalFrame.srcdoc = '';
    modalFrame.classList.remove('loaded');
  }

  /* Reset loader to visible */
  if (loader) loader.classList.remove('hidden');
  modalFrame.classList.remove('loaded');

  /* Build srcdoc: override Plotly's fixed height, then fire resize so it
     re-lays out to fill 100vh. Two timeouts cover sync and async init. */
  const src = inlineIframe.srcdoc || '';
  const fillStyle = '<style>' +
    'html,body{margin:0;padding:0;height:100%!important;overflow:hidden!important}' +
    '.plotly-graph-div{height:100vh!important;width:100%!important}' +
    '</style>' +
    '<script>window.addEventListener("load",function(){' +
      'window.dispatchEvent(new Event("resize"));' +
      'setTimeout(function(){window.dispatchEvent(new Event("resize"));},200);' +
    '});<\/script>';
  const injected = src.includes('</head>')
    ? src.replace('</head>', fillStyle + '</head>')
    : fillStyle + src;
  modalFrame.srcdoc = injected;

  /* Open backdrop + panel immediately */
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';
  history.pushState({ chartModal: true }, '');

  /* Once iframe has loaded and Plotly has re-rendered, fade chart in */
  modalFrame.addEventListener('load', function onLoad() {
    modalFrame.removeEventListener('load', onLoad);
    /* Wait for the 200 ms resize + one paint cycle */
    setTimeout(function() {
      if (loader) loader.classList.add('hidden');
      modalFrame.classList.add('loaded');
    }, 260);
  }, { once: true });
};

window.closeChartModal = function() {
  const modal      = document.getElementById('chart-modal');
  const modalFrame = document.getElementById('chart-modal-iframe');
  if (!modal || !modal.classList.contains('open')) return;

  /* Animate out */
  modal.classList.remove('open');
  document.body.style.overflow = '';

  /* Clear srcdoc only after the CSS transition finishes (300 ms panel + small buffer)
     so there's no flash of blank content during the close animation. */
  setTimeout(function() {
    if (modalFrame) {
      modalFrame.srcdoc = '';
      modalFrame.classList.remove('loaded');
    }
    const loader = document.getElementById('chart-modal-loader');
    if (loader) loader.classList.remove('hidden');
  }, 320);
};

/* Backdrop click — called by onclick on the overlay element in base.html */
window.handleChartModalBackdropClick = function(e) {
  /* Only close when the click target is the backdrop itself, not the inner panel */
  const modal = document.getElementById('chart-modal');
  if (modal && e.target === modal) {
    history.back();
  }
};

/* Escape key — close modal (takes priority over the existing blur-on-Escape handler) */
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    const modal = document.getElementById('chart-modal');
    if (modal && modal.classList.contains('open')) {
      e.stopImmediatePropagation();
      history.back();
    }
  }
}, true /* capture phase — runs before the existing keydown listener */);

/* Browser back button — close modal instead of navigating away */
window.addEventListener('popstate', function(e) {
  const modal = document.getElementById('chart-modal');
  if (modal && modal.classList.contains('open')) {
    closeChartModal();
  }
});
