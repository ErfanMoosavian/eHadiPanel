"""Tests for the local web edition: permission map, auth store, HTTP server."""
from __future__ import annotations

import ast
import http.cookiejar
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import uvicorn

from src.web import permissions as P
from src.web.auth import MAX_FAILS, AuthStore
from src.web.server import create_app

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- permissions
def _appapi_methods() -> set[str]:
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AppAPI")
    return {f.name for f in cls.body if isinstance(f, ast.FunctionDef) and not f.name.startswith("_")}


def test_every_appapi_method_is_classified():
    """A new AppAPI method must be given a permission (or marked desktop-only) before the web edition exposes it."""
    known = set(P.METHOD_PERMS) | P.CLIENT_SIDE | P.DESKTOP_ONLY | P.FORBIDDEN
    assert _appapi_methods() - known == set()


def test_admin_has_everything_and_roles_differ():
    assert P.role_has("admin", "finance.edit") and P.role_has("admin", "anything.at.all")
    assert not P.role_has("alumni_affairs", "finance.view")
    assert P.role_has("alumni_affairs", "registration.review")
    assert not P.role_has("executive", "attendance.edit")
    assert not P.role_has("nonexistent", "dashboard.view")


def test_audit_log_cannot_be_cleared():
    assert "clear_audit_logs" in P.FORBIDDEN and "clear_audit_logs" not in P.METHOD_PERMS


# --------------------------------------------------------------------------- auth store
@pytest.fixture()
def auth(tmp_path):
    return AuthStore(tmp_path / "auth.sqlite3")


def test_login_session_and_logout(auth):
    auth.create_user("ali", "علی", "admin", "correct-horse")
    assert auth.login("ali", "wrong-password") is None
    tok = auth.login("ali", "correct-horse")
    assert tok and auth.user_for_token(tok).username == "ali"
    auth.logout(tok)
    assert auth.user_for_token(tok) is None


def test_lockout_after_repeated_failures(auth):
    auth.create_user("ali", "علی", "admin", "correct-horse")
    for _ in range(MAX_FAILS):
        assert auth.login("ali", "bad", client="1.2.3.4") is None
    assert auth.login("ali", "correct-horse", client="9.9.9.9") is None  # locked even with the right password


def test_disable_and_password_change_end_sessions(auth):
    auth.create_user("ali", "علی", "admin", "correct-horse")
    tok = auth.login("ali", "correct-horse")
    auth.set_password("ali", "another-secret")
    assert auth.user_for_token(tok) is None
    tok = auth.login("ali", "another-secret")
    auth.set_active("ali", False)
    assert auth.user_for_token(tok) is None and auth.login("ali", "another-secret") is None


def test_validation(auth):
    with pytest.raises(ValueError):
        auth.create_user("x", "X", "admin", "short")
    with pytest.raises(ValueError):
        auth.create_user("x", "X", "no_such_role", "long-enough-pw")
    auth.create_user("x", "X", "admin", "long-enough-pw")
    with pytest.raises(ValueError):
        auth.create_user("X", "X2", "admin", "long-enough-pw")  # usernames are case-insensitive


