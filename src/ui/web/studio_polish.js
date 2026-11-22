(() => {
  const THEME_KEY = 'ehadi_saas_theme';
  const SIDEBAR_KEY = 'ehadi_sidebar_collapsed';

  window.showToast = function (msg) {
    let stack = document.getElementById('proToastStack');
    if (!stack) {
      stack = document.createElement('div');
      stack.id = 'proToastStack';
      stack.className = 'pro-toast-stack';
      document.body.appendChild(stack);
    }
    const t = document.createElement('div');
    t.className = 'pro-toast';
    t.textContent = String(msg || '');
    stack.appendChild(t);
    setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 220); }, 2900);
  };

  function triggerSmoothMaximize() {
    if (window.pywebview?.api?.toggle_maximize) window.pywebview.api.toggle_maximize();
    else if (window.pywebview?.api?.toggle_maximize_window) window.pywebview.api.toggle_maximize_window();
  }

  // ==================== سایدبار #sidebar ====================
  function setupSidebar() {
    const sb = document.getElementById('sidebar') || document.querySelector('.sidebar');
    if (!sb) return;
    if (sb.parentElement) {
      const disp = window.getComputedStyle(sb.parentElement).display;
      sb.parentElement.setAttribute('data-pro-shell', disp === 'grid' ? 'grid' : 'flex');
    }

    const navList = sb.querySelector('.nav-list');
    if (navList && !document.getElementById('navBtnMediaStudio')) {
      const oldBtn = document.getElementById('navBtnEitaaStudio');
      if (oldBtn) oldBtn.remove();
      const btn = document.createElement('button');
      btn.id = 'navBtnMediaStudio';
      btn.type = 'button';
      btn.className = 'nav-btn';
      btn.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 20h9"></path>
          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
        </svg>
        <span class="pro-nav-lbl">تولید محتوای رسانه‌ای</span>
      `;
      btn.addEventListener('click', (e) => { e.preventDefault(); openMediaStudio(); });
      navList.appendChild(btn);
    }

    sb.querySelectorAll('.nav-btn').forEach(btn => {
      if (btn.dataset.proNavReady === '1') return;
      btn.dataset.proNavReady = '1';
      const label = (btn.textContent || '').trim().replace(/\s+/g, ' ');
      if (label) btn.setAttribute('data-tooltip', label);

      Array.from(btn.childNodes).forEach(node => {
        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
          const sp = document.createElement('span');
          sp.className = 'pro-nav-lbl';
          sp.textContent = node.textContent.trim();
          btn.replaceChild(sp, node);
        } else if (node.nodeType === Node.ELEMENT_NODE && node.tagName !== 'SVG' && !node.querySelector('svg')) {
          node.classList.add('pro-nav-lbl');
        }
      });
    });
  }

  function toggleSidebar(force) {
    setupSidebar();
    const next = typeof force === 'boolean' ? force : !document.body.classList.contains('sidebar-collapsed');
    document.body.classList.toggle('sidebar-collapsed', next);
    try { localStorage.setItem(SIDEBAR_KEY, next ? '1' : '0'); } catch (_) {}
    if (!next && typeof window.moveIndicator === 'function') {
      setTimeout(() => window.moveIndicator(document.querySelector('.nav-btn.active')), 300);
    }
  }

  // ==================== تم روشن / تیره ====================
  function applyTheme(theme) {
    const t = theme === 'light' ? 'light' : 'dark';
    document.body.setAttribute('data-studio-theme', t);
    try { localStorage.setItem(THEME_KEY, t); } catch (_) {}
    document.querySelectorAll('.studio-theme-btn').forEach(b => b.classList.toggle('active', b.dataset.theme === t));
  }
  function toggleTheme() { applyTheme(document.body.getAttribute('data-studio-theme') === 'light' ? 'dark' : 'light'); }

  function mountThemeSwitcher() {
    const sb = document.getElementById('sidebar') || document.querySelector('.sidebar');
    if (!sb) return;
    if (!document.getElementById('studioThemeSwitcher')) {
      const anchor = sb.querySelector('.nav-section-label') || sb.querySelector('.nav-list');
      const box = document.createElement('div');
      box.id = 'studioThemeSwitcher';
      box.className = 'studio-theme-switcher';
      box.innerHTML = `<button type="button" class="studio-theme-btn" data-theme="light">روشن</button><button type="button" class="studio-theme-btn" data-theme="dark">تیره</button>`;
      if (anchor && anchor.parentElement) anchor.parentElement.insertBefore(box, anchor);
      else sb.appendChild(box);
      box.querySelectorAll('.studio-theme-btn').forEach(b => b.addEventListener('click', () => applyTheme(b.dataset.theme)));
    }
    let saved = 'light';
    try { saved = localStorage.getItem(THEME_KEY) || 'light'; } catch (_) {}
    applyTheme(saved);
    try { if (localStorage.getItem(SIDEBAR_KEY) === '1') toggleSidebar(true); } catch (_) {}
  }

  // ==================== پاپ‌آپ تنظیمات (منو دقیقاً سمت راست مثل داشبورد) ====================
  function mountPrefsModal() {
    if (document.getElementById('ehadiPrefsBackdrop')) return;
    const bd = document.createElement('div');
    bd.id = 'ehadiPrefsBackdrop';
    bd.className = 'pro-overlay-root';
    bd.innerHTML = `
      <div class="pro-modal-box" role="dialog" aria-modal="true">
        <div class="pro-modal-header">
          <div class="pro-modal-title"><span>⚙</span><span>تنظیمات و پیکربندی سامانه (Preferences)</span></div>
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="pro-kbd">ESC</span>
            <button type="button" class="pro-icon-btn" id="btnPrefsCloseX" title="بستن">✕</button>
          </div>
        </div>
        <div class="pro-modal-body">
          <div class="pro-modal-nav">
            <button type="button" class="pro-cat-btn active" data-pane="ai">🤖 هوش مصنوعی و API</button>
            <button type="button" class="pro-cat-btn" data-pane="reports">📄 سربرگ، لوگو و فونت‌ها</button>
            <button type="button" class="pro-cat-btn" data-pane="appearance">🎨 ظاهر و محیط کاربری</button>
            <button type="button" class="pro-cat-btn" data-pane="shortcuts">⌨ میانبرها و پنجره</button>
          </div>
          <div class="pro-modal-content">
            <div class="pro-pane active" id="prefs-pane-ai">
              <div class="pro-pane-title">تنظیمات هسته هوش مصنوعی، کلید API و مدل‌ها</div>
              <div id="prefsSlotAI"></div>
            </div>
            <div class="pro-pane" id="prefs-pane-reports">
              <div class="pro-pane-title">هویت بصری، سربرگ رسمی، متن‌های پیش‌فرض و فونت</div>
              <div id="prefsSlotReports"></div>
            </div>
            <div class="pro-pane" id="prefs-pane-appearance">
              <div class="pro-pane-title">ظاهر محیط کاربری (SaaS Theme)</div>
              <div class="glass-card" style="padding:16px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
                <div>
                  <div style="font-weight:700; font-size:13px;">پوسته رنگی نرم‌افزار</div>
                  <div style="font-size:11.5px; color:var(--s-text-muted); margin-top:3px;">انتخاب بین حالت روشن (مناسب لوگوی PNG) و حالت تیره استودیویی</div>
                </div>
                <div style="display:flex; gap:8px;">
                  <button type="button" class="ghost-btn" id="btnPrefsLight">تم روشن</button>
                  <button type="button" class="ghost-btn" id="btnPrefsDark">تم تیره</button>
                </div>
              </div>
            </div>
            <div class="pro-pane" id="prefs-pane-shortcuts">
              <div class="pro-pane-title">میانبرهای کیبورد و کنترل پنجره</div>
              <div class="glass-card" style="padding:14px; font-size:12px; line-height:2.2; color:var(--s-text-muted);">
                <div><span class="pro-kbd">Ctrl + K</span> — پالت دستورات سریع</div>
                <div><span class="pro-kbd">Ctrl + ,</span> — پنجره تنظیمات</div>
                <div><span class="pro-kbd">Ctrl + B</span> — جمع یا باز کردن سایدبار</div>
                <div><span class="pro-kbd">Ctrl + Shift + T</span> — تغییر تم روشن/تیره</div>
                <div><span class="pro-kbd">F11</span> — بزرگ‌نمایی / بازگردانی پنجره</div>
              </div>
            </div>
          </div>
        </div>
        <div class="pro-modal-footer">
          <span style="font-size:11px; color:var(--s-text-dim);">مؤسسه علمی فرهنگی امام هادی (علیه‌السلام) — eHadiPanel v5.0</span>
          <button type="button" class="primary-btn" id="btnPrefsDone" style="padding:7px 22px;">تأیید و بستن</button>
        </div>
      </div>
    `;
    bd.addEventListener('click', (e) => { if (e.target === bd) closeAllModals(); });
    document.body.appendChild(bd);

    bd.querySelectorAll('.pro-cat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        bd.querySelectorAll('.pro-cat-btn').forEach(b => b.classList.remove('active'));
        bd.querySelectorAll('.pro-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const p = document.getElementById('prefs-pane-' + btn.dataset.pane);
        if (p) p.classList.add('active');
      });
    });

    document.getElementById('btnPrefsCloseX').addEventListener('click', closeAllModals);
    document.getElementById('btnPrefsDone').addEventListener('click', closeAllModals);
    document.getElementById('btnPrefsLight').addEventListener('click', () => applyTheme('light'));
    document.getElementById('btnPrefsDark').addEventListener('click', () => applyTheme('dark'));
  }

  function distributeSettingsCards() {
    const sp = document.getElementById('page-settings');
    const sAI = document.getElementById('prefsSlotAI');
    const sRep = document.getElementById('prefsSlotReports');
    if (!sp || !sAI || !sRep) return;
    const bc = document.getElementById('brandingCard');
    if (bc && bc.parentElement !== sRep) { bc.style.marginTop = '0'; sRep.appendChild(bc); }
    Array.from(sp.children).forEach(ch => { if (ch.id !== 'brandingCard') sAI.appendChild(ch); });
  }

  function openPrefs(pane) {
    closeAllModals();
    mountPrefsModal();
    distributeSettingsCards();
    const bd = document.getElementById('ehadiPrefsBackdrop');
    if (pane) {
      const btn = bd.querySelector(`.pro-cat-btn[data-pane="${pane}"]`);
      if (btn) btn.click();
    }
    requestAnimationFrame(() => bd.classList.add('open'));
  }

  // ==================== تولید محتوای رسانه‌ای (فرم هوشمند بدون شلوغ‌کاری) ====================
  const MODE_META = {
    course: 'اطلاعیه ثبت‌نام دوره‌های کوتاه‌مدت — فقط فیلدهای مورد نیاز ثبت‌نام دوره نمایش داده می‌شود.',
    session: 'اطلاعیه نشست علمی — شامل ارائه‌دهنده، ناقد، دبیر جلسه، زمان و لینک ثبت‌نام.',
    event: 'اطلاعیه همایش تخصصی یا مراسم — شامل اساتید/سخنرانان، زمان و مکان برگزاری.',
    report: 'گزارش جلسه و گزارش تصویری — بدون فیلدهای اضافی ثبت‌نام؛ آماده درج زیر آلبوم تصاویر.',
    intro: 'معرفی دوره یا معرفی استاد — مخصوص پست‌های تکمیلی (Reply) برای معرفی مباحث یا سوابق استاد.',
    pub_news: 'معرفی کتاب و انتشارات یا آرشیو بازتاب در خبرگزاری‌ها (حوزه، ابنا، فارس، تسنیم و...).',
  };

  function mountMediaStudio() {
    if (document.getElementById('mediaStudioBackdrop')) return;
    const bd = document.createElement('div');
    bd.id = 'mediaStudioBackdrop';
    bd.className = 'pro-overlay-root';
    bd.innerHTML = `
      <div class="pro-modal-box" role="dialog" aria-modal="true">
        <div class="pro-modal-header">
          <div class="pro-modal-title"><span>✍</span><span>تولید محتوای رسانه‌ای — ایتا و تلگرام (@emamhadi_qom)</span></div>
          <button type="button" class="pro-icon-btn" id="btnMediaClose">✕</button>
        </div>
        <div class="pro-modal-body">
          <div class="pro-modal-nav" id="mediaTplNav">
            <button type="button" class="pro-cat-btn active" data-tpl="course">📌 اطلاعیه دوره کوتاه‌مدت</button>
            <button type="button" class="pro-cat-btn" data-tpl="session">🎙 اطلاعیه نشست علمی</button>
            <button type="button" class="pro-cat-btn" data-tpl="event">🏛 همایش و مراسم</button>
            <button type="button" class="pro-cat-btn" data-tpl="report">📸 گزارش جلسه و تصویری</button>
            <button type="button" class="pro-cat-btn" data-tpl="intro">📝 معرفی دوره / استاد</button>
            <button type="button" class="pro-cat-btn" data-tpl="pub_news">📚 کتاب / بازتاب خبری</button>
          </div>
          <div class="pro-modal-content">
            <div class="eitaa-grid">
              <div class="eitaa-form" id="mediaForm">
                <div class="eitaa-mode-hint" id="mediaModeHint"></div>

                <div class="eitaa-field" data-modes="event,intro,pub_news">
                  <label id="lblSubType">نوع پست</label>
                  <select id="msSubType" class="glass-select"></select>
                </div>

                <div class="eitaa-field" data-modes="course,report">
                  <label id="lblOrder">ترتیب دوره (مثلاً نوزدهمین)</label>
                  <input id="msOrder" class="glass-input" type="text" placeholder="نوزدهمین" />
                </div>

                <div class="eitaa-field" data-modes="course,report,intro">
                  <label>کارگروه / موضوع (برای هشتگ)</label>
                  <select id="msGroup" class="glass-select">
                    <option value="دین_شناسی">دین‌شناسی</option>
                    <option value="تاریخ">تاریخ</option>
                    <option value="قرآن">قرآن</option>
                    <option value="فقه">فقه</option>
                    <option value="حدیث">حدیث و اصالت میراث</option>
                    <option value="تربیت_مبلغ">تربیت مبلغ</option>
                  </select>
                </div>

                <div class="eitaa-field" data-modes="course,session,event,report,intro,pub_news">
                  <label id="lblTitle">عنوان</label>
                  <input id="msTitle" class="glass-input" type="text" placeholder="عنوان دقیق را وارد کنید..." />
                </div>

                <div class="eitaa-field" data-modes="course,session">
                  <label>زیرعنوان / محور کوتاه (اختیاری)</label>
                  <input id="msSub" class="glass-input" type="text" placeholder="مثلاً: منبع‌شناسی و روش پژوهش در تاریخ اسلام" />
                </div>

                <div class="eitaa-field" data-modes="course">
                  <label>مخاطبین (اختیاری)</label>
                  <input id="msAudience" class="glass-input" type="text" placeholder="مخصوص طلاب سطح ۲ و ۳" />
                </div>

                <div class="eitaa-field" data-modes="course,session,event,report,intro,pub_news">
                  <label id="lblTeacher">استاد / ارائه‌دهنده</label>
                  <input id="msTeacher" class="glass-input" type="text" placeholder="حجت‌الاسلام والمسلمین دکتر ..." />
                </div>

                <div class="eitaa-field" data-modes="course">
                  <label>سوابق علمی استاد (اختیاری)</label>
                  <input id="msBio" class="glass-input" type="text" placeholder="استاد حوزه و دانشگاه / مؤلف کتاب ..." />
                </div>

                <div class="eitaa-field" data-modes="session">
                  <label>ناقد جلسه (اختیاری)</label>
                  <input id="msCritic" class="glass-input" type="text" placeholder="دکتر ..." />
                </div>

                <div class="eitaa-field" data-modes="session">
                  <label>دبیر جلسه (اختیاری)</label>
                  <input id="msModerator" class="glass-input" type="text" placeholder="جناب آقای ..." />
                </div>

                <div class="eitaa-field" data-modes="course">
                  <label>تعداد جلسات و روز</label>
                  <input id="msSessions" class="glass-input" type="text" placeholder="۶ جلسه _ پنجشنبه‌ها" />
                </div>

                <div class="eitaa-field" data-modes="course,session,event,report">
                  <label id="lblDate">تاریخ برگزاری</label>
                  <input id="msDate" class="glass-input" type="text" placeholder="مثلاً: از ۲۶ آبان ۱۴۰۵" />
                </div>

                <div class="eitaa-field" data-modes="course,session,event">
                  <label>ساعت برگزاری</label>
                  <input id="msTime" class="glass-input" type="text" placeholder="ساعت ۱۸ الی ۱۹:۳۰" />
                </div>

                <div class="eitaa-field" data-modes="event">
                  <label>مکان برگزاری</label>
                  <input id="msLocation" class="glass-input" type="text" placeholder="قم، سالن همایش‌های ..." />
                </div>

                <div class="eitaa-field" data-modes="course,session,event">
                  <label>مهلت ثبت‌نام (اختیاری)</label>
                  <input id="msDeadline" class="glass-input" type="text" placeholder="تا سه‌شنبه ۲۲ آبان" />
                </div>

                <div class="eitaa-field" data-modes="course,session,event,intro">
                  <label>لینک ثبت‌نام پرس‌لاین (اختیاری)</label>
                  <input id="msLink" class="glass-input" type="text" dir="ltr" placeholder="https://survey.porsline.ir/s/..." />
                </div>

                <div class="eitaa-field" data-modes="pub_news">
                  <label id="lblPublisher">ناشر / لینک‌های خبرگزاری (هر خط یک مورد)</label>
                  <textarea id="msExtra" class="glass-input" rows="3" placeholder="انتشارات سمت — یا لینک خبرگزاری حوزه، ابنا، فارس..."></textarea>
                </div>

                <div class="eitaa-field" data-modes="report,intro,pub_news">
                  <label id="lblDesc">متن خلاصه / توضیحات</label>
                  <textarea id="msDesc" class="glass-input" rows="3" placeholder="خلاصه مباحث جلسه اول، معرفی دوره یا جزئیات رونمایی..."></textarea>
                </div>

                <div class="eitaa-field" data-modes="report">
                  <label>لینک خبر در خبرگزاری (اختیاری)</label>
                  <input id="msNewsUrl" class="glass-input" type="text" dir="ltr" placeholder="https://fa.abna24.com/..." />
                </div>
              </div>

              <div class="eitaa-preview-box">
                <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
                  <strong style="font-size:12.5px;">پیش‌نمایش آماده انتشار</strong>
                  <div style="display:flex; gap:6px;">
                    <button type="button" class="ghost-btn" id="btnClearMedia" style="padding:5px 10px; font-size:11px;">پاک کردن</button>
                    <button type="button" class="primary-btn" id="btnCopyMedia" style="padding:6px 14px; font-size:11.5px;">📋 کپی متن</button>
                  </div>
                </div>
                <textarea id="msPreview" class="eitaa-preview-text"></textarea>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
    bd.addEventListener('click', (e) => { if (e.target === bd) closeAllModals(); });
    document.body.appendChild(bd);
    document.getElementById('btnMediaClose').addEventListener('click', closeAllModals);

    let activeTpl = 'course';
    const val = (id) => (document.getElementById(id)?.value || '').trim();

    function populateSubTypeOptions(tpl) {
      const sel = document.getElementById('msSubType');
      const map = {
        event: [['conference', 'همایش تخصصی'], ['ceremony', 'مجلس عزاداری / یادبود']],
        intro: [['course_intro', 'معرفی دوره'], ['teacher_intro', 'آشنایی با استاد']],
        pub_news: [['book', 'معرفی کتاب / اثر پژوهشی'], ['press', 'بازتاب در خبرگزاری‌ها']],
      };
      const opts = map[tpl] || [];
      sel.innerHTML = opts.map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
    }

    function updateDynamicForm() {
      document.getElementById('mediaModeHint').textContent = MODE_META[activeTpl] || '';
      populateSubTypeOptions(activeTpl);

      // تنظیم هوشمند برچسب‌ها متناسب با دسته انتخابی
      const labels = {
        course:   { title: 'عنوان دوره', teacher: 'استاد دوره', date: 'بازه تاریخ برگزاری', order: 'ترتیب دوره (مثلاً نوزدهمین)' },
        session:  { title: 'عنوان نشست علمی', teacher: 'ارائه‌دهنده', date: 'تاریخ / مناسبت نشست' },
        event:    { title: 'عنوان همایش یا مراسم', teacher: 'اساتید / سخنرانان و مداحان', date: 'تاریخ برگزاری' },
        report:   { title: 'عنوان دوره / نشست / همایش', teacher: 'استاد / سخنران', date: 'تاریخ یا ماه برگزاری', order: 'ترتیب دوره (یا خالی برای نشست/همایش)', desc: 'خلاصه جلسه اول یا محور مباحث (اختیاری)' },
        intro:    { title: 'عنوان دوره', teacher: 'نام استاد', desc: 'متن معرفی دوره یا سوابق و آثار استاد' },
        pub_news: { title: 'عنوان کتاب یا رویداد خبری', teacher: 'مؤلف / پدیدآورنده (برای کتاب)', desc: 'توضیح تکمیلی یا جزئیات رونمایی (اختیاری)' },
      }[activeTpl] || {};

      if (labels.title) document.getElementById('lblTitle').textContent = labels.title;
      if (labels.teacher) document.getElementById('lblTeacher').textContent = labels.teacher;
      if (labels.date) document.getElementById('lblDate').textContent = labels.date;
      if (labels.order) document.getElementById('lblOrder').textContent = labels.order;
      if (labels.desc) document.getElementById('lblDesc').textContent = labels.desc;

      // نمایش صرفاً فیلدهای مرتبط با دسته فعلی
      bd.querySelectorAll('#mediaForm .eitaa-field[data-modes]').forEach(el => {
        const modes = (el.dataset.modes || '').split(',');
        el.classList.toggle('hidden-field', !modes.includes(activeTpl));
      });
      buildText();
    }

    function buildText() {
      const subType = val('msSubType');
      const order = val('msOrder');
      const group = (val('msGroup') || 'دین_شناسی').replace(/\s+/g, '_');
      const groupTitle = group.replace(/_/g, ' ');
      const title = val('msTitle') || 'عنوان ...';
      const sub = val('msSub');
      const audience = val('msAudience');
      const teacher = val('msTeacher');
      const bio = val('msBio');
      const critic = val('msCritic');
      const moderator = val('msModerator');
      const sessions = val('msSessions');
      const date = val('msDate');
      const time = val('msTime');
      const location = val('msLocation');
      const deadline = val('msDeadline');
      const link = val('msLink');
      const extra = val('msExtra');
      const desc = val('msDesc');
      const newsUrl = val('msNewsUrl');
      const tTag = teacher.replace(/حجت[‌ ]?الاسلام|و[ ]?المسلمین|آیت[‌ ]?الله|دکتر|استاد/g, '').trim().replace(/\s+/g, '_');

      let out = '';
      if (activeTpl === 'course') {
        out = `🔰 ${order ? order + ' دوره از دوره‌های' : 'دوره‌های'} کوتاه‌مدت مؤسسه امام هادی «علیه‌السلام»\n\n▫️ ${title}${sub ? '\n' + sub : ''}${audience ? '\n\n' + audience : ''}${teacher ? '\n\n🎙 استاد: ' + teacher : ''}${bio ? '\n' + bio : ''}${sessions ? '\n\n📌 ' + sessions : ''}${date ? '\n🗓 ' + date : ''}${time ? '\n🕰 ' + time : ''}${deadline ? '\n\nمهلت ثبت‌نام: ' + deadline : ''}${link ? '\n\n👇👇 لینک ثبت‌نام 👇👇\n' + link : ''}\n\n👇 راه‌های ارتباطی 👇\n۰۲۵-۳۷۷۲۵۲۲۵-۷\n\n@emamhadi_qom`;
      } else if (activeTpl === 'session') {
        out = `مؤسسه علمی فرهنگی امام هادی «علیه‌السلام»\n\nنشست علمی\n\n▫️ ${title}${sub ? '\n' + sub : ''}${teacher ? '\n\n🎙 ارائه‌دهنده: ' + teacher : ''}${critic ? '\n🎙 ناقد: ' + critic : ''}${moderator ? '\nدبیر جلسه: ' + moderator : ''}${date ? '\n\n🗓 ' + date : ''}${time ? '\n🕰 ' + time : ''}${deadline ? '\n\nمهلت ثبت‌نام: ' + deadline : ''}${link ? '\n\n👇👇 لینک ثبت‌نام 👇👇\n' + link : ''}\n\n👇 راه‌های ارتباطی 👇\n۰۲۵-۳۷۷۲۵۲۲۵-۷\n\n@emamhadi_qom`;
      } else if (activeTpl === 'event') {
        if (subType === 'ceremony') {
          out = `▪️ ${title}${teacher ? '\n\n' + teacher : ''}${date ? '\n\n🗓 زمان: ' + date : ''}${time ? '\n🕰 ' + time : ''}${location ? '\n📌 مکان: ' + location : ''}\n\nمؤسسه علمی فرهنگی امام هادی علیه‌السلام\n@emamhadi_qom`;
        } else {
          out = `مؤسسه علمی فرهنگی امام هادی علیه‌السلام برگزار می‌کند:\n\nهمایش تخصصی\n«${title}»${teacher ? '\n\n🎙 اساتید:\n' + teacher : ''}${date || time ? '\n\n🕰 زمان:\n' + [date, time].filter(Boolean).join(' — ') : ''}${location ? '\n📌 مکان: ' + location : ''}${deadline ? '\n\nمهلت ثبت‌نام: ' + deadline : ''}${link ? '\n\nلینک ثبت‌نام:\n' + link : ''}\n\nراه‌های ارتباطی:\n۰۲۵-۳۷۷۲۵۲۲۵-۷\n\n@emamhadi_qom`;
        }
      } else if (activeTpl === 'report') {
        const hdr = order
          ? `🔰 گزارش تصویری ${order} دوره از دوره‌های کوتاه‌مدت مؤسسه امام هادی (علیه‌السلام)`
          : `🔰 گزارش تصویری برنامه «${title}» در مؤسسه امام هادی (علیه‌السلام)`;
        out = `${hdr}\n\n🔻 «${title}» از سلسله برنامه‌های کارگروه ${groupTitle}${teacher ? ' با ارائه ' + teacher : ''}${date ? ' در ' + date : ''} برگزار شد.${desc ? '\n\n🔻 ' + desc : ''}${newsUrl ? '\n\n' + newsUrl : ''}\n\n❖ــــــــــــــــــــــــــــــــــــــــــــــــــــ❖\n\n#گزارش_تصویری\n#${group}${tTag ? '\n#' + tTag : ''}\n\n@emamhadi_qom`;
      } else if (activeTpl === 'intro') {
        const head = subType === 'teacher_intro'
          ? `🔻 آشنایی با ${teacher || 'استاد دوره'}:`
          : `📝 معرفی دوره «${title}»:`;
        const tag = subType === 'teacher_intro' ? '#معرفی_استاد' : '#معرفی_دوره';
        out = `${head}\n\n📌 ${desc || 'توضیحات معرفی را وارد کنید...'}${link ? '\n\nلینک ثبت‌نام:\n' + link : ''}\n\n${tag}\n#${group}${tTag ? '\n#' + tTag : ''}\n\n@emamhadi_qom`;
      } else {
        if (subType === 'press') {
          out = `🔻 بازتاب «${title}» مؤسسه علمی فرهنگی امام هادی علیه‌السلام در خبرگزاری‌ها:\n\n${extra || 'خبرگزاری حوزه: ...\nخبرگزاری ابنا: ...'}${desc ? '\n\n' + desc : ''}\n\n@emamhadi_qom`;
        } else {
          out = `📚 «${title}»${teacher ? '\n\nاثر: ' + teacher : ''}\n\nتهیه‌شده در: مؤسسه علمی فرهنگی امام هادی علیه‌السلام${extra ? '\nچاپ / ناشر: ' + extra : ''}${desc ? '\n\n' + desc : ''}\n\n@emamhadi_qom`;
        }
      }
      document.getElementById('msPreview').value = out;
    }

    bd.querySelectorAll('#mediaTplNav .pro-cat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        bd.querySelectorAll('#mediaTplNav .pro-cat-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeTpl = btn.dataset.tpl;
        updateDynamicForm();
      });
    });

    bd.querySelectorAll('#mediaForm input, #mediaForm textarea, #mediaForm select').forEach(el => {
      el.addEventListener('input', buildText);
      el.addEventListener('change', buildText);
    });

    document.getElementById('btnClearMedia').addEventListener('click', () => {
      bd.querySelectorAll('#mediaForm input, #mediaForm textarea').forEach(el => { el.value = ''; });
      buildText();
    });

    document.getElementById('btnCopyMedia').addEventListener('click', async () => {
      const txt = document.getElementById('msPreview').value;
      try { await navigator.clipboard.writeText(txt); } catch (_) {
        document.getElementById('msPreview').select(); document.execCommand('copy');
      }
      window.showToast('متن آماده انتشار کپی شد.');
    });

    updateDynamicForm();
  }

  function openMediaStudio() {
    closeAllModals();
    mountMediaStudio();
    const bd = document.getElementById('mediaStudioBackdrop');
    requestAnimationFrame(() => bd.classList.add('open'));
  }

  // ==================== پالت دستورات سریع (Ctrl + K) ====================
  const COMMANDS = [
    { label: 'باز کردن تولید محتوای رسانه‌ای (ایتا و تلگرام)', cat: 'محتوا', key: '', run: openMediaStudio },
    { label: 'باز کردن پنجره تنظیمات (Preferences)', cat: 'تنظیمات', key: 'Ctrl+,', run: () => openPrefs() },
    { label: 'رفتن به داشبورد مدیریتی و BI', cat: 'ناوبری', key: 'Ctrl+1', run: () => goPage('dashboard') },
    { label: 'رفتن به دستیار هوشمند (AI)', cat: 'ناوبری', key: 'Ctrl+2', run: () => goPage('chat') },
    { label: 'رفتن به مدیریت و پردازش اسناد', cat: 'ناوبری', key: 'Ctrl+3', run: () => goPage('docs') },
    { label: 'خروجی PDF رسمی از داشبورد BI', cat: 'گزارش', key: '', run: () => window.exportBiOfficialReport && window.exportBiOfficialReport('pdf') },
    { label: 'خروجی Word رسمی از داشبورد BI', cat: 'گزارش', key: '', run: () => window.exportBiOfficialReport && window.exportBiOfficialReport('docx') },
    { label: 'تغییر تم (روشن / تیره)', cat: 'ظاهر', key: 'Ctrl+Shift+T', run: toggleTheme },
    { label: 'جمع یا باز کردن سایدبار', cat: 'ظاهر', key: 'Ctrl+B', run: () => toggleSidebar() },
  ];

  function goPage(id) {
    if (id === 'settings') { openPrefs(); return; }
    const btn = document.querySelector(`.nav-btn[onclick*="'${id}'"]`);
    if (typeof window.switchPage === 'function') window.switchPage(id, btn);
  }

  let cmdIdx = 0, cmdFiltered = COMMANDS.slice();
  function mountCmdPalette() {
    if (document.getElementById('cmdBackdrop')) return;
    const el = document.createElement('div');
    el.id = 'cmdBackdrop';
    el.className = 'pro-overlay-root';
    el.innerHTML = `
      <div class="pro-modal-box cmd-box" role="dialog" aria-modal="true">
        <div class="cmd-input-wrap">
          <span style="color:var(--s-text-dim);">⌕</span>
          <input id="cmdSearchInput" class="cmd-input" type="text" placeholder="نام بخش یا دستور را تایپ کنید..." />
          <span class="pro-kbd">ESC</span>
        </div>
        <div class="cmd-list" id="cmdList"></div>
      </div>
    `;
    el.addEventListener('click', (e) => { if (e.target === el) closeAllModals(); });
    document.body.appendChild(el);
    const inp = document.getElementById('cmdSearchInput');
    inp.addEventListener('input', () => {
      const q = inp.value.trim().toLowerCase();
      cmdFiltered = COMMANDS.filter(c => c.label.toLowerCase().includes(q) || c.cat.toLowerCase().includes(q));
      cmdIdx = 0; renderCmd();
    });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); cmdIdx = (cmdIdx + 1) % Math.max(1, cmdFiltered.length); renderCmd(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); cmdIdx = (cmdIdx - 1 + Math.max(1, cmdFiltered.length)) % Math.max(1, cmdFiltered.length); renderCmd(); }
      else if (e.key === 'Enter' && cmdFiltered[cmdIdx]) { e.preventDefault(); const fn = cmdFiltered[cmdIdx].run; closeAllModals(); fn && fn(); }
    });
  }
  function renderCmd() {
    const list = document.getElementById('cmdList');
    if (!list) return;
    list.innerHTML = cmdFiltered.map((c, i) => `
      <button type="button" class="cmd-item ${i === cmdIdx ? 'selected' : ''}" data-i="${i}">
        <span>${c.label}</span><span class="pro-kbd">${c.key || c.cat}</span>
      </button>
    `).join('');
    list.querySelectorAll('.cmd-item').forEach(b => b.addEventListener('click', () => {
      const it = cmdFiltered[Number(b.dataset.i)]; closeAllModals(); it && it.run && it.run();
    }));
  }
  function openCmdPalette() {
    closeAllModals(); mountCmdPalette();
    cmdFiltered = COMMANDS.slice(); cmdIdx = 0; renderCmd();
    const bd = document.getElementById('cmdBackdrop');
    requestAnimationFrame(() => bd.classList.add('open'));
    const inp = document.getElementById('cmdSearchInput'); inp.value = ''; setTimeout(() => inp.focus(), 30);
  }

  function closeAllModals() {
    document.querySelectorAll('.pro-overlay-root.open').forEach(el => el.classList.remove('open'));
  }

  // ==================== نوار ابزار سریع بالا ====================
  function mountTopbar() {
    const main = document.querySelector('.main-content, main');
    if (!main || document.getElementById('proTopbar')) return;
    const bar = document.createElement('div');
    bar.id = 'proTopbar';
    bar.className = 'pro-topbar';
    bar.innerHTML = `
      <div class="pro-topbar-right">
        <button class="pro-icon-btn" id="btnToggleSidebar" title="جمع/باز کردن سایدبار (Ctrl+B)">☰</button>
        <span class="pro-breadcrumb" id="proBreadcrumb">مؤسسه علمی فرهنگی امام هادی (علیه‌السلام)</span>
      </div>
      <div class="pro-topbar-left">
        <button class="pro-cmd-trigger" id="btnOpenCmdPalette"><span>جست‌وجو و دستورات...</span><span class="pro-kbd">Ctrl + K</span></button>
        <button class="pro-icon-btn" id="btnQuickMedia" title="تولید محتوای رسانه‌ای">✍</button>
        <button class="pro-icon-btn" id="btnQuickSettings" title="تنظیمات سیستم (Ctrl+,)">⚙</button>
        <button class="pro-icon-btn" id="btnQuickTheme" title="تغییر تم روشن/تیره">◐</button>
        <button class="pro-icon-btn" id="btnQuickFull" title="بزرگ‌نمایی / بازگردانی">⛶</button>
      </div>
    `;
    main.insertBefore(bar, main.firstChild);
    document.getElementById('btnToggleSidebar').addEventListener('click', () => toggleSidebar());
    document.getElementById('btnOpenCmdPalette').addEventListener('click', openCmdPalette);
    document.getElementById('btnQuickMedia').addEventListener('click', openMediaStudio);
    document.getElementById('btnQuickSettings').addEventListener('click', () => openPrefs());
    document.getElementById('btnQuickTheme').addEventListener('click', toggleTheme);
    document.getElementById('btnQuickFull').addEventListener('click', triggerSmoothMaximize);
  }

  // ==================== ریسایز ۸ جهته نرم با SetBounds (بدون فریم سفید ویندوز) ====================
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
        let rafPending = false;
        let latest = null;
        const onMove = (mv) => {
          const dx = mv.screenX - sx;
          const dy = mv.screenY - sy;
          let nx = bx, ny = by, nw = bw, nh = bh;
          if (dir.includes('right')) nw = Math.max(1024, bw + dx);
          if (dir.includes('bottom')) nh = Math.max(680, bh + dy);
          if (dir.includes('left')) {
            nw = Math.max(1024, bw - dx);
            nx = bx + (bw - nw);
          }
          if (dir.includes('top')) {
            nh = Math.max(680, bh - dy);
            ny = by + (bh - nh);
          }
          latest = [nx, ny, nw, nh];
          if (!rafPending) {
            rafPending = true;
            requestAnimationFrame(() => {
              rafPending = false;
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

  function hookSwitchPageAndWinButtons() {
    if (typeof window.switchPage === 'function' && !window.switchPage._v50Hooked) {
      const orig = window.switchPage;
      const wrapped = function (pageId, btn) {
        if (String(pageId).toLowerCase() === 'settings') { openPrefs(); return; }
        return orig.apply(this, arguments);
      };
      wrapped._v50Hooked = true;
      window.switchPage = wrapped;
    }

    document.querySelectorAll('.win-btn[onclick*="toggle_maximize"]').forEach(btn => {
      if (btn.dataset.maxHooked === '1') return;
      btn.dataset.maxHooked = '1';
      btn.removeAttribute('onclick');
      btn.addEventListener('click', (e) => { e.preventDefault(); triggerSmoothMaximize(); });
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAllModals();
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openCmdPalette(); }
    else if ((e.ctrlKey || e.metaKey) && e.key === ',') { e.preventDefault(); openPrefs(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') { e.preventDefault(); toggleSidebar(); }
    else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 't') { e.preventDefault(); toggleTheme(); }
    else if ((e.ctrlKey || e.metaKey) && ['1', '2', '3'].includes(e.key)) { e.preventDefault(); goPage({ '1': 'dashboard', '2': 'chat', '3': 'docs' }[e.key]); }
    else if (e.key === 'F11') { e.preventDefault(); triggerSmoothMaximize(); }
  });

  function initAll() {
    hookSwitchPageAndWinButtons();
    setupSidebar();
    mountResizeHandles();
    mountThemeSwitcher();
    mountTopbar();
    mountPrefsModal();
    mountMediaStudio();
    mountCmdPalette();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAll);
  else initAll();
  window.addEventListener('pywebviewready', () => { initAll(); setTimeout(syncSidebarLogo, 120); });
  window.openSettingsModal = openPrefs;
  window.openMediaStudio = openMediaStudio;
  window.refreshStudioLogo = syncSidebarLogo;
})();
