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

  function call(method, args) {
    if (CLIENT_SIDE[method]) return Promise.resolve(local[method] ? local[method]() : { ok: true });
    return fetch('/rpc/' + encodeURIComponent(method), {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ args: args })
    }).then(function (r) {
      if (r.status === 401) { window.location.href = '/login'; return new Promise(function () {}); }
      return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; });
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
      box.appendChild(t); box.appendChild(b); document.body.appendChild(box);
    }).catch(function () {});
  }

  window.addEventListener('load', function () {
    startEvents(); userChip();
    setTimeout(function () { window.dispatchEvent(new Event('pywebviewready')); }, 0);
  });
})();
