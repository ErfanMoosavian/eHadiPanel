(() => {
  let memState = { rules: [], aliases: [], rejected: [], pending: [], pending_count: 0, config: {}, history: [] };
  let activeTab = 'pending';
  let modalOpen = false;

  const ENTITY_LABELS = {
    teacher: 'استاد / سخنران',
    workgroup: 'کارگروه',
    person: 'مخاطب / پرسنل',
    finance: 'مالی / فروشنده',
    general: 'عمومی',
  };

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
    const cAlias = document.getElementById('ehMemCntAliases');
    const cBrain = document.getElementById('ehMemCntBrain');
    const cRules = document.getElementById('ehMemCntRules');
    const cfg = memState.config || {};

    if (cPend) cPend.textContent = String((memState.pending || []).length);
    if (cAlias) cAlias.textContent = String((memState.aliases || []).length + (memState.rejected || []).length);
    if (cBrain) cBrain.textContent = String((cfg.compound_names || []).length);
    if (cRules) cRules.textContent = String((memState.rules || []).length);
    if (!body) return;

    // ---------- TAB 1: صف بازبینی (پیشنهادهای ادغام) ----------
    if (activeTab === 'pending') {
      const items = memState.pending || [];
      if (!items.length) {
        body.innerHTML = `
          <div class="eh-mem-empty-box">
            <strong>مورد مشکوکی در صف بازبینی وجود ندارد.</strong>
            <p>با ورود فایل‌های جدید، سامانه به‌صورت خودکار نام‌های مشابه را شناسایی کرده و اینجا برای تأیید یا منع ادغام نمایش می‌دهد.</p>
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
          ${it.caution ? `<div class="eh-mem-caution">${escHtml(it.caution)}</div>` : ''}
          <div class="eh-mem-pair-edit">
            <label>نام معیار نهایی پس از ادغام:</label>
            <input type="text" class="eh-mem-canon-inp" value="${escHtml(it.suggested_canonical)}" />
          </div>
          <div class="eh-mem-pair-btns">
            <button type="button" class="eh-diag-btn-primary eh-mem-approve-btn">ادغام کن و به خاطر بسپار</button>
            <button type="button" class="eh-diag-btn-sec eh-mem-reject-btn">جدا هستند (منع ادغام)</button>
          </div>
        </div>
      `).join('');

      body.querySelectorAll('.eh-mem-pair-card').forEach(card => {
        const it = items[Number(card.dataset.idx)];
        card.querySelector('.eh-mem-approve-btn').addEventListener('click', async (e) => {
          const canon = (card.querySelector('.eh-mem-canon-inp').value || '').trim() || it.suggested_canonical;
          const aliasVal = (canon === it.item_a) ? it.item_b : it.item_a;
          e.currentTarget.disabled = true;
          await window.pywebview.api.resolve_fuzzy_pair(canon, aliasVal, it.entity_type, 'approved', it.confidence / 100);
          toast(`ادغام «${aliasVal}» ← «${canon}» ثبت شد.`, 'healthy');
          await refreshMemoryState();
        });
        card.querySelector('.eh-mem-reject-btn').addEventListener('click', async (e) => {
          e.currentTarget.disabled = true;
          await window.pywebview.api.resolve_fuzzy_pair(it.item_a, it.item_b, it.entity_type, 'rejected', it.confidence / 100);
          toast('قانون منع ادغام برای این دو نام ثبت شد.', 'info');
          await refreshMemoryState();
        });
      });
      return;
    }

    // ---------- TAB 2: ادغام‌ها و قوانین منع ادغام ----------
    if (activeTab === 'aliases') {
      const aliases = memState.aliases || [];
      const rejected = memState.rejected || [];
      const approvedHtml = aliases.length
        ? aliases.map(a => `
            <div class="eh-mem-rule-row">
              <div class="eh-mem-rule-txt">
                <span class="eh-mem-type-pill">${escHtml(ENTITY_LABELS[a.entity_type] || a.entity_type)}</span>
                <span>«${escHtml(a.alias_name)}» <strong>←</strong> «${escHtml(a.canonical_name)}»</span>
              </div>
              <button type="button" class="eh-mem-del-btn" data-id="${a.id}">حذف</button>
            </div>`).join('')
        : '<div class="eh-mem-empty-box"><p>هنوز ادغام تأییدشده‌ای ثبت نشده است.</p></div>';

      const rejectedHtml = rejected.length
        ? rejected.map(r => `
            <div class="eh-mem-rule-row eh-mem-rej-row">
              <div class="eh-mem-rule-txt">
                <span class="eh-mem-type-pill pill-danger">منع ادغام</span>
                <span>«${escHtml(r.canonical_name)}» <strong>≠</strong> «${escHtml(r.alias_name)}»</span>
              </div>
              <button type="button" class="eh-mem-del-btn" data-id="${r.id}">حذف</button>
            </div>`).join('')
        : '<div class="eh-mem-empty-box"><p>قانون منع ادغامی ثبت نشده است.</p></div>';

      body.innerHTML = `
        <div class="eh-mem-section-card">
          <div class="eh-mem-sec-title">ثبت دستی ادغام یا منع ادغام</div>
          <div class="eh-mem-add-form eh-mem-alias-grid">
            <select id="ehMemAliasType" class="eh-mem-select">
              <option value="teacher">استاد / سخنران</option>
              <option value="workgroup">کارگروه</option>
              <option value="person">مخاطب</option>
              <option value="finance">مالی</option>
            </select>
            <input type="text" id="ehMemAliasFrom" placeholder="نام اول / نام فرعی..." />
            <input type="text" id="ehMemAliasTo" placeholder="نام معیار / نام دوم..." />
            <div class="eh-mem-inline-btns">
              <button type="button" class="eh-diag-btn-primary" id="ehMemAddAliasBtn">ثبت ادغام</button>
              <button type="button" class="eh-diag-btn-sec" id="ehMemAddRejectBtn">ثبت منع ادغام</button>
            </div>
          </div>
        </div>
        <div class="eh-mem-sec-title" style="margin-top:12px;">ادغام‌های فعال (${aliases.length})</div>
        <div class="eh-mem-list-stack">${approvedHtml}</div>
        <div class="eh-mem-sec-title" style="margin-top:14px;">قوانین منع ادغام (${rejected.length})</div>
        <div class="eh-mem-list-stack">${rejectedHtml}</div>
      `;

      const savePair = async (decision) => {
        const et = body.querySelector('#ehMemAliasType').value;
        const fromV = (body.querySelector('#ehMemAliasFrom').value || '').trim();
        const toV = (body.querySelector('#ehMemAliasTo').value || '').trim();
        if (!fromV || !toV) { toast('هر دو نام را وارد کنید.', 'warning'); return; }
        const res = await window.pywebview.api.resolve_fuzzy_pair(toV, fromV, et, decision, 1.0);
        if (res && res.ok) {
          toast(decision === 'approved' ? 'ادغام نام‌ها ثبت شد.' : 'قانون منع ادغام ثبت شد.', 'healthy');
          await refreshMemoryState();
        } else if (res && res.error) toast(res.error, 'warning');
      };

      body.querySelector('#ehMemAddAliasBtn').addEventListener('click', () => savePair('approved'));
      body.querySelector('#ehMemAddRejectBtn').addEventListener('click', () => savePair('rejected'));
      body.querySelectorAll('.eh-mem-del-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          await window.pywebview.api.delete_entity_alias(Number(btn.dataset.id));
          toast('مورد حذف شد.', 'info');
          await refreshMemoryState();
        });
      });
      return;
    }

    // ---------- TAB 3: نام‌های مرکب، القاب، تفکیک فردی/جمعی و ساعات مشترک ----------
    if (activeTab === 'brain') {
      const compounds = cfg.compound_names || [];
      const honorifics = cfg.honorifics || [];
      const collectives = cfg.collective_keywords || [];
      const overrides = cfg.entity_type_overrides || {};
      const hoursPol = cfg.hours_policy || 'equal';
      const dataMode = cfg.data_mode || 'clean';

      const cmpChips = compounds.length
        ? compounds.map(c => `<span class="eh-mem-tag-chip">${escHtml(c)} <button type="button" class="eh-mem-tag-x" data-cmp="${escHtml(c)}">×</button></span>`).join('')
        : '<span class="eh-mem-muted-note">هنوز نام مرکبی ثبت نشده است (مثال: حیدری فطرت، هاشمی گلپایگانی).</span>';

      const ovRows = Object.entries(overrides).length
        ? Object.entries(overrides).map(([k, v]) => `
            <div class="eh-mem-rule-row">
              <div class="eh-mem-rule-txt">
                <span class="eh-mem-type-pill">${v === 'collective' ? 'جمعی / گروهی' : 'فردی (استاد)'}</span>
                <span>«${escHtml(k)}»</span>
              </div>
              <button type="button" class="eh-mem-del-btn eh-mem-del-ov" data-raw="${escHtml(k)}">حذف</button>
            </div>`).join('')
        : '<div class="eh-mem-muted-note">تغییر نوع دستی ثبت نشده است.</div>';

      body.innerHTML = `
        <div class="eh-mem-section-card">
          <div class="eh-mem-sec-title">سیاست محاسبه ساعات دوره‌های مشترک و حالت داده</div>
          <div class="eh-mem-policy-grid">
            <div>
              <label class="eh-mem-mini-lbl">سیاست ساعات دوره‌های چنداستاده:</label>
              <div class="eh-mem-seg-group" id="ehMemHoursGroup">
                <button type="button" class="eh-mem-seg ${hoursPol === 'equal' ? 'active' : ''}" data-pol="equal">تقسیم مساوی</button>
                <button type="button" class="eh-mem-seg ${hoursPol === 'full' ? 'active' : ''}" data-pol="full">ساعت کامل</button>
                <button type="button" class="eh-mem-seg ${hoursPol === 'split' ? 'active' : ''}" data-pol="split">تفکیکی</button>
              </div>
            </div>
            <div>
              <label class="eh-mem-mini-lbl">حالت محاسبه آمار داشبورد:</label>
              <div class="eh-mem-seg-group" id="ehMemModeGroup">
                <button type="button" class="eh-mem-seg ${dataMode === 'clean' ? 'active' : ''}" data-mode="clean">داده‌های تمیزشده</button>
                <button type="button" class="eh-mem-seg ${dataMode === 'raw' ? 'active' : ''}" data-mode="raw">داده‌های خام</button>
              </div>
            </div>
          </div>
        </div>

        <div class="eh-mem-section-card" style="margin-top:10px;">
          <div class="eh-mem-sec-title">نام‌های مرکب محافظت‌شده (هرگز شکسته نشوند)</div>
          <div class="eh-mem-add-form">
            <input type="text" id="ehMemCmpInp" placeholder="مثلاً: حیدری فطرت" />
            <button type="button" class="eh-diag-btn-primary" id="ehMemCmpAddBtn">افزودن نام مرکب</button>
          </div>
          <div class="eh-mem-chips-wrap">${cmpChips}</div>
        </div>

        <div class="eh-mem-section-card" style="margin-top:10px;">
          <div class="eh-mem-sec-title">تغییر نوع موجودیت (فردی در برابر جمعی/گروهی)</div>
          <div class="eh-mem-add-form eh-mem-ov-form">
            <input type="text" id="ehMemOvInp" placeholder="عبارت دقیق در فایل (مثلاً: پنل تخصصی یا نام یک استاد)" />
            <select id="ehMemOvType" class="eh-mem-select">
              <option value="individual">فردی (استاد مستقل)</option>
              <option value="collective">جمعی / گروهی</option>
            </select>
            <button type="button" class="eh-diag-btn-primary" id="ehMemOvBtn">ثبت</button>
          </div>
          <div class="eh-mem-list-stack" style="margin-top:8px;">${ovRows}</div>
        </div>

        <div class="eh-mem-section-card" style="margin-top:10px;">
          <div class="eh-mem-sec-title">القاب و کلیدواژه‌های جمعی (با کاما یا خط جدید جدا کنید)</div>
          <label class="eh-mem-mini-lbl">القاب قابل حذف در مقایسه نام‌ها:</label>
          <textarea id="ehMemHonTxt" class="eh-mem-textarea" rows="2">${escHtml(honorifics.join('، '))}</textarea>
          <label class="eh-mem-mini-lbl" style="margin-top:8px;">کلیدواژه‌های تشخیص دوره گروهی/جمعی:</label>
          <textarea id="ehMemColTxt" class="eh-mem-textarea" rows="2">${escHtml(collectives.join('، '))}</textarea>
          <div style="margin-top:8px; display:flex; justify-content:flex-end;">
            <button type="button" class="eh-diag-btn-primary" id="ehMemSaveListsBtn">ذخیره القاب و کلیدواژه‌ها</button>
          </div>
        </div>
      `;

      body.querySelectorAll('#ehMemHoursGroup .eh-mem-seg').forEach(b => {
        b.addEventListener('click', async () => {
          const res = await window.pywebview.api.set_hours_policy(b.dataset.pol);
          if (res && res.ok) { toast('سیاست ساعات دوره‌های مشترک ذخیره شد.', 'healthy'); await refreshMemoryState(); }
        });
      });

      body.querySelectorAll('#ehMemModeGroup .eh-mem-seg').forEach(b => {
        b.addEventListener('click', async () => {
          const res = await window.pywebview.api.save_brain_config({ data_mode: b.dataset.mode });
          if (res && res.ok) { toast('حالت محاسبه داده‌ها بروزرسانی شد.', 'healthy'); await refreshMemoryState(); }
        });
      });

      body.querySelector('#ehMemCmpAddBtn').addEventListener('click', async () => {
        const inp = body.querySelector('#ehMemCmpInp');
        const val = (inp.value || '').trim();
        const res = await window.pywebview.api.add_compound_name(val);
        if (res && res.ok) { inp.value = ''; toast('نام مرکب به لیست محافظت اضافه شد.', 'healthy'); await refreshMemoryState(); }
        else if (res && res.error) toast(res.error, 'warning');
      });

      body.querySelectorAll('.eh-mem-tag-x').forEach(btn => {
        btn.addEventListener('click', async () => {
          await window.pywebview.api.delete_compound_name(btn.dataset.cmp);
          toast('نام مرکب حذف شد.', 'info');
          await refreshMemoryState();
        });
      });

      body.querySelector('#ehMemOvBtn').addEventListener('click', async () => {
        const raw = (body.querySelector('#ehMemOvInp').value || '').trim();
        const tp = body.querySelector('#ehMemOvType').value;
        if (!raw) { toast('عبارت را وارد کنید.', 'warning'); return; }
        const res = await window.pywebview.api.set_entity_type_override(raw, tp);
        if (res && res.ok) { toast('نوع موجودیت ثبت شد.', 'healthy'); await refreshMemoryState(); }
      });

      body.querySelectorAll('.eh-mem-del-ov').forEach(btn => {
        btn.addEventListener('click', async () => {
          await window.pywebview.api.set_entity_type_override(btn.dataset.raw, 'auto');
          toast('تنظیم دستی حذف شد.', 'info');
          await refreshMemoryState();
        });
      });

      body.querySelector('#ehMemSaveListsBtn').addEventListener('click', async () => {
        const splitList = s => String(s || '').split(/[،,\n]+/).map(x => x.trim()).filter(Boolean);
        const res = await window.pywebview.api.save_brain_config({
          honorifics: splitList(body.querySelector('#ehMemHonTxt').value),
          collective_keywords: splitList(body.querySelector('#ehMemColTxt').value),
        });
        if (res && res.ok) { toast('فهرست القاب و کلیدواژه‌ها ذخیره شد.', 'healthy'); await refreshMemoryState(); }
      });
      return;
    }

    // ---------- TAB 4: قوانین، تاریخچه بازگشت (Undo) و خروجی/ورودی JSON ----------
    if (activeTab === 'rules_history') {
      const rules = memState.rules || [];
      const history = memState.history || [];

      const rulesHtml = rules.length
        ? rules.map(r => `
            <div class="eh-mem-rule-row">
              <div class="eh-mem-rule-txt">
                <span class="eh-mem-type-pill">${escHtml(r.scope)}</span>
                <span>${escHtml(r.rule_text)}</span>
              </div>
              <button type="button" class="eh-mem-del-btn" data-rule-id="${r.id}">حذف</button>
            </div>`).join('')
        : '<div class="eh-mem-empty-box"><p>قانون دائمی ثبت نشده است.</p></div>';

      const histHtml = history.length
        ? history.slice(0, 15).map(h => `
            <div class="eh-mem-rule-row ${h.is_undone ? 'is-undone' : ''}">
              <div class="eh-mem-rule-txt">
                <span class="eh-mem-time-pill">${escHtml(h.created_at)}</span>
                <span>${escHtml(h.summary)}</span>
              </div>
              ${h.is_undone
                ? '<span class="eh-mem-undone-lbl">بازگردانی شد</span>'
                : `<button type="button" class="eh-diag-btn-sec eh-mem-undo-btn" data-hid="${h.id}">بازگردانی</button>`}
            </div>`).join('')
        : '<div class="eh-mem-muted-note">هنوز تغییری ثبت نشده است.</div>';

      body.innerHTML = `
        <div class="eh-mem-section-card">
          <div class="eh-mem-sec-title">قوانین دائمی هوش مصنوعی</div>
          <div class="eh-mem-add-form">
            <input type="text" id="ehMemNewRuleInp" placeholder="مثلاً: فاکتورهای چاپ بنر و پوستر را در دسته تبلیغات حساب کن..." />
            <button type="button" class="eh-diag-btn-primary" id="ehMemAddRuleBtn">ثبت قانون</button>
          </div>
          <div class="eh-mem-list-stack" style="margin-top:8px;">${rulesHtml}</div>
        </div>

        <div class="eh-mem-section-card" style="margin-top:10px;">
          <div class="eh-mem-sec-head-row">
            <div class="eh-mem-sec-title" style="margin:0;">پشتیبان‌گیری و انتقال قوانین (JSON)</div>
            <div class="eh-mem-inline-btns">
              <button type="button" class="eh-diag-btn-sec" id="ehMemExportJsonBtn">خروجی JSON</button>
              <button type="button" class="eh-diag-btn-primary" id="ehMemImportJsonBtn">ورود از JSON</button>
              <input type="file" id="ehMemImportFile" accept=".json" style="display:none;" />
            </div>
          </div>
        </div>

        <div class="eh-mem-section-card" style="margin-top:10px;">
          <div class="eh-mem-sec-title">تاریخچه تغییرات و بازگشت‌پذیری (Undo)</div>
          <div class="eh-mem-list-stack">${histHtml}</div>
        </div>
      `;

      body.querySelector('#ehMemAddRuleBtn').addEventListener('click', async () => {
        const inp = body.querySelector('#ehMemNewRuleInp');
        const txt = (inp.value || '').trim();
        if (txt.length < 4) { toast('متن قانون را کامل‌تر بنویسید.', 'warning'); return; }
        const res = await window.pywebview.api.add_user_rule(txt, 'عمومی');
        if (res && res.ok) { inp.value = ''; toast('قانون جدید ذخیره شد.', 'healthy'); await refreshMemoryState(); }
      });

      body.querySelectorAll('[data-rule-id]').forEach(btn => {
        btn.addEventListener('click', async () => {
          await window.pywebview.api.delete_user_rule(Number(btn.dataset.ruleId));
          toast('قانون حذف شد.', 'info');
          await refreshMemoryState();
        });
      });

      body.querySelectorAll('.eh-mem-undo-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const res = await window.pywebview.api.undo_brain_action(Number(btn.dataset.hid));
          if (res && res.ok) { toast('تغییر با موفقیت بازگردانی شد.', 'healthy'); await refreshMemoryState(); }
          else if (res && res.error) toast(res.error, 'warning');
        });
      });

      body.querySelector('#ehMemExportJsonBtn').addEventListener('click', async () => {
        const res = await window.pywebview.api.export_brain_config();
        if (res && res.ok && res.json) {
          const blob = new Blob([res.json], { type: 'application/json;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `eHadi_EntityBrain_${new Date().toISOString().slice(0, 10)}.json`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
          toast('فایل پشتیبان JSON قوانین دانلود شد.', 'healthy');
        }
      });

      const fileInp = body.querySelector('#ehMemImportFile');
      body.querySelector('#ehMemImportJsonBtn').addEventListener('click', () => fileInp.click());
      fileInp.addEventListener('change', async (e) => {
        const f = e.target.files?.[0];
        if (!f) return;
        const text = await f.text();
        const res = await window.pywebview.api.import_brain_config(text);
        if (res && res.ok) {
          toast('قوانین و تنظیمات با موفقیت وارد شدند.', 'healthy');
          await refreshMemoryState();
        } else {
          toast((res && res.error) || 'خطا در ورود فایل JSON', 'error');
        }
        fileInp.value = '';
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
            <span class="eh-diag-modal-ico">✦</span>
            <div>
              <h3>هسته هوشمند موجودیت‌ها و حافظه قوانین</h3>
              <p>کنترل کامل ادغام‌ها، نام‌های مرکب، منع ادغام، سیاست ساعات و پشتیبان‌گیری JSON</p>
            </div>
          </div>
          <button type="button" class="eh-diag-close" id="ehMemCloseBtn" title="بستن">✕</button>
        </div>

        <div class="eh-mem-tabs">
          <button type="button" class="eh-mem-tab active" data-tab="pending">صف بازبینی <span class="eh-mem-tab-cnt" id="ehMemCntPending">0</span></button>
          <button type="button" class="eh-mem-tab" data-tab="aliases">ادغام و منع ادغام <span class="eh-mem-tab-cnt" id="ehMemCntAliases">0</span></button>
          <button type="button" class="eh-mem-tab" data-tab="brain">نام مرکب و ساعات <span class="eh-mem-tab-cnt" id="ehMemCntBrain">0</span></button>
          <button type="button" class="eh-mem-tab" data-tab="rules_history">قوانین و بازگشت <span class="eh-mem-tab-cnt" id="ehMemCntRules">0</span></button>
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
    btn.title = 'هسته هوشمند موجودیت‌ها و حافظه قوانین (Ctrl+Shift+M)';
    btn.innerHTML = `
      <span class="eh-mem-sb-ico">✦</span>
      <span class="eh-diag-sb-lbl">هسته هوشمند و حافظه</span>
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
