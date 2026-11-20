(() => {
  let memState = { rules: [], aliases: [], pending: [], pending_count: 0 };
  let activeTab = 'pending';
  let modalOpen = false;

  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toast(msg, kind = 'info') {
    let box = document.getElementById('ehDiagNotice');
    if (!box) {
      box = document.createElement('div');
      box.id = 'ehDiagNotice';
      box.className = 'eh-diag-toast';
      document.body.appendChild(box);
    }
    box.className = `eh-diag-toast eh-diag-toast-${kind} show`;
    box.textContent = msg;
    clearTimeout(box._tmr);
    box._tmr = setTimeout(() => box.classList.remove('show'), 4500);
  }

  async function refreshMemoryState() {
    const api = window.pywebview?.api;
    if (!api || typeof api.get_memory_state !== 'function') return;
    try {
      const res = await api.get_memory_state();
      if (res && res.ok) {
        memState = res;
        updateSidebarBadge();
        if (modalOpen) renderModalBody();
      }
    } catch (_) {}
  }

  function updateSidebarBadge() {
    const badge = document.getElementById('ehMemPendingBadge');
    if (!badge) return;
    const cnt = memState.pending_count || 0;
    badge.textContent = cnt > 0 ? String(cnt) : '';
    badge.style.display = cnt > 0 ? 'inline-flex' : 'none';
  }

  function renderModalBody() {
    const body = document.getElementById('ehMemTabBody');
    const cPend = document.getElementById('ehMemCntPending');
    const cRules = document.getElementById('ehMemCntRules');
    const cAlias = document.getElementById('ehMemCntAliases');
    if (cPend) cPend.textContent = String((memState.pending || []).length);
    if (cRules) cRules.textContent = String((memState.rules || []).length);
    if (cAlias) cAlias.textContent = String((memState.aliases || []).length);
    if (!body) return;

    if (activeTab === 'pending') {
      const items = memState.pending || [];
      if (!items.length) {
        body.innerHTML = `
          <div class="eh-mem-empty-box">
            <strong>مورد مشکوکی در داده‌های فعلی یافت نشد.</strong>
            <p>با ورود فایل‌های اکسل یا فاکتور جدید، سامانه به‌صورت خودکار نام‌های مشابه را شناسایی کرده و اینجا برای تأیید شما نمایش می‌دهد.</p>
          </div>`;
        return;
      }
      body.innerHTML = items.map((it, idx) => `
        <div class="eh-mem-pair-card" data-idx="${idx}">
          <div class="eh-mem-pair-top">
            <span class="eh-mem-type-pill">${escHtml(it.entity_label)}</span>
            <span class="eh-mem-conf-pill">شباهت ${it.confidence}٪</span>
          </div>
          <div class="eh-mem-pair-names">
            <div class="eh-mem-chip-val">«${escHtml(it.item_a)}» <small>(${it.count_a} مورد)</small></div>
            <span class="eh-mem-vs">≈</span>
            <div class="eh-mem-chip-val">«${escHtml(it.item_b)}» <small>(${it.count_b} مورد)</small></div>
          </div>
          ${it.caution ? `<div class="eh-mem-caution">${escHtml(it.caution)}</div>` : ""}
          <div class="eh-mem-pair-edit">
            <label>نام معیار نهایی پس از ادغام:</label>
            <input type="text" class="eh-mem-canon-inp" value="${escHtml(it.suggested_canonical)}" />
          </div>
          <div class="eh-mem-pair-btns">
            <button type="button" class="eh-diag-btn-primary eh-mem-approve-btn">ادغام کن و به خاطر بسپار</button>
            <button type="button" class="eh-diag-btn-sec eh-mem-reject-btn">دو مورد جدا هستند</button>
          </div>
        </div>
      `).join('');

      body.querySelectorAll('.eh-mem-pair-card').forEach(card => {
        const idx = Number(card.dataset.idx);
        const it = items[idx];
        card.querySelector('.eh-mem-approve-btn').addEventListener('click', async (e) => {
          const canon = (card.querySelector('.eh-mem-canon-inp').value || '').trim() || it.suggested_canonical;
          const aliasVal = (canon === it.item_a) ? it.item_b : it.item_a;
          e.currentTarget.disabled = true;
          await window.pywebview.api.resolve_fuzzy_pair(canon, aliasVal, it.entity_type, 'approved', it.confidence / 100);
          toast(`تطبیق «${aliasVal}» به «${canon}» در حافظه دائمی ذخیره شد.`, 'healthy');
          await refreshMemoryState();
        });
        card.querySelector('.eh-mem-reject-btn').addEventListener('click', async (e) => {
          e.currentTarget.disabled = true;
          await window.pywebview.api.resolve_fuzzy_pair(it.item_a, it.item_b, it.entity_type, 'rejected', it.confidence / 100);
          toast('ثبت شد: این دو مورد جدا هستند و دیگر پرسیده نمی‌شوند.', 'info');
          await refreshMemoryState();
        });
      });
      return;
    }

    if (activeTab === 'rules') {
      const rules = memState.rules || [];
      const listHtml = rules.length
        ? rules.map(r => `
            <div class="eh-mem-rule-row">
              <div class="eh-mem-rule-txt">
                <span class="eh-mem-type-pill">${escHtml(r.scope)}</span>
                <span>${escHtml(r.rule_text)}</span>
              </div>
              <button type="button" class="eh-mem-del-btn" data-id="${r.id}" title="حذف قانون">حذف</button>
            </div>
          `).join('')
        : '<div class="eh-mem-empty-box"><p>هنوز قانون دائمی ثبت نشده است. هم از اینجا و هم مستقیم داخل چت می‌توانید قانون جدید به هوش مصنوعی یاد بدهید.</p></div>';

      body.innerHTML = `
        <div class="eh-mem-add-form">
          <input type="text" id="ehMemNewRuleInp" placeholder="مثلاً: فاکتورهای چاپ بنر و پوستر را در دسته تبلیغات حساب کن..." />
          <button type="button" class="eh-diag-btn-primary" id="ehMemAddRuleBtn">ثبت قانون دائمی</button>
        </div>
        <div class="eh-mem-list-stack">${listHtml}</div>
      `;

      body.querySelector('#ehMemAddRuleBtn').addEventListener('click', async () => {
        const inp = body.querySelector('#ehMemNewRuleInp');
        const txt = (inp.value || '').trim();
        if (txt.length < 4) { toast('لطفاً متن قانون را کامل‌تر بنویسید.', 'warning'); return; }
        const res = await window.pywebview.api.add_user_rule(txt, 'عمومی');
        if (res && res.ok) {
          inp.value = '';
          toast('قانون جدید در حافظه دائمی هوش مصنوعی ذخیره شد.', 'healthy');
          await refreshMemoryState();
        }
      });

      body.querySelectorAll('.eh-mem-del-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          await window.pywebview.api.delete_user_rule(Number(btn.dataset.id));
          toast('قانون حذف شد.', 'info');
          await refreshMemoryState();
        });
      });
      return;
    }

    if (activeTab === 'aliases') {
      const aliases = memState.aliases || [];
      const listHtml = aliases.length
        ? aliases.map(a => `
            <div class="eh-mem-rule-row">
              <div class="eh-mem-rule-txt">
                <span class="eh-mem-type-pill">${escHtml(a.entity_type)}</span>
                <span>«${escHtml(a.alias_name)}» <strong>←</strong> «${escHtml(a.canonical_name)}»</span>
              </div>
              <button type="button" class="eh-mem-del-btn" data-id="${a.id}">حذف</button>
            </div>
          `).join('')
        : '<div class="eh-mem-empty-box"><p>هنوز نام معادلی ثبت نشده است.</p></div>';

      body.innerHTML = `
        <div class="eh-mem-add-form eh-mem-alias-form">
          <input type="text" id="ehMemAliasFrom" placeholder="نام فرعی / املای نامرتب (مثلاً: س.ر. هاشمی)" />
          <input type="text" id="ehMemAliasTo" placeholder="نام معیار (مثلاً: استاد هاشمی گلپایگانی)" />
          <button type="button" class="eh-diag-btn-primary" id="ehMemAddAliasBtn">ذخیره معادل</button>
        </div>
        <div class="eh-mem-list-stack">${listHtml}</div>
      `;

      body.querySelector('#ehMemAddAliasBtn').addEventListener('click', async () => {
        const fromV = (body.querySelector('#ehMemAliasFrom').value || '').trim();
        const toV = (body.querySelector('#ehMemAliasTo').value || '').trim();
        if (!fromV || !toV) { toast('هر دو فیلد را پر کنید.', 'warning'); return; }
        const res = await window.pywebview.api.resolve_fuzzy_pair(toV, fromV, 'teacher', 'approved', 1.0);
        if (res && res.ok) {
          toast('تطبیق نام در حافظه دائمی ثبت شد.', 'healthy');
          await refreshMemoryState();
        }
      });

      body.querySelectorAll('.eh-mem-del-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          await window.pywebview.api.delete_entity_alias(Number(btn.dataset.id));
          toast('تطبیق حذف شد.', 'info');
          await refreshMemoryState();
        });
      });
    }
  }

  function ensureMemoryModal() {
    let modal = document.getElementById('ehMemModal');
    if (modal) return modal;

    modal = document.createElement('div');
    modal.id = 'ehMemModal';
    modal.className = 'eh-diag-backdrop';
    modal.innerHTML = `
      <div class="eh-diag-modal eh-mem-modal" role="dialog" aria-modal="true">
        <div class="eh-diag-modal-hdr">
          <div class="eh-diag-modal-title">
            <span class="eh-diag-modal-ico">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            </span>
            <div>
              <h3>حافظه قوانین و تطبیق هوشمند داده‌ها</h3>
              <p>تشخیص موارد مشابه در فایل‌های نامرتب و آموزش قوانین دائمی به دستیار هوشمند</p>
            </div>
          </div>
          <button type="button" class="eh-diag-close" id="ehMemCloseBtn" title="بستن">✕</button>
        </div>

        <div class="eh-mem-tabs">
          <button type="button" class="eh-mem-tab active" data-tab="pending">نیاز به تأیید شما <span class="eh-mem-tab-cnt" id="ehMemCntPending">0</span></button>
          <button type="button" class="eh-mem-tab" data-tab="rules">قوانین دائمی <span class="eh-mem-tab-cnt" id="ehMemCntRules">0</span></button>
          <button type="button" class="eh-mem-tab" data-tab="aliases">نام‌های معادل <span class="eh-mem-tab-cnt" id="ehMemCntAliases">0</span></button>
        </div>

        <div id="ehMemTabBody" class="eh-mem-tab-body"></div>
      </div>
    `;
    document.body.appendChild(modal);

    modal.addEventListener('click', (e) => { if (e.target === modal) closeMemoryModal(); });
    modal.querySelector('#ehMemCloseBtn').addEventListener('click', closeMemoryModal);
    modal.querySelectorAll('.eh-mem-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        activeTab = btn.dataset.tab;
        modal.querySelectorAll('.eh-mem-tab').forEach(b => b.classList.toggle('active', b === btn));
        renderModalBody();
      });
    });

    return modal;
  }

  function openMemoryModal() {
    const modal = ensureMemoryModal();
    modal.classList.add('open');
    modalOpen = true;
    renderModalBody();
    refreshMemoryState();
  }

  function closeMemoryModal() {
    const modal = document.getElementById('ehMemModal');
    if (modal) modal.classList.remove('open');
    modalOpen = false;
  }

  function mountSidebarMemoryBtn() {
    if (document.getElementById('ehMemSidebarBtn')) return;
    const sidebar = document.querySelector('.sidebar, aside');
    if (!sidebar) return;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'ehMemSidebarBtn';
    btn.className = 'eh-diag-sb-btn eh-mem-sb-btn';
    btn.title = 'مدیریت قوانین دائمی و تأیید نام‌های مشابه (Ctrl+Shift+M)';
    btn.innerHTML = `
      <span class="eh-mem-sb-ico">✦</span>
      <span class="eh-diag-sb-lbl">حافظه قوانین و تطبیق</span>
      <span id="ehMemPendingBadge" class="eh-mem-badge" style="display:none;">0</span>
    `;
    btn.addEventListener('click', openMemoryModal);

    const diagBtn = document.getElementById('ehDiagSidebarBtn');
    if (diagBtn && diagBtn.parentElement) {
      diagBtn.parentElement.insertBefore(btn, diagBtn);
    } else {
      const footer = sidebar.querySelector('.sidebar-footer, .sb-footer');
      if (footer) footer.insertBefore(btn, footer.firstChild);
      else sidebar.appendChild(btn);
    }
  }

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && (e.key === 'M' || e.key === 'm')) {
      e.preventDefault();
      if (modalOpen) closeMemoryModal();
      else openMemoryModal();
    } else if (e.key === 'Escape' && modalOpen) {
      closeMemoryModal();
    }
  });

  window.openMemoryModal = openMemoryModal;

  window.addEventListener('DOMContentLoaded', () => {
    setTimeout(mountSidebarMemoryBtn, 80);
  });
  window.addEventListener('pywebviewready', () => {
    mountSidebarMemoryBtn();
    setTimeout(refreshMemoryState, 1600);
  });
})();
