(() => {
  const App = window.eHadiApp;
  const ic = App.icon;

  // ---------- پلاگین ۱: پنجره تنظیمات دسته‌بندی‌شده (Preferences) ----------
  App.registerSettingsTab({
    id: 'ai', icon: 'cpu', label: 'هوش مصنوعی و API',
    title: 'تنظیمات هسته هوش مصنوعی، کلید API و مدل‌ها',
    bodyHtml: '<div id="prefsSlotAI"></div>',
  });
  App.registerSettingsTab({
    id: 'reports', icon: 'fileText', label: 'سربرگ، لوگو و فونت‌ها',
    title: 'هویت بصری، سربرگ رسمی، متن‌های پیش‌فرض و مدیریت فونت',
    bodyHtml: '<div id="prefsSlotReports"></div>',
  });
  App.registerSettingsTab({
    id: 'appearance', icon: 'palette', label: 'ظاهر و محیط کاربری',
    title: 'پوسته رنگی و تنظیمات نمایش نرم‌افزار',
    bodyHtml: `
      <div class="glass-card" style="padding:16px; display:flex; align-items:center; justify-content:space-between; gap:14px;">
        <div>
          <div style="font-weight:700; font-size:13px;">پوسته رنگی محیط کاربری</div>
          <div style="font-size:11.5px; color:var(--s-text-muted); margin-top:4px;">سوییچ آنی بین تم تیره استودیویی و تم روشن با کنتراست بالا</div>
        </div>
        <div style="display:flex; gap:8px;">
          <button type="button" class="ghost-btn pro-btn-ic" id="btnPrefsLight">${ic('sun', 14)}<span>تم روشن</span></button>
          <button type="button" class="ghost-btn pro-btn-ic" id="btnPrefsDark">${ic('moon', 14)}<span>تم تیره</span></button>
        </div>
      </div>
    `,
  });
  App.registerSettingsTab({
    id: 'shortcuts', icon: 'keyboard', label: 'میانبرها و پنجره',
    title: 'کلیدهای میانبر سریع کیبورد',
    bodyHtml: `
      <div class="glass-card" style="padding:16px; font-size:12px; line-height:2.3; color:var(--s-text-muted);">
        <div><span class="pro-kbd">Ctrl + K</span> — باز کردن پالت دستورات سریع</div>
        <div><span class="pro-kbd">Ctrl + ,</span> — باز کردن پنجره تنظیمات</div>
        <div><span class="pro-kbd">Ctrl + B</span> — جمع یا باز کردن نرم سایدبار</div>
        <div><span class="pro-kbd">Ctrl + Shift + T</span> — تغییر سریع تم روشن و تیره</div>
        <div><span class="pro-kbd">F11</span> — بزرگ‌نمایی / بازگردانی پنجره</div>
      </div>
    `,
  });

  App.registerModal('preferences', {
    render() {
      const tabs = App.getSettingsTabs();
      const navBtns = tabs.map((t, i) => `
        <button type="button" class="pro-cat-btn ${i === 0 ? 'active' : ''}" data-pane="${t.id}">
          ${ic(t.icon, 16)}<span>${t.label}</span>
        </button>
      `).join('');
      const panes = tabs.map((t, i) => `
        <div class="pro-pane ${i === 0 ? 'active' : ''}" id="prefs-pane-${t.id}">
          <div class="pro-pane-title">${t.title}</div>
          ${t.bodyHtml}
        </div>
      `).join('');
      return `
        <div class="pro-modal-box" role="dialog" aria-modal="true">
          <div class="pro-modal-header">
            <div class="pro-modal-title">${ic('settings', 17)}<span>تنظیمات و پیکربندی سامانه</span></div>
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="pro-kbd">ESC</span>
              <button type="button" class="pro-icon-btn" data-close-modal title="بستن">${ic('close', 15)}</button>
            </div>
          </div>
          <div class="pro-modal-body">
            <div class="pro-modal-nav">${navBtns}</div>
            <div class="pro-modal-content">${panes}</div>
          </div>
          <div class="pro-modal-footer">
            <span style="font-size:11px; color:var(--s-text-dim);">مؤسسه علمی فرهنگی امام هادی (علیه‌السلام) — eHadiPanel v5.2 Pro</span>
            <button type="button" class="primary-btn" data-close-modal style="padding:7px 22px;">تأیید و بستن</button>
          </div>
        </div>
      `;
    },
    onMount(bd) {
      bd.querySelectorAll('.pro-cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          bd.querySelectorAll('.pro-cat-btn').forEach(b => b.classList.remove('active'));
          bd.querySelectorAll('.pro-pane').forEach(p => p.classList.remove('active'));
          btn.classList.add('active');
          const p = bd.querySelector('#prefs-pane-' + btn.dataset.pane);
          if (p) p.classList.add('active');
        });
      });
      bd.querySelector('#btnPrefsLight')?.addEventListener('click', () => App.applyTheme('light'));
      bd.querySelector('#btnPrefsDark')?.addEventListener('click', () => App.applyTheme('dark'));
    },
    onOpen(bd, opts) {
      const sp = document.getElementById('page-settings');
      const sAI = bd.querySelector('#prefsSlotAI');
      const sRep = bd.querySelector('#prefsSlotReports');
      if (sp && sAI && sRep) {
        const bc = document.getElementById('brandingCard');
        if (bc && bc.parentElement !== sRep) { bc.style.marginTop = '0'; sRep.appendChild(bc); }
        Array.from(sp.children).forEach(ch => { if (ch.id !== 'brandingCard') sAI.appendChild(ch); });
      }
      if (opts && opts.pane) bd.querySelector(`.pro-cat-btn[data-pane="${opts.pane}"]`)?.click();
    },
  });

  // ---------- پلاگین ۲: تولید محتوای رسانه‌ای (فرم هوشمند با آیکون‌های فلت) ----------
  const MODE_META = {
    course: 'اطلاعیه ثبت‌نام دوره‌های کوتاه‌مدت — صرفاً فیلدهای ثبت‌نام دوره نمایش داده می‌شوند.',
    session: 'اطلاعیه نشست علمی — شامل ارائه‌دهنده، ناقد، دبیر جلسه، زمان و لینک ثبت‌نام.',
    event: 'اطلاعیه همایش تخصصی یا مراسم — شامل اساتید/سخنرانان، زمان و مکان برگزاری.',
    report: 'گزارش جلسه و گزارش تصویری — بدون فیلدهای اضافی ثبت‌نام؛ آماده درج زیر آلبوم تصاویر.',
    intro: 'معرفی دوره یا معرفی استاد — مناسب پست‌های تکمیلی معرفی مباحث یا سوابق استاد.',
    pub_news: 'معرفی کتاب و انتشارات یا آرشیو بازتاب در خبرگزاری‌ها (حوزه، ابنا، فارس، تسنیم و...).',
  };

  App.registerSidebarAction({
    id: 'media_studio',
    icon: 'penTool',
    label: 'تولید محتوای رسانه‌ای',
    onClick: () => App.openModal('media_studio'),
  });

  App.registerModal('media_studio', {
    render() {
      return `
        <div class="pro-modal-box" role="dialog" aria-modal="true">
          <div class="pro-modal-header">
            <div class="pro-modal-title">${ic('penTool', 17)}<span>تولید محتوای رسانه‌ای — ایتا و تلگرام (@emamhadi_qom)</span></div>
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="pro-kbd">ESC</span>
              <button type="button" class="pro-icon-btn" data-close-modal title="بستن">${ic('close', 15)}</button>
            </div>
          </div>
          <div class="pro-modal-body">
            <div class="pro-modal-nav" id="mediaTplNav">
              <button type="button" class="pro-cat-btn active" data-tpl="course">${ic('calendar', 16)}<span>اطلاعیه دوره کوتاه‌مدت</span></button>
              <button type="button" class="pro-cat-btn" data-tpl="session">${ic('mic', 16)}<span>اطلاعیه نشست علمی</span></button>
              <button type="button" class="pro-cat-btn" data-tpl="event">${ic('landmark', 16)}<span>همایش و مراسم</span></button>
              <button type="button" class="pro-cat-btn" data-tpl="report">${ic('camera', 16)}<span>گزارش جلسه و تصویری</span></button>
              <button type="button" class="pro-cat-btn" data-tpl="intro">${ic('userCheck', 16)}<span>معرفی دوره / استاد</span></button>
              <button type="button" class="pro-cat-btn" data-tpl="pub_news">${ic('bookOpen', 16)}<span>کتاب / بازتاب خبری</span></button>
            </div>
            <div class="pro-modal-content">
              <div class="eitaa-grid">
                <div class="eitaa-form" id="mediaForm">
                  <div class="eitaa-mode-hint" id="mediaModeHint"></div>
                  <div class="eitaa-field" data-modes="event,intro,pub_news"><label>نوع پست</label><select id="msSubType" class="glass-select"></select></div>
                  <div class="eitaa-field" data-modes="course,report"><label id="lblOrder">ترتیب دوره</label><input id="msOrder" class="glass-input" type="text" placeholder="نوزدهمین" /></div>
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
                  <div class="eitaa-field" data-modes="course,session,event,report,intro,pub_news"><label id="lblTitle">عنوان</label><input id="msTitle" class="glass-input" type="text" placeholder="عنوان دقیق را وارد کنید..." /></div>
                  <div class="eitaa-field" data-modes="course,session"><label>زیرعنوان / محور کوتاه (اختیاری)</label><input id="msSub" class="glass-input" type="text" placeholder="منبع‌شناسی و روش پژوهش..." /></div>
                  <div class="eitaa-field" data-modes="course"><label>مخاطبین (اختیاری)</label><input id="msAudience" class="glass-input" type="text" placeholder="مخصوص طلاب سطح ۲ و ۳" /></div>
                  <div class="eitaa-field" data-modes="course,session,event,report,intro,pub_news"><label id="lblTeacher">استاد / ارائه‌دهنده</label><input id="msTeacher" class="glass-input" type="text" placeholder="حجت‌الاسلام والمسلمین دکتر ..." /></div>
                  <div class="eitaa-field" data-modes="course"><label>سوابق علمی استاد (اختیاری)</label><input id="msBio" class="glass-input" type="text" placeholder="استاد حوزه و دانشگاه" /></div>
                  <div class="eitaa-field" data-modes="session"><label>ناقد جلسه (اختیاری)</label><input id="msCritic" class="glass-input" type="text" placeholder="دکتر ..." /></div>
                  <div class="eitaa-field" data-modes="session"><label>دبیر جلسه (اختیاری)</label><input id="msModerator" class="glass-input" type="text" placeholder="جناب آقای ..." /></div>
                  <div class="eitaa-field" data-modes="course"><label>تعداد جلسات و روز</label><input id="msSessions" class="glass-input" type="text" placeholder="۶ جلسه _ پنجشنبه‌ها" /></div>
                  <div class="eitaa-field" data-modes="course,session,event,report"><label id="lblDate">تاریخ برگزاری</label><input id="msDate" class="glass-input" type="text" placeholder="از ۲۶ آبان ۱۴۰۵" /></div>
                  <div class="eitaa-field" data-modes="course,session,event"><label>ساعت برگزاری</label><input id="msTime" class="glass-input" type="text" placeholder="ساعت ۱۸ الی ۱۹:۳۰" /></div>
                  <div class="eitaa-field" data-modes="event"><label>مکان برگزاری</label><input id="msLocation" class="glass-input" type="text" placeholder="قم، سالن همایش‌های ..." /></div>
                  <div class="eitaa-field" data-modes="course,session,event"><label>مهلت ثبت‌نام (اختیاری)</label><input id="msDeadline" class="glass-input" type="text" placeholder="تا سه‌شنبه ۲۲ آبان" /></div>
                  <div class="eitaa-field" data-modes="course,session,event,intro"><label>لینک ثبت‌نام پرس‌لاین (اختیاری)</label><input id="msLink" class="glass-input" type="text" dir="ltr" placeholder="https://survey.porsline.ir/s/..." /></div>
                  <div class="eitaa-field" data-modes="pub_news"><label>ناشر / لینک‌های خبرگزاری (هر خط یک مورد)</label><textarea id="msExtra" class="glass-input" rows="3" placeholder="انتشارات سمت — یا لینک خبرگزاری‌ها..."></textarea></div>
                  <div class="eitaa-field" data-modes="report,intro,pub_news"><label id="lblDesc">متن خلاصه / توضیحات</label><textarea id="msDesc" class="glass-input" rows="3" placeholder="توضیحات یا خلاصه مباحث..."></textarea></div>
                  <div class="eitaa-field" data-modes="report"><label>لینک خبر در خبرگزاری (اختیاری)</label><input id="msNewsUrl" class="glass-input" type="text" dir="ltr" placeholder="https://fa.abna24.com/..." /></div>
                </div>
                <div class="eitaa-preview-box">
                  <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
                    <strong style="font-size:12.5px;">پیش‌نمایش آماده انتشار</strong>
                    <div style="display:flex; gap:6px;">
                      <button type="button" class="ghost-btn pro-btn-ic" id="btnClearMedia" style="padding:5px 10px; font-size:11px;">${ic('trash', 13)}<span>پاک کردن</span></button>
                      <button type="button" class="primary-btn pro-btn-ic" id="btnCopyMedia" style="padding:6px 14px; font-size:11.5px;">${ic('copy', 13)}<span>کپی متن</span></button>
                    </div>
                  </div>
                  <textarea id="msPreview" class="eitaa-preview-text"></textarea>
                </div>
              </div>
            </div>
          </div>
        </div>
      `;
    },
    onMount(bd) {
      let activeTpl = 'course';
      const val = (id) => (bd.querySelector('#' + id)?.value || '').trim();

      function setSubTypes(tpl) {
        const sel = bd.querySelector('#msSubType');
        const map = {
          event: [['conference', 'همایش تخصصی'], ['ceremony', 'مجلس عزاداری / یادبود']],
          intro: [['course_intro', 'معرفی دوره'], ['teacher_intro', 'آشنایی با استاد']],
          pub_news: [['book', 'معرفی کتاب / اثر پژوهشی'], ['press', 'بازتاب در خبرگزاری‌ها']],
        };
        sel.innerHTML = (map[tpl] || []).map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
      }

      function buildText() {
        const subType = val('msSubType'), order = val('msOrder');
        const group = (val('msGroup') || 'دین_شناسی').replace(/\s+/g, '_');
        const title = val('msTitle') || 'عنوان ...', sub = val('msSub'), audience = val('msAudience');
        const teacher = val('msTeacher'), bio = val('msBio'), critic = val('msCritic'), moderator = val('msModerator');
        const sessions = val('msSessions'), date = val('msDate'), time = val('msTime'), location = val('msLocation');
        const deadline = val('msDeadline'), link = val('msLink'), extra = val('msExtra'), desc = val('msDesc'), newsUrl = val('msNewsUrl');
        const tTag = teacher.replace(/حجت[‌ ]?الاسلام|و[ ]?المسلمین|آیت[‌ ]?الله|دکتر|استاد/g, '').trim().replace(/\s+/g, '_');

        let out = '';
        if (activeTpl === 'course') {
          out = `🔰 ${order ? order + ' دوره از دوره‌های' : 'دوره‌های'} کوتاه‌مدت مؤسسه امام هادی «علیه‌السلام»\n\n▫️ ${title}${sub ? '\n' + sub : ''}${audience ? '\n\n' + audience : ''}${teacher ? '\n\n🎙 استاد: ' + teacher : ''}${bio ? '\n' + bio : ''}${sessions ? '\n\n📌 ' + sessions : ''}${date ? '\n🗓 ' + date : ''}${time ? '\n🕰 ' + time : ''}${deadline ? '\n\nمهلت ثبت‌نام: ' + deadline : ''}${link ? '\n\n👇👇 لینک ثبت‌نام 👇👇\n' + link : ''}\n\n👇 راه‌های ارتباطی 👇\n۰۲۵-۳۷۷۲۵۲۲۵-۷\n\n@emamhadi_qom`;
        } else if (activeTpl === 'session') {
          out = `مؤسسه علمی فرهنگی امام هادی «علیه‌السلام»\n\nنشست علمی\n\n▫️ ${title}${sub ? '\n' + sub : ''}${teacher ? '\n\n🎙 ارائه‌دهنده: ' + teacher : ''}${critic ? '\n🎙 ناقد: ' + critic : ''}${moderator ? '\nدبیر جلسه: ' + moderator : ''}${date ? '\n\n🗓 ' + date : ''}${time ? '\n🕰 ' + time : ''}${deadline ? '\n\nمهلت ثبت‌نام: ' + deadline : ''}${link ? '\n\n👇👇 لینک ثبت‌نام 👇👇\n' + link : ''}\n\n👇 راه‌های ارتباطی 👇\n۰۲۵-۳۷۷۲۵۲۲۵-۷\n\n@emamhadi_qom`;
        } else if (activeTpl === 'event') {
          out = subType === 'ceremony'
            ? `▪️ ${title}${teacher ? '\n\n' + teacher : ''}${date ? '\n\n🗓 زمان: ' + date : ''}${time ? '\n🕰 ' + time : ''}${location ? '\n📌 مکان: ' + location : ''}\n\nمؤسسه علمی فرهنگی امام هادی علیه‌السلام\n@emamhadi_qom`
            : `مؤسسه علمی فرهنگی امام هادی علیه‌السلام برگزار می‌کند:\n\nهمایش تخصصی\n«${title}»${teacher ? '\n\n🎙 اساتید:\n' + teacher : ''}${date || time ? '\n\n🕰 زمان:\n' + [date, time].filter(Boolean).join(' — ') : ''}${location ? '\n📌 مکان: ' + location : ''}${deadline ? '\n\nمهلت ثبت‌نام: ' + deadline : ''}${link ? '\n\nلینک ثبت‌نام:\n' + link : ''}\n\nراه‌های ارتباطی:\n۰۲۵-۳۷۷۲۵۲۲۵-۷\n\n@emamhadi_qom`;
        } else if (activeTpl === 'report') {
          const hdr = order
            ? `🔰 گزارش تصویری ${order} دوره از دوره‌های کوتاه‌مدت مؤسسه امام هادی (علیه‌السلام)`
            : `🔰 گزارش تصویری برنامه «${title}» در مؤسسه امام هادی (علیه‌السلام)`;
          out = `${hdr}\n\n🔻 «${title}» از سلسله برنامه‌های کارگروه ${group.replace(/_/g, ' ')}${teacher ? ' با ارائه ' + teacher : ''}${date ? ' در ' + date : ''} برگزار شد.${desc ? '\n\n🔻 ' + desc : ''}${newsUrl ? '\n\n' + newsUrl : ''}\n\n❖ــــــــــــــــــــــــــــــــــــــــــــــــــــ❖\n\n#گزارش_تصویری\n#${group}${tTag ? '\n#' + tTag : ''}\n\n@emamhadi_qom`;
        } else if (activeTpl === 'intro') {
          const head = subType === 'teacher_intro' ? `🔻 آشنایی با ${teacher || 'استاد دوره'}:` : `📝 معرفی دوره «${title}»:`;
          const tag = subType === 'teacher_intro' ? '#معرفی_استاد' : '#معرفی_دوره';
          out = `${head}\n\n📌 ${desc || 'توضیحات معرفی را وارد کنید...'}${link ? '\n\nلینک ثبت‌نام:\n' + link : ''}\n\n${tag}\n#${group}${tTag ? '\n#' + tTag : ''}\n\n@emamhadi_qom`;
        } else {
          out = subType === 'press'
            ? `🔻 بازتاب «${title}» مؤسسه علمی فرهنگی امام هادی علیه‌السلام در خبرگزاری‌ها:\n\n${extra || 'خبرگزاری حوزه: ...\nخبرگزاری ابنا: ...'}${desc ? '\n\n' + desc : ''}\n\n@emamhadi_qom`
            : `📚 «${title}»${teacher ? '\n\nاثر: ' + teacher : ''}\n\nتهیه‌شده در: مؤسسه علمی فرهنگی امام هادی علیه‌السلام${extra ? '\nچاپ / ناشر: ' + extra : ''}${desc ? '\n\n' + desc : ''}\n\n@emamhadi_qom`;
        }
        bd.querySelector('#msPreview').value = out;
      }

      function updateForm() {
        bd.querySelector('#mediaModeHint').textContent = MODE_META[activeTpl] || '';
        setSubTypes(activeTpl);
        const lbls = {
          course:   { title: 'عنوان دوره', teacher: 'استاد دوره', date: 'بازه تاریخ برگزاری', order: 'ترتیب دوره (مثلاً نوزدهمین)' },
          session:  { title: 'عنوان نشست علمی', teacher: 'ارائه‌دهنده', date: 'تاریخ / مناسبت نشست' },
          event:    { title: 'عنوان همایش یا مراسم', teacher: 'اساتید / سخنرانان', date: 'تاریخ برگزاری' },
          report:   { title: 'عنوان دوره / نشست / همایش', teacher: 'استاد / سخنران', date: 'تاریخ یا ماه برگزاری', order: 'ترتیب دوره (اختیاری)', desc: 'خلاصه جلسه یا محور مباحث (اختیاری)' },
          intro:    { title: 'عنوان دوره', teacher: 'نام استاد', desc: 'متن معرفی دوره یا سوابق استاد' },
          pub_news: { title: 'عنوان کتاب یا رویداد خبری', teacher: 'مؤلف (برای کتاب)', desc: 'توضیح تکمیلی (اختیاری)' },
        }[activeTpl] || {};
        if (lbls.title) bd.querySelector('#lblTitle').textContent = lbls.title;
        if (lbls.teacher) bd.querySelector('#lblTeacher').textContent = lbls.teacher;
        if (lbls.date) bd.querySelector('#lblDate').textContent = lbls.date;
        if (lbls.order) bd.querySelector('#lblOrder').textContent = lbls.order;
        if (lbls.desc) bd.querySelector('#lblDesc').textContent = lbls.desc;

        bd.querySelectorAll('#mediaForm .eitaa-field[data-modes]').forEach(el => {
          el.classList.toggle('hidden-field', !(el.dataset.modes || '').split(',').includes(activeTpl));
        });
        buildText();
      }

      bd.querySelectorAll('#mediaTplNav .pro-cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          bd.querySelectorAll('#mediaTplNav .pro-cat-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          activeTpl = btn.dataset.tpl;
          updateForm();
        });
      });
      bd.querySelectorAll('#mediaForm input, #mediaForm textarea, #mediaForm select').forEach(el => {
        el.addEventListener('input', buildText);
        el.addEventListener('change', buildText);
      });
      bd.querySelector('#btnClearMedia').addEventListener('click', () => {
        bd.querySelectorAll('#mediaForm input, #mediaForm textarea').forEach(el => { el.value = ''; });
        buildText();
      });
      bd.querySelector('#btnCopyMedia').addEventListener('click', async () => {
        const txt = bd.querySelector('#msPreview').value;
        try { await navigator.clipboard.writeText(txt); } catch (_) {
          bd.querySelector('#msPreview').select(); document.execCommand('copy');
        }
        App.toast('متن آماده انتشار در کلیپ‌بورد کپی شد.');
      });
      updateForm();
    },
  });

  // ---------- پلاگین ۳: پالت دستورات سریع (Ctrl + K) ----------
  [
    { label: 'باز کردن تولید محتوای رسانه‌ای', cat: 'محتوا', key: '', run: () => App.openModal('media_studio') },
    { label: 'باز کردن پنجره تنظیمات سامانه', cat: 'تنظیمات', key: 'Ctrl+,', run: () => App.openModal('preferences') },
    { label: 'رفتن به داشبورد مدیریتی و BI', cat: 'ناوبری', key: 'Ctrl+1', run: () => App.goPage('dashboard') },
    { label: 'رفتن به دستیار هوشمند (AI)', cat: 'ناوبری', key: 'Ctrl+2', run: () => App.goPage('chat') },
    { label: 'رفتن به مدیریت و پردازش اسناد', cat: 'ناوبری', key: 'Ctrl+3', run: () => App.goPage('docs') },
    { label: 'خروجی PDF رسمی از داشبورد BI', cat: 'گزارش', key: '', run: () => window.exportBiOfficialReport?.('pdf') },
    { label: 'خروجی Word رسمی از داشبورد BI', cat: 'گزارش', key: '', run: () => window.exportBiOfficialReport?.('docx') },
    { label: 'تغییر تم روشن و تیره', cat: 'ظاهر', key: 'Ctrl+Shift+T', run: () => App.toggleTheme() },
    { label: 'جمع یا باز کردن سایدبار', cat: 'ظاهر', key: 'Ctrl+B', run: () => App.toggleSidebar() },
  ].forEach(c => App.registerCommand(c));

  App.registerModal('cmd_palette', {
    render() {
      return `
        <div class="pro-modal-box cmd-box" role="dialog" aria-modal="true">
          <div class="cmd-input-wrap">
            <span style="color:var(--s-text-dim); display:inline-flex;">${ic('search', 16)}</span>
            <input id="cmdSearchInput" class="cmd-input" type="text" placeholder="نام بخش یا دستور را تایپ کنید..." />
            <span class="pro-kbd">ESC</span>
          </div>
          <div class="cmd-list" id="cmdList"></div>
        </div>
      `;
    },
    onMount(bd) {
      let idx = 0, filtered = App.getCommands();
      const inp = bd.querySelector('#cmdSearchInput');
      const list = bd.querySelector('#cmdList');
      const draw = () => {
        list.innerHTML = filtered.map((c, i) => `
          <button type="button" class="cmd-item ${i === idx ? 'selected' : ''}" data-i="${i}">
            <span>${c.label}</span><span class="pro-kbd">${c.key || c.cat}</span>
          </button>
        `).join('');
        list.querySelectorAll('.cmd-item').forEach(b => b.addEventListener('click', () => {
          const it = filtered[Number(b.dataset.i)]; App.closeAllModals(); it?.run?.();
        }));
      };
      inp.addEventListener('input', () => {
        const q = inp.value.trim().toLowerCase();
        filtered = App.getCommands().filter(c => c.label.toLowerCase().includes(q) || c.cat.toLowerCase().includes(q));
        idx = 0; draw();
      });
      inp.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') { e.preventDefault(); idx = (idx + 1) % Math.max(1, filtered.length); draw(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); idx = (idx - 1 + Math.max(1, filtered.length)) % Math.max(1, filtered.length); draw(); }
        else if (e.key === 'Enter' && filtered[idx]) { e.preventDefault(); const fn = filtered[idx].run; App.closeAllModals(); fn?.(); }
      });
      bd._resetCmd = () => { filtered = App.getCommands(); idx = 0; inp.value = ''; draw(); setTimeout(() => inp.focus(), 25); };
    },
    onOpen(bd) { bd._resetCmd && bd._resetCmd(); },
  });

  // شروع کامل سیستم پس از ثبت همه پلاگین‌ها
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => App.boot());
  else App.boot();
})();
