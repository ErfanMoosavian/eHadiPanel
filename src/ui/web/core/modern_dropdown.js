(() => {
  // ===== ۱. تبدیل خودکار تمام منوهای بازشونده (<select>) به منوی مدرن داشبوردی =====
  let activePortal = null;

  function closePortal() {
    if (activePortal) {
      activePortal.menu.remove();
      activePortal.trigger.classList.remove('open');
      activePortal = null;
    }
  }

  function enhanceSelect(sel) {
    if (!sel || sel.dataset.ehSelectReady === '1') return;
    sel.dataset.ehSelectReady = '1';
    sel.classList.add('eh-native-hidden');

    const wrap = document.createElement('div');
    wrap.className = 'eh-cselect eh-cselect-wrap';
    if (sel.classList.contains('bi-select') || sel.closest('.bi-toolbar')) {
      wrap.classList.add('eh-bi-cselect');
      if (sel.id) wrap.classList.add('eh-sel-' + sel.id);
    }
    if (sel.id === 'selEitaaTpl' || sel.closest('#ehEitaaTplBar')) {
      wrap.classList.add('eh-eitaa-cselect');
    }
    if (sel.classList.contains('eh-mem-select') || sel.closest('.eh-mem-modal')) {
      wrap.classList.add('eh-mem-cselect');
    }
    if (sel.style.minWidth) wrap.style.minWidth = sel.style.minWidth;

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'eh-cselect-btn';
    const lbl = document.createElement('span');
    lbl.className = 'eh-cselect-lbl';
    const chev = document.createElement('span');
    chev.className = 'eh-cselect-chev';
    chev.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';
    trigger.appendChild(lbl);
    trigger.appendChild(chev);

    sel.parentNode.insertBefore(wrap, sel);
    wrap.appendChild(sel);
    wrap.appendChild(trigger);

    const syncLabel = () => {
      const opt = sel.options[sel.selectedIndex];
      let txt = opt ? opt.textContent.trim() : 'انتخاب...';
      if (sel.id === 'fltTeacher' && opt && opt.value && typeof window.formatTeacherShort === 'function') {
        const shortTxt = window.formatTeacherShort(txt);
        if (shortTxt) txt = shortTxt;
      }
      lbl.textContent = txt;
      trigger.title = opt ? opt.textContent.trim() : '';
    };
    syncLabel();

    sel.addEventListener('change', syncLabel);
    new MutationObserver(syncLabel).observe(sel, { childList: true, subtree: true, attributes: true });

    trigger.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (activePortal && activePortal.sel === sel) { closePortal(); return; }
      closePortal();

      const normFaSearch = (s) => String(s || '')
        .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
        .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
        .replace(/[يیى]/g, 'ی').replace(/[كک]/g, 'ک').replace(/[ھہۀة]/g, 'ه').replace(/[آأإ]/g, 'ا').replace(/\u200c/g, ' ')
        .replace(/\s+/g, ' ').trim().toLowerCase();

      const menu = document.createElement('div');
      menu.className = 'eh-cselect-menu';
      menu.setAttribute('dir', 'rtl');
      menu.dataset.ehPortalManaged = '1';

      const optsArr = Array.from(sel.options);
      const isTeacherSel = (sel.id === 'fltTeacher');
      const listWrap = document.createElement('div');
      listWrap.className = 'eh-cselect-list';
      listWrap.setAttribute('dir', 'rtl');
      let searchInp = null;

      if (optsArr.length > 10) {
        const sw = document.createElement('div');
        sw.className = 'eh-cselect-search-wrap';
        searchInp = document.createElement('input');
        searchInp.type = 'text';
        searchInp.className = 'eh-cselect-search';
        searchInp.placeholder = 'جست‌وجو در گزینه‌ها...';
        searchInp.addEventListener('click', (ev) => ev.stopPropagation());
        searchInp.addEventListener('mousedown', (ev) => ev.stopPropagation());
        sw.appendChild(searchInp);
        menu.appendChild(sw);
      }

      const emptyNote = document.createElement('div');
      emptyNote.className = 'eh-cselect-empty';
      emptyNote.textContent = 'موردی یافت نشد';
      emptyNote.hidden = true;

      const itemNodes = [];
      let longestLen = 0;
      optsArr.forEach((opt, idx) => {
        const rawTxt = (opt.textContent || '').trim();
        let dispTxt = rawTxt;
        if (isTeacherSel && opt.value && typeof window.formatTeacherShort === 'function') {
          const st = window.formatTeacherShort(rawTxt);
          if (st) dispTxt = st;
        }
        if (dispTxt.length > longestLen) longestLen = dispTxt.length;

        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'eh-cselect-item' + (idx === sel.selectedIndex ? ' selected' : '');
        item.title = rawTxt;

        const spTxt = document.createElement('span');
        spTxt.className = 'eh-cselect-item-txt';
        spTxt.textContent = dispTxt;
        item.appendChild(spTxt);

        if (idx === sel.selectedIndex) {
          const spChk = document.createElement('span');
          spChk.className = 'eh-cselect-check';
          spChk.textContent = '✓';
          item.appendChild(spChk);
        }

        item.dataset.searchKey = normFaSearch(`${dispTxt} ${rawTxt}`);
        item.addEventListener('click', (ev) => {
          ev.stopPropagation();
          sel.selectedIndex = idx;
          sel.dispatchEvent(new Event('change', { bubbles: true }));
          syncLabel();
          closePortal();
        });
        listWrap.appendChild(item);
        itemNodes.push(item);
      });
      listWrap.appendChild(emptyNote);
      menu.appendChild(listWrap);

      const getVisibleItems = () => itemNodes.filter(b => !b.hidden);
      let focusIdx = Math.max(0, optsArr.findIndex((_, i) => i === sel.selectedIndex));

      const highlightIdx = (nextI) => {
        const vis = getVisibleItems();
        if (!vis.length) return;
        focusIdx = (nextI + vis.length) % vis.length;
        vis.forEach((b, i) => b.classList.toggle('kbd-focus', i === focusIdx));
        vis[focusIdx].scrollIntoView({ block: 'nearest' });
      };

      const onMenuKey = (ev) => {
        if (ev.key === 'Escape') { ev.preventDefault(); closePortal(); return; }
        if (ev.key === 'ArrowDown') { ev.preventDefault(); highlightIdx(focusIdx + 1); return; }
        if (ev.key === 'ArrowUp') { ev.preventDefault(); highlightIdx(focusIdx - 1); return; }
        if (ev.key === 'Enter') {
          const vis = getVisibleItems();
          if (vis.length) {
            ev.preventDefault();
            (vis[focusIdx] || vis[0]).click();
          }
        }
      };
      if (searchInp) {
        searchInp.addEventListener('keydown', onMenuKey);
        searchInp.addEventListener('input', () => {
          const q = normFaSearch(searchInp.value);
          let shown = 0;
          itemNodes.forEach(btn => {
            const ok = !q || (btn.dataset.searchKey || '').includes(q);
            btn.hidden = !ok;
            btn.classList.remove('kbd-focus');
            if (ok) shown += 1;
          });
          focusIdx = 0;
          emptyNote.hidden = shown > 0;
        });
      }

      menu.addEventListener('click', (ev) => ev.stopPropagation());
      menu.addEventListener('mousedown', (ev) => ev.stopPropagation());
      menu.addEventListener('wheel', (ev) => {
        ev.stopPropagation();
        if (listWrap.scrollHeight > listWrap.clientHeight + 1) {
          const atTop = listWrap.scrollTop <= 0 && ev.deltaY < 0;
          const atBot = listWrap.scrollTop + listWrap.clientHeight >= listWrap.scrollHeight - 1 && ev.deltaY > 0;
          if (atTop || atBot) ev.preventDefault();
        }
      }, { passive: false });

      document.body.appendChild(menu);

      const r = trigger.getBoundingClientRect();
      const estTextW = Math.ceil(longestLen * 6.9) + 56;
      const menuW = Math.min(Math.max(r.width, estTextW, 236), Math.min(430, window.innerWidth - 24));
      const spaceBelow = window.innerHeight - r.bottom - 14;
      const spaceAbove = r.top - 14;
      const openAbove = spaceBelow < 220 && spaceAbove > spaceBelow;
      const maxH = Math.max(150, Math.min(340, openAbove ? spaceAbove : spaceBelow));

      menu.style.width = `${menuW}px`;
      menu.style.maxHeight = `${maxH}px`;

      const actualH = Math.min(maxH, menu.scrollHeight || maxH);
      const topPos = openAbove ? Math.max(10, r.top - actualH - 6) : (r.bottom + 6);
      const leftPos = Math.min(window.innerWidth - menuW - 12, Math.max(12, r.right - menuW));

      menu.style.top = `${topPos}px`;
      menu.style.left = `${leftPos}px`;
      trigger.classList.add('open');
      requestAnimationFrame(() => {
        menu.classList.add('open');
        const selItem = listWrap.querySelector('.eh-cselect-item.selected');
        if (selItem) { try { selItem.scrollIntoView({ block: 'nearest' }); } catch (_) {} }
        if (searchInp) { try { searchInp.focus({ preventScroll: true }); } catch (_) {} }
      });
      activePortal = { sel, trigger, menu };
    });
  }

  function scanSelects(root = document) {
    root.querySelectorAll('select.glass-select, select.bi-select, select.eh-mem-select, .eh-mem-modal select').forEach(enhanceSelect);
  }

  document.addEventListener('click', (e) => {
    const seg = e.target && e.target.closest ? e.target.closest('.eh-mem-seg-group .eh-mem-seg') : null;
    if (!seg) return;
    const grp = seg.closest('.eh-mem-seg-group');
    if (grp) {
      grp.querySelectorAll('.eh-mem-seg').forEach(b => b.classList.remove('active'));
      seg.classList.add('active');
    }
  }, true);
  window.__ehScanSelects = scanSelects;

  document.addEventListener('click', closePortal);
  window.addEventListener('resize', closePortal);
  window.addEventListener('scroll', (e) => {
    if (activePortal && activePortal.menu && (e.target === activePortal.menu || activePortal.menu.contains(e.target))) {
      return;
    }
    closePortal();
  }, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePortal(); });

  let _selScanTmr = null;
  new MutationObserver((muts) => {
    let maybeSelect = false;
    for (let i = 0; i < muts.length; i++) {
      const added = muts[i].addedNodes;
      for (let j = 0; j < added.length; j++) {
        const n = added[j];
        if (n && n.nodeType === 1 && (n.tagName === 'SELECT' || (n.querySelector && n.querySelector('select')))) {
          maybeSelect = true;
          break;
        }
      }
      if (maybeSelect) break;
    }
    if (!maybeSelect) return;
    clearTimeout(_selScanTmr);
    _selScanTmr = setTimeout(() => scanSelects(), 45);
  }).observe(document.documentElement, { childList: true, subtree: true });

  // ===== ۲. رادار مدیریتی امروز + دفترچه تصمیم‌ها و بکاپ فوری در داشبورد =====
  function mountExecutiveRadar() {
    const dash = document.getElementById('page-dashboard');
    const statsGrid = dash && dash.querySelector('.stats-grid');
    if (!dash || !statsGrid || document.getElementById('ehExecRadarBox')) return;

    const box = document.createElement('div');
    box.id = 'ehExecRadarBox';
    box.className = 'eh-radar-grid';
    box.innerHTML = `
      <div class="glass-card eh-radar-card">
        <div class="card-title" style="margin-bottom:10px;">
          <span>رادار مدیریتی و وضعیت امروز</span>
          <div style="display:flex; gap:6px;">
            <button type="button" class="ghost-btn bi-mini-btn" id="btnQuickBackup">بکاپ فوری دیتابیس</button>
            <button type="button" class="ghost-btn bi-mini-btn" id="btnQuickBoardroom">حالت ارائه جلسه</button>
          </div>
        </div>
        <div id="ehRadarItems" class="eh-radar-list">
          <div class="eh-radar-row"><span>در حال بررسی سلامت داده‌ها و رویدادها...</span></div>
        </div>
      </div>

      <div class="glass-card eh-radar-card">
        <div class="card-title" style="margin-bottom:10px;">
          <span>دفترچه تصمیم‌ها و پیگیری‌های مدیر</span>
          <span class="stat-pill" id="ehDecCount">۰ مورد</span>
        </div>
        <div style="display:flex; gap:6px; margin-bottom:10px;">
          <input id="inpNewDecision" class="glass-input" type="text" placeholder="ثبت تصمیم یا پیگیری جدید و Enter..." style="flex:1; padding:6px 10px; font-size:11.5px;" />
          <button type="button" class="primary-btn bi-mini-btn" id="btnAddDecision">ثبت</button>
        </div>
        <div id="ehDecisionsList" class="eh-radar-list" style="max-height:145px; overflow-y:auto;"></div>
      </div>
    `;
    statsGrid.insertAdjacentElement('afterend', box);

    document.getElementById('btnQuickBackup').addEventListener('click', async () => {
      const r = await window.pywebview?.api?.create_backup_now?.();
      if (r && r.ok) window.showToast?.(`بکاپ امن ذخیره شد (${(r.files || []).length} فایل).`);
      else window.showToast?.('خطا در بکاپ: ' + (r?.error || ''));
    });

    document.getElementById('btnQuickBoardroom').addEventListener('click', () => {
      window.eHadiApp?.openModal('exec_analytics');
      setTimeout(() => document.getElementById('btnOpenBoardroom')?.click(), 300);
    });

    const addDec = async () => {
      const inp = document.getElementById('inpNewDecision');
      const title = (inp.value || '').trim();
      if (!title) return;
      inp.value = '';
      await window.pywebview?.api?.save_decision_item?.({ title });
      loadDecisionsUI();
    };
    document.getElementById('btnAddDecision').addEventListener('click', addDec);
    document.getElementById('inpNewDecision').addEventListener('keydown', (e) => { if (e.key === 'Enter') addDec(); });

    loadRadarUI();
    loadDecisionsUI();
  }

  async function loadRadarUI() {
    const el = document.getElementById('ehRadarItems');
    if (!el) return;
    try {
      const res = await window.pywebview?.api?.get_executive_analytics?.({});
      const k = (res && res.kpis) || {};
      const dups = (res && res.data_health && res.data_health.duplicates) ? res.data_health.duplicates.length : 0;
      const rows = [
        `<span>مجموع حضور ثبت‌شده: <strong>${Number(k.total_attendance || 0).toLocaleString('fa-IR')}</strong> نفر در ${Number(k.total_courses || 0).toLocaleString('fa-IR')} دوره</span><button type="button" class="eh-mini-btn" onclick="window.eHadiApp?.openModal('exec_analytics')">مرکز آمار</button>`,
        `<span>دبیرخانه هوشمند: <strong>${Number(k.letters_count || 0).toLocaleString('fa-IR')}</strong> نامه و گزارش رسمی ثبت‌شده</span><button type="button" class="eh-mini-btn" onclick="window.eHadiApp?.openModal('letter_registry')">دبیرخانه</button>`,
      ];
      el.innerHTML = rows.map(r => `<div class="eh-radar-row">${r}</div>`).join('');
    } catch (_) {}
  }

  async function loadDecisionsUI() {
    const el = document.getElementById('ehDecisionsList');
    const cnt = document.getElementById('ehDecCount');
    if (!el) return;
    const res = await window.pywebview?.api?.get_decisions?.();
    const list = (res && res.decisions) || [];
    if (cnt) cnt.textContent = `${list.length.toLocaleString('fa-IR')} مورد`;
    if (!list.length) {
      el.innerHTML = '<div class="eh-radar-row" style="color:var(--s-text-dim);">تصمیمی ثبت نشده است؛ موردی اضافه کنید تا همیشه جلو چشمتان باشد.</div>';
      return;
    }
    el.innerHTML = list.map(d => `
      <div class="eh-radar-row ${d.done ? 'done' : ''}">
        <label style="display:flex; align-items:center; gap:8px; cursor:pointer; flex:1;">
          <input type="checkbox" ${d.done ? 'checked' : ''} data-toggle-dec="${d.id}" />
          <span>${d.title}</span>
        </label>
        <button type="button" class="eh-mini-btn" data-del-dec="${d.id}" title="حذف">✕</button>
      </div>
    `).join('');

    el.querySelectorAll('[data-toggle-dec]').forEach(chk => {
      chk.addEventListener('change', async () => {
        const it = list.find(x => x.id === chk.dataset.toggleDec);
        if (!it) return;
        it.done = chk.checked;
        await window.pywebview?.api?.save_decision_item?.(it);
        loadDecisionsUI();
      });
    });
    el.querySelectorAll('[data-del-dec]').forEach(btn => {
      btn.addEventListener('click', async () => {
        await window.pywebview?.api?.delete_decision_item?.(btn.dataset.delDec);
        loadDecisionsUI();
      });
    });
  }

  // لوگوی برداری در نوار عنوان
  function mountTitlebarLogo() {
    const badge = document.querySelector('.title-badge');
    if (!badge || badge.querySelector('.eh-title-svg')) return;
    const img = document.createElement('img');
    img.src = 'assets/ehadi_logo.svg';
    img.className = 'eh-title-svg';
    img.width = 18;
    img.height = 18;
    img.style.borderRadius = '5px';
    badge.insertBefore(img, badge.firstChild);
  }

  window.addEventListener('DOMContentLoaded', () => { scanSelects(); mountTitlebarLogo(); });
  window.addEventListener('pywebviewready', () => {
    setTimeout(() => { scanSelects(); mountTitlebarLogo(); mountExecutiveRadar(); }, 250);
  });
})();
