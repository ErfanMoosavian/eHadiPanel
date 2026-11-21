(() => {
  const errQueue = [];
  let recentSent = [];
  let lastHealth = null;
  let modalOpen = false;

  function activePageId() {
    const p = document.querySelector('.page.active');
    return p ? (p.id || 'unknown') : 'boot';
  }

  function pushFrontendError(payload) {
    try {
      const now = Date.now();
      recentSent = recentSent.filter(ts => now - ts < 60000);
      if (recentSent.length >= 25) return; // anti-flood guard
      recentSent.push(now);

      const enriched = {
        type: payload.type || 'js_error',
        page: activePageId(),
        message: String(payload.message || '').slice(0, 700),
        source: String(payload.source || '').slice(0, 180),
        line: payload.line || '',
        stack: String(payload.stack || '').slice(0, 1000)
      };

      const api = window.pywebview?.api;
      if (api && typeof api.log_frontend_error === 'function') {
        api.log_frontend_error(enriched).catch(() => {});
      } else {
        errQueue.push(enriched);
        if (errQueue.length > 30) errQueue.shift();
      }
    } catch (_) {}
  }

  function flushErrorQueue() {
    const api = window.pywebview?.api;
    if (!api || typeof api.log_frontend_error !== 'function') return;
    while (errQueue.length) {
      const item = errQueue.shift();
      api.log_frontend_error(item).catch(() => {});
    }
  }

  // Global JS error listeners
  window.addEventListener('error', (ev) => {
    pushFrontendError({
      type: 'window.onerror',
      message: ev.message || 'Script Error',
      source: ev.filename || '',
      line: ev.lineno || '',
      stack: ev.error?.stack || ''
    });
  });

  window.addEventListener('unhandledrejection', (ev) => {
    const r = ev.reason;
    pushFrontendError({
      type: 'unhandledrejection',
      message: r?.message || String(r || 'Promise rejection'),
      stack: r?.stack || ''
    });
  });

  // Non-invasive console.error hook
  const origConsoleError = console.error.bind(console);
  console.error = function (...args) {
    origConsoleError(...args);
    try {
      const msg = args.map(a => (a instanceof Error ? a.message : (typeof a === 'object' ? JSON.stringify(a) : String(a)))).join(' ');
      if (msg && !msg.includes('log_frontend_error')) {
        pushFrontendError({ type: 'console.error', message: msg });
      }
    } catch (_) {}
  };

  function statusLabel(st) {
    if (st === 'healthy') return 'سالم';
    if (st === 'warning') return 'هشدار';
    return 'خطا';
  }

  function renderCheckItems(checks) {
    if (!Array.isArray(checks) || !checks.length) {
      return '<div class="eh-diag-empty">در حال بررسی زیرسیستم‌ها...</div>';
    }
    return checks.map(c => `
      <div class="eh-diag-row eh-diag-st-${c.status}">
        <div class="eh-diag-row-main">
          <div class="eh-diag-row-title">${c.title || ''}</div>
          <div class="eh-diag-row-detail">${c.detail || ''}</div>
        </div>
        <span class="eh-diag-badge eh-diag-badge-${c.status}">${statusLabel(c.status)}</span>
      </div>
    `).join('');
  }

  function showDiagNotice(text, kind = 'info') {
    let box = document.getElementById('ehDiagNotice');
    if (!box) {
      box = document.createElement('div');
      box.id = 'ehDiagNotice';
      box.className = 'eh-diag-toast';
      document.body.appendChild(box);
    }
    box.className = `eh-diag-toast eh-diag-toast-${kind} show`;
    box.textContent = text;
    clearTimeout(box._tmr);
    box._tmr = setTimeout(() => box.classList.remove('show'), 5200);
  }

  async function doExportBundle(btnEl) {
    const api = window.pywebview?.api;
    if (!api || typeof api.export_diagnostic_bundle !== 'function') {
      showDiagNotice('رابط پشتیبانی هنوز آماده نیست؛ چند لحظه بعد دوباره امتحان کنید.', 'warning');
      return;
    }
    const origTxt = btnEl ? btnEl.textContent : '';
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.textContent = 'در حال ساخت بسته گزارش...';
    }
    try {
      const res = await api.export_diagnostic_bundle();
      if (res && res.ok) {
        showDiagNotice(`بسته گزارش خطا ساخته شد (${res.filename} - ${res.size_kb} KB) و پوشه آن باز شد.`, 'healthy');
      } else {
        showDiagNotice(`خطا در ساخت گزارش: ${res?.error || 'نامشخص'}`, 'error');
      }
    } catch (e) {
      showDiagNotice(`خطا در ساخت گزارش: ${e.message || e}`, 'error');
    } finally {
      if (btnEl) {
        btnEl.disabled = false;
        btnEl.textContent = origTxt;
      }
    }
  }

  async function runCheck(checkNetwork = false, silent = false) {
    const api = window.pywebview?.api;
    if (!api || typeof api.run_health_check !== 'function') return null;
    try {
      const res = await api.run_health_check(Boolean(checkNetwork));
      if (res && res.ok) {
        lastHealth = res;
        updateHealthIndicators(res);
        if (!silent) {
          showDiagNotice(res.summary || 'بررسی سلامت انجام شد.', res.status);
        } else if (res.status === 'error') {
          showDiagNotice('هشدار سلامت سامانه: خطایی در بررسی اولیه شناسایی شد. روی «سلامت سامانه» کلیک کنید.', 'error');
        }
      }
      return res;
    } catch (e) {
      const mSum = document.getElementById('ehDiagModalSummary');
      if (mSum) {
        mSum.className = 'eh-diag-summary eh-diag-st-error';
        mSum.textContent = `خطا در بررسی سلامت: ${e?.message || e}`;
      }
      if (!silent) showDiagNotice('خطا در اجرای تست سلامت.', 'error');
      return null;
    }
  }

  async function loadRecentErrorsInto(container) {
    const api = window.pywebview?.api;
    if (!container || !api || typeof api.get_recent_errors !== 'function') return;
    try {
      const res = await api.get_recent_errors(10);
      if (!res || !res.ok || !res.items?.length) {
        container.innerHTML = '<div class="eh-diag-empty">هیچ خطایی ثبت نشده است.</div>';
        return;
      }
      container.innerHTML = res.items.map(it => `
        <div class="eh-diag-err-line">
          <span class="eh-diag-err-src">${it.source}</span>
          <span class="eh-diag-err-txt">${it.text.replace(/</g, '&lt;')}</span>
        </div>
      `).join('');
    } catch (_) {}
  }

  function updateHealthIndicators(res) {
    // 1. Sidebar compact button
    const sbBtn = document.getElementById('ehDiagSidebarBtn');
    if (sbBtn && res) {
      sbBtn.dataset.status = res.status;
      const lbl = sbBtn.querySelector('.eh-diag-sb-lbl');
      if (lbl) {
        lbl.textContent = res.status === 'healthy' ? 'سلامت سامانه: پایدار' : (res.status === 'warning' ? 'سلامت سامانه: هشدار' : 'سلامت سامانه: خطا');
      }
    }
    // 2. Modal list
    const mList = document.getElementById('ehDiagModalList');
    const mSum = document.getElementById('ehDiagModalSummary');
    if (mList && res) mList.innerHTML = renderCheckItems(res.checks);
    if (mSum && res) {
      mSum.className = `eh-diag-summary eh-diag-st-${res.status}`;
      mSum.textContent = `${res.summary} (${res.timestamp})`;
    }
    // 3. Settings page card list
    const sList = document.getElementById('ehDiagSettingsList');
    if (sList && res) sList.innerHTML = renderCheckItems(res.checks);
  }

  function ensureDiagnosticsModal() {
    let modal = document.getElementById('ehDiagModal');
    if (modal) return modal;

    modal = document.createElement('div');
    modal.id = 'ehDiagModal';
    modal.className = 'eh-diag-backdrop';
    modal.innerHTML = `
      <div class="eh-diag-modal" role="dialog" aria-modal="true">
        <div class="eh-diag-modal-hdr">
          <div class="eh-diag-modal-title">
            <span class="eh-diag-modal-ico">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
            </span>
            <div>
              <h3>مرکز سلامت سامانه و گزارش خطا (پشتیبانی)</h3>
              <p>پایش خودکار پایگاه‌داده و تهیه فایل تشخیصی بدون اطلاعات محرمانه</p>
            </div>
          </div>
          <button type="button" class="eh-diag-close" id="ehDiagCloseBtn" title="بستن">✕</button>
        </div>

        <div id="ehDiagModalSummary" class="eh-diag-summary">در حال آماده‌سازی گزارش سلامت...</div>
        <div id="ehDiagModalList" class="eh-diag-list"></div>

        <details class="eh-diag-err-details" id="ehDiagErrDetails">
          <summary>مشاهده ۱۰ خطای فنی اخیر (پایتون و رابط کاربری)</summary>
          <div id="ehDiagErrList" class="eh-diag-err-list"></div>
        </details>

        <div class="eh-diag-privacy">
          حریم خصوصی: فایل گزارش خطا شامل هیچ متن سند، فایل اکسل، ردیف آماری یا کلید API نیست.
        </div>

        <div class="eh-diag-actions">
          <button type="button" class="eh-diag-btn-primary" id="ehDiagExportBtn">ساخت فایل گزارش خطا (.zip)</button>
          <button type="button" class="eh-diag-btn-sec" id="ehDiagRecheckBtn">اجرای تست سلامت کامل (با شبکه)</button>
          <button type="button" class="eh-diag-btn-sec" id="ehDiagClearErrBtn">پاکسازی لاگ خطاها</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeDiagnosticsModal();
    });
    modal.querySelector('#ehDiagCloseBtn').addEventListener('click', closeDiagnosticsModal);
    modal.querySelector('#ehDiagExportBtn').addEventListener('click', (e) => doExportBundle(e.currentTarget));
    modal.querySelector('#ehDiagRecheckBtn').addEventListener('click', async (e) => {
      const b = e.currentTarget;
      b.disabled = true;
      b.textContent = 'در حال بررسی کامل...';
      await runCheck(true, false);
      await loadRecentErrorsInto(document.getElementById('ehDiagErrList'));
      b.disabled = false;
      b.textContent = 'اجرای تست سلامت کامل (با شبکه)';
    });
    modal.querySelector('#ehDiagClearErrBtn').addEventListener('click', async (e) => {
      const b = e.currentTarget;
      const api = window.pywebview?.api;
      if (!api || typeof api.clear_error_logs !== 'function') return;
      b.disabled = true;
      await api.clear_error_logs();
      await runCheck(false, true);
      await loadRecentErrorsInto(document.getElementById('ehDiagErrList'));
      showDiagNotice('تاریخچه خطاهای قبلی پاکسازی شد.', 'healthy');
      b.disabled = false;
    });
    modal.querySelector('#ehDiagErrDetails').addEventListener('toggle', (e) => {
      if (e.target.open) loadRecentErrorsInto(document.getElementById('ehDiagErrList'));
    });

    return modal;
  }

  function openDiagnosticsModal() {
    const modal = ensureDiagnosticsModal();
    modal.classList.add('open');
    modalOpen = true;
    if (lastHealth) {
      updateHealthIndicators(lastHealth);
    }
    runCheck(false, true);
  }

  function closeDiagnosticsModal() {
    const modal = document.getElementById('ehDiagModal');
    if (modal) modal.classList.remove('open');
    modalOpen = false;
  }

  function mountSidebarHealthTrigger() {
    if (document.getElementById('ehDiagSidebarBtn')) return;
    const sidebar = document.querySelector('.sidebar, aside');
    if (!sidebar) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'ehDiagSidebarBtn';
    btn.className = 'eh-diag-sb-btn';
    btn.dataset.status = 'healthy';
    btn.title = 'بررسی سلامت سامانه و ساخت فایل گزارش خطا (Ctrl+Shift+D)';
    btn.innerHTML = `<span class="eh-diag-sb-dot"></span><span class="eh-diag-sb-lbl">سلامت سامانه و پشتیبانی</span>`;
    btn.addEventListener('click', openDiagnosticsModal);

    const footer = sidebar.querySelector('.sidebar-footer, .sb-footer');
    if (footer) {
      footer.insertBefore(btn, footer.firstChild);
    } else {
      sidebar.appendChild(btn);
    }
  }

  function mountSettingsSupportCard() {
    const settingsPage = document.getElementById('page-settings');
    if (!settingsPage || document.getElementById('ehDiagSettingsCard')) return;

    const card = document.createElement('div');
    card.id = 'ehDiagSettingsCard';
    card.className = 'glass-card eh-diag-settings-card';
    card.innerHTML = `
      <div class="eh-diag-set-hdr">
        <div>
          <h3>سلامت سامانه و ارسال گزارش خطا به پشتیبانی</h3>
          <p>در صورت بروز هرگونه خطا یا کندی، فایل گزارش فنی را تولید کرده و برای پشتیبانی ارسال کنید.</p>
        </div>
        <div class="eh-diag-set-btns">
          <button type="button" class="eh-diag-btn-sec" id="ehDiagSetCheckBtn">تست سلامت کامل</button>
          <button type="button" class="eh-diag-btn-primary" id="ehDiagSetExportBtn">ساخت فایل گزارش خطا (.zip)</button>
        </div>
      </div>
      <div id="ehDiagSettingsList" class="eh-diag-list"></div>
    `;
    settingsPage.appendChild(card);

    card.querySelector('#ehDiagSetExportBtn').addEventListener('click', (e) => doExportBundle(e.currentTarget));
    card.querySelector('#ehDiagSetCheckBtn').addEventListener('click', async (e) => {
      const b = e.currentTarget;
      b.disabled = true;
      b.textContent = 'در حال بررسی...';
      await runCheck(true, false);
      b.disabled = false;
      b.textContent = 'تست سلامت کامل';
    });

    if (lastHealth) updateHealthIndicators(lastHealth);
  }

  // Shortcut Ctrl+Shift+D to open Diagnostics Modal from anywhere
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && (e.key === 'D' || e.key === 'd')) {
      e.preventDefault();
      if (modalOpen) closeDiagnosticsModal();
      else openDiagnosticsModal();
    } else if (e.key === 'Escape' && modalOpen) {
      closeDiagnosticsModal();
    }
  });

  window.openDiagnosticsModal = openDiagnosticsModal;

  window.addEventListener('DOMContentLoaded', () => {
    mountSidebarHealthTrigger();
    mountSettingsSupportCard();
  });

  window.addEventListener('pywebviewready', () => {
    mountSidebarHealthTrigger();
    mountSettingsSupportCard();
    flushErrorQueue();
    setTimeout(() => runCheck(false, true), 1200);
  });
})();
