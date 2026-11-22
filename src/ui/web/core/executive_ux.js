(() => {
  const PALETTE_KEY = 'ehadi_accent_scheme';
  const DENSITY_KEY = 'ehadi_ui_density';
  const EITA_TPL_KEY = 'ehadi_eitaa_templates_v1';
  const ic = (name, size = 17) => (window.eHadiIcons ? window.eHadiIcons.get(name, size) : '');
  const toFa = (n) => Number(n || 0).toLocaleString('fa-IR');

  const INST_NAME = '\u0645\u0624\u0633\u0633\u0647 \u0627\u0645\u0627\u0645 \u0647\u0627\u062f\u06cc';
  const ALAYH_TEXT = '\u0639\u0644\u06cc\u0647\u200c\u0627\u0644\u0633\u0644\u0627\u0645';
  const INST_HTML = `${INST_NAME} <span class="eh-honorific">${ALAYH_TEXT}</span>`;

  const PAGE_TITLES = {
    dashboard: '\u062f\u0627\u0634\u0628\u0648\u0631\u062f',
    chat: '\u062f\u0633\u062a\u06cc\u0627\u0631 \u0647\u0648\u0634\u0645\u0646\u062f',
    docs: '\u0627\u0633\u0646\u0627\u062f \u0648 \u0641\u0627\u06cc\u0644\u200c\u0647\u0627',
    exec_analytics: '\u0622\u0645\u0627\u0631 \u0648 \u0646\u0645\u0648\u062f\u0627\u0631\u0647\u0627',
    event_pipeline: '\u0631\u0648\u06cc\u062f\u0627\u062f\u0647\u0627',
    letter_registry: '\u062f\u0628\u06cc\u0631\u062e\u0627\u0646\u0647',
  };

  // Surgically tag ONLY the 4 rows inside the "????? ???????????" card (zero collateral damage)
  function tagSubsystemCard() {
    const headings = document.querySelectorAll('h2, h3, h4, .card-title');
    for (const h of headings) {
      if ((h.textContent || '').includes('\u0648\u0636\u0639\u06cc\u062a \u0632\u06cc\u0631\u0633\u06cc\u0633\u062a\u0645')) {
        const card = h.closest('.glass-card') || h.parentElement?.parentElement;
        if (!card || card.dataset.ehSubsysTagged === '1') continue;
        card.dataset.ehSubsysTagged = '1';
        const rows = Array.from(card.querySelectorAll('.pipeline-item')).filter(el => !el.classList.contains('eh-subsys-item'));
        if (rows.length) {
          const listParent = rows[0].parentElement;
          if (listParent && listParent !== card) listParent.classList.add('eh-subsys-list');
          rows.forEach(r => r.classList.add('eh-subsys-row'));
        }
      }
    }
  }

  function applyCleanHonorificInTitlebar() { return;
    const tb = document.querySelector('.titlebar');
    if (!tb) return;
    tb.querySelectorAll('span, div').forEach(el => {
      if (el.children.length === 0 && el.textContent && el.textContent.includes(INST_NAME) && !el.dataset.ehHonDone) {
        el.dataset.ehHonDone = '1';
        el.innerHTML = el.textContent
          .replaceAll(`${INST_NAME} (\u0639\u0644\u06cc\u0647\u200c\u0627\u0644\u0633\u0644\u0627\u0645)`, INST_HTML)
          .replaceAll(`${INST_NAME} (\u0639)`, INST_HTML)
          .replaceAll(`${INST_NAME}\u0611`, INST_HTML)
          .replace(new RegExp(INST_NAME + '(?!\\s*<span)'), INST_HTML);
      }
    });
  }

  function hookDotlessToasts() {
    if (typeof window.showToast === 'function' && !window.showToast._v29Hooked) {
      const origToast = window.showToast;
      const cleanToast = function (msg, ...rest) {
        const cleaned = String(msg ?? '').replace(/[\.\u06d4]+\s*$/g, '').trim();
        return origToast.call(this, cleaned, ...rest);
      };
      cleanToast._v29Hooked = true;
      window.showToast = cleanToast;
    }
    const stack = document.getElementById('proToastStack') || document.querySelector('.pro-toast-stack');
    if (stack && !stack._v29Obs) {
      stack._v29Obs = true;
      new MutationObserver(() => {
        stack.querySelectorAll('.pro-toast').forEach(t => {
          t.setAttribute('dir', 'rtl');
          t.querySelectorAll('span, div').forEach(n => {
            if (n.children.length === 0 && n.textContent) {
              n.textContent = n.textContent.replace(/[\.\u06d4]+\s*$/g, '').trim();
            }
          });
        });
      }).observe(stack, { childList: true, subtree: true });
    }
  }

  // Prevent Enter/Space from EVER toggling maximize/restore via focused titlebar buttons
  function setupSmoothWindowControls() {
    if (!window._v29EnterGuard) {
      window._v29EnterGuard = true;
      document.addEventListener('keydown', (e) => {
        if ((e.key === 'Enter' || e.key === ' ') && document.activeElement?.closest?.('.titlebar')) {
          e.preventDefault();
          e.stopPropagation();
          document.activeElement.blur();
          return;
        }
        if (e.key === 'Enter' && e.altKey) {
          e.preventDefault();
          e.stopPropagation();
        }
      }, true);
    }

    const tb = document.querySelector('.titlebar');
    if (!tb || tb.dataset.v29WinHooked === '1') return;
    tb.dataset.v29WinHooked = '1';

    const triggerMorph = () => {
      document.body.classList.remove('eh-win-morphing');
      void document.body.offsetWidth;
      document.body.classList.add('eh-win-morphing');
      setTimeout(() => document.body.classList.remove('eh-win-morphing'), 380);
    };

    tb.querySelectorAll('button').forEach(btn => {
      btn.setAttribute('tabindex', '-1');
      btn.addEventListener('mousedown', (e) => { e.preventDefault(); });
      btn.addEventListener('click', () => {
        btn.blur();
        const oc = btn.getAttribute('onclick') || '';
        if (oc.includes('max') || oc.includes('toggle')) triggerMorph();
      });
    });

    tb.addEventListener('dblclick', (e) => {
      if (e.target.closest('button, input, a')) return;
      triggerMorph();
      if (typeof window.toggleMax === 'function') window.toggleMax();
      else window.pywebview?.api?.toggle_maximize?.();
    });
  }

  function updateBreadcrumb(key) {
    const el = document.getElementById('proBreadcrumb');
    if (!el) return;
    const sub = PAGE_TITLES[key];
    el.innerHTML = sub ? `${INST_HTML} &nbsp;\u2039&nbsp; ${sub}` : INST_HTML;
  }

  function syncNavIndicator(btn) {
    const ind = document.getElementById('navIndicator');
    const navList = document.querySelector('#sidebar .nav-list');
    if (!ind || !navList) return;
    if (!btn || !navList.contains(btn)) { ind.style.opacity = '0'; return; }
    ind.style.opacity = '1';
    ind.style.height = btn.offsetHeight + 'px';
    ind.style.transform = `translateY(${btn.offsetTop}px)`;
  }

  function mountAmbientMesh() {
    if (document.querySelector('.eh-ambient-canvas')) return;
    const mesh = document.createElement('div');
    mesh.className = 'eh-ambient-canvas';
    mesh.setAttribute('aria-hidden', 'true');
    mesh.innerHTML = '<span></span><span></span><span></span>';
    document.body.insertBefore(mesh, document.body.firstChild);
  }

  function refreshAllChartsTheme() {
    try {
      if (typeof window.loadDashboardStats === 'function') window.loadDashboardStats();
      const refExec = document.getElementById('btnRefreshExec');
      if (refExec && document.getElementById('proModal_exec_analytics')?.classList.contains('active')) {
        refExec.click();
      }
    } catch (_) {}
  }

  function applyPalette(scheme, persistBackend = false) {
    const sc = scheme === 'navy' ? 'navy' : 'emerald';
    document.body.setAttribute('data-accent-scheme', sc);
    try { localStorage.setItem(PALETTE_KEY, sc); } catch (_) {}
    document.querySelectorAll('[data-set-palette]').forEach(el => {
      el.classList.toggle('active', el.dataset.setPalette === sc);
    });
    const qPal = document.getElementById('btnQuickPalette');
    if (qPal) {
      qPal.title = sc === 'navy'
        ? '\u0631\u0646\u06af\u200c\u0628\u0646\u062f\u06cc: \u0633\u0631\u0645\u0647\u200c\u0627\u06cc (\u062a\u063a\u06cc\u06cc\u0631 \u0628\u0647 \u0633\u0628\u0632 \u0632\u0645\u0631\u062f\u06cc)'
        : '\u0631\u0646\u06af\u200c\u0628\u0646\u062f\u06cc: \u0633\u0628\u0632 \u0632\u0645\u0631\u062f\u06cc (\u062a\u063a\u06cc\u06cc\u0631 \u0628\u0647 \u0633\u0631\u0645\u0647\u200c\u0627\u06cc)';
    }
    refreshAllChartsTheme();
    if (persistBackend) {
      window.pywebview?.api?.save_branding_settings?.({ ui_palette: sc }).catch?.(() => {});
    }
  }

  function applyDensity(mode, persistBackend = false) {
    const d = mode === 'compact' ? 'compact' : 'comfortable';
    document.body.setAttribute('data-ui-density', d);
    try { localStorage.setItem(DENSITY_KEY, d); } catch (_) {}
    document.querySelectorAll('[data-set-density]').forEach(el => {
      el.classList.toggle('active', el.dataset.setDensity === d);
    });
    if (persistBackend) {
      window.pywebview?.api?.save_branding_settings?.({ ui_density: d }).catch?.(() => {});
    }
  }

  function togglePalette() {
    const cur = document.body.getAttribute('data-accent-scheme') || 'navy';
    applyPalette(cur === 'navy' ? 'emerald' : 'navy', true);
    window.showToast?.(cur === 'navy'
      ? '\u0631\u0646\u06af\u200c\u0628\u0646\u062f\u06cc \u0633\u0628\u0632 \u0632\u0645\u0631\u062f\u06cc \u0641\u0639\u0627\u0644 \u0634\u062f'
      : '\u0631\u0646\u06af\u200c\u0628\u0646\u062f\u06cc \u0633\u0631\u0645\u0647\u200c\u0627\u06cc \u0641\u0639\u0627\u0644 \u0634\u062f');
  }

  let initPal = 'navy', initDen = 'comfortable';
  try {
    initPal = localStorage.getItem(PALETTE_KEY) || 'navy';
    initDen = localStorage.getItem(DENSITY_KEY) || 'comfortable';
  } catch (_) {}
  applyPalette(initPal, false);
  applyDensity(initDen, false);

  document.addEventListener('pointermove', (e) => {
    const card = e.target.closest?.('.glass-card, .eh-kpi, .eh-quick-card, .bi-card, .bi-kpi, .eh-chart-box, #sidebar .nav-btn, #sidebar .eh-diag-sb-btn, #sidebar .eh-mem-sb-btn');
    if (card) {
      const r = card.getBoundingClientRect();
      card.style.setProperty('--mx', Math.round(e.clientX - r.left) + 'px');
      card.style.setProperty('--my', Math.round(e.clientY - r.top) + 'px');
    }
    const tilt = e.target.closest?.('.stat-card, .eh-quick-card, .bi-kpi, .eh-kpi');
    if (tilt) {
      const r = tilt.getBoundingClientRect();
      const px = (e.clientX - r.left) / Math.max(1, r.width);
      const py = (e.clientY - r.top) / Math.max(1, r.height);
      tilt.style.transform = 'perspective(900px) rotateX(' + ((0.5 - py) * 2.6).toFixed(2) + 'deg) rotateY(' + ((px - 0.5) * 2.6).toFixed(2) + 'deg) translateY(-3px)';
    }
  }, { passive: true });

  document.addEventListener('pointerout', (e) => {
    const tilt = e.target.closest?.('.stat-card, .eh-quick-card, .bi-kpi, .eh-kpi');
    if (tilt && (!e.relatedTarget || !tilt.contains(e.relatedTarget))) tilt.style.transform = '';
  }, { passive: true });

  document.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    const target = e.target.closest?.('.primary-btn, .ghost-btn, .eh-quick-card, .bi-lens-tab, .nav-btn, .eh-diag-sb-btn, .eh-mem-sb-btn, .pro-icon-btn, .pro-cat-btn, .eh-mini-btn, .prompt-chip, .cite-chip, .eh-cselect-btn, .eh-theme-card, .eh-palette-card, .eh-topbar-board-btn');
    if (!target) return;
    const r = target.getBoundingClientRect();
    const x = e.clientX - r.left;
    const y = e.clientY - r.top;
    const maxDist = Math.hypot(Math.max(x, r.width - x), Math.max(y, r.height - y));
    const diameter = Math.ceil(maxDist * 2.2);

    const wave = document.createElement('span');
    wave.className = 'eh-click-wave';
    wave.style.width = diameter + 'px';
    wave.style.height = diameter + 'px';
    wave.style.left = x + 'px';
    wave.style.top = y + 'px';
    target.appendChild(wave);

    if (wave.animate) {
      wave.animate([
        { transform: 'translate(-50%, -50%) scale(0)', opacity: 0.85 },
        { transform: 'translate(-50%, -50%) scale(1)', opacity: 0 }
      ], { duration: 480, easing: 'cubic-bezier(0.16, 1, 0.3, 1)', fill: 'forwards' }).onfinish = () => wave.remove();
    } else {
      setTimeout(() => wave.remove(), 500);
    }
  }, true);

  function polishChatAndPageCopy() { return;
    const chatHdr = document.querySelector('#page-chat .page-header');
    if (chatHdr) {
      const h2 = chatHdr.querySelector('h2');
      const p = chatHdr.querySelector('p');
      if (h2) h2.textContent = '\u062f\u0633\u062a\u06cc\u0627\u0631 \u0647\u0648\u0634\u0645\u0646\u062f';
      if (p) p.textContent = '\u067e\u0631\u0633\u0634\u200c\u0648\u067e\u0627\u0633\u062e \u0627\u0632 \u0631\u0648\u06cc \u0627\u0633\u0646\u0627\u062f \u0648 \u0622\u0645\u0627\u0631\u0647\u0627\u06cc \u0645\u0624\u0633\u0633\u0647 \u0648 \u062a\u0647\u06cc\u0647 \u06af\u0632\u0627\u0631\u0634';
    }
    document.querySelectorAll('.prompt-chip').forEach(ch => {
      ch.textContent = ch.textContent.replace(/\s*\(SQL\s*\+\s*\u0627\u06a9\u0633\u0644\)/g, '');
    });

    const box = document.getElementById('chatMessages');
    if (!box || box._ehObserved) return;
    box._ehObserved = true;

    const cleanChatDom = () => {
      box.querySelectorAll('.msg-bubble, .msg-text').forEach(el => {
        if (el.innerHTML.includes('#### ') || el.innerHTML.includes('### ')) {
          el.innerHTML = el.innerHTML.replace(/(^|<br\s*\/?>)\s*#{3,4}\s+([^<\n]+)/g, '$1<div class="eh-chat-h">$2</div>');
        }
        if (el.innerHTML.includes('tbl_')) {
          el.innerHTML = el.innerHTML.replace(/\s*\/\s*\u0646\u0627\u0645 \u062c\u062f\u0648\u0644 \u067e\u0627\u06cc\u06af\u0627\u0647 \u062f\u0627\u062f\u0647:\s*tbl_[a-zA-Z0-9_]+/g, '');
        }
      });
      box.querySelectorAll('.cite-chip, .stat-pill').forEach(chip => {
        if (chip.textContent.includes('DuckDB') || chip.textContent.includes('SQL')) {
          chip.textContent = '\u06af\u0632\u0627\u0631\u0634 \u0622\u0645\u0627\u0631\u06cc';
        }
      });
    };
    cleanChatDom();
    new MutationObserver(cleanChatDom).observe(box, { childList: true, subtree: true });
  }

  let cachedAnalytics = null;
  let cacheTs = 0;

  function setupSmartApiLayer() {
    const api = window.pywebview?.api;
    if (!api || api._v29Wrapped) return;
    api._v29Wrapped = true;

    const origAnalytics = api.get_executive_analytics?.bind(api);
    if (origAnalytics) {
      api.get_executive_analytics = async function (filters = {}) {
        const isDefault = !filters || Object.values(filters).every(v => v === '' || v === null || v === undefined);
        if (isDefault && cachedAnalytics && (Date.now() - cacheTs < 45000)) return cachedAnalytics;
        const res = await origAnalytics(filters);
        if (isDefault && res && res.ok) { cachedAnalytics = res; cacheTs = Date.now(); }
        return res;
      };
    }

    ['scan_documents', 'import_porsline_excel', 'merge_participants', 'save_event_pipeline', 'delete_document'].forEach(fn => {
      if (typeof api[fn] === 'function') {
        const orig = api[fn].bind(api);
        api[fn] = async function () { cachedAnalytics = null; return orig.apply(this, arguments); };
      }
    });
  }

  function handleNetworkStatus() {
    const online = navigator.onLine;
    const badge = document.querySelector('.engine-status .engine-badge');
    if (badge) {
      badge.innerHTML = online
        ? '<span class="engine-dot"></span>\u0622\u0645\u0627\u062f\u0647 \u0628\u0647 \u06a9\u0627\u0631'
        : '<span class="engine-dot" style="background:#f59e0b;"></span>\u062d\u0627\u0644\u062a \u0622\u0641\u0644\u0627\u06cc\u0646';
    }
    if (!online) window.pywebview?.api?.save_branding_settings?.({ voice_engine: 'whisper' }).catch?.(() => {});
  }
  window.addEventListener('online', handleNetworkStatus);
  window.addEventListener('offline', handleNetworkStatus);

  async function openTeacher360Drawer(rawName) {
    if (!rawName) return;
    const data = cachedAnalytics || await window.pywebview?.api?.get_executive_analytics?.({});
    if (!data || !data.ok) return;
    const tObj = (data.teachers || []).find(t => t.name === rawName) || { name: rawName, attendance: 0, unique: 0, courses: 0, avg_attendance: 0, groups: [] };
    const shortName = window.formatTeacherShort ? window.formatTeacherShort(tObj.name) : tObj.name;

    document.getElementById('ehTeacherDrawer360')?.remove();
    const bd = document.createElement('div');
    bd.id = 'ehTeacherDrawer360';
    bd.className = 'eh-drawer-backdrop open';
    bd.innerHTML = `
      <div class="eh-drawer-panel" role="dialog" aria-modal="true">
        <div class="eh-drawer-head">
          <div>
            <strong style="font-size:15px;">${shortName}</strong>
            <div style="font-size:11px; color:var(--s-text-muted); margin-top:2px;">${tObj.name}</div>
          </div>
          <button type="button" class="pro-icon-btn" id="btnCloseT360">${ic('close', 15)}</button>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px;">
          <div class="eh-set-card" style="padding:10px; text-align:center;">
            <span style="font-size:11px; color:var(--s-text-muted);">\u062a\u0639\u062f\u0627\u062f \u062f\u0648\u0631\u0647</span>
            <strong style="font-size:18px; color:var(--lg-accent);">${toFa(tObj.courses)}</strong>
          </div>
          <div class="eh-set-card" style="padding:10px; text-align:center;">
            <span style="font-size:11px; color:var(--s-text-muted);">\u0645\u062c\u0645\u0648\u0639 \u062d\u0636\u0648\u0631</span>
            <strong style="font-size:18px; color:var(--lg-accent);">${toFa(tObj.attendance)}</strong>
          </div>
          <div class="eh-set-card" style="padding:10px; text-align:center;">
            <span style="font-size:11px; color:var(--s-text-muted);">\u0645\u062e\u0627\u0637\u0628 \u06cc\u06a9\u062a\u0627</span>
            <strong style="font-size:18px; color:var(--lg-accent);">${toFa(tObj.unique)}</strong>
          </div>
        </div>
        <div class="eh-set-card">
          <div class="eh-set-card-title">\u06a9\u0627\u0631\u06af\u0631\u0648\u0647\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644 \u0648 \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u062c\u0630\u0628</div>
          <div style="font-size:12px; color:var(--s-text-muted);">\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0634\u0631\u06a9\u062a\u200c\u06a9\u0646\u0646\u062f\u0647 \u062f\u0631 \u0647\u0631 \u062f\u0648\u0631\u0647: <strong>${toFa(tObj.avg_attendance)} \u0646\u0641\u0631</strong></div>
          <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:4px;">
            ${(tObj.groups || []).map(g => `<span class="eh-badge">${g}</span>`).join('') || '<span class="eh-badge">\u062f\u0648\u0631\u0647\u200c\u0647\u0627\u06cc \u0639\u0644\u0645\u06cc</span>'}
          </div>
        </div>
        <div style="display:flex; gap:8px; margin-top:auto;">
          <button type="button" class="primary-btn" id="btnAskAiTeacher" style="flex:1;">\u062a\u062d\u0644\u06cc\u0644 \u0639\u0645\u0644\u06a9\u0631\u062f \u062f\u0631 \u062f\u0633\u062a\u06cc\u0627\u0631 \u0647\u0648\u0634\u0645\u0646\u062f</button>
        </div>
      </div>
    `;
    document.body.appendChild(bd);
    const close = () => bd.remove();
    bd.addEventListener('click', e => { if (e.target === bd) close(); });
    bd.querySelector('#btnCloseT360').addEventListener('click', close);
    bd.querySelector('#btnAskAiTeacher').addEventListener('click', () => {
      close();
      window.switchPageById?.('chat');
      const inp = document.getElementById('chatInput');
      if (inp) {
        inp.value = '\u06af\u0632\u0627\u0631\u0634 \u06a9\u0627\u0645\u0644 \u062f\u0648\u0631\u0647\u200c\u0647\u0627 \u0648 \u0622\u0645\u0627\u0631 \u0645\u062e\u0627\u0637\u0628\u0627\u0646 ' + shortName + ' \u0631\u0627 \u0628\u0646\u0648\u06cc\u0633';
        inp.focus();
      }
    });
  }
  window.openTeacher360Drawer = openTeacher360Drawer;

  const J_MONTHS = ['\u0641\u0631\u0648\u0631\u062f\u06cc\u0646','\u0627\u0631\u062f\u06cc\u0628\u0647\u0634\u062a','\u062e\u0631\u062f\u0627\u062f','\u062a\u06cc\u0631','\u0645\u0631\u062f\u0627\u062f','\u0634\u0647\u0631\u06cc\u0648\u0631','\u0645\u0647\u0631','\u0622\u0628\u0627\u0646','\u0622\u0630\u0631','\u062f\u06cc','\u0628\u0647\u0645\u0646','\u0627\u0633\u0641\u0646\u062f'];
  function attachJalaliPickers() {
    document.querySelectorAll('input[placeholder*="140"], input[placeholder*="\u06f1\u06f4\u06f0"], input[id*="Date"]').forEach(inp => {
      if (inp.dataset.ehJalali === '1') return;
      inp.dataset.ehJalali = '1';
      inp.addEventListener('focus', () => {
        document.querySelector('.eh-jalali-pop')?.remove();
        let yr = 1405, mo = 8;
        const pop = document.createElement('div');
        pop.className = 'eh-jalali-pop';
        const r = inp.getBoundingClientRect();
        pop.style.top = Math.min(window.innerHeight - 250, r.bottom + 6) + 'px';
        pop.style.left = Math.max(12, Math.min(window.innerWidth - 270, r.left)) + 'px';

        const renderCal = () => {
          const maxD = mo <= 6 ? 31 : (mo <= 11 ? 30 : 29);
          const days = Array.from({ length: maxD }, (_, i) =>
            `<button type="button" class="eh-jalali-day" data-d="${i + 1}">${toFa(i + 1)}</button>`
          ).join('');
          pop.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <button type="button" class="eh-mini-btn" id="jpPrev">\u203a</button>
              <strong style="font-size:12px;">${J_MONTHS[mo - 1]} ${toFa(yr)}</strong>
              <button type="button" class="eh-mini-btn" id="jpNext">\u2039</button>
            </div>
            <div class="eh-jalali-grid">${days}</div>
          `;
          pop.querySelector('#jpPrev').onclick = (ev) => { ev.stopPropagation(); mo--; if (mo < 1) { mo = 12; yr--; } renderCal(); };
          pop.querySelector('#jpNext').onclick = (ev) => { ev.stopPropagation(); mo++; if (mo > 12) { mo = 1; yr++; } renderCal(); };
          pop.querySelectorAll('[data-d]').forEach(b => {
            b.onclick = () => {
              const dd = String(b.dataset.d).padStart(2, '0');
              const mm = String(mo).padStart(2, '0');
              inp.value = `${yr}/${mm}/${dd}`;
              inp.dispatchEvent(new Event('change', { bubbles: true }));
              pop.remove();
            };
          });
        };
        renderCal();
        document.body.appendChild(pop);
        setTimeout(() => {
          const off = (ev) => {
            if (!pop.contains(ev.target) && ev.target !== inp) {
              pop.remove();
              document.removeEventListener('pointerdown', off);
            }
          };
          document.addEventListener('pointerdown', off);
        }, 50);
      });
    });
  }

  const FULL_PAGE_MODALS = new Set(['exec_analytics', 'event_pipeline', 'letter_registry']);

  function triggerBoardroomNow() {
    if (typeof window.openBoardroomMode === 'function') {
      window.openBoardroomMode();
      return;
    }
    openEmbeddedFullPage('exec_analytics');
    setTimeout(() => {
      if (typeof window.openBoardroomMode === 'function') window.openBoardroomMode();
      else document.getElementById('btnOpenBoardroom')?.click();
    }, 320);
  }

  function enhanceChartCopyButtons(rootEl) {
    rootEl.querySelectorAll('.eh-chart-box').forEach(box => {
      const head = box.querySelector('.eh-chart-head');
      const body = box.querySelector('[id^="ch"]');
      if (!head || !body || head.querySelector('.eh-copy-chart-btn')) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'eh-mini-btn eh-copy-chart-btn';
      btn.textContent = '\u06a9\u067e\u06cc \u062a\u0635\u0648\u06cc\u0631';
      btn.addEventListener('click', () => window.eHadiCharts?.copyChartToClipboard(body));
      head.appendChild(btn);
    });
  }

  async function injectEitaaTemplates(bd) {
    const content = bd.querySelector('.pro-modal-content');
    if (!content || bd.querySelector('#ehEitaaTplBar')) return;
    const bar = document.createElement('div');
    bar.id = 'ehEitaaTplBar';
    bar.className = 'eh-set-card';
    bar.style.marginBottom = '12px';
    bar.innerHTML = `
      <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap;">
        <strong style="font-size:12px;">\u0627\u0644\u06af\u0648\u0647\u0627\u06cc \u0630\u062e\u06cc\u0631\u0647\u200c\u0634\u062f\u0647:</strong>
        <div style="display:flex; gap:6px; align-items:center;">
          <select id="selEitaaTpl" class="glass-select" style="min-width:170px; height:32px; font-size:11.5px;"></select>
          <button type="button" class="ghost-btn bi-mini-btn" id="btnSaveEitaaTpl">\u0630\u062e\u06cc\u0631\u0647 \u0645\u062a\u0646 \u0628\u0647\u200c\u0639\u0646\u0648\u0627\u0646 \u0627\u0644\u06af\u0648</button>
        </div>
      </div>
    `;
    content.insertBefore(bar, content.firstChild);

    let arr = [];
    try {
      const br = await window.pywebview?.api?.get_branding_settings?.();
      if (Array.isArray(br?.branding?.eitaa_templates)) arr = br.branding.eitaa_templates;
      else arr = JSON.parse(localStorage.getItem(EITA_TPL_KEY) || '[]');
    } catch (_) {}

    const renderList = () => {
      const sel = bar.querySelector('#selEitaaTpl');
      sel.innerHTML = '<option value="">\u0627\u0646\u062a\u062e\u0627\u0628 \u0627\u0644\u06af\u0648</option>' +
        arr.map((t, i) => `<option value="${i}">${t.title}</option>`).join('');
      sel.onchange = () => {
        if (sel.value === '') return;
        const item = arr[Number(sel.value)];
        const out = bd.querySelector('#msPreview') || bd.querySelector('.eitaa-preview-text') || bd.querySelector('textarea');
        if (item && out) { out.value = item.text; window.showToast?.('\u0627\u0644\u06af\u0648 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc \u0634\u062f'); }
      };
    };
    renderList();

    bar.querySelector('#btnSaveEitaaTpl').addEventListener('click', async () => {
      const out = bd.querySelector('#msPreview') || bd.querySelector('.eitaa-preview-text') || bd.querySelector('textarea');
      const txt = out?.value?.trim();
      if (!txt) { window.showToast?.('\u0627\u0628\u062a\u062f\u0627 \u0645\u062a\u0646 \u0631\u0627 \u062a\u0648\u0644\u06cc\u062f \u06cc\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f'); return; }
      arr.unshift({ title: '\u0627\u0644\u06af\u0648\u06cc \u0634\u0645\u0627\u0631\u0647 ' + toFa(arr.length + 1), text: txt });
      arr = arr.slice(0, 20);
      try { localStorage.setItem(EITA_TPL_KEY, JSON.stringify(arr)); } catch (_) {}
      await window.pywebview?.api?.save_branding_settings?.({ eitaa_templates: arr }).catch?.(() => {});
      renderList();
      window.showToast?.('\u0627\u0644\u06af\u0648 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f');
    });
  }

  function injectUndoInDataHealth(bd) {
    const content = bd.querySelector('.pro-modal-content');
    if (!content || bd.querySelector('#ehHealthUndoBar')) return;
    const bar = document.createElement('div');
    bar.id = 'ehHealthUndoBar';
    bar.className = 'eh-set-card';
    bar.style.marginBottom = '12px';
    bar.innerHTML = `
      <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap;">
        <span style="font-size:11.8px; color:var(--s-text-muted);">\u067e\u06cc\u0634 \u0627\u0632 \u0627\u062f\u063a\u0627\u0645 \u0627\u0633\u0627\u0645\u06cc\u060c \u0646\u0633\u062e\u0647 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646 \u0622\u0646\u06cc \u062b\u0628\u062a \u0645\u06cc\u200c\u0634\u0648\u062f</span>
        <button type="button" class="ghost-btn bi-mini-btn" id="btnSnapBeforeMerge">\u0627\u06cc\u062c\u0627\u062f \u0646\u0642\u0637\u0647 \u0628\u0627\u0632\u06af\u0634\u062a \u0622\u0646\u06cc</button>
      </div>
    `;
    content.insertBefore(bar, content.firstChild);
    bar.querySelector('#btnSnapBeforeMerge').addEventListener('click', async () => {
      const r = await window.pywebview?.api?.create_backup_now?.();
      if (r && r.ok) window.showToast?.('\u0646\u0642\u0637\u0647 \u0628\u0627\u0632\u06af\u0634\u062a \u062f\u0631 \u067e\u0648\u0634\u0647 backups \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f');
    });
  }

  function openEmbeddedFullPage(modalId, opts = {}) {
    const App = window.eHadiApp;
    const content = document.querySelector('main.content');
    if (!App || !content || !App._rawOpenModal) return;

    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

    App._rawOpenModal(modalId, opts);
    const bd = document.getElementById('proModal_' + modalId);
    if (!bd) return;

    if (bd.parentElement !== content) content.appendChild(bd);
    bd.classList.remove('pro-overlay-root', 'open');
    bd.classList.add('page', 'eh-embedded-page', 'active');

    const navBtn = document.getElementById('navAction_' + modalId);
    if (navBtn) {
      navBtn.classList.add('active');
      syncNavIndicator(navBtn);
    }
    updateBreadcrumb(modalId);
    content.scrollTop = 0;

    setTimeout(() => {
      attachJalaliPickers();
      if (modalId === 'exec_analytics') enhanceChartCopyButtons(bd);
    }, 180);
  }

  function hookRouting() {
    const App = window.eHadiApp;
    if (App && !App._v29RoutingHooked) {
      App._v29RoutingHooked = true;
      App._rawOpenModal = App.openModal.bind(App);
      App.openModal = function (id, opts) {
        if (id === 'boardroom') { triggerBoardroomNow(); return; }
        if (FULL_PAGE_MODALS.has(id)) { openEmbeddedFullPage(id, opts); return; }
        const res = App._rawOpenModal(id, opts);
        const bd = document.getElementById('proModal_' + id);
        if (bd) {
          setTimeout(() => {
            attachJalaliPickers();
            if (id === 'media_studio') injectEitaaTemplates(bd);
            if (id === 'data_health') injectUndoInDataHealth(bd);
          }, 120);
        }
        return res;
      };

      const origTheme = App.applyTheme?.bind(App);
      if (origTheme) {
        App.applyTheme = function (th) {
          origTheme(th);
          refreshAllChartsTheme();
        };
      }
    }

    if (typeof window.switchPage === 'function' && !window.switchPage._v29Hooked) {
      const origSwitch = window.switchPage;
      const wrapped = function (pageId, btn) {
        if (String(pageId).toLowerCase() === 'settings') {
          window.eHadiApp?.openModal('preferences');
          return;
        }
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        const res = origSwitch.apply(this, arguments);
        const targetBtn = btn || document.querySelector(`#sidebar .nav-btn[onclick*="'${pageId}'"]`);
        syncNavIndicator(targetBtn);
        updateBreadcrumb(pageId);
        return res;
      };
      wrapped._v29Hooked = true;
      window.switchPage = wrapped;
    }

    if (typeof window.moveIndicator === 'function' && !window.moveIndicator._v29Hooked) {
      const wrappedMove = function (btn) { syncNavIndicator(btn); };
      wrappedMove._v29Hooked = true;
      window.moveIndicator = wrappedMove;
    }
  }

  function mountTopbarActions() {
    const leftBar = document.querySelector('#proTopbar .pro-topbar-left');
    const themeBtn = document.getElementById('btnQuickTheme');
    if (!leftBar || !themeBtn) return;

    if (!document.getElementById('btnTopBoardroom')) {
      const brBtn = document.createElement('button');
      brBtn.id = 'btnTopBoardroom';
      brBtn.type = 'button';
      brBtn.className = 'eh-topbar-board-btn';
      brBtn.innerHTML = ic('presentation', 15) + '<span>\u0627\u0631\u0627\u0626\u0647 \u062c\u0644\u0633\u0647</span>';
      brBtn.title = '\u0646\u0645\u0627\u06cc\u0634 \u062a\u0645\u0627\u0645\u200c\u0635\u0641\u062d\u0647 \u0627\u0633\u0644\u0627\u06cc\u062f\u0647\u0627\u06cc \u062c\u0644\u0633\u0647';
      brBtn.addEventListener('click', triggerBoardroomNow);
      leftBar.insertBefore(brBtn, themeBtn);
    }

    if (!document.getElementById('btnQuickPalette')) {
      const btn = document.createElement('button');
      btn.id = 'btnQuickPalette';
      btn.type = 'button';
      btn.className = 'pro-icon-btn';
      btn.innerHTML = ic('palette', 16);
      btn.addEventListener('click', togglePalette);
      leftBar.insertBefore(btn, themeBtn);
      applyPalette(document.body.getAttribute('data-accent-scheme') || 'navy', false);
    }
  }

  function upgradeSettingsModal() {
    const App = window.eHadiApp;
    if (!App || App._v29SettingsReady) return;
    App._v29SettingsReady = true;
    document.getElementById('proModal_preferences')?.remove();

    App.registerModal('preferences', {
      render() {
        return `
          <div class="pro-modal-box eh-xl-modal" role="dialog" aria-modal="true">
            <div class="pro-modal-header">
              <div class="pro-modal-title">${ic('settings', 17)}<span>\u062a\u0646\u0638\u06cc\u0645\u0627\u062a \u0633\u0627\u0645\u0627\u0646\u0647</span></div>
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="pro-kbd">ESC</span>
                <button type="button" class="pro-icon-btn" data-close-modal title="\u0628\u0633\u062a\u0646">${ic('close', 15)}</button>
              </div>
            </div>
            <div class="pro-modal-body">
              <div class="pro-modal-nav" id="v29SettingsNav">
                <button type="button" class="pro-cat-btn active" data-pane="appearance">${ic('palette', 16)}<span>\u0638\u0627\u0647\u0631 \u0648 \u0631\u0646\u06af\u200c\u0628\u0646\u062f\u06cc</span></button>
                <button type="button" class="pro-cat-btn" data-pane="ai">${ic('cpu', 16)}<span>\u0647\u0648\u0634 \u0645\u0635\u0646\u0648\u0639\u06cc \u0648 \u06a9\u0644\u06cc\u062f</span></button>
                <button type="button" class="pro-cat-btn" data-pane="voice">${ic('mic', 16)}<span>\u062f\u0633\u062a\u06cc\u0627\u0631 \u0635\u0648\u062a\u06cc</span></button>
                <button type="button" class="pro-cat-btn" data-pane="reports">${ic('fileText', 16)}<span>\u0633\u0631\u0628\u0631\u06af \u0648 \u0641\u0648\u0646\u062a</span></button>
                <button type="button" class="pro-cat-btn" data-pane="backup">${ic('shieldCheck', 16)}<span>\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u200c\u06af\u06cc\u0631\u06cc \u0648 \u0648\u0642\u0627\u06cc\u0639</span></button>
                <button type="button" class="pro-cat-btn" data-pane="shortcuts">${ic('keyboard', 16)}<span>\u0645\u06cc\u0627\u0646\u0628\u0631\u0647\u0627</span></button>
              </div>
              <div class="pro-modal-content">
                <div class="pro-pane active" id="prefs-pane-appearance">
                  <div class="pro-pane-title">\u0634\u062e\u0635\u06cc\u200c\u0633\u0627\u0632\u06cc \u0631\u0646\u06af\u200c\u0628\u0646\u062f\u06cc\u060c \u0631\u0648\u0634\u0646\u0627\u06cc\u06cc \u0648 \u062a\u0631\u0627\u06a9\u0645 \u0645\u062d\u06cc\u0637</div>
                  <div class="eh-set-grid2">
                    <div class="eh-set-card">
                      <div class="eh-set-card-title">\u0627\u0646\u062a\u062e\u0627\u0628 \u067e\u0627\u0644\u062a \u0631\u0646\u06af\u06cc</div>
                      <button type="button" class="eh-palette-card" data-set-palette="navy">
                        <div>
                          <div style="font-weight:800; font-size:12.5px;">\u0633\u0631\u0645\u0647\u200c\u0627\u06cc</div>
                          <div style="font-size:11px; color:var(--s-text-muted); margin-top:2px;">\u062a\u0631\u06a9\u06cc\u0628 \u0633\u0631\u0645\u0647\u200c\u0627\u06cc \u0648 \u0622\u0628\u06cc \u0631\u0648\u0634\u0646</div>
                        </div>
                        <span class="eh-swatches"><span class="eh-swatch" style="background:#0f172a;"></span><span class="eh-swatch" style="background:#38bdf8;"></span><span class="eh-swatch" style="background:#818cf8;"></span></span>
                      </button>
                      <button type="button" class="eh-palette-card" data-set-palette="emerald">
                        <div>
                          <div style="font-weight:800; font-size:12.5px;">\u0633\u0628\u0632 \u0632\u0645\u0631\u062f\u06cc</div>
                          <div style="font-size:11px; color:var(--s-text-muted); margin-top:2px;">\u062a\u0631\u06a9\u06cc\u0628 \u0633\u0628\u0632 \u0632\u0645\u0631\u062f\u06cc \u0648 \u0641\u06cc\u0631\u0648\u0632\u0647\u200c\u0627\u06cc</div>
                        </div>
                        <span class="eh-swatches"><span class="eh-swatch" style="background:#064e3b;"></span><span class="eh-swatch" style="background:#10b981;"></span><span class="eh-swatch" style="background:#2dd4bf;"></span></span>
                      </button>
                    </div>
                    <div class="eh-set-card">
                      <div class="eh-set-card-title">\u062d\u0627\u0644\u062a \u0631\u0648\u0634\u0646\u0627\u06cc\u06cc \u0648 \u062a\u0631\u0627\u06a9\u0645</div>
                      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                        <button type="button" class="eh-theme-card" data-set-theme="dark"><span>${ic('moon', 16)} <strong>\u062a\u0645 \u062a\u06cc\u0631\u0647</strong></span></button>
                        <button type="button" class="eh-theme-card" data-set-theme="light"><span>${ic('sun', 16)} <strong>\u062a\u0645 \u0631\u0648\u0634\u0646</strong></span></button>
                      </div>
                      <div class="eh-set-card-desc" style="margin-top:4px;">\u062a\u0631\u0627\u06a9\u0645 \u0641\u0627\u0635\u0644\u0647\u200c\u06af\u0630\u0627\u0631\u06cc \u06a9\u0627\u0631\u062a\u200c\u0647\u0627:</div>
                      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                        <button type="button" class="eh-theme-card" data-set-density="comfortable"><strong>\u062d\u0627\u0644\u062a \u0631\u0627\u062d\u062a</strong></button>
                        <button type="button" class="eh-theme-card" data-set-density="compact"><strong>\u062d\u0627\u0644\u062a \u0641\u0634\u0631\u062f\u0647</strong></button>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="pro-pane" id="prefs-pane-ai">
                  <div class="pro-pane-title">\u062a\u0646\u0638\u06cc\u0645\u0627\u062a \u0627\u062a\u0635\u0627\u0644 \u0648 \u06a9\u0644\u06cc\u062f \u062f\u0633\u062a\u06cc\u0627\u0631 \u0647\u0648\u0634\u0645\u0646\u062f</div>
                  <div id="prefsSlotAI"></div>
                </div>
                <div class="pro-pane" id="prefs-pane-voice">
                  <div class="pro-pane-title">\u062a\u0646\u0638\u06cc\u0645\u0627\u062a \u062f\u0633\u062a\u06cc\u0627\u0631 \u0635\u0648\u062a\u06cc \u0648 \u062a\u0628\u062f\u06cc\u0644 \u06af\u0641\u062a\u0627\u0631 \u0628\u0647 \u0645\u062a\u0646</div>
                  <div class="eh-set-grid2">
                    <div class="eh-set-card">
                      <div class="eh-set-card-title">\u0645\u0648\u062a\u0648\u0631 \u062a\u0634\u062e\u06cc\u0635 \u06af\u0641\u062a\u0627\u0631 \u0641\u0627\u0631\u0633\u06cc</div>
                      <select id="selSetVoiceEngine" class="glass-select">
                        <option value="gemini">\u062c\u0645\u06cc\u0646\u0627\u06cc \u0622\u0646\u0644\u0627\u06cc\u0646 (\u067e\u06cc\u0634\u0646\u0647\u0627\u062f\u06cc)</option>
                        <option value="whisper">\u0648\u06cc\u0633\u067e\u0631 \u0622\u0641\u0644\u0627\u06cc\u0646 (\u0628\u062f\u0648\u0646 \u0646\u06cc\u0627\u0632 \u0628\u0647 \u0627\u06cc\u0646\u062a\u0631\u0646\u062a)</option>
                      </select>
                      <select id="selSetWhisperModel" class="glass-select">
                        <option value="small">Small (\u0645\u062a\u0639\u0627\u062f\u0644 \u0648 \u0633\u0631\u06cc\u0639)</option>
                        <option value="base">Base (\u0633\u0628\u06a9)</option>
                        <option value="medium">Medium (\u062f\u0642\u062a \u0628\u0627\u0644\u0627)</option>
                      </select>
                    </div>
                    <div class="eh-set-card">
                      <div class="eh-set-card-title">\u067e\u0627\u0633\u062e \u0635\u0648\u062a\u06cc \u0648 \u0645\u06cc\u0627\u0646\u0628\u0631</div>
                      <label style="display:flex; align-items:center; gap:8px; cursor:pointer; font-size:12.5px; font-weight:700; color:var(--s-text);">
                        <input type="checkbox" id="chkSetVoiceTts" checked /> \u067e\u062e\u0634 \u067e\u0627\u0633\u062e \u0635\u0648\u062a\u06cc \u0641\u0627\u0631\u0633\u06cc
                      </label>
                      <div class="eh-set-card-desc">\u0645\u06cc\u0627\u0646\u0628\u0631 \u0645\u06cc\u06a9\u0631\u0648\u0641\u0648\u0646: <span class="pro-kbd">Alt + Space</span></div>
                      <button type="button" class="primary-btn" id="btnSaveVoiceSet">\u0630\u062e\u06cc\u0631\u0647 \u062a\u0646\u0638\u06cc\u0645\u0627\u062a \u0635\u0648\u062a\u06cc</button>
                    </div>
                  </div>
                </div>
                <div class="pro-pane" id="prefs-pane-reports">
                  <div class="pro-pane-title">\u0633\u0631\u0628\u0631\u06af \u0631\u0633\u0645\u06cc \u0646\u0627\u0645\u0647\u200c\u0647\u0627\u060c \u0644\u0648\u06af\u0648 \u0648 \u0641\u0648\u0646\u062a</div>
                  <div id="prefsSlotReports"></div>
                </div>
                <div class="pro-pane" id="prefs-pane-backup">
                  <div class="pro-pane-title">\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u200c\u06af\u06cc\u0631\u06cc \u0648 \u06af\u0632\u0627\u0631\u0634 \u0648\u0642\u0627\u06cc\u0639</div>
                  <div class="eh-set-grid2">
                    <div class="eh-set-card">
                      <div class="eh-set-card-title">\u0646\u0633\u062e\u0647 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646 \u0641\u0648\u0631\u06cc</div>
                      <div style="display:flex; gap:8px; flex-wrap:wrap;">
                        <button type="button" class="primary-btn pro-btn-ic" id="btnSetBackupNow">${ic('shieldCheck', 15)}<span>\u0627\u06cc\u062c\u0627\u062f \u0628\u06a9\u0627\u067e \u0647\u0645\u06cc\u0646 \u0627\u0644\u0627\u0646</span></button>
                        <button type="button" class="ghost-btn pro-btn-ic" id="btnSetOpenDocs">${ic('folder', 15)}<span>\u067e\u0648\u0634\u0647 \u0627\u0633\u0646\u0627\u062f</span></button>
                      </div>
                    </div>
                    <div class="eh-set-card">
                      <div class="eh-set-card-title">\u0628\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u062f\u0627\u062f\u0647\u200c\u0647\u0627</div>
                      <div style="display:flex; gap:8px; flex-wrap:wrap;">
                        <button type="button" class="ghost-btn pro-btn-ic" id="btnSetRescan">${ic('refresh', 15)}<span>\u0627\u0633\u06a9\u0646 \u0645\u062c\u062f\u062f \u0641\u0627\u06cc\u0644\u200c\u0647\u0627</span></button>
                        <button type="button" class="ghost-btn pro-btn-ic" id="btnSetHealth">${ic('users', 15)}<span>\u067e\u0627\u06a9\u200c\u0633\u0627\u0632\u06cc \u062f\u0627\u062f\u0647\u200c\u0647\u0627</span></button>
                      </div>
                    </div>
                  </div>
                  <div class="eh-set-card" style="margin-top:12px;">
                    <div class="eh-set-card-head">
                      <div>
                        <span class="eh-set-card-title">تاریخچه فعالیت‌های سامانه</span>
                        <div class="eh-set-card-desc" style="margin-top:2px;">گزارش خودکار ثبت تصمیم‌ها، پشتیبان‌گیری، اسکن اسناد و تغییرات مدیریتی</div>
                      </div>
                      <div style="display:flex; gap:6px; align-items:center;">
                        <button type="button" class="eh-mini-btn" id="btnClearAudit" title="پاکسازی تاریخچه فعالیت‌های قبلی">پاکسازی</button>
                        <button type="button" class="eh-mini-btn" id="btnRefreshAudit" title="بارگذاری مجدد فهرست">بروزرسانی</button>
                      </div>
                    </div>
                    <div id="setAuditList" style="max-height:190px; overflow-y:auto; display:flex; flex-direction:column; gap:6px; font-size:11.5px;"></div>
                  </div>
                </div>
                <div class="pro-pane" id="prefs-pane-shortcuts">
                  <div class="pro-pane-title">\u06a9\u0644\u06cc\u062f\u0647\u0627\u06cc \u0645\u06cc\u0627\u0646\u0628\u0631 \u0633\u0631\u06cc\u0639</div>
                  <div class="eh-shortcut-grid">
                    <div class="eh-shortcut-row"><span>\u062c\u0633\u062a\u200c\u0648\u062c\u0648\u06cc \u0633\u0631\u06cc\u0639 \u062f\u0631 \u0628\u0631\u0646\u0627\u0645\u0647 \u0648 \u062f\u0627\u062f\u0647\u200c\u0647\u0627</span><span class="pro-kbd">Ctrl + K</span></div>
                    <div class="eh-shortcut-row"><span>\u0628\u0627\u0632 \u06a9\u0631\u062f\u0646 \u062a\u0646\u0638\u06cc\u0645\u0627\u062a</span><span class="pro-kbd">Ctrl + ,</span></div>
                    <div class="eh-shortcut-row"><span>\u0641\u0639\u0627\u0644\u200c\u0633\u0627\u0632\u06cc \u062f\u0633\u062a\u06cc\u0627\u0631 \u0635\u0648\u062a\u06cc</span><span class="pro-kbd">Alt + Space</span></div>
                    <div class="eh-shortcut-row"><span>\u062c\u0645\u0639 \u06cc\u0627 \u0628\u0627\u0632 \u06a9\u0631\u062f\u0646 \u0645\u0646\u0648\u06cc \u06a9\u0646\u0627\u0631\u06cc</span><span class="pro-kbd">Ctrl + B</span></div>
                    <div class="eh-shortcut-row"><span>\u062a\u063a\u06cc\u06cc\u0631 \u062a\u0645 \u0631\u0648\u0634\u0646 \u0648 \u062a\u06cc\u0631\u0647</span><span class="pro-kbd">Ctrl + Shift + T</span></div>
                    <div class="eh-shortcut-row"><span>\u062a\u0645\u0627\u0645\u200c\u0635\u0641\u062d\u0647 \u06a9\u0631\u062f\u0646 \u067e\u0646\u062c\u0631\u0647</span><span class="pro-kbd">F11</span></div>
                  </div>
                </div>
              </div>
            </div>
            <div class="pro-modal-footer">
              <span style="font-size:11px; color:var(--s-text-dim);">eHadiPanel Beta 0.2 — ${INST_HTML}</span>
              <button type="button" class="primary-btn" data-close-modal style="padding:7px 22px;">\u062a\u0623\u06cc\u06cc\u062f \u0648 \u0628\u0633\u062a\u0646</button>
            </div>
          </div>
        `;
      },
      onMount(bd) {
        bd.querySelectorAll('#v29SettingsNav .pro-cat-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            bd.querySelectorAll('#v29SettingsNav .pro-cat-btn').forEach(b => b.classList.remove('active'));
            bd.querySelectorAll('.pro-pane').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            bd.querySelector('#prefs-pane-' + btn.dataset.pane)?.classList.add('active');
            if (btn.dataset.pane === 'backup') loadAuditLogs(bd);
          });
        });
        bd.querySelectorAll('[data-set-palette]').forEach(btn => {
          btn.addEventListener('click', () => {
            applyPalette(btn.dataset.setPalette, true);
            window.showToast?.('\u0631\u0646\u06af\u200c\u0628\u0646\u062f\u06cc \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f');
          });
        });
        bd.querySelectorAll('[data-set-theme]').forEach(btn => {
          btn.addEventListener('click', () => { App.applyTheme(btn.dataset.setTheme); syncThemeCards(bd); });
        });
        bd.querySelectorAll('[data-set-density]').forEach(btn => {
          btn.addEventListener('click', () => { applyDensity(btn.dataset.setDensity, true); window.showToast?.('\u062a\u0631\u0627\u06a9\u0645 \u0645\u062d\u06cc\u0637 \u0628\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u0634\u062f'); });
        });
        bd.querySelector('#btnSaveVoiceSet')?.addEventListener('click', async () => {
          await window.pywebview?.api?.save_branding_settings?.({
            voice_engine: bd.querySelector('#selSetVoiceEngine').value,
            whisper_model: bd.querySelector('#selSetWhisperModel').value,
            voice_tts: bd.querySelector('#chkSetVoiceTts').checked,
          });
          window.showToast?.('\u062a\u0646\u0638\u06cc\u0645\u0627\u062a \u0635\u0648\u062a\u06cc \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f');
        });
        bd.querySelector('#btnSetBackupNow')?.addEventListener('click', async () => {
          const r = await window.pywebview?.api?.create_backup_now?.();
          if (r && r.ok) { window.showToast?.('\u0646\u0633\u062e\u0647 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646 \u0627\u06cc\u062c\u0627\u062f \u0634\u062f'); loadAuditLogs(bd); }
        });
        bd.querySelector('#btnSetOpenDocs')?.addEventListener('click', () => window.pywebview?.api?.open_raw_docs_folder?.());
        bd.querySelector('#btnSetRescan')?.addEventListener('click', () => { App.closeAllModals(); window.scanDocs?.(); });
        bd.querySelector('#btnSetHealth')?.addEventListener('click', () => App.openModal('data_health'));
        bd.querySelector('#btnRefreshAudit')?.addEventListener('click', () => loadAuditLogs(bd));
        bd.querySelector('#btnClearAudit')?.addEventListener('click', async () => {
          const r = await window.pywebview?.api?.clear_audit_logs?.();
          if (r && r.ok) {
            window.showToast?.('تاریخچه فعالیت‌های سامانه پاکسازی شد');
            loadAuditLogs(bd);
          }
        });
      },
      async onOpen(bd, opts) {
        const sp = document.getElementById('page-settings');
        const sAI = bd.querySelector('#prefsSlotAI');
        const sRep = bd.querySelector('#prefsSlotReports');
        const sBackup = bd.querySelector('#prefs-pane-backup');
        if (sp && sAI && sRep) {
          const bc = document.getElementById('brandingCard');
          if (bc && bc.parentElement !== sRep) { bc.style.marginTop = '0'; sRep.appendChild(bc); }
          const diagCard = document.getElementById('ehDiagSettingsCard');
          if (diagCard && sBackup && diagCard.parentElement !== sBackup) {
            diagCard.style.marginTop = '12px';
            sBackup.appendChild(diagCard);
          }
          Array.from(sp.children).forEach(ch => {
            if (ch.id === 'brandingCard' || ch.id === 'ehDiagSettingsCard') return;
            if (ch.classList.contains('page-header')) { ch.remove(); return; }
            sAI.appendChild(ch);
          });
        }
        // Also clean any previously moved redundant header or misplaced diag card
        sAI?.querySelectorAll('.page-header').forEach(h => h.remove());
        const existingDiagInAI = sAI?.querySelector('#ehDiagSettingsCard');
        if (existingDiagInAI && sBackup) {
          existingDiagInAI.style.marginTop = '12px';
          sBackup.appendChild(existingDiagInAI);
        }
        sAI?.querySelectorAll('h3, .card-title').forEach(el => {
          if (el.textContent.includes('\u062a\u0646\u0638\u06cc\u0645\u0627\u062a \u0633\u06cc\u0633\u062a\u0645')) {
            el.textContent = '\u062a\u0646\u0638\u06cc\u0645\u0627\u062a \u0627\u062a\u0635\u0627\u0644 \u0648 \u06a9\u0644\u06cc\u062f \u0647\u0648\u0634 \u0645\u0635\u0646\u0648\u0639\u06cc';
          }
          el.style.fontSize = '13px';
          el.style.fontWeight = '800';
        });

        const keyInp = document.getElementById('inputApiKey');
        if (keyInp && !document.getElementById('btnToggleApiEye')) {
          const row = document.createElement('div');
          row.style.cssText = 'display:flex; gap:8px; align-items:center;';
          keyInp.style.flex = '1';
          keyInp.parentNode.insertBefore(row, keyInp);
          row.appendChild(keyInp);
          const eyeBtn = document.createElement('button');
          eyeBtn.id = 'btnToggleApiEye';
          eyeBtn.type = 'button';
          eyeBtn.className = 'ghost-btn bi-mini-btn';
          eyeBtn.textContent = '\u0646\u0645\u0627\u06cc\u0634 \u06a9\u0644\u06cc\u062f';
          eyeBtn.addEventListener('click', () => {
            const isPwd = keyInp.type === 'password';
            keyInp.type = isPwd ? 'text' : 'password';
            eyeBtn.textContent = isPwd ? '\u0645\u062e\u0641\u06cc \u06a9\u0631\u062f\u0646' : '\u0646\u0645\u0627\u06cc\u0634 \u06a9\u0644\u06cc\u062f';
          });
          row.appendChild(eyeBtn);
        }
        syncThemeCards(bd);
        applyPalette(document.body.getAttribute('data-accent-scheme') || 'navy', false);
        applyDensity(document.body.getAttribute('data-ui-density') || 'comfortable', false);
        try {
          const br = await window.pywebview?.api?.get_branding_settings?.();
          if (br && br.ok && br.branding) {
            const b = br.branding;
            if (b.voice_engine) bd.querySelector('#selSetVoiceEngine').value = b.voice_engine;
            if (b.whisper_model) bd.querySelector('#selSetWhisperModel').value = b.whisper_model;
            bd.querySelector('#chkSetVoiceTts').checked = b.voice_tts !== false;
            if (b.ui_palette) applyPalette(b.ui_palette, false);
            if (b.ui_density) applyDensity(b.ui_density, false);
          }
        } catch (_) {}
        if (opts && opts.pane) bd.querySelector(`#v29SettingsNav .pro-cat-btn[data-pane="${opts.pane}"]`)?.click();
      }
    });
  }

  function syncThemeCards(bd) {
    const cur = document.body.getAttribute('data-studio-theme') || 'dark';
    bd.querySelectorAll('[data-set-theme]').forEach(el => { el.classList.toggle('active', el.dataset.setTheme === cur); });
  }

  async function loadAuditLogs(bd) {
    const box = bd.querySelector('#setAuditList');
    if (!box) return;
    const esc = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const ACTION_MAP = {
      decision_saved: { title: 'ثبت / بروزرسانی تصمیم مدیریتی', tag: 'دفترچه تصمیم‌ها', kind: 'accent' },
      decision_deleted: { title: 'حذف تصمیم از دفترچه', tag: 'دفترچه تصمیم‌ها', kind: 'warn' },
      backup_snapshot: { title: 'ایجاد نسخه پشتیبان امن', tag: 'پشتیبان‌گیری', kind: 'ok' },
      docs_scanned: { title: 'اسکن و پردازش اسناد', tag: 'مدیریت اسناد', kind: 'ok' },
      settings_saved: { title: 'ذخیره تنظیمات سامانه', tag: 'تنظیمات', kind: 'accent' },
      branding_saved: { title: 'بروزرسانی سربرگ و تنظیمات ظاهری', tag: 'سربرگ و ظاهر', kind: 'accent' },
      event_saved: { title: 'ثبت رویداد اجرایی', tag: 'رویدادها', kind: 'accent' },
      event_deleted: { title: 'حذف رویداد اجرایی', tag: 'رویدادها', kind: 'warn' },
      letter_saved: { title: 'ثبت نامه در دبیرخانه', tag: 'دبیرخانه', kind: 'ok' },
      porsline_imported: { title: 'ورود فایل پرس‌لاین', tag: 'پرس‌لاین', kind: 'ok' },
      data_merged: { title: 'ادغام رکوردهای تکراری', tag: 'پاک‌سازی داده‌ها', kind: 'ok' },
    };
    const MOD_MAP = {
      decisions: 'دفترچه تصمیم‌ها',
      safety: 'پشتیبان‌گیری',
      docs: 'مدیریت اسناد',
      settings: 'تنظیمات',
      events: 'رویدادها',
      letters: 'دبیرخانه',
      porsline: 'پرس‌لاین',
    };
    try {
      const res = await window.pywebview?.api?.get_audit_logs?.();
      const logs = (res && res.logs) || [];
      if (!logs.length) {
        box.innerHTML = '<div style="color:var(--s-text-muted); padding:10px 6px; font-size:11.8px;">هنوز فعالیتی در تاریخچه سامانه ثبت نشده است.</div>';
        return;
      }
      box.innerHTML = logs.slice(0, 25).map(lg => {
        const meta = ACTION_MAP[lg.action] || {
          title: String(lg.action || 'رویداد سامانه').replace(/_/g, ' '),
          tag: MOD_MAP[lg.module] || lg.module || 'سیستم',
          kind: lg.status === 'error' ? 'warn' : 'accent',
        };
        const d = (lg.details && typeof lg.details === 'object') ? lg.details : {};
        let detailStr = '';
        if (lg.action === 'decision_saved') {
          const stLabel = d.done ? 'تکمیل‌شده' : 'در دست پیگیری';
          detailStr = d.title ? `«${d.title}» — ${stLabel}` : `وضعیت: ${stLabel}`;
        } else if (lg.action === 'decision_deleted') {
          detailStr = d.title ? `«${d.title}»` : '';
        } else if (lg.action === 'backup_snapshot') {
          const fcnt = Array.isArray(d.files) ? d.files.length : 0;
          detailStr = fcnt ? `${toFa(fcnt)} فایل پایگاه‌داده ذخیره شد` : (d.error ? `خطا: ${d.error}` : '');
        } else if (lg.action === 'docs_scanned') {
          detailStr = `${toFa(d.files || 0)} سند و ${toFa(d.tables || 0)} جدول بررسی شد`;
        } else if (d.title) {
          detailStr = `«${d.title}»`;
        } else if (d.error) {
          detailStr = `خطا: ${d.error}`;
        }
        const tsClean = String(lg.ts || '').replace(/\d/g, ch => '۰۱۲۳۴۵۶۷۸۹'[ch]);
        return `
          <div class="eh-audit-row">
            <div class="eh-audit-main">
              <div class="eh-audit-top">
                <span class="eh-audit-badge kind-${meta.kind}">${esc(meta.tag)}</span>
                <strong class="eh-audit-title">${esc(meta.title)}</strong>
              </div>
              ${detailStr ? `<div class="eh-audit-detail">${esc(detailStr)}</div>` : ''}
            </div>
            <span class="eh-audit-ts">${esc(tsClean)}</span>
          </div>
        `;
      }).join('');
    } catch (_) {}
  }

  function organizeExecutiveSidebar() {
    const navList = document.querySelector('#sidebar .nav-list');
    if (!navList || navList.dataset.ehGrouped === '1') return true;
    const btnDash = navList.querySelector(".nav-btn[onclick*=\"'dashboard'\"]");
    const btnChat = navList.querySelector(".nav-btn[onclick*=\"'chat'\"]");
    const btnDocs = navList.querySelector(".nav-btn[onclick*=\"'docs'\"]");
    const btnExec = document.getElementById('navAction_exec_analytics');
    const btnMedia = document.getElementById('navAction_media_studio') || document.getElementById('navBtnMediaStudio');
    const btnEvent = document.getElementById('navAction_event_pipeline');
    const btnLetter = document.getElementById('navAction_letter_registry');
    const btnPorsline = document.getElementById('navAction_porsline_hub');
    const btnHealth = document.getElementById('navAction_data_health');
    if (!btnDash || !btnExec || !btnMedia) return false;
    navList.dataset.ehGrouped = '1';

    let indicator = document.getElementById('navIndicator');
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.id = 'navIndicator';
    }

    const setLabel = (btn, text) => {
      if (!btn) return;
      const lbl = btn.querySelector('.pro-nav-lbl') || btn.querySelector('span');
      if (lbl) lbl.textContent = text;
      btn.setAttribute('data-tooltip', text);
    };
    setLabel(btnDash, '\u062f\u0627\u0634\u0628\u0648\u0631\u062f');
    setLabel(btnChat, '\u062f\u0633\u062a\u06cc\u0627\u0631 \u0647\u0648\u0634\u0645\u0646\u062f');
    setLabel(btnExec, '\u0622\u0645\u0627\u0631 \u0648 \u0646\u0645\u0648\u062f\u0627\u0631\u0647\u0627');
    setLabel(btnMedia, '\u062a\u0648\u0644\u06cc\u062f \u0645\u062d\u062a\u0648\u0627');
    setLabel(btnEvent, '\u0631\u0648\u06cc\u062f\u0627\u062f\u0647\u0627');
    setLabel(btnLetter, '\u062f\u0628\u06cc\u0631\u062e\u0627\u0646\u0647');
    setLabel(btnPorsline, '\u067e\u0631\u0633\u200c\u0644\u0627\u06cc\u0646');
    setLabel(btnDocs, '\u0627\u0633\u0646\u0627\u062f \u0648 \u0641\u0627\u06cc\u0644\u200c\u0647\u0627');
    setLabel(btnHealth, '\u067e\u0627\u06a9\u200c\u0633\u0627\u0632\u06cc \u062f\u0627\u062f\u0647\u200c\u0647\u0627');

    const btnSettings = document.querySelector("#sidebar .sidebar-footer .nav-btn[onclick*='settings']") || document.querySelector('#sidebar .sidebar-footer .nav-btn:not(.eh-diag-sb-btn):not(.eh-mem-sb-btn)');
    setLabel(btnSettings, '\u062a\u0646\u0638\u06cc\u0645\u0627\u062a');

    const mkHeader = (t) => { const d = document.createElement('div'); d.className = 'eh-nav-group-lbl'; d.textContent = t; return d; };
    const oldTop = document.querySelector('#sidebar .nav-section-label');
    if (oldTop) oldTop.style.display = 'none';

    navList.innerHTML = '';
    navList.appendChild(indicator);
    navList.appendChild(mkHeader('\u0645\u06cc\u0632 \u06a9\u0627\u0631'));
    [btnDash, btnChat, btnExec].forEach(b => b && navList.appendChild(b));
    navList.appendChild(mkHeader('\u0639\u0645\u0644\u06cc\u0627\u062a \u0648 \u0645\u062d\u062a\u0648\u0627'));
    [btnMedia, btnEvent, btnLetter].forEach(b => b && navList.appendChild(b));
    navList.appendChild(mkHeader('\u062f\u0627\u062f\u0647\u200c\u0647\u0627 \u0648 \u0627\u0633\u0646\u0627\u062f'));
    [btnPorsline, btnDocs, btnHealth].forEach(b => b && navList.appendChild(b));

    if (window.ResizeObserver && !navList._ehObserved) {
      navList._ehObserved = true;
      new ResizeObserver(() => syncNavIndicator(navList.querySelector('.nav-btn.active'))).observe(navList);
    }
    requestAnimationFrame(() => syncNavIndicator(navList.querySelector('.nav-btn.active')));
    return true;
  }

  function enhanceUnifiedDashboard() {
    const dash = document.getElementById('page-dashboard');
    if (!dash) return;
    const statsGrid = dash.querySelector('.stats-grid');
    if (statsGrid && !document.getElementById('ehHeroBanner')) {
      const hero = document.createElement('div');
      hero.id = 'ehHeroBanner';
      hero.className = 'eh-quick-strip';
      hero.innerHTML =
        '<div class="eh-quick-grid">' +
        '<button type="button" class="eh-quick-card" id="qkAskAi"><div class="eh-quick-ico">' + ic('search', 18) + '</div><div><span class="eh-quick-title">\u067e\u0631\u0633\u0634 \u0627\u0632 \u062f\u0633\u062a\u06cc\u0627\u0631</span><span class="eh-quick-desc">\u062f\u0631\u06cc\u0627\u0641\u062a \u0633\u0631\u06cc\u0639 \u0622\u0645\u0627\u0631 \u0648 \u06af\u0632\u0627\u0631\u0634</span></div></button>' +
        '<button type="button" class="eh-quick-card" id="qkPorsline"><div class="eh-quick-ico">' + ic('upload', 18) + '</div><div><span class="eh-quick-title">\u067e\u0631\u0633\u200c\u0644\u0627\u06cc\u0646</span><span class="eh-quick-desc">\u062b\u0628\u062a \u0627\u06a9\u0633\u0644 \u0648 \u0628\u0631\u06af\u0647 \u062d\u0636\u0648\u0631 \u0648 \u063a\u06cc\u0627\u0628</span></div></button>' +
        '<button type="button" class="eh-quick-card" id="qkMedia"><div class="eh-quick-ico">' + ic('penTool', 18) + '</div><div><span class="eh-quick-title">\u062a\u0648\u0644\u06cc\u062f \u0645\u062d\u062a\u0648\u0627</span><span class="eh-quick-desc">\u0646\u06af\u0627\u0631\u0634 \u0627\u0637\u0644\u0627\u0639\u06cc\u0647 \u0648 \u06af\u0632\u0627\u0631\u0634 \u062a\u0635\u0648\u06cc\u0631\u06cc</span></div></button>' +
        '<button type="button" class="eh-quick-card" id="qkStats"><div class="eh-quick-ico">' + ic('barChart', 18) + '</div><div><span class="eh-quick-title">\u0622\u0645\u0627\u0631 \u0648 \u0646\u0645\u0648\u062f\u0627\u0631\u0647\u0627</span><span class="eh-quick-desc">\u062a\u062d\u0644\u06cc\u0644 \u062f\u0648\u0631\u0647\u200c\u0647\u0627\u060c \u0627\u0633\u0627\u062a\u06cc\u062f \u0648 \u062e\u0631\u0648\u062c\u06cc</span></div></button>' +
        '</div>';
      dash.insertBefore(hero, statsGrid);
      document.getElementById('qkAskAi').addEventListener('click', () => window.switchPageById?.('chat'));
      document.getElementById('qkPorsline').addEventListener('click', () => window.eHadiApp?.openModal('porsline_hub'));
      document.getElementById('qkMedia').addEventListener('click', () => window.eHadiApp?.openModal('media_studio'));
      document.getElementById('qkStats').addEventListener('click', () => openEmbeddedFullPage('exec_analytics'));
    }

    const radarItems = document.getElementById('ehRadarItems');
    if (radarItems && !document.getElementById('ehHealthGaugeWrap')) {
      Promise.all([
        window.pywebview?.api?.get_executive_analytics?.({}).catch(() => null),
        window.pywebview?.api?.get_event_pipelines?.().catch(() => null),
      ]).then(([res, evRes]) => {
        if (res && res.ok && !document.getElementById('ehHealthGaugeWrap')) {
          const score = Number(res.kpis?.data_health_score ?? 100);
          const r = 17, c = 2 * Math.PI * r;
          const offset = c * (1 - Math.max(0, Math.min(100, score)) / 100);
          const wrap = document.createElement('div');
          wrap.id = 'ehHealthGaugeWrap';
          wrap.className = 'eh-health-ring-wrap';
          wrap.innerHTML =
            '<svg class="eh-health-ring" viewBox="0 0 42 42">' +
            '<circle cx="21" cy="21" r="' + r + '" fill="none" stroke="rgba(148,163,184,0.18)" stroke-width="4"/>' +
            '<circle class="fg" cx="21" cy="21" r="' + r + '" fill="none" stroke-width="4" stroke-dasharray="' + c.toFixed(1) + '" stroke-dashoffset="' + offset.toFixed(1) + '" transform="rotate(-90 21 21)"/>' +
            '<text x="21" y="25" text-anchor="middle" font-size="10.5" font-weight="800" fill="currentColor">' + toFa(score) + '%</text>' +
            '</svg>' +
            '<div style="flex:1;"><strong style="font-size:12px;">\u0633\u0644\u0627\u0645\u062a \u0648 \u06cc\u06a9\u062a\u0627\u06cc\u06cc \u062f\u0627\u062f\u0647\u200c\u0647\u0627</strong>' +
            '<div style="font-size:10.8px; color:var(--s-text-muted); margin-top:2px;">\u067e\u0627\u06cc\u0634 \u062e\u0648\u062f\u06a9\u0627\u0631 \u062a\u06a9\u0631\u0627\u0631\u0647\u0627 \u0648 \u0633\u0644\u0627\u0645\u062a \u062c\u062f\u0627\u0648\u0644</div></div>';
          radarItems.parentNode.insertBefore(wrap, radarItems);
        }

        const pendingEvs = ((evRes && evRes.events) || []).filter(ev => {
          const st = ev.stages || {};
          return Object.values(st).filter(Boolean).length < 6;
        });
        if (pendingEvs.length && !document.getElementById('ehRadarEventsRow')) {
          const row = document.createElement('div');
          row.id = 'ehRadarEventsRow';
          row.className = 'eh-radar-row';
          row.innerHTML = `<span>${toFa(pendingEvs.length)} \u0631\u0648\u06cc\u062f\u0627\u062f \u062f\u0631 \u062d\u0627\u0644 \u067e\u06cc\u06af\u06cc\u0631\u06cc \u0648 \u062a\u06a9\u0645\u06cc\u0644 \u0645\u0631\u0627\u062d\u0644</span><button type="button" class="eh-mini-btn" id="btnGoEventsRadar">\u0645\u0634\u0627\u0647\u062f\u0647 \u0631\u0648\u06cc\u062f\u0627\u062f\u0647\u0627</button>`;
          radarItems.appendChild(row);
          row.querySelector('#btnGoEventsRadar').addEventListener('click', () => openEmbeddedFullPage('event_pipeline'));
        }
      });
    }

    const decList = document.getElementById('ehDecisionList');
    if (decList && !document.getElementById('btnGenMinutesAi')) {
      const btnMin = document.createElement('button');
      btnMin.id = 'btnGenMinutesAi';
      btnMin.type = 'button';
      btnMin.className = 'ghost-btn bi-mini-btn';
      btnMin.style.marginTop = '8px';
      btnMin.textContent = '\u062a\u0648\u0644\u06cc\u062f \u062e\u0648\u062f\u06a9\u0627\u0631 \u0635\u0648\u0631\u062a\u200c\u062c\u0644\u0633\u0647 \u0628\u0627 \u062f\u0633\u062a\u06cc\u0627\u0631';
      btnMin.addEventListener('click', async () => {
        const dRes = await window.pywebview?.api?.get_decisions?.().catch(() => null);
        const items = ((dRes && dRes.decisions) || []).map((d, i) => `${toFa(i + 1)}. ${d.title}`).join('\n');
        window.switchPageById?.('chat');
        const inp = document.getElementById('chatInput');
        if (inp) {
          inp.value = '\u0628\u0631 \u0627\u0633\u0627\u0633 \u0622\u0645\u0627\u0631 \u0641\u0639\u0644\u06cc \u0645\u0624\u0633\u0633\u0647 \u0648 \u0645\u0635\u0648\u0628\u0627\u062a \u0632\u06cc\u0631\u060c \u06cc\u06a9 \u0635\u0648\u0631\u062a\u200c\u062c\u0644\u0633\u0647 \u0631\u0633\u0645\u06cc \u0648 \u0627\u062f\u0627\u0631\u06cc \u062a\u0646\u0638\u06cc\u0645 \u06a9\u0646:\n' + (items || '\u0645\u0631\u0648\u0631 \u0639\u0645\u0644\u06a9\u0631\u062f \u06a9\u0627\u0631\u06af\u0631\u0648\u0647\u200c\u0647\u0627 \u0648 \u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0631\u06cc\u0632\u06cc \u062f\u0648\u0631\u0647\u200c\u0647\u0627\u06cc \u0622\u062a\u06cc');
          inp.focus();
        }
      });
      decList.parentNode.appendChild(btnMin);
    }
  }

  async function registerLiveSearchCommands() {
    const App = window.eHadiApp;
    if (!App || App._v29LiveCmds) return;
    App._v29LiveCmds = true;
    try {
      const res = await window.pywebview?.api?.get_executive_analytics?.({});
      if (res && res.ok) {
        (res.teachers || []).slice(0, 25).forEach(t => {
          const shortName = window.formatTeacherShort ? window.formatTeacherShort(t.name) : t.name;
          App.registerCommand({
            label: `\u067e\u0631\u0648\u0646\u062f\u0647 ${shortName} (${toFa(t.courses)} \u062f\u0648\u0631\u0647)`,
            cat: '\u0627\u0633\u0627\u062a\u06cc\u062f',
            key: '',
            run: () => openTeacher360Drawer(t.name)
          });
        });
      }
    } catch (_) {}
  }

  function startAll() {
    mountAmbientMesh();
    hookDotlessToasts();
    setupSmoothWindowControls();
    tagSubsystemCard();
    applyCleanHonorificInTitlebar();
    let tries = 0;
    const t = setInterval(() => {
      tries++;
      setupSmoothWindowControls();
      tagSubsystemCard();
      applyCleanHonorificInTitlebar();
      if (organizeExecutiveSidebar() || tries > 8) clearInterval(t);
    }, 200);
    hookRouting();
    mountTopbarActions();
    upgradeSettingsModal();
    enhanceUnifiedDashboard();
    polishChatAndPageCopy();
    attachJalaliPickers();
    handleNetworkStatus();
    updateBreadcrumb('dashboard');
  }

  window.addEventListener('DOMContentLoaded', startAll);
  window.addEventListener('pywebviewready', async () => {
    setupSmartApiLayer();
    startAll();
    setTimeout(() => { enhanceUnifiedDashboard(); registerLiveSearchCommands(); polishChatAndPageCopy(); hookDotlessToasts(); setupSmoothWindowControls(); tagSubsystemCard(); applyCleanHonorificInTitlebar(); }, 400);
    try {
      const br = await window.pywebview?.api?.get_branding_settings?.();
      if (br?.branding?.ui_palette) applyPalette(br.branding.ui_palette, false);
      if (br?.branding?.ui_density) applyDensity(br.branding.ui_density, false);
    } catch (_) {}
  });
  window.toggleAppPalette = togglePalette;
})();

