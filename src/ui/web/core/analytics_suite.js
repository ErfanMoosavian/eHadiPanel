(() => {
  const App = window.eHadiApp;
  const Ch = window.eHadiCharts;
  const ic = App.icon;

  let lastAnalytics = null;
  let currentFilters = { group: '', teacher: '', year: '' };
  let porslineDraft = null;

  function chartCardHtml(id, title) {
    return `
      <div class="eh-chart-box glass-card">
        <div class="eh-chart-head">
          <strong>${title}</strong>
          <div class="eh-chart-actions">
            <button type="button" class="eh-mini-btn" data-dl-chart="${id}" data-kind="png" title="دانلود تصویر PNG">${ic('download', 13)}<span>PNG</span></button>
            <button type="button" class="eh-mini-btn" data-dl-chart="${id}" data-kind="svg" title="دانلود برداری SVG"><span>SVG</span></button>
          </div>
        </div>
        <div class="eh-chart-stage" id="${id}"></div>
      </div>
    `;
  }

  // ==================== ثبت ۵ ورودی جدید در سایدبار و پالت دستورات ====================
  [
    { id: 'exec_analytics', icon: 'barChart', label: 'مرکز آمار و گزارش‌سازی' },
    { id: 'porsline_hub', icon: 'upload', label: 'ورودی پرس‌لاین و حضورغیاب' },
    { id: 'event_pipeline', icon: 'gitBranch', label: 'چرخه رویدادها و تبلیغات ایتا' },
    { id: 'letter_registry', icon: 'archive', label: 'دبیرخانه و بایگانی نامه‌ها' },
    { id: 'data_health', icon: 'shieldCheck', label: 'سلامت و یکتاسازی داده‌ها' },
  ].forEach(m => {
    App.registerSidebarAction({ id: m.id, icon: m.icon, label: m.label, onClick: () => App.openModal(m.id) });
    App.registerCommand({ label: `باز کردن ${m.label}`, cat: 'ماژول‌ها', key: '', run: () => App.openModal(m.id) });
  });
  App.registerCommand({ label: 'حالت ارائه جلسه هیئت‌مدیره (Boardroom)', cat: 'ارائه', key: '', run: () => openBoardroom() });

  // ==================== ۱. مرکز جامع آمار و گزارش‌سازی گرافیکی ====================
  App.registerModal('exec_analytics', {
    render() {
      return `
        <div class="pro-modal-box eh-xl-modal" role="dialog" aria-modal="true">
          <div class="pro-modal-header">
            <div class="pro-modal-title">${ic('barChart', 17)}<span>مرکز جامع آمار، تحلیل و گزارش‌سازی گرافیکی</span></div>
            <div style="display:flex; align-items:center; gap:8px;">
              <button type="button" class="ghost-btn pro-btn-ic" id="btnOpenBoardroom" style="padding:5px 11px; font-size:11.5px;">${ic('presentation', 14)}<span>حالت ارائه جلسه</span></button>
              <button type="button" class="pro-icon-btn" id="btnRefreshExec" title="بروزرسانی">${ic('refresh', 15)}</button>
              <button type="button" class="pro-icon-btn" data-close-modal title="بستن">${ic('close', 15)}</button>
            </div>
          </div>
          <div class="pro-modal-body">
            <div class="pro-modal-nav" id="execNav">
              <button type="button" class="pro-cat-btn active" data-pane="overview">${ic('trendingUp', 16)}<span>نمای کلان و منحنی‌ها</span></button>
              <button type="button" class="pro-cat-btn" data-pane="audience">${ic('users', 16)}<span>مخاطبان یکتا و هم‌پوشانی</span></button>
              <button type="button" class="pro-cat-btn" data-pane="teachers_fin">${ic('userCheck', 16)}<span>اساتید و بهره‌وری مالی</span></button>
              <button type="button" class="pro-cat-btn" data-pane="builder">${ic('sliders', 16)}<span>گزارش‌ساز سفارشی</span></button>
            </div>
            <div class="pro-modal-content">
              <!-- نوار فیلتر متقاطع سراسری -->
              <div class="eh-filter-bar glass-card">
                <select id="fltGroup" class="glass-select"><option value="">همه کارگروه‌ها</option></select>
                <select id="fltTeacher" class="glass-select"><option value="">همه اساتید</option></select>
                <select id="fltYear" class="glass-select"><option value="">همه سال‌ها</option></select>
                <button type="button" class="ghost-btn" id="btnResetFilters" style="padding:6px 12px; font-size:11.5px;">حذف فیلترها</button>
              </div>

              <!-- تب ۱: نمای کلان -->
              <div class="pro-pane active" id="exec-pane-overview">
                <div class="eh-kpi-row" id="execKpiGrid"></div>
                <div class="eh-chart-grid2">
                  ${chartCardHtml('chTimeline', 'منحنی جذب مخاطب جدید در برابر مخاطب قدیمی')}
                  ${chartCardHtml('chRetention', 'توزیع وفاداری و تعداد حضور مخاطبان')}
                </div>
                <div class="eh-chart-grid2">
                  ${chartCardHtml('chRadar', 'توازن عملکرد کارگروه‌ها (نمودار راداری)')}
                  ${chartCardHtml('chHeatmap', 'نقشه حرارتی برگزاری برنامه‌ها در ماه‌های سال')}
                </div>
              </div>

              <!-- تب ۲: مخاطبان یکتا و هم‌پوشانی -->
              <div class="pro-pane" id="exec-pane-audience">
                <div class="eh-chart-grid2">
                  ${chartCardHtml('chGroupUnique', 'مقایسه حضور کل در برابر شرکت‌کنندگان یکتای کارگروه‌ها')}
                  <div class="eh-chart-box glass-card">
                    <div class="eh-chart-head"><strong>ماتریس هم‌پوشانی کارگروه‌ها (Cross-Group Affinity)</strong></div>
                    <div id="affinityMatrixBox" style="overflow:auto;"></div>
                  </div>
                </div>
                <div class="glass-card" style="padding:14px;">
                  <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:10px;">
                    <strong>فهرست شرکت‌کنندگان یکتاسازی‌شده (کلیک روی نام برای پرونده ۳۶۰ درجه)</strong>
                    <input id="inpSearchParticipant" class="glass-input" type="text" placeholder="جست‌وجوی نام یا موبایل..." style="width:230px; padding:6px 10px;"/>
                  </div>
                  <div style="max-height:290px; overflow:auto;">
                    <table class="glass-table" style="width:100%;">
                      <thead><tr><th>نام و نام خانوادگی</th><th>شماره تماس</th><th>سطح</th><th>تعداد دوره</th><th>وضعیت وفاداری</th><th>کارگروه‌ها</th></tr></thead>
                      <tbody id="tblParticipantsBody"></tbody>
                    </table>
                  </div>
                </div>
              </div>

              <!-- تب ۳: اساتید و بهره‌وری مالی -->
              <div class="pro-pane" id="exec-pane-teachers_fin">
                <div class="eh-chart-grid2">
                  ${chartCardHtml('chTeachers', 'ماتریس اثرگذاری اساتید (مخاطب کل / یکتا)')}
                  ${chartCardHtml('chPareto', 'تحلیل پارتو ۸۰/۲۰ سرفصل‌های هزینه')}
                </div>
                <div class="glass-card" style="padding:14px;">
                  <strong style="display:block; margin-bottom:10px;">عملکرد تفکیکی اساتید (کلیک روی نام استاد برای پرونده ۳۶۰ درجه و ویرایش سوابق)</strong>
                  <div style="max-height:280px; overflow:auto;">
                    <table class="glass-table" style="width:100%;">
                      <thead><tr><th>نام استاد</th><th>تعداد دوره</th><th>کل مخاطبان</th><th>مخاطبان یکتا</th><th>میانگین هر دوره</th><th>کارگروه‌ها</th></tr></thead>
                      <tbody id="tblTeachersBody"></tbody>
                    </table>
                  </div>
                </div>
              </div>

              <!-- تب ۴: گزارش‌ساز سفارشی -->
              <div class="pro-pane" id="exec-pane-builder">
                <div class="glass-card" style="padding:18px; display:flex; flex-direction:column; gap:14px;">
                  <div class="pro-pane-title">ساخت و خروجی گزارش جامع مدیریتی (سربرگ رسمی مؤسسه امام هادی (علیه‌السلام))</div>
                  <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                    <div class="eitaa-field"><label>عنوان گزارش</label><input id="repTitle" class="glass-input" value="گزارش جامع عملکرد علمی، آموزشی و تحلیل مخاطبان یکتا"/></div>
                    <div class="eitaa-field"><label>گیرنده / مخاطب گزارش (برای ثبت در دبیرخانه)</label><input id="repRecipient" class="glass-input" value="هیئت‌مدیره و مدیریت محترم مؤسسه"/></div>
                  </div>
                  <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:10px; font-size:12px;">
                    <label class="eh-chk"><input type="checkbox" id="chkKpis" checked/> شاخص‌های کلان (KPIs)</label>
                    <label class="eh-chk"><input type="checkbox" id="chkChTimeline" checked/> نمودار روند جذب مخاطبان</label>
                    <label class="eh-chk"><input type="checkbox" id="chkChGroup" checked/> نمودار کارگروه‌ها (کل و یکتا)</label>
                    <label class="eh-chk"><input type="checkbox" id="chkChTeachers" checked/> نمودار عملکرد اساتید</label>
                    <label class="eh-chk"><input type="checkbox" id="chkTblGroups" checked/> جدول تفکیکی کارگروه‌ها</label>
                    <label class="eh-chk"><input type="checkbox" id="chkTblTeachers" checked/> جدول عملکرد اساتید</label>
                  </div>
                  <div style="display:flex; flex-wrap:wrap; gap:10px; padding-top:8px;">
                    <button type="button" class="primary-btn pro-btn-ic" data-export-exec="pdf" style="padding:9px 18px;">${ic('fileText', 15)}<span>خروجی PDF رسمی همراه با نمودار</span></button>
                    <button type="button" class="ghost-btn pro-btn-ic" data-export-exec="docx" style="padding:9px 18px;">${ic('fileText', 15)}<span>خروجی Word رسمی همراه با نمودار</span></button>
                    <button type="button" class="ghost-btn pro-btn-ic" data-export-exec="xlsx" style="padding:9px 18px;">${ic('download', 15)}<span>خروجی Excel تحلیلی چندشیته (شامل مخاطبان یکتا)</span></button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      `;
    },
    onMount(bd) {
      bd.querySelectorAll('#execNav .pro-cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          bd.querySelectorAll('#execNav .pro-cat-btn').forEach(b => b.classList.remove('active'));
          bd.querySelectorAll('.pro-pane').forEach(p => p.classList.remove('active'));
          btn.classList.add('active');
          bd.querySelector('#exec-pane-' + btn.dataset.pane)?.classList.add('active');
        });
      });

      ['fltGroup', 'fltTeacher', 'fltYear'].forEach(id => {
        bd.querySelector('#' + id).addEventListener('change', () => {
          currentFilters = {
            group: bd.querySelector('#fltGroup').value,
            teacher: bd.querySelector('#fltTeacher').value,
            year: bd.querySelector('#fltYear').value,
          };
          loadAndDrawAnalytics(bd);
        });
      });

      bd.querySelector('#btnResetFilters').addEventListener('click', () => {
        currentFilters = { group: '', teacher: '', year: '' };
        bd.querySelector('#fltGroup').value = '';
        bd.querySelector('#fltTeacher').value = '';
        bd.querySelector('#fltYear').value = '';
        loadAndDrawAnalytics(bd);
      });

      bd.querySelector('#btnRefreshExec').addEventListener('click', () => loadAndDrawAnalytics(bd));
      bd.querySelector('#btnOpenBoardroom').addEventListener('click', () => openBoardroom());

      bd.querySelector('#inpSearchParticipant').addEventListener('input', () => drawParticipantsTable(bd));

      bd.querySelectorAll('[data-dl-chart]').forEach(btn => {
        btn.addEventListener('click', () => {
          const box = bd.querySelector('#' + btn.dataset.dlChart);
          Ch.downloadChart(box, `ehadi_${btn.dataset.dlChart}`, btn.dataset.kind);
          App.toast(`نمودار با فرمت ${btn.dataset.kind.toUpperCase()} ذخیره شد.`);
        });
      });

      bd.querySelectorAll('[data-export-exec]').forEach(btn => {
        btn.addEventListener('click', () => runExecutiveExport(bd, btn.dataset.exportExec));
      });
    },
    onOpen(bd) { loadAndDrawAnalytics(bd); },
  });

  async function loadAndDrawAnalytics(bd) {
    const res = await window.pywebview?.api?.get_executive_analytics?.(currentFilters);
    if (!res || !res.ok) return;
    lastAnalytics = res;

    // پر کردن سلکت‌های فیلتر
    const fillSel = (id, list, allLbl, curVal) => {
      const sel = bd.querySelector('#' + id);
      if (!sel) return;
      sel.innerHTML = `<option value="">${allLbl}</option>` + (list || []).map(x => `<option value="${x}" ${x === curVal ? 'selected' : ''}>${x}</option>`).join('');
    };
    fillSel('fltGroup', res.filters_meta.groups, 'همه کارگروه‌ها', currentFilters.group);
    fillSel('fltTeacher', res.filters_meta.teachers, 'همه اساتید', currentFilters.teacher);
    fillSel('fltYear', res.filters_meta.years, 'همه سال‌ها', currentFilters.year);

    const k = res.kpis;
    const uniqNote = res.has_person_level ? 'محاسبه دقیق فردی' : 'تخمین از جداول تجمیعی';
    bd.querySelector('#execKpiGrid').innerHTML = [
      ['شرکت‌کنندگان یکتا', Ch.fmtNum(k.unique_participants), uniqNote],
      ['مجموع حضور کل', Ch.fmtNum(k.total_attendance), `در ${Ch.fmtNum(k.total_courses)} دوره و رویداد`],
      ['نرخ بازگشت و وفاداری', `${Ch.toFa(k.repeat_rate)}٪`, `میانگین ${Ch.toFa(k.avg_per_course)} نفر/دوره`],
      ['اساتید و کارگروه‌ها', `${Ch.fmtNum(k.total_teachers)} / ${Ch.fmtNum(k.total_groups)}`, `سلامت داده: ${Ch.toFa(k.data_health_score)}٪`],
      ['هزینه هر مخاطب', k.cost_per_attendee ? `${Ch.fmtNum(k.cost_per_attendee)} ت` : 'ثبت نشده', `کل هزینه: ${Ch.fmtNum(k.total_cost)} ت`],
    ].map(([l, v, s]) => `<div class="eh-kpi glass-card"><div class="eh-kpi-l">${l}</div><div class="eh-kpi-v">${v}</div><div class="eh-kpi-s">${s}</div></div>`).join('');

    const tl = res.timeline || [];
    Ch.renderSplineArea(
      bd.querySelector('#chTimeline'),
      [
        { name: 'مخاطبان جدید', values: tl.map(x => x.new_participants), color: '#10b981' },
        { name: 'مخاطبان قدیمی', values: tl.map(x => x.returning_participants), color: '#0ea5e9' },
      ],
      tl.map(x => x.label),
      { id: 'tl' }
    );
    Ch.renderDonut(
      bd.querySelector('#chRetention'),
      (res.retention || []).map(x => ({ label: x.label, value: x.count })),
      'مخاطبان یکتا'
    );
    Ch.renderRadar(
      bd.querySelector('#chRadar'),
      (res.groups || []).map(g => ({ label: g.name, value: g.attendance }))
    );
    Ch.renderHeatmap(bd.querySelector('#chHeatmap'), res.heatmap || []);

    Ch.renderHBar(
      bd.querySelector('#chGroupUnique'),
      (res.groups || []).map(g => ({ label: g.name, v1: g.attendance, v2: g.unique })),
      { c1: '#10b981', c2: '#0ea5e9' }
    );
    Ch.renderHBar(
      bd.querySelector('#chTeachers'),
      (res.teachers || []).map(t => ({ label: t.name, v1: t.attendance, v2: t.unique })),
      { isTeacher: true }
    );
    Ch.renderHBar(
      bd.querySelector('#chPareto'),
      (res.pareto_costs || []).map(c => ({ label: c.category, v1: c.amount })),
      { c1: '#f59e0b' }
    );

    // ماتریس هم‌پوشانی کارگروه‌ها
    const aff = res.affinity_matrix || { labels: [], matrix: [] };
    const affBox = bd.querySelector('#affinityMatrixBox');
    if (affBox) {
      if (aff.labels && aff.labels.length && res.has_person_level) {
        const flatVals = aff.matrix.flat ? aff.matrix.flat() : [];
        const maxVal = Math.max(1, ...flatVals);
        const ths = '<th>کارگروه</th>' + aff.labels.map(l => `<th>${String(l).slice(0, 11)}</th>`).join('');
        const trs = aff.labels.map((l, i) => `<tr><th>${l}</th>` + (aff.matrix[i] || []).map((v, j) => {
          const a = v ? (0.14 + (v / maxVal) * 0.62).toFixed(2) : '0';
          const disp = (i === j && v === 0) ? Ch.fmtNum(res.groups[i]?.unique || 0) : Ch.fmtNum(v);
          return `<td style="text-align:center; background:rgba(16,185,129,${a}); font-weight:700;">${disp}</td>`;
        }).join('') + '</tr>').join('');
        affBox.innerHTML = `<table class="glass-table" style="width:100%; font-size:11px;"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
      } else {
        affBox.innerHTML = `
          <div class="eh-empty-chart" style="display:flex; flex-direction:column; align-items:center; gap:10px;">
            <span>برای محاسبه دقیق هم‌پوشانی کارگروه‌ها، فایل‌های ثبت‌نام پرس‌لاین را وارد کنید.</span>
            <button type="button" class="ghost-btn" id="btnGoPorslineFromAff" style="padding:6px 14px; font-size:11.5px;">ورود فایل پرس‌لاین</button>
          </div>`;
        affBox.querySelector('#btnGoPorslineFromAff')?.addEventListener('click', () => App.openModal('porsline_hub'));
      }
    }

    // جدول اساتید با کلیک پرونده ۳۶۰
    bd.querySelector('#tblTeachersBody').innerHTML = (res.teachers || []).map(t => `
      <tr>
        <td><button type="button" class="eh-link-btn" data-open-teacher="${t.name}">${t.name}</button></td>
        <td>${Ch.fmtNum(t.courses)}</td><td>${Ch.fmtNum(t.attendance)}</td><td>${Ch.fmtNum(t.unique)}</td>
        <td>${Ch.toFa(t.avg_attendance)}</td><td>${(t.groups || []).join('، ')}</td>
      </tr>
    `).join('') || '<tr><td colspan="6" style="text-align:center;">داده‌ای یافت نشد.</td></tr>';

    bd.querySelectorAll('[data-open-teacher]').forEach(btn => {
      btn.addEventListener('click', () => openTeacherDrawer(btn.dataset.openTeacher));
    });
    drawParticipantsTable(bd);
  }

  function drawParticipantsTable(bd) {
    if (!lastAnalytics) return;
    const q = (bd.querySelector('#inpSearchParticipant')?.value || '').trim().toLowerCase();
    const list = (lastAnalytics.participants || []).filter(p => !q || p.name.toLowerCase().includes(q) || (p.phone || '').includes(q));
    bd.querySelector('#tblParticipantsBody').innerHTML = list.slice(0, 120).map(p => `
      <tr>
        <td><button type="button" class="eh-link-btn" data-open-person="${p.id}">${p.name}</button></td>
        <td dir="ltr" style="text-align:right;">${Ch.toFa(p.phone || '—')}</td>
        <td>${p.level || '—'}</td>
        <td>${Ch.fmtNum(p.courses_count)}</td>
        <td><span class="eh-badge">${p.loyalty}</span></td>
        <td>${(p.groups || []).join('، ')}</td>
      </tr>
    `).join('') || '<tr><td colspan="6" style="text-align:center;">برای مشاهده لیست فردی و یکتاسازی دقیق، فایل خروجی پرس‌لاین را وارد کنید.</td></tr>';

    bd.querySelectorAll('[data-open-person]').forEach(btn => {
      btn.addEventListener('click', () => openParticipantDrawer(btn.dataset.openPerson));
    });
  }

  async function runExecutiveExport(bd, fmt) {
    if (!lastAnalytics) return;
    const k = lastAnalytics.kpis;
    const payload = {
      format: fmt,
      filters: currentFilters,
      title: bd.querySelector('#repTitle').value.trim(),
      recipient: bd.querySelector('#repRecipient').value.trim(),
      kpis: bd.querySelector('#chkKpis').checked ? [
        { label: 'شرکت‌کنندگان یکتا', value: Ch.fmtNum(k.unique_participants) },
        { label: 'مجموع حضور کل', value: Ch.fmtNum(k.total_attendance) },
        { label: 'نرخ بازگشت و وفاداری', value: `${Ch.toFa(k.repeat_rate)}٪` },
        { label: 'تعداد دوره‌ها', value: Ch.fmtNum(k.total_courses) },
      ] : [],
      charts: [],
      tables: [],
      content: 'این گزارش به‌صورت خودکار از مرکز تحلیل و آمار مؤسسه علمی فرهنگی امام هادی (علیه‌السلام) استخراج شده است.',
    };

    if (fmt !== 'xlsx') {
      const pairs = [
        ['chkChTimeline', '#chTimeline', 'منحنی جذب مخاطب جدید در برابر مخاطب قدیمی'],
        ['chkChGroup', '#chGroupUnique', 'مقایسه حضور کل و مخاطبان یکتای کارگروه‌ها'],
        ['chkChTeachers', '#chTeachers', 'ماتریس عملکرد اساتید'],
      ];
      for (const [chk, sel, ttl] of pairs) {
        if (bd.querySelector('#' + chk)?.checked) {
          const svg = bd.querySelector(sel + ' svg');
          const uri = await Ch.svgToPngDataUri(svg, 2, true);
          if (uri) payload.charts.push({ title: ttl, data_uri: uri });
        }
      }
      if (bd.querySelector('#chkTblGroups')?.checked && lastAnalytics.groups.length) {
        payload.tables.push({
          title: 'جدول عملکرد تفکیکی کارگروه‌ها',
          columns: ['کارگروه', 'تعداد دوره', 'حضور کل', 'مخاطب یکتا', 'میانگین هر دوره'],
          rows: lastAnalytics.groups.map(g => [g.name, g.courses, g.attendance, g.unique, g.avg_attendance]),
        });
      }
      if (bd.querySelector('#chkTblTeachers')?.checked && lastAnalytics.teachers.length) {
        payload.tables.push({
          title: 'جدول عملکرد اساتید',
          columns: ['نام استاد', 'تعداد دوره', 'کل مخاطبان', 'مخاطبان یکتا', 'کارگروه‌ها'],
          rows: lastAnalytics.teachers.slice(0, 25).map(t => [t.name, t.courses, t.attendance, t.unique, (t.groups || []).join('، ')]),
        });
      }
    }

    const res = await window.pywebview?.api?.export_executive_report?.(payload);
    if (res && res.ok) App.toast(`گزارش ${fmt.toUpperCase()} با موفقیت تولید و در دبیرخانه ثبت شد.`);
    else if (res && !res.cancelled) App.toast(res.error || 'خطا در تولید گزارش');
  }

  // ==================== ۲. ورودی هوشمند پرس‌لاین و لیست حضور و غیاب A4 ====================
  App.registerModal('porsline_hub', {
    render() {
      return `
        <div class="pro-modal-box" role="dialog" aria-modal="true">
          <div class="pro-modal-header">
            <div class="pro-modal-title">${ic('upload', 17)}<span>ورودی هوشمند پرس‌لاین و تولید برگه حضور و غیاب رسمی A4</span></div>
            <button type="button" class="pro-icon-btn" data-close-modal>${ic('close', 15)}</button>
          </div>
          <div class="pro-modal-content" style="display:flex; flex-direction:column; gap:14px;">
            <div class="glass-card" style="padding:16px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
              <div>
                <div style="font-weight:700; font-size:13px;">بارگذاری فایل اکسل یا CSV خروجی پرس‌لاین</div>
                <div style="font-size:11.5px; color:var(--s-text-muted); margin-top:3px;">پاک‌سازی خودکار نام‌ها و شماره‌ها، تشخیص مخاطبان جدید و قدیمی و صدور برگه حضور و غیاب رسمی</div>
              </div>
              <button type="button" class="primary-btn pro-btn-ic" id="btnPickPorsline" style="padding:9px 18px;">${ic('upload', 15)}<span>انتخاب فایل پرس‌لاین</span></button>
            </div>

            <div id="porslineWorkspace" style="display:none; flex-direction:column; gap:12px;">
              <div class="eh-kpi-row" id="porslineSummary"></div>
              <div class="glass-card" style="padding:14px; display:grid; grid-template-columns:2fr 1fr 1.2fr 1fr 0.7fr; gap:10px;">
                <div class="eitaa-field"><label>عنوان دوره</label><input id="plCourse" class="glass-input"/></div>
                <div class="eitaa-field"><label>کارگروه</label><select id="plGroup" class="glass-select"><option>دین‌شناسی</option><option>تاریخ</option><option>قرآن</option><option>فقه</option><option>حدیث</option><option>تربیت مبلغ</option></select></div>
                <div class="eitaa-field"><label>نام استاد</label><input id="plTeacher" class="glass-input" placeholder="دکتر ..."/></div>
                <div class="eitaa-field"><label>تاریخ برگزاری</label><input id="plDate" class="glass-input" placeholder="آبان ۱۴۰۵"/></div>
                <div class="eitaa-field"><label>تعداد جلسات</label><input id="plSessions" type="number" min="1" max="10" value="6" class="glass-input"/></div>
              </div>
              <div style="display:flex; flex-wrap:wrap; gap:8px;">
                <button type="button" class="primary-btn pro-btn-ic" id="btnCommitPorsline" style="padding:8px 16px;">${ic('check', 14)}<span>ذخیره در پایگاه داده آمار یکتا</span></button>
                <button type="button" class="ghost-btn pro-btn-ic" id="btnPrintAttendance" style="padding:8px 16px;">${ic('fileText', 14)}<span>صدور برگه حضور و غیاب چاپی A4 (PDF)</span></button>
                <button type="button" class="ghost-btn pro-btn-ic" id="btnCopyPhones" style="padding:8px 16px;">${ic('copy', 14)}<span>کپی لیست شماره‌های تماس برای اطلاع‌رسانی</span></button>
              </div>
              <div class="glass-card" style="padding:12px; max-height:270px; overflow:auto;">
                <table class="glass-table" style="width:100%;">
                  <thead><tr><th>ردیف</th><th>نام و نام خانوادگی</th><th>شماره تماس</th><th>سطح</th><th>وضعیت سابقه</th></tr></thead>
                  <tbody id="tblPorslineBody"></tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      `;
    },
    onMount(bd) {
      bd.querySelector('#btnPickPorsline').addEventListener('click', async () => {
        const res = await window.pywebview?.api?.select_and_preview_porsline?.();
        if (!res || res.cancelled) return;
        if (!res.ok) { App.toast(res.error || 'خطا در خواندن فایل'); return; }
        porslineDraft = res;
        bd.querySelector('#porslineWorkspace').style.display = 'flex';
        bd.querySelector('#plCourse').value = res.suggested_course || '';
        bd.querySelector('#porslineSummary').innerHTML = [
          ['کل ثبت‌نامی پاک‌سازی‌شده', Ch.fmtNum(res.total_cleaned), res.file_name],
          ['مخاطبان کاملاً جدید', Ch.fmtNum(res.new_count), 'ورود اول به مؤسسه'],
          ['طلاب قدیمی و وفادار', Ch.fmtNum(res.returning_count), 'دارای سابقه حضور قبلی'],
        ].map(([l, v, s]) => `<div class="eh-kpi glass-card"><div class="eh-kpi-l">${l}</div><div class="eh-kpi-v">${v}</div><div class="eh-kpi-s">${s}</div></div>`).join('');
        bd.querySelector('#tblPorslineBody').innerHTML = (res.participants || []).map((p, i) => `
          <tr><td>${Ch.fmtNum(i + 1)}</td><td>${p.name}</td><td dir="ltr" style="text-align:right;">${Ch.toFa(p.phone || '—')}</td><td>${p.level || '—'}</td><td><span class="eh-badge">${p.is_new ? 'جدید' : 'سابقه‌دار'}</span></td></tr>
        `).join('');
      });

      bd.querySelector('#btnCommitPorsline').addEventListener('click', async () => {
        if (!porslineDraft) return;
        const r = await window.pywebview?.api?.commit_porsline_import?.({
          course_title: bd.querySelector('#plCourse').value,
          group: bd.querySelector('#plGroup').value,
          teacher: bd.querySelector('#plTeacher').value,
          date: bd.querySelector('#plDate').value,
          participants: porslineDraft.participants,
        });
        if (r && r.ok) App.toast(`${Ch.fmtNum(r.added)} رکورد به پایگاه داده آمار یکتا اضافه شد.`);
      });

      bd.querySelector('#btnPrintAttendance').addEventListener('click', async () => {
        if (!porslineDraft) return;
        const r = await window.pywebview?.api?.export_attendance_sheet?.({
          course_title: bd.querySelector('#plCourse').value,
          group: bd.querySelector('#plGroup').value,
          teacher: bd.querySelector('#plTeacher').value,
          sessions_count: Number(bd.querySelector('#plSessions').value || 6),
          participants: porslineDraft.participants,
        });
        if (r && r.ok) App.toast('برگه حضور و غیاب رسمی A4 صادر و در دبیرخانه ثبت شد.');
      });

      bd.querySelector('#btnCopyPhones').addEventListener('click', async () => {
        if (!porslineDraft) return;
        const phones = porslineDraft.participants.map(p => p.phone).filter(Boolean).join('\n');
        if (!phones) { App.toast('شماره تماسی در فایل یافت نشد.'); return; }
        await navigator.clipboard.writeText(phones);
        App.toast('لیست شماره‌های پاک‌سازی‌شده کپی شد.');
      });
    },
  });

  // ==================== ۳. سلامت داده‌ها و ادغام هوشمند (Data Health) ====================
  App.registerModal('data_health', {
    render() {
      return `
        <div class="pro-modal-box" role="dialog" aria-modal="true">
          <div class="pro-modal-header">
            <div class="pro-modal-title">${ic('shieldCheck', 17)}<span>خطایاب، سلامت داده‌ها و ادغام هوشمند رکوردهای تکراری</span></div>
            <button type="button" class="pro-icon-btn" data-close-modal>${ic('close', 15)}</button>
          </div>
          <div class="pro-modal-content" style="display:flex; flex-direction:column; gap:14px;">
            <div class="eh-kpi-row" id="dhKpis"></div>
            <div class="glass-card" style="padding:14px;">
              <strong style="display:block; margin-bottom:10px;">رکوردهای مشکوک به ثبت تکراری (ادغام با یک کلیک)</strong>
              <div id="dhDupList" style="display:flex; flex-direction:column; gap:8px;"></div>
            </div>
          </div>
        </div>
      `;
    },
    onOpen(bd) { refreshDataHealth(bd); },
  });

  async function refreshDataHealth(bd) {
    const res = await window.pywebview?.api?.get_executive_analytics?.({});
    if (!res || !res.ok) return;
    const dh = res.data_health || { score: 100, total_records: 0, missing_phone: 0, missing_level: 0, duplicates: [] };
    bd.querySelector('#dhKpis').innerHTML = [
      ['امتیاز سلامت دیتابیس', `${Ch.toFa(dh.score)}٪`, 'شاخص کیفیت و یکتایی'],
      ['مخاطبان ثبت‌شده', Ch.fmtNum(dh.total_records), 'رکورد فردی قابل راستی‌آزمایی'],
      ['تکراری‌های احتمالی', Ch.fmtNum(dh.duplicates.length), 'نیازمند بررسی و ادغام'],
      ['فاقد شماره تماس', Ch.fmtNum(dh.missing_phone), `فاقد سطح: ${Ch.fmtNum(dh.missing_level)}`],
    ].map(([l, v, s]) => `<div class="eh-kpi glass-card"><div class="eh-kpi-l">${l}</div><div class="eh-kpi-v">${v}</div><div class="eh-kpi-s">${s}</div></div>`).join('');

    const box = bd.querySelector('#dhDupList');
    if (!dh.duplicates.length) {
      box.innerHTML = '<div class="eh-empty-chart">هیچ رکورد تکراری مشکوکی یافت نشد؛ داده‌ها کاملاً تمیز هستند.</div>';
      return;
    }
    box.innerHTML = dh.duplicates.map((d, i) => `
      <div class="eh-dup-row">
        <div><strong>${d.name_a}</strong> <span style="color:var(--s-text-dim);">(${Ch.toFa(d.phone_a)})</span>  ↔  <strong>${d.name_b}</strong> <span style="color:var(--s-text-dim);">(${Ch.toFa(d.phone_b)})</span></div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="eh-badge">شباهت ${Ch.toFa(d.similarity)}٪</span>
          <button type="button" class="primary-btn" data-merge-idx="${i}" style="padding:5px 12px; font-size:11px;">ادغام به «${d.name_a}»</button>
        </div>
      </div>
    `).join('');
    box.querySelectorAll('[data-merge-idx]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const d = dh.duplicates[Number(btn.dataset.mergeIdx)];
        await window.pywebview?.api?.merge_duplicate_records?.(d.name_a, d.name_b);
        App.toast('رکوردها با موفقیت ادغام شدند.');
        refreshDataHealth(bd);
      });
    });
  }

  // ==================== ۴. دبیرخانه هوشمند و بایگانی نامه‌ها ====================
  App.registerModal('letter_registry', {
    render() {
      return `
        <div class="pro-modal-box" role="dialog" aria-modal="true">
          <div class="pro-modal-header">
            <div class="pro-modal-title">${ic('archive', 17)}<span>دبیرخانه هوشمند و دفتر اندیکاتور نامه‌های رسمی</span></div>
            <button type="button" class="pro-icon-btn" data-close-modal>${ic('close', 15)}</button>
          </div>
          <div class="pro-modal-content" style="display:flex; flex-direction:column; gap:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
              <span style="font-size:12px; color:var(--s-text-muted);">تمامی گزارش‌های PDF، Word و برگه‌های حضور و غیاب صادرشده به‌صورت خودکار اینجا ثبت می‌شوند.</span>
              <input id="inpSearchLetters" class="glass-input" placeholder="جست‌وجو در شماره یا موضوع نامه..." style="width:250px; padding:6px 10px;"/>
            </div>
            <div class="glass-card" style="padding:12px; flex:1; overflow:auto;">
              <table class="glass-table" style="width:100%;">
                <thead><tr><th>شماره نامه</th><th>تاریخ شمسی</th><th>موضوع</th><th>گیرنده</th><th>فرمت</th><th>عملیات</th></tr></thead>
                <tbody id="tblLettersBody"></tbody>
              </table>
            </div>
          </div>
        </div>
      `;
    },
    onMount(bd) {
      bd.querySelector('#inpSearchLetters').addEventListener('input', () => drawLetters(bd));
    },
    onOpen(bd) { drawLetters(bd); },
  });

  async function drawLetters(bd) {
    const res = await window.pywebview?.api?.get_letter_registry?.();
    const q = (bd.querySelector('#inpSearchLetters')?.value || '').trim().toLowerCase();
    const rows = ((res && res.letters) || []).filter(l => !q || (l.title || '').toLowerCase().includes(q) || (l.letter_no || '').includes(q));
    bd.querySelector('#tblLettersBody').innerHTML = rows.map(l => `
      <tr>
        <td dir="ltr" style="text-align:right; font-weight:700;">${l.letter_no}</td>
        <td>${l.date}</td>
        <td>${l.title}</td>
        <td>${l.recipient || '—'}</td>
        <td><span class="eh-badge">${l.format}</span></td>
        <td style="display:flex; gap:6px;">
          <button type="button" class="eh-mini-btn" data-open-f="${encodeURIComponent(l.path)}" title="باز کردن فایل">${ic('externalLink', 13)}</button>
          <button type="button" class="eh-mini-btn" data-reveal-f="${encodeURIComponent(l.path)}" title="نمایش در پوشه">${ic('folder', 13)}</button>
          <button type="button" class="eh-mini-btn" data-del-ltr="${l.id}" title="حذف از فهرست">${ic('trash', 13)}</button>
        </td>
      </tr>
    `).join('') || '<tr><td colspan="6" style="text-align:center;">هنوز نامه‌ای در دبیرخانه ثبت نشده است.</td></tr>';

    bd.querySelectorAll('[data-open-f]').forEach(b => b.addEventListener('click', () => window.pywebview?.api?.open_registered_file?.(decodeURIComponent(b.dataset.openF), false)));
    bd.querySelectorAll('[data-reveal-f]').forEach(b => b.addEventListener('click', () => window.pywebview?.api?.open_registered_file?.(decodeURIComponent(b.dataset.revealF), true)));
    bd.querySelectorAll('[data-del-ltr]').forEach(b => b.addEventListener('click', async () => { await window.pywebview?.api?.delete_registered_letter?.(b.dataset.delLtr); drawLetters(bd); }));
  }

  // ==================== ۵. چرخه رویدادها و آرشیو بازتاب خبرگزاری‌ها ====================
  const STAGES = [
    ['poster', 'پوستر و پرس‌لاین'], ['intro', 'معرفی دوره/استاد'], ['held', 'برگزاری'],
    ['photos', 'گزارش تصویری'], ['media', 'صوت و کلیپ'], ['eitaa_ads', 'تبلیغات ایتا'],
  ];

  App.registerModal('event_pipeline', {
    render() {
      return `
        <div class="pro-modal-box" role="dialog" aria-modal="true">
          <div class="pro-modal-header">
            <div class="pro-modal-title">${ic('gitBranch', 17)}<span>پیگیر چرخه رویدادها و تبلیغات در کانال‌های ایتا</span></div>
            <button type="button" class="pro-icon-btn" data-close-modal>${ic('close', 15)}</button>
          </div>
          <div class="pro-modal-content" style="display:flex; flex-direction:column; gap:14px;">
            <div class="glass-card" style="padding:14px; display:grid; grid-template-columns:2fr 1fr 1.2fr 1fr auto; gap:8px; align-items:end;">
              <div class="eitaa-field"><label>عنوان رویداد / دوره جدید</label><input id="evTitle" class="glass-input" placeholder="مثلاً: همایش اصالت میراث..."/></div>
              <div class="eitaa-field"><label>کارگروه</label><select id="evGroup" class="glass-select"><option>دین‌شناسی</option><option>تاریخ</option><option>قرآن</option><option>فقه</option><option>حدیث</option><option>تربیت مبلغ</option></select></div>
              <div class="eitaa-field"><label>استاد / سخنران</label><input id="evTeacher" class="glass-input" placeholder="آیت‌الله / دکتر ..."/></div>
              <div class="eitaa-field"><label>تاریخ</label><input id="evDate" class="glass-input" placeholder="آذر ۱۴۰۵"/></div>
              <button type="button" class="primary-btn pro-btn-ic" id="btnAddEvent" style="padding:8px 14px;">${ic('plus', 14)}<span>ثبت</span></button>
            </div>
            <div id="eventPipelineList" style="display:flex; flex-direction:column; gap:10px;"></div>
          </div>
        </div>
      `;
    },
    onMount(bd) {
      bd.querySelector('#btnAddEvent').addEventListener('click', async () => {
        const title = bd.querySelector('#evTitle').value.trim();
        if (!title) return;
        await window.pywebview?.api?.save_event_pipeline?.({
          title,
          group: bd.querySelector('#evGroup').value,
          teacher: bd.querySelector('#evTeacher').value.trim(),
          date: bd.querySelector('#evDate').value.trim(),
        });
        bd.querySelector('#evTitle').value = '';
        bd.querySelector('#evTeacher').value = '';
        drawEvents(bd);
        App.toast('رویداد جدید در چرخه اجرایی ثبت شد.');
      });
    },
    onOpen(bd) { drawEvents(bd); },
  });

  async function drawEvents(bd) {
    const res = await window.pywebview?.api?.get_event_pipelines?.();
    const list = (res && res.events) || [];
    const box = bd.querySelector('#eventPipelineList');
    if (!list.length) {
      box.innerHTML = '<div class="eh-empty-chart">رویدادی ثبت نشده است.</div>';
      return;
    }
    box.innerHTML = list.map((ev, idx) => {
      const doneCount = STAGES.filter(([k]) => ev.stages && ev.stages[k]).length;
      const pct = Math.round((doneCount / STAGES.length) * 100);
      const pills = STAGES.map(([k, lbl]) => `
        <button type="button" class="eh-stage-pill ${ev.stages && ev.stages[k] ? 'done' : ''}" data-ev="${idx}" data-st="${k}">
          ${ev.stages && ev.stages[k] ? ic('check', 12) : ''}<span>${lbl}</span>
        </button>
      `).join('');
      const links = (ev.eitaa_ads || []).map((lk, li) => `<span class="eh-badge">${lk.agency}: <a href="${lk.url}" target="_blank" style="color:inherit;">مشاهده</a> <button type="button" data-del-lk="${idx}:${li}" style="border:none;background:none;color:inherit;cursor:pointer;">×</button></span>`).join('');
      return `
        <div class="glass-card" style="padding:14px; display:flex; flex-direction:column; gap:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div><strong>${ev.title}</strong> <span style="font-size:11px; color:var(--s-text-muted);">(${ev.group}${ev.teacher ? ' — ' + ev.teacher : ''}${ev.date ? ' — ' + ev.date : ''})</span></div>
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="eh-badge">تکمیل ${Ch.toFa(pct)}٪</span>
              <button type="button" class="eh-mini-btn" data-del-ev="${ev.id}" title="حذف">${ic('trash', 13)}</button>
            </div>
          </div>
          <div class="eh-progress-track"><div class="eh-progress-fill" style="width:${pct}%;"></div></div>
          <div style="display:flex; flex-wrap:wrap; gap:6px;">${pills}</div>
          <div style="display:flex; flex-wrap:wrap; align-items:center; gap:6px; padding-top:4px; border-top:1px dashed var(--s-border);">
            <span style="font-size:11px; color:var(--s-text-muted);">تبلیغات کانال‌های ایتا:</span>
            ${links || '<span style="font-size:11px; color:var(--s-text-dim);">ثبت نشده</span>'}
            <input class="glass-input" data-ag="${idx}" placeholder="نام کانال ایتا..." style="width:155px; padding:4px 8px; font-size:11px;"/>
            <input class="glass-input" data-url="${idx}" dir="ltr" placeholder="https://..." style="width:190px; padding:4px 8px; font-size:11px;"/>
            <button type="button" class="ghost-btn" data-add-lk="${idx}" style="padding:4px 10px; font-size:11px;">+ افزودن لینک</button>
          </div>
        </div>
      `;
    }).join('');

    box.querySelectorAll('[data-st]').forEach(btn => btn.addEventListener('click', async () => {
      const ev = list[Number(btn.dataset.ev)];
      ev.stages = ev.stages || {};
      ev.stages[btn.dataset.st] = !ev.stages[btn.dataset.st];
      await window.pywebview?.api?.save_event_pipeline?.(ev);
      drawEvents(bd);
    }));
    box.querySelectorAll('[data-add-lk]').forEach(btn => btn.addEventListener('click', async () => {
      const idx = Number(btn.dataset.addLk);
      const ag = box.querySelector(`[data-ag="${idx}"]`).value.trim();
      const url = box.querySelector(`[data-url="${idx}"]`).value.trim();
      if (!ag || !url) return;
      const ev = list[idx];
      ev.eitaa_ads = ev.eitaa_ads || [];
      ev.eitaa_ads.push({ agency: ag, url });
      ev.stages = ev.stages || {};
      ev.stages.eitaa_ads = true;
      await window.pywebview?.api?.save_event_pipeline?.(ev);
      drawEvents(bd);
    }));
    box.querySelectorAll('[data-del-lk]').forEach(btn => btn.addEventListener('click', async () => {
      const [ei, li] = btn.dataset.delLk.split(':').map(Number);
      (list[ei].eitaa_ads || []).splice(li, 1);
      await window.pywebview?.api?.save_event_pipeline?.(list[ei]);
      drawEvents(bd);
    }));
    box.querySelectorAll('[data-del-ev]').forEach(btn => btn.addEventListener('click', async () => {
      await window.pywebview?.api?.delete_event_pipeline?.(btn.dataset.delEv);
      drawEvents(bd);
    }));
  }

  // ==================== ۶. پرونده ۳۶۰ درجه کشویی (Slide-Over Drawer) ====================
  function ensureDrawer() {
    let dr = document.getElementById('ehProfileDrawer');
    if (!dr) {
      dr = document.createElement('div');
      dr.id = 'ehProfileDrawer';
      dr.className = 'eh-drawer-backdrop';
      dr.innerHTML = `<div class="eh-drawer-panel"><div class="eh-drawer-head"><strong id="ehDrawerTitle">پرونده</strong><button type="button" class="pro-icon-btn" id="btnCloseDrawer">${ic('close', 15)}</button></div><div class="eh-drawer-body" id="ehDrawerBody"></div></div>`;
      dr.addEventListener('click', (e) => { if (e.target === dr) dr.classList.remove('open'); });
      document.body.appendChild(dr);
      dr.querySelector('#btnCloseDrawer').addEventListener('click', () => dr.classList.remove('open'));
    }
    return dr;
  }

  async function openTeacherDrawer(name) {
    const dr = ensureDrawer();
    const res = await window.pywebview?.api?.get_teacher_profile?.(name);
    if (!res || !res.ok) return;
    const st = res.stats;
    dr.querySelector('#ehDrawerTitle').textContent = `پرونده ۳۶۰ درجه استاد: ${name}`;
    dr.querySelector('#ehDrawerBody').innerHTML = `
      <div class="eh-kpi-row" style="grid-template-columns:1fr 1fr;">
        <div class="eh-kpi glass-card"><div class="eh-kpi-l">تعداد دوره‌ها</div><div class="eh-kpi-v">${Ch.fmtNum(st.courses)}</div></div>
        <div class="eh-kpi glass-card"><div class="eh-kpi-l">مخاطبان کل / یکتا</div><div class="eh-kpi-v">${Ch.fmtNum(st.attendance)} / ${Ch.fmtNum(st.unique)}</div></div>
      </div>
      <div class="eitaa-field"><label>سوابق علمی و معرفی استاد (قابل فراخوانی در تولید محتوا)</label><textarea id="drTeacherBio" class="glass-input" rows="3">${res.bio || ''}</textarea></div>
      <div class="eitaa-field"><label>آثار و تألیفات</label><textarea id="drTeacherWorks" class="glass-input" rows="2">${res.works || ''}</textarea></div>
      <div style="display:flex; gap:8px;">
        <button type="button" class="primary-btn" id="btnSaveTeacherMeta" style="padding:7px 14px; font-size:11.5px;">ذخیره سوابق استاد</button>
        <button type="button" class="ghost-btn" id="btnSendTeacherMedia" style="padding:7px 14px; font-size:11.5px;">ارسال به تولید محتوا</button>
      </div>
      <div style="margin-top:8px;"><strong style="font-size:12px;">دوره‌ها و نشست‌های ارائه‌شده:</strong></div>
      <div style="display:flex; flex-direction:column; gap:6px;">
        ${(res.courses || []).map(c => `<div class="eh-dup-row"><span>${c.title}</span><span class="eh-badge">${c.group || '—'}</span></div>`).join('') || '<div class="eh-empty-chart">دوره‌ای ثبت نشده است.</div>'}
      </div>
    `;
    dr.querySelector('#btnSaveTeacherMeta').addEventListener('click', async () => {
      await window.pywebview?.api?.save_teacher_meta?.(name, dr.querySelector('#drTeacherBio').value, dr.querySelector('#drTeacherWorks').value);
      App.toast('سوابق علمی استاد ذخیره شد.');
    });
    dr.querySelector('#btnSendTeacherMedia').addEventListener('click', () => {
      const bio = dr.querySelector('#drTeacherBio').value;
      const works = dr.querySelector('#drTeacherWorks').value;
      dr.classList.remove('open');
      App.openModal('media_studio');
      setTimeout(() => {
        const md = document.getElementById('proModal_media_studio');
        if (!md) return;
        md.querySelector('[data-tpl="intro"]')?.click();
        const t = md.querySelector('#msTeacher'); if (t) { t.value = name; t.dispatchEvent(new Event('input')); }
        const d = md.querySelector('#msDesc'); if (d) { d.value = [bio, works ? `آثار: ${works}` : ''].filter(Boolean).join('\n\n'); d.dispatchEvent(new Event('input')); }
      }, 60);
    });
    requestAnimationFrame(() => dr.classList.add('open'));
  }

  async function openParticipantDrawer(personId) {
    const dr = ensureDrawer();
    const res = await window.pywebview?.api?.get_participant_profile?.(personId);
    if (!res || !res.ok) return;
    const p = res.participant;
    dr.querySelector('#ehDrawerTitle').textContent = `پرونده مخاطب: ${p.name}`;
    dr.querySelector('#ehDrawerBody').innerHTML = `
      <div class="eh-kpi-row" style="grid-template-columns:1fr 1fr;">
        <div class="eh-kpi glass-card"><div class="eh-kpi-l">تعداد دوره‌های حضور</div><div class="eh-kpi-v">${Ch.fmtNum(p.courses_count)}</div></div>
        <div class="eh-kpi glass-card"><div class="eh-kpi-l">رده وفاداری</div><div class="eh-kpi-v" style="font-size:15px;">${p.loyalty}</div></div>
      </div>
      <div class="glass-card" style="padding:12px; font-size:12px; line-height:2;">
        <div><strong>شماره تماس:</strong> <span dir="ltr">${Ch.toFa(p.phone || '—')}</span></div>
        <div><strong>سطح حوزوی:</strong> ${p.level || '—'}</div>
        <div><strong>کارگروه‌ها:</strong> ${(p.groups || []).join('، ') || '—'}</div>
      </div>
      <strong style="font-size:12px;">سوابق شرکت در دوره‌ها:</strong>
      <div style="display:flex; flex-direction:column; gap:6px;">
        ${(p.courses || []).map(c => `<div class="eh-dup-row"><span>${c}</span></div>`).join('')}
      </div>
    `;
    requestAnimationFrame(() => dr.classList.add('open'));
  }

  async function openBoardroom() {
    const res = lastAnalytics || await window.pywebview?.api?.get_executive_analytics?.({});
    if (!res || !res.ok) return;
    lastAnalytics = res;

    let decList = [];
    try {
      const dRes = await window.pywebview?.api?.get_decisions?.();
      decList = (dRes && dRes.decisions) || [];
    } catch (_) {}

    let ov = document.getElementById('ehBoardroomOverlay');
    if (ov) ov.remove();
    ov = document.createElement('div');
    ov.id = 'ehBoardroomOverlay';
    ov.className = 'eh-boardroom-overlay eh-br-luxury';

    const totalSlides = 6;
    const dotsHtml = Array.from({ length: totalSlides }, (_, idx) =>
      `<button type="button" class="eh-br-dot ${idx === 0 ? 'active' : ''}" data-br-jump="${idx}" title="\u0627\u0633\u0644\u0627\u06cc\u062f ${Ch.toFa(idx + 1)}"></button>`
    ).join('');

    ov.innerHTML = `
      <div class="eh-br-ambient"></div>
      <div class="eh-br-top">
        <div class="eh-br-brand">
          <span class="eh-br-badge-icon">${ic('presentation', 17)}</span>
          <div>
            <strong>\u06af\u0632\u0627\u0631\u0634 \u062c\u0627\u0645\u0639 \u062c\u0644\u0633\u0647 \u0647\u06cc\u0626\u062a\u200c\u0645\u062f\u06cc\u0631\u0647</strong>
            <div style="font-size:11px; color:var(--s-text-muted);">\u0645\u0624\u0633\u0633\u0647 \u0639\u0644\u0645\u06cc \u0641\u0631\u0647\u0646\u06af\u06cc \u0627\u0645\u0627\u0645 \u0647\u0627\u062f\u06cc (\u0639\u0644\u06cc\u0647\u200c\u0627\u0644\u0633\u0644\u0627\u0645)</div>
          </div>
        </div>
        <div class="eh-br-dots">${dotsHtml}</div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="pro-kbd">\u2190 / \u2192</span>
          <button type="button" class="ghost-btn bi-mini-btn" id="brClose">${ic('close', 14)}<span>\u062e\u0631\u0648\u062c \u0627\u0632 \u0627\u0631\u0627\u0626\u0647</span></button>
        </div>
      </div>

      <div class="eh-br-stage" id="brStage"></div>

      <div class="eh-br-dock">
        <button type="button" class="pro-icon-btn" id="brPrev" title="\u0627\u0633\u0644\u0627\u06cc\u062f \u0642\u0628\u0644\u06cc">${ic('chevronRight', 18)}</button>
        <span id="brCounter" style="font-size:12.5px; font-weight:800; min-width:58px; text-align:center;">\u06f1 / \u06f6</span>
        <button type="button" class="pro-icon-btn" id="brNext" title="\u0627\u0633\u0644\u0627\u06cc\u062f \u0628\u0639\u062f\u06cc">${ic('chevronLeft', 18)}</button>
      </div>
    `;
    document.body.appendChild(ov);

    let slide = 0;
    const drawSlide = () => {
      const st = ov.querySelector('#brStage');
      ov.querySelector('#brCounter').textContent = `${Ch.toFa(slide + 1)} / ${Ch.toFa(totalSlides)}`;
      ov.querySelectorAll('.eh-br-dot').forEach((d, idx) => d.classList.toggle('active', idx === slide));
      const k = res.kpis || {};

      if (slide === 0) {
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">\u0627\u0633\u0644\u0627\u06cc\u062f \u06f1 \u0627\u0632 \u06f6 \u2022 \u0646\u0645\u0627\u06cc \u06a9\u0644\u0627\u0646 \u0639\u0645\u0644\u06a9\u0631\u062f</div>
            <h2>\u062e\u0644\u0627\u0635\u0647 \u0634\u0627\u062e\u0635\u200c\u0647\u0627\u06cc \u0631\u0627\u0647\u0628\u0631\u062f\u06cc \u0645\u0624\u0633\u0633\u0647 \u0627\u0645\u0627\u0645 \u0647\u0627\u062f\u06cc (\u0639\u0644\u06cc\u0647\u200c\u0627\u0644\u0633\u0644\u0627\u0645)</h2>
            <div class="eh-br-kpis-6">
              <div class="eh-br-kpi-card"><span class="eh-br-kpi-lbl">\u0634\u0631\u06a9\u062a\u200c\u06a9\u0646\u0646\u062f\u06af\u0627\u0646 \u06cc\u06a9\u062a\u0627</span><strong class="eh-br-kpi-num">${Ch.fmtNum(k.unique_participants)}</strong><small>\u0627\u0641\u0631\u0627\u062f \u063a\u06cc\u0631\u062a\u06a9\u0631\u0627\u0631\u06cc</small></div>
              <div class="eh-br-kpi-card"><span class="eh-br-kpi-lbl">\u0645\u062c\u0645\u0648\u0639 \u062d\u0636\u0648\u0631 \u06a9\u0644</span><strong class="eh-br-kpi-num">${Ch.fmtNum(k.total_attendance)}</strong><small>\u0646\u0641\u0631-\u062d\u0636\u0648\u0631 \u062f\u0631 \u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0647\u0627</small></div>
              <div class="eh-br-kpi-card"><span class="eh-br-kpi-lbl">\u062f\u0648\u0631\u0647\u200c\u0647\u0627 \u0648 \u0631\u0648\u06cc\u062f\u0627\u062f\u0647\u0627</span><strong class="eh-br-kpi-num">${Ch.fmtNum(k.total_courses)}</strong><small>\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 ${Ch.toFa(k.avg_per_course)} \u0646\u0641\u0631/\u062f\u0648\u0631\u0647</small></div>
              <div class="eh-br-kpi-card"><span class="eh-br-kpi-lbl">\u0646\u0631\u062e \u0648\u0641\u0627\u062f\u0627\u0631\u06cc \u0648 \u0628\u0627\u0632\u06af\u0634\u062a</span><strong class="eh-br-kpi-num">${Ch.toFa(k.repeat_rate)}\u066a</strong><small>\u062d\u0636\u0648\u0631 \u0645\u062c\u062f\u062f \u0645\u062e\u0627\u0637\u0628\u0627\u0646</small></div>
              <div class="eh-br-kpi-card"><span class="eh-br-kpi-lbl">\u0627\u0633\u0627\u062a\u06cc\u062f \u0648 \u06a9\u0627\u0631\u06af\u0631\u0648\u0647\u200c\u0647\u0627</span><strong class="eh-br-kpi-num">${Ch.fmtNum(k.total_teachers)} / ${Ch.fmtNum(k.total_groups)}</strong><small>\u0634\u0628\u06a9\u0647 \u0639\u0644\u0645\u06cc \u0648 \u067e\u0698\u0648\u0647\u0634\u06cc</small></div>
              <div class="eh-br-kpi-card"><span class="eh-br-kpi-lbl">\u0633\u0644\u0627\u0645\u062a \u0648 \u06cc\u06a9\u062a\u0627\u06cc\u06cc \u062f\u0627\u062f\u0647</span><strong class="eh-br-kpi-num">${Ch.toFa(k.data_health_score)}\u066a</strong><small>\u067e\u0627\u06cc\u0634 \u06a9\u06cc\u0641\u06cc\u062a \u062b\u0628\u062a\u200c\u0646\u0627\u0645\u200c\u0647\u0627</small></div>
            </div>
          </div>`;
      } else if (slide === 1) {
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">\u0627\u0633\u0644\u0627\u06cc\u062f \u06f2 \u0627\u0632 \u06f6 \u2022 \u067e\u0648\u06cc\u0627\u06cc\u06cc \u062c\u0630\u0628 \u0645\u062e\u0627\u0637\u0628</div>
            <h2>\u0631\u0648\u0646\u062f \u062c\u0630\u0628 \u0645\u062e\u0627\u0637\u0628\u0627\u0646 \u062c\u062f\u06cc\u062f \u062f\u0631 \u0628\u0631\u0627\u0628\u0631 \u0645\u062e\u0627\u0637\u0628\u0627\u0646 \u0642\u062f\u06cc\u0645\u06cc</h2>
            <div class="eh-br-card-wide"><div id="brCh1" style="width:100%;"></div></div>
          </div>`;
        Ch.renderSplineArea(st.querySelector('#brCh1'), [
          { name: '\u0645\u062e\u0627\u0637\u0628\u0627\u0646 \u062c\u062f\u06cc\u062f', values: res.timeline.map(x => x.new_participants) },
          { name: '\u0645\u062e\u0627\u0637\u0628\u0627\u0646 \u0642\u062f\u06cc\u0645\u06cc', values: res.timeline.map(x => x.returning_participants) },
        ], res.timeline.map(x => x.label), { id: 'br1' });
      } else if (slide === 2) {
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">\u0627\u0633\u0644\u0627\u06cc\u062f \u06f3 \u0627\u0632 \u06f6 \u2022 \u0639\u0645\u0644\u06a9\u0631\u062f \u06a9\u0627\u0631\u06af\u0631\u0648\u0647\u200c\u0647\u0627</div>
            <h2>\u0645\u0642\u0627\u06cc\u0633\u0647 \u062d\u0636\u0648\u0631 \u06a9\u0644\u060c \u0645\u062e\u0627\u0637\u0628\u0627\u0646 \u06cc\u06a9\u062a\u0627 \u0648 \u062a\u0648\u0627\u0632\u0646 \u06a9\u0627\u0631\u06af\u0631\u0648\u0647\u200c\u0647\u0627</h2>
            <div class="eh-br-grid2">
              <div class="eh-br-card-wide"><div id="brCh2Bar" style="width:100%;"></div></div>
              <div class="eh-br-card-wide"><div id="brCh2Rad" style="width:100%;"></div></div>
            </div>
          </div>`;
        Ch.renderHBar(st.querySelector('#brCh2Bar'), res.groups.map(g => ({ label: g.name, v1: g.attendance, v2: g.unique })));
        Ch.renderRadar(st.querySelector('#brCh2Rad'), res.groups.map(g => ({ label: g.name, value: g.attendance })));
      } else if (slide === 3) {
        const topT = (res.teachers || []).slice(0, 6);
        const medals = ['\ud83e\udd47', '\ud83e\udd48', '\ud83e\udd49', '\u06f4', '\u06f5', '\u06f6'];
        const cards = topT.map((t, idx) => `
          <div class="eh-br-teacher-card">
            <div class="eh-br-medal">${medals[idx] || Ch.toFa(idx + 1)}</div>
            <div style="flex:1; min-width:0;">
              <div style="font-size:15px; font-weight:800; color:var(--s-text);">${Ch.formatTeacherShort(t.name)}</div>
              <div style="font-size:11.5px; color:var(--s-text-muted); margin-top:2px;">${(t.groups || []).join('\u060c ') || '\u062f\u0648\u0631\u0647\u200c\u0647\u0627\u06cc \u0639\u0644\u0645\u06cc'}</div>
            </div>
            <div style="text-align:left;">
              <div style="font-size:18px; font-weight:800; color:var(--lg-accent);">${Ch.fmtNum(t.attendance)} \u0646\u0641\u0631</div>
              <div style="font-size:11px; color:var(--s-text-muted);">${Ch.fmtNum(t.courses)} \u062f\u0648\u0631\u0647 \u2022 \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 ${Ch.toFa(t.avg_attendance)}</div>
            </div>
          </div>
        `).join('');
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">\u0627\u0633\u0644\u0627\u06cc\u062f \u06f4 \u0627\u0632 \u06f6 \u2022 \u0634\u0628\u06a9\u0647 \u0627\u0633\u0627\u062a\u06cc\u062f</div>
            <h2>\u0627\u0633\u0627\u062a\u06cc\u062f \u0634\u0627\u062e\u0635 \u0648 \u0627\u062b\u0631\u06af\u0630\u0627\u0631 \u0645\u0624\u0633\u0633\u0647</h2>
            <div class="eh-br-teachers-grid">${cards || '<div class="eh-empty-chart">\u062f\u0627\u062f\u0647\u200c\u0627\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a.</div>'}</div>
          </div>`;
      } else if (slide === 4) {
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">\u0627\u0633\u0644\u0627\u06cc\u062f \u06f5 \u0627\u0632 \u06f6 \u2022 \u062a\u0642\u0648\u06cc\u0645 \u0627\u062c\u0631\u0627\u06cc\u06cc</div>
            <h2>\u0646\u0642\u0634\u0647 \u062d\u0631\u0627\u0631\u062a\u06cc \u0628\u0631\u06af\u0632\u0627\u0631\u06cc \u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0647\u0627 \u062f\u0631 \u0645\u0627\u0647\u200c\u0647\u0627\u06cc \u0633\u0627\u0644</h2>
            <div class="eh-br-card-wide"><div id="brChHeat" style="width:100%;"></div></div>
          </div>`;
        Ch.renderHeatmap(st.querySelector('#brChHeat'), res.heatmap || []);
      } else {
        const rows = decList.slice(0, 8).map((d, i) => `
          <div class="eh-br-dec-row">
            <span class="eh-step-num">${Ch.toFa(i + 1)}</span>
            <span style="flex:1; font-size:14px; font-weight:700;">${d.title}</span>
            <span class="eh-badge">${d.done ? '\u0627\u0646\u062c\u0627\u0645 \u0634\u062f' : '\u062f\u0631 \u062f\u0633\u062a \u067e\u06cc\u06af\u06cc\u0631\u06cc'}</span>
          </div>
        `).join('');
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">\u0627\u0633\u0644\u0627\u06cc\u062f \u06f6 \u0627\u0632 \u06f6 \u2022 \u0645\u0635\u0648\u0628\u0627\u062a \u0648 \u062a\u0635\u0645\u06cc\u0645\u200c\u0647\u0627</div>
            <h2>\u062f\u0633\u062a\u0648\u0631 \u062c\u0644\u0633\u0647 \u0648 \u067e\u06cc\u06af\u06cc\u0631\u06cc\u200c\u0647\u0627\u06cc \u0645\u062f\u06cc\u0631\u06cc\u062a\u06cc</h2>
            <div class="eh-br-card-wide" style="display:flex; flex-direction:column; gap:10px;">
              ${rows || '<div class="eh-empty-chart">\u0645\u0648\u0631\u062f\u06cc \u062f\u0631 \u062f\u0641\u062a\u0631\u0686\u0647 \u062a\u0635\u0645\u06cc\u0645\u200c\u0647\u0627 \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a\u061b \u0627\u0632 \u0635\u0641\u062d\u0647 \u0627\u0635\u0644\u06cc \u0645\u0648\u0627\u0631\u062f \u062c\u0644\u0633\u0647 \u0631\u0627 \u0627\u0636\u0627\u0641\u0647 \u06a9\u0646\u06cc\u062f.</div>'}
            </div>
          </div>`;
      }
    };

    const closeBr = () => { document.removeEventListener('keydown', onKey); ov.remove(); };
    const onKey = (e) => {
      if (e.key === 'Escape') closeBr();
      if (e.key === 'ArrowLeft') { slide = (slide + 1) % totalSlides; drawSlide(); }
      if (e.key === 'ArrowRight') { slide = (slide - 1 + totalSlides) % totalSlides; drawSlide(); }
    };
    document.addEventListener('keydown', onKey);
    ov.querySelectorAll('[data-br-jump]').forEach(btn => btn.addEventListener('click', () => { slide = Number(btn.dataset.brJump); drawSlide(); }));
    ov.querySelector('#brNext').addEventListener('click', () => { slide = (slide + 1) % totalSlides; drawSlide(); });
    ov.querySelector('#brPrev').addEventListener('click', () => { slide = (slide - 1 + totalSlides) % totalSlides; drawSlide(); });
    ov.querySelector('#brClose').addEventListener('click', closeBr);
    drawSlide();
  }

  window.openBoardroomMode = openBoardroom;
  App.boot();
})();
