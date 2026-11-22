(() => {
  const App = window.eHadiApp;
  const Ch = window.eHadiCharts;
  const ic = App.icon;
  const helpBtn = (key, cls = '') => (window.eHadiHelp?.btn ? window.eHadiHelp.btn(key, cls) : '');

  let lastAnalytics = null;
  let currentFilters = { group: '', teacher: '', year: '' };
  let porslineDraft = null;
  let partState = {
    search: '',
    loyalty: 'ALL',
    group: '',
    course: '',
    quality: 'ALL',
    sortBy: 'courses_desc',
    page: 1,
    pageSize: 25,
    filtered: [],
  };
  let tchState = {
    search: '',
    sortBy: 'attendance',
    sortDir: 'desc',
  };

  function escH(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function avatarInitials(name) {
    const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'م';
    if (parts.length === 1) return parts[0].slice(0, 2);
    return (parts[0][0] || '') + '‌' + (parts[parts.length - 1][0] || '');
  }

  function loyaltyClass(loyalty) {
    if (loyalty === 'هسته اصلی') return 'eh-loy-core';
    if (loyalty === 'مخاطب وفادار') return 'eh-loy-loyal';
    if (loyalty === 'مخاطب فعال') return 'eh-loy-active';
    return 'eh-loy-new';
  }

  function shortWgName(name) {
    const s = String(name || '').trim();
    if (s.includes('انس با الکافی') || s.includes('حدیث‌خوانی')) return 'انس با الکافی';
    if (s.includes('تربیت سخنران')) return 'تربیت سخنران';
    return s.replace(/^کارگروه\s+/, '').trim() || s;
  }

  async function copyTextQuick(txt, msg) {
    try {
      await navigator.clipboard.writeText(txt);
      App.toast(msg || 'در حافظه کپی شد.');
    } catch (_) {
      const ta = document.createElement('textarea');
      ta.value = txt;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      App.toast(msg || 'در حافظه کپی شد.');
    }
  }

  const CARD_SVGS = {
    trend: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>',
    donut: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>',
    radar: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 21 7 21 17 12 22 3 17 3 7 12 2"/><polygon points="12 7 16.5 9.5 16.5 14.5 12 17 7.5 14.5 7.5 9.5 12 7"/></svg>',
    calendar: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><rect x="8" y="14" width="3" height="3" rx="0.5" fill="currentColor" stroke="none"/></svg>',
    bars: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    matrix: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/></svg>',
    crm: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    teachers: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><polyline points="16 11 18 13 22 9"/></svg>',
    pareto: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M14.5 9.2c-.5-.8-1.4-1.2-2.5-1.2-1.5 0-2.5.8-2.5 2 0 2.4 5 1.6 5 4 0 1.2-1.1 2-2.6 2-1.2 0-2.2-.5-2.7-1.3"/><line x1="12" y1="6.5" x2="12" y2="17.5"/></svg>',
    award: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/></svg>',
    report: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
  };

  function cardIconHtml(kind = 'bars', tone = 'sky') {
    return `<span class="eh-card-ico eh-ico-${tone}" aria-hidden="true">${CARD_SVGS[kind] || CARD_SVGS.bars}</span>`;
  }

  function chartCardHtml(id, title, subtitle = '', helpKey = '', iconKind = 'bars', iconTone = 'sky') {
    return `
      <div class="eh-chart-box glass-card">
        <div class="eh-chart-head">
          <div class="eh-card-title-wrap">
            ${cardIconHtml(iconKind, iconTone)}
            <div class="eh-card-title-txt">
              <div class="eh-card-title-row">
                <strong>${title}</strong>
                ${helpKey ? helpBtn(helpKey) : ''}
              </div>
              ${subtitle ? `<span class="eh-card-sub">${subtitle}</span>` : ''}
            </div>
          </div>
          <div class="eh-chart-actions">
            <button type="button" class="eh-exp-trigger" data-exp-menu="${id}" title="خروجی و کپی نمودار" aria-label="خروجی و کپی نمودار" aria-haspopup="menu" aria-expanded="false">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              <svg class="eh-exp-chev" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
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
              <button type="button" class="pro-cat-btn" data-pane="audience">${ic('users', 16)}<span>مخاطبان یکتا و پرونده ۳۶۰°</span></button>
              <button type="button" class="pro-cat-btn" data-pane="teachers_fin">${ic('userCheck', 16)}<span>اساتید و بهره‌وری مالی</span></button>
              <button type="button" class="pro-cat-btn" data-pane="builder">${ic('sliders', 16)}<span>گزارش‌ساز سفارشی</span></button>
            </div>
            <div class="pro-modal-content">
              <div class="eh-filter-bar glass-card">
                <select id="fltGroup" class="glass-select"><option value="">همه کارگروه‌ها</option></select>
                <select id="fltTeacher" class="glass-select"><option value="">همه اساتید</option></select>
                <select id="fltYear" class="glass-select"><option value="">همه سال‌ها</option></select>
                <button type="button" class="ghost-btn" id="btnResetFilters" style="padding:6px 12px; font-size:11.5px;">حذف فیلترها</button>
                ${helpBtn('exec_filters')}
              </div>

              <div class="pro-pane active" id="exec-pane-overview">
                <div class="eh-kpi-row" id="execKpiGrid"></div>
                <div class="eh-chart-grid2">
                  ${chartCardHtml('chTimeline', 'منحنی جذب مخاطب جدید در برابر مخاطب قدیمی', 'روند جذب و بازگشت مخاطبان در طول زمان', 'ch_timeline', 'trend', 'teal')}
                  ${chartCardHtml('chRetention', 'توزیع وفاداری و تعداد حضور مخاطبان', 'تفکیک مخاطبان یکتا بر اساس تداوم حضور در دوره‌ها', 'ch_retention', 'donut', 'violet')}
                </div>
                <div class="eh-chart-grid2">
                  ${chartCardHtml('chRadar', 'توازن عملکرد کارگروه‌ها (نمودار راداری)', 'مقایسه سهم مخاطبان در کارگروه‌های اصلی مؤسسه', 'ch_radar', 'radar', 'sky')}
                  ${chartCardHtml('chHeatmap', 'نقشه حرارتی برگزاری برنامه‌ها در ماه‌های سال', 'تراکم ماهانه برگزاری دوره‌های دارای تاریخ ثبت‌شده', 'ch_heatmap', 'calendar', 'amber')}
                </div>
              </div>

              <div class="pro-pane" id="exec-pane-audience">
                <div class="eh-chart-grid2">
                  ${chartCardHtml('chGroupUnique', 'مقایسه حضور کل در برابر شرکت‌کنندگان یکتا', 'نفر-دوره (میله بالا) در مقایسه با افراد منحصربه‌فرد (میله پایین)', 'ch_group_unique', 'bars', 'teal')}
                  <div class="eh-chart-box glass-card">
                    <div class="eh-chart-head">
                      <div class="eh-card-title-wrap">
                        ${cardIconHtml('matrix', 'violet')}
                        <div class="eh-card-title-txt">
                          <div class="eh-card-title-row">
                            <strong>ماتریس هم‌پوشانی کارگروه‌ها</strong>
                            ${helpBtn('affinity_matrix')}
                          </div>
                          <span class="eh-card-sub">تعداد مخاطبان مشترک بین کارگروه‌های مختلف (Cross-Group Affinity)</span>
                        </div>
                      </div>
                    </div>
                    <div id="affinityMatrixBox" class="eh-aff-wrap"></div>
                  </div>
                </div>

                <div class="eh-crm-card glass-card">
                  <div class="eh-sec-hdr">
                    <div class="eh-card-title-wrap">
                      ${cardIconHtml('crm', 'sky')}
                      <div class="eh-card-title-txt">
                        <div class="eh-card-title-row">
                          <strong>بانک جامع مخاطبان یکتاسازی‌شده و پرونده ۳۶۰ درجه</strong>
                          ${helpBtn('audience_crm')}
                        </div>
                        <span class="eh-card-sub">یکتاسازی خودکار بر اساس موبایل، کد ملی و نام • کلیک روی هر مخاطب برای باز کردن پرونده کامل، جلسات و ثبت یادداشت</span>
                      </div>
                    </div>
                    <div class="eh-sec-actions">
                      <button type="button" class="ghost-btn pro-btn-ic eh-crm-act-btn" id="btnCopyFilteredPhones" title="کپی شماره‌های لیست فیلترشده برای پیامک یا ایتا">${ic('copy', 13)}<span>کپی شماره‌ها</span></button>
                      <button type="button" class="primary-btn pro-btn-ic eh-crm-act-btn" id="btnExportFilteredParticipants" title="خروجی اکسل رسمی از دقیقاً همین لیست فیلترشده">${ic('download', 13)}<span>خروجی Excel</span></button>
                    </div>
                  </div>

                  <div class="eh-crm-kpis" id="crmKpiStrip"></div>
                  <div class="eh-crm-chips" id="crmLoyaltyChips"></div>

                  <div class="eh-crm-toolbar">
                    <div class="eh-crm-search-wrap">
                      <input id="inpSearchParticipant" class="glass-input" type="text" placeholder="جست‌وجوی نام، موبایل، کد ملی، دوره یا برچسب..."/>
                    </div>
                    <select id="crmFltGroup" class="glass-select eh-crm-select"><option value="">همه کارگروه‌ها</option></select>
                    <select id="crmFltCourse" class="glass-select eh-crm-select"><option value="">همه دوره‌ها</option></select>
                    <select id="crmFltQuality" class="glass-select eh-crm-select">
                      <option value="ALL">همه وضعیت‌های حضور</option>
                      <option value="HIGH_ATT">حضور عالی (۸۰٪ به بالا)</option>
                      <option value="LOW_ATT">کم‌حضور / نیاز به پیگیری (&lt;۶۰٪)</option>
                      <option value="HAS_PHONE">دارای شماره موبایل</option>
                      <option value="NO_PHONE">فاقد شماره موبایل</option>
                      <option value="HAS_META">دارای برچسب یا یادداشت</option>
                    </select>
                    <select id="crmSortBy" class="glass-select eh-crm-select">
                      <option value="courses_desc">مرتب‌سازی: بیشترین دوره</option>
                      <option value="att_rate_desc">بالاترین نرخ حضور (٪)</option>
                      <option value="sessions_desc">بیشترین جلسات حاضرشده</option>
                      <option value="engagement_desc">بالاترین امتیاز مشارکت</option>
                      <option value="groups_desc">بیشترین تنوع کارگروه</option>
                      <option value="att_rate_asc">کمترین حضور (اولویت پیگیری)</option>
                      <option value="name_asc">مرتب‌سازی الفبایی (نام)</option>
                    </select>
                    <button type="button" class="ghost-btn eh-crm-reset-btn" id="btnResetCrmFilters" title="پاک‌سازی فیلترهای جدول">پاک‌سازی</button>
                  </div>

                  <div class="eh-crm-table-wrap">
                    <table class="glass-table eh-crm-table">
                      <thead>
                        <tr>
                          <th class="eh-th-sort" data-crm-sort="name">نام و نام خانوادگی</th>
                          <th>شماره تماس</th>
                          <th>سطح</th>
                          <th class="eh-th-sort" data-crm-sort="courses">دوره‌ها</th>
                          <th class="eh-th-sort" data-crm-sort="att_rate">نرخ حضور واقعی</th>
                          <th class="eh-th-sort" data-crm-sort="loyalty">وفاداری</th>
                          <th>کارگروه‌ها و برچسب‌ها</th>
                        </tr>
                      </thead>
                      <tbody id="tblParticipantsBody"></tbody>
                    </table>
                  </div>

                  <div class="eh-crm-footer">
                    <span id="crmCountInfo" class="eh-crm-count-info">در حال بارگذاری...</span>
                    <div class="eh-crm-pager">
                      <button type="button" class="eh-mini-btn" id="btnCrmPrev">قبلی</button>
                      <span id="crmPageInfo">صفحه ۱ از ۱</span>
                      <button type="button" class="eh-mini-btn" id="btnCrmNext">بعدی</button>
                    </div>
                  </div>
                </div>
              </div>

              <div class="pro-pane" id="exec-pane-teachers_fin">
                <div class="eh-chart-grid2">
                  ${chartCardHtml('chTeachers', 'ماتریس اثرگذاری اساتید', 'مقایسه مخاطبان جذب‌شده (کلیک روی نام استاد برای پرونده ۳۶۰°)', 'ch_teachers', 'teachers', 'amber')}
                  ${chartCardHtml('chPareto', 'تحلیل پارتو ۸۰/۲۰ سرفصل‌های هزینه', 'بزرگ‌ترین سرفصل‌های بودجه و هزینه‌کرد مؤسسه', 'ch_pareto', 'pareto', 'amber')}
                </div>
                <div class="eh-crm-card glass-card">
                  <div class="eh-sec-hdr">
                    <div class="eh-card-title-wrap">
                      ${cardIconHtml('award', 'teal')}
                      <div class="eh-card-title-txt">
                        <div class="eh-card-title-row">
                          <strong>عملکرد تفکیکی اساتید</strong>
                          ${helpBtn('teachers_table')}
                        </div>
                        <span class="eh-card-sub">کلیک روی نام هر استاد برای باز کردن پرونده ۳۶۰ درجه و ویرایش سوابق علمی</span>
                      </div>
                    </div>
                    <input id="inpSearchTeacher" class="glass-input" type="text" placeholder="جست‌وجوی نام استاد یا کارگروه..." style="width:230px; padding:6px 11px; font-size:11.5px;"/>
                  </div>
                  <div class="eh-crm-table-wrap" style="max-height:320px;">
                    <table class="glass-table eh-crm-table">
                      <thead>
                        <tr>
                          <th class="eh-th-sort" data-tch-sort="name">نام استاد</th>
                          <th class="eh-th-sort" data-tch-sort="courses">تعداد دوره</th>
                          <th class="eh-th-sort" data-tch-sort="attendance">کل مخاطبان</th>
                          <th class="eh-th-sort" data-tch-sort="unique">مخاطبان یکتا</th>
                          <th class="eh-th-sort" data-tch-sort="avg_attendance">میانگین/دوره</th>
                          <th class="eh-th-sort" data-tch-sort="hours_effective">ساعت تدریس</th>
                          <th>کارگروه‌ها</th>
                        </tr>
                      </thead>
                      <tbody id="tblTeachersBody"></tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div class="pro-pane" id="exec-pane-builder">
                <div class="eh-crm-card glass-card">
                  <div class="eh-sec-hdr">
                    <div class="eh-card-title-wrap">
                      ${cardIconHtml('report', 'sky')}
                      <div class="eh-card-title-txt">
                        <div class="eh-card-title-row">
                          <strong>ساخت و خروجی گزارش جامع مدیریتی</strong>
                          ${helpBtn('report_builder')}
                        </div>
                        <span class="eh-card-sub">تولید خروجی با سربرگ رسمی مؤسسه علمی فرهنگی امام هادی علیه‌السلام و ثبت خودکار در دبیرخانه</span>
                      </div>
                    </div>
                    <div class="eh-preset-bar">
                      <button type="button" class="eh-mini-btn eh-preset-btn active" data-rep-preset="board">قالب هیئت‌مدیره</button>
                      <button type="button" class="eh-mini-btn eh-preset-btn" data-rep-preset="edu">قالب آموزشی و مخاطبان</button>
                      <button type="button" class="eh-mini-btn eh-preset-btn" data-rep-preset="fin">قالب مالی و اساتید</button>
                    </div>
                  </div>

                  <div class="eh-builder-grid">
                    <div class="eh-builder-form">
                      <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                        <div class="eitaa-field"><label>عنوان گزارش</label><input id="repTitle" class="glass-input" value="گزارش جامع عملکرد علمی، آموزشی و تحلیل مخاطبان یکتا"/></div>
                        <div class="eitaa-field"><label>گیرنده / مخاطب گزارش (برای ثبت در دبیرخانه)</label><input id="repRecipient" class="glass-input" value="هیئت‌مدیره و مدیریت محترم مؤسسه"/></div>
                      </div>
                      <div class="eh-chk-grid">
                        <label class="eh-chk"><input type="checkbox" id="chkKpis" checked/> شاخص‌های کلان (KPIs)</label>
                        <label class="eh-chk"><input type="checkbox" id="chkChTimeline" checked/> نمودار روند جذب مخاطبان</label>
                        <label class="eh-chk"><input type="checkbox" id="chkChGroup" checked/> نمودار کارگروه‌ها (کل و یکتا)</label>
                        <label class="eh-chk"><input type="checkbox" id="chkChTeachers" checked/> نمودار عملکرد اساتید</label>
                        <label class="eh-chk"><input type="checkbox" id="chkChPareto" checked/> نمودار پارتو هزینه‌ها</label>
                        <label class="eh-chk"><input type="checkbox" id="chkTblGroups" checked/> جدول تفکیکی کارگروه‌ها</label>
                        <label class="eh-chk"><input type="checkbox" id="chkTblTeachers" checked/> جدول عملکرد اساتید</label>
                        <label class="eh-chk"><input type="checkbox" id="chkTblParticipants"/> جدول مخاطبان برتر (۳۶۰°)</label>
                      </div>
                      <div style="display:flex; flex-wrap:wrap; gap:10px; padding-top:8px;">
                        <button type="button" class="primary-btn pro-btn-ic" data-export-exec="pdf" style="padding:9px 18px;">${ic('fileText', 15)}<span>خروجی PDF رسمی همراه با نمودار</span></button>
                        <button type="button" class="ghost-btn pro-btn-ic" data-export-exec="docx" style="padding:9px 18px;">${ic('fileText', 15)}<span>خروجی Word رسمی همراه با نمودار</span></button>
                        <button type="button" class="ghost-btn pro-btn-ic" data-export-exec="xlsx" style="padding:9px 18px;">${ic('download', 15)}<span>خروجی Excel تحلیلی چندشیته</span></button>
                      </div>
                    </div>

                    <div class="eh-rep-preview" id="repPreviewBox"></div>
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
          if (btn.dataset.pane === 'builder') updateReportPreview(bd);
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
        ['fltGroup', 'fltTeacher', 'fltYear'].forEach(id => {
          const el = bd.querySelector('#' + id);
          if (el) { el.value = ''; el.dispatchEvent(new Event('change')); }
        });
      });

      bd.querySelector('#btnRefreshExec').addEventListener('click', () => loadAndDrawAnalytics(bd, true));
      bd.querySelector('#btnOpenBoardroom').addEventListener('click', () => openBoardroom());

      bd.querySelector('#inpSearchParticipant').addEventListener('input', (e) => {
        partState.search = e.target.value || '';
        partState.page = 1;
        drawParticipantsTable(bd);
      });
      bd.querySelector('#crmFltGroup').addEventListener('change', (e) => {
        partState.group = e.target.value || '';
        partState.page = 1;
        drawParticipantsTable(bd);
      });
      bd.querySelector('#crmFltCourse').addEventListener('change', (e) => {
        partState.course = e.target.value || '';
        partState.page = 1;
        drawParticipantsTable(bd);
      });
      bd.querySelector('#crmFltQuality').addEventListener('change', (e) => {
        partState.quality = e.target.value || 'ALL';
        partState.page = 1;
        drawParticipantsTable(bd);
      });
      bd.querySelector('#crmSortBy').addEventListener('change', (e) => {
        partState.sortBy = e.target.value || 'courses_desc';
        partState.page = 1;
        drawParticipantsTable(bd);
      });
      bd.querySelector('#btnResetCrmFilters').addEventListener('click', () => {
        partState.search = '';
        partState.loyalty = 'ALL';
        partState.group = '';
        partState.course = '';
        partState.quality = 'ALL';
        partState.sortBy = 'courses_desc';
        partState.page = 1;
        const inp = bd.querySelector('#inpSearchParticipant'); if (inp) inp.value = '';
        ['crmFltGroup', 'crmFltCourse'].forEach(id => { const s = bd.querySelector('#' + id); if (s) { s.value = ''; s.dispatchEvent(new Event('change')); } });
        const fq = bd.querySelector('#crmFltQuality'); if (fq) { fq.value = 'ALL'; fq.dispatchEvent(new Event('change')); }
        const sb = bd.querySelector('#crmSortBy'); if (sb) { sb.value = 'courses_desc'; sb.dispatchEvent(new Event('change')); }
        drawParticipantsTable(bd);
      });

      bd.querySelectorAll('[data-crm-sort]').forEach(th => {
        th.addEventListener('click', () => {
          const col = th.dataset.crmSort;
          const mapToggle = {
            name: ['name_asc', 'name_desc'],
            courses: ['courses_desc', 'courses_asc'],
            att_rate: ['att_rate_desc', 'att_rate_asc'],
            loyalty: ['loyalty_desc', 'loyalty_asc'],
          };
          const [a, b] = mapToggle[col] || ['courses_desc', 'courses_asc'];
          partState.sortBy = (partState.sortBy === a) ? b : a;
          partState.page = 1;
          const sb = bd.querySelector('#crmSortBy');
          if (sb && Array.from(sb.options).some(o => o.value === partState.sortBy)) {
            sb.value = partState.sortBy;
            sb.dispatchEvent(new Event('change'));
          } else {
            drawParticipantsTable(bd);
          }
        });
      });

      bd.querySelector('#btnCrmPrev').addEventListener('click', () => {
        if (partState.page > 1) { partState.page -= 1; drawParticipantsTable(bd); }
      });
      bd.querySelector('#btnCrmNext').addEventListener('click', () => {
        const totalP = Math.max(1, Math.ceil((partState.filtered || []).length / partState.pageSize));
        if (partState.page < totalP) { partState.page += 1; drawParticipantsTable(bd); }
      });

      bd.querySelector('#btnCopyFilteredPhones').addEventListener('click', () => {
        const phones = (partState.filtered || []).map(p => p.phone).filter(Boolean);
        const uniquePhones = Array.from(new Set(phones));
        if (!uniquePhones.length) {
          App.toast('در لیست فیلترشده شماره تماسی یافت نشد.');
          return;
        }
        copyTextQuick(uniquePhones.join('\n'), `${Ch.fmtNum(uniquePhones.length)} شماره تماس یکتا در حافظه کپی شد.`);
      });

      bd.querySelector('#btnExportFilteredParticipants').addEventListener('click', async () => {
        const list = partState.filtered || [];
        if (!list.length) {
          App.toast('لیست مخاطبان برای خروجی خالی است.');
          return;
        }
        const rows = list.map((p, idx) => [
          idx + 1,
          p.name || '',
          p.phone || '',
          p.nid || '',
          p.level || '',
          p.courses_count || 0,
          p.attended_sessions || 0,
          p.total_sessions || 0,
          p.attendance_rate !== null && p.attendance_rate !== undefined ? `${p.attendance_rate}%` : '—',
          p.loyalty || '',
          p.engagement_score || 0,
          (p.groups || []).join('، '),
          (p.tags || []).join('، '),
          p.notes || '',
        ]);
        const res = await window.pywebview?.api?.export_filtered_participants_excel?.({
          title: `فهرست مخاطبان یکتاسازی‌شده (${list.length} نفر)`,
          rows,
        });
        if (res && res.ok) App.toast(`فایل اکسل با ${Ch.fmtNum(res.count)} مخاطب با موفقیت ذخیره شد.`);
        else if (res && !res.cancelled) App.toast(res.error || 'خطا در خروجی اکسل');
      });

      bd.querySelector('#inpSearchTeacher').addEventListener('input', (e) => {
        tchState.search = (e.target.value || '').trim().toLowerCase();
        drawTeachersTable(bd);
      });
      bd.querySelectorAll('[data-tch-sort]').forEach(th => {
        th.addEventListener('click', () => {
          const col = th.dataset.tchSort;
          if (tchState.sortBy === col) tchState.sortDir = tchState.sortDir === 'desc' ? 'asc' : 'desc';
          else { tchState.sortBy = col; tchState.sortDir = col === 'name' ? 'asc' : 'desc'; }
          drawTeachersTable(bd);
        });
      });

      bd.querySelectorAll('[data-rep-preset]').forEach(btn => {
        btn.addEventListener('click', () => {
          bd.querySelectorAll('[data-rep-preset]').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const mode = btn.dataset.repPreset;
          const setChk = (id, v) => { const c = bd.querySelector('#' + id); if (c) c.checked = v; };
          if (mode === 'board') {
            bd.querySelector('#repTitle').value = 'گزارش جامع عملکرد علمی، آموزشی و مالی برای هیئت‌مدیره';
            setChk('chkKpis', true); setChk('chkChTimeline', true); setChk('chkChGroup', true);
            setChk('chkChTeachers', true); setChk('chkChPareto', true); setChk('chkTblGroups', true);
            setChk('chkTblTeachers', true); setChk('chkTblParticipants', false);
          } else if (mode === 'edu') {
            bd.querySelector('#repTitle').value = 'گزارش تخصصی آموزش، کارگروه‌ها و تحلیل مخاطبان یکتا';
            setChk('chkKpis', true); setChk('chkChTimeline', true); setChk('chkChGroup', true);
            setChk('chkChTeachers', false); setChk('chkChPareto', false); setChk('chkTblGroups', true);
            setChk('chkTblTeachers', false); setChk('chkTblParticipants', true);
          } else if (mode === 'fin') {
            bd.querySelector('#repTitle').value = 'گزارش بهره‌وری اساتید و تحلیل پارتو سرفصل‌های هزینه';
            setChk('chkKpis', true); setChk('chkChTimeline', false); setChk('chkChGroup', false);
            setChk('chkChTeachers', true); setChk('chkChPareto', true); setChk('chkTblGroups', false);
            setChk('chkTblTeachers', true); setChk('chkTblParticipants', false);
          }
          updateReportPreview(bd);
        });
      });

      bd.querySelectorAll('#exec-pane-builder input').forEach(inp => {
        inp.addEventListener('input', () => updateReportPreview(bd));
        inp.addEventListener('change', () => updateReportPreview(bd));
      });

      let activeExpPop = null;
      const closeExpMenu = () => {
        if (activeExpPop) {
          activeExpPop.el.remove();
          activeExpPop.btn.classList.remove('active');
          activeExpPop.btn.setAttribute('aria-expanded', 'false');
          activeExpPop = null;
        }
      };

      const openExpMenu = (btn, chartId) => {
        if (activeExpPop && activeExpPop.btn === btn) {
          closeExpMenu();
          return;
        }
        closeExpMenu();
        const box = bd.querySelector('#' + chartId);
        if (!box) return;

        const pop = document.createElement('div');
        pop.className = 'eh-exp-popover';
        pop.setAttribute('role', 'menu');
        pop.innerHTML = `
          <button type="button" class="eh-exp-item" data-exp-act="copy" role="menuitem">
            <span class="eh-exp-item-ico eh-ico-sky">${ic('copy', 14)}</span>
            <span class="eh-exp-item-txt"><strong>کپی تصویر در حافظه</strong><small>آماده ارسال در ایتا و پاورپوینت</small></span>
          </button>
          <button type="button" class="eh-exp-item" data-exp-act="png" role="menuitem">
            <span class="eh-exp-item-ico eh-ico-teal">${ic('download', 14)}</span>
            <span class="eh-exp-item-txt"><strong>دانلود تصویر باکیفیت (PNG)</strong><small>مناسب گزارش‌های رسمی و اسلاید</small></span>
          </button>
          <button type="button" class="eh-exp-item" data-exp-act="svg" role="menuitem">
            <span class="eh-exp-item-ico eh-ico-violet"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg></span>
            <span class="eh-exp-item-txt"><strong>دانلود برداری لایه‌باز (SVG)</strong><small>مناسب ایلاستریتور و چاپ</small></span>
          </button>
        `;
        pop.addEventListener('click', (e) => e.stopPropagation());
        pop.querySelectorAll('[data-exp-act]').forEach(it => {
          it.addEventListener('click', () => {
            const act = it.dataset.expAct;
            closeExpMenu();
            if (act === 'copy') {
              Ch.copyChartToClipboard(box);
            } else {
              Ch.downloadChart(box, `ehadi_${chartId}`, act);
              App.toast(`نمودار با فرمت ${act.toUpperCase()} ذخیره شد.`);
            }
          });
        });

        document.body.appendChild(pop);
        const r = btn.getBoundingClientRect();
        const popW = 228;
        pop.style.width = `${popW}px`;
        const popH = pop.offsetHeight || 156;
        let top = r.bottom + 6;
        if (top + popH > window.innerHeight - 12) top = Math.max(12, r.top - popH - 6);
        let left = r.left;
        if (left + popW > window.innerWidth - 12) left = Math.max(12, r.right - popW);
        pop.style.top = `${Math.round(top)}px`;
        pop.style.left = `${Math.round(left)}px`;

        btn.classList.add('active');
        btn.setAttribute('aria-expanded', 'true');
        requestAnimationFrame(() => pop.classList.add('open'));
        activeExpPop = { el: pop, btn };
      };

      bd.querySelectorAll('[data-exp-menu]').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          openExpMenu(btn, btn.dataset.expMenu);
        });
      });

      if (!window.__ehExpMenuBound) {
        window.__ehExpMenuBound = true;
        document.addEventListener('click', () => closeExpMenu());
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeExpMenu(); });
        window.addEventListener('resize', closeExpMenu);
        window.addEventListener('scroll', (e) => {
          if (activeExpPop && (e.target === activeExpPop.el || activeExpPop.el.contains(e.target))) return;
          closeExpMenu();
        }, true);
      }

      bd.querySelectorAll('[data-export-exec]').forEach(btn => {
        btn.addEventListener('click', () => runExecutiveExport(bd, btn.dataset.exportExec));
      });
    },
    onOpen(bd) { loadAndDrawAnalytics(bd); },
  });

  function showExecSkeletons(bd) {
    const kpiEl = bd.querySelector('#execKpiGrid');
    if (kpiEl && !kpiEl.children.length) {
      kpiEl.innerHTML = Array.from({ length: 5 }, () =>
        '<div class="eh-kpi glass-card eh-skel-card"><div class="eh-skel-line" style="width:55%; height:10px;"></div><div class="eh-skel-line" style="width:72%; height:22px; margin-top:8px;"></div><div class="eh-skel-line" style="width:45%; height:9px; margin-top:7px;"></div></div>'
      ).join('');
    }
    ['#chTimeline', '#chRetention', '#chRadar', '#chHeatmap', '#chGroupUnique', '#chTeachers', '#chPareto'].forEach(sel => {
      const el = bd.querySelector(sel);
      if (el && !el.querySelector('svg')) {
        el.innerHTML = '<div class="eh-skel-stage"><div class="eh-skel-bar" style="width:86%"></div><div class="eh-skel-bar" style="width:68%"></div><div class="eh-skel-bar" style="width:78%"></div><div class="eh-skel-bar" style="width:54%"></div></div>';
      }
    });
  }

  function triggerSmoothReveal(bd) {
    const targets = bd.querySelectorAll('#execKpiGrid .eh-kpi, .eh-chart-stage > svg, #affinityMatrixBox > table, #tblTeachersBody, #tblParticipantsBody');
    targets.forEach((el, idx) => {
      el.classList.remove('eh-exec-reveal');
      void el.offsetWidth;
      el.style.animationDelay = `${Math.min(idx * 24, 140)}ms`;
      el.classList.add('eh-exec-reveal');
    });
  }

  async function loadAndDrawAnalytics(bd, forceRefresh = false) {
    const isDefaultFilter = !currentFilters.group && !currentFilters.teacher && !currentFilters.year;
    let res = null;
    if (!forceRefresh && isDefaultFilter) {
      if (lastAnalytics && lastAnalytics.ok) res = lastAnalytics;
      else if (window.__ehExecCache && window.__ehExecCache.ok) res = window.__ehExecCache;
    }
    if (!res) {
      showExecSkeletons(bd);
      const reqPayload = forceRefresh ? { ...currentFilters, _force: true } : currentFilters;
      res = await window.pywebview?.api?.get_executive_analytics?.(reqPayload);
      if (!res || !res.ok) return;
      if (isDefaultFilter) window.__ehExecCache = res;
    } else {
      // Silently verify freshness in background after instant paint if coming from boot cache
      const bootSnap = res;
      window.pywebview?.api?.get_executive_analytics?.(currentFilters)?.then(fresh => {
        if (fresh && fresh.ok && isDefaultFilter) window.__ehExecCache = fresh;
        if (fresh && fresh.ok && bootSnap !== fresh && fresh.kpis && bootSnap.kpis &&
            (fresh.kpis.total_attendance !== bootSnap.kpis.total_attendance ||
             fresh.kpis.unique_participants !== bootSnap.kpis.unique_participants ||
             fresh.kpis.total_cost !== bootSnap.kpis.total_cost)) {
          lastAnalytics = fresh;
          loadAndDrawAnalytics(bd, false);
        }
      }).catch(() => {});
    }
    lastAnalytics = res;

    const fillSel = (id, list, allLbl, curVal) => {
      const sel = bd.querySelector('#' + id);
      if (!sel) return;
      sel.textContent = '';
      const defOpt = document.createElement('option');
      defOpt.value = '';
      defOpt.textContent = allLbl;
      sel.appendChild(defOpt);
      const items = Array.isArray(list) ? list : [];
      let matched = false;
      items.forEach(x => {
        const val = String(x ?? '');
        if (!val) return;
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val;
        if (val === String(curVal || '')) { opt.selected = true; matched = true; }
        sel.appendChild(opt);
      });
      sel.value = matched ? String(curVal || '') : '';
    };
    fillSel('fltGroup', res.filters_meta?.groups, 'همه کارگروه‌ها', currentFilters.group);
    fillSel('fltTeacher', res.filters_meta?.teachers, 'همه اساتید', currentFilters.teacher);
    fillSel('fltYear', res.filters_meta?.years, 'همه سال‌ها', currentFilters.year);

    const k = res.kpis || {};
    const costUnit = res.cost_unit || k.cost_unit || 'ریال';
    const uniqNote = res.has_person_level ? 'محاسبه دقیق فردی' : 'نیاز به فایل فردی/پرس‌لاین';
    bd.querySelector('#execKpiGrid').innerHTML = [
      ['شرکت‌کنندگان یکتا', res.has_person_level ? Ch.fmtNum(k.unique_participants) : '—', uniqNote],
      ['مجموع حضور کل', Ch.fmtNum(k.total_attendance), `در ${Ch.fmtNum(k.total_courses)} دوره و رویداد`],
      ['نرخ بازگشت و وفاداری', res.has_person_level ? `${Ch.toFa(k.repeat_rate)}٪` : `${Ch.toFa(k.avg_per_course)} نفر`, `میانگین ${Ch.toFa(k.avg_per_course)} نفر/دوره`],
      ['اساتید و کارگروه‌ها', `${Ch.fmtNum(k.total_teachers)} / ${Ch.fmtNum(k.total_groups)}`, `سلامت داده: ${Ch.toFa(k.data_health_score)}٪`],
      ['هزینه هر مخاطب', k.cost_per_attendee ? `${Ch.fmtNum(k.cost_per_attendee)} ${costUnit}` : 'ثبت نشده', `کل هزینه: ${Ch.fmtNum(k.total_cost)} ${costUnit}`],
    ].map(([l, v, s]) => `<div class="eh-kpi glass-card"><div class="eh-kpi-l">${l}</div><div class="eh-kpi-v">${v}</div><div class="eh-kpi-s">${s}</div></div>`).join('');

    const tl = res.timeline || [];
    const datedTl = tl.filter(x => x.label && x.label !== 'نامشخص');
    const hasMultiDatedTl = datedTl.length >= 2;
    const hasPersonTl = res.has_person_level && hasMultiDatedTl && datedTl.some(x => (x.new_participants || 0) + (x.returning_participants || 0) > 0);
    const fCourses = res.filtered_courses || [];

    if (hasPersonTl || hasMultiDatedTl) {
      const tlBox = bd.querySelector('#chTimeline')?.closest('.eh-chart-box');
      if (tlBox) {
        const tlT = tlBox.querySelector('.eh-card-title-row strong');
        const tlS = tlBox.querySelector('.eh-card-sub');
        if (tlT) tlT.textContent = 'منحنی جذب مخاطب جدید در برابر مخاطب قدیمی';
        if (tlS) tlS.textContent = 'روند جذب و بازگشت مخاطبان در طول زمان';
      }
    }
    if (hasPersonTl) {
      Ch.renderSplineArea(
        bd.querySelector('#chTimeline'),
        [
          { name: 'مخاطبان جدید', values: datedTl.map(x => x.new_participants), color: '#10b981' },
          { name: 'مخاطبان قدیمی', values: datedTl.map(x => x.returning_participants), color: '#0ea5e9' },
        ],
        datedTl.map(x => x.label),
        { id: 'tl' }
      );
    } else if (hasMultiDatedTl) {
      Ch.renderSplineArea(
        bd.querySelector('#chTimeline'),
        [
          { name: 'مجموع مخاطبان', values: datedTl.map(x => x.attendance || 0), color: '#10b981' },
          { name: 'تعداد دوره‌ها', values: datedTl.map(x => x.courses || 0), color: '#38bdf8' },
        ],
        datedTl.map(x => x.label),
        { id: 'tl' }
      );
    } else if (fCourses.length) {
      const tlBox = bd.querySelector('#chTimeline')?.closest('.eh-chart-box');
      if (tlBox) {
        const tlT = tlBox.querySelector('.eh-card-title-row strong');
        const tlS = tlBox.querySelector('.eh-card-sub');
        if (tlT) tlT.textContent = 'پرمخاطب‌ترین دوره‌ها و نشست‌ها';
        if (tlS) tlS.textContent = 'مقایسه بیشترین تعداد شرکت‌کنندگان (با ثبت تاریخ چندساله به منحنی زمانی تبدیل می‌شود)';
      }
      Ch.renderHBar(
        bd.querySelector('#chTimeline'),
        fCourses.slice(0, 7).map(c => ({ label: c.title, v1: c.attendance || 0 })),
        { c1: '#10b981', limit: 7 }
      );
    } else {
      Ch.renderSplineArea(bd.querySelector('#chTimeline'), [], [], { id: 'tl' });
    }

    const retItems = (res.retention || []).map(x => ({ label: x.label, value: x.count }));
    const retTotal = retItems.reduce((a, b) => a + Number(b.value || 0), 0);
    if (retTotal > 0) {
      Ch.renderDonut(bd.querySelector('#chRetention'), retItems, 'مخاطبان یکتا');
    } else if (currentFilters.teacher && fCourses.length) {
      Ch.renderDonut(bd.querySelector('#chRetention'), fCourses.slice(0, 6).map(c => ({ label: c.title, value: c.attendance || 1 })), 'مخاطب دوره‌ها');
    } else if ((res.groups || []).length) {
      Ch.renderDonut(bd.querySelector('#chRetention'), (res.groups || []).slice(0, 6).map(g => ({ label: g.name, value: g.attendance || g.courses })), 'مخاطب کل');
    } else {
      Ch.renderDonut(bd.querySelector('#chRetention'), retItems, 'مخاطبان یکتا');
    }

    if ((res.groups || []).length >= 3) {
      Ch.renderRadar(bd.querySelector('#chRadar'), (res.groups || []).map(g => ({ label: g.name, value: g.attendance })));
    } else if (fCourses.length) {
      Ch.renderHBar(bd.querySelector('#chRadar'), fCourses.slice(0, 8).map(c => ({ label: c.title, v1: c.attendance || 0 })), { c1: '#38bdf8' });
    } else {
      Ch.renderHBar(bd.querySelector('#chRadar'), (res.groups || []).map(g => ({ label: g.name, v1: g.attendance || 0 })), { c1: '#38bdf8' });
    }
    Ch.renderHeatmap(bd.querySelector('#chHeatmap'), res.heatmap || []);

    Ch.renderHBar(
      bd.querySelector('#chGroupUnique'),
      (res.groups || []).map(g => ({ label: g.name, v1: g.attendance, v2: g.unique })),
      { c1: '#10b981', c2: '#38bdf8', forceDual: Boolean(res.has_person_level) }
    );
    const teachersByAtt = (res.teachers || []).slice().sort((a, b) => (Number(b.attendance || 0) - Number(a.attendance || 0)) || (Number(b.courses || 0) - Number(a.courses || 0)));
    Ch.renderHBar(
      bd.querySelector('#chTeachers'),
      teachersByAtt.map(t => ({ label: t.name, v1: t.attendance, v2: t.unique })),
      { isTeacher: true }
    );
    Ch.renderHBar(
      bd.querySelector('#chPareto'),
      (res.pareto_costs || []).map(c => ({ label: c.category, v1: c.amount })),
      { c1: '#f59e0b', compact: true, unit: costUnit }
    );

    const aff = res.affinity_matrix || { labels: [], matrix: [] };
    const affBox = bd.querySelector('#affinityMatrixBox');
    if (affBox) {
      if (aff.labels && aff.labels.length && res.has_person_level) {
        const flatVals = aff.matrix.flat ? aff.matrix.flat() : [];
        const maxVal = Math.max(1, ...flatVals);
        const ths = '<th>کارگروه</th>' + aff.labels.map(l => `<th title="${escH(l)}">${escH(shortWgName(l))}</th>`).join('');
        const trs = aff.labels.map((l, i) => `<tr><th title="${escH(l)}">${escH(shortWgName(l))}</th>` + (aff.matrix[i] || []).map((v, j) => {
          const isDiag = i === j;
          const dispVal = (isDiag && v === 0) ? (res.groups[i]?.unique || 0) : v;
          const a = dispVal ? (isDiag ? 0.42 : (0.14 + (dispVal / maxVal) * 0.56)).toFixed(2) : '0';
          const tip = isDiag
            ? `${l}: ${Ch.fmtNum(dispVal)} مخاطب یکتا`
            : `اشتراک «${l}» و «${aff.labels[j]}»: ${Ch.fmtNum(dispVal)} مخاطب مشترک`;
          const cls = isDiag ? 'eh-aff-diag' : (dispVal > 0 ? 'eh-aff-hit' : 'eh-aff-zero');
          return `<td class="${cls}" title="${escH(tip)}" style="${dispVal ? `background:rgba(var(--lg-accent-rgb),${a});` : ''}">${Ch.fmtNum(dispVal)}</td>`;
        }).join('') + '</tr>').join('');
        affBox.innerHTML = `<table class="glass-table eh-aff-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
      } else {
        affBox.innerHTML = `
          <div class="eh-empty-chart" style="display:flex; flex-direction:column; align-items:center; gap:10px;">
            <span>برای محاسبه دقیق هم‌پوشانی کارگروه‌ها، فایل‌های ثبت‌نام پرس‌لاین یا لیست حضورغیاب را وارد کنید.</span>
            <button type="button" class="ghost-btn" id="btnGoPorslineFromAff" style="padding:6px 14px; font-size:11.5px;">ورود فایل پرس‌لاین</button>
          </div>`;
        affBox.querySelector('#btnGoPorslineFromAff')?.addEventListener('click', () => App.openModal('porsline_hub'));
      }
    }

    const allParts = res.participants || [];
    const crmGroups = Array.from(new Set(allParts.flatMap(p => p.groups || []))).sort((a, b) => a.localeCompare(b, 'fa'));
    const crmCourses = Array.from(new Set(allParts.flatMap(p => p.courses || []))).sort((a, b) => a.localeCompare(b, 'fa'));
    fillSel('crmFltGroup', crmGroups, 'همه کارگروه‌ها', partState.group);
    fillSel('crmFltCourse', crmCourses, 'همه دوره‌ها', partState.course);

    drawTeachersTable(bd);
    drawParticipantsTable(bd);
    updateReportPreview(bd);
    window.__ehScanSelects?.(bd);
    triggerSmoothReveal(bd);
  }

  function drawTeachersTable(bd) {
    if (!lastAnalytics) return;
    const q = tchState.search || '';
    const list = (lastAnalytics.teachers || []).filter(t => {
      if (!q) return true;
      return (t.name || '').toLowerCase().includes(q) || (t.groups || []).join(' ').toLowerCase().includes(q);
    });
    const dir = tchState.sortDir === 'asc' ? 1 : -1;
    list.sort((a, b) => {
      if (tchState.sortBy === 'name') return dir * String(a.name || '').localeCompare(String(b.name || ''), 'fa');
      return dir * (Number(a[tchState.sortBy] || 0) - Number(b[tchState.sortBy] || 0));
    });

    bd.querySelectorAll('[data-tch-sort]').forEach(th => {
      th.classList.toggle('sorted-asc', th.dataset.tchSort === tchState.sortBy && tchState.sortDir === 'asc');
      th.classList.toggle('sorted-desc', th.dataset.tchSort === tchState.sortBy && tchState.sortDir === 'desc');
    });

    bd.querySelector('#tblTeachersBody').innerHTML = list.map(t => `
      <tr>
        <td><button type="button" class="eh-link-btn" data-open-teacher="${escH(t.name)}">${escH(t.name)}</button></td>
        <td><strong>${Ch.fmtNum(t.courses)}</strong></td>
        <td>${Ch.fmtNum(t.attendance)}</td>
        <td>${t.unique ? Ch.fmtNum(t.unique) : '—'}</td>
        <td>${Ch.toFa(t.avg_attendance)}</td>
        <td>${t.hours_effective ? Ch.toFa(t.hours_effective) + ' ساعت' : '—'}</td>
        <td>${(t.groups || []).map(g => `<span class="eh-mini-tag">${escH(shortWgName(g))}</span>`).join(' ')}</td>
      </tr>
    `).join('') || '<tr><td colspan="7" style="text-align:center; padding:18px; color:var(--s-text-muted);">استادی با این مشخصات یافت نشد.</td></tr>';

    bd.querySelectorAll('[data-open-teacher]').forEach(btn => {
      btn.addEventListener('click', () => openTeacherDrawer(btn.dataset.openTeacher));
    });
  }

  function drawParticipantsTable(bd) {
    if (!lastAnalytics) return;
    const all = lastAnalytics.participants || [];
    const q = (partState.search || '').trim().toLowerCase();

    const baseFiltered = all.filter(p => {
      if (partState.group && !(p.groups || []).includes(partState.group)) return false;
      if (partState.course && !(p.courses || []).includes(partState.course)) return false;
      if (partState.quality === 'HIGH_ATT' && !(p.attendance_rate !== null && p.attendance_rate >= 80)) return false;
      if (partState.quality === 'LOW_ATT' && !(p.attendance_rate !== null && p.attendance_rate < 60)) return false;
      if (partState.quality === 'HAS_PHONE' && !p.phone) return false;
      if (partState.quality === 'NO_PHONE' && p.phone) return false;
      if (partState.quality === 'HAS_META' && !p.notes && !(p.tags && p.tags.length)) return false;
      if (q) {
        const hay = `${p.name || ''} ${p.phone || ''} ${p.nid || ''} ${(p.courses || []).join(' ')} ${(p.groups || []).join(' ')} ${(p.tags || []).join(' ')} ${p.notes || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    const loyCounts = { ALL: baseFiltered.length, 'هسته اصلی': 0, 'مخاطب وفادار': 0, 'مخاطب فعال': 0, 'مخاطب جدید': 0 };
    baseFiltered.forEach(p => { if (loyCounts[p.loyalty] !== undefined) loyCounts[p.loyalty] += 1; });

    const chipsEl = bd.querySelector('#crmLoyaltyChips');
    if (chipsEl) {
      const chipDefs = [
        ['ALL', 'همه مخاطبان', ''],
        ['هسته اصلی', 'هسته اصلی (۵+)', 'eh-loy-core'],
        ['مخاطب وفادار', 'وفادار (۳-۴)', 'eh-loy-loyal'],
        ['مخاطب فعال', 'فعال (۲)', 'eh-loy-active'],
        ['مخاطب جدید', 'جدید (۱)', 'eh-loy-new'],
      ];
      chipsEl.innerHTML = chipDefs.map(([key, lbl, cls]) => `
        <button type="button" class="eh-loy-chip ${cls} ${partState.loyalty === key ? 'active' : ''}" data-loy-chip="${key}">
          <span>${lbl}</span>
          <span class="eh-loy-cnt">${Ch.fmtNum(loyCounts[key] || 0)}</span>
        </button>
      `).join('');
      chipsEl.querySelectorAll('[data-loy-chip]').forEach(ch => {
        ch.addEventListener('click', () => {
          partState.loyalty = ch.dataset.loyChip;
          partState.page = 1;
          drawParticipantsTable(bd);
        });
      });
    }

    const list = baseFiltered.filter(p => partState.loyalty === 'ALL' || p.loyalty === partState.loyalty);

    const rateVal = (p, fallback) => (p.attendance_rate !== null && p.attendance_rate !== undefined) ? Number(p.attendance_rate) : fallback;
    list.sort((a, b) => {
      switch (partState.sortBy) {
        case 'courses_asc': return (a.courses_count - b.courses_count) || a.name.localeCompare(b.name, 'fa');
        case 'att_rate_desc': return (rateVal(b, -1) - rateVal(a, -1)) || (b.courses_count - a.courses_count);
        case 'att_rate_asc': return (rateVal(a, 999) - rateVal(b, 999)) || (b.courses_count - a.courses_count);
        case 'sessions_desc': return ((b.attended_sessions || 0) - (a.attended_sessions || 0)) || (b.courses_count - a.courses_count);
        case 'engagement_desc': return ((b.engagement_score || 0) - (a.engagement_score || 0)) || (b.courses_count - a.courses_count);
        case 'groups_desc': return ((b.groups_count || 0) - (a.groups_count || 0)) || (b.courses_count - a.courses_count);
        case 'loyalty_desc': return ((b.loyalty_rank || 0) - (a.loyalty_rank || 0)) || (b.courses_count - a.courses_count);
        case 'loyalty_asc': return ((a.loyalty_rank || 0) - (b.loyalty_rank || 0)) || (a.courses_count - b.courses_count);
        case 'name_asc': return a.name.localeCompare(b.name, 'fa');
        case 'name_desc': return b.name.localeCompare(a.name, 'fa');
        case 'courses_desc':
        default:
          return (b.courses_count - a.courses_count) || (rateVal(b, -1) - rateVal(a, -1)) || a.name.localeCompare(b.name, 'fa');
      }
    });

    partState.filtered = list;

    const kpiStrip = bd.querySelector('#crmKpiStrip');
    if (kpiStrip) {
      const retCnt = list.filter(p => p.courses_count >= 2).length;
      const retPct = list.length ? Math.round((retCnt / list.length) * 100) : 0;
      const rated = list.filter(p => p.attendance_rate !== null && p.attendance_rate !== undefined);
      const avgAtt = rated.length ? Math.round(rated.reduce((s, p) => s + Number(p.attendance_rate), 0) / rated.length) : null;
      const phoneCnt = list.filter(p => Boolean(p.phone)).length;
      const phonePct = list.length ? Math.round((phoneCnt / list.length) * 100) : 0;
      kpiStrip.innerHTML = [
        ['مخاطبان یکتای فیلترشده', Ch.fmtNum(list.length), `از مجموع ${Ch.fmtNum(all.length)} نفر`],
        ['مخاطبان بازگشتی (۲+ دوره)', `${Ch.fmtNum(retCnt)} نفر`, `${Ch.toFa(retPct)}٪ این گروه`],
        ['میانگین نرخ حضور واقعی', avgAtt !== null ? `${Ch.toFa(avgAtt)}٪` : '—', rated.length ? `بر اساس ${Ch.fmtNum(rated.length)} پرونده جلسه‌دار` : 'بدون ستون جلسه'],
        ['پوشش شماره تماس', `${Ch.toFa(phonePct)}٪`, `${Ch.fmtNum(phoneCnt)} شماره آماده پیامک`],
      ].map(([l, v, s]) => `<div class="eh-crm-kpi"><div class="eh-crm-kpi-l">${l}</div><div class="eh-crm-kpi-v">${v}</div><div class="eh-crm-kpi-s">${s}</div></div>`).join('');
    }

    const totalPages = Math.max(1, Math.ceil(list.length / partState.pageSize));
    if (partState.page > totalPages) partState.page = totalPages;
    const startIdx = (partState.page - 1) * partState.pageSize;
    const pageItems = list.slice(startIdx, startIdx + partState.pageSize);

    bd.querySelector('#tblParticipantsBody').innerHTML = pageItems.map(p => {
      const hasRate = p.attendance_rate !== null && p.attendance_rate !== undefined && p.total_sessions > 0;
      const ratePct = hasRate ? Math.round(p.attendance_rate) : 0;
      const rateColor = ratePct >= 80 ? '#10b981' : (ratePct >= 50 ? '#f59e0b' : '#f43f5e');
      const attCell = hasRate
        ? `<div class="eh-att-cell">
             <div class="eh-att-meta"><span>${Ch.fmtNum(p.attended_sessions)}/${Ch.fmtNum(p.total_sessions)} جلسه</span><strong style="color:${rateColor};">${Ch.toFa(ratePct)}٪</strong></div>
             <div class="eh-att-track"><div class="eh-att-fill" style="width:${Math.max(4, ratePct)}%; background:${rateColor};"></div></div>
           </div>`
        : '<span style="color:var(--s-text-dim); font-size:11px;">ثبت نشده</span>';

      const mergedPill = (p.merged_variants && p.merged_variants.length)
        ? `<span class="eh-merge-pill" title="یکتاشده با: ${escH(p.merged_variants.join('، '))}">یکتاشده</span>` : '';
      const noteDot = p.notes ? `<span class="eh-note-dot" title="یادداشت: ${escH(p.notes)}">📝</span>` : '';
      const tagsHtml = (p.tags || []).slice(0, 2).map(tg => `<span class="eh-crm-tag">${escH(tg)}</span>`).join('');
      const groupsHtml = (p.groups || []).slice(0, 2).map(g => `<span class="eh-mini-tag">${escH(shortWgName(g))}</span>`).join('');

      return `
        <tr class="eh-crm-row">
          <td>
            <div class="eh-person-cell">
              <span class="eh-avatar ${loyaltyClass(p.loyalty)}">${escH(avatarInitials(p.name))}</span>
              <div class="eh-person-meta">
                <button type="button" class="eh-link-btn eh-person-link" data-open-person="${escH(p.id)}">${escH(p.name)}</button>
                <div class="eh-person-sub">${mergedPill}${noteDot}${p.nid ? `<span>کد ملی: ${Ch.toFa(p.nid)}</span>` : ''}</div>
              </div>
            </div>
          </td>
          <td>
            ${p.phone ? `<div class="eh-phone-cell"><span dir="ltr">${Ch.toFa(p.phone)}</span><button type="button" class="eh-copy-tiny" data-copy-phone="${escH(p.phone)}" title="کپی شماره">کپی</button></div>` : '<span style="color:var(--s-text-dim);">—</span>'}
          </td>
          <td>${escH(Ch.toFa(p.level || '—'))}</td>
          <td><strong class="eh-cnt-num">${Ch.fmtNum(p.courses_count)}</strong></td>
          <td>${attCell}</td>
          <td><span class="eh-loy-badge ${loyaltyClass(p.loyalty)}">${escH(p.loyalty)}</span></td>
          <td><div class="eh-tags-wrap">${groupsHtml}${tagsHtml}</div></td>
        </tr>
      `;
    }).join('') || '<tr><td colspan="7" style="text-align:center; padding:24px; color:var(--s-text-muted);">مخاطبی با این فیلتر یافت نشد؛ فیلترها را تغییر دهید یا فایل پرس‌لاین وارد کنید.</td></tr>';

    const cntInfo = bd.querySelector('#crmCountInfo');
    if (cntInfo) {
      cntInfo.textContent = list.length
        ? `نمایش ${Ch.fmtNum(startIdx + 1)} تا ${Ch.fmtNum(Math.min(startIdx + pageItems.length, list.length))} از ${Ch.fmtNum(list.length)} مخاطب یکتا`
        : 'هیچ مخاطبی مطابق فیلتر یافت نشد';
    }
    const pgInfo = bd.querySelector('#crmPageInfo');
    if (pgInfo) pgInfo.textContent = `صفحه ${Ch.fmtNum(partState.page)} از ${Ch.fmtNum(totalPages)}`;
    const prevB = bd.querySelector('#btnCrmPrev'); if (prevB) prevB.disabled = partState.page <= 1;
    const nextB = bd.querySelector('#btnCrmNext'); if (nextB) nextB.disabled = partState.page >= totalPages;

    bd.querySelectorAll('[data-open-person]').forEach(btn => {
      btn.addEventListener('click', () => openParticipantDrawer(btn.dataset.openPerson, bd));
    });
    bd.querySelectorAll('[data-copy-phone]').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        copyTextQuick(btn.dataset.copyPhone, `شماره ${Ch.toFa(btn.dataset.copyPhone)} کپی شد.`);
      });
    });
  }

  function updateReportPreview(bd) {
    const box = bd.querySelector('#repPreviewBox');
    if (!box) return;
    const title = bd.querySelector('#repTitle')?.value?.trim() || 'گزارش رسمی';
    const rec = bd.querySelector('#repRecipient')?.value?.trim() || 'مدیریت محترم';
    const picked = [];
    const checkMap = [
      ['chkKpis', 'کارت‌های شاخص کلان (KPIs)'],
      ['chkChTimeline', 'نمودار روند جذب / دوره‌ها'],
      ['chkChGroup', 'نمودار مقایسه کارگروه‌ها'],
      ['chkChTeachers', 'نمودار اثرگذاری اساتید'],
      ['chkChPareto', 'نمودار پارتو هزینه‌ها'],
      ['chkTblGroups', 'جدول تفکیکی کارگروه‌ها'],
      ['chkTblTeachers', 'جدول عملکرد اساتید'],
      ['chkTblParticipants', 'جدول مخاطبان برتر ۳۶۰°'],
    ];
    checkMap.forEach(([id, lbl]) => { if (bd.querySelector('#' + id)?.checked) picked.push(lbl); });
    const fltTags = [
      currentFilters.group ? `کارگروه: ${currentFilters.group}` : '',
      currentFilters.teacher ? `استاد: ${currentFilters.teacher}` : '',
      currentFilters.year ? `سال: ${currentFilters.year}` : '',
    ].filter(Boolean);
    box.innerHTML = `
      <div class="eh-rep-prev-hdr">پیش‌نمایش ساختار گزارش خروجی</div>
      <div class="eh-rep-prev-title">${escH(title)}</div>
      <div class="eh-rep-prev-meta">گیرنده: <strong>${escH(rec)}</strong></div>
      <div class="eh-rep-prev-meta">دامنه فیلتر: <strong>${fltTags.length ? escH(fltTags.join(' • ')) : 'کل داده‌های مؤسسه'}</strong></div>
      <div class="eh-rep-prev-list">
        ${picked.length ? picked.map((x, i) => `<div><span>${Ch.fmtNum(i + 1)}.</span> ${escH(x)}</div>`).join('') : '<div style="color:var(--s-text-dim);">حداقل یک بخش را انتخاب کنید.</div>'}
      </div>
    `;
  }

  async function runExecutiveExport(bd, fmt) {
    if (!lastAnalytics) return;
    const k = lastAnalytics.kpis;
    const costUnit = lastAnalytics.cost_unit || k.cost_unit || 'ریال';
    const payload = {
      format: fmt,
      filters: currentFilters,
      title: bd.querySelector('#repTitle').value.trim(),
      recipient: bd.querySelector('#repRecipient').value.trim(),
      kpis: bd.querySelector('#chkKpis').checked ? [
        { label: 'شرکت‌کنندگان یکتا', value: Ch.fmtNum(k.unique_participants) },
        { label: 'مجموع حضور کل', value: Ch.fmtNum(k.total_attendance) },
        { label: 'نرخ بازگشت و وفاداری', value: `${Ch.toFa(k.repeat_rate)}٪` },
        { label: 'کل هزینه‌های ثبت‌شده', value: k.total_cost ? `${Ch.fmtNum(k.total_cost)} ${costUnit}` : `${Ch.fmtNum(k.total_courses)} دوره` },
      ] : [],
      charts: [],
      tables: [],
      content: 'این گزارش به‌صورت خودکار از مرکز تحلیل و آمار مؤسسه علمی فرهنگی امام هادی علیه‌السلام استخراج شده است.',
    };

    if (fmt !== 'xlsx') {
      const pairs = [
        ['chkChTimeline', '#chTimeline', 'منحنی جذب مخاطب جدید در برابر مخاطب قدیمی'],
        ['chkChGroup', '#chGroupUnique', 'مقایسه حضور کل و مخاطبان یکتای کارگروه‌ها'],
        ['chkChTeachers', '#chTeachers', 'ماتریس عملکرد اساتید'],
        ['chkChPareto', '#chPareto', 'تحلیل پارتو ۸۰/۲۰ سرفصل‌های هزینه'],
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
          columns: ['نام استاد', 'تعداد دوره', 'کل مخاطبان', 'مخاطبان یکتا', 'ساعت تدریس', 'کارگروه‌ها'],
          rows: lastAnalytics.teachers.slice(0, 25).map(t => [t.name, t.courses, t.attendance, t.unique, t.hours_effective || 0, (t.groups || []).join('، ')]),
        });
      }
      if (bd.querySelector('#chkTblParticipants')?.checked && (lastAnalytics.participants || []).length) {
        payload.tables.push({
          title: 'فهرست مخاطبان برتر یکتاسازی‌شده (۳۶۰ درجه)',
          columns: ['نام و نام خانوادگی', 'شماره تماس', 'تعداد دوره', 'نرخ حضور', 'وفاداری', 'کارگروه‌ها'],
          rows: lastAnalytics.participants.slice(0, 40).map(p => [
            p.name, p.phone || '—', p.courses_count,
            p.attendance_rate !== null && p.attendance_rate !== undefined ? `${p.attendance_rate}%` : '—',
            p.loyalty, (p.groups || []).join('، '),
          ]),
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
                <div class="eitaa-field"><label>کارگروه</label><select id="plGroup" class="glass-select"><option>کارگروه دین شناسی</option><option>کارگروه تاریخ</option><option>کارگروه قرآن</option><option>کارگروه فقه</option><option>کارگروه حدیث</option><option>حدیث‌خوانی (انس با الکافی)</option><option>تربیت سخنران و مبلغ</option></select></div>
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
        const r = window.__ehExecCache = null; lastAnalytics = null; await window.pywebview?.api?.commit_porsline_import?.({
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
          <button type="button" class="ghost-btn" data-reject-idx="${i}" style="padding:5px 11px; font-size:11px;">متفاوت‌اند (منع ادغام)</button>
        </div>
      </div>
    `).join('');
    box.querySelectorAll('[data-merge-idx]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const d = dh.duplicates[Number(btn.dataset.mergeIdx)];
        await window.pywebview?.api?.merge_duplicate_records?.(d.name_a, d.name_b); window.__ehExecCache = null; lastAnalytics = null;
        App.toast('رکوردها با موفقیت ادغام شدند.');
        refreshDataHealth(bd);
      });
    });
    box.querySelectorAll('[data-reject-idx]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const d = dh.duplicates[Number(btn.dataset.rejectIdx)];
        await window.pywebview?.api?.reject_duplicate_records?.(d.name_a, d.name_b); window.__ehExecCache = null; lastAnalytics = null;
        App.toast('قانون منع ادغام ثبت شد؛ این دو فرد دیگر تکراری تشخیص داده نمی‌شوند.');
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
          <button type="button" class="eh-mini-btn eh-act-ico" data-open-f="${encodeURIComponent(l.path)}" title="باز کردن فایل">${ic('externalLink', 14)}</button>
          <button type="button" class="eh-mini-btn eh-act-ico" data-reveal-f="${encodeURIComponent(l.path)}" title="نمایش در پوشه">${ic('folder', 14)}</button>
          <button type="button" class="eh-mini-btn eh-act-ico eh-act-danger" data-del-ltr="${l.id}" title="حذف از فهرست">${ic('trash', 14)}</button>
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
            <div class="pro-modal-title">${ic('gitBranch', 17)}<span>پیگیر چرخه رویدادها و تبلیغات در کانال‌های ایتا</span>${helpBtn('event_pipeline_help')}</div>
            <button type="button" class="pro-icon-btn" data-close-modal>${ic('close', 15)}</button>
          </div>
          <div class="pro-modal-content" style="display:flex; flex-direction:column; gap:14px;">
            <div class="glass-card" style="padding:14px; display:grid; grid-template-columns:2fr 1fr 1.2fr 1fr auto; gap:8px; align-items:end;">
              <div class="eitaa-field"><label>عنوان رویداد / دوره جدید</label><input id="evTitle" class="glass-input" placeholder="مثلاً: همایش اصالت میراث..."/></div>
              <div class="eitaa-field"><label>کارگروه</label><select id="evGroup" class="glass-select"><option>کارگروه دین شناسی</option><option>کارگروه تاریخ</option><option>کارگروه قرآن</option><option>کارگروه فقه</option><option>کارگروه حدیث</option><option>حدیث‌خوانی (انس با الکافی)</option><option>تربیت سخنران و مبلغ</option></select></div>
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
              <button type="button" class="eh-mini-btn eh-act-ico eh-act-danger" data-del-ev="${ev.id}" title="حذف">${ic('trash', 14)}</button>
            </div>
          </div>
          <div class="eh-progress-track"><div class="eh-progress-fill" style="width:${pct}%;"></div></div>
          <div style="display:flex; flex-wrap:wrap; gap:6px;">${pills}</div>
          <div style="display:flex; flex-wrap:wrap; align-items:center; gap:6px; padding-top:4px; border-top:1px dashed var(--s-border);">
            <span style="font-size:11px; color:var(--s-text-muted);">تبلیغات کانال‌های ایتا:</span>
            ${links || '<span style="font-size:11px; color:var(--s-text-dim);">ثبت نشده</span>'}
            <input class="glass-input" data-ag="${idx}" placeholder="نام کانال ایتا..." style="width:155px; padding:4px 8px; font-size:11px;"/>
            <input class="glass-input" data-url="${idx}" dir="ltr" placeholder="https://..." style="width:190px; padding:4px 8px; font-size:11px;"/>
            <button type="button" class="eh-mini-btn eh-ev-add-lk" data-add-lk="${idx}">+ افزودن لینک</button>
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
      dr.innerHTML = `<div class="eh-drawer-panel"><div class="eh-drawer-head"><div id="ehDrawerTitle" class="eh-drawer-title">پرونده</div><button type="button" class="pro-icon-btn" id="btnCloseDrawer" title="بستن">${ic('close', 15)}</button></div><div class="eh-drawer-body" id="ehDrawerBody"></div></div>`;
      dr.addEventListener('click', (e) => { if (e.target === dr) dr.classList.remove('open'); });
      document.body.appendChild(dr);
      dr.querySelector('#btnCloseDrawer').addEventListener('click', () => dr.classList.remove('open'));
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && dr.classList.contains('open')) dr.classList.remove('open'); });
    }
    return dr;
  }

  function showDrawerSmooth(dr) {
    dr.classList.remove('open');
    void dr.offsetWidth;
    requestAnimationFrame(() => dr.classList.add('open'));
  }

  async function openTeacherDrawer(name) {
    const dr = ensureDrawer();
    const res = await window.pywebview?.api?.get_teacher_profile?.(name);
    if (!res || !res.ok) return;
    const st = res.teacher || res.stats || {};
    dr.querySelector('#ehDrawerTitle').innerHTML = `
      <div class="eh-dr-vip-head">
        <span class="eh-avatar eh-loy-core eh-avatar-lg">${escH(avatarInitials(name))}</span>
        <div>
          <strong style="font-size:14px; display:block;">${escH(name)}</strong>
          <span style="font-size:11px; color:var(--s-text-muted);">پرونده ۳۶۰ درجه استاد • ${(st.groups || []).map(shortWgName).join('، ') || 'فعال در مؤسسه'}</span>
        </div>
      </div>`;
    dr.querySelector('#ehDrawerBody').innerHTML = `
      <div class="eh-dr-kpi-grid">
        <div class="eh-dr-kpi"><div class="eh-dr-kpi-l">تعداد دوره‌ها</div><div class="eh-dr-kpi-v">${Ch.fmtNum(st.courses || 0)}</div></div>
        <div class="eh-dr-kpi"><div class="eh-dr-kpi-l">کل مخاطبان</div><div class="eh-dr-kpi-v">${Ch.fmtNum(st.attendance || 0)}</div></div>
        <div class="eh-dr-kpi"><div class="eh-dr-kpi-l">مخاطبان یکتا</div><div class="eh-dr-kpi-v">${st.unique ? Ch.fmtNum(st.unique) : '—'}</div></div>
        <div class="eh-dr-kpi"><div class="eh-dr-kpi-l">ساعت تدریس</div><div class="eh-dr-kpi-v">${st.hours_effective ? Ch.toFa(st.hours_effective) : '—'}</div></div>
      </div>
      <div class="eh-dr-sec glass-card">
        <div class="eh-dr-sec-title">سوابق علمی و آثار (قابل استفاده در تولید محتوا)</div>
        <div class="eitaa-field"><label>معرفی و سوابق علمی استاد</label><textarea id="drTeacherBio" class="glass-input" rows="3">${escH(st.bio || res.bio || '')}</textarea></div>
        <div class="eitaa-field"><label>آثار و تألیفات</label><textarea id="drTeacherWorks" class="glass-input" rows="2">${escH(st.works || res.works || '')}</textarea></div>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button type="button" class="primary-btn" id="btnSaveTeacherMeta" style="padding:7px 14px; font-size:11.5px;">ذخیره سوابق استاد</button>
          <button type="button" class="ghost-btn" id="btnSendTeacherMedia" style="padding:7px 14px; font-size:11.5px;">ارسال به تولید محتوا</button>
        </div>
      </div>
      <div class="eh-dr-sec glass-card">
        <div class="eh-dr-sec-title">دوره‌ها و نشست‌های ارائه‌شده</div>
        <div style="display:flex; flex-direction:column; gap:6px;">
          ${(res.audit_rows || res.courses || []).map(c => `<div class="eh-dup-row"><span>${escH(c.course || c.title)}</span><span class="eh-mini-tag">${escH(shortWgName(c.group || '—'))}</span></div>`).join('') || '<div class="eh-empty-chart">دوره‌ای ثبت نشده است.</div>'}
        </div>
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
    showDrawerSmooth(dr);
  }

  async function openParticipantDrawer(personId, parentBd = null) {
    const dr = ensureDrawer();
    const res = await window.pywebview?.api?.get_participant_profile?.(personId);
    if (!res || !res.ok || !res.participant) return;
    const p = res.participant;
    const hasRate = p.attendance_rate !== null && p.attendance_rate !== undefined && p.total_sessions > 0;
    const rateTxt = hasRate ? `${Ch.toFa(Math.round(p.attendance_rate))}٪` : '—';
    const sessTxt = p.total_sessions > 0 ? `${Ch.fmtNum(p.attended_sessions)} از ${Ch.fmtNum(p.total_sessions)}` : '—';
    const details = p.course_details || (p.courses || []).map(c => ({ course: c, group: '', teacher: '', date: '', session_marks: [], sessions_total: 0, sessions_attended: 0 }));

    dr.querySelector('#ehDrawerTitle').innerHTML = `
      <div class="eh-dr-vip-head">
        <span class="eh-avatar ${loyaltyClass(p.loyalty)} eh-avatar-lg">${escH(avatarInitials(p.name))}</span>
        <div style="min-width:0;">
          <div style="display:flex; align-items:center; gap:7px; flex-wrap:wrap;">
            <strong style="font-size:14.5px;">${escH(p.name)}</strong>
            <span class="eh-loy-badge ${loyaltyClass(p.loyalty)}">${escH(p.loyalty)}</span>
          </div>
          <div style="display:flex; align-items:center; gap:8px; margin-top:4px; font-size:11px; color:var(--s-text-muted); flex-wrap:wrap;">
            <span>امتیاز مشارکت: <strong style="color:var(--lg-accent);">${Ch.fmtNum(p.engagement_score || 0)} از ۱۰۰</strong></span>
            ${p.phone ? `<span>•</span><span dir="ltr">${Ch.toFa(p.phone)}</span><button type="button" class="eh-copy-tiny" id="btnDrCopyPhone">کپی</button>` : ''}
            ${(p.merged_variants && p.merged_variants.length) ? `<span class="eh-merge-pill" title="رکوردهای یکتاشده: ${escH(p.merged_variants.join('، '))}">یکتاشده از ${Ch.fmtNum(p.merged_variants.length + 1)} نام</span>` : ''}
          </div>
        </div>
      </div>`;

    const statusBadge = (mk) => {
      const clsMap = { present: 'eh-mk-ok', late: 'eh-mk-late', excused: 'eh-mk-exc', spam: 'eh-mk-abs', absent: 'eh-mk-abs' };
      const icoMap = { present: '✓', late: '⏱', excused: '!', spam: '✕', absent: '✕' };
      return `<span class="eh-sess-chip ${clsMap[mk.status] || 'eh-mk-abs'}" title="${escH(mk.label + ': ' + mk.raw)}"><span>${escH(mk.label)}</span><strong>${icoMap[mk.status] || '•'} ${escH(mk.raw)}</strong></span>`;
    };

    dr.querySelector('#ehDrawerBody').innerHTML = `
      <div class="eh-dr-kpi-grid">
        <div class="eh-dr-kpi"><div class="eh-dr-kpi-l">دوره‌های حضور</div><div class="eh-dr-kpi-v">${Ch.fmtNum(p.courses_count)}</div></div>
        <div class="eh-dr-kpi"><div class="eh-dr-kpi-l">نرخ حضور واقعی</div><div class="eh-dr-kpi-v">${rateTxt}</div></div>
        <div class="eh-dr-kpi"><div class="eh-dr-kpi-l">جلسات حاضرشده</div><div class="eh-dr-kpi-v" style="font-size:13.5px;">${sessTxt}</div></div>
        <div class="eh-dr-kpi"><div class="eh-dr-kpi-l">کارگروه‌ها</div><div class="eh-dr-kpi-v">${Ch.fmtNum((p.groups || []).length)}</div></div>
      </div>

      ${((p.groups && p.groups.length) || (p.teachers && p.teachers.length)) ? `
        <div class="eh-dr-sec glass-card">
          <div class="eh-dr-sec-title">کارگروه‌ها و اساتید مرتبط</div>
          ${p.groups && p.groups.length ? `<div class="eh-dr-chip-row"><span class="eh-dr-sub-lbl">کارگروه‌ها:</span>${p.groups.map(g => `<span class="eh-mini-tag">${escH(g)}</span>`).join('')}</div>` : ''}
          ${p.teachers && p.teachers.length ? `<div class="eh-dr-chip-row" style="margin-top:6px;"><span class="eh-dr-sub-lbl">اساتید:</span>${p.teachers.map(t => `<button type="button" class="eh-teacher-chip" data-dr-teacher="${escH(t)}">${escH(t)}</button>`).join('')}</div>` : ''}
        </div>
      ` : ''}

      <div class="eh-dr-sec glass-card">
        <div class="eh-dr-sec-title">پرونده تکمیلی، برچسب‌ها و یادداشت مدیریت (ذخیره دائمی)</div>
        <div class="eh-dr-form-grid">
          <div class="eitaa-field"><label>شماره تماس</label><input id="drPartPhone" class="glass-input eh-ltr-num" value="${escH(p.phone || '')}" placeholder="مثلاً 09121234567"/></div>
          <div class="eitaa-field"><label>کد ملی</label><input id="drPartNid" class="glass-input eh-ltr-num" value="${escH(p.nid || '')}" placeholder="کد ملی ۱۰ رقمی..."/></div>
          <div class="eitaa-field"><label>سطح حوزوی / تحصیلی</label><input id="drPartLevel" class="glass-input" value="${escH(p.level || '')}" placeholder="مثلاً سطح ۲"/></div>
          <div class="eitaa-field"><label>برچسب‌ها (با ویرگول جدا کنید)</label><input id="drPartTags" class="glass-input" value="${escH((p.tags || []).join('، '))}" placeholder="استعداد برتر، نماینده کلاس..."/></div>
        </div>
        <div class="eitaa-field" style="margin-top:8px;"><label>یادداشت اختصاصی پرونده</label><textarea id="drPartNotes" class="glass-input" rows="2" placeholder="توضیحات پیگیری، توانمندی‌ها یا وضعیت مخاطب...">${escH(p.notes || '')}</textarea></div>
        <div style="display:flex; justify-content:flex-end; margin-top:9px;">
          <button type="button" class="primary-btn" id="btnSavePartMeta" style="padding:7px 16px; font-size:11.5px;">ذخیره تغییرات پرونده ✓</button>
        </div>
      </div>

      <div class="eh-dr-sec glass-card">
        <div class="eh-dr-sec-title">تایم‌لاین دوره‌ها و جزئیات حضور در تک‌تک جلسات (${Ch.fmtNum(details.length)} دوره)</div>
        <div class="eh-course-timeline">
          ${details.map(c => {
            const cRate = (c.attendance_rate !== null && c.attendance_rate !== undefined && c.sessions_total > 0)
              ? `<span class="eh-mini-tag" style="border-color:rgba(16,185,129,0.4); color:#34d399;">${Ch.fmtNum(c.sessions_attended)}/${Ch.fmtNum(c.sessions_total)} جلسه (${Ch.toFa(Math.round(c.attendance_rate))}٪)</span>`
              : '';
            return `
              <div class="eh-tl-course">
                <div class="eh-tl-course-top">
                  <strong>${escH(c.course)}</strong>
                  ${cRate}
                </div>
                <div class="eh-tl-course-meta">
                  ${c.group ? `<span>${escH(c.group)}</span>` : ''}
                  ${c.teacher && c.teacher !== 'نامشخص' ? `<span>• استاد: ${escH(c.teacher)}</span>` : ''}
                  ${c.date ? `<span>• ${Ch.toFa(c.date)}</span>` : ''}
                </div>
                ${(c.session_marks && c.session_marks.length) ? `<div class="eh-sess-grid">${c.session_marks.map(statusBadge).join('')}</div>` : ''}
              </div>
            `;
          }).join('') || '<div class="eh-empty-chart">دوره‌ای ثبت نشده است.</div>'}
        </div>
      </div>
    `;

    dr.querySelector('#btnDrCopyPhone')?.addEventListener('click', () => {
      copyTextQuick(p.phone, `شماره ${Ch.toFa(p.phone)} کپی شد.`);
    });
    dr.querySelectorAll('[data-dr-teacher]').forEach(tb => {
      tb.addEventListener('click', () => openTeacherDrawer(tb.dataset.drTeacher));
    });
    dr.querySelector('#btnSavePartMeta')?.addEventListener('click', async () => {
      const savePayload = {
        phone: dr.querySelector('#drPartPhone').value.trim(),
        nid: dr.querySelector('#drPartNid').value.trim(),
        level: dr.querySelector('#drPartLevel').value.trim(),
        tags: dr.querySelector('#drPartTags').value.trim(),
        notes: dr.querySelector('#drPartNotes').value.trim(),
      };
      const rSave = await window.pywebview?.api?.save_participant_meta?.(p.profile_key || p.id, savePayload);
      if (rSave && rSave.ok) {
        App.toast('اطلاعات و یادداشت پرونده مخاطب ذخیره شد.');
        if (parentBd) await loadAndDrawAnalytics(parentBd);
      } else {
        App.toast(rSave?.error || 'خطا در ذخیره پرونده');
      }
    });

    showDrawerSmooth(dr);
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

    const slideTitles = [
      'نمای کلان عملکرد',
      'روند زمانی و جذب',
      'عملکرد کارگروه‌ها',
      'شبکه اساتید',
      'تقویم اجرایی',
      'مصوبات و پیگیری‌ها',
    ];
    const totalSlides = slideTitles.length;
    const dotsHtml = slideTitles.map((ttl, idx) =>
      `<button type="button" class="eh-br-dot ${idx === 0 ? 'active' : ''}" data-br-jump="${idx}" title="اسلاید ${Ch.toFa(idx + 1)}: ${ttl}"></button>`
    ).join('');

    ov.innerHTML = `
      <div class="eh-br-ambient"></div>
      <div class="eh-br-top">
        <div class="eh-br-brand">
          <span class="eh-br-badge-icon">${ic('presentation', 17)}</span>
          <div>
            <strong>گزارش جامع جلسه هیئت‌مدیره</strong>
            <div style="font-size:11px; color:var(--s-text-muted);">مؤسسه علمی فرهنگی امام هادی (علیه‌السلام)</div>
          </div>
        </div>
        <div class="eh-br-dots">${dotsHtml}</div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="pro-kbd" title="کلید چپ: اسلاید بعدی • کلید راست: اسلاید قبلی">→ قبلی | بعدی ←</span>
          <button type="button" class="ghost-btn bi-mini-btn" id="brClose">${ic('close', 14)}<span>خروج از ارائه</span></button>
        </div>
      </div>

      <div class="eh-br-stage" id="brStage"></div>

      <div class="eh-br-dock">
        <button type="button" class="eh-br-nav-btn" id="brPrev" title="اسلاید قبلی (کلید راست)">${ic('chevronRight', 16)}<span>قبلی</span></button>
        <span id="brCounter" class="eh-br-counter">اسلاید ۱ از ۶</span>
        <button type="button" class="eh-br-nav-btn" id="brNext" title="اسلاید بعدی (کلید چپ)"><span>بعدی</span>${ic('chevronLeft', 16)}</button>
      </div>
    `;
    document.body.appendChild(ov);

    let slide = 0;
    const drawSlide = () => {
      const st = ov.querySelector('#brStage');
      ov.querySelector('#brCounter').textContent = `اسلاید ${Ch.toFa(slide + 1)} از ${Ch.toFa(totalSlides)}`;
      ov.querySelectorAll('.eh-br-dot').forEach((d, idx) => d.classList.toggle('active', idx === slide));
      const prevBtn = ov.querySelector('#brPrev');
      const nextBtn = ov.querySelector('#brNext');
      if (prevBtn) prevBtn.disabled = (slide === 0);
      if (nextBtn) nextBtn.disabled = (slide === totalSlides - 1);

      const k = res.kpis || {};
      const groups = res.groups || [];
      const hasPerson = Boolean(res.has_person_level && k.unique_verified && k.unique_participants > 0);
      const wb = k.workload_balance || { score: 100, top3_share_pct: 0, label: 'متوازن' };
      const topGroup = groups[0] || null;
      const topGroupShare = (topGroup && k.total_attendance > 0)
        ? Math.round((topGroup.attendance / k.total_attendance) * 100)
        : 0;
      const bestAvgGroup = groups
        .filter(g => g.courses >= 2 && g.avg_attendance > 0)
        .sort((a, b) => b.avg_attendance - a.avg_attendance)[0] || topGroup;

      if (slide === 0) {
        // Smart 6th executive KPI tailored to available real data (NEVER shows internal data-health in boardroom!)
        let card6Html = '';
        if (hasPerson) {
          card6Html = `
            <div class="eh-br-kpi-card">
              <span class="eh-br-kpi-lbl">مخاطبان یکتا و وفاداری</span>
              <strong class="eh-br-kpi-num">${Ch.fmtNum(k.unique_participants)}</strong>
              <small>نرخ بازگشت و حضور مجدد: ${Ch.toFa(k.repeat_rate)}٪</small>
            </div>`;
        } else if (Number(k.total_cost || 0) > 0) {
          card6Html = `
            <div class="eh-br-kpi-card">
              <span class="eh-br-kpi-lbl">هزینه کل و سرانه مخاطب</span>
              <strong class="eh-br-kpi-num">${Ch.fmtNum(k.total_cost)}</strong>
              <small>تومان • سرانه هر نفر-دوره: ${Ch.fmtNum(k.cost_per_attendee)} تومان</small>
            </div>`;
        } else if (Number(k.total_hours || 0) > 0) {
          card6Html = `
            <div class="eh-br-kpi-card">
              <span class="eh-br-kpi-lbl">مجموع ساعات آموزشی</span>
              <strong class="eh-br-kpi-num">${Ch.toFa(k.total_hours)}</strong>
              <small>ساعت در ${Ch.fmtNum(k.total_sessions || 0)} جلسه ثبت‌شده</small>
            </div>`;
        } else if (bestAvgGroup) {
          card6Html = `
            <div class="eh-br-kpi-card">
              <span class="eh-br-kpi-lbl">بالاترین میانگین استقبال</span>
              <strong class="eh-br-kpi-num eh-br-kpi-text">${bestAvgGroup.name}</strong>
              <small>میانگین ${Ch.toFa(bestAvgGroup.avg_attendance)} نفر در هر دوره (${Ch.fmtNum(bestAvgGroup.courses)} دوره)</small>
            </div>`;
        } else {
          card6Html = `
            <div class="eh-br-kpi-card">
              <span class="eh-br-kpi-lbl">کارگروه‌های فعال</span>
              <strong class="eh-br-kpi-num">${Ch.fmtNum(k.total_groups)}</strong>
              <small>حوزه‌های علمی و آموزشی فعال</small>
            </div>`;
        }

        const coursesSub = k.joint_courses > 0
          ? `در ${Ch.fmtNum(k.total_groups)} کارگروه • شامل ${Ch.fmtNum(k.joint_courses)} دوره مشترک`
          : `در ${Ch.fmtNum(k.total_groups)} کارگروه تخصصی`;

        const medVal = (k.median_per_course !== undefined && k.median_per_course !== null && k.median_per_course > 0)
          ? k.median_per_course
          : k.avg_per_course;

        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">اسلاید ۱ از ۶ • نمای کلان عملکرد</div>
            <h2>خلاصه شاخص‌های راهبردی مؤسسه امام هادی (علیه‌السلام)</h2>
            <div class="eh-br-kpis-6">
              <div class="eh-br-kpi-card">
                <span class="eh-br-kpi-lbl">مجموع مشارکت (نفر-دوره)</span>
                <strong class="eh-br-kpi-num">${Ch.fmtNum(k.total_attendance)}</strong>
                <small>کل حضور ثبت‌شده در برنامه‌های مؤسسه</small>
              </div>
              <div class="eh-br-kpi-card">
                <span class="eh-br-kpi-lbl">دوره‌ها و رویدادهای برگزارشده</span>
                <strong class="eh-br-kpi-num">${Ch.fmtNum(k.total_courses)}</strong>
                <small>${coursesSub}</small>
              </div>
              <div class="eh-br-kpi-card">
                <span class="eh-br-kpi-lbl">میانگین استقبال در هر دوره</span>
                <strong class="eh-br-kpi-num">${Ch.toFa(k.avg_per_course)} نفر</strong>
                <small>میانه واقعی (Median): ${Ch.toFa(medVal)} نفر در هر دوره</small>
              </div>
              <div class="eh-br-kpi-card">
                <span class="eh-br-kpi-lbl">پرمخاطب‌ترین کارگروه (کانون جذب)</span>
                <strong class="eh-br-kpi-num eh-br-kpi-text">${topGroup ? topGroup.name : '—'}</strong>
                <small>${topGroup ? `${Ch.fmtNum(topGroup.attendance)} نفر (${Ch.toFa(topGroupShare)}٪ کل حضور در ${Ch.fmtNum(topGroup.courses)} دوره)` : 'ثبت‌نشده'}</small>
              </div>
              <div class="eh-br-kpi-card">
                <span class="eh-br-kpi-lbl">شبکه اساتید و توازن بار علمی</span>
                <strong class="eh-br-kpi-num">${Ch.fmtNum(k.total_teachers)} استاد</strong>
                <small>توازن بار کاری: ${Ch.toFa(wb.score)}٪ (${wb.label})</small>
              </div>
              ${card6Html}
            </div>
          </div>`;
      } else if (slide === 1) {
        const tlTitle = hasPerson
          ? 'روند جذب مخاطبان جدید در برابر مخاطبان قدیمی'
          : 'روند مجموع حضور (نفر-دوره) و تعداد برنامه‌ها در بازه‌های زمانی';
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">اسلاید ۲ از ۶ • روند زمانی و جذب</div>
            <h2>${tlTitle}</h2>
            <div class="eh-br-card-wide"><div id="brCh1" style="width:100%;"></div></div>
          </div>`;
        if (hasPerson) {
          Ch.renderSplineArea(st.querySelector('#brCh1'), [
            { name: 'مخاطبان جدید', values: res.timeline.map(x => x.new_participants) },
            { name: 'مخاطبان قدیمی', values: res.timeline.map(x => x.returning_participants) },
          ], res.timeline.map(x => x.label), { id: 'br1' });
        } else {
          Ch.renderSplineArea(st.querySelector('#brCh1'), [
            { name: 'مجموع نفر-دوره', values: res.timeline.map(x => x.attendance) },
          ], res.timeline.map(x => x.label), { id: 'br1' });
        }
      } else if (slide === 2) {
        const gTitle = hasPerson
          ? 'مقایسه حضور کل، مخاطبان یکتا و توازن کارگروه‌ها'
          : 'مقایسه سهم مشارکت و توازن عملکرد کارگروه‌ها';
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">اسلاید ۳ از ۶ • عملکرد کارگروه‌ها</div>
            <h2>${gTitle}</h2>
            <div class="eh-br-grid2">
              <div class="eh-br-card-wide"><div id="brCh2Bar" style="width:100%;"></div></div>
              <div class="eh-br-card-wide"><div id="brCh2Rad" style="width:100%;"></div></div>
            </div>
          </div>`;
        Ch.renderHBar(
          st.querySelector('#brCh2Bar'),
          groups.map(g => hasPerson ? { label: g.name, v1: g.attendance, v2: g.unique } : { label: g.name, v1: g.attendance })
        );
        Ch.renderRadar(st.querySelector('#brCh2Rad'), groups.map(g => ({ label: g.name, value: g.attendance })));
      } else if (slide === 3) {
        const topT = (res.teachers || []).slice(0, 6);
        const cards = topT.map((t, idx) => {
          const courseMeta = (t.joint_courses && t.joint_courses > 0)
            ? `${Ch.fmtNum(t.courses)} دوره (${Ch.fmtNum(t.independent_courses || 0)} مستقل، ${Ch.fmtNum(t.joint_courses)} مشترک) • میانگین ${Ch.toFa(t.avg_attendance)}`
            : `${Ch.fmtNum(t.courses)} دوره • میانگین ${Ch.toFa(t.avg_attendance)}`;
          return `
            <div class="eh-br-teacher-card">
              <div class="eh-br-rank-badge">${Ch.toFa(idx + 1)}</div>
              <div style="flex:1; min-width:0;">
                <div style="font-size:15px; font-weight:800; color:var(--s-text);">${Ch.formatTeacherShort(t.name)}</div>
                <div style="font-size:11.5px; color:var(--s-text-muted); margin-top:2px;">${(t.groups || []).join('، ') || 'دوره‌های علمی'}</div>
              </div>
              <div style="text-align:left;">
                <div style="font-size:18px; font-weight:800; color:var(--lg-accent);">${Ch.fmtNum(t.attendance)} نفر</div>
                <div style="font-size:11px; color:var(--s-text-muted);">${courseMeta}</div>
              </div>
            </div>`;
        }).join('');
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">اسلاید ۴ از ۶ • شبکه اساتید</div>
            <h2>اساتید شاخص و اثرگذار مؤسسه</h2>
            <div class="eh-br-teachers-grid">${cards || '<div class="eh-empty-chart">داده‌ای ثبت نشده است.</div>'}</div>
          </div>`;
      } else if (slide === 4) {
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">اسلاید ۵ از ۶ • تقویم اجرایی</div>
            <h2>نقشه حرارتی برگزاری برنامه‌ها در ماه‌های سال</h2>
            <div class="eh-br-card-wide"><div id="brChHeat" style="width:100%;"></div></div>
          </div>`;
        Ch.renderHeatmap(st.querySelector('#brChHeat'), res.heatmap || []);
      } else {
        const rows = decList.slice(0, 8).map((d, i) => `
          <div class="eh-br-dec-row">
            <span class="eh-step-num">${Ch.toFa(i + 1)}</span>
            <span style="flex:1; font-size:14px; font-weight:700;">${d.title}</span>
            <span class="eh-badge">${d.done ? 'انجام شد' : 'در دست پیگیری'}</span>
          </div>
        `).join('');
        st.innerHTML = `
          <div class="eh-br-slide">
            <div class="eh-br-pill">اسلاید ۶ از ۶ • مصوبات و تصمیم‌ها</div>
            <h2>دستور جلسه و پیگیری‌های مدیریتی</h2>
            <div class="eh-br-card-wide" style="display:flex; flex-direction:column; gap:10px;">
              ${rows || '<div class="eh-empty-chart">موردی در دفترچه تصمیم‌ها ثبت نشده است؛ از صفحه اصلی موارد جلسه را اضافه کنید.</div>'}
            </div>
          </div>`;
      }
    };

    const goNext = () => { if (slide < totalSlides - 1) { slide += 1; drawSlide(); } };
    const goPrev = () => { if (slide > 0) { slide -= 1; drawSlide(); } };
    const closeBr = () => { document.removeEventListener('keydown', onKey); ov.remove(); };
    const onKey = (e) => {
      if (e.key === 'Escape') closeBr();
      if (e.key === 'ArrowLeft' || e.key === 'PageDown' || e.key === ' ') { e.preventDefault(); goNext(); }
      if (e.key === 'ArrowRight' || e.key === 'PageUp') { e.preventDefault(); goPrev(); }
    };
    document.addEventListener('keydown', onKey);
    ov.querySelectorAll('[data-br-jump]').forEach(btn => btn.addEventListener('click', () => { slide = Number(btn.dataset.brJump); drawSlide(); }));
    ov.querySelector('#brNext').addEventListener('click', goNext);
    ov.querySelector('#brPrev').addEventListener('click', goPrev);
    ov.querySelector('#brClose').addEventListener('click', closeBr);
    drawSlide();
  }

  window.openBoardroomMode = openBoardroom;
  App.boot();
})();