// _V33_0_FIX_START
(() => {
  const INST_NAME = '\u0645\u0624\u0633\u0633\u0647 \u0627\u0645\u0627\u0645 \u0647\u0627\u062f\u06cc';
  const ALAYH = '\u0639\u0644\u06cc\u0647\u200c\u0627\u0644\u0633\u0644\u0627\u0645';

  const ICONS = {
    donut: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>',
    top: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
    compare: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    teachers: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    pulse: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    docEngine: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    duckdb: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
    lancedb: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
    gemini: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z"/></svg>',
  };

  let dashObserver = null;
  let isApplying = false;

  function pauseObserver(fn) {
    if (dashObserver) dashObserver.disconnect();
    try {
      fn();
    } finally {
      const dash = document.getElementById('page-dashboard');
      if (dash && dashObserver) {
        dashObserver.observe(dash, { childList: true, subtree: true });
      }
    }
  }

  // --- Bulletproof Persian Number Parsing & Observer-Isolated Count-Up ---
  function parseFaNumber(str) {
    const raw = String(str || '').trim();
    if (!raw || raw.includes(' / ')) return null;
    const norm = raw
      .replace(/[\u06f0-\u06f9]/g, d => String(d.charCodeAt(0) - 0x06f0))
      .replace(/[\u0660-\u0669]/g, d => String(d.charCodeAt(0) - 0x0660))
      .replace(/[\u066c\u060c,\s]/g, '')
      .replace(/[\u066b\u2044\/]/g, '.');
    const m = norm.match(/^(-?\d+(?:\.\d+)?)(.*)$/);
    if (!m) return null;
    const val = parseFloat(m[1]);
    if (!Number.isFinite(val)) return null;
    const decPart = m[1].includes('.') ? m[1].split('.')[1].length : 0;
    const suffix = (m[2] || '').trim();
    if (suffix.length > 5) return null;
    return { val, decimals: decPart, suffix };
  }

  function formatFaNum(val, decimals, suffix) {
    const formatted = Number(val).toLocaleString('fa-IR', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
    return suffix ? (formatted + ' ' + suffix) : formatted;
  }

  const numMemory = new Map();

  function animateNumericElement(el, key) {
    if (!el || el.children.length > 0) return;
    if (el.dataset.ehAnimating === '1') return;

    const currentTxt = (el.textContent || '').trim();
    if (!currentTxt || currentTxt === el.dataset.ehLastWritten) return;

    const parsed = parseFaNumber(currentTxt);
    if (!parsed) return;

    const k = key || el.id;
    if (!k) return;

    const prev = numMemory.has(k) ? numMemory.get(k) : 0;
    numMemory.set(k, parsed.val);

    if (prev === parsed.val) {
      el.dataset.ehLastWritten = currentTxt;
      return;
    }

    if (el._ehCountRaf) cancelAnimationFrame(el._ehCountRaf);
    el.dataset.ehAnimating = '1';

    const startVal = prev;
    const endVal = parsed.val;
    const dur = 260;
    let t0 = null;
    el.classList.remove('eh-num-pop');
    void el.offsetWidth;
    el.classList.add('eh-num-pop');

    const step = (now) => {
      if (t0 === null) t0 = now;
      const p = Math.max(0, Math.min(1, (now - t0) / dur));
      const eased = 1 - Math.pow(1 - p, 4);
      const cur = startVal + (endVal - startVal) * eased;
      const outTxt = formatFaNum(p < 1 ? cur : endVal, parsed.decimals, parsed.suffix);

      pauseObserver(() => {
        el.textContent = outTxt;
        el.dataset.ehLastWritten = outTxt;
      });

      if (p < 1) {
        el._ehCountRaf = requestAnimationFrame(step);
      } else {
        el._ehCountRaf = null;
        delete el.dataset.ehAnimating;
      }
    };
    el._ehCountRaf = requestAnimationFrame(step);
  }

  function triggerSmoothCountUps(dash) {
    if (!dash) return;
    const statEls = dash.querySelectorAll('.stat-value, .bi-kpi-val, .bi-kpi-num, .eh-kpi-val');
    statEls.forEach((el, idx) => {
      if (el.children.length > 0) return;
      const card = el.closest('.stat-card, .bi-kpi, .eh-kpi, .glass-card');
      const lblEl = card?.querySelector('.stat-label, .bi-kpi-lbl, .eh-kpi-lbl, span, small');
      const stableKey = el.id || ('kpi_' + ((lblEl?.textContent || '').trim().slice(0, 20) || idx));
      animateNumericElement(el, stableKey);
    });
  }

  // --- Zero-Jump Scroll Anchoring ---
  let anchorState = null;

  function captureScrollAnchor(e) {
    const dash = document.getElementById('page-dashboard');
    const content = document.querySelector('main.content');
    if (!dash || !content || !dash.contains(e.target)) return;

    const clickedCard = e.target.closest('.eh-bi-quad-card');
    if (!clickedCard) return;

    const typeMatch = Array.from(clickedCard.classList).find(c => c.startsWith('eh-bi-theme-'));
    const hubWrap = clickedCard.parentElement?.parentElement || clickedCard.parentElement;
    if (hubWrap && hubWrap !== dash) {
      const h = hubWrap.offsetHeight;
      if (h > 250) {
        hubWrap.style.minHeight = h + 'px';
        clearTimeout(hubWrap._ehMinHTmr);
        hubWrap._ehMinHTmr = setTimeout(() => { hubWrap.style.minHeight = ''; }, 700);
      }
    }

    anchorState = {
      typeClass: typeMatch || null,
      rectTop: clickedCard.getBoundingClientRect().top,
      scrollTop: content.scrollTop,
      ts: performance.now(),
      innerScrolls: {}
    };
    dash.querySelectorAll('.eh-bi-quad-card').forEach(c => {
      const tc = Array.from(c.classList).find(x => x.startsWith('eh-bi-theme-'));
      const sc = c.querySelector('.eh-donut-scroll, .eh-cmp-scroll, .eh-rank-scroll');
      if (tc && sc) anchorState.innerScrolls[tc] = sc.scrollTop;
    });
  }

  function restoreScrollAnchorNow() {
    if (!anchorState || (performance.now() - anchorState.ts > 650)) {
      anchorState = null;
      return;
    }
    const dash = document.getElementById('page-dashboard');
    const content = document.querySelector('main.content');
    if (!dash || !content) return;

    Object.entries(anchorState.innerScrolls).forEach(([tc, st]) => {
      if (tc === 'eh-bi-theme-donut' || tc === 'eh-bi-theme-compare') {
        const c = dash.querySelector('.' + tc);
        const sc = c?.querySelector('.eh-donut-scroll, .eh-cmp-scroll');
        if (sc && Math.abs(sc.scrollTop - st) > 1) sc.scrollTop = st;
      }
    });

    if (anchorState.typeClass) {
      const card = dash.querySelector('.' + anchorState.typeClass);
      if (card) {
        const newTop = card.getBoundingClientRect().top;
        const delta = newTop - anchorState.rectTop;
        if (Math.abs(delta) > 0.5) content.scrollTop += delta;
        return;
      }
    }
    if (Math.abs(content.scrollTop - anchorState.scrollTop) > 1) {
      content.scrollTop = anchorState.scrollTop;
    }
  }

  // --- Titlebar Delicate Fix ---
  function fixTitlebarDelicately() {
    const tb = document.querySelector('.titlebar');
    if (!tb || tb.querySelector('.eh-tb-brand-text')) return;
    const walker = document.createTreeWalker(tb, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let n;
    while ((n = walker.nextNode())) {
      const p = n.parentElement;
      if (!p || p.closest('.version-pill, button')) continue;
      if ((n.nodeValue || '').includes(INST_NAME)) nodes.push(n);
    }
    nodes.forEach(txtNode => {
      const cleanBase = (txtNode.nodeValue || '')
        .replaceAll(ALAYH, '')
        .replaceAll('(\u0639)', '')
        .replaceAll('\u0611', '')
        .replace(/\(\s*\)/g, '')
        .replace(/\s+/g, ' ')
        .trim();
      const wrap = document.createElement('span');
      wrap.className = 'eh-tb-brand-text';
      wrap.setAttribute('dir', 'rtl');
      wrap.innerHTML = `${cleanBase} <span class="eh-honorific">${ALAYH}</span>`;
      txtNode.parentNode.replaceChild(wrap, txtNode);
    });
  }

  // --- Compact 4-Column Live Telemetry Strip for "????? ???????????" ---
  function upgradeSubsystemTelemetryCard(dash, leaves) {
    for (const el of leaves) {
      const txt = (el.textContent || '').trim();
      if (!txt.startsWith('\u0648\u0636\u0639\u06cc\u062a \u0632\u06cc\u0631\u0633\u06cc\u0633\u062a\u0645')) continue;
      const card = el.closest('.glass-card, .bi-card, .card') || el.parentElement?.parentElement;
      if (!card || card.dataset.ehTelemetryDone === '1') break;

      const specs = [
        { kw: '\u0645\u0648\u062a\u0648\u0631 \u067e\u0631\u062f\u0627\u0632\u0634', ico: ICONS.docEngine, sub: '\u067e\u0631\u062f\u0627\u0632\u0634 \u0648 \u062a\u062d\u0644\u06cc\u0644 \u0627\u0633\u0646\u0627\u062f' },
        { kw: 'DuckDB', ico: ICONS.duckdb, sub: '\u0645\u0648\u062a\u0648\u0631 \u0622\u0645\u0627\u0631\u06cc \u0648 \u062c\u062f\u0627\u0648\u0644' },
        { kw: 'LanceDB', ico: ICONS.lancedb, sub: '\u062c\u0633\u062a\u062c\u0648\u06cc \u0645\u0639\u0646\u0627\u06cc\u06cc \u0627\u0633\u0646\u0627\u062f' },
        { kw: 'Gemini', ico: ICONS.gemini, sub: '\u0647\u0633\u062a\u0647 \u0647\u0648\u0634 \u0645\u0635\u0646\u0648\u0639\u06cc' },
      ];

      const foundRows = [];
      specs.forEach(sp => {
        const lf = Array.from(card.querySelectorAll('*')).find(n => n.children.length === 0 && (n.textContent || '').includes(sp.kw));
        if (!lf) return;
        let p = lf.parentElement;
        while (p && p !== card) {
          const pt = p.textContent || '';
          const matchCount = specs.filter(s => pt.includes(s.kw)).length;
          if (matchCount === 1 && (p.classList.contains('pipeline-item') || pt.includes('\u0641\u0639\u0627\u0644') || pt.includes('\u0645\u062a\u0635\u0644') || pt.includes('\u0628\u0631\u0631\u0633\u06cc') || pt.includes('\u0622\u0645\u0627\u062f\u0647') || pt.includes('\u06a9\u0644\u06cc\u062f'))) {
            foundRows.push({ row: p, spec: sp });
            break;
          }
          p = p.parentElement;
        }
      });

      if (foundRows.length < 2) break;
      card.dataset.ehTelemetryDone = '1';
      card.classList.add('eh-subsys-card');

      // Ensure parent split container doesn't force giant empty vertical height
      const splitParent = card.closest('.dash-split');
      if (splitParent) {
        splitParent.style.minHeight = '';
      }

      // Build sleek compact header row
      if (!card.querySelector('.eh-subsys-hdr')) {
        const hdr = document.createElement('div');
        hdr.className = 'eh-subsys-hdr';
        const titleGrp = document.createElement('div');
        titleGrp.className = 'eh-subsys-hdr-title';
        titleGrp.innerHTML = `<span class="eh-subsys-hdr-ico">${ICONS.pulse}</span>`;
        const parentOfEl = el.parentElement;
        el.style.margin = '0';
        el.style.fontSize = '13.5px';
        el.style.fontWeight = '800';
        titleGrp.appendChild(el);
        hdr.appendChild(titleGrp);

        const onlinePill = document.createElement('span');
        onlinePill.className = 'eh-subsys-online-pill';
        onlinePill.innerHTML = `<span class="eh-live-dot"></span>\u0647\u0645\u0647 \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627 \u0641\u0639\u0627\u0644`;
        hdr.appendChild(onlinePill);
        card.insertBefore(hdr, card.firstChild);
        if (parentOfEl && parentOfEl !== card && parentOfEl.children.length === 0) parentOfEl.remove();
      }

      // Upgrade wrapper to 4-column horizontal grid & rebuild each tile cleanly
      const parentWrap = foundRows[0].row.parentElement;
      if (parentWrap && parentWrap !== card) {
        parentWrap.classList.remove('eh-subsys-row', 'eh-subsys-list');
        parentWrap.classList.add('eh-subsys-wrapper');
        parentWrap.style.background = '';
        parentWrap.style.border = '';
      }

      foundRows.forEach(({ row, spec }) => {
        const children = Array.from(row.children);
        let nameTxt = '';
        let statusTxt = '';
        if (children.length >= 2) {
          nameTxt = (children[0].textContent || '').trim();
          statusTxt = (children[children.length - 1].textContent || '').trim();
        } else {
          nameTxt = spec.kw;
          statusTxt = '\u0641\u0639\u0627\u0644';
        }
        const statusIdAttr = (spec.kw === 'Gemini' || row.querySelector('#aiStatusLabel')) ? ' id="aiStatusLabel"' : '';
        const shortStatus = statusTxt.includes('\u0622\u0645\u0627\u062f\u0647') ? '\u0645\u062a\u0635\u0644 \u0648 \u0622\u0645\u0627\u062f\u0647' : statusTxt;
        row.className = 'eh-subsys-item';
        row.style.cssText = '';
        row.innerHTML = `
          <div class="eh-ss-main">
            <span class="eh-ss-ico">${spec.ico}</span>
            <div class="eh-ss-meta">
              <span class="eh-ss-name" title="${nameTxt}">${nameTxt}</span>
              <span class="eh-ss-sub">${spec.sub}</span>
            </div>
          </div>
          <span class="eh-ss-badge" title="${statusTxt}"><span class="eh-live-dot"></span><span${statusIdAttr}>${shortStatus}</span></span>
        `;
      });
      break;
    }
  }

  function shortenVerboseTeacherLeaves(container) {
    if (!container || typeof window.formatTeacherShort !== 'function') return;
    const isTeachersCard = Boolean(container.closest('.eh-bi-theme-teachers'));
    const isTopCard = Boolean(container.closest('.eh-bi-theme-top'));
    if (!isTeachersCard && !isTopCard) return;

    const rows = Array.from(container.children).filter(el => el.nodeType === 1);
    rows.forEach(row => {
      const textLeaves = Array.from(row.querySelectorAll('span, div, strong, b')).filter(el => {
        if (el.children.length > 0) return false;
        const raw = (el.textContent || '').trim();
        if (!raw || raw.length < 3) return false;
        if (/^[\d\u06f0-\u06f9\s,\u066c.%?]+$/.test(raw)) return false;
        if (raw.includes('\u0646\u0641\u0631') || raw.includes('\u062f\u0648\u0631\u0647')) return false;
        return true;
      });
      if (!textLeaves.length) return;

      let teacherTargets = [];
      if (isTeachersCard) {
        teacherTargets = textLeaves;
      } else if (isTopCard) {
        // In RTL Top Courses row: Rightmost text leaf is the COURSE TITLE, Leftmost text leaf is the TEACHER NAME!
        if (textLeaves.length >= 2) {
          const sortedByX = textLeaves.slice().sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
          // Only pick the leftmost leaf (teacher), NEVER the rightmost leaf (course title)
          teacherTargets = [sortedByX[0]];
        }
      }

      teacherTargets.forEach(el => {
        if (el.dataset.ehShortened === '1') return;
        const raw = (el.textContent || '').trim();
        const formatted = window.formatTeacherShort(raw);
        el.dataset.ehShortened = '1';
        el.setAttribute('title', raw);
        if (formatted && formatted !== raw) {
          el.textContent = formatted;
        }
      });
    });
  }

  // --- Interactive Cross-Highlight: Link Legend Rows <-> Donut SVG Slices + Live Center Preview ---
  function bindDonutCrossHighlight(card, listEl) {
    if (!card || !listEl) return;
    const svg = card.querySelector('svg');
    if (!svg || svg.dataset.ehCrossBound === '1') return;

    const items = Array.from(listEl.children).filter(el => el.classList.contains('eh-donut-item'));
    if (!items.length) return;

    let slices = Array.from(svg.querySelectorAll('path')).filter(p => {
      const f = (p.getAttribute('fill') || getComputedStyle(p).fill || '').toLowerCase();
      return f && f !== 'none' && f !== 'transparent' && f !== 'rgba(0, 0, 0, 0)';
    });
    if (slices.length < 2) {
      slices = Array.from(svg.querySelectorAll('circle')).filter(c => {
        const da = c.getAttribute('stroke-dasharray') || getComputedStyle(c).strokeDasharray || '';
        return da && da !== 'none';
      });
    }
    if (!slices.length) return;

    svg.dataset.ehCrossBound = '1';
    svg.classList.add('eh-donut-svg');
    slices.forEach(s => s.classList.add('eh-donut-slice'));

    const donutZone = svg.parentElement;
    let centerNumEl = null;
    let centerLblEl = null;
    const centerCandidates = [
      ...Array.from(svg.querySelectorAll('text')),
      ...Array.from(donutZone ? donutZone.querySelectorAll('div, span, strong, b') : []).filter(el => el.children.length === 0 && !el.closest('.eh-donut-scroll, .eh-bi-hdr'))
    ];
    centerCandidates.forEach(el => {
      const t = (el.textContent || '').trim();
      if (!t) return;
      if (!centerNumEl && parseFaNumber(t)) centerNumEl = el;
      else if (!centerLblEl && !parseFaNumber(t)) centerLblEl = el;
    });

    if (centerNumEl) {
      centerNumEl.dataset.ehOrigVal = (centerNumEl.textContent || '').trim();
      animateNumericElement(centerNumEl, 'donut_center_total');
    }
    if (centerLblEl) {
      centerLblEl.dataset.ehOrigVal = (centerLblEl.textContent || '').trim();
    }

    const getColor = (el) => {
      if (!el) return '';
      const cs = getComputedStyle(el);
      return (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)')
        ? cs.backgroundColor
        : (cs.fill && cs.fill !== 'none' ? cs.fill : cs.stroke || '');
    };

    const itemMeta = items.map((item, idx) => {
      const dot = item.querySelector('[style*="border-radius: 50%"], [style*="border-radius:50%"], .bi-dot, .legend-dot, span[style*="background"]');
      const dotColor = getColor(dot);
      const itemLeaves = Array.from(item.querySelectorAll('*')).filter(el => el.children.length === 0);
      let name = '';
      let countStr = '';
      itemLeaves.forEach(lf => {
        const t = (lf.textContent || '').trim();
        if (!t) return;
        if (t.includes('%') || t.includes('\u066a')) {
          const beforeParen = t.split('(')[0].trim();
          if (beforeParen) countStr = beforeParen;
        } else if (parseFaNumber(t) && !countStr) {
          countStr = t;
        } else if (t.length > 2 && !t.startsWith('(')) {
          name = t;
        }
      });
      let sliceIdx = slices.findIndex(s => {
        const sc = getComputedStyle(s);
        const c1 = sc.fill && sc.fill !== 'none' ? sc.fill : '';
        const c2 = sc.stroke && sc.stroke !== 'none' ? sc.stroke : '';
        return dotColor && (c1 === dotColor || c2 === dotColor);
      });
      if (sliceIdx === -1) sliceIdx = idx < slices.length ? idx : -1;
      return { item, sliceIdx, name, countStr };
    });

    const activatePair = (metaIdx) => {
      const m = itemMeta[metaIdx];
      if (!m) return;
      pauseObserver(() => {
        items.forEach((it, i) => {
          it.classList.toggle('eh-cross-active', i === metaIdx);
          it.classList.toggle('eh-item-dim', i !== metaIdx);
        });
        slices.forEach((sl, si) => {
          sl.classList.toggle('eh-slice-pop', si === m.sliceIdx);
          sl.classList.toggle('eh-slice-dim', si !== m.sliceIdx);
        });
        if (centerNumEl && m.countStr) {
          if (centerNumEl._ehCountRaf) cancelAnimationFrame(centerNumEl._ehCountRaf);
          delete centerNumEl.dataset.ehAnimating;
          centerNumEl.textContent = m.countStr;
          centerNumEl.dataset.ehLastWritten = m.countStr;
        }
        if (centerLblEl && m.name) {
          centerLblEl.textContent = m.name.length > 18 ? (m.name.slice(0, 17) + '\u2026') : m.name;
        }
      });
    };

    const resetPair = () => {
      pauseObserver(() => {
        items.forEach(it => it.classList.remove('eh-cross-active', 'eh-item-dim'));
        slices.forEach(sl => sl.classList.remove('eh-slice-pop', 'eh-slice-dim'));
        if (centerNumEl && centerNumEl.dataset.ehOrigVal) {
          centerNumEl.textContent = centerNumEl.dataset.ehOrigVal;
          centerNumEl.dataset.ehLastWritten = centerNumEl.dataset.ehOrigVal;
        }
        if (centerLblEl && centerLblEl.dataset.ehOrigVal) {
          centerLblEl.textContent = centerLblEl.dataset.ehOrigVal;
        }
      });
    };

    itemMeta.forEach((m, idx) => {
      m.item.addEventListener('mouseenter', () => activatePair(idx));
      m.item.addEventListener('mouseleave', resetPair);
      if (m.sliceIdx >= 0 && slices[m.sliceIdx]) {
        const sl = slices[m.sliceIdx];
        sl.addEventListener('mouseenter', () => activatePair(idx));
        sl.addEventListener('mouseleave', resetPair);
      }
    });
  }

  // --- Synchronous, Zero-Flicker Enhancement Engine ---
  function applyAllDashboardV33() {
    if (isApplying) return;
    isApplying = true;
    if (dashObserver) dashObserver.disconnect();

    try {
      fixTitlebarDelicately();
      const dash = document.getElementById('page-dashboard');
      if (!dash) return;

      const leaves = Array.from(dash.querySelectorAll('h2, h3, h4, .card-title, span, div, p, strong')).filter(el => el.children.length === 0);

      // 1. Compact 4-Column Subsystems Telemetry Card
      upgradeSubsystemTelemetryCard(dash, leaves);

      // 2. Four Main BI Quad Cards
      const matchers = [
        { type: 'donut', test: (t) => t.includes('\u0633\u0647\u0645 \u0645\u062e\u0627\u0637\u0628\u0627\u0646') },
        { type: 'top', test: (t) => t.includes('\u067e\u0631\u0645\u062e\u0627\u0637\u0628') && !t.includes('\u067e\u0631\u0645\u062e\u0627\u0637\u0628\u200c\u062a\u0631\u06cc\u0646') && !t.includes('\u067e\u0631\u0645\u062e\u0627\u0637\u0628 \u062a\u0631\u06cc\u0646') },
        { type: 'compare', test: (t) => t.includes('\u0645\u0642\u0627\u06cc\u0633\u0647 \u06a9\u0627\u0631\u06af\u0631\u0648\u0647') },
        { type: 'teachers', test: (t) => t.includes('\u0627\u0633\u0627\u062a\u06cc\u062f \u0634\u0627\u062e\u0635') },
      ];

      matchers.forEach(({ type, test }) => {
        const titleEl = leaves.find(el => {
          if (el.closest('svg, button, table')) return false;
          const t = (el.textContent || '').trim();
          return t.length >= 8 && t.length <= 65 && test(t);
        });
        if (!titleEl) return;

        let card = titleEl.closest('.bi-card, .glass-card, .card, .chart-card');
        if (!card) {
          let p = titleEl.parentElement;
          while (p && p !== dash) {
            if (p.offsetHeight >= 140 && p.offsetWidth >= 240) { card = p; break; }
            p = p.parentElement;
          }
        }
        if (!card || card === dash) return;

        card.classList.add('eh-bi-quad-card', 'eh-bi-theme-' + type);

        const headRow = titleEl.closest('.eh-bi-hdr') || titleEl.parentElement;
        if (headRow && headRow !== card) {
          headRow.classList.add('eh-bi-hdr', 'eh-bi-hdr-' + type);
          if (!headRow.querySelector('.eh-bi-ico')) {
            const grp = document.createElement('div');
            grp.className = 'eh-bi-title-group';
            const ico = document.createElement('span');
            ico.className = 'eh-bi-ico';
            ico.innerHTML = ICONS[type];
            headRow.insertBefore(grp, titleEl);
            grp.appendChild(ico);
            grp.appendChild(titleEl);
          }
          const grpEl = headRow.querySelector('.eh-bi-title-group');
          Array.from(headRow.children).forEach(ch => {
            if (ch !== grpEl && (ch.textContent || '').trim().length > 2) {
              ch.classList.add('eh-bi-sub-pill');
            }
          });
        }

        if (type === 'donut') {
          const pctLeaf = Array.from(card.querySelectorAll('*')).find(n =>
            n.children.length === 0 && !n.closest('svg, .eh-bi-hdr') &&
            ((n.textContent || '').includes('%') || (n.textContent || '').includes('\u066a'))
          );
          if (pctLeaf) {
            let row = pctLeaf.parentElement;
            while (row && row.parentElement && row.parentElement !== card) {
              const sibs = Array.from(row.parentElement.children).filter(c => {
                const ct = c.textContent || '';
                return ct.includes('%') || ct.includes('\u066a');
              });
              if (sibs.length >= 3) {
                const list = row.parentElement;
                list.classList.add('eh-donut-scroll');
                Array.from(list.children).forEach(el => {
                  if (el.nodeType === 1) el.classList.add('eh-donut-item');
                });
                bindDonutCrossHighlight(card, list);
                break;
              }
              row = row.parentElement;
            }
          }
        }

        if (type === 'compare') {
          // 1. Find & hoist the color legend to the top (right below card header) with NO hover
          const legendEl = Array.from(card.querySelectorAll('div')).find(d => {
            const dt = (d.textContent || '').trim();
            return dt.includes('\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0645\u062e\u0627\u0637\u0628 \u0647\u0631 \u062f\u0648\u0631\u0647') && dt.includes('\u062a\u0639\u062f\u0627\u062f \u062f\u0648\u0631\u0647') && dt.length < 75;
          });
          if (legendEl) {
            legendEl.classList.remove('eh-cmp-item', 'eh-compare-legend-pad', 'eh-hover-row');
            legendEl.classList.add('eh-compare-legend-top');
            const hdr = card.querySelector('.eh-bi-hdr');
            if (hdr && legendEl.previousElementSibling !== hdr) {
              hdr.insertAdjacentElement('afterend', legendEl);
            }
          }

          // 2. Tag ONLY actual workgroup comparison cards (never the legend)
          const avgLeaf = Array.from(card.querySelectorAll('*')).find(n =>
            n.children.length === 0 && !n.closest('svg, .eh-bi-hdr, .eh-compare-legend-top') &&
            (n.textContent || '').includes('\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646') &&
            (n.textContent || '').includes('\u0646\u0641\u0631')
          );
          if (avgLeaf) {
            let item = avgLeaf.parentElement;
            while (item && item.parentElement && item.parentElement !== card) {
              const sibs = Array.from(item.parentElement.children).filter(c => {
                const ct = c.textContent || '';
                return !c.classList.contains('eh-compare-legend-top') && ct.includes('\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646') && ct.includes('\u0646\u0641\u0631');
              });
              if (sibs.length >= 2) {
                const list = item.parentElement;
                list.classList.add('eh-cmp-scroll');
                Array.from(list.children).forEach(el => {
                  if (el.nodeType === 1 && !el.classList.contains('eh-compare-legend-top')) {
                    const et = el.textContent || '';
                    if (et.includes('\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646') && et.includes('\u0646\u0641\u0631')) {
                      el.classList.add('eh-cmp-item');
                    }
                  }
                });
                break;
              }
              item = item.parentElement;
            }
          }
        }

        if (type === 'top' || type === 'teachers') {
          const nafarLeaf = Array.from(card.querySelectorAll('*')).find(n =>
            n.children.length === 0 && !n.closest('svg, .eh-bi-hdr') &&
            (n.textContent || '').includes('\u0646\u0641\u0631')
          );
          if (nafarLeaf) {
            let row = nafarLeaf.parentElement;
            while (row && row.parentElement && row.parentElement !== card) {
              const sibs = Array.from(row.parentElement.children).filter(c => (c.textContent || '').includes('\u0646\u0641\u0631'));
              if (sibs.length >= 2 || row.parentElement.children.length === 1) {
                if (row.parentElement.offsetHeight >= 70) {
                  const list = row.parentElement;
                  list.classList.add('eh-rank-scroll');
                  Array.from(list.children).forEach(el => {
                    if (el.nodeType === 1) {
                      el.classList.add('eh-rank-item');
                      if (el.dataset.ehRev !== '1') {
                        el.dataset.ehRev = '1';
                        el.classList.add('eh-soft-reveal');
                      }
                    }
                  });
                  shortenVerboseTeacherLeaves(list);
                  break;
                }
              }
              row = row.parentElement;
            }
          }
        }
      });

      // 3. Stable Smooth Count-Up on KPI Numbers
      triggerSmoothCountUps(dash);

      // 4. Restore Exact Scroll Anchor Synchronously
      restoreScrollAnchorNow();
    } finally {
      const dash = document.getElementById('page-dashboard');
      if (dash && dashObserver) {
        dashObserver.observe(dash, { childList: true, subtree: true });
      }
      isApplying = false;
    }
  }

  document.addEventListener('pointerdown', captureScrollAnchor, true);

  function bootV33() {
    const dash = document.getElementById('page-dashboard');
    if (dash && !dashObserver) {
      dashObserver = new MutationObserver(() => {
        applyAllDashboardV33();
      });
      dashObserver.observe(dash, { childList: true, subtree: true });
    }
    applyAllDashboardV33();
  }

  window.addEventListener('DOMContentLoaded', bootV33);
  window.addEventListener('pywebviewready', () => {
    bootV33();
    setTimeout(applyAllDashboardV33, 350);
    setTimeout(applyAllDashboardV33, 1000);
  });
})();
// _V33_0_FIX_END

// _V34_API_TEACHER_NORM_START
(() => {
  function normBiPayload(obj) {
    if (!obj || typeof obj !== 'object' || typeof window.formatTeacherShort !== 'function') return obj;
    const normList = (arr) => {
      if (!Array.isArray(arr)) return;
      arr.forEach(item => {
        if (!item || typeof item !== 'object') return;
        if (typeof item.teacher === 'string' && item.teacher.trim()) {
          item.teacher = window.formatTeacherShort(item.teacher);
        }
        if (typeof item.instructor === 'string' && item.instructor.trim()) {
          item.instructor = window.formatTeacherShort(item.instructor);
        }
      });
    };
    normList(obj.top_courses);
    normList(obj.courses);
    normList(obj.rows);

    // Merge duplicate teacher variants (e.g. "????? ?????????" + "?????? ????? ?????????") in dashboard top_teachers
    if (Array.isArray(obj.top_teachers) && obj.top_teachers.length) {
      const merged = new Map();
      obj.top_teachers.forEach(t => {
        if (!t || typeof t !== 'object') return;
        const rawName = t.teacher || t.name || '';
        const canon = window.formatTeacherShort(rawName);
        if (!merged.has(canon)) {
          const copy = { ...t };
          if ('teacher' in copy) copy.teacher = canon;
          if ('name' in copy) copy.name = canon;
          merged.set(canon, copy);
        } else {
          const ex = merged.get(canon);
          ['count', 'courses', 'course_count', 'participants', 'total_participants', 'attendance', 'total'].forEach(k => {
            if (typeof ex[k] === 'number' && typeof t[k] === 'number') ex[k] += t[k];
          });
        }
      });
      const sortKey = ['participants', 'total_participants', 'attendance', 'total'].find(k =>
        Array.from(merged.values()).some(v => typeof v[k] === 'number')
      );
      const out = Array.from(merged.values());
      if (sortKey) out.sort((a, b) => (b[sortKey] || 0) - (a[sortKey] || 0));
      obj.top_teachers = out;
    }
    return obj;
  }

  function wrapBiApi() {
    const api = window.pywebview?.api;
    if (!api || api._v34NormWrapped) return;
    api._v34NormWrapped = true;
    Object.keys(api).forEach(fnName => {
      if (!/bi|dashboard|course/i.test(fnName)) return;
      if (typeof api[fnName] !== 'function') return;
      const orig = api[fnName].bind(api);
      api[fnName] = async function () {
        const res = await orig.apply(this, arguments);
        if (res && typeof res === 'object') {
          normBiPayload(res);
          if (res.data && typeof res.data === 'object') normBiPayload(res.data);
          if (res.bi && typeof res.bi === 'object') normBiPayload(res.bi);
        }
        return res;
      };
    });
  }

  window.addEventListener('pywebviewready', wrapBiApi);
})();
// _V34_API_TEACHER_NORM_END



// _V36_EXPLORER_SMART_START
(() => {
  const ROW_ID_RX = /^(\u0631\u062f\u06cc\u0641|\u0634\u0645\u0627\u0631\u0647|id|no\.?|#|row|index)$/i;
  const GOOD_AXIS_RX = /(\u0646\u0627\u0645 \u062f\u0648\u0631\u0647|\u0639\u0646\u0648\u0627\u0646|\u062f\u0648\u0631\u0647|\u0627\u0633\u062a\u0627\u062f|\u06a9\u0627\u0631\u06af\u0631\u0648\u0647|\u0634\u0631\u062d|\u06a9\u0627\u0644\u0627|\u0645\u0648\u0636\u0648\u0639)/i;
  const GOOD_METRIC_RX = /(\u0634\u0631\u06a9\u062a|\u0645\u062e\u0627\u0637\u0628|\u062d\u0627\u0636\u0631|\u062a\u0639\u062f\u0627\u062f \u0646\u0641\u0631|\u0645\u0628\u0644\u063a|\u062c\u0645\u0639|\u0647\u0632\u06cc\u0646\u0647|\u0642\u06cc\u0645\u062a)/i;

  function cleanOptLabel(txt) {
    return String(txt || '').replace(/^(\u0645\u062d\u0648\u0631|\u0634\u0627\u062e\u0635)\s*:\s*/i, '').trim();
  }

  function autoFixExplorerDefaults() {
    const selects = Array.from(document.querySelectorAll('#page-dashboard select'));
    if (selects.length < 2) return;

    const axisSel = selects.find(s => Array.from(s.options).some(o => (o.textContent || '').includes('\u0645\u062d\u0648\u0631:')));
    const metricSel = selects.find(s => Array.from(s.options).some(o => (o.textContent || '').includes('\u0634\u0627\u062e\u0635:')));
    if (!axisSel || !metricSel) return;

    const sig = Array.from(axisSel.options).map(o => o.value).join('|') + '||' + Array.from(metricSel.options).map(o => o.value).join('|');
    if (axisSel.dataset.ehSmartSig === sig) return;
    axisSel.dataset.ehSmartSig = sig;

    let changed = false;

    // 1. If Axis defaulted to "????" / "id" / "?????", switch to a meaningful text column (e.g., ??? ???? / ??? ?????)
    const curAxisLbl = cleanOptLabel(axisSel.options[axisSel.selectedIndex]?.textContent);
    if (ROW_ID_RX.test(curAxisLbl)) {
      const opts = Array.from(axisSel.options);
      const bestAxis =
        opts.find(o => GOOD_AXIS_RX.test(cleanOptLabel(o.textContent))) ||
        opts.find(o => !ROW_ID_RX.test(cleanOptLabel(o.textContent)) && !GOOD_METRIC_RX.test(cleanOptLabel(o.textContent)));
      if (bestAxis && bestAxis.value !== axisSel.value) {
        axisSel.value = bestAxis.value;
        changed = true;
      }
    }

    // 2. If Metric defaulted to "????? ?????" or "????", switch to a real numeric column (e.g., ????? ???? ???????)
    const curMetricLbl = cleanOptLabel(metricSel.options[metricSel.selectedIndex]?.textContent);
    if (curMetricLbl.includes('\u062a\u0639\u062f\u0627\u062f \u0631\u06a9\u0648\u0631\u062f') || ROW_ID_RX.test(curMetricLbl)) {
      const mOpts = Array.from(metricSel.options);
      const bestMetric =
        mOpts.find(o => GOOD_METRIC_RX.test(cleanOptLabel(o.textContent))) ||
        mOpts.find(o => {
          const l = cleanOptLabel(o.textContent);
          return !l.includes('\u062a\u0639\u062f\u0627\u062f \u0631\u06a9\u0648\u0631\u062f') && !ROW_ID_RX.test(l);
        });
      if (bestMetric && bestMetric.value !== metricSel.value) {
        metricSel.value = bestMetric.value;
        changed = true;
      }
    }

    if (changed) {
      axisSel.dispatchEvent(new Event('change', { bubbles: true }));
      metricSel.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  let exTmr = null;
  const schedEx = () => {
    clearTimeout(exTmr);
    exTmr = setTimeout(autoFixExplorerDefaults, 120);
  };

  window.addEventListener('DOMContentLoaded', () => {
    const dash = document.getElementById('page-dashboard');
    if (dash) new MutationObserver(schedEx).observe(dash, { childList: true, subtree: true });
    schedEx();
  });
  window.addEventListener('pywebviewready', () => setTimeout(schedEx, 400));
})();
// _V36_EXPLORER_SMART_END

// _V37_UI_POLISH_START
(() => {
  // 1. Remove the unwanted green 4-square icon in the top-left titlebar cleanly
  function hideExtraTitlebarLogoIcon() {
    const tb = document.querySelector('.titlebar');
    if (!tb) return;

    // Any SVG or IMG inside titlebar that is NOT inside a window control button
    tb.querySelectorAll('svg, img').forEach(icEl => {
      if (icEl.closest('button')) return;
      icEl.classList.add('eh-tb-hidden-icon');
      const p = icEl.parentElement;
      if (
        p &&
        p !== tb &&
        !p.classList.contains('titlebar-left') &&
        !p.classList.contains('titlebar-title') &&
        !p.classList.contains('app-brand') &&
        !p.querySelector('.status-dot, .version-pill, .eh-tb-brand-text') &&
        (p.textContent || '').trim() === ''
      ) {
        p.classList.add('eh-tb-hidden-icon');
      }
    });

    // Also catch any pure-CSS decorative logo square (16px..32px, empty text, not .status-dot)
    tb.querySelectorAll('div, span').forEach(el => {
      if (el.closest('button') || el.classList.contains('status-dot') || el.classList.contains('eh-tb-hidden-icon')) return;
      if (el.querySelector('.status-dot, .version-pill, .eh-tb-brand-text, button')) return;
      if ((el.textContent || '').trim() !== '') return;
      const r = el.getBoundingClientRect();
      if (r.width >= 16 && r.width <= 34 && r.height >= 16 && r.height <= 34) {
        el.classList.add('eh-tb-hidden-icon');
      }
    });
  }

  // 2. Smart Dropdown Polish (Only narrows Dashboard workgroup bar; keeps form dropdowns full width; formats teacher options & prevents bottom clipping)
  function polishAllCustomDropdownsV37() {
    hideExtraTitlebarLogoIcon();

    const triggers = document.querySelectorAll('.eh-cselect-btn, [class*="cselect-btn"], [class*="select-trigger"]');
    triggers.forEach(btn => {
      const wrap = btn.closest('.eh-cselect, .eh-cselect-wrap, [class*="cselect"]') || btn.parentElement;
      if (!wrap) return;
      wrap.classList.add('eh-cselect-wrap');

      // Only narrow the Dashboard BI workgroup filter bar (NOT Events or Media Studio vertical form fields!)
      const inDash = Boolean(wrap.closest('#page-dashboard'));
      const btnTxt = (btn.textContent || '').trim();
      const isBiWorkgroup =
        inDash &&
        (btnTxt.includes('\u06a9\u0627\u0631\u06af\u0631\u0648\u0647') ||
          btnTxt.includes('\u062d\u062f\u06cc\u062b') ||
          btnTxt.includes('\u062a\u0627\u0631\u06cc\u062e') ||
          btnTxt.includes('\u0642\u0631\u0622\u0646') ||
          btnTxt.includes('\u0641\u0642\u0647') ||
          btnTxt.includes('\u0633\u062e\u0646\u0631\u0627\u0646') ||
          btnTxt.includes('\u062f\u06cc\u0646'));
      if (!wrap.classList.contains('eh-bi-cselect')) wrap.classList.toggle('eh-bi-wg-select', isBiWorkgroup);

      const parentCard = wrap.closest('.glass-card, .bi-card, .bi-toolbar, .bi-controls');
      if (parentCard && inDash) parentCard.classList.add('eh-has-dropdown-open');
    });

    const menus = new Set(document.querySelectorAll('.eh-cselect-menu, .eh-cselect-panel, .eh-cselect-dropdown, [class*="cselect-menu"], [class*="cselect-list"]'));
    document.querySelectorAll('div, ul').forEach(el => {
      if (el.children.length >= 4 && el.children.length <= 150) {
        const cs = getComputedStyle(el);
        if (cs.position === 'fixed' || cs.position === 'absolute') {
          const t = el.textContent || '';
          if (
            (t.includes('\u0647\u0645\u0647 \u06a9\u0627\u0631\u06af\u0631\u0648\u0647') && t.includes('\u06a9\u0627\u0631\u06af\u0631\u0648\u0647 \u0641\u0642\u0647')) ||
            (t.includes('\u0647\u0645\u0647 \u0627\u0633\u0627\u062a\u06cc\u062f') && (t.includes('\u062d\u062c\u062a') || t.includes('\u0627\u0633\u062a\u0627\u062f')))
          ) {
            menus.add(el);
          }
        }
      }
    });

    menus.forEach(menu => {
      menu.classList.add('eh-select-menu-fixed');
      const mTxt = menu.textContent || '';
      const isTeacherMenu = mTxt.includes('\u0647\u0645\u0647 \u0627\u0633\u0627\u062a\u06cc\u062f');

      // Normalize verbose teacher option labels cleanly (single-line ellipsis + full name tooltip) without changing option values
      Array.from(menu.children).forEach(opt => {
        if (opt.nodeType !== 1) return;
        const leaves = Array.from(opt.querySelectorAll('span, div')).filter(n => n.children.length === 0 && (n.textContent || '').trim().length > 1);
        const labelEl = leaves.find(n => (n.textContent || '').trim() !== '\u2713') || (opt.children.length === 0 ? opt : null);
        if (!labelEl) return;

        if (!labelEl.classList.contains('eh-dd-opt-text')) labelEl.classList.add('eh-dd-opt-text');
        const raw = (labelEl.textContent || '').trim();
        if (!opt.getAttribute('title') && raw.length > 2) opt.setAttribute('title', raw);

        if (isTeacherMenu && typeof window.formatTeacherShort === 'function' && labelEl.dataset.ehTeacherOptDone !== '1') {
          if (raw && !raw.includes('\u0647\u0645\u0647 \u0627\u0633\u0627\u062a\u06cc\u062f')) {
            labelEl.dataset.ehTeacherOptDone = '1';
            const cleaned = window.formatTeacherShort(raw);
            if (cleaned && cleaned !== raw) labelEl.textContent = cleaned;
          }
        }
      });

      // Keep menu inside viewport cleanly so bottom item is never clipped
      const mr = menu.getBoundingClientRect();
      if (mr.height > 0 && mr.width > 0) {
        if (mr.width > 350 && mTxt.includes('\u0647\u0645\u0647 \u06a9\u0627\u0631\u06af\u0631\u0648\u0647')) {
          if (getComputedStyle(menu).position === 'fixed') {
            const rightEdge = mr.right;
            menu.style.width = '285px';
            menu.style.left = Math.max(12, rightEdge - 285) + 'px';
            menu.style.right = 'auto';
          } else {
            menu.style.width = '285px';
            menu.style.right = '0';
            menu.style.left = 'auto';
          }
        }
        const avail = Math.max(200, window.innerHeight - mr.top - 22);
        if (mr.bottom > window.innerHeight - 16) {
          menu.style.maxHeight = avail + 'px';
        }
      }

      if (menu.dataset.ehScrollProtected === '1') return;
      menu.dataset.ehScrollProtected = '1';

      ['mousedown', 'pointerdown', 'click'].forEach(evName => {
        menu.addEventListener(evName, (e) => {
          if (e.target === menu) {
            e.stopPropagation();
          }
        }, false);
      });

      menu.addEventListener('wheel', (e) => {
        const scTarget = (menu.scrollHeight > menu.clientHeight + 2)
          ? menu
          : Array.from(menu.children).find(ch => ch.scrollHeight > ch.clientHeight + 2);
        if (scTarget) {
          scTarget.scrollTop += e.deltaY;
          e.preventDefault();
          e.stopPropagation();
        }
      }, { passive: false, capture: true });
    });
  }

  let tmr = null;
  const sched = () => {
    clearTimeout(tmr);
    tmr = setTimeout(polishAllCustomDropdownsV37, 25);
  };

  window.addEventListener('DOMContentLoaded', () => {
    sched();
    new MutationObserver(sched).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] });
  });
  window.addEventListener('pywebviewready', () => {
    sched();
    setTimeout(sched, 350);
    setTimeout(sched, 900);
  });
  document.addEventListener('click', sched, true);
})();
// _V37_UI_POLISH_END

// _V42_CHAT_MASTER_START
(() => {
  let chatObs = null;
  let busy = false;

  function locateChatDom() {
    const chatPage = document.getElementById('page-chat');
    if (!chatPage) return {};

    const inp =
      document.getElementById('chatInput') ||
      chatPage.querySelector('textarea, input[type="text"], input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])');

    let feed =
      document.getElementById('chatMessages') ||
      document.getElementById('chatHistory') ||
      document.getElementById('chatLog') ||
      document.getElementById('chatFeed') ||
      chatPage.querySelector('.chat-messages, .messages-container, .chat-feed, .chat-history, .chat-log');

    if (!feed && inp) {
      let p = inp.parentElement;
      while (p && p !== chatPage) {
        const sibs = Array.from(p.parentElement?.children || []).filter(ch => ch !== p && ch.nodeType === 1);
        const cand = sibs.find(ch => {
          const idc = ((ch.id || '') + ' ' + (ch.className || '')).toLowerCase();
          if (idc.includes('msg') || idc.includes('message') || idc.includes('feed') || idc.includes('history') || idc.includes('chat-body')) return true;
          const t = ch.textContent || '';
          return (t.includes('\u062f\u0633\u062a\u06cc\u0627\u0631') || t.includes('\u0634\u0645\u0627')) && !ch.querySelector('.prompt-chip');
        });
        if (cand) { feed = cand; break; }
        p = p.parentElement;
      }
    }
    return { chatPage, inp, feed };
  }

  function removeHeaderAndTuckControls(chatPage, feed, bottomZone, chipsRow) {
    // 1. Permanently hide the redundant .page-header box at top of #page-chat
    const hdr = chatPage.querySelector('.page-header');
    if (hdr) hdr.classList.add('eh-v42-gone');

    // 2. Relocate the 4 functional buttons (mode switches, clear, source preview) into a compact inline group beside the prompt chips
    if (chatPage.dataset.ehV42ToolsMoved === '1') return;

    const toolKeywords = [
      '\u062a\u062d\u0644\u06cc\u0644\u06af\u0631',
      '\u06af\u0632\u0627\u0631\u0634 \u0647\u06cc\u0626\u062a',
      '\u067e\u0627\u06a9\u0633\u0627\u0632\u06cc',
      '\u067e\u06cc\u0634\u200c\u0646\u0645\u0627\u06cc\u0634',
      '\u067e\u06cc\u0634 \u0646\u0645\u0627\u06cc\u0634'
    ];

    const toolBtns = Array.from(chatPage.querySelectorAll('button')).filter(b => {
      if ((feed && feed.contains(b)) || b.classList.contains('prompt-chip') || b.closest('.eh-v42-composer, .eh-v42-mini-tools, .eh-v48-chat-controls, .eh-v48-action-bar, .eh-v48-cite-drawer')) return false;
      const t = (b.textContent || '').trim();
      return toolKeywords.some(k => t.includes(k));
    });

    if (!toolBtns.length) return;
    chatPage.dataset.ehV42ToolsMoved = '1';

    const oldParents = new Set();
    toolBtns.forEach(b => {
      let p = b.parentElement;
      while (p && p !== chatPage && p !== hdr && !(feed && p.contains(feed))) {
        oldParents.add(p);
        p = p.parentElement;
      }
    });

    // Build single slim aux row containing prompt chips (right) + mini tools (left)
    const targetHost = bottomZone || feed?.parentElement;
    if (targetHost) {
      let auxRow = targetHost.querySelector('.eh-v42-aux-row');
      if (!auxRow) {
        auxRow = document.createElement('div');
        auxRow.className = 'eh-v42-aux-row';
        if (chipsRow && chipsRow.parentElement) {
          chipsRow.parentElement.insertBefore(auxRow, chipsRow);
          auxRow.appendChild(chipsRow);
        } else {
          targetHost.insertBefore(auxRow, targetHost.firstChild);
        }
      }
      let miniTools = auxRow.querySelector('.eh-v42-mini-tools');
      if (!miniTools) {
        miniTools = document.createElement('div');
        miniTools.className = 'eh-v42-mini-tools';
        auxRow.appendChild(miniTools);
      }
      toolBtns.forEach(b => miniTools.appendChild(b));
    }

    // Hide any leftover empty toolbar wrapper containers so ZERO vertical space is wasted at top
    oldParents.forEach(op => {
      if (op.contains(feed) || op.querySelector('input, textarea, .prompt-chip, .eh-v42-mini-tools, .eh-v48-chat-controls')) return;
      if ((op.textContent || '').trim() === '' || op.querySelectorAll('button').length === 0) {
        op.classList.add('eh-v42-gone');
      }
    });
  }

  function cleanTextNodesSafely(rootEl) {
    rootEl.querySelectorAll('code').forEach(cd => {
      if (/^tbl_[a-zA-Z0-9_]+$/.test((cd.textContent || '').trim())) cd.style.display = 'none';
    });

    const walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let n;
    while ((n = walker.nextNode())) {
      const p = n.parentElement;
      if (!p || p.closest('table, button, script, style, .eh-chat-h')) continue;
      if ((n.nodeValue || '').trim()) nodes.push(n);
    }

    nodes.forEach(node => {
      let val = node.nodeValue || '';
      let changed = false;

      if (val.includes('tbl_') || val.includes('\u0646\u0627\u0645 \u062c\u062f\u0648\u0644 \u067e\u0627\u06cc\u06af\u0627\u0647 \u062f\u0627\u062f\u0647')) {
        val = val
          .replace(/\s*\(\u0646\u0627\u0645 \u062c\u062f\u0648\u0644\s*\(SQL:\s*tbl_[a-zA-Z0-9_]+\)\)/g, '')
          .replace(/\s*\(SQL:\s*tbl_[a-zA-Z0-9_]+\)/g, '')
          .replace(/\s*\/\s*\u0646\u0627\u0645 \u062c\u062f\u0648\u0644 \u067e\u0627\u06cc\u06af\u0627\u0647 \u062f\u0627\u062f\u0647:\s*(?:tbl_[a-zA-Z0-9_]+)?/g, '')
          .replace(/\s*\(\u0646\u0627\u0645 \u062c\u062f\u0648\u0644:\s*tbl_[a-zA-Z0-9_]+\)/g, '')
          .replace(/tbl_[a-zA-Z0-9_]+/g, '')
          .trimEnd();
        changed = true;
      }

      if (val.includes('\u06a9\u0648\u0626\u0631\u06cc \u062f\u0642\u06cc\u0642 SQL')) {
        val = val.replaceAll('\u06a9\u0648\u0626\u0631\u06cc \u062f\u0642\u06cc\u0642 SQL', '\u062a\u062d\u0644\u06cc\u0644 \u062f\u0642\u06cc\u0642 \u0622\u0645\u0627\u0631\u06cc');
        changed = true;
      }
      if (val.includes('\u067e\u062e\u0634 \u0632\u0646\u062f\u0647 + SQL')) {
        val = '\u062a\u062d\u0644\u06cc\u0644 \u0632\u0646\u062f\u0647 \u0627\u0633\u0646\u0627\u062f \u0648 \u0622\u0645\u0627\u0631';
        changed = true;
      }
      if (val.includes('DuckDB') || val.includes('(SQL')) {
        val = '\u062a\u062d\u0644\u06cc\u0644 \u0622\u0645\u0627\u0631\u06cc \u0647\u0648\u0634\u0645\u0646\u062f';
        changed = true;
      }

      if (changed) node.nodeValue = val;

      if (/^\s*#{2,4}\s+/.test(val)) {
        const cleanTitle = val.replace(/^\s*#{2,4}\s+/, '').trim();
        if (cleanTitle && node.parentNode) {
          const hdrDiv = document.createElement('div');
          hdrDiv.className = 'eh-chat-h';
          hdrDiv.textContent = cleanTitle;
          const par = node.parentElement;
          if (par && (par.tagName === 'STRONG' || par.tagName === 'B') && par.childNodes.length === 1 && par.parentNode) {
            par.parentNode.replaceChild(hdrDiv, par);
          } else {
            node.parentNode.replaceChild(hdrDiv, node);
          }
        }
      }
    });
  }

  function applyChatV42() {
    if (busy) return;
    const { chatPage, inp, feed } = locateChatDom();
    if (!chatPage || !feed) return;

    busy = true;
    if (chatObs) chatObs.disconnect();

    try {
      // 1. Structure flex containers cleanly
      feed.classList.add('eh-v42-feed');

      const stage = feed.parentElement;
      if (stage && stage !== chatPage) {
        stage.classList.add('eh-v42-stage');
        stage.style.marginRight = '0';

        let anc = stage.parentElement;
        while (anc && anc !== chatPage) {
          const sibs = Array.from(anc.children).filter(c => c !== stage && !c.contains(stage) && c.nodeType === 1 && !c.classList.contains('eh-v42-gone'));
          if (sibs.length > 0 && anc.querySelector('[id*="preview"], [class*="preview"], [id*="source"], [class*="source"]')) {
            anc.classList.add('eh-v42-split');
            const anyVis = sibs.some(s => {
              const cs = getComputedStyle(s);
              return cs.display !== 'none' && cs.visibility !== 'hidden' && !s.classList.contains('hidden') && !s.classList.contains('collapsed') && s.offsetWidth > 30;
            });
            anc.classList.toggle('eh-no-preview', !anyVis);
            anc.classList.toggle('eh-has-preview', anyVis);
          } else {
            anc.classList.add('eh-v42-plain-wrap');
          }
          anc.style.paddingRight = '0';
          anc.style.marginRight = '0';
          anc = anc.parentElement;
        }
      }

      // 2. Tag composer & chips
      let bottomZone = null;
      if (inp) {
        const dock = inp.parentElement;
        if (dock && dock !== stage && dock !== chatPage) {
          dock.classList.add('eh-v42-composer');
          const btm = dock.parentElement;
          if (btm && btm !== stage && btm !== chatPage) {
            btm.classList.add('eh-v42-bottom');
            bottomZone = btm;
          }
        }
      }

      let chipsRow = null;
      const firstChip = chatPage.querySelector('.prompt-chip');
      if (firstChip && firstChip.parentElement && firstChip.parentElement !== stage) {
        chipsRow = firstChip.parentElement;
        chipsRow.classList.add('eh-v42-chips');
      }

      chatPage.querySelectorAll('.prompt-chip').forEach(ch => {
        if (ch.textContent.includes('SQL')) {
          ch.textContent = ch.textContent.replace(/\s*\(SQL\s*\+\s*\u0627\u06a9\u0633\u0644\)/g, '');
        }
      });

      // 3. Completely remove top header & tuck mode/clear buttons neatly into bottom aux row
      removeHeaderAndTuckControls(chatPage, feed, bottomZone, chipsRow);

      // 4. Polish message bubbles cleanly
      Array.from(feed.children).forEach(msg => {
        if (msg.nodeType !== 1) return;
        const cls = (msg.className || '').toLowerCase();
        const txt = msg.textContent || '';
        const isUser =
          cls.includes('user') ||
          cls.includes('human') ||
          cls.includes('self') ||
          (txt.includes('\u0634\u0645\u0627') && !txt.includes('\u062f\u0633\u062a\u06cc\u0627\u0631') && !msg.querySelector('table'));

        if (isUser) {
          msg.classList.add('eh-v42-user');
          msg.classList.remove('eh-v42-ai');
        } else {
          msg.classList.add('eh-v42-ai');
          msg.classList.remove('eh-v42-user');

          const metaTarget = Array.from(msg.querySelectorAll('div')).find(d => {
            if (d === msg || d.querySelector('table')) return false;
            const dt = d.textContent || '';
            const hasMeta =
              (dt.includes('\u062f\u0633\u062a\u06cc\u0627\u0631') && dt.length < 130) ||
              (d.querySelector('button') && (dt.includes('\u06a9\u067e\u06cc') || dt.includes('PDF')));
            return hasMeta && !d.parentElement?.classList.contains('eh-v42-ai-meta');
          });
          if (metaTarget) metaTarget.classList.add('eh-v42-ai-meta');
        }

        cleanTextNodesSafely(msg);

        msg.querySelectorAll('table').forEach(tbl => {
          if (!tbl.parentElement?.classList.contains('eh-chat-tbl-wrap')) {
            const wrap = document.createElement('div');
            wrap.className = 'eh-chat-tbl-wrap';
            tbl.parentNode.insertBefore(wrap, tbl);
            wrap.appendChild(tbl);
          }
        });
      });

      if (chatPage.classList.contains('active')) {
        const content = document.querySelector('main.content');
        if (content && content.scrollTop !== 0) content.scrollTop = 0;
      }
    } finally {
      if (chatObs) {
        chatObs.observe(chatPage, { attributes: true, attributeFilter: ['class', 'style'], childList: true, subtree: true });
      }
      busy = false;
    }
  }

  function hookZeroJumpSwitch() {
    if (typeof window.switchPage === 'function' && !window.switchPage._v42Hooked) {
      const orig = window.switchPage;
      const wrapped = function (pageId, btn) {
        const content = document.querySelector('main.content');
        const res = orig.apply(this, arguments);
        if (content) content.scrollTop = 0;
        if (String(pageId) === 'chat') applyChatV42();
        return res;
      };
      wrapped._v42Hooked = true;
      window.switchPage = wrapped;
    }
  }

  let rafPending = false;
  const scheduleV42 = () => {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      applyChatV42();
    });
  };

  function bootChatV42() {
    hookZeroJumpSwitch();
    const chatPage = document.getElementById('page-chat');
    if (chatPage && !chatObs) {
      chatObs = new MutationObserver(scheduleV42);
      chatObs.observe(chatPage, { attributes: true, attributeFilter: ['class', 'style'], childList: true, subtree: true });
    }
    applyChatV42();
  }

  window.addEventListener('DOMContentLoaded', bootChatV42);
  window.addEventListener('pywebviewready', () => {
    bootChatV42();
    setTimeout(applyChatV42, 300);
  });
})();
// _V42_CHAT_MASTER_END


// ================= eHadiPanel v48.0 Pro — Glassy Tooltips + Global Persian Digits =================
(() => {
  if (window.__EH_GLASS_TOOLTIP_V48) return;
  window.__EH_GLASS_TOOLTIP_V48 = true;

  // ---------- 1. SLEEK FROSTED-GLASS TOOLTIP ENGINE ----------
  let tipEl = null;
  let activeTarget = null;
  let showTimer = null;
  let lastHideTs = 0;

  function ensureTip() {
    if (tipEl && tipEl.isConnected) return tipEl;
    tipEl = document.createElement('div');
    tipEl.id = 'ehGlassTooltip';
    tipEl.className = 'eh-glass-tooltip';
    tipEl.setAttribute('role', 'tooltip');
    document.body.appendChild(tipEl);
    return tipEl;
  }

  function extractTip(el) {
    if (!el || el.nodeType !== 1) return '';
    // Move native HTML title to data-eh-tip so Windows never paints ugly default tooltips
    const nativeTitle = el.getAttribute('title');
    if (nativeTitle && nativeTitle.trim()) {
      el.setAttribute('data-eh-tip', nativeTitle.trim());
      if (!el.getAttribute('aria-label')) el.setAttribute('aria-label', nativeTitle.trim());
      el.removeAttribute('title');
    }
    // Move SVG <title> child to data-eh-tip on parent element
    if (el instanceof SVGElement) {
      const svgT = Array.from(el.children).find(c => c.tagName && c.tagName.toLowerCase() === 'title');
      if (svgT && svgT.textContent && svgT.textContent.trim()) {
        el.setAttribute('data-eh-tip', svgT.textContent.trim());
        svgT.remove();
      }
    }
    const tip = el.getAttribute('data-eh-tip') || el.getAttribute('data-tooltip') || '';
    if (!tip.trim()) return '';
    // Do not show redundant label tooltip on expanded sidebar nav items
    if (el.classList.contains('nav-btn') && !el.classList.contains('eh-diag-sb-btn') && !el.classList.contains('eh-mem-sb-btn') && el.closest('#sidebar') && !document.body.classList.contains('sidebar-collapsed')) {
      return '';
    }
    return tip.trim();
  }

  function findTipHost(startEl) {
    let cur = startEl;
    while (cur && cur !== document.body && cur !== document.documentElement) {
      if (cur.nodeType === 1) {
        const t = extractTip(cur);
        if (t) return { el: cur, text: t };
      }
      cur = cur.parentElement || cur.parentNode;
    }
    return null;
  }

  function positionTip(targetEl, tipNode) {
    const r = targetEl.getBoundingClientRect();
    const tw = tipNode.offsetWidth;
    const th = tipNode.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const margin = 10;

    let top, left, placement = 'top';
    const inCollapsedSb = Boolean(targetEl.closest('#sidebar') && document.body.classList.contains('sidebar-collapsed'));

    if (inCollapsedSb) {
      placement = 'left';
      left = r.left - tw - 10;
      top = r.top + (r.height - th) / 2;
      if (left < margin) {
        left = r.right + 10;
        placement = 'right';
      }
    } else {
      left = r.left + (r.width - tw) / 2;
      top = r.top - th - 9;
      if (top < margin) {
        top = r.bottom + 9;
        placement = 'bottom';
      }
    }

    left = Math.max(margin, Math.min(vw - tw - margin, left));
    top = Math.max(margin, Math.min(vh - th - margin, top));

    tipNode.dataset.pos = placement;
    tipNode.style.left = `${Math.round(left)}px`;
    tipNode.style.top = `${Math.round(top)}px`;
  }

  function showTip(targetEl, text) {
    const node = ensureTip();
    node.textContent = text;
    node.classList.remove('visible');
    node.style.display = 'block';
    positionTip(targetEl, node);
    requestAnimationFrame(() => {
      if (activeTarget === targetEl) node.classList.add('visible');
    });
  }

  function hideTip(immediate = false) {
    clearTimeout(showTimer);
    showTimer = null;
    activeTarget = null;
    if (!tipEl) return;
    tipEl.classList.remove('visible');
    lastHideTs = performance.now();
    if (immediate) tipEl.style.display = 'none';
  }

  // Strip native title attributes proactively so Chromium never flashes default tooltips
  function stripNativeTitles(root = document) {
    try {
      root.querySelectorAll('[title]').forEach(el => {
        const v = (el.getAttribute('title') || '').trim();
        if (v) {
          el.setAttribute('data-eh-tip', v);
          if (!el.getAttribute('aria-label')) el.setAttribute('aria-label', v);
        }
        el.removeAttribute('title');
      });
    } catch (_) {}
  }

  document.addEventListener('pointerover', (e) => {
    const hit = findTipHost(e.target);
    if (!hit) {
      if (activeTarget) hideTip();
      return;
    }
    if (activeTarget === hit.el) return;
    clearTimeout(showTimer);
    activeTarget = hit.el;
    const warm = (performance.now() - lastHideTs) < 350;
    showTimer = setTimeout(() => {
      if (activeTarget === hit.el && hit.el.isConnected) {
        showTip(hit.el, hit.text);
      }
    }, warm ? 75 : 220);
  }, true);

  document.addEventListener('pointerout', (e) => {
    if (!activeTarget) return;
    const rel = e.relatedTarget;
    if (rel && activeTarget.contains(rel)) return;
    hideTip();
  }, true);

  document.addEventListener('pointerdown', () => hideTip(true), true);
  document.addEventListener('wheel', () => hideTip(true), { capture: true, passive: true });
  window.addEventListener('scroll', () => hideTip(true), true);
  window.addEventListener('blur', () => hideTip(true));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideTip(true); });

  // ---------- 2. SMART GLOBAL PERSIAN DIGIT NORMALIZER ----------
  const FA_MAP = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'CODE', 'PRE', 'NOSCRIPT']);
  const SKIP_SEL = '.pro-kbd, .version-pill, .eh-modal-handle-pill, .eh-diag-err-txt, .eh-v48-no-fa-digits, [dir="ltr"]';

  function convertSafePersianDigits(str) {
    if (!/[0-9]/.test(str)) return str;
    // Split preserving whitespace; skip any token that contains ASCII letters, @, URLs, or Windows paths
    return str.replace(/\S+/g, (tok) => {
      if (!/[0-9]/.test(tok)) return tok;
      if (/[A-Za-z@\\]/.test(tok) || tok.includes('://')) return tok;
      return tok.replace(/[0-9]/g, d => FA_MAP[Number(d)]);
    });
  }

  let digitObs = null;
  let isNormalizing = false;

  function normalizeTextNode(node) {
    if (!node || node.nodeType !== 3) return;
    const val = node.nodeValue;
    if (!val || !/[0-9]/.test(val)) return;
    const p = node.parentElement;
    if (!p || SKIP_TAGS.has(p.tagName) || p.closest(SKIP_SEL)) return;
    const next = convertSafePersianDigits(val);
    if (next !== val) node.nodeValue = next;
  }

  function normalizeDigitsInSubtree(root = document.body) {
    if (!root || isNormalizing) return;
    isNormalizing = true;
    try {
      if (root.nodeType === 3) {
        normalizeTextNode(root);
      } else if (root.nodeType === 1) {
        stripNativeTitles(root);
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
          normalizeTextNode(node);
        }
      }
    } catch (_) {} finally {
      isNormalizing = false;
    }
  }

  function startDigitObserver() {
    if (!document.body || digitObs) return;
    normalizeDigitsInSubtree(document.body);
    digitObs = new MutationObserver((muts) => {
      if (isNormalizing) return;
      // Run SYNCHRONOUSLY inside microtask BEFORE browser paint -> ZERO English-to-Persian flash or jump!
      digitObs.disconnect();
      try {
        for (const m of muts) {
          const tgt = m.target;
          if (!tgt) continue;
          if (tgt.nodeType === 1 && (tgt.id === 'ehGlassTooltip' || tgt.closest?.('#ehGlassTooltip'))) continue;
          if (m.type === 'characterData') {
            normalizeTextNode(tgt);
          } else if (m.addedNodes && m.addedNodes.length) {
            m.addedNodes.forEach(n => {
              if (n.nodeType === 1 && (n.id === 'ehGlassTooltip' || n.classList?.contains('eh-click-wave'))) return;
              normalizeDigitsInSubtree(n);
            });
          }
        }
      } finally {
        digitObs.observe(document.body, { childList: true, subtree: true, characterData: true });
      }
    });
    digitObs.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  window.addEventListener('DOMContentLoaded', startDigitObserver);
  window.addEventListener('pywebviewready', () => {
    startDigitObserver();
    setTimeout(() => normalizeDigitsInSubtree(document.body), 250);
  });
})();


