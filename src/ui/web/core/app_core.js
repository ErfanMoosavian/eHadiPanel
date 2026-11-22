window.eHadiApp = (() => {
  const THEME_KEY = 'ehadi_saas_theme';
  const SIDEBAR_KEY = 'ehadi_sidebar_collapsed';

  const registry = {
    modals: new Map(),
    commands: [],
    settingsTabs: [],
    sidebarActions: [],
  };

  const icon = (name, size = 16) => (window.eHadiIcons ? window.eHadiIcons.get(name, size) : '');

  // ==================== Toast انیمیشنی ====================
  function toast(msg, kind = 'info') {
    let stack = document.getElementById('proToastStack');
    if (!stack) {
      stack = document.createElement('div');
      stack.id = 'proToastStack';
      stack.className = 'pro-toast-stack';
      document.body.appendChild(stack);
    }
    const el = document.createElement('div');
    el.className = `pro-toast pro-toast-${kind}`;
    el.innerHTML = `<span class="pro-toast-ico">${icon('check', 15)}</span><span></span>`;
    el.querySelector('span:last-child').textContent = String(msg || '');
    stack.appendChild(el);
    setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 220); }, 2900);
  }
  window.showToast = toast;

  // ==================== مدیریت تم روشن و تیره ====================
  function applyTheme(theme) {
    const t = theme === 'light' ? 'light' : 'dark';
    document.body.setAttribute('data-studio-theme', t);
    try { localStorage.setItem(THEME_KEY, t); } catch (_) {}
    document.querySelectorAll('.studio-theme-btn').forEach(b => b.classList.toggle('active', b.dataset.theme === t));
    const qBtn = document.getElementById('btnQuickTheme');
    if (qBtn) qBtn.innerHTML = icon(t === 'light' ? 'moon' : 'sun', 16);
  }

  function toggleTheme() {
    applyTheme(document.body.getAttribute('data-studio-theme') === 'light' ? 'dark' : 'light');
  }

  // ==================== تولتیپ شناور ۶۰ فریم برای سایدبار جمع‌شده ====================
  function ensureTooltipPortal() {
    let tip = document.getElementById('proFloatingTooltip');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'proFloatingTooltip';
      tip.className = 'pro-floating-tooltip';
      document.body.appendChild(tip);
    }
    return tip;
  }

  function showNavTooltip(_btn) {
    // Unified tooltip engine (#ehGlassTooltip in executive_ux.js) handles all tooltips cleanly
    const legacy = document.getElementById('proFloatingTooltip');
    if (legacy) legacy.remove();
  }

  function hideNavTooltip() {
    const tip = document.getElementById('proFloatingTooltip');
    if (tip) tip.classList.remove('visible');
  }

  // ==================== سایدبار روان با انیمیشن واقعی عرض ====================
  function prepareSidebar() {
    const sb = document.getElementById('sidebar') || document.querySelector('.sidebar');
    if (!sb) return null;

    // تبدیل شل اصلی به flex-row در صورت grid بودن برای انیمیشن کاملاً روان width
    const shell = sb.parentElement;
    if (shell && !shell.dataset.proShellReady) {
      shell.dataset.proShellReady = '1';
      const st = window.getComputedStyle(shell);
      if (st.display === 'grid' && shell.children.length === 2) {
        shell.classList.add('pro-smooth-shell');
      }
    }

    // درج اکشن‌های ثبت‌شده در رجیستری سایدبار
    const navList = sb.querySelector('.nav-list');
    if (navList) {
      registry.sidebarActions.forEach(act => {
        const btnId = `navAction_${act.id}`;
        if (document.getElementById(btnId)) return;
        const btn = document.createElement('button');
        btn.id = btnId;
        btn.type = 'button';
        btn.className = 'nav-btn';
        btn.innerHTML = `${icon(act.icon, 19)}<span class="pro-nav-lbl">${act.label}</span>`;
        btn.addEventListener('click', (e) => { e.preventDefault(); act.onClick && act.onClick(); });
        navList.appendChild(btn);
      });
    }

    // ایزوله‌سازی متن‌های تمام دکمه‌های .nav-btn و اتصال تولتیپ شناور
    sb.querySelectorAll('.nav-btn').forEach(btn => {
      if (btn.dataset.proNavReady === '1') return;
      btn.dataset.proNavReady = '1';
      const lblText = (btn.textContent || '').trim().replace(/\s+/g, ' ');
      if (lblText) btn.setAttribute('data-tooltip', lblText);

      Array.from(btn.childNodes).forEach(node => {
        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
          const sp = document.createElement('span');
          sp.className = 'pro-nav-lbl';
          sp.textContent = node.textContent.trim();
          btn.replaceChild(sp, node);
        } else if (node.nodeType === Node.ELEMENT_NODE && node.tagName.toLowerCase() !== 'svg' && !node.querySelector('svg')) {
          node.classList.add('pro-nav-lbl');
        }
      });

      btn.addEventListener('mouseenter', () => showNavTooltip(btn));
      btn.addEventListener('mouseleave', hideNavTooltip);
      btn.addEventListener('click', hideNavTooltip);
    });

    // سوییچر تم در سایدبار
    if (!document.getElementById('studioThemeSwitcher')) {
      const anchor = sb.querySelector('.nav-section-label') || sb.querySelector('.nav-list');
      const box = document.createElement('div');
      box.id = 'studioThemeSwitcher';
      box.className = 'studio-theme-switcher';
      box.innerHTML = `
        <button type="button" class="studio-theme-btn" data-theme="light">${icon('sun', 13)}<span>روشن</span></button>
        <button type="button" class="studio-theme-btn" data-theme="dark">${icon('moon', 13)}<span>تیره</span></button>
      `;
      if (anchor && anchor.parentElement) anchor.parentElement.insertBefore(box, anchor);
      else sb.appendChild(box);
      box.querySelectorAll('.studio-theme-btn').forEach(b => b.addEventListener('click', () => applyTheme(b.dataset.theme)));
    }
    return sb;
  }

  function toggleSidebar(force) {
    prepareSidebar();
    hideNavTooltip();
    const next = typeof force === 'boolean' ? force : !document.body.classList.contains('sidebar-collapsed');
    document.body.classList.toggle('sidebar-collapsed', next);
    try { localStorage.setItem(SIDEBAR_KEY, next ? '1' : '0'); } catch (_) {}
    if (!next && typeof window.moveIndicator === 'function') {
      setTimeout(() => window.moveIndicator(document.querySelector('.nav-btn.active')), 340);
    }
  }

  // ==================== مدیریت یکپارچه مودال‌ها (پاپ‌آپ با منوی سمت راست) ====================
  function registerModal(id, config) {
    registry.modals.set(id, config);
  }

  function openModal(id, opts = {}) {
    closeAllModals();
    const cfg = registry.modals.get(id);
    if (!cfg) return;
    let bd = document.getElementById(`proModal_${id}`);
    if (!bd) {
      bd = document.createElement('div');
      bd.id = `proModal_${id}`;
      bd.className = 'pro-overlay-root';
      bd.innerHTML = cfg.render();
      bd.addEventListener('click', (e) => { if (e.target === bd) closeAllModals(); });
      document.body.appendChild(bd);
      bd.querySelectorAll('[data-close-modal]').forEach(btn => btn.addEventListener('click', closeAllModals));
      cfg.onMount && cfg.onMount(bd);
    }
    cfg.onOpen && cfg.onOpen(bd, opts);
    requestAnimationFrame(() => bd.classList.add('open'));
  }

  function closeAllModals() {
    document.querySelectorAll('.pro-overlay-root.open').forEach(el => el.classList.remove('open'));
  }

  // ==================== کنترل پنجره و ریسایز ۸ جهته ====================
  function triggerMaximize() {
    if (window.pywebview?.api?.toggle_maximize) window.pywebview.api.toggle_maximize();
    else if (window.pywebview?.api?.toggle_maximize_window) window.pywebview.api.toggle_maximize_window();
  }

  function mountResizeHandles() {
    if (document.querySelector('.win-resize-handle')) return;
    [['n','top'],['s','bottom'],['e','right'],['w','left'],['ne','top-right'],['nw','top-left'],['se','bottom-right'],['sw','bottom-left']].forEach(([c, dir]) => {
      const h = document.createElement('div');
      h.className = `win-resize-handle win-resize-${c}`;
      h.addEventListener('mousedown', async (e) => {
        if (e.button !== 0) return;
        e.preventDefault(); e.stopPropagation();
        const b = await window.pywebview?.api?.get_window_bounds?.();
        if (!b || !b.ok) return;
        const sx = e.screenX, sy = e.screenY;
        const bx = b.x, by = b.y, bw = b.w, bh = b.h;
        let raf = false, latest = null;
        const onMove = (mv) => {
          const dx = mv.screenX - sx, dy = mv.screenY - sy;
          let nx = bx, ny = by, nw = bw, nh = bh;
          if (dir.includes('right')) nw = Math.max(1024, bw + dx);
          if (dir.includes('bottom')) nh = Math.max(680, bh + dy);
          if (dir.includes('left')) { nw = Math.max(1024, bw - dx); nx = bx + (bw - nw); }
          if (dir.includes('top')) { nh = Math.max(680, bh - dy); ny = by + (bh - nh); }
          latest = [nx, ny, nw, nh];
          if (!raf) {
            raf = true;
            requestAnimationFrame(() => {
              raf = false;
              if (latest) window.pywebview?.api?.set_window_bounds?.(...latest);
            });
          }
        };
        const onUp = () => {
          window.removeEventListener('mousemove', onMove);
          window.removeEventListener('mouseup', onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
      });
      document.body.appendChild(h);
    });
  }

  // ==================== نوار ابزار سریع بالا با آیکون‌های فلت ====================
  function mountTopbar() {
    const main = document.querySelector('.main-content, main');
    if (!main || document.getElementById('proTopbar')) return;
    const bar = document.createElement('div');
    bar.id = 'proTopbar';
    bar.className = 'pro-topbar';
    bar.innerHTML = `
      <div class="pro-topbar-right">
        <button class="pro-icon-btn" id="btnToggleSidebar" title="جمع/باز کردن سایدبار (Ctrl+B)">${icon('panelRight', 16)}</button>
        <span class="pro-breadcrumb" id="proBreadcrumb">مؤسسه علمی فرهنگی امام هادی (علیه‌السلام)</span>
      </div>
      <div class="pro-topbar-left">
        <button class="pro-cmd-trigger" id="btnOpenCmdPalette">
          ${icon('search', 14)}
          <span>جست‌وجو و دستورات...</span>
          <span class="pro-kbd">Ctrl + K</span>
        </button>
        <button class="pro-icon-btn" id="btnQuickMedia" title="تولید محتوای رسانه‌ای">${icon('penTool', 16)}</button>
        <button class="pro-icon-btn" id="btnQuickSettings" title="تنظیمات سیستم (Ctrl+,)">${icon('settings', 16)}</button>
        <button class="pro-icon-btn" id="btnQuickTheme" title="تغییر تم روشن/تیره">${icon('sun', 16)}</button>
        <button class="pro-icon-btn" id="btnQuickFull" title="بزرگ‌نمایی / بازگردانی">${icon('maximize', 15)}</button>
      </div>
    `;
    main.insertBefore(bar, main.firstChild);
    document.getElementById('btnToggleSidebar').addEventListener('click', () => toggleSidebar());
    document.getElementById('btnOpenCmdPalette').addEventListener('click', () => openModal('cmd_palette'));
    document.getElementById('btnQuickMedia').addEventListener('click', () => openModal('media_studio'));
    document.getElementById('btnQuickSettings').addEventListener('click', () => openModal('preferences'));
    document.getElementById('btnQuickTheme').addEventListener('click', toggleTheme);
    document.getElementById('btnQuickFull').addEventListener('click', triggerMaximize);
  }

  // ==================== همگام‌سازی لوگوی شفاف PNG ====================
  async function syncSidebarLogo() {
    try {
      const sb = document.getElementById('sidebar') || document.querySelector('.sidebar');
      if (!sb) return;
      // Remove any legacy duplicate banner so only the clean single calligraphy crest renders
      const oldBanner = document.getElementById('studioLogoBanner');
      if (oldBanner) oldBanner.remove();
      const brandEl = sb.querySelector('.brand.eh-brand-logo-only');
      if (brandEl) {
        brandEl.style.removeProperty('display');
        const img = brandEl.querySelector('.eh-brand-logo-img');
        const res = await window.pywebview?.api?.get_branding_settings?.();
        const uri = res && res.logo_data_uri;
        // Only swap if user explicitly saved a custom logo data URI
        if (img && uri && res?.branding?.logo_path) {
          img.src = uri;
        }
      }
    } catch (_) {}
  }

  function goPage(id) {
    if (String(id).toLowerCase() === 'settings') { openModal('preferences'); return; }
    const btn = document.querySelector(`.nav-btn[onclick*="'${id}'"]`);
    if (typeof window.switchPage === 'function') window.switchPage(id, btn);
  }

  function hookBaseFunctions() {
    if (typeof window.switchPage === 'function' && !window.switchPage._v52Hooked) {
      const orig = window.switchPage;
      const wrapped = function (pageId, btn) {
        if (String(pageId).toLowerCase() === 'settings') { openModal('preferences'); return; }
        return orig.apply(this, arguments);
      };
      wrapped._v52Hooked = true;
      window.switchPage = wrapped;
    }
    document.querySelectorAll('.win-btn[onclick*="toggle_maximize"]').forEach(btn => {
      if (btn.dataset.maxHooked === '1') return;
      btn.dataset.maxHooked = '1';
      btn.removeAttribute('onclick');
      btn.addEventListener('click', (e) => { e.preventDefault(); triggerMaximize(); });
    });
  }

  // ==================== میانبرهای کیبورد ====================
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAllModals();
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openModal('cmd_palette'); }
    else if ((e.ctrlKey || e.metaKey) && e.key === ',') { e.preventDefault(); openModal('preferences'); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') { e.preventDefault(); toggleSidebar(); }
    else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 't') { e.preventDefault(); toggleTheme(); }
    else if ((e.ctrlKey || e.metaKey) && ['1', '2', '3'].includes(e.key)) { e.preventDefault(); goPage({ '1': 'dashboard', '2': 'chat', '3': 'docs' }[e.key]); }
    else if (e.key === 'F11') { e.preventDefault(); triggerMaximize(); }
  });

  function boot() {
    hookBaseFunctions();
    prepareSidebar();
    mountResizeHandles();
    mountTopbar();
    let savedTheme = 'dark';
    try { savedTheme = localStorage.getItem(THEME_KEY) || 'dark'; } catch (_) {}
    applyTheme(savedTheme);
    try { if (localStorage.getItem(SIDEBAR_KEY) === '1') toggleSidebar(true); } catch (_) {}
  }

  window.addEventListener('pywebviewready', () => { boot(); setTimeout(syncSidebarLogo, 120); });
  window.refreshStudioLogo = syncSidebarLogo;

  return {
    boot,
    icon,
    toast,
    goPage,
    applyTheme,
    toggleTheme,
    toggleSidebar,
    triggerMaximize,
    registerModal,
    openModal,
    closeAllModals,
    registerCommand: (cmd) => registry.commands.push(cmd),
    getCommands: () => registry.commands,
    registerSettingsTab: (tab) => registry.settingsTabs.push(tab),
    getSettingsTabs: () => registry.settingsTabs,
    registerSidebarAction: (act) => registry.sidebarActions.push(act),
  };
})();