# --------------------------------------------------------------------------- HTTP server
class FakeAPI:
    def __init__(self):
        self.calls: list[str] = []
        self.window = None

    def set_window(self, w):
        self.window = w

    def get_dashboard_data(self):
        return {"ok": True, "n": float("nan")}

    def get_settings(self):
        return {"api_key": "SECRET", "model": "m"}

    def get_bi_table_data(self, name):
        return {"name": name}

    def save_dropped_chunk(self, name, b64, first):
        self.calls.append("save_dropped_chunk")
        return {"ok": True}

    def export_table_excel(self, payload):
        sel = self.window.create_file_dialog(30, save_filename=payload.get("name", "گزارش.xlsx"), file_types=("x",))
        Path(sel[0]).write_bytes(b"XLSXDATA")
        return {"ok": True, "path": sel[0]}

    def add_files_dialog(self):
        sel = self.window.create_file_dialog(10, allow_multiple=True)
        if not sel:
            return {"copied": 0}
        self.calls.append("added:" + ",".join(sorted(Path(p).name + "=" + Path(p).read_text() for p in sel)))
        return {"copied": len(sel)}

    def clear_audit_logs(self):
        self.calls.append("clear_audit_logs")
        return {"ok": True}

    def ask_ai_stream(self, stream_id, question, *a):
        def push():
            time.sleep(0.2)
            pkt = {"stream_id": stream_id, "type": "token", "data": {"text": "سلام"}}
            self.window.evaluate_js("window.__onAiStreamEvent && window.__onAiStreamEvent(" + json.dumps(pkt, ensure_ascii=False) + ")")
        threading.Thread(target=push, daemon=True).start()
        return {"ok": True}


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect())

    def req(self, path, body=None, method=None, ctype="application/json"):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method or ("POST" if data is not None else "GET"))
        if data is not None and ctype:
            r.add_header("Content-Type", ctype)
        try:
            with self.op.open(r, timeout=10) as resp:
                return resp.status, resp.read().decode(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), e.headers

    def rpc(self, method, *args, **kw):
        s, b, _ = self.req(f"/rpc/{method}", {"args": list(args)}, **kw)
        return s, (json.loads(b) if b.startswith("{") else b)

    def up(self, name, data: bytes):
        from urllib.parse import quote
        r = urllib.request.Request(self.base + "/api/upload?name=" + quote(name), data=data, method="POST")
        r.add_header("Content-Type", "application/octet-stream")
        try:
            with self.op.open(r, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def login(self, u, p):
        return self.req("/api/login", {"username": u, "password": p})[0]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


@pytest.fixture()
def srv(tmp_path):
    auth = AuthStore(tmp_path / "auth.sqlite3")
    auth.create_user("boss", "مدیر", "admin", "boss-password")
    auth.create_user("boss2", "مدیر دوم", "admin", "boss2-password")
    auth.create_user("exec", "اجرایی", "executive", "exec-password")
    auth.create_user("alumni", "دانش‌آموختگان", "alumni_affairs", "alumni-password")
    api = FakeAPI()
    audit_log: list[tuple] = []
    app = create_app(api, auth, audit=lambda *a: audit_log.append(a), work_dir=tmp_path / "work", max_upload_mb=1)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    while not server.started:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", api, audit_log
    server.should_exit = True
    t.join(5)


def test_unauthenticated_access_is_refused(srv):
    base, _, _ = srv
    c = Client(base)
    s, _, h = c.req("/")
    assert s == 303 and h["location"] == "/login"
    assert c.rpc("get_dashboard_data")[0] == 401
    assert c.req("/api/events")[0] == 401
    assert c.req("/login")[0] == 200


def test_login_cookie_flags_and_index_gets_shim(srv):
    base, _, _ = srv
    c = Client(base)
    assert c.login("boss", "wrong") == 401
    s, _, h = c.req("/api/login", {"username": "boss", "password": "boss-password"})
    cookie = h["set-cookie"].lower()
    assert s == 200 and "httponly" in cookie and "samesite=strict" in cookie
    s, html, _ = c.req("/")
    assert s == 200 and "/__web/web_shim.js" in html
    assert c.req("/api/me")[0] == 200


def test_rpc_permissions(srv):
    base, api, _ = srv
    ex = Client(base)
    ex.login("exec", "exec-password")
    assert ex.rpc("get_dashboard_data")[0] == 200
    assert ex.rpc("ask_ai_stream", "s1", "q")[0] == 403          # AI is admin-only for now
    assert ex.rpc("get_settings")[0] == 403
    assert ex.rpc("save_dropped_chunk", "a.xlsx", "", True)[0] == 403
    al = Client(base)
    al.login("alumni", "alumni-password")
    assert al.rpc("save_dropped_chunk", "a.xlsx", "", True)[0] == 200
    assert al.rpc("save_finance_category_rule", "k", "c")[0] == 403


def test_admin_cannot_clear_audit_and_unknown_methods(srv):
    base, api, _ = srv
    a = Client(base)
    a.login("boss", "boss-password")
    assert a.rpc("clear_audit_logs")[0] == 403 and "clear_audit_logs" not in api.calls
    assert a.rpc("no_such_method")[0] == 404
    assert a.rpc("_invalidate_caches")[0] == 403
    s, body = a.rpc("open_file_path", "C:/x")
    assert s == 200 and body["ok"] is False                       # desktop-only message
    s, body = a.rpc("toggle_maximize")                            # window chrome is client-side
    assert s == 404


def test_input_validation_and_json_safety(srv):
    base, _, _ = srv
    a = Client(base)
    a.login("boss", "boss-password")
    assert a.rpc("get_bi_table_data", 'x"; DROP TABLE y; --')[0] == 400
    assert a.rpc("get_bi_table_data", "جدول ۱")[0] == 200
    assert a.rpc("save_dropped_chunk", "evil.exe", "", True)[0] == 400
    assert a.req("/rpc/get_dashboard_data", {"args": []}, ctype="text/plain")[0] == 400   # CSRF-style form posts
    s, body = a.rpc("get_dashboard_data")
    assert s == 200 and body["n"] is None                          # NaN -> null


def test_api_key_never_reaches_browser(srv):
    base, _, _ = srv
    a = Client(base)
    a.login("boss", "boss-password")
    s, body = a.rpc("get_settings")
    assert body["api_key"] == "" and body["has_key"] is True


def test_actions_are_audited_with_user(srv):
    base, _, audit_log = srv
    al = Client(base)
    al.login("alumni", "alumni-password")
    al.rpc("save_dropped_chunk", "a.xlsx", "", True)
    al.rpc("save_finance_category_rule", "k", "c")
    actions = [(a[0], a[2], a[3]["user"]) for a in audit_log]
    assert ("rpc:save_dropped_chunk", "ok", "alumni") in actions
    assert ("rpc:save_finance_category_rule", "forbidden", "alumni") in actions


def test_stream_events_reach_only_the_owner(srv):
    base, _, _ = srv
    a, b = Client(base), Client(base)
    a.login("boss", "boss-password")
    b.login("boss2", "boss2-password")

    def open_stream(c):
        r = urllib.request.Request(base + "/api/events")
        return c.op.open(r, timeout=3)

    sa, sb = open_stream(a), open_stream(b)
    assert a.rpc("ask_ai_stream", "stream-A", "hello")[0] == 200
    line = ""
    while not line.startswith("data:"):
        line = sa.readline().decode()
    assert json.loads(line[5:])["stream_id"] == "stream-A"
    sb.fp.raw._sock.settimeout(1.0) if hasattr(sb.fp, "raw") else None
    got_other = False
    try:
        for _ in range(3):
            if sb.readline().decode().startswith("data:"):
                got_other = True
    except Exception:
        pass
    assert not got_other


def test_static_assets_served_and_no_traversal(srv):
    base, _, _ = srv
    c = Client(base)
    assert c.req("/core/app_core.js")[0] == 200
    assert c.req("/fonts/fonts.css")[0] == 200
    s, body, _ = c.req("/..%2f..%2fmain.py")
    assert s in (400, 404) and "AppAPI" not in body
    s, body, _ = c.req("/%2e%2e/%2e%2e/main.py")
    assert s in (400, 404) and "AppAPI" not in body


# --------------------------------------------------------------------------- upload / download
def test_export_is_downloaded_by_the_owner_only(srv):
    base, _, _ = srv
    a, b = Client(base), Client(base)
    a.login("boss", "boss-password")
    b.login("boss2", "boss2-password")
    s, res = a.rpc("export_table_excel", {"name": "گزارش دانش‌پژوهان.xlsx"})
    assert s == 200 and res["ok"] and res["path"] == "گزارش دانش‌پژوهان.xlsx"       # no server path leaks
    assert "tmp" not in json.dumps(res) and res["download_url"].startswith("/api/download/")
    st, body, h = a.req(res["download_url"])
    assert st == 200 and body == "XLSXDATA" and "attachment" in h["content-disposition"]
    assert b.req(res["download_url"])[0] == 404                                       # another user's session
    assert Client(base).req(res["download_url"])[0] == 401


def test_export_name_cannot_escape_the_temp_folder(srv):
    base, _, _ = srv
    a = Client(base)
    a.login("boss", "boss-password")
    s, res = a.rpc("export_table_excel", {"name": "../../evil.xlsx"})
    assert s == 200 and res["path"] == "evil.xlsx"


def test_browser_upload_feeds_the_open_dialog(srv):
    base, api, _ = srv
    c = Client(base)
    c.login("alumni", "alumni-password")
    s, up = c.up("فهرست.xlsx", "hello".encode())
    assert s == 200 and up["ok"]
    s, b, _ = c.req("/rpc/add_files_dialog", {"args": [], "staged": [up["id"]]})
    assert s == 200 and json.loads(b)["copied"] == 1
    assert api.calls[-1] == "added:فهرست.xlsx=hello"
    # staged files are one-shot
    assert json.loads(c.req("/rpc/add_files_dialog", {"args": [], "staged": [up["id"]]})[1])["ok"] is False
    # no upload = the user cancelled the picker
    assert c.rpc("add_files_dialog")[1] == {"copied": 0}


def test_upload_rules(srv):
    base, _, _ = srv
    c, other = Client(base), Client(base)
    c.login("alumni", "alumni-password")
    other.login("boss", "boss-password")
    assert c.up("virus.exe", b"x")[0] == 400
    try:  # rejected from Content-Length before the body is read; the client may see a reset instead of the 413
        assert c.up("big.xlsx", b"x" * (2 * 1024 * 1024))[0] == 413
    except urllib.error.URLError:
        pass
    assert c.up("ok.xlsx", b"x" * 1000)[0] == 200                      # the server is still healthy afterwards
    s, up = c.up("a.xlsx", b"1")
    # another user cannot use my staged file, and a font cannot be fed to the documents importer
    assert json.loads(other.req("/rpc/add_files_dialog", {"args": [], "staged": [up["id"]]})[1])["ok"] is False
    s, fnt = c.up("f.ttf", b"1")
    assert json.loads(c.req("/rpc/add_files_dialog", {"args": [], "staged": [fnt["id"]]})[1])["ok"] is False
    assert Client(base).up("a.xlsx", b"1")[0] == 401
    s, b, _ = c.req("/rpc/get_dashboard_data", {"args": [], "staged": [up["id"]]})   # staged only for upload methods
    assert s == 400