// ================= eHadiPanel v48.0 Pro — Unify Sidebar Footer Buttons with Native .nav-btn =================
(() => {
  if (window.__EH_SB_BTN_UNIFY_V488) return;
  window.__EH_SB_BTN_UNIFY_V488 = true;

  function unifyFooterBtns() {
    ['ehDiagSidebarBtn', 'ehMemSidebarBtn'].forEach(id => {
      const btn = document.getElementById(id);
      if (!btn) return;
      if (!btn.classList.contains('nav-btn')) btn.classList.add('nav-btn');
    });
  }

  function bootUnify() {
    unifyFooterBtns();
    const sb = document.querySelector('#sidebar, .sidebar');
    if (sb && !sb._ehFooterBtnObs) {
      sb._ehFooterBtnObs = new MutationObserver(unifyFooterBtns);
      sb._ehFooterBtnObs.observe(sb, { childList: true, subtree: true });
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    bootUnify();
    setTimeout(unifyFooterBtns, 250);
    setTimeout(unifyFooterBtns, 900);
  });
  window.addEventListener('pywebviewready', () => {
    bootUnify();
    setTimeout(unifyFooterBtns, 400);
  });
})();


// ================= eHadiPanel v48.0 Pro — Maximized Window 8-Edge Resize Cursor Guard =================
(() => {
  if (window.__EH_MAX_RESIZE_GUARD_V489) return;
  window.__EH_MAX_RESIZE_GUARD_V489 = true;

  let isMaxState = false;
  const RESIZE_CUR_RX = /(?:^|-)(?:n|s|e|w|ne|nw|se|sw|ew|ns|nesw|nwse|col|row)-resize$/i;

  function tagResizeHandles() {
    if (!document.body) return;
    // Tag explicit frameless resize edge/corner elements (direct body children or matching resize selectors)
    const candidates = new Set(document.querySelectorAll(
      '[data-resize], [data-resize-dir], [data-dir][class*="resize"], [class*="resize-handle"], [class*="win-resize"], [class*="edge-resize"], [class*="resizer"]'
    ));
    Array.from(document.body.children).forEach(el => {
      if (!el || el.nodeType !== 1 || el.id === 'ehGlassTooltip') return;
      if (el.classList.contains('eh-win-resize-edge')) return;
      try {
        const cs = getComputedStyle(el);
        if (cs.position === 'fixed' && RESIZE_CUR_RX.test((cs.cursor || '').trim())) {
          candidates.add(el);
        }
      } catch (_) {}
    });
    candidates.forEach(el => {
      el.classList.add('eh-win-resize-edge');
      if (isMaxState) {
        el.style.setProperty('pointer-events', 'none', 'important');
        el.style.setProperty('cursor', 'default', 'important');
      } else {
        el.style.removeProperty('pointer-events');
        el.style.removeProperty('cursor');
      }
    });
  }

  function clearInlineResizeCursor() {
    if (!isMaxState) return;
    [document.documentElement, document.body].forEach(node => {
      if (!node || !node.style) return;
      if (RESIZE_CUR_RX.test((node.style.cursor || '').trim())) {
        node.style.cursor = '';
      }
    });
  }

  function applyMaxState(val) {
    isMaxState = Boolean(val);
    document.body?.classList.toggle('eh-win-maximized', isMaxState);
    tagResizeHandles();
    if (isMaxState) clearInlineResizeCursor();
  }

  window.__ehSetMaximized = applyMaxState;

  async function probeMaximizedState() {
    try {
      const res = await window.pywebview?.api?.is_window_maximized?.();
      if (res && typeof res.maximized === 'boolean') {
        applyMaxState(res.maximized);
        return;
      }
    } catch (_) {}
    // Fallback heuristic if API unavailable
    const heur = (window.outerWidth >= (window.screen?.availWidth || 99999) - 4) &&
                 (window.outerHeight >= (window.screen?.availHeight || 99999) - 4);
    applyMaxState(heur);
  }

  // Intercept mousemove near edges while maximized so no JS resize handler overrides cursor
  window.addEventListener('mousemove', clearInlineResizeCursor, false);
  window.addEventListener('pointermove', clearInlineResizeCursor, false);
  window.addEventListener('resize', scheduleProbeMax);

  let resizeProbeTimer = null;
  function scheduleProbeMax() {
    clearTimeout(resizeProbeTimer);
    resizeProbeTimer = setTimeout(probeMaximizedState, 90);
  }

  // Also probe right after clicking maximize button or double-clicking titlebar
  document.addEventListener('click', (e) => {
    const btn = e.target?.closest?.('.win-btn');
    if (btn && (btn.getAttribute('onclick') || '').includes('max')) {
      setTimeout(probeMaximizedState, 120);
      setTimeout(probeMaximizedState, 360);
    }
  }, true);
  document.addEventListener('dblclick', (e) => {
    if (e.target?.closest?.('.titlebar') && !e.target?.closest?.('button, input, a')) {
      setTimeout(probeMaximizedState, 120);
      setTimeout(probeMaximizedState, 360);
    }
  }, true);

  window.addEventListener('DOMContentLoaded', () => {
    tagResizeHandles();
    scheduleProbeMax();
  });
  window.addEventListener('pywebviewready', () => {
    tagResizeHandles();
    probeMaximizedState();
    setTimeout(() => { tagResizeHandles(); probeMaximizedState(); }, 450);
  });
})();


