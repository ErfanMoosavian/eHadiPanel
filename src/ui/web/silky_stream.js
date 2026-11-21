(() => {
  const chatStreamEl = document.getElementById('chatStream');
  if (!chatStreamEl) return;

  const activeStreams = {};
  let localReg = 0;
  let localSeq = 0;
  let userPinnedToBottom = true;

  // Persistent v48 chat controls state
  window.currentChatRoute = localStorage.getItem('ehadi_chat_route') || 'auto';
  window.currentChatLength = localStorage.getItem('ehadi_chat_length') || 'concise';
  window.chatCiteVisibility = localStorage.getItem('ehadi_chat_cites') || 'collapsed';

  window.setChatRoute = function (route, btn) {
    if (!['auto', 'institutional', 'free'].includes(route)) route = 'auto';
    window.currentChatRoute = route;
    localStorage.setItem('ehadi_chat_route', route);
    document.querySelectorAll('.eh-v48-route-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.route === route);
    });
    const inp = document.getElementById('chatInput');
    if (inp) {
      if (route === 'institutional') inp.placeholder = 'پرسش از اسناد و آمار مؤسسه را بنویسید (فقط از داده‌های واقعی)...';
      else if (route === 'free') inp.placeholder = 'هر سؤال عمومی، نگارش نامه یا ایده‌پردازی را بنویسید (آزاد)...';
      else inp.placeholder = 'سؤال آماری از مؤسسه یا هر درخواست عمومی را بنویسید و Enter بزنید...';
    }
  };

  window.setChatLength = function (lenMode, btn) {
    if (!['concise', 'balanced', 'analytical'].includes(lenMode)) lenMode = 'concise';
    window.currentChatLength = lenMode;
    localStorage.setItem('ehadi_chat_length', lenMode);
    document.querySelectorAll('.eh-v48-len-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.len === lenMode);
    });
  };

  window.toggleCiteVisibilityPref = function (btn) {
    const next = (window.chatCiteVisibility === 'hidden') ? 'collapsed' : 'hidden';
    window.chatCiteVisibility = next;
    localStorage.setItem('ehadi_chat_cites', next);
    if (btn) btn.textContent = next === 'hidden' ? 'منابع: مخفی' : 'منابع: کشویی';
    document.body.classList.toggle('eh-v48-hide-cites', next === 'hidden');
  };

  window.toggleMsgCitations = function (drawerId, btn) {
    const el = document.getElementById(drawerId);
    if (!el) return;
    const isOpen = el.classList.toggle('open');
    if (btn) {
      btn.classList.toggle('open', isOpen);
      const cnt = btn.dataset.cnt || '';
      btn.innerHTML = isOpen
        ? `منابع (${cnt}) <span class="eh-v48-chev">▴</span>`
        : `منابع (${cnt}) <span class="eh-v48-chev">▾</span>`;
    }
  };

  // Apply persisted preferences on load
  document.addEventListener('DOMContentLoaded', () => {
    window.setChatRoute(window.currentChatRoute);
    window.setChatLength(window.currentChatLength);
    document.body.classList.toggle('eh-v48-hide-cites', window.chatCiteVisibility === 'hidden');
    const cBtn = document.getElementById('ehV48CitePrefBtn');
    if (cBtn) cBtn.textContent = window.chatCiteVisibility === 'hidden' ? 'منابع: مخفی' : 'منابع: کشویی';
  });

  chatStreamEl.addEventListener('scroll', () => {
    const dist = chatStreamEl.scrollHeight - chatStreamEl.scrollTop - chatStreamEl.clientHeight;
    userPinnedToBottom = dist < 85;
  });

  function smoothScrollStep() {
    if (!userPinnedToBottom) return;
    const target = chatStreamEl.scrollHeight - chatStreamEl.clientHeight;
    const diff = target - chatStreamEl.scrollTop;
    if (diff > 0.8) chatStreamEl.scrollTop += Math.max(1.2, diff * 0.18);
    else if (diff > 0) chatStreamEl.scrollTop = target;
  }

  function autoCloseInlineMarkers(text) {
    let s = String(text || '');
    if (/(?<!\*)\*$/.test(s)) s = s.slice(0, -1);
    const boldMatches = s.match(/\*\*/g);
    if (boldMatches && boldMatches.length % 2 === 1) s += '**';
    const codeMatches = s.match(/`/g);
    if (codeMatches && codeMatches.length % 2 === 1) s += '`';
    return s;
  }

  function tokenizeInline(rawText, isStreaming) {
    const cleaned = isStreaming ? autoCloseInlineMarkers(rawText) : String(rawText || '');
    const tokens = [];
    const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
    let lastIdx = 0;
    let match;

    const pushWords = (str, kind) => {
      if (!str) return;
      if (kind === 'code') {
        tokens.push({ kind: 'code', text: str });
        return;
      }
      const parts = str.match(/\S+\s*|\s+/g) || [str];
      for (const p of parts) tokens.push({ kind, text: p });
    };

    while ((match = regex.exec(cleaned)) !== null) {
      if (match.index > lastIdx) pushWords(cleaned.slice(lastIdx, match.index), 'plain');
      const seg = match[0];
      if (seg.startsWith('`')) pushWords(seg.slice(1, -1), 'code');
      else if (seg.startsWith('**')) pushWords(seg.slice(2, -2), 'bold');
      else if (seg.startsWith('*')) pushWords(seg.slice(1, -1), 'italic');
      lastIdx = regex.lastIndex;
    }
    if (lastIdx < cleaned.length) pushWords(cleaned.slice(lastIdx), 'plain');
    return tokens;
  }

  function createInlineNode(tok, animate) {
    let tag = 'span';
    if (tok.kind === 'bold') tag = 'strong';
    else if (tok.kind === 'italic') tag = 'em';
    else if (tok.kind === 'code') tag = 'code';

    const el = document.createElement(tag);
    el.className = animate ? 'sw sw-in' : 'sw';
    el.textContent = tok.text;
    el._tkKind = tok.kind;
    el._tkText = tok.text;
    el._tkKey = tok.kind + '|' + tok.text;
    return el;
  }

  function patchInlineWords(container, rawText, animateNew) {
    const tokens = tokenizeInline(rawText, animateNew);
    const existing = [];
    for (const ch of Array.from(container.childNodes)) {
      if (ch.nodeType === 1 && ch.classList.contains('stream-cursor')) continue;
      existing.push(ch);
    }

    const oldLen = existing.length;
    for (let i = 0; i < tokens.length; i++) {
      const tok = tokens[i];
      const key = tok.kind + '|' + tok.text;
      if (i < oldLen) {
        const cur = existing[i];
        if (cur._tkKey === key) continue;
        if (cur._tkKind === tok.kind && tok.text.startsWith(cur._tkText || '')) {
          cur.textContent = tok.text;
          cur._tkText = tok.text;
          cur._tkKey = key;
        } else {
          const replacement = createInlineNode(tok, false);
          container.replaceChild(replacement, cur);
          existing[i] = replacement;
        }
      } else {
        container.appendChild(createInlineNode(tok, animateNew));
      }
    }

    for (let i = oldLen - 1; i >= tokens.length; i--) {
      if (existing[i] && existing[i].parentNode === container) {
        container.removeChild(existing[i]);
      }
    }
  }

  function parseMarkdownBlocks(mdText, isStreaming) {
    const lines = String(mdText || '').replace(/\r\n/g, '\n').split('\n');
    const blocks = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i].trim();
      if (line === '') { i++; continue; }

      if (line.startsWith('```')) {
        const codeLines = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith('```')) {
          codeLines.push(lines[i]);
          i++;
        }
        if (i < lines.length) i++;
        const codeStr = codeLines.join('\n');
        blocks.push({ type: 'codeblock', raw: '```' + codeStr, text: codeStr });
        continue;
      }

      if (line.startsWith('|')) {
        const nextLine = (i + 1 < lines.length) ? lines[i + 1].trim() : '';
        if (/^\|?[\s:-]+\|[\s|:-]*$/.test(nextLine)) {
          const splitRow = r => r.replace(/^\||\|$/g, '').split('|').map(c => c.trim());
          const headers = splitRow(line);
          const rawParts = [line, nextLine];
          i += 2;
          const rows = [];
          while (i < lines.length && lines[i].trim().startsWith('|')) {
            const rLine = lines[i].trim();
            if (isStreaming && i === lines.length - 1 && !rLine.endsWith('|')) {
              i++;
              break;
            }
            const cells = splitRow(rLine);
            if (cells.length > 0) {
              rows.push({ raw: rLine, cells });
              rawParts.push(rLine);
            }
            i++;
          }
          blocks.push({ type: 'table', raw: rawParts.join('\n'), headers, rows });
          continue;
        }
        if (isStreaming && i >= lines.length - 2) { i++; continue; }
      }

      if (/^\|?[\s:-]+\|[\s|:-]*$/.test(line) && line.includes('|')) { i++; continue; }
      if (/^-{3,}$/.test(line)) { blocks.push({ type: 'hr', raw: '---' }); i++; continue; }
      if (line.startsWith('### ')) { blocks.push({ type: 'h4', raw: line, text: line.slice(4) }); i++; continue; }
      if (line.startsWith('## ')) { blocks.push({ type: 'h3', raw: line, text: line.slice(3) }); i++; continue; }
      if (line.startsWith('# ')) { blocks.push({ type: 'h3', raw: line, text: line.slice(2) }); i++; continue; }

      if (/^[-*•]\s+/.test(line)) {
        const items = [];
        const rawParts = [];
        while (i < lines.length && /^[-*•]\s+/.test(lines[i].trim())) {
          const t = lines[i].trim();
          rawParts.push(t);
          items.push(t.replace(/^[-*•]\s+/, ''));
          i++;
        }
        blocks.push({ type: 'ul', raw: rawParts.join('\n'), items });
        continue;
      }

      if (/^\d+[.)]\s+/.test(line)) {
        const items = [];
        const rawParts = [];
        while (i < lines.length && /^\d+[.)]\s+/.test(lines[i].trim())) {
          const t = lines[i].trim();
          rawParts.push(t);
          items.push(t.replace(/^\d+[.)]\s+/, ''));
          i++;
        }
        blocks.push({ type: 'ol', raw: rawParts.join('\n'), items });
        continue;
      }

      blocks.push({ type: 'p', raw: line, text: line });
      i++;
    }
    return blocks;
  }

  function renderIncrementalMarkdown(st, isFinal) {
    const animate = !isFinal;
    const blocks = parseMarkdownBlocks(st.displayedText, animate);
    const root = st.bodyEl;
    const cache = st.blockCache;

    if (st.cursorEl && st.cursorEl.parentNode) st.cursorEl.parentNode.removeChild(st.cursorEl);

    while (cache.length > blocks.length) {
      const popped = cache.pop();
      if (popped && popped.el && popped.el.parentNode === root) root.removeChild(popped.el);
    }

    let lastInlineTarget = null;

    for (let i = 0; i < blocks.length; i++) {
      const blk = blocks[i];
      const prev = cache[i];

      if (prev && prev.type === blk.type && prev.raw === blk.raw) {
        if (prev.lastTarget) lastInlineTarget = prev.lastTarget;
        continue;
      }

      if (prev && prev.type === blk.type) {
        if (blk.type === 'p' || blk.type === 'h3' || blk.type === 'h4') {
          patchInlineWords(prev.el, blk.text, animate);
          prev.raw = blk.raw;
          prev.lastTarget = prev.el;
          lastInlineTarget = prev.el;
          continue;
        }
        if (blk.type === 'ul' || blk.type === 'ol') {
          const ul = prev.el;
          const prevItems = prev.items || [];
          for (let j = 0; j < blk.items.length; j++) {
            if (j < ul.children.length) {
              if (prevItems[j] !== blk.items[j]) patchInlineWords(ul.children[j], blk.items[j], animate);
            } else {
              const li = document.createElement('li');
              if (animate) li.className = 'block-in';
              patchInlineWords(li, blk.items[j], animate);
              ul.appendChild(li);
            }
          }
          while (ul.children.length > blk.items.length) ul.removeChild(ul.lastElementChild);
          prev.raw = blk.raw;
          prev.items = blk.items.slice();
          prev.lastTarget = ul.lastElementChild || ul;
          lastInlineTarget = prev.lastTarget;
          continue;
        }
        if (blk.type === 'table') {
          const tbody = prev.tbody;
          const prevRows = prev.rows || [];
          for (let r = 0; r < blk.rows.length; r++) {
            if (r < tbody.children.length) {
              if (prevRows[r] !== blk.rows[r].raw) {
                tbody.children[r].innerHTML = blk.rows[r].cells.map(c => `<td>${inlineFormat(escapeHtml(c))}</td>`).join('');
              }
            } else {
              const tr = document.createElement('tr');
              if (animate) tr.className = 'row-in';
              tr.innerHTML = blk.rows[r].cells.map(c => `<td>${inlineFormat(escapeHtml(c))}</td>`).join('');
              tbody.appendChild(tr);
            }
          }
          while (tbody.children.length > blk.rows.length) tbody.removeChild(tbody.lastElementChild);
          prev.raw = blk.raw;
          prev.rows = blk.rows.map(x => x.raw);
          prev.lastTarget = null;
          lastInlineTarget = null;
          continue;
        }
        if (blk.type === 'codeblock') {
          prev.el.textContent = blk.text;
          prev.raw = blk.raw;
          lastInlineTarget = null;
          continue;
        }
      }

      let el;
      const entry = { type: blk.type, raw: blk.raw, el: null, lastTarget: null };

      if (blk.type === 'hr') {
        el = document.createElement('hr');
        el.className = animate ? 'md-hr block-in' : 'md-hr';
      } else if (blk.type === 'h3' || blk.type === 'h4') {
        el = document.createElement(blk.type);
        if (animate) el.className = 'block-in';
        patchInlineWords(el, blk.text, animate);
        entry.lastTarget = el;
      } else if (blk.type === 'p') {
        el = document.createElement('p');
        el.style.margin = '4px 0';
        if (animate) el.className = 'block-in';
        patchInlineWords(el, blk.text, animate);
        entry.lastTarget = el;
      } else if (blk.type === 'ul' || blk.type === 'ol') {
        el = document.createElement(blk.type);
        blk.items.forEach(itemTxt => {
          const li = document.createElement('li');
          if (animate) li.className = 'block-in';
          patchInlineWords(li, itemTxt, animate);
          el.appendChild(li);
        });
        entry.items = blk.items.slice();
        entry.lastTarget = el.lastElementChild || el;
      } else if (blk.type === 'table') {
        el = document.createElement('div');
        el.className = animate ? 'ai-table-card block-in' : 'ai-table-card';
        const scroll = document.createElement('div');
        scroll.className = 'ai-table-scroll';
        const table = document.createElement('table');
        table.className = 'glass-table';
        const thead = document.createElement('thead');
        thead.innerHTML = `<tr>${blk.headers.map(h => `<th>${inlineFormat(escapeHtml(h))}</th>`).join('')}</tr>`;
        const tbody = document.createElement('tbody');
        blk.rows.forEach(rowObj => {
          const tr = document.createElement('tr');
          if (animate) tr.className = 'row-in';
          tr.innerHTML = rowObj.cells.map(c => `<td>${inlineFormat(escapeHtml(c))}</td>`).join('');
          tbody.appendChild(tr);
        });
        table.appendChild(thead);
        table.appendChild(tbody);
        scroll.appendChild(table);
        el.appendChild(scroll);
        entry.tbody = tbody;
        entry.rows = blk.rows.map(x => x.raw);
      } else if (blk.type === 'codeblock') {
        el = document.createElement('pre');
        el.className = animate ? 'md-codeblock block-in' : 'md-codeblock';
        el.textContent = blk.text;
      }

      entry.el = el;
      if (prev && prev.el && prev.el.parentNode === root) root.replaceChild(el, prev.el);
      else root.appendChild(el);
      cache[i] = entry;
      lastInlineTarget = entry.lastTarget;
    }

    if (!isFinal && st.cursorEl && lastInlineTarget) {
      lastInlineTarget.appendChild(st.cursorEl);
    }
  }

  function buildScopePill(scope) {
    if (scope === 'free') {
      return '<span class="eh-v48-scope-pill scope-free">پاسخ عمومی</span>';
    }
    return '<span class="eh-v48-scope-pill scope-inst">اسناد مؤسسه</span>';
  }

  function buildKpisHtml(msg) {
    const kpis = msg.kpis || [];
    if (!kpis.length) return '';
    return `<div class="eh-v48-kpi-strip">${kpis.map(k => `
      <div class="eh-v48-kpi-chip">
        <span class="eh-v48-kpi-l">${escapeHtml(k.label)}</span>
        <span class="eh-v48-kpi-v">${escapeHtml(k.value)}</span>
      </div>
    `).join('')}</div>`;
  }

  function buildFooterAndExtrasHtml(msg, copyId) {
    let tablesHtml = '';
    const hasMdTable = /\n\|[^\n]+\|\n\|[\s:-]+\|/.test('\n' + (msg.content || ''));
    if (msg.tables && msg.tables.length > 0) {
      tablesHtml = msg.tables.map(tbl => {
        const tid = `stbl_${++localReg}`;
        tableRegistry[tid] = tbl;
        const cols = tbl.columns || [];
        const rows = (tbl.rows || []).slice(0, 60);
        const ths = cols.map(c => `<th>${escapeHtml(c)}</th>`).join('');
        const trs = rows.map(r => `<tr>${r.map(v => `<td>${escapeHtml(v)}</td>`).join('')}</tr>`).join('');
        const rowLabel = tbl.total_rows ? `${tbl.total_rows} ردیف` : `${rows.length} ردیف`;
        const collapsedClass = hasMdTable ? 'collapsed' : '';
        const toggleText = hasMdTable ? 'نمایش جدول کامل' : 'بستن جدول';
        return `
          <div class="ai-table-card ${collapsedClass}" id="card_${tid}">
            <div class="ai-table-head">
              <span class="ai-table-title">📊 ${escapeHtml(tbl.title || 'جدول آماری')} (${rowLabel})</span>
              <div style="display:flex; align-items:center; gap:8px;">
                <button class="toggle-table-btn" onclick="toggleSqlCard('card_${tid}', this)">${toggleText}</button>
                <button class="excel-btn" onclick="exportTable('${tid}')">خروجی اکسل (.xlsx)</button>
              </div>
            </div>
            <div class="ai-table-scroll">
              <table class="glass-table">
                <thead><tr>${ths}</tr></thead>
                <tbody>${trs}</tbody>
              </table>
            </div>
          </div>
        `;
      }).join('');
    }

    const isFree = (msg.response_scope === 'free');
    const cites = isFree ? [] : (msg.citations || []);
    const transText = (!isFree && msg.transparency) ? String(msg.transparency) : '';

    let citeBtnHtml = '';
    let citeDrawerHtml = '';
    if (cites.length > 0 || transText) {
      const drawerId = `scitedrw_${++localReg}`;
      const cntFa = String(cites.length || 1).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
      citeBtnHtml = `<button type="button" class="eh-v48-cite-toggle" data-cnt="${cntFa}" onclick="toggleMsgCitations('${drawerId}', this)">منابع (${cntFa}) <span class="eh-v48-chev">▾</span></button>`;

      const citeItems = cites.map(c => {
        const cid = `scite_${++localReg}`;
        citationRegistry[cid] = c;
        const canPreview = c.chunk_id && !String(c.chunk_id).startsWith('row::') && !String(c.chunk_id).startsWith('tbl::');
        const locTxt = c.location ? ` — ${escapeHtml(c.location)}` : '';
        if (canPreview) {
          return `<button type="button" class="eh-v48-cite-item" onclick="openCitation('${cid}')"><span>📄 ${escapeHtml(c.file_name)}</span><small>${locTxt}</small></button>`;
        }
        return `<div class="eh-v48-cite-item is-static"><span>📄 ${escapeHtml(c.file_name)}</span><small>${locTxt}</small></div>`;
      }).join('');

      const transBlock = transText ? `<div class="eh-v48-trans-note">✦ ${escapeHtml(transText)}</div>` : '';
      citeDrawerHtml = `
        <div class="eh-v48-cite-drawer" id="${drawerId}">
          ${transBlock}
          ${citeItems ? `<div class="eh-v48-cite-list">${citeItems}</div>` : ''}
        </div>
      `;
    }

    const actionBarHtml = `
      <div class="eh-v48-action-bar">
        <button type="button" class="copy-mini-btn" onclick="copyText('${copyId}')">کپی متن</button>
        ${citeBtnHtml}
        ${buildScopePill(msg.response_scope || (cites.length ? 'institutional' : 'free'))}
      </div>
      ${citeDrawerHtml}
    `;

    return tablesHtml + actionBarHtml;
  }

  function pullNextSmoothWord(st, now) {
    const pending = st.pendingText;
    if (!pending) return '';
    if (pending[0] === '\n') {
      st.pendingText = pending.slice(1);
      return '\n';
    }
    const m = pending.match(/^([^\s\n]+[ \t]*|[ \t]+)/);
    if (!m) return '';
    const chunk = m[0];
    const hasBoundary = /[ \t\n]$/.test(chunk) || pending.length > chunk.length;
    if (!hasBoundary && !st.serverDone && (now - st.lastArrivalTime) < 75) return '';
    st.pendingText = pending.slice(chunk.length);
    return chunk;
  }

  function finalizeStreamInPlace(st) {
    if (st.finalized) return;
    st.finalized = true;
    delete activeStreams[st.sid];

    const msg = st.finalMsg || { role: 'assistant', content: st.displayedText, tools: st.tools, response_scope: 'institutional' };
    const finalContent = msg.content || st.displayedText || '';
    st.displayedText = finalContent;
    renderIncrementalMarkdown(st, true);

    st.bubbleEl.classList.remove('is-streaming');
    if (st.statusWrapEl) st.statusWrapEl.classList.add('hidden-smooth');
    if (st.cursorEl) {
      st.cursorEl.classList.add('fade-out');
      setTimeout(() => st.cursorEl && st.cursorEl.remove(), 320);
    }

    const timeStr = msg.created_at || new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
    const speedHtml = st.elapsed ? `<span class="speed-pill">⚡ ${st.elapsed} ثانیه</span>` : '';
    st.metaTitleEl.innerHTML = `<span class="eh-v48-ai-ico">✦</span> دستیار هوشمند • ${escapeHtml(timeStr)} ${speedHtml}`;

    if (st.kpiWrapEl) {
      st.kpiWrapEl.innerHTML = buildKpisHtml(msg);
    }

    const copyId = `scopy_${++localReg}`;
    window[copyId] = finalContent;
    const footerHtml = buildFooterAndExtrasHtml(msg, copyId);
    if (footerHtml) {
      st.extrasEl.innerHTML = `<div class="extras-reveal">${footerHtml}</div>`;
    }

    let settleFrames = 16;
    const settleScroll = () => {
      smoothScrollStep();
      if (--settleFrames > 0) requestAnimationFrame(settleScroll);
    };
    requestAnimationFrame(settleScroll);

    document.getElementById('btnSend').disabled = false;
    document.getElementById('chatInput').focus();
  }

  function startPacerLoop(st) {
    if (st.loopActive) return;
    st.loopActive = true;

    const tick = (now) => {
      if (st.finalized || st.errored) {
        st.loopActive = false;
        return;
      }

      const pendingLen = st.pendingText.length;
      if (pendingLen > 0) {
        let minInterval = 24;
        let wordsPerFrame = 1;
        if (st.serverDone) {
          minInterval = 10;
          wordsPerFrame = Math.max(1, Math.min(5, Math.ceil(pendingLen / 70)));
        } else if (pendingLen > 240) {
          minInterval = 13;
          wordsPerFrame = Math.min(4, Math.ceil(pendingLen / 100));
        } else if (pendingLen > 90) {
          minInterval = 16;
          wordsPerFrame = 2;
        }

        if (now - st.lastReleaseTime >= minInterval) {
          let added = '';
          for (let k = 0; k < wordsPerFrame; k++) {
            const w = pullNextSmoothWord(st, now);
            if (!w) break;
            added += w;
          }
          if (added) {
            if (!st.hasVisibleText) {
              st.hasVisibleText = true;
              if (st.statusWrapEl) st.statusWrapEl.classList.add('hidden-smooth');
            }
            st.displayedText += added;
            st.lastReleaseTime = now;
            renderIncrementalMarkdown(st, false);
          }
        }
        smoothScrollStep();
      } else if (st.serverDone) {
        finalizeStreamInPlace(st);
        st.loopActive = false;
        return;
      }
      requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
  }

  window.__EH_SILKY_APPEND = window.appendMessageBubble = function (msg) {
    const div = document.createElement('div');
    const isUser = msg.role === 'user';
    div.className = `msg-bubble ${isUser ? 'msg-user eh-v42-user' : 'msg-ai eh-v42-ai'}`;

    if (isUser) {
      div.innerHTML = `
        <div class="msg-body">${escapeHtml(msg.content)}</div>
        <div class="eh-v48-user-time">${escapeHtml(msg.created_at || '')}</div>
      `;
    } else {
      const copyId = `scopy_${++localReg}`;
      window[copyId] = msg.content || '';
      const kpisHtml = buildKpisHtml(msg);
      const footerHtml = buildFooterAndExtrasHtml(msg, copyId);

      div.innerHTML = `
        <div class="msg-meta eh-v42-ai-meta">
          <span class="meta-title"><span class="eh-v48-ai-ico">✦</span> دستیار هوشمند • ${escapeHtml(msg.created_at || '')}</span>
        </div>
        <div class="eh-v48-kpi-wrap">${kpisHtml}</div>
        <div class="msg-body"></div>
        <div class="msg-extras">${footerHtml}</div>
      `;
      renderIncrementalMarkdown({
        displayedText: msg.content || '',
        bodyEl: div.querySelector('.msg-body'),
        blockCache: [],
        cursorEl: null,
      }, true);
    }
    chatStreamEl.appendChild(div);
    chatStreamEl.scrollTop = chatStreamEl.scrollHeight;
  };

  window.__EH_SILKY_ON_EVENT = window.__onAiStreamEvent = function (evt) {
    if (!evt || !evt.stream_id) return;
    const st = activeStreams[evt.stream_id];
    if (!st) return;

    if (evt.type === 'status') {
      if (st.statusTextEl && !st.hasVisibleText) {
        st.statusTextEl.textContent = (evt.data && evt.data.text) || 'در حال پردازش...';
      }
    } else if (evt.type === 'tool') {
      const label = evt.data && evt.data.label;
      if (label && st.toolsEl && !st.tools.includes(label)) {
        st.tools.push(label);
      }
    } else if (evt.type === 'token') {
      const txt = (evt.data && evt.data.text) || '';
      if (txt) {
        st.pendingText += txt;
        st.lastArrivalTime = performance.now();
        startPacerLoop(st);
      }
    } else if (evt.type === 'done') {
      st.serverDone = true;
      st.finalMsg = (evt.data && evt.data.message) || null;
      st.elapsed = evt.data && evt.data.elapsed;
      if (st.pendingText.length === 0) finalizeStreamInPlace(st);
      else startPacerLoop(st);
    } else if (evt.type === 'error') {
      st.errored = true;
      delete activeStreams[evt.stream_id];
      st.bubbleEl.classList.remove('is-streaming');
      if (st.statusWrapEl) st.statusWrapEl.classList.add('hidden-smooth');
      if (st.cursorEl) st.cursorEl.remove();
      st.metaTitleEl.innerHTML = '<span class="eh-v48-ai-ico">✦</span> دستیار هوشمند • خطا';
      st.bodyEl.innerHTML = `<div class="block-in" style="color:#fca5a5;">${escapeHtml((evt.data && evt.data.error) || 'خطا در ارتباط با مدل هوشمند')}</div>`;
      document.getElementById('btnSend').disabled = false;
      document.getElementById('chatInput').focus();
    }
  };

  window.__EH_SILKY_SEND = window.sendMessage = async function () {
    const input = document.getElementById('chatInput');
    const btn = document.getElementById('btnSend');
    const question = input.value.trim();
    if (!question || btn.disabled) return;

    userPinnedToBottom = true;
    const nowTime = new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
    window.appendMessageBubble({ role: 'user', content: question, created_at: nowTime });

    input.value = '';
    btn.disabled = true;

    const sid = `st_${Date.now()}_${++localSeq}`;
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble msg-ai eh-v42-ai is-streaming block-in';
    bubble.innerHTML = `
      <div class="msg-meta eh-v42-ai-meta">
        <span class="meta-title"><span class="eh-v48-ai-ico">✦</span> دستیار هوشمند • در حال بررسی</span>
        <div class="meta-right" style="display:flex; align-items:center; gap:6px;">
          <div class="tool-badges"></div>
        </div>
      </div>
      <div class="live-status-bar">
        <span class="pulse-orb"></span>
        <span class="live-status-text">در حال پردازش...</span>
      </div>
      <div class="eh-v48-kpi-wrap"></div>
      <div class="msg-body"></div>
      <div class="msg-extras"></div>
    `;
    chatStreamEl.appendChild(bubble);
    chatStreamEl.scrollTop = chatStreamEl.scrollHeight;

    const cursorEl = document.createElement('span');
    cursorEl.className = 'stream-cursor';

    activeStreams[sid] = {
      sid,
      bubbleEl: bubble,
      metaTitleEl: bubble.querySelector('.meta-title'),
      metaRightEl: bubble.querySelector('.meta-right'),
      toolsEl: bubble.querySelector('.tool-badges'),
      statusWrapEl: bubble.querySelector('.live-status-bar'),
      statusTextEl: bubble.querySelector('.live-status-text'),
      kpiWrapEl: bubble.querySelector('.eh-v48-kpi-wrap'),
      bodyEl: bubble.querySelector('.msg-body'),
      extrasEl: bubble.querySelector('.msg-extras'),
      cursorEl,
      blockCache: [],
      pendingText: '',
      displayedText: '',
      tools: [],
      hasVisibleText: false,
      lastArrivalTime: performance.now(),
      lastReleaseTime: 0,
      loopActive: false,
      serverDone: false,
      finalMsg: null,
      elapsed: null,
      finalized: false,
      errored: false,
    };

    try {
      await pywebview.api.ask_ai_stream(
        sid,
        question,
        currentChatMode,
        window.currentChatRoute || 'auto',
        window.currentChatLength || 'concise'
      );
    } catch (e) {
      delete activeStreams[sid];
      bubble.remove();
      btn.disabled = false;
      showToast('خطا در ارسال پرسش: ' + e);
    }
  };
})();
