"""Local web edition: a Starlette app that serves the existing UI and exposes the
``AppAPI`` methods as authenticated, permission-checked RPC calls.

The browser gets a ``window.pywebview.api`` shim (see ``web_shim.js``), so the
current front-end keeps working without a rewrite.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import queue
import re
import threading
from pathlib import Path
from typing import Any, Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from src.web import permissions as P
from src.web.auth import AuthStore, User

WEB_DIR = Path(__file__).resolve().parent.parent / "ui" / "web"
SHIM = Path(__file__).resolve().parent / "web_shim.js"
LOGIN = Path(__file__).resolve().parent / "login.html"
COOKIE = "ehadi_session"
MAX_BODY = 12 * 1024 * 1024
DESKTOP_MSG = "این قابلیت در نسخه وب هنوز فعال نیست (نیاز به دیالوگ فایل یا سیستم‌عامل دارد)."
_STREAM_ID_RX = re.compile(r'"stream_id"\s*:\s*"([^"]{1,80})"')
_SAFE_TABLE_RX = re.compile(r'^[^"\';\\\x00-\x1f]{1,160}$')


def _clean(o: Any) -> Any:
    """JSON-safe copy: NaN/inf -> None, unknown types -> str."""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_clean(v) for v in o]
    if o is None or isinstance(o, (str, int, bool)):
        return o
    return str(o)


def _json(data: Any, status: int = 200) -> Response:
    return Response(json.dumps(_clean(data), ensure_ascii=False), status_code=status, media_type="application/json")


class StreamHub:
    """Routes AI stream events only to the session that started the stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, queue.Queue] = {}          # token -> queue
        self._owner: dict[str, str] = {}                    # stream_id -> token

    def subscribe(self, token: str) -> queue.Queue:
        with self._lock:
            return self._queues.setdefault(token, queue.Queue(maxsize=2000))

    def drop(self, token: str) -> None:
        with self._lock:
            self._queues.pop(token, None)
            for k in [k for k, v in self._owner.items() if v == token]:
                self._owner.pop(k, None)

    def claim(self, stream_id: str, token: str) -> None:
        with self._lock:
            self._owner[stream_id] = token

    def publish(self, stream_id: str, packet: dict) -> None:
        with self._lock:
            q = self._queues.get(self._owner.get(stream_id, ""))
        if q is not None:
            try:
                q.put_nowait(packet)
            except queue.Full:
                pass


class WebWindow:
    """Stands in for the pywebview window: ``AppAPI`` pushes AI tokens via ``evaluate_js``."""

    def __init__(self, hub: StreamHub) -> None:
        self.hub = hub

    def evaluate_js(self, js: str) -> None:
        start = js.find("(", js.find("__onAiStreamEvent(") if "__onAiStreamEvent(" in js else 0)
        end = js.rfind(")")
        if start < 0 or end <= start:
            return
        try:
            packet = json.loads(js[start + 1:end])
        except Exception:
            return
        sid = str(packet.get("stream_id", ""))
        if sid:
            self.hub.publish(sid, packet)

    def __getattr__(self, name: str) -> Callable[..., None]:  # minimize(), destroy(), ...
        return lambda *a, **k: None