// ================= Pure-CSS Smooth Open/Close Lifecycle for Diagnostics & Memory Modals =================
(() => {
  if (window.__EH_MODAL_PURE_CSS_V500) return;
  window.__EH_MODAL_PURE_CSS_V500 = true;

  const closeTimers = new WeakMap();

  function cancelPendingClose(bd) {
    if (!bd) return;
    const t = closeTimers.get(bd);
    if (t) {
      clearTimeout(t);
      closeTimers.delete(bd);
    }
    bd.classList.remove('eh-closing');
    bd.style.removeProperty('display');
    bd.style.removeProperty('opacity');
    bd.style.removeProperty('pointer-events');
  }

  function smoothHideBackdrop(bd) {
    if (!bd || !bd.classList?.contains('open') || bd.classList.contains('eh-closing')) return;
    bd.classList.add('eh-closing');
    const timer = setTimeout(() => {
      closeTimers.delete(bd);
      bd.classList.remove('open', 'eh-closing');
      bd.style.removeProperty('display');
    }, 185);
    closeTimers.set(bd, timer);
  }

  // Before sidebar footer buttons trigger openDiagnosticsModal / openMemoryModal, clear any closing state
  document.addEventListener('pointerdown', (e) => {
    const btn = e.target?.closest?.('#ehDiagSidebarBtn, #ehMemSidebarBtn, [onclick*="openDiagnosticsModal"], [onclick*="openMemoryModal"]');
    if (!btn) return;
    document.querySelectorAll('.eh-diag-backdrop').forEach(cancelPendingClose);
  }, true);

  // Intercept close button / backdrop click for smooth fade-out without ever breaking next open
  document.addEventListener('click', (e) => {
    const bd = e.target?.closest?.('.eh-diag-backdrop');
    if (!bd) return;
    if (e.target === bd || e.target.closest?.('.eh-diag-close, [data-close-modal], .eh-mem-close')) {
      e.preventDefault();
      e.stopImmediatePropagation();
      smoothHideBackdrop(bd);
    }
  }, true);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.eh-diag-backdrop.open:not(.eh-closing)').forEach(smoothHideBackdrop);
    }
  }, true);
})();

