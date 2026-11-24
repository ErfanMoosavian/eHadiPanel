"""Local web edition: a Starlette app that serves the existing UI and exposes the
``AppAPI`` methods as authenticated, permission-checked RPC calls.

The browser gets a ``window.pywebview.api`` shim (see ``web_shim.js``), so the
current front-end keeps working without a rewrite.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import queue
import re
import secrets
import shutil
import tempfile
import threading
import time
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
TAXONOMY_PAGE = Path(__file__).resolve().parent / "taxonomy.html"
OVERRIDES_CSS = Path(__file__).resolve().parent / "web_overrides.css"
_VOICE_SCRIPT_RX = re.compile(r'<script[^>]+voice_copilot\.js[^>]*>\s*</script>', re.I)
COOKIE = "ehadi_session"
MAX_BODY = 12 * 1024 * 1024
DESKTOP_MSG = "این قابلیت در نسخه وب هنوز فعال نیست (نیاز به دیالوگ فایل یا سیستم‌عامل دارد)."
_STREAM_ID_RX = re.compile(r'"stream_id"\s*:\s*"([^"]{1,80})"')
_ID_RX = re.compile(r"^[0-9a-f]{16}$")
_BAD_NAME_RX = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
DOWNLOAD_TTL = 15 * 60
STAGING_TTL = 3600
_ctx = threading.local()  # per-RPC-call file context (see WebWindow.create_file_dialog)
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


def safe_name(name: str, default: str = "file") -> str:
    base = Path(str(name or "").replace("\\", "/")).name
    base = _BAD_NAME_RX.sub("_", base).strip(" .")[:150]
    return base or default


class CallFiles:
    def __init__(self, out_dir: Path, staged: list[Path]) -> None:
        self.out_dir, self.staged = out_dir, staged


def disable_desktop_side_effects() -> None:
    """The desktop code calls os.startfile() after exporting; in the web edition the browser downloads instead."""
    os.startfile = lambda *a, **k: None  # type: ignore[attr-defined]


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

    def create_file_dialog(self, dialog_type: Any = None, directory: str = "", allow_multiple: bool = False,
                           save_filename: str = "", file_types: Any = ()) -> Any:
        """Web replacement for the native dialogs.

        SAVE (recognised by ``save_filename``): hand back a path inside this call's temp folder; the
        file is then offered to the browser as a download.
        OPEN: hand back the files the browser uploaded for this call, or None (= cancelled).
        """
        files = getattr(_ctx, "files", None)
        if files is None:
            return None
        if save_filename:
            return (str(files.out_dir / safe_name(save_filename)),)
        return tuple(str(p) for p in files.staged) or None

    def __getattr__(self, name: str) -> Callable[..., None]:  # minimize(), destroy(), ...
        return lambda *a, **k: None


def create_app(api: Any, auth: AuthStore, secure_cookie: bool = False, audit: Callable[..., None] | None = None,
               work_dir: Path | str | None = None, max_upload_mb: int | None = None,
               services: list[Any] | tuple[Any, ...] = ()) -> Starlette:
    hub = StreamHub()
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="ehadi_web_"))
    (work / "staging").mkdir(parents=True, exist_ok=True)
    (work / "out").mkdir(parents=True, exist_ok=True)
    max_upload = (max_upload_mb or int(os.environ.get("EHADI_MAX_UPLOAD_MB", "1024"))) * 1024 * 1024
    downloads: dict[str, dict] = {}
    dl_lock = threading.Lock()

    def sweep() -> None:
        now = time.time()
        with dl_lock:
            for k in [k for k, v in downloads.items() if v["expires"] < now]:
                shutil.rmtree(downloads.pop(k)["dir"], ignore_errors=True)
        for root in ((work / "staging").glob("*/*"), (work / "out").glob("*")):
            for d in root:
                try:
                    if d.is_dir() and now - d.stat().st_mtime > STAGING_TTL:
                        shutil.rmtree(d, ignore_errors=True)
                except OSError:
                    pass

    def staging_root(token: str) -> Path:
        return work / "staging" / hashlib.sha256(token.encode()).hexdigest()[:16]
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
        css_tag = '<link rel="stylesheet" href="/__web/web_overrides.css">'
        html = html.replace("<head>", "<head>" + shim_tag, 1) if "<head>" in html else shim_tag + html
        html = html.replace("</head>", css_tag + "</head>", 1) if "</head>" in html else html + css_tag
        html = _VOICE_SCRIPT_RX.sub("", html)
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    async def login_page(request: Request) -> Response:
        return HTMLResponse(LOGIN.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})

    async def taxonomy_page(request: Request) -> Response:
        if not current(request):
            return RedirectResponse("/login", status_code=303)
        html = TAXONOMY_PAGE.read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    async def shim(request: Request) -> Response:
        return FileResponse(SHIM, media_type="application/javascript", headers={"Cache-Control": "no-store"})

    async def overrides_css(request: Request) -> Response:
        return FileResponse(OVERRIDES_CSS, media_type="text/css", headers={"Cache-Control": "no-store"})

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

    def _register_downloads(token: str, out_dir: Path, result: Any) -> Any:
        files = sorted(p for p in out_dir.iterdir() if p.is_file()) if out_dir.exists() else []
        if not files:
            shutil.rmtree(out_dir, ignore_errors=True)
            return result
        items = []
        with dl_lock:
            for f in files:
                did = secrets.token_hex(8)
                downloads[did] = {"path": f, "name": f.name, "token": token, "dir": out_dir, "expires": time.time() + DOWNLOAD_TTL}
                items.append({"url": f"/api/download/{did}", "name": f.name})
        if isinstance(result, dict) and result.get("ok", True) is not False:
            result = {**result, "downloads": items, "download_url": items[0]["url"], "path": items[0]["name"]}
        return result

    def _call(user: User, token: str, method: str, args: list, staged: list[Path]) -> Any:
        fn = getattr(api, method, None)
        for svc in services:  # web-only services extend the desktop API
            if not callable(fn):
                fn = getattr(svc, method, None)
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
        if method in P.DOWNLOAD_METHODS or method in P.UPLOAD_METHODS:
            sweep()
            out_dir = work / "out" / secrets.token_hex(8)
            out_dir.mkdir(parents=True)
            _ctx.files = CallFiles(out_dir, staged)
            try:
                result = fn(*args)
            finally:
                _ctx.files = None
                for p in staged:  # staged uploads are one-shot
                    shutil.rmtree(p.parent, ignore_errors=True)
            return _register_downloads(token, out_dir, result)
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
            body = await request.json()
            args, staged_ids = body.get("args", []), body.get("staged", [])
            if not isinstance(args, list) or not isinstance(staged_ids, list):
                raise ValueError
        except Exception:
            return _json({"ok": False, "error": "آرگومان‌ها نامعتبرند."}, 400)
        bad = _check_args(method, args)
        if bad:
            return _json({"ok": False, "error": bad}, 400)
        token = request.cookies.get(COOKIE, "")
        staged: list[Path] = []
        if staged_ids:
            allowed = P.UPLOAD_METHODS.get(method)
            if allowed is None:
                return _json({"ok": False, "error": "این متد فایل نمی‌پذیرد."}, 400)
            for sid in staged_ids[:50]:
                found = list((staging_root(token) / str(sid)).glob("*")) if _ID_RX.match(str(sid)) else []
                if len(found) != 1 or found[0].suffix.lower() not in allowed:
                    return _json({"ok": False, "error": "فایل بارگذاری‌شده نامعتبر یا نوع آن مجاز نیست."}, 400)
                staged.append(found[0])
        try:
            result = await asyncio.to_thread(_call, user, token, method, args, staged)
        except Exception as exc:  # keep internals out of the browser
            log(f"rpc:{method}", "error", user, error=str(exc)[:200])
            return _json({"ok": False, "error": "خطای داخلی در اجرای عملیات."}, 500)
        if not method.startswith("get_"):
            log(f"rpc:{method}", "ok", user)
        return _json(result)

    async def upload(request: Request) -> Response:
        user = current(request)
        if not user:
            return _json({"ok": False, "error": "نیاز به ورود."}, 401)
        token = request.cookies.get(COOKIE, "")
        name = safe_name(request.query_params.get("name", ""))
        if Path(name).suffix.lower() not in P.UPLOAD_ANY_EXT:
            return _json({"ok": False, "error": "نوع فایل مجاز نیست."}, 400)
        if int(request.headers.get("content-length", "0") or 0) > max_upload:
            return _json({"ok": False, "error": "حجم فایل بیشتر از حد مجاز است."}, 413)
        sweep()
        fid = secrets.token_hex(8)
        d = staging_root(token) / fid
        d.mkdir(parents=True)
        size = 0
        try:
            with open(d / name, "wb") as fh:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > max_upload:
                        raise OverflowError
                    fh.write(chunk)
        except OverflowError:
            shutil.rmtree(d, ignore_errors=True)
            return _json({"ok": False, "error": "حجم فایل بیشتر از حد مجاز است."}, 413)
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            return _json({"ok": False, "error": "بارگذاری ناقص ماند."}, 400)
        log("upload", "ok", user, name=name, bytes=size)
        return _json({"ok": True, "id": fid, "name": name, "size": size})

    async def download(request: Request) -> Response:
        user = current(request)
        if not user:
            return _json({"ok": False, "error": "نیاز به ورود."}, 401)
        with dl_lock:
            item = downloads.get(request.path_params["did"])
        if not item or item["token"] != request.cookies.get(COOKIE, "") or not Path(item["path"]).exists():
            return _json({"ok": False, "error": "فایل پیدا نشد یا منقضی شده است."}, 404)
        return FileResponse(item["path"], filename=item["name"], headers={"Cache-Control": "no-store"})

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
        Route("/taxonomy", taxonomy_page),
        Route("/__web/web_shim.js", shim),
        Route("/__web/web_overrides.css", overrides_css),
        Route("/api/login", api_login, methods=["POST"]),
        Route("/api/logout", api_logout, methods=["POST"]),
        Route("/api/me", api_me),
        Route("/api/events", events),
        Route("/rpc/{method}", rpc, methods=["POST"]),
        Route("/api/upload", upload, methods=["POST"]),
        Route("/api/download/{did}", download),
        Mount("/", app=StaticFiles(directory=str(WEB_DIR))),
    ]
    return Starlette(routes=routes)
