window.eHadiCharts = (() => {
  const FA_DIGITS = ['\u06f0','\u06f1','\u06f2','\u06f3','\u06f4','\u06f5','\u06f6','\u06f7','\u06f8','\u06f9'];
  const toFa = (v) => String(v ?? '').replace(/\d/g, d => FA_DIGITS[Number(d)]);
  const fmtNum = (n) => toFa(Number(n || 0).toLocaleString('en-US'));
  const PALETTE = ['#10b981', '#38bdf8', '#f59e0b', '#818cf8', '#14b8a6', '#ec4899', '#f97316'];

  function escXml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function formatTeacherShort(raw) {
    let s = String(raw || '')
      .replace(/\u064a/g, '\u06cc')
      .replace(/\u0643/g, '\u06a9')
      .replace(/[\u0623\u0625]/g, '\u0627')
      .replace(/[\u200c\u200f\u200e]+/g, ' ')
      .replace(/\s+/g, ' ')
      .replace(/(\.{2,}|\u2026)+$/g, '')
      .trim();
    if (!s) return '\u0646\u0627\u0645\u0634\u062e\u0635';

    const collective = [
      '\u062c\u0645\u0639\u06cc \u0627\u0632', '\u06af\u0631\u0648\u0647\u06cc \u0627\u0632',
      '\u062c\u0645\u0639\u06cc', '\u06af\u0631\u0648\u0647\u06cc',
      '\u0627\u0633\u0627\u062a\u06cc\u062f', '\u0646\u0634\u0633\u062a',
      '\u0647\u0645\u0627\u06cc\u0634', '\u06a9\u0627\u0631\u06af\u0631\u0648\u0647',
      '\u0646\u0627\u0634\u0646\u0627\u0633', '\u0646\u0627\u0645\u0634\u062e\u0635'
    ];
    if (collective.some(k => s.includes(k))) return s;

    const FIRST_NAMES = new Set([
      '\u0631\u0636\u0627', '\u0645\u062d\u0645\u062f', '\u0639\u0644\u06cc', '\u062d\u0633\u06cc\u0646',
      '\u062d\u0633\u0646', '\u0645\u0647\u062f\u06cc', '\u0627\u062d\u0645\u062f', '\u0645\u062d\u0645\u0648\u062f',
      '\u0645\u0635\u0637\u0641\u06cc', '\u0645\u0631\u062a\u0636\u06cc', '\u0645\u062c\u062a\u0628\u06cc',
      '\u062c\u0648\u0627\u062f', '\u06a9\u0627\u0638\u0645', '\u0635\u0627\u062f\u0642', '\u0628\u0627\u0642\u0631',
      '\u062a\u0642\u06cc', '\u0646\u0642\u06cc', '\u0627\u06a9\u0628\u0631', '\u0627\u0635\u063a\u0631',
      '\u0639\u0628\u0627\u0633', '\u0645\u0633\u0639\u0648\u062f', '\u0633\u0639\u06cc\u062f', '\u0645\u062c\u06cc\u062f',
      '\u062d\u0645\u06cc\u062f', '\u0648\u062d\u06cc\u062f', '\u062f\u0627\u0648\u062f', '\u062f\u0627\u0648\u0648\u062f',
      '\u0631\u0633\u0648\u0644', '\u0646\u0627\u0635\u0631', '\u0645\u0646\u0635\u0648\u0631', '\u0645\u062d\u0633\u0646',
      '\u062d\u0627\u0645\u062f', '\u0627\u0645\u06cc\u0631', '\u0627\u0628\u0631\u0627\u0647\u06cc\u0645',
      '\u0627\u0633\u0645\u0627\u0639\u06cc\u0644', '\u06cc\u0648\u0633\u0641', '\u062c\u0639\u0641\u0631',
      '\u0647\u0627\u062f\u06cc', '\u062d\u0628\u06cc\u0628', '\u06a9\u0631\u06cc\u0645', '\u0631\u062d\u06cc\u0645',
      '\u0642\u0627\u0633\u0645', '\u062c\u0644\u0627\u0644', '\u062c\u0645\u0627\u0644', '\u06a9\u0645\u0627\u0644',
      '\u0645\u0638\u0647\u0631', '\u0637\u0627\u0647\u0631', '\u0635\u0627\u0644\u062d', '\u0639\u0627\u062f\u0644',
      '\u0639\u0627\u0631\u0641', '\u0645\u06cc\u062b\u0645', '\u0633\u062c\u0627\u062f', '\u06cc\u0627\u0633\u0631',
      '\u0627\u0628\u0648\u0627\u0644\u0641\u0636\u0644', '\u063a\u0644\u0627\u0645\u0631\u0636\u0627',
      '\u063a\u0644\u0627\u0645\u062d\u0633\u06cc\u0646', '\u0639\u0628\u062f\u0627\u0644\u0644\u0647',
      '\u0639\u0628\u062f\u0627\u0644\u0631\u0636\u0627', '\u0639\u0628\u062f\u0627\u0644\u062d\u0633\u06cc\u0646',
      '\u0639\u0628\u062f\u0627\u0644\u06a9\u0631\u06cc\u0645', '\u0639\u0628\u062f\u0627\u0644\u0631\u062d\u06cc\u0645',
      '\u0639\u0628\u062f\u0627\u0644\u0645\u062c\u06cc\u062f', '\u062d\u0645\u06cc\u062f\u0631\u0636\u0627',
      '\u0639\u0644\u06cc\u0631\u0636\u0627', '\u0645\u062d\u0645\u062f\u0631\u0636\u0627',
      '\u0645\u062d\u0645\u062f\u062d\u0633\u06cc\u0646', '\u0645\u062d\u0645\u062f\u0645\u0647\u062f\u06cc',
      '\u0645\u062d\u0645\u062f\u062c\u0648\u0627\u062f', '\u0645\u062d\u0645\u062f\u0639\u0644\u06cc',
      '\u0645\u062d\u0645\u062f\u062a\u0642\u06cc', '\u0645\u062d\u0645\u062f\u0628\u0627\u0642\u0631',
      '\u0645\u062d\u0645\u062f\u0635\u0627\u062f\u0642', '\u0627\u0645\u06cc\u0631\u062d\u0633\u06cc\u0646',
      '\u0641\u0627\u0637\u0645\u0647', '\u0632\u0647\u0631\u0627', '\u0645\u0631\u06cc\u0645',
      '\u0632\u06cc\u0646\u0628', '\u0645\u0639\u0635\u0648\u0645\u0647'
    ]);

    const JUNK_ONLY = new Set([
      '\u0648\u0627\u0644\u0645\u0633\u0644\u0645\u06cc\u0646', '\u0627\u0644\u0645\u0633\u0644\u0645\u06cc\u0646',
      '\u0627\u0644\u0627\u0633\u0644\u0627\u0645', '\u062d\u062c\u062a', '\u062d\u062c\u062c',
      '\u062f\u06a9\u062a\u0631', '\u0627\u0633\u062a\u0627\u062f', '\u0648'
    ]);

    const honorificRx = /^(?:\u062d\u062c\u062a\s*\u0627\u0644\u0627\u0633\u0644\u0627\u0645(?:\s*\u0648\s*\u0627\u0644\u0645\u0633\u0644\u0645\u06cc\u0646)?|\u062d\u062c\u062c\s*\u0627\u0644\u0627\u0633\u0644\u0627\u0645(?:\s*\u0648\s*\u0627\u0644\u0645\u0633\u0644\u0645\u06cc\u0646)?|\u0648\s*\u0627\u0644\u0645\u0633\u0644\u0645\u06cc\u0646|\u0627\u0644\u0645\u0633\u0644\u0645\u06cc\u0646|\u0622\u06cc\u062a\s*\u0627\u0644\u0644\u0647(?:\s*\u0627\u0644\u0639\u0638\u0645\u06cc)?|\u062f\u06a9\u062a\u0631|\u0645\u0647\u0646\u062f\u0633|\u062c\u0646\u0627\u0628\s*\u0622\u0642\u0627\u06cc|\u0622\u0642\u0627\u06cc|\u0633\u0631\u06a9\u0627\u0631\s*\u062e\u0627\u0646\u0645|\u062e\u0627\u0646\u0645|\u0627\u0633\u062a\u0627\u062f|\u0634\u06cc\u062e|\u0633\u06cc\u062f\u0647|\u0633\u06cc\u062f|\u062d\u0627\u062c)(?:[\s:\-\u2013\u2014]+|$)/;

    const cleanPerson = (txt) => {
      let p = String(txt || '').replace(/^[\s:\-\u2013\u2014\u060c]+|[\s:\-\u2013\u2014\u060c]+$/g, '').trim();
      for (let i = 0; i < 6; i++) {
        const next = p.replace(honorificRx, '').trim();
        if (next === p) break;
        p = next;
      }
      let words = p.split(/\s+/).filter(w => w && !JUNK_ONLY.has(w));
      for (let step = 0; step < 3 && words.length >= 2; step++) {
        const w0 = words[0];
        if (FIRST_NAMES.has(w0)) { words.shift(); continue; }
        if ((w0.startsWith('\u0633\u06cc\u062f\u0647') || w0.startsWith('\u0633\u06cc\u062f')) && w0.length > 4) {
          const rest = w0.startsWith('\u0633\u06cc\u062f\u0647') ? w0.slice(4) : w0.slice(3);
          if (FIRST_NAMES.has(rest)) { words.shift(); continue; }
        }
        break;
      }
      let res = words.join(' ').trim();
      res = res.replace(/\u0647\u0627\u0634\u0645\u06cc \u06af\u0644\u067e\u0627\u06cc(?:\u06af\u0627)?$/, '\u0647\u0627\u0634\u0645\u06cc \u06af\u0644\u067e\u0627\u06cc\u06af\u0627\u0646\u06cc');
      return res;
    };

    // Only split before embedded clerical title (???/???/???) when NOT preceded by another title word
    const splitReady = s.replace(/\s+(?=(?:\u062d\u062c\u062a|\u062d\u062c\u062c|\u0622\u06cc\u062a)\s)/g, ' / ');
    const rawParts = splitReady.split(/\s*\/\s*|\s*\u060c\s*|\s+[\-\u2013\u2014]\s+|\s+\u0648\s+(?=(?:\u062f\u06a9\u062a\u0631|\u0627\u0633\u062a\u0627\u062f|\u062d\u062c\u062a|\u0622\u06cc\u062a)\s)/);
    const cleaned = [];
    rawParts.forEach(part => {
      const cp = cleanPerson(part);
      if (cp && !JUNK_ONLY.has(cp) && !cleaned.includes(cp)) cleaned.push(cp);
    });
    if (!cleaned.length) return raw.trim();
    if (cleaned.length > 1) {
      const shown = cleaned.slice(0, 2).map(p => '\u0627\u0633\u062a\u0627\u062f ' + p);
      return cleaned.length > 2 ? shown.join('\u060c ') + ' \u0648...' : shown.join(' \u0648 ');
    }
    return '\u0627\u0633\u062a\u0627\u062f ' + cleaned[0];
  }
  window.formatTeacherShort = formatTeacherShort;

  function trimLabel(s, max = 24) {
    const clean = String(s || '').replace(/\s+/g, ' ').trim();
    return clean.length > max ? clean.slice(0, max - 1) + '\u2026' : clean;
  }

  function themeColors() {
    const light = document.body.getAttribute('data-studio-theme') === 'light';
    const navy = document.body.getAttribute('data-accent-scheme') === 'navy';
    return {
      text: light ? '#0f172a' : '#f8fafc',
      muted: light ? '#334155' : '#94a3b8',
      grid: light ? 'rgba(15, 23, 42, 0.10)' : 'rgba(148, 163, 184, 0.16)',
      track: light ? (navy ? 'rgba(29, 78, 216, 0.09)' : 'rgba(5, 150, 105, 0.09)') : 'rgba(148, 163, 184, 0.12)',
      bg: light ? '#f8fafc' : '#0d1520',
      primary: navy ? (light ? '#1d4ed8' : '#38bdf8') : (light ? '#059669' : '#10b981'),
      secondary: navy ? (light ? '#0284c7' : '#818cf8') : (light ? '#0d9488' : '#2dd4bf'),
    };
  }

  function smoothPath(pts) {
    if (!pts.length) return '';
    if (pts.length === 1) return `M ${pts[0][0]},${pts[0][1]}`;
    let d = `M ${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
      const cp1x = p1[0] + (p2[0] - p0[0]) / 6;
      const cp1y = p1[1] + (p2[1] - p0[1]) / 6;
      const cp2x = p2[0] - (p3[0] - p1[0]) / 6;
      const cp2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
    }
    return d;
  }

  function renderHBar(container, items, opts = {}) {
    if (!container) return;
    const tc = themeColors();
    const list = (items || []).slice(0, 8);
    if (!list.length) {
      container.innerHTML = '<div class="eh-empty-chart">\u062f\u0627\u062f\u0647\u200c\u0627\u06cc \u0628\u0631\u0627\u06cc \u0646\u0645\u0627\u06cc\u0634 \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a.</div>';
      return;
    }
    const W = 540, rowH = 48, H = Math.max(195, list.length * rowH + 20);
    const labelStartX = W - 10;
    const barRightX = W - 185;
    const barLeftEdge = 112;
    const barAreaW = barRightX - barLeftEdge;
    const maxV = Math.max(1, ...list.map(i => Math.max(Number(i.v1 || 0), Number(i.v2 || 0))));

    let rows = '';
    list.forEach((it, idx) => {
      const y = 12 + idx * rowH;
      const v1 = Number(it.v1 || 0);
      const hasV2 = it.v2 !== undefined && it.v2 !== null;
      const v2 = hasV2 ? Number(it.v2 || 0) : 0;
      const w1 = Math.max(6, (v1 / maxV) * barAreaW);
      const w2 = hasV2 ? Math.max(5, (v2 / maxV) * barAreaW) : 0;
      const rawLbl = opts.isTeacher ? formatTeacherShort(it.label) : it.label;
      const lbl = escXml(toFa(trimLabel(rawLbl, 23)));
      const fullTip = escXml(it.label);
      const teacherAttr = opts.isTeacher ? ` class="eh-svg-teacher-lbl" data-teacher-raw="${fullTip}" style="cursor:pointer;"` : '';

      rows += `<text x="${labelStartX}" y="${y + 21}" direction="rtl" unicode-bidi="plaintext" text-anchor="start" font-size="13.5" font-weight="700" fill="${tc.text}"${teacherAttr}><title>${fullTip}</title>${lbl}</text>`;
      rows += `<rect x="${barLeftEdge}" y="${y + 5}" width="${barAreaW}" height="24" rx="7" fill="${tc.track}"/>`;
      if (hasV2) {
        rows += `<rect class="eh-svg-bar" x="${barRightX - w1}" y="${y + 5}" width="${w1}" height="11" rx="5" fill="${opts.c1 || tc.primary}"><title>${fullTip} (\u06a9\u0644): ${fmtNum(v1)}</title></rect>`;
        rows += `<rect class="eh-svg-bar" x="${barRightX - w2}" y="${y + 18}" width="${w2}" height="9" rx="4.5" fill="${opts.c2 || tc.secondary}"><title>${fullTip} (\u06cc\u06a9\u062a\u0627): ${fmtNum(v2)}</title></rect>`;
      } else {
        rows += `<rect class="eh-svg-bar" x="${barRightX - w1}" y="${y + 5}" width="${w1}" height="24" rx="7" fill="${opts.c1 || tc.primary}"><title>${fullTip}: ${fmtNum(v1)}</title></rect>`;
      }
      const valTxt = hasV2 ? `${fmtNum(v1)} / ${fmtNum(v2)}` : fmtNum(v1);
      rows += `<text x="14" y="${y + 21}" direction="rtl" unicode-bidi="plaintext" text-anchor="start" font-size="12" font-weight="700" fill="${tc.muted}">${toFa(valTxt)}</text>`;
    });

    container.innerHTML = `<svg class="eh-chart-svg" dir="ltr" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${rows}</svg>`;
    if (opts.isTeacher) {
      container.querySelectorAll('.eh-svg-teacher-lbl').forEach(el => {
        el.addEventListener('click', () => window.openTeacher360Drawer?.(el.getAttribute('data-teacher-raw')));
      });
    }
  }

  function renderSplineArea(container, series, labels, opts = {}) {
    if (!container) return;
    const tc = themeColors();
    if (!labels || !labels.length) {
      container.innerHTML = '<div class="eh-empty-chart">\u062f\u0627\u062f\u0647\u200c\u0627\u06cc \u0628\u0631\u0627\u06cc \u0646\u0645\u0627\u06cc\u0634 \u0631\u0648\u0646\u062f \u0632\u0645\u0627\u0646\u06cc \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f.</div>';
      return;
    }
    const W = 540, H = 235, padL = 46, padR = 20, padT = 32, padB = 36;
    const cw = W - padL - padR, ch = H - padT - padB;
    const maxV = Math.max(1, ...series.flatMap(s => s.values)) * 1.15;

    let grid = '';
    for (let i = 0; i <= 4; i++) {
      const y = padT + (ch * i) / 4;
      const val = Math.round(maxV * (1 - i / 4));
      grid += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${tc.grid}" stroke-dasharray="3 3"/>`;
      grid += `<text x="${padL - 8}" y="${y + 4}" text-anchor="end" font-size="11.5" fill="${tc.muted}">${fmtNum(val)}</text>`;
    }

    let defs = '<defs>', paths = '', dots = '';
    series.forEach((s, si) => {
      const col = s.color || (si === 0 ? tc.primary : tc.secondary);
      const gid = `g_${opts.id || 's'}_${si}_${Math.random().toString(36).slice(2, 6)}`;
      defs += `<linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${col}" stop-opacity="0.34"/><stop offset="100%" stop-color="${col}" stop-opacity="0.01"/></linearGradient>`;
      const pts = s.values.map((v, idx) => {
        const x = labels.length === 1 ? padL + cw / 2 : padL + (cw * idx) / (labels.length - 1);
        const y = padT + ch - (v / maxV) * ch;
        return [x, y, v];
      });
      const lineD = smoothPath(pts);
      const areaD = pts.length > 1 ? `${lineD} L ${pts[pts.length - 1][0]},${padT + ch} L ${pts[0][0]},${padT + ch} Z` : '';
      if (areaD) paths += `<path d="${areaD}" fill="url(#${gid})"/>`;
      paths += `<path class="eh-svg-spline" d="${lineD}" fill="none" stroke="${col}" stroke-width="2.8" stroke-linecap="round"/>`;
      pts.forEach(([x, y, v], idx) => {
        dots += `<circle cx="${x}" cy="${y}" r="4.5" fill="${tc.bg}" stroke="${col}" stroke-width="2.4"><title>${escXml(labels[idx])} - ${escXml(s.name)}: ${fmtNum(v)}</title></circle>`;
      });
    });
    defs += '</defs>';

    const xLabels = labels.map((lb, idx) => {
      const x = labels.length === 1 ? padL + cw / 2 : padL + (cw * idx) / (labels.length - 1);
      return `<text x="${x}" y="${H - 10}" text-anchor="middle" font-size="12" fill="${tc.muted}">${escXml(toFa(lb))}</text>`;
    }).join('');

    const legend = series.map((s, si) => {
      const col = s.color || (si === 0 ? tc.primary : tc.secondary);
      const lx = W - padR - si * 155;
      return `<g transform="translate(${lx}, 15)"><rect x="-11" y="-9" width="11" height="11" rx="3" fill="${col}"/><text x="-17" y="1" direction="rtl" text-anchor="start" font-size="12" font-weight="700" fill="${tc.text}">${escXml(s.name)}</text></g>`;
    }).join('');

    container.innerHTML = `<svg class="eh-chart-svg" dir="ltr" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${defs}${grid}${paths}${dots}${xLabels}${legend}</svg>`;
  }

  function renderDonut(container, items, centerLabel = '\u0645\u062c\u0645\u0648\u0639') {
    if (!container) return;
    const tc = themeColors();
    const W = 460, H = 230, cx = 108, cy = 115, r = 74, sw = 24;
    const total = (items || []).reduce((a, b) => a + Number(b.value || 0), 0);
    const circ = 2 * Math.PI * r;
    let offset = 0, segs = '', legend = '';

    (items || []).forEach((it, idx) => {
      const val = Number(it.value || 0);
      const frac = total > 0 ? val / total : 0;
      const len = frac * circ;
      const col = it.color || PALETTE[idx % PALETTE.length];
      if (len > 0) {
        segs += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${col}" stroke-width="${sw}" stroke-dasharray="${len.toFixed(2)} ${(circ - len).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}" transform="rotate(-90 ${cx} ${cy})"><title>${escXml(it.label)}: ${fmtNum(val)} (${toFa(Math.round(frac * 100))}\u066a)</title></circle>`;
      }
      offset += len;
      const ly = 50 + idx * 38;
      legend += `<g transform="translate(215, ${ly})">
        <rect x="225" y="-10" width="12" height="12" rx="3.5" fill="${col}"/>
        <text x="217" y="0" direction="rtl" text-anchor="start" font-size="12.5" font-weight="700" fill="${tc.text}">${escXml(toFa(it.label))}</text>
        <text x="0" y="0" direction="ltr" text-anchor="start" font-size="12" fill="${tc.muted}">${fmtNum(val)} (${toFa(Math.round(frac * 100))}\u066a)</text>
      </g>`;
    });

    if (total === 0) segs = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${tc.grid}" stroke-width="${sw}"/>`;

    container.innerHTML = `<svg class="eh-chart-svg" dir="ltr" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
      ${segs}
      <text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="21" font-weight="800" fill="${tc.text}">${fmtNum(total)}</text>
      <text x="${cx}" y="${cy + 18}" text-anchor="middle" font-size="11.5" fill="${tc.muted}">${escXml(centerLabel)}</text>
      ${legend}
    </svg>`;
  }

  function renderRadar(container, items) {
    if (!container) return;
    const tc = themeColors();
    const list = (items || []).slice(0, 6);
    if (list.length < 3) {
      container.innerHTML = '<div class="eh-empty-chart">\u0628\u0631\u0627\u06cc \u0646\u0645\u0648\u062f\u0627\u0631 \u0631\u0627\u062f\u0627\u0631\u06cc \u062d\u062f\u0627\u0642\u0644 \u06f3 \u06a9\u0627\u0631\u06af\u0631\u0648\u0647 \u0646\u06cc\u0627\u0632 \u0627\u0633\u062a.</div>';
      return;
    }
    const W = 460, H = 245, cx = 230, cy = 124, R = 76;
    const maxV = Math.max(1, ...list.map(x => Number(x.value || 0)));
    const step = (2 * Math.PI) / list.length;

    let rings = '', axes = '', pts = [];
    for (let r = 1; r <= 4; r++) {
      const rr = (R * r) / 4;
      const rpts = list.map((_, i) => `${(cx + rr * Math.cos(i * step - Math.PI / 2)).toFixed(1)},${(cy + rr * Math.sin(i * step - Math.PI / 2)).toFixed(1)}`).join(' ');
      rings += `<polygon points="${rpts}" fill="none" stroke="${tc.grid}" stroke-width="1"/>`;
    }
    list.forEach((it, i) => {
      const ang = i * step - Math.PI / 2;
      const ax = cx + R * Math.cos(ang), ay = cy + R * Math.sin(ang);
      axes += `<line x1="${cx}" y1="${cy}" x2="${ax}" y2="${ay}" stroke="${tc.grid}"/>`;
      const lx = cx + (R + 30) * Math.cos(ang), ly = cy + (R + 22) * Math.sin(ang);
      axes += `<text x="${lx}" y="${ly}" text-anchor="middle" font-size="12" font-weight="700" fill="${tc.text}">${escXml(toFa(trimLabel(it.label, 16)))}</text>`;
      const vr = (Number(it.value || 0) / maxV) * R;
      pts.push([cx + vr * Math.cos(ang), cy + vr * Math.sin(ang)]);
    });
    const poly = pts.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
    const dots = pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="4.5" fill="${tc.primary}"><title>${escXml(list[i].label)}: ${fmtNum(list[i].value)}</title></circle>`).join('');

    container.innerHTML = `<svg class="eh-chart-svg" dir="ltr" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
      ${rings}${axes}<polygon points="${poly}" fill="${tc.primary}" fill-opacity="0.22" stroke="${tc.primary}" stroke-width="2.4"/>${dots}
    </svg>`;
  }

  function renderHeatmap(container, months) {
    if (!container) return;
    const tc = themeColors();
    const W = 580, H = 135;
    const maxC = Math.max(1, ...(months || []).map(m => Number(m.courses || 0)));
    const cw = 42, ch = 56, gap = 5, startX = 12;
    const isNavy = document.body.getAttribute('data-accent-scheme') === 'navy';

    const cells = (months || []).map((m, idx) => {
      const x = startX + idx * (cw + gap);
      const ratio = Number(m.courses || 0) / maxC;
      const rgb = isNavy ? '56, 189, 248' : '16, 185, 129';
      const fill = ratio === 0 ? tc.track : `rgba(${rgb}, ${(0.24 + ratio * 0.76).toFixed(2)})`;
      const txtCol = ratio > 0.45 ? '#ffffff' : tc.text;
      return `<g>
        <rect x="${x}" y="18" width="${cw}" height="${ch}" rx="8" fill="${fill}"><title>${escXml(m.month)}: ${fmtNum(m.courses)} \u062f\u0648\u0631\u0647 (${fmtNum(m.attendance)} \u0645\u062e\u0627\u0637\u0628)</title></rect>
        <text x="${x + cw / 2}" y="52" text-anchor="middle" font-size="14" font-weight="800" fill="${txtCol}">${fmtNum(m.courses)}</text>
        <text x="${x + cw / 2}" y="96" text-anchor="middle" font-size="10.5" fill="${tc.muted}">${escXml(m.month.slice(0, 6))}</text>
      </g>`;
    }).join('');

    container.innerHTML = `<svg class="eh-chart-svg" dir="ltr" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${cells}</svg>`;
  }

  function svgToPngDataUri(svgEl, scale = 2.5, whiteBg = false) {
    return new Promise((resolve) => {
      if (!svgEl) return resolve('');
      const clone = svgEl.cloneNode(true);
      const vb = (clone.getAttribute('viewBox') || '0 0 500 230').split(/\s+/).map(Number);
      const w = vb[2] || 500, h = vb[3] || 230;
      clone.setAttribute('width', String(w));
      clone.setAttribute('height', String(h));
      clone.style.fontFamily = 'Vazirmatn, Tahoma, sans-serif';
      const xml = new XMLSerializer().serializeToString(clone);
      const blob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = w * scale; canvas.height = h * scale;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = whiteBg ? '#ffffff' : themeColors().bg;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        resolve(canvas.toDataURL('image/png'));
      };
      img.onerror = () => { URL.revokeObjectURL(url); resolve(''); };
      img.src = url;
    });
  }

  async function copyChartToClipboard(container) {
    const svg = container?.querySelector('svg');
    if (!svg) return;
    const uri = await svgToPngDataUri(svg, 2.5, false);
    if (!uri) return;
    try {
      const res = await fetch(uri);
      const blob = await res.blob();
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
      window.showToast?.('\u062a\u0635\u0648\u06cc\u0631 \u0646\u0645\u0648\u062f\u0627\u0631 \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 \u06a9\u067e\u06cc \u0634\u062f\u061b \u0622\u0645\u0627\u062f\u0647 \u0627\u0631\u0633\u0627\u0644 \u062f\u0631 \u0627\u06cc\u062a\u0627 \u06cc\u0627 \u067e\u0627\u0648\u0631\u067e\u0648\u06cc\u0646\u062a.');
    } catch (_) {
      window.showToast?.('\u06a9\u067e\u06cc \u062a\u0635\u0648\u06cc\u0631 \u062f\u0631 \u0627\u06cc\u0646 \u0628\u062e\u0634 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc \u0646\u0634\u062f\u061b \u0627\u0632 \u062f\u06a9\u0645\u0647 \u062f\u0627\u0646\u0644\u0648\u062f PNG \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646\u06cc\u062f.');
    }
  }

  async function downloadChart(container, fileBase, kind = 'png') {
    const svg = container?.querySelector('svg');
    if (!svg) return;
    if (kind === 'svg') {
      const xml = new XMLSerializer().serializeToString(svg);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }));
      a.download = `${fileBase}.svg`;
      a.click();
      return;
    }
    const uri = await svgToPngDataUri(svg, 2.5, false);
    if (!uri) return;
    const a = document.createElement('a');
    a.href = uri;
    a.download = `${fileBase}.png`;
    a.click();
  }

  return { toFa, fmtNum, formatTeacherShort, renderSplineArea, renderDonut, renderHBar, renderRadar, renderHeatmap, svgToPngDataUri, copyChartToClipboard, downloadChart };
})();
