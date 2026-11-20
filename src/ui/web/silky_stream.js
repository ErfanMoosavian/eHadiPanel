(() => {
  const chatStreamEl = document.getElementById('chatStream');
  if (!chatStreamEl) return;

  const activeStreams = {};
  let localReg = 0;
  let localSeq = 0;
  let userPinnedToBottom = true;

  chatStreamEl.addEventListener('scroll', () => {
    const dist = chatStreamEl.scrollHeight - chatStreamEl.scrollTop - chatStreamEl.clientHeight;
    userPinnedToBottom = dist < 85;
  });

  function smoothScrollStep() {
    if (!userPinnedToBottom) return;
    const target = chatStreamEl.scrollHeight - chatStreamEl.clientHeight;
    const diff = target - chatStreamEl.scrollTop;
    if (diff > 0.8) {
      chatStreamEl.scrollTop += Math.max(1.2, diff * 0.18);
    } else if (diff > 0) {
      chatStreamEl.scrollTop = target;
    }
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

    if (st.cursorEl && st.cursorEl.parentNode) {
      st.cursorEl.parentNode.removeChild(st.cursorEl);
    }

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
        el.style.margin = '6px 0';
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

  function buildExtrasHtml(msg) {
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
        const toggleText = hasMdTable ? 'نمایش داده‌های خام SQL' : 'جمع کردن جدول';
        return `
          <div class="ai-table-card ${collapsedClass}" id="card_${tid}">
            <div class="ai-table-head">
              <span class="ai-table-title">📊 ${escapeHtml(tbl.title || 'نتیجه تحلیل جدولی')} (${rowLabel})</span>
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

    let citationsHtml = '';
    if (msg.citations && msg.citations.length > 0) {
      const chips = msg.citations.map(c => {
        const cid = `scite_${++localReg}`;
        citationRegistry[cid] = c;
        return `<button class="cite-chip" onclick="openCitation('${cid}')">📄 ${escapeHtml(c.file_name)} — ${escapeHtml(c.location)}</button>`;
      }).join('');
      citationsHtml = `<div class="citation-row">${chips}</div>`;
    }
    return tablesHtml + citationsHtml;
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

    const msg = st.finalMsg || { role: 'assistant', content: st.displayedText, tools: st.tools };
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
    st.metaTitleEl.innerHTML = `دستیار هوشمند • ${escapeHtml(timeStr)} ${speedHtml}`;

    const copyId = `scopy_${++localReg}`;
    window[copyId] = finalContent;
    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-mini-btn block-in';
    copyBtn.textContent = 'کپی متن';
    copyBtn.onclick = () => copyText(copyId);
    st.metaRightEl.appendChild(copyBtn);

    const extrasHtml = buildExtrasHtml(msg);
    if (extrasHtml) {
      st.extrasEl.innerHTML = `<div class="extras-reveal">${extrasHtml}</div>`;
    }

    let settleFrames = 18;
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
        let minInterval = 28;
        let wordsPerFrame = 1;
        if (st.serverDone) {
          minInterval = 12;
          wordsPerFrame = Math.max(1, Math.min(4, Math.ceil(pendingLen / 75)));
        } else if (pendingLen > 240) {
          minInterval = 14;
          wordsPerFrame = Math.min(4, Math.ceil(pendingLen / 110));
        } else if (pendingLen > 90) {
          minInterval = 18;
          wordsPerFrame = 2;
        } else if (pendingLen > 35) {
          minInterval = 22;
          wordsPerFrame = 1;
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

  // جایگزینی توابع رندر و استریم در صفحه
  window.__EH_SILKY_APPEND = window.appendMessageBubble = function (msg) {
    const div = document.createElement('div');
    const isUser = msg.role === 'user';
    div.className = `msg-bubble ${isUser ? 'msg-user' : 'msg-ai'}`;

    if (isUser) {
      div.innerHTML = `
        <div class="msg-meta" style="color:rgba(255,255,255,0.68);">
          <span>شما</span>
          <span>${escapeHtml(msg.created_at || '')}</span>
        </div>
        <div class="msg-body">${escapeHtml(msg.content)}</div>
      `;
    } else {
      const toolsHtml = (msg.tools && msg.tools.length > 0)
        ? `<div class="tool-badges">${msg.tools.map(t => `<span class="tool-badge">⚡ ${escapeHtml(t)}</span>`).join('')}</div>`
        : '';
      const copyId = `scopy_${++localReg}`;
      window[copyId] = msg.content || '';
      const extrasHtml = buildExtrasHtml(msg);

      div.innerHTML = `
        <div class="msg-meta">
          <span>دستیار هوشمند • ${escapeHtml(msg.created_at || '')}</span>
          <div style="display:flex; align-items:center; gap:8px;">
            ${toolsHtml}
            <button class="copy-mini-btn" onclick="copyText('${copyId}')">کپی متن</button>
          </div>
        </div>
        <div class="msg-body"></div>
        <div class="msg-extras">${extrasHtml}</div>
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
        const span = document.createElement('span');
        span.className = 'tool-badge';
        span.textContent = '⚡ ' + label;
        st.toolsEl.appendChild(span);
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
      st.metaTitleEl.textContent = 'دستیار هوشمند • خطا در دریافت پاسخ';
      st.bodyEl.innerHTML = `<div class="block-in" style="color:#fca5a5;">${escapeHtml((evt.data && evt.data.error) || 'خطای نامشخص در ارتباط با Gemini')}</div>`;
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
    bubble.className = 'msg-bubble msg-ai is-streaming block-in';
    bubble.innerHTML = `
      <div class="msg-meta">
        <span class="meta-title">دستیار هوشمند • در حال تحلیل و نگارش</span>
        <div class="meta-right" style="display:flex; align-items:center; gap:8px;">
          <div class="tool-badges"></div>
        </div>
      </div>
      <div class="live-status-bar">
        <span class="pulse-orb"></span>
        <span class="live-status-text">در حال تحلیل پرسش...</span>
      </div>
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
      await pywebview.api.ask_ai_stream(sid, question, currentChatMode);
    } catch (e) {
      delete activeStreams[sid];
      bubble.remove();
      btn.disabled = false;
      showToast('خطا در ارسال پرسش: ' + e);
    }
  };
})();