def create_app(api: Any, auth: AuthStore, secure_cookie: bool = False, audit: Callable[..., None] | None = None) -> Starlette:
    hub = StreamHub()
    if hasattr(api, "set_window"):
        api.set_window(WebWindow(hub))

    def log(action: str, status: str, user: User | None, **details: Any) -> None:
        if audit:
            audit(action, "web", status, {"user": user.username if user else "-", **details})

    def current(request: Request) -> User | None:
        return auth.user_for_token(request.cookies.get(COOKIE))

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else ""

    # ---- pages -----------------------------------------------------------
    async def index(request: Request) -> Response:
        if not current(request):
            return RedirectResponse("/login", status_code=303)
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        shim_tag = '<script src="/__web/web_shim.js"></script>'
        html = html.replace("<head>", "<head>" + shim_tag, 1) if "<head>" in html else shim_tag + html
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    async def login_page(request: Request) -> Response:
        return HTMLResponse(LOGIN.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})

    async def shim(request: Request) -> Response:
        return FileResponse(SHIM, media_type="application/javascript", headers={"Cache-Control": "no-store"})

    # ---- auth API --------------------------------------------------------
    async def api_login(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:
            return _json({"ok": False, "error": "درخواست نامعتبر."}, 400)
        token = await asyncio.to_thread(auth.login, str(body.get("username", "")), str(body.get("password", "")), client_ip(request))
        if not token:
            log("login", "denied", None, username=str(body.get("username", ""))[:40], ip=client_ip(request))
            return _json({"ok": False, "error": "نام کاربری یا رمز عبور درست نیست، یا حساب موقتاً قفل شده است."}, 401)
        user = auth.user_for_token(token)
        log("login", "ok", user, ip=client_ip(request))
        resp = _json({"ok": True})
        resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=secure_cookie, max_age=12 * 3600, path="/")
        return resp

    async def api_logout(request: Request) -> Response:
        user = current(request)
        auth.logout(request.cookies.get(COOKIE))
        hub.drop(request.cookies.get(COOKIE, ""))
        log("logout", "ok", user)
        resp = _json({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    async def api_me(request: Request) -> Response:
        user = current(request)
        if not user:
            return _json({"ok": False}, 401)
        perms = P.ROLES[user.role]["perms"]
        return _json({"ok": True, "username": user.username, "display_name": user.display_name,
                      "role": user.role, "role_label": P.ROLES[user.role]["label"],
                      "permissions": ["*"] if P.ALL in perms else sorted(perms)})

    # ---- RPC -------------------------------------------------------------
    def _check_args(method: str, args: list) -> str | None:
        if method == "get_bi_table_data" and not (args and isinstance(args[0], str) and _SAFE_TABLE_RX.match(args[0])):
            return "نام جدول نامعتبر است."
        if method == "save_dropped_chunk":
            name = str(args[0] if args else "")
            if Path(name.replace("\\", "/")).suffix.lower() not in P.ALLOWED_UPLOAD_EXT:
                return "نوع فایل مجاز نیست."
        return None

    def _call(user: User, token: str, method: str, args: list) -> Any:
        fn = getattr(api, method, None)
        if not callable(fn):
            return {"ok": False, "error": "متد وجود ندارد."}
        if method == "ask_ai_stream" and args:
            hub.claim(str(args[0]), token)
        if method == "get_settings":  # never send the API key to the browser
            res = fn(*args)
            if isinstance(res, dict):
                res = {**res, "has_key": bool(res.get("api_key")), "api_key": ""}
            return res
        if method == "save_settings" and len(args) >= 2 and not str(args[0] or "").strip():
            from src.core.config import Config  # blank key = keep the stored one
            args = [Config.GEMINI_API_KEY, *args[1:]]
        return fn(*args)

    async def rpc(request: Request) -> Response:
        user = current(request)
        if not user:
            return _json({"ok": False, "error": "نیاز به ورود."}, 401)
        method = request.path_params["method"]
        if method.startswith("_") or method in P.FORBIDDEN:
            return _json({"ok": False, "error": "این عملیات مجاز نیست."}, 403)
        if method in P.DESKTOP_ONLY:
            return _json({"ok": False, "error": DESKTOP_MSG})
        perm = P.METHOD_PERMS.get(method)
        if perm is None:
            return _json({"ok": False, "error": "متد ناشناخته."}, 404)
        if perm != "auth" and not P.role_has(user.role, perm):
            log(f"rpc:{method}", "forbidden", user)
            return _json({"ok": False, "error": "شما به این بخش دسترسی ندارید."}, 403)
        if "application/json" not in request.headers.get("content-type", ""):
            return _json({"ok": False, "error": "درخواست نامعتبر."}, 400)
        if int(request.headers.get("content-length", "0") or 0) > MAX_BODY:
            return _json({"ok": False, "error": "حجم درخواست زیاد است."}, 413)
        try:
            args = (await request.json()).get("args", [])
            if not isinstance(args, list):
                raise ValueError
        except Exception:
            return _json({"ok": False, "error": "آرگومان‌ها نامعتبرند."}, 400)
        bad = _check_args(method, args)
        if bad:
            return _json({"ok": False, "error": bad}, 400)
        try:
            result = await asyncio.to_thread(_call, user, request.cookies.get(COOKIE, ""), method, args)
        except Exception as exc:  # keep internals out of the browser
            log(f"rpc:{method}", "error", user, error=str(exc)[:200])
            return _json({"ok": False, "error": "خطای داخلی در اجرای عملیات."}, 500)
        if not method.startswith("get_"):
            log(f"rpc:{method}", "ok", user)
        return _json(result)

    async def events(request: Request) -> Response:
        token = request.cookies.get(COOKIE, "")
        if not auth.user_for_token(token):
            return _json({"ok": False}, 401)
        q = hub.subscribe(token)
        loop = asyncio.get_running_loop()

        async def gen():
            try:
                while not await request.is_disconnected():
                    try:
                        pkt = await loop.run_in_executor(None, lambda: q.get(True, 15))
                        yield f"data: {json.dumps(_clean(pkt), ensure_ascii=False)}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
            finally:
                pass

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    routes = [
        Route("/", index), Route("/index.html", index),
        Route("/login", login_page),
        Route("/__web/web_shim.js", shim),
        Route("/api/login", api_login, methods=["POST"]),
        Route("/api/logout", api_logout, methods=["POST"]),
        Route("/api/me", api_me),
        Route("/api/events", events),
        Route("/rpc/{method}", rpc, methods=["POST"]),
        Mount("/", app=StaticFiles(directory=str(WEB_DIR))),
    ]
    return Starlette(routes=routes)
