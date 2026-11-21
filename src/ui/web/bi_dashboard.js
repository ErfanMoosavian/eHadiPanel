(() => {
  const COLORS = [
    '#38bdf8', '#818cf8', '#34d399', '#f59e0b',
    '#f472b6', '#a78bfa', '#2dd4bf', '#fb7185'
  ];

  const state = {
    mounted: false,
    activeLens: 'education',
    data: null,
    // فیلترهای آموزشی
    eduWorkgroup: 'ALL',
    eduSearch: '',
    // فیلترهای مالی
    finCategory: 'ALL',
    finFile: 'ALL',
    finSearch: '',
    // وضعیت کاوشگر پویا
    uniTable: '',
    uniCache: {},
    uniGroupCol: '',
    uniMetricCol: '__COUNT__',
    uniAgg: 'sum',
  };

  const esc = s => String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  const faNum = n => Number(n || 0).toLocaleString('fa-IR');
  const faDec = n => Number(n || 0).toLocaleString('fa-IR', { maximumFractionDigits: 1 });

  function parseClientNum(v) {
    if (v === null || v === undefined) return null;
    const s = String(v)
      .replace(/[۰-۹]/g, d => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d))
      .replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
      .replace(/[,٬،]/g, '').trim();
    if (!s || s === '-') return null;
    const m = s.match(/-?\d+(?:\.\d+)?/);
    return m ? Number(m[0]) : null;
  }

  function ensureShell() {
    if (state.mounted) return;
    const dashPage = document.getElementById('page-dashboard');
    const split = dashPage && dashPage.querySelector('.dash-split');
    if (!dashPage || !split) return;

    const root = document.createElement('div');
    root.id = 'biHubRoot';
    root.className = 'bi-root';
    root.innerHTML = `
      <div class="glass-card bi-hub-header">
        <div class="bi-hub-brand">
          <span class="bi-dot"></span>
          <div>
            <strong>مرکز هوش تجاری و تحلیل آماری</strong>
            <div class="bi-hub-sub">تحلیل زنده و آفلاین روی داده‌های آموزشی، فاکتورهای خرید و کلیه جداول ثبت‌شده</div>
          </div>
        </div>

        <div class="bi-lens-tabs" id="biLensTabs">
          <button class="bi-lens-tab active" data-lens="education">
            <span>آموزش و دوره‌ها</span>
            <span class="bi-tab-badge" id="biBadgeEdu">0</span>
          </button>
          <button class="bi-lens-tab" data-lens="finance">
            <span>مالی و فاکتورهای خرید</span>
            <span class="bi-tab-badge fin" id="biBadgeFin">0</span>
          </button>
          <button class="bi-lens-tab" data-lens="universal">
            <span>کاوشگر پویای جداول</span>
            <span class="bi-tab-badge uni" id="biBadgeUni">0</span>
          </button>
        </div>

        <button class="ghost-btn bi-mini-btn" id="biGlobalRefresh" title="بروزرسانی کامل داده‌های BI">↻ بروزرسانی</button>
      </div>

      <div id="biLensViewport" class="bi-viewport"></div>
    `;

    dashPage.insertBefore(root, split);
    state.mounted = true;

    root.querySelectorAll('.bi-lens-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        state.activeLens = btn.getAttribute('data-lens');
        root.querySelectorAll('.bi-lens-tab').forEach(b => b.classList.toggle('active', b === btn));
        renderActiveLens();
      });
    });

    document.getElementById('biGlobalRefresh').addEventListener('click', loadBiData);
  }

  function buildDonutHtml(items, total, selectedKey, centerLabel, unitLabel) {
    const r = 58;
    const C = 2 * Math.PI * r;
    const safeTotal = total || 1;
    let offset = 0;

    const slicesSvg = items.map((it, idx) => {
      const color = COLORS[idx % COLORS.length];
      const frac = it.value / safeTotal;
      const len = Math.max(0, frac * C - 1.8);
      const isSelected = selectedKey === it.name;
      const isDim = selectedKey !== 'ALL' && !isSelected;
      const svg = `<circle
        cx="78" cy="78" r="${r}"
        fill="none" stroke="${color}"
        stroke-width="${isSelected ? 19 : 15}"
        stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}"
        stroke-dashoffset="${(-offset).toFixed(2)}"
        class="bi-slice ${isDim ? 'dim' : ''}"
        data-slice="${esc(it.name)}"
      ><title>${esc(it.name)}: ${faNum(it.value)} ${esc(unitLabel)} (${Math.round(frac * 100)}٪)</title></circle>`;
      offset += frac * C;
      return svg;
    }).join('');

    const activeObj = selectedKey === 'ALL'
      ? { name: centerLabel, value: total }
      : (items.find(x => x.name === selectedKey) || { name: selectedKey, value: 0 });

    const legendHtml = items.map((it, idx) => {
      const color = COLORS[idx % COLORS.length];
      const pct = Math.round((it.value / safeTotal) * 100);
      const activeCls = selectedKey === it.name ? 'active' : '';
      return `
        <button class="bi-legend-item ${activeCls}" data-slice="${esc(it.name)}">
          <span class="bi-legend-dot" style="background:${color};"></span>
          <span class="bi-legend-name">${esc(it.name)}</span>
          <span class="bi-legend-val">${faNum(it.value)} <small>(${faNum(pct)}٪)</small></span>
        </button>
      `;
    }).join('');

    return `
      <div class="bi-donut-svg-box">
        <svg viewBox="0 0 156 156" class="bi-donut-svg">
          <circle cx="78" cy="78" r="${r}" fill="none" stroke="rgba(148,163,184,0.12)" stroke-width="15"/>
          <g transform="rotate(-90 78 78)">${slicesSvg}</g>
        </svg>
        <div class="bi-donut-center">
          <div class="bi-donut-num">${faNum(Math.round(activeObj.value))}</div>
          <div class="bi-donut-lbl">${esc(activeObj.name)}</div>
        </div>
      </div>
      <div class="bi-legend-list">${legendHtml}</div>
    `;
  }

  // ==================== لنز ۱: هوش تجاری آموزشی ====================

  function getFilteredEdu() {
    const edu = (state.data && state.data.education) || { records: [] };
    const q = (state.eduSearch || '').trim().toLowerCase();
    return (edu.records || []).filter(r => {
      if (state.eduWorkgroup !== 'ALL' && r.workgroup !== state.eduWorkgroup) return false;
      if (q && !(r.course.toLowerCase().includes(q) || r.teacher.toLowerCase().includes(q) || r.workgroup.toLowerCase().includes(q))) {
        return false;
      }
      return true;
    });
  }

  function renderEducationLens(vp) {
    const edu = (state.data && state.data.education) || { has_data: false, records: [], workgroups: [] };
    if (!edu.has_data) {
      vp.innerHTML = `<div class="glass-card bi-empty-box">
        <h3>هنوز جدول دوره‌های آموزشی در دیتابیس ثبت نشده است</h3>
        <p>فایل‌های گزارش دوره‌ها (PowerPoint، Excel یا Access) را اضافه و اسکن کنید تا داشبورد آموزشی به‌طور خودکار فعال شود.</p>
        <button class="primary-btn" onclick="window.addFiles && window.addFiles()">افزودن اسناد آموزشی</button>
      </div>`;
      return;
    }

    const allRecs = edu.records || [];
    const filtered = getFilteredEdu();
    const valid = filtered.filter(r => r.participants !== null && r.participants !== undefined);
    const totalCourses = filtered.length;
    const totalParticipants = valid.reduce((s, r) => s + Number(r.participants || 0), 0);
    const avg = valid.length ? totalParticipants / valid.length : 0;
    const topRec = valid.slice().sort((a, b) => b.participants - a.participants)[0];

    // داده‌های دونات و مقایسه روی کل کارگروه‌ها
    const wgMap = {};
    allRecs.forEach(r => {
      if (!wgMap[r.workgroup]) wgMap[r.workgroup] = { name: r.workgroup, value: 0, courses: 0, validCourses: 0 };
      wgMap[r.workgroup].courses += 1;
      if (r.participants !== null && r.participants !== undefined) {
        wgMap[r.workgroup].validCourses += 1;
        wgMap[r.workgroup].value += Number(r.participants);
      }
    });
    const wgItems = Object.values(wgMap).sort((a, b) => b.value - a.value);
    const wgTotal = wgItems.reduce((s, x) => s + x.value, 0);

    // ۱۰ دوره پرمخاطب فیلترشده
    const topCourses = valid.slice().sort((a, b) => b.participants - a.participants).slice(0, 10);
    const maxC = Math.max(...topCourses.map(x => x.participants), 1);

    // مقایسه کارگروه‌ها
    const cmpItems = wgItems.map(x => ({ ...x, avg: x.validCourses ? x.value / x.validCourses : 0 }))
      .sort((a, b) => b.avg - a.avg);
    const maxAvg = Math.max(...cmpItems.map(x => x.avg), 1);
    const maxCnt = Math.max(...cmpItems.map(x => x.courses), 1);

    // اساتید شاخص
    const tMap = {};
    filtered.forEach(r => {
      if (r.is_collective || !r.teacher_key) return;
      if (!tMap[r.teacher_key]) tMap[r.teacher_key] = { name: r.teacher, courses: 0, participants: 0 };
      if (r.teacher.length > tMap[r.teacher_key].name.length) tMap[r.teacher_key].name = r.teacher;
      tMap[r.teacher_key].courses += 1;
      tMap[r.teacher_key].participants += Number(r.participants || 0);
    });
    const teachers = Object.values(tMap).sort((a, b) => (b.participants - a.participants) || (b.courses - a.courses)).slice(0, 8);
    const maxT = Math.max(...teachers.map(x => x.participants), 1);

    vp.innerHTML = `
      <div class="glass-card bi-toolbar">
        <div class="bi-toolbar-controls" style="flex:1;">
          <select id="eduWgSel" class="glass-select bi-select">
            <option value="ALL">همه کارگروه‌ها و بخش‌ها (${faNum(allRecs.length)} دوره)</option>
            ${(edu.workgroups || []).map(w => `<option value="${esc(w)}" ${w === state.eduWorkgroup ? 'selected' : ''}>${esc(w)}</option>`).join('')}
          </select>
          <input id="eduSearchInp" class="glass-input bi-search" type="text" placeholder="جست‌وجوی زنده نام دوره یا استاد..." value="${esc(state.eduSearch)}" />
        </div>
        <div class="bi-toolbar-controls">
          <button class="ghost-btn bi-mini-btn" id="eduAskAiBtn">تحلیل آموزشی با AI ✦</button>
          <button class="excel-btn" id="eduExportBtn">خروجی اکسل (.xlsx)</button>
        </div>
      </div>

      <div class="bi-kpi-row">
        <div class="glass-card bi-kpi">
          <div class="bi-kpi-label">تعداد دوره‌ها</div>
          <div class="bi-kpi-val">${faNum(totalCourses)}</div>
          <div class="bi-kpi-sub">${totalCourses - valid.length > 0 ? `${faNum(totalCourses - valid.length)} دوره فاقد آمار ثبت‌شده` : 'تمامی دوره‌ها دارای آمار'}</div>
        </div>
        <div class="glass-card bi-kpi">
          <div class="bi-kpi-label">مجموع نفر-حضور جدولی</div>
          <div class="bi-kpi-val" style="color:#38bdf8;">${faNum(totalParticipants)}</div>
          <div class="bi-kpi-sub">جمع دقیق از جداول ثبت‌شده</div>
        </div>
        <div class="glass-card bi-kpi">
          <div class="bi-kpi-label">میانگین شرکت‌کننده هر دوره</div>
          <div class="bi-kpi-val" style="color:#34d399;">${faDec(avg)}</div>
          <div class="bi-kpi-sub">نفر به‌ازای هر دوره آماری</div>
        </div>
        <div class="glass-card bi-kpi">
          <div class="bi-kpi-label">پرمخاطب‌ترین دوره</div>
          <div class="bi-kpi-val bi-kpi-text" style="color:#f59e0b;">${topRec ? esc(topRec.course) : '—'}</div>
          <div class="bi-kpi-sub">${topRec ? `${faNum(topRec.participants)} نفر • ${esc(topRec.workgroup)}` : ''}</div>
        </div>
      </div>

      <div class="bi-grid">
        <div class="glass-card bi-card">
          <div class="card-title"><span>سهم مخاطبان به تفکیک کارگروه</span><span class="bi-hint">برای فیلتر روی برش کلیک کنید</span></div>
          <div class="bi-donut-wrap" id="eduDonutBox">${buildDonutHtml(wgItems, wgTotal, state.eduWorkgroup, 'کل مؤسسه', 'نفر')}</div>
        </div>

        <div class="glass-card bi-card">
          <div class="card-title"><span>${state.eduWorkgroup === 'ALL' ? '۱۰ دوره پرمخاطب مؤسسه' : `دوره‌های پرمخاطب (${esc(state.eduWorkgroup)})`}</span><span class="bi-hint">بر اساس تعداد شرکت‌کنندگان</span></div>
          <div class="bi-bars">
            ${topCourses.length ? topCourses.map((it, idx) => `
              <div class="bi-bar-row" title="${esc(it.course)} — ${esc(it.teacher)} (${esc(it.source)})">
                <div class="bi-bar-head">
                  <span class="bi-bar-rank">${faNum(idx + 1)}</span>
                  <span class="bi-bar-name">${esc(it.course)}</span>
                  <span class="bi-bar-teacher">${esc(it.teacher)}</span>
                  <span class="bi-bar-num">${faNum(it.participants)} نفر</span>
                </div>
                <div class="bi-bar-track"><div class="bi-bar-fill" style="width:${Math.max(4, Math.round(it.participants / maxC * 100))}%; background:linear-gradient(90deg, ${COLORS[idx % COLORS.length]}cc, ${COLORS[idx % COLORS.length]});"></div></div>
              </div>
            `).join('') : '<div class="empty-state"><p>موردی یافت نشد.</p></div>'}
          </div>
        </div>

        <div class="glass-card bi-card">
          <div class="card-title"><span>مقایسه کارگروه‌ها: میانگین مخاطب و تعداد دوره</span><span class="bi-hint">کلیک برای فیلتر</span></div>
          <div class="bi-wg-compare" id="eduCmpBox">
            ${cmpItems.map(it => `
              <div class="bi-cmp-item ${state.eduWorkgroup === it.name ? 'active' : ''}" data-slice="${esc(it.name)}">
                <div class="bi-cmp-head"><strong>${esc(it.name)}</strong><span>${faNum(it.courses)} دوره • میانگین ${faDec(it.avg)} نفر</span></div>
                <div class="bi-cmp-bars">
                  <div class="bi-cmp-track"><div class="bi-cmp-fill avg" style="width:${Math.max(5, Math.round(it.avg / maxAvg * 100))}%;"></div></div>
                  <div class="bi-cmp-track"><div class="bi-cmp-fill cnt" style="width:${Math.max(5, Math.round(it.courses / maxCnt * 100))}%;"></div></div>
                </div>
              </div>
            `).join('')}
            <div class="bi-cmp-legend"><span><i style="background:#38bdf8;"></i>میانگین مخاطب هر دوره</span><span><i style="background:#818cf8;"></i>تعداد دوره‌ها</span></div>
          </div>
        </div>

        <div class="glass-card bi-card">
          <div class="card-title"><span>اساتید شاخص (دوره‌های انفرادی)</span><span class="bi-hint">مرتب‌شده بر اساس مجموع مخاطبان</span></div>
          <div class="bi-teachers">
            ${teachers.length ? teachers.map((t, idx) => `
              <div class="bi-teacher-row">
                <div class="bi-bar-head">
                  <span class="bi-bar-rank">${faNum(idx + 1)}</span>
                  <span class="bi-bar-name">${esc(t.name)}</span>
                  <span class="stat-pill">${faNum(t.courses)} دوره</span>
                  <span class="bi-bar-num" style="color:#34d399;">${faNum(t.participants)} نفر</span>
                </div>
                <div class="bi-bar-track"><div class="bi-bar-fill" style="width:${Math.max(6, Math.round(t.participants / maxT * 100))}%; background:linear-gradient(90deg, #10b981cc, #34d399);"></div></div>
              </div>
            `).join('') : '<div class="empty-state"><p>استاد انفرادی در این فیلتر ثبت نشده است.</p></div>'}
          </div>
        </div>
      </div>
    `;

    window.__ehScanSelects && window.__ehScanSelects(vp);
    document.getElementById('eduWgSel').addEventListener('change', e => {
      state.eduWorkgroup = e.target.value;
      renderEducationLens(vp);
    });
    const searchEl = document.getElementById('eduSearchInp');
    searchEl.addEventListener('input', e => {
      state.eduSearch = e.target.value;
      const pos = searchEl.selectionStart;
      renderEducationLens(vp);
      const reEl = document.getElementById('eduSearchInp');
      if (reEl) { reEl.focus(); reEl.setSelectionRange(pos, pos); }
    });
    vp.querySelectorAll('[data-slice]').forEach(el => {
      el.addEventListener('click', () => {
        const wg = el.getAttribute('data-slice');
        state.eduWorkgroup = state.eduWorkgroup === wg ? 'ALL' : wg;
        renderEducationLens(vp);
      });
    });
    document.getElementById('eduAskAiBtn').addEventListener('click', () => {
      const q = state.eduWorkgroup === 'ALL'
        ? 'تحلیل مدیریتی جامع از عملکرد کل کارگروه‌های آموزشی مؤسسه، دوره‌های پرمخاطب و پیشنهادهای اجرایی ارائه کن.'
        : `تحلیل کامل آماری و مدیریتی از «${state.eduWorkgroup}» شامل تعداد دوره‌ها، مجموع و میانگین مخاطبان، اساتید شاخص و پیشنهادهای بهبود ارائه کن.`;
      window.switchPageById && window.switchPageById('chat');
      window.sendQuickPrompt && window.sendQuickPrompt(q);
    });
    document.getElementById('eduExportBtn').addEventListener('click', () => {
      exportExcel({
        title: state.eduWorkgroup === 'ALL' ? 'گزارش_جامع_دوره‌های_مؤسسه' : `گزارش_${state.eduWorkgroup}`,
        columns: ['ردیف', 'کارگروه / بخش', 'نام دوره', 'نام استاد', 'تعداد شرکت‌کنندگان', 'منبع'],
        rows: filtered.map((r, i) => [i + 1, r.workgroup, r.course, r.teacher, r.participants ?? '-', r.source]),
      });
    });
  }

  // ==================== لنز ۲: هوش تجاری مالی، خرید و فاکتورها ====================

  function getFilteredFin() {
    const fin = (state.data && state.data.finance) || { records: [] };
    const q = (state.finSearch || '').trim().toLowerCase();
    return (fin.records || []).filter(r => {
      if (state.finCategory !== 'ALL' && r.category !== state.finCategory) return false;
      if (state.finFile !== 'ALL' && r.file_name !== state.finFile) return false;
      if (q && !(r.item.toLowerCase().includes(q) || r.vendor.toLowerCase().includes(q) || r.category.toLowerCase().includes(q) || r.invoice_no.toLowerCase().includes(q))) {
        return false;
      }
      return true;
    });
  }

  function renderFinanceLens(vp) {
    const fin = (state.data && state.data.finance) || { has_data: false, records: [], categories: [], files: [], unit: 'تومان', unstructured_hints: [] };
    const unit = fin.unit || 'تومان';

    if (!fin.has_data) {
      const hintsHtml = (fin.unstructured_hints && fin.unstructured_hints.length)
        ? `<div class="bi-fin-hint-box">
            <strong>اسناد متنی با کلیدواژه مالی شناسایی شدند:</strong>
            <span>${fin.unstructured_hints.map(h => esc(h.file_name)).join('، ')}</span>
            <button class="ghost-btn bi-mini-btn" id="finAnalyzeHintsBtn">استخراج مالی با AI ✦</button>
          </div>`
        : '';

      vp.innerHTML = `
        <div class="glass-card bi-empty-box">
          <div class="stat-pill" style="margin-bottom:6px; border-color:rgba(52,211,153,0.4); color:#34d399;">موتور تحلیل مالی و تدارکات آماده است</div>
          <h3>به‌محض افزودن فایل فاکتورها و هزینه‌ها، داشبورد مالی خودکار فعال می‌شود</h3>
          <p>کافی است فایل‌های اکسل، اکسس، ورد یا PDF حاوی جداول خرید (شامل ستون‌هایی مثل <strong>شرح کالا/خدمت، مبلغ یا فی×تعداد، تاریخ، فروشنده، شماره فاکتور</strong>) را در بخش «مدیریت اسناد» اضافه و اسکن کنید.</p>
          <div class="bi-tax-chips">
            <span class="fmt-badge">پذیرایی و تشریفات</span>
            <span class="fmt-badge">تجهیزات و فناوری</span>
            <span class="fmt-badge">چاپ و انتشارات</span>
            <span class="fmt-badge">نوشت‌افزار و ملزومات</span>
            <span class="fmt-badge">حق‌التدریس و هدایا</span>
            <span class="fmt-badge">ایاب‌وذهاب و حمل‌ونقل</span>
            <span class="fmt-badge">تأسیسات و پشتیبانی</span>
          </div>
          ${hintsHtml}
          <div class="action-group" style="margin-top:8px;">
            <button class="primary-btn" onclick="window.addFiles && window.addFiles()">افزودن فایل فاکتورها و هزینه‌ها</button>
            <button class="ghost-btn" onclick="window.switchPageById && window.switchPageById('docs')">ورود به مدیریت اسناد</button>
          </div>
        </div>
      `;
      const hintBtn = document.getElementById('finAnalyzeHintsBtn');
      if (hintBtn) {
        hintBtn.addEventListener('click', () => {
          window.switchPageById && window.switchPageById('chat');
          window.sendQuickPrompt && window.sendQuickPrompt('تمام ارقام مالی، هزینه‌ها و فاکتورهای ثبت‌شده در اسناد مؤسسه را استخراج و دسته‌بندی کن.');
        });
      }
      return;
    }

    const allRecs = fin.records || [];
    const filtered = getFilteredFin();
    const totalSpend = filtered.reduce((s, r) => s + Number(r.amount || 0), 0);
    const avgSpend = filtered.length ? totalSpend / filtered.length : 0;

    // سرفصل‌ها روی کل (یا فایل فیلترشده) برای دونات تعاملی
    const baseForDonut = state.finFile === 'ALL' ? allRecs : allRecs.filter(r => r.file_name === state.finFile);
    const catMap = {};
    baseForDonut.forEach(r => {
      if (!catMap[r.category]) catMap[r.category] = { name: r.category, value: 0, count: 0 };
      catMap[r.category].value += Number(r.amount || 0);
      catMap[r.category].count += 1;
    });
    const catItems = Object.values(catMap).sort((a, b) => b.value - a.value);
    const catTotal = catItems.reduce((s, x) => s + x.value, 0);
    const topCat = catItems[0];

    // ۱۰ قلم/فاکتور بزرگ
    const topItems = filtered.slice().sort((a, b) => b.amount - a.amount).slice(0, 10);
    const maxItem = Math.max(...topItems.map(x => x.amount), 1);

    // روند بر اساس دوره زمانی / فایل
    const periodMap = {};
    filtered.forEach(r => {
      const k = r.period || r.file_name;
      if (!periodMap[k]) periodMap[k] = { name: k, value: 0, count: 0 };
      periodMap[k].value += Number(r.amount || 0);
      periodMap[k].count += 1;
    });
    const periods = Object.values(periodMap).sort((a, b) => a.name.localeCompare(b.name, 'fa'));
    const maxPeriod = Math.max(...periods.map(x => x.value), 1);

    // فروشندگان برتر
    const vMap = {};
    filtered.forEach(r => {
      if (!r.vendor || r.vendor === 'ثبت‌نشده') return;
      if (!vMap[r.vendor]) vMap[r.vendor] = { name: r.vendor, value: 0, count: 0 };
      vMap[r.vendor].value += Number(r.amount || 0);
      vMap[r.vendor].count += 1;
    });
    const vendors = Object.values(vMap).sort((a, b) => b.value - a.value).slice(0, 8);
    const maxV = Math.max(...vendors.map(x => x.value), 1);

    vp.innerHTML = `
      <div class="glass-card bi-toolbar">
        <div class="bi-toolbar-controls" style="flex:1;">
          <select id="finCatSel" class="glass-select bi-select">
            <option value="ALL">همه سرفصل‌های هزینه</option>
            ${(fin.categories || []).map(c => `<option value="${esc(c)}" ${c === state.finCategory ? 'selected' : ''}>${esc(c)}</option>`).join('')}
          </select>
          <select id="finFileSel" class="glass-select bi-select">
            <option value="ALL">همه فایل‌های مالی</option>
            ${(fin.files || []).map(f => `<option value="${esc(f)}" ${f === state.finFile ? 'selected' : ''}>${esc(f)}</option>`).join('')}
          </select>
          <input id="finSearchInp" class="glass-input bi-search" type="text" placeholder="جست‌وجوی کالا، فروشنده یا شماره فاکتور..." value="${esc(state.finSearch)}" />
        </div>
        <div class="bi-toolbar-controls">
          <button class="ghost-btn bi-mini-btn" id="finAskAiBtn">ممیزی و تحلیل مالی AI ✦</button>
          <button class="excel-btn" id="finExportBtn">خروجی اکسل مالی (.xlsx)</button>
        </div>
      </div>

      <div class="bi-kpi-row">
        <div class="glass-card bi-kpi">
          <div class="bi-kpi-label">جمع کل هزینه‌ها (${esc(unit)})</div>
          <div class="bi-kpi-val" style="color:#34d399;">${faNum(Math.round(totalSpend))}</div>
          <div class="bi-kpi-sub">${esc(unit)} • محاسبه دقیق از فاکتورها</div>
        </div>
        <div class="glass-card bi-kpi">
          <div class="bi-kpi-label">تعداد اقلام / ردیف‌های خرید</div>
          <div class="bi-kpi-val">${faNum(filtered.length)}</div>
          <div class="bi-kpi-sub">از ${faNum((fin.files || []).length)} فایل مالی نمایه‌شده</div>
        </div>
        <div class="glass-card bi-kpi">
          <div class="bi-kpi-label">میانگین مبلغ هر قلم</div>
          <div class="bi-kpi-val" style="color:#38bdf8;">${faNum(Math.round(avgSpend))}</div>
          <div class="bi-kpi-sub">${esc(unit)}</div>
        </div>
        <div class="glass-card bi-kpi">
          <div class="bi-kpi-label">بیشترین سرفصل هزینه</div>
          <div class="bi-kpi-val bi-kpi-text" style="color:#f59e0b;">${topCat ? esc(topCat.name) : '—'}</div>
          <div class="bi-kpi-sub">${topCat ? `${faNum(Math.round(topCat.value))} ${esc(unit)} (${Math.round(topCat.value / (catTotal || 1) * 100)}٪)` : ''}</div>
        </div>
      </div>

      <div class="bi-grid">
        <div class="glass-card bi-card">
          <div class="card-title"><span>سهم سرفصل‌های هزینه (دسته‌بندی خودکار)</span><span class="bi-hint">کلیک برای فیلتر</span></div>
          <div class="bi-donut-wrap">${buildDonutHtml(catItems, catTotal, state.finCategory, 'کل هزینه‌ها', unit)}</div>
        </div>

        <div class="glass-card bi-card">
          <div class="card-title"><span>۱۰ قلم / فاکتور با بیشترین مبلغ</span><span class="bi-hint">${esc(unit)}</span></div>
          <div class="bi-bars">
            ${topItems.map((it, idx) => `
              <div class="bi-bar-row" title="${esc(it.item)} | ${esc(it.vendor)} | ${esc(it.date)}">
                <div class="bi-bar-head">
                  <span class="bi-bar-rank">${faNum(idx + 1)}</span>
                  <span class="bi-bar-name">${esc(it.item)}</span>
                  <span class="stat-pill">${esc(it.category)}</span>
                  <span class="bi-bar-num" style="color:#34d399;">${faNum(Math.round(it.amount))}</span>
                </div>
                <div class="bi-bar-track"><div class="bi-bar-fill" style="width:${Math.max(4, Math.round(it.amount / maxItem * 100))}%; background:linear-gradient(90deg, ${COLORS[idx % COLORS.length]}cc, ${COLORS[idx % COLORS.length]});"></div></div>
              </div>
            `).join('')}
          </div>
        </div>

        <div class="glass-card bi-card">
          <div class="card-title"><span>روند هزینه به تفکیک دوره زمانی / منبع</span><span class="bi-hint">${esc(unit)}</span></div>
          <div class="bi-bars">
            ${periods.map(p => `
              <div class="bi-bar-row">
                <div class="bi-bar-head">
                  <span class="bi-bar-name">${esc(p.name)}</span>
                  <span class="stat-pill">${faNum(p.count)} قلم</span>
                  <span class="bi-bar-num">${faNum(Math.round(p.value))}</span>
                </div>
                <div class="bi-bar-track"><div class="bi-bar-fill" style="width:${Math.max(5, Math.round(p.value / maxPeriod * 100))}%; background:linear-gradient(90deg, #6366f1cc, #38bdf8);"></div></div>
              </div>
            `).join('')}
          </div>
        </div>

        <div class="glass-card bi-card">
          <div class="card-title"><span>تأمین‌کنندگان و فروشندگان برتر</span><span class="bi-hint">بر اساس مجموع خرید</span></div>
          <div class="bi-teachers">
            ${vendors.length ? vendors.map((v, idx) => `
              <div class="bi-teacher-row">
                <div class="bi-bar-head">
                  <span class="bi-bar-rank">${faNum(idx + 1)}</span>
                  <span class="bi-bar-name">${esc(v.name)}</span>
                  <span class="stat-pill">${faNum(v.count)} تراکنش</span>
                  <span class="bi-bar-num" style="color:#f59e0b;">${faNum(Math.round(v.value))}</span>
                </div>
                <div class="bi-bar-track"><div class="bi-bar-fill" style="width:${Math.max(6, Math.round(v.value / maxV * 100))}%; background:linear-gradient(90deg, #d97706cc, #f59e0b);"></div></div>
              </div>
            `).join('') : '<div class="empty-state"><p>ستون فروشنده در فاکتورها ثبت نشده است.</p></div>'}
          </div>
        </div>
      </div>

      <div class="glass-card bi-card" style="min-height:auto;">
        <div class="card-title"><span>دفترچه ریز اقلام و فاکتورها (نمایش تا ۵۰ ردیف فیلترشده)</span><span class="stat-pill">${faNum(filtered.length)} ردیف</span></div>
        <div class="ai-table-scroll" style="max-height:240px;">
          <table class="glass-table">
            <thead><tr><th>شرح کالا / خدمت</th><th>سرفصل</th><th>مبلغ (${esc(unit)})</th><th>فروشنده</th><th>تاریخ</th><th>فایل منبع</th></tr></thead>
            <tbody>
              ${filtered.slice(0, 50).map(r => `<tr>
                <td><strong>${esc(r.item)}</strong></td>
                <td><span class="fmt-badge">${esc(r.category)}</span></td>
                <td style="color:#34d399; font-weight:700;">${faNum(Math.round(r.amount))}</td>
                <td>${esc(r.vendor)}</td>
                <td>${esc(r.date)}</td>
                <td>${esc(r.file_name)}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;

    window.__ehScanSelects && window.__ehScanSelects(vp);
    document.getElementById('finCatSel').addEventListener('change', e => { state.finCategory = e.target.value; renderFinanceLens(vp); });
    document.getElementById('finFileSel').addEventListener('change', e => { state.finFile = e.target.value; renderFinanceLens(vp); });
    const fSearch = document.getElementById('finSearchInp');
    fSearch.addEventListener('input', e => {
      state.finSearch = e.target.value;
      const pos = fSearch.selectionStart;
      renderFinanceLens(vp);
      const reEl = document.getElementById('finSearchInp');
      if (reEl) { reEl.focus(); reEl.setSelectionRange(pos, pos); }
    });
    vp.querySelectorAll('[data-slice]').forEach(el => {
      el.addEventListener('click', () => {
        const c = el.getAttribute('data-slice');
        state.finCategory = state.finCategory === c ? 'ALL' : c;
        renderFinanceLens(vp);
      });
    });
    document.getElementById('finAskAiBtn').addEventListener('click', () => {
      const scope = state.finCategory === 'ALL' ? 'تمامی هزینه‌ها و فاکتورهای خرید مؤسسه' : `سرفصل هزینه «${state.finCategory}»`;
      const q = `یک گزارش ممیزی و تحلیل مالی دقیق از ${scope} شامل جمع کل، بزرگ‌ترین اقلام، روند هزینه‌ها و پیشنهادهای بهینه‌سازی بودجه ارائه کن.`;
      window.switchPageById && window.switchPageById('chat');
      window.sendQuickPrompt && window.sendQuickPrompt(q);
    });
    document.getElementById('finExportBtn').addEventListener('click', () => {
      exportExcel({
        title: state.finCategory === 'ALL' ? 'گزارش_جامع_مالی_و_فاکتورها' : `هزینه‌های_${state.finCategory}`,
        columns: ['ردیف', 'شرح کالا / خدمت', 'سرفصل هزینه', `مبلغ (${unit})`, 'تعداد', 'فروشنده', 'تاریخ', 'شماره فاکتور', 'فایل منبع'],
        rows: filtered.map((r, i) => [i + 1, r.item, r.category, r.amount, r.qty, r.vendor, r.date, r.invoice_no, r.file_name]),
      });
    });
  }

  // ==================== لنز ۳: کاوشگر پویا برای همه جداول DuckDB ====================

  async function renderUniversalLens(vp) {
    const tables = (state.data && state.data.universal && state.data.universal.tables) || [];
    if (!tables.length) {
      vp.innerHTML = `<div class="glass-card bi-empty-box"><h3>هیچ جدولی در دیتابیس DuckDB موجود نیست</h3><p>ابتدا اسناد خود را در بخش «مدیریت و پردازش اسناد» اسکن کنید.</p></div>`;
      return;
    }

    if (!state.uniTable || !tables.some(t => t.table_name === state.uniTable)) {
      state.uniTable = tables[0].table_name;
    }

    let tblData = state.uniCache[state.uniTable];
    if (!tblData) {
      vp.innerHTML = `<div class="glass-card bi-empty-box"><p>در حال بارگذاری ساختار جدول از DuckDB...</p></div>`;
      const res = await pywebview.api.get_bi_table_data(state.uniTable);
      if (!res || !res.ok) {
        vp.innerHTML = `<div class="glass-card bi-empty-box"><p>خطا در خواندن جدول: ${esc((res && res.error) || '')}</p></div>`;
        return;
      }
      state.uniCache[state.uniTable] = res;
      tblData = res;
    }

    const cols = tblData.columns || [];
    const textCols = tblData.text_columns && tblData.text_columns.length ? tblData.text_columns : cols;
    const numCols = tblData.numeric_columns || [];

    const skipAxisRx = /^(ردیف|شماره|id|no|index)$/i;
    const skipMetricRx = /(ردیف|سال|کد\s*ملی|موبایل|تلفن|شماره|تاریخ|id)/i;
    const smartNumCols = numCols.filter(c => !skipMetricRx.test(String(c || '').trim()));
    if (!cols.includes(state.uniGroupCol)) {
      state.uniGroupCol = textCols.find(c => !skipAxisRx.test(String(c || '').trim())) || textCols[0] || cols[0] || '';
    }
    if (!state.uniMetricCol || (state.uniMetricCol !== '__COUNT__' && !numCols.includes(state.uniMetricCol))) {
      state.uniMetricCol = smartNumCols[0] || numCols[0] || '__COUNT__';
    }

    const gIdx = cols.indexOf(state.uniGroupCol);
    const mIdx = state.uniMetricCol === '__COUNT__' ? -1 : cols.indexOf(state.uniMetricCol);

    const groups = {};
    let totalMetric = 0;
    let validRows = 0;
    const sumRowRx = /^(جمع\s*کل|مجموع(\s*کل)?|جمع|کل|میانگین|total|grand\s*total|subtotal)$/i;
    (tblData.rows || []).forEach(r => {
      const k = (gIdx >= 0 ? String(r[gIdx] || '').trim() : '') || 'نامشخص';
      if (sumRowRx.test(k)) return;
      if (!groups[k]) groups[k] = { name: k, sum: 0, count: 0 };
      if (mIdx >= 0) {
        const v = parseClientNum(r[mIdx]);
        if (v !== null) {
          groups[k].sum += v;
          groups[k].count += 1;
          totalMetric += v;
          validRows += 1;
        }
      } else {
        groups[k].sum += 1;
        groups[k].count += 1;
        totalMetric += 1;
        validRows += 1;
      }
    });

    const chartItems = Object.values(groups).map(g => ({
      name: g.name,
      value: (state.uniAgg === 'avg' && g.count > 0) ? (g.sum / g.count) : g.sum,
      count: g.count,
    })).filter(x => x.value > 0).sort((a, b) => b.value - a.value).slice(0, 12);

    const maxVal = Math.max(...chartItems.map(x => x.value), 1);
    const domainTag = d => d === 'finance' ? 'مالی' : (d === 'education' ? 'آموزشی' : 'عمومی');

    vp.innerHTML = `
      <div class="glass-card bi-toolbar">
        <div class="bi-toolbar-controls" style="flex:1;">
          <select id="uniTblSel" class="glass-select bi-select" style="min-width:230px;">
            ${tables.map(t => `<option value="${esc(t.table_name)}" ${t.table_name === state.uniTable ? 'selected' : ''}>[${domainTag(t.domain)}] ${esc(t.file_name)} — ${esc(t.source_sheet)} (${faNum(t.rows_count)} ردیف)</option>`).join('')}
          </select>
          <select id="uniGrpSel" class="glass-select bi-select">
            ${cols.map(c => `<option value="${esc(c)}" ${c === state.uniGroupCol ? 'selected' : ''}>محور: ${esc(c)}</option>`).join('')}
          </select>
          <select id="uniMetSel" class="glass-select bi-select">
            <option value="__COUNT__" ${state.uniMetricCol === '__COUNT__' ? 'selected' : ''}>شاخص: تعداد رکورد</option>
            ${numCols.map(c => `<option value="${esc(c)}" ${c === state.uniMetricCol ? 'selected' : ''}>شاخص: ${esc(c)}</option>`).join('')}
          </select>
          ${state.uniMetricCol !== '__COUNT__' ? `
            <select id="uniAggSel" class="glass-select bi-select" style="min-width:110px;">
              <option value="sum" ${state.uniAgg === 'sum' ? 'selected' : ''}>مجموع (Sum)</option>
              <option value="avg" ${state.uniAgg === 'avg' ? 'selected' : ''}>میانگین (Avg)</option>
            </select>
          ` : ''}
        </div>
        <div class="bi-toolbar-controls">
          <button class="ghost-btn bi-mini-btn" id="uniAskAiBtn">تحلیل جدول با AI ✦</button>
          <button class="excel-btn" id="uniExportBtn">خروجی اکسل جدول (.xlsx)</button>
        </div>
      </div>

      <div class="bi-grid">
        <div class="glass-card bi-card">
          <div class="card-title"><span>نمودار پویا (${esc(state.uniGroupCol)})</span><span class="stat-pill">مجموع کل: ${faDec(totalMetric)}</span></div>
          <div class="bi-bars">
            ${chartItems.length ? chartItems.map((it, idx) => `
              <div class="bi-bar-row">
                <div class="bi-bar-head">
                  <span class="bi-bar-rank">${faNum(idx + 1)}</span>
                  <span class="bi-bar-name">${esc(it.name)}</span>
                  <span class="bi-bar-num">${faDec(it.value)}</span>
                </div>
                <div class="bi-bar-track"><div class="bi-bar-fill" style="width:${Math.max(4, Math.round(it.value / maxVal * 100))}%; background:linear-gradient(90deg, ${COLORS[idx % COLORS.length]}cc, ${COLORS[idx % COLORS.length]});"></div></div>
              </div>
            `).join('') : '<div class="empty-state"><p>مقدار عددی برای ترسیم یافت نشد.</p></div>'}
          </div>
        </div>

        <div class="glass-card bi-card">
          <div class="card-title"><span>پیش‌نمایش زنده داده‌های جدول</span><span class="stat-pill">${faNum(tblData.total_rows)} ردیف / ${faNum(cols.length)} ستون</span></div>
          <div class="ai-table-scroll" style="max-height:270px;">
            <table class="glass-table">
              <thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>
              <tbody>${(tblData.rows || []).slice(0, 40).map(r => `<tr>${r.map(v => `<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    window.__ehScanSelects && window.__ehScanSelects(vp);
    document.getElementById('uniTblSel').addEventListener('change', e => {
      state.uniTable = e.target.value;
      state.uniGroupCol = '';
      state.uniMetricCol = '';
      renderUniversalLens(vp);
    });
    document.getElementById('uniGrpSel').addEventListener('change', e => { state.uniGroupCol = e.target.value; renderUniversalLens(vp); });
    document.getElementById('uniMetSel').addEventListener('change', e => { state.uniMetricCol = e.target.value; renderUniversalLens(vp); });
    const aggEl = document.getElementById('uniAggSel');
    if (aggEl) aggEl.addEventListener('change', e => { state.uniAgg = e.target.value; renderUniversalLens(vp); });

    document.getElementById('uniAskAiBtn').addEventListener('click', () => {
      const q = `جدول «${tblData.source_sheet}» از فایل «${tblData.file_name}» را به‌صورت کامل تحلیل آماری و مدیریتی کن.`;
      window.switchPageById && window.switchPageById('chat');
      window.sendQuickPrompt && window.sendQuickPrompt(q);
    });
    document.getElementById('uniExportBtn').addEventListener('click', () => {
      exportExcel({
        title: `${tblData.file_name}_${tblData.source_sheet}`,
        columns: cols,
        rows: tblData.rows || [],
      });
    });
  }

  async function exportExcel(payload) {
    try {
      const res = await pywebview.api.export_table_excel(payload);
      if (res && res.cancelled) return;
      if (res && res.ok) {
        window.showToast && window.showToast(`فایل اکسل ذخیره شد: ${res.path}`);
        await pywebview.api.open_file_path(res.path);
      } else {
        window.showToast && window.showToast('خطا در ذخیره اکسل: ' + ((res && res.error) || 'نامشخص'));
      }
    } catch (e) {
      window.showToast && window.showToast('خطا در خروجی اکسل: ' + e);
    }
  }

  function renderActiveLens() {
    const vp = document.getElementById('biLensViewport');
    if (!vp) return;
    if (state.activeLens === 'education') renderEducationLens(vp);
    else if (state.activeLens === 'finance') renderFinanceLens(vp);
    else renderUniversalLens(vp);
  }

  async function loadBiData() {
    ensureShell();
    state.uniCache = {};
    try {
      const res = await pywebview.api.get_bi_analytics();
      if (!res || !res.ok) return;
      state.data = res;

      const eduCnt = (res.education && res.education.records) ? res.education.records.length : 0;
      const finCnt = (res.finance && res.finance.records) ? res.finance.records.length : 0;
      const uniCnt = (res.universal && res.universal.tables) ? res.universal.tables.length : 0;

      const bEdu = document.getElementById('biBadgeEdu');
      const bFin = document.getElementById('biBadgeFin');
      const bUni = document.getElementById('biBadgeUni');
      if (bEdu) bEdu.textContent = faNum(eduCnt);
      if (bFin) bFin.textContent = finCnt > 0 ? faNum(finCnt) : 'آماده';
      if (bUni) bUni.textContent = faNum(uniCnt);

      renderActiveLens();
    } catch (e) {
      console.error('BI Load Error:', e);
    }
  }

  window.reloadBiDashboard = loadBiData;

  const origScan = window.scanDocs;
  if (typeof origScan === 'function') {
    window.scanDocs = async function (...args) {
      const out = await origScan.apply(this, args);
      setTimeout(loadBiData, 250);
      return out;
    };
  }

  window.addEventListener('pywebviewready', () => {
    setTimeout(loadBiData, 120);
  });
})();