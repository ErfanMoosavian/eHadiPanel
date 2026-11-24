/* Local web edition: emulates pywebview's window.pywebview.api over HTTP so the
   existing front-end runs unchanged in a browser. */
(function () {
  'use strict';
  var CLIENT_SIDE = {
    set_window: 1, minimize: 1, close: 1, get_window_bounds: 1, set_window_bounds: 1, toggle_maximize: 1,
    is_window_maximized: 1, toggle_maximize_window: 1, begin_window_resize: 1, start_window_resize: 1,
    resize_window_absolute: 1, toggle_fullscreen_window: 1
  };
  var local = {
    get_window_bounds: function () { return { x: 0, y: 0, width: window.innerWidth, height: window.innerHeight }; },
    is_window_maximized: function () { return true; },
    toggle_fullscreen_window: function () {
      if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen();
      return { ok: true };
    }
  };

  // Methods that used a native "open file" dialog: pick files in the browser, upload, then call the RPC.
  var PICK = {
    add_files_dialog: { accept: '.pdf,.docx,.pptx,.xlsx,.xls,.csv,.accdb,.mdb', multiple: true, cancel: { copied: 0 } },
    select_logo_dialog: { accept: '.png,.jpg,.jpeg,.webp', multiple: false, cancel: { ok: false, cancelled: true } },
    select_font_dialog: { accept: '.ttf,.otf,.woff2', multiple: false, cancel: { ok: false, cancelled: true } },
    select_and_preview_porsline: { accept: '.xlsx,.xls,.csv', multiple: false, cancel: { ok: false, cancelled: true } }
  };

  var chip = null;
  function status(text) {
    if (!text) { if (chip) { chip.remove(); chip = null; } return; }
    if (!chip) {
      chip = document.createElement('div');
      chip.style.cssText = 'position:fixed;bottom:10px;right:10px;z-index:99999;padding:8px 12px;border-radius:10px;' +
        'font:12px Vazirmatn,Tahoma,sans-serif;color:#fff;background:rgba(59,109,240,.92);direction:rtl';
      document.body.appendChild(chip);
    }
    chip.textContent = text;
  }

  function pickFiles(spec) {
    return new Promise(function (resolve) {
      var input = document.createElement('input');
      input.type = 'file'; input.accept = spec.accept; input.multiple = !!spec.multiple; input.style.display = 'none';
      var done = function (files) { input.remove(); resolve(files); };
      input.onchange = function () { done(Array.prototype.slice.call(input.files || [])); };
      input.oncancel = function () { done([]); };
      document.body.appendChild(input);
      input.click();
    });
  }

  function uploadAll(files) {
    var ids = [], chain = Promise.resolve();
    files.forEach(function (f, i) {
      chain = chain.then(function () {
        status('در حال بارگذاری ' + (i + 1) + ' از ' + files.length + ': ' + f.name);
        return fetch('/api/upload?name=' + encodeURIComponent(f.name), { method: 'POST', credentials: 'same-origin', body: f })
          .then(function (r) {
            if (r.status === 401) { window.location.href = '/login'; return new Promise(function () {}); }
            return r.json();
          })
          .then(function (d) { if (!d.ok) throw new Error(d.error || 'upload failed'); ids.push(d.id); });
      });
    });
    return chain.then(function () { return ids; });
  }

  function triggerDownload(url, name) {
    var a = document.createElement('a');
    a.href = url; a.download = name || ''; a.style.display = 'none';
    document.body.appendChild(a); a.click(); a.remove();
  }

  function rpc(method, args, staged) {
    var payload = { args: args };
    if (staged && staged.length) payload.staged = staged;
    return fetch('/rpc/' + encodeURIComponent(method), {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) {
      if (r.status === 401) { window.location.href = '/login'; return new Promise(function () {}); }
      return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; });
    }).then(function (data) {
      if (data && data.download_url) triggerDownload(data.download_url, data.path);
      return data;
    });
  }

  function call(method, args) {
    if (CLIENT_SIDE[method]) return Promise.resolve(local[method] ? local[method]() : { ok: true });
    var spec = PICK[method];
    if (!spec) return rpc(method, args);
    return pickFiles(spec).then(function (files) {
      if (!files.length) return spec.cancel;
      return uploadAll(files).then(function (ids) { status(''); return rpc(method, args, ids); })
        .catch(function (e) { status(''); return { ok: false, error: String(e && e.message || e) }; });
    });
  }

  window.pywebview = {
    api: new Proxy({}, {
      get: function (_, prop) {
        if (typeof prop !== 'string' || prop === 'then') return undefined;
        return function () { return call(prop, Array.prototype.slice.call(arguments)); };
      }
    })
  };

  function startEvents() {
    if (!window.EventSource) return;
    var es = new EventSource('/api/events');
    es.onmessage = function (e) {
      try { if (window.__onAiStreamEvent) window.__onAiStreamEvent(JSON.parse(e.data)); } catch (_) {}
    };
  }

  function userChip() {
    fetch('/api/me', { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (me) {
      if (!me || !me.ok) return;
      var box = document.createElement('div');
      box.style.cssText = 'position:fixed;bottom:10px;left:10px;z-index:99999;display:flex;gap:8px;align-items:center;' +
        'padding:6px 10px;border-radius:10px;font:12px Vazirmatn,Tahoma,sans-serif;color:#dfe6f3;' +
        'background:rgba(10,16,32,.85);border:1px solid rgba(255,255,255,.12);direction:rtl';
      var t = document.createElement('span');
      t.textContent = me.display_name + ' — ' + me.role_label;
      var b = document.createElement('button');
      b.textContent = 'خروج';
      b.style.cssText = 'cursor:pointer;border:0;border-radius:6px;padding:3px 8px;background:#2a3550;color:#fff;font:inherit';
      b.onclick = function () {
        fetch('/api/logout', { method: 'POST', credentials: 'same-origin' }).then(function () { window.location.href = '/login'; });
      };
      var lnk = document.createElement('a');
      lnk.href = '/taxonomy'; lnk.textContent = 'ساختار کارگروه‌ها';
      lnk.style.cssText = 'color:#9ec0ff;text-decoration:none';
      box.appendChild(t); box.appendChild(lnk); box.appendChild(b); document.body.appendChild(box);
    }).catch(function () {});
  }

  function cleanDesktopUI() {
    if (!document.body) return;
    document.body.classList.add('eh-web-mode', 'eh-win-maximized');
    document.querySelectorAll('.win-resize-handle, .eh-win-resize-edge').forEach(function (el) { el.remove(); });
    document.querySelectorAll('[onclick]').forEach(function (el) {
      var oc = el.getAttribute('onclick') || '';
      if (/openFolder|open_raw_docs_folder|open_file_path|open_registered_file|listen_voice|process_voice/i.test(oc)) {
        el.classList.add('eh-web-hidden');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', cleanDesktopUI);
  window.addEventListener('load', function () {
    cleanDesktopUI(); startEvents(); userChip();
    setTimeout(function () {
      window.dispatchEvent(new Event('pywebviewready'));
      window.dispatchEvent(new Event('resize'));
    }, 0);
  });
})();
