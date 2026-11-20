(() => {
  const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const BUILTIN_FONTS = ['Vazirmatn', 'IRANSans', 'Tahoma', 'Calibri', 'Arial', 'B Nazanin', 'B Mitra', 'B Zar'];

  function buildFontOptions(selectedVal, customFonts) {
    const names = [...BUILTIN_FONTS];
    (customFonts || []).forEach(f => {
      if (f && f.name && !names.includes(f.name)) names.unshift(f.name);
    });
    if (selectedVal && !names.includes(selectedVal)) names.unshift(selectedVal);
    return names.map(n => `<option value="${esc(n)}" ${n === selectedVal ? 'selected' : ''}>${esc(n)}</option>`).join('');
  }

  function mountBrandingCard() {
    const settingsPage = document.getElementById('page-settings');
    if (!settingsPage || document.getElementById('brandingCard')) return;

    const card = document.createElement('div');
    card.id = 'brandingCard';
    card.className = 'glass-card spotlight-card';
    card.style.cssText = 'display:flex; flex-direction:column; gap:16px; margin-top:16px;';
    card.innerHTML = `
      <div class="card-title" style="margin-bottom:0;">
        <span>هویت بصری، سربرگ، متن‌های پیش‌فرض و مدیریت فونت</span>
        <span class="stat-pill">چاپ A4 راست‌چین + تاریخ شمسی</span>
      </div>

      <div class="brand-setup-grid">
        <div class="brand-logo-box">
          <div class="brand-logo-preview" id="brandLogoPreview"><span>بدون لوگو</span></div>
          <button class="ghost-btn bi-mini-btn" id="btnPickLogo">انتخاب لوگو (PNG / JPG)</button>
        </div>

        <div style="flex:1; display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px;">
          <div class="form-group">
            <label>عنوان رسمی مؤسسه در سربرگ</label>
            <input id="inpOrgName" class="glass-input" type="text" />
          </div>
          <div class="form-group">
            <label>نام واحد / زیرعنوان سربرگ</label>
            <input id="inpUnitName" class="glass-input" type="text" />
          </div>
          <div class="form-group">
            <label>تم رنگی سربرگ و جداول</label>
            <select id="inpBrandTheme" class="glass-select">
              <option value="emerald_beige">سبز زمردی و بژ سازمانی (الهام‌گرفته از نمونه)</option>
              <option value="steel_beige">آبی فولادی و بژ سازمانی</option>
            </select>
          </div>
          <div class="form-group">
            <label>عنوان پیش‌فرض اکسل / گزارش</label>
            <input id="inpExcelTitle" class="glass-input" type="text" />
          </div>
        </div>
      </div>

      <div style="display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px;">
        <div class="form-group">
          <label>متن پیش‌فرض بالای گزارش‌ها (مقدمه / توضیح)</label>
          <input id="inpDefaultIntro" class="glass-input" type="text" />
        </div>
        <div class="form-group">
          <label>آدرس / متن پاورقی پایین صفحه</label>
          <input id="inpFooterText" class="glass-input" type="text" /></div><div class="form-group"><label>تلفن / واحد تماس پاورقی</label><input id="inpContactText" class="glass-input" type="text" />
        </div>
      </div>

      <div class="font-manager-box">
        <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
          <strong style="font-size:12.5px; color:#f8fafc;">انتخاب و افزودن فونت (PDF، Word و Excel)</strong>
          <div style="display:flex; gap:8px; align-items:center;">
            <input id="inpNewFontLabel" class="glass-input" type="text" style="width:160px; padding:6px 10px; font-size:11.5px;" placeholder="نام دلخواه فونت (اختیاری)" />
            <button class="ghost-btn bi-mini-btn" id="btnAddFontFile">+ افزودن فایل فونت (.ttf / .otf)</button>
          </div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px;">
          <div class="form-group">
            <label>فونت خروجی PDF</label>
            <select id="selPdfFont" class="glass-select"></select>
          </div>
          <div class="form-group">
            <label>فونت خروجی Word (.docx)</label>
            <select id="selWordFont" class="glass-select"></select>
          </div>
          <div class="form-group">
            <label>فونت خروجی Excel (.xlsx)</label>
            <select id="selExcelFont" class="glass-select"></select>
          </div>
        </div>
      </div>

      <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;">
        <div style="display:flex; gap:18px; font-size:12px; color:#cbd5e1; align-items:center; flex-wrap:wrap;">
          <label style="display:inline-flex; align-items:center; gap:6px; cursor:pointer;">
            <input type="checkbox" id="chkBismillah" /> نمایش «بسم‌الله‌الرحمن‌الرحیم»
          </label>
          <label style="display:inline-flex; align-items:center; gap:6px; cursor:pointer;">
            <input type="checkbox" id="chkSignature" /> نمایش کادر امضا
          </label>
          <input id="inpSigTitle" class="glass-input" type="text" style="width:220px; padding:5px 10px; font-size:11.5px;" placeholder="عنوان امضا..." />
        </div>
        <button class="primary-btn" id="btnSaveBranding">ذخیره تنظیمات سربرگ و فونت</button>
      </div>
    `;
    settingsPage.appendChild(card);

    document.getElementById('btnPickLogo').addEventListener('click', async () => {
      const res = await pywebview.api.select_logo_dialog();
      if (res && res.cancelled) return;
      if (res && res.ok) {
        applyLogoPreview(res.logo_data_uri);
        window.showToast && window.showToast('لوگوی مؤسسه با موفقیت ثبت شد.');
      } else {
        window.showToast && window.showToast('خطا در انتخاب لوگو: ' + ((res && res.error) || ''));
      }
    });

    document.getElementById('btnAddFontFile').addEventListener('click', async () => {
      const lbl = document.getElementById('inpNewFontLabel').value.trim();
      const res = await pywebview.api.select_font_dialog(lbl);
      if (res && res.cancelled) return;
      if (res && res.ok) {
        document.getElementById('inpNewFontLabel').value = '';
        await loadBrandingUI();
        window.showToast && window.showToast(`فونت «${res.font_name}» اضافه و فعال شد.`);
      } else {
        window.showToast && window.showToast('خطا در افزودن فونت: ' + ((res && res.error) || ''));
      }
    });

    document.getElementById('btnSaveBranding').addEventListener('click', async () => {
      const payload = {
        org_name: document.getElementById('inpOrgName').value.trim(),
        unit_name: document.getElementById('inpUnitName').value.trim(),
        default_intro_text: document.getElementById('inpDefaultIntro').value.trim(),
        footer_text: document.getElementById('inpFooterText').value.trim(),
        contact_text: document.getElementById('inpContactText').value.trim(),
        excel_default_title: document.getElementById('inpExcelTitle').value.trim(),
        signature_title: document.getElementById('inpSigTitle').value.trim(),
        theme: document.getElementById('inpBrandTheme').value,
        pdf_font: document.getElementById('selPdfFont').value,
        word_font: document.getElementById('selWordFont').value,
        excel_font: document.getElementById('selExcelFont').value,
        show_bismillah: document.getElementById('chkBismillah').checked,
        show_signature: document.getElementById('chkSignature').checked,
      };
      const res = await pywebview.api.save_branding_settings(payload);
      if (res && res.ok) window.showToast && window.showToast('تنظیمات سربرگ، متن پیش‌فرض و فونت ذخیره شد.');
    });
  }

  function applyLogoPreview(dataUri) {
    const box = document.getElementById('brandLogoPreview');
    if (!box) return;
    box.innerHTML = dataUri ? `<img src="${dataUri}" alt="Logo" />` : '<span>بدون لوگو</span>';
  }

  async function loadBrandingUI() {
    mountBrandingCard();
    try {
      const res = await pywebview.api.get_branding_settings();
      if (res && res.ok && res.branding) {
        const b = res.branding;
        document.getElementById('inpOrgName').value = b.org_name || '';
        document.getElementById('inpUnitName').value = b.unit_name || '';
        document.getElementById('inpDefaultIntro').value = b.default_intro_text || '';
        document.getElementById('inpFooterText').value = b.footer_text || '';
        document.getElementById('inpContactText').value = b.contact_text || '';
        document.getElementById('inpExcelTitle').value = b.excel_default_title || '';
        document.getElementById('inpSigTitle').value = b.signature_title || '';
        document.getElementById('inpBrandTheme').value = b.theme || 'emerald_beige';
        document.getElementById('chkBismillah').checked = Boolean(b.show_bismillah);
        document.getElementById('chkSignature').checked = b.show_signature !== false;

        document.getElementById('selPdfFont').innerHTML = buildFontOptions(b.pdf_font || 'Vazirmatn', b.custom_fonts);
        document.getElementById('selWordFont').innerHTML = buildFontOptions(b.word_font || 'Tahoma', b.custom_fonts);
        document.getElementById('selExcelFont').innerHTML = buildFontOptions(b.excel_font || 'Tahoma', b.custom_fonts);
        applyLogoPreview(res.logo_data_uri);
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function runExport(kind, payload) {
    try {
      const fn = kind === 'pdf' ? pywebview.api.export_report_pdf : pywebview.api.export_report_docx;
      const res = await fn(payload);
      if (res && res.cancelled) return;
      if (res && res.ok) {
        const label = kind === 'pdf' ? 'PDF رسمی' : 'Word رسمی';
        window.showToast && window.showToast(`گزارش ${label} ساخته شد: ${res.path}`);
        await pywebview.api.open_file_path(res.path);
      } else {
        window.showToast && window.showToast('خطا در ساخت گزارش: ' + ((res && res.error) || 'نامشخص'));
      }
    } catch (e) {
      window.showToast && window.showToast('خطا در خروجی گزارش: ' + e);
    }
  }

  function extractBubblePayload(bubble) {
    const copyBtn = bubble.querySelector('.copy-mini-btn');
    let mdText = '';
    if (copyBtn) {
      const oc = copyBtn.getAttribute('onclick') || '';
      const m = oc.match(/copyText\('([^']+)'\)/);
      if (m && window[m[1]]) mdText = window[m[1]];
    }
    if (!mdText) {
      const body = bubble.querySelector('.msg-body');
      mdText = body ? body.innerText : '';
    }
    let title = 'گزارش تحلیلی هوشمند مؤسسه امام هادی (ع)';
    const prev = bubble.previousElementSibling;
    if (prev && prev.classList.contains('msg-user')) {
      const q = (prev.querySelector('.msg-body')?.innerText || '').trim();
      if (q) title = q.slice(0, 75);
    }
    const cites = Array.from(bubble.querySelectorAll('.cite-chip')).map(ch => {
      const parts = (ch.textContent || '').replace('📄', '').trim().split('—');
      return { file_name: (parts[0] || '').trim(), location: (parts[1] || '').trim() };
    });
    return { title, content: mdText, citations: cites, tables: [] };
  }

  function injectChatExportButtons(bubble) {
    if (!bubble || !bubble.classList.contains('msg-ai') || bubble.classList.contains('is-streaming')) return;
    const copyBtn = bubble.querySelector('.copy-mini-btn');
    if (!copyBtn || bubble.querySelector('.rep-export-btn')) return;

    const wrap = copyBtn.parentElement;
    const btnPdf = document.createElement('button');
    btnPdf.className = 'copy-mini-btn rep-export-btn rep-pdf';
    btnPdf.textContent = 'PDF رسمی';
    btnPdf.onclick = () => runExport('pdf', extractBubblePayload(bubble));

    const btnWord = document.createElement('button');
    btnWord.className = 'copy-mini-btn rep-export-btn rep-word';
    btnWord.textContent = 'Word رسمی';
    btnWord.onclick = () => runExport('docx', extractBubblePayload(bubble));

    wrap.insertBefore(btnWord, copyBtn);
    wrap.insertBefore(btnPdf, btnWord);
  }

  function observeChatForButtons() {
    const stream = document.getElementById('chatStream');
    if (!stream) return;
    const scan = () => stream.querySelectorAll('.msg-ai').forEach(injectChatExportButtons);
    scan();
    const obs = new MutationObserver(scan);
    obs.observe(stream, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  }

  window.exportBiOfficialReport = function (kind) {
    const kpiEls = document.querySelectorAll('#biLensViewport .bi-kpi');
    const kpis = Array.from(kpiEls).map(el => ({
      label: el.querySelector('.bi-kpi-label')?.textContent?.trim() || '',
      value: el.querySelector('.bi-kpi-val')?.textContent?.trim() || '',
    }));
    const activeTab = document.querySelector('.bi-lens-tab.active span')?.textContent?.trim() || 'هوش تجاری';
    const rows = Array.from(document.querySelectorAll('#biLensViewport .bi-bar-row')).slice(0, 15).map((r, i) => [
      i + 1,
      r.querySelector('.bi-bar-name')?.textContent?.trim() || '',
      r.querySelector('.bi-bar-num')?.textContent?.trim() || '',
    ]);
    runExport(kind, {
      title: `گزارش مدیریتی داشبورد — ${activeTab}`,
      content: `گزارش تحلیلی استخراج‌شده از داده‌های زنده **${activeTab}** در پایگاه داده مؤسسه.`,
      kpis,
      tables: rows.length ? [{ title: 'خلاصه اقلام و شاخص‌های برتر', columns: ['ردیف', 'عنوان', 'مقدار / تعداد'], rows }] : [],
    });
  };

  function injectBiReportButtons() {
    const hdr = document.querySelector('.bi-hub-header');
    if (!hdr || document.getElementById('biOfficialPdfBtn')) return;
    const grp = document.createElement('div');
    grp.style.cssText = 'display:flex; gap:6px; align-items:center;';
    grp.innerHTML = `
      <button class="ghost-btn bi-mini-btn" id="biOfficialPdfBtn">گزارش PDF رسمی</button>
      <button class="ghost-btn bi-mini-btn" id="biOfficialDocxBtn">گزارش Word</button>
    `;
    const refBtn = document.getElementById('biGlobalRefresh');
    if (refBtn) hdr.insertBefore(grp, refBtn);
    else hdr.appendChild(grp);

    document.getElementById('biOfficialPdfBtn').addEventListener('click', () => window.exportBiOfficialReport('pdf'));
    document.getElementById('biOfficialDocxBtn').addEventListener('click', () => window.exportBiOfficialReport('docx'));
  }

  window.addEventListener('pywebviewready', () => {
    loadBrandingUI();
    observeChatForButtons();
    setTimeout(injectBiReportButtons, 350);
  });
})();