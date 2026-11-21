from __future__ import annotations

import datetime as _dt
from src.core.db_manager import detect_duplicate_files, format_jalali_now, get_db_lock, iso_to_jalali
import importlib.metadata as _meta
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import traceback
import types
import zipfile

APP_VERSION = "Beta 0.2"
_INSTALLED = False
_FE_LOCK = threading.Lock()
_JS_API_REF = None


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _paths() -> dict[str, Path]:
    base = _project_root()
    try:
        from src.core.config import Config
        Config.ensure_directories()
        data_dir = Path(Config.DATA_DIR)
        log_dir = Path(Config.LOGS_DIR)
        diag_dir = data_dir / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        data_dir = base / "data"
        log_dir = data_dir / "logs"
        diag_dir = data_dir / "diagnostics"
        log_dir.mkdir(parents=True, exist_ok=True)
    return {
        "root": base,
        "data": data_dir,
        "logs": log_dir,
        "diag": diag_dir,
        "app_log": log_dir / "app.log",
        "fe_log": log_dir / "frontend.log",
    }


def redact_sensitive(text: str) -> str:
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"AIza[0-9A-Za-z\-_]{20,}", "[REDACTED_GEMINI_KEY]", s)
    s = re.sub(r"sk-[0-9A-Za-z\-_]{16,}", "[REDACTED_API_KEY]", s)
    s = re.sub(
        r"(?i)(api[_-]?key|authorization|bearer|password|secret|token)(\s*[:=]\s*['\"]?)([^\s'\",;}{]+)",
        r"\1\2[REDACTED]",
        s,
    )
    s = re.sub(r"(?i)([A-Z]:\\Users\\)([^\\/\s\"']+)", r"\1<USER>", s)
    return s


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive(super().format(record))


def _setup_logging() -> None:
    p = _paths()
    root_logger = logging.getLogger()
    if any(getattr(h, "_eh_diag_handler", False) for h in root_logger.handlers):
        return
    handler = RotatingFileHandler(
        str(p["app_log"]),
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler._eh_diag_handler = True  # type: ignore[attr-defined]
    handler.setLevel(logging.WARNING)
    handler.setFormatter(
        _RedactingFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root_logger.addHandler(handler)
    if root_logger.level == logging.NOTSET or root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)


def _install_excepthooks() -> None:
    orig_sys_hook = sys.excepthook

    def _sys_hook(exc_type, exc_value, exc_tb):
        try:
            tb_txt = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            logging.getLogger("eHadiPanel.Crash").error(
                "Unhandled MainThread Exception:\n%s", redact_sensitive(tb_txt)
            )
        except Exception:
            pass
        try:
            orig_sys_hook(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _sys_hook

    if hasattr(threading, "excepthook"):
        orig_th_hook = threading.excepthook

        def _th_hook(args):
            try:
                tb_txt = "".join(
                    traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
                )
                tname = getattr(args.thread, "name", "unknown")
                logging.getLogger("eHadiPanel.ThreadCrash").error(
                    "Unhandled Thread(%s) Exception:\n%s", tname, redact_sensitive(tb_txt)
                )
            except Exception:
                pass
            try:
                orig_th_hook(args)
            except Exception:
                pass

        threading.excepthook = _th_hook


def log_frontend_error(payload=None) -> dict:
    try:
        p = _paths()
        fe_log = p["fe_log"]
        if isinstance(payload, str):
            data = {"type": "js_error", "message": payload}
        elif isinstance(payload, dict):
            data = payload
        else:
            data = {"type": "js_error", "message": str(payload)}

        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        etype = redact_sensitive(str(data.get("type", "js_error")))[:40]
        page = redact_sensitive(str(data.get("page", "-")))[:40]
        msg = redact_sensitive(str(data.get("message", "")))[:800]
        src = redact_sensitive(str(data.get("source", "")))[:200]
        line = data.get("line", "")
        stack = redact_sensitive(str(data.get("stack", "")))[:1200].replace("\n", " | ")

        entry = f"{ts} | {etype} | page={page} | {msg}"
        if src:
            entry += f" | src={src}:{line}"
        if stack:
            entry += f" | stack={stack}"
        entry += "\n"

        with _FE_LOCK:
            if fe_log.exists() and fe_log.stat().st_size > 1024 * 1024:
                bak = fe_log.with_suffix(".log.1")
                if bak.exists():
                    bak.unlink(missing_ok=True)
                fe_log.rename(bak)
            with fe_log.open("a", encoding="utf-8") as f:
                f.write(entry)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _find_duckdb_files() -> list[Path]:
    p = _paths()
    found: list[Path] = []
    seen: set[str] = set()
    search_roots: list[Path] = []
    try:
        from src.core.config import Config
        if getattr(Config, "DUCKDB_PATH", None):
            search_roots.append(Path(Config.DUCKDB_PATH).parent)
        if getattr(Config, "STORAGE_DIR", None):
            search_roots.append(Path(Config.STORAGE_DIR))
    except Exception:
        pass
    search_roots.extend([p["data"], p["root"]])
    for folder in search_roots:
        if not folder.exists():
            continue
        for pat in ("*.duckdb", "*/*.duckdb"):
            for fp in folder.glob(pat):
                key = str(fp.resolve()).lower()
                if key not in seen and fp.is_file():
                    seen.add(key)
                    found.append(fp)
    return found


def _audit_duckdb(collect_schema: bool = False) -> tuple[dict, list[dict]]:
    schemas: list[dict] = []
    db_files = _find_duckdb_files()
    if not db_files:
        return (
            {
                "id": "duckdb",
                "title": "پایگاه‌داده تحلیلی (DuckDB)",
                "status": "warning",
                "detail": "هنوز فایل پایگاه‌داده آماری ساخته نشده است (پس از ورود اولین فایل اکسل ایجاد می‌شود).",
            },
            schemas,
        )

    try:
        import duckdb  # type: ignore
    except Exception as exc:
        return (
            {
                "id": "duckdb",
                "title": "پایگاه‌داده تحلیلی (DuckDB)",
                "status": "error",
                "detail": f"کتابخانه DuckDB بارگذاری نشد: {exc}",
            },
            schemas,
        )

    total_tables = 0
    empty_tables: list[str] = []
    broken_tables: list[str] = []
    db_errors: list[str] = []

    for db_path in db_files:
        _lk = get_db_lock(db_path)
        _lk.acquire()
        con = None
        try:
            try:
                con = duckdb.connect(str(db_path))
            except Exception:
                con = duckdb.connect(str(db_path), read_only=True)

            rows = con.execute("SHOW TABLES").fetchall()
            t_names = [str(r[0]) for r in rows]
            total_tables += len(t_names)
            db_info = {"file": db_path.name, "size_kb": round(db_path.stat().st_size / 1024, 1), "tables": []}

            SYS_EMPTY_OK = {
                "user_rules", "entity_aliases", "app_settings", "diagnostics_log",
                "chat_history", "processed_files", "tabular_catalog", "smart_teachers_exploded",
                "entity_brain_config", "entity_brain_history", "_meta_teacher_sig",
            }
            for tname in t_names:
                safe_t = tname.replace('"', '""')
                try:
                    cnt = con.execute(f'SELECT COUNT(*) FROM "{safe_t}"').fetchone()[0]
                    tl = tname.lower()
                    if cnt == 0 and tl not in SYS_EMPTY_OK and not tl.startswith("_"):
                        empty_tables.append(tname)
                    if collect_schema:
                        cols = con.execute(f'DESCRIBE "{safe_t}"').fetchall()
                        db_info["tables"].append(
                            {
                                "name": tname,
                                "rows": int(cnt),
                                "columns": [{"name": str(c[0]), "type": str(c[1])} for c in cols],
                            }
                        )
                except Exception as t_exc:
                    broken_tables.append(f"{tname} ({t_exc})")
                    if collect_schema:
                        db_info["tables"].append({"name": tname, "error": str(t_exc)})
            schemas.append(db_info)
        except Exception as exc:
            db_errors.append(f"{db_path.name}: {exc}")
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass
            try:
                _lk.release()
            except Exception:
                pass

    if db_errors or broken_tables:
        msg = "خطا در خواندن پایگاه‌داده: " + " | ".join((db_errors + broken_tables)[:3])
        return (
            {
                "id": "duckdb",
                "title": "پایگاه‌داده تحلیلی (DuckDB)",
                "status": "error",
                "detail": redact_sensitive(msg),
            },
            schemas,
        )

    if total_tables == 0:
        return (
            {
                "id": "duckdb",
                "title": "پایگاه‌داده تحلیلی (DuckDB)",
                "status": "warning",
                "detail": f"{len(db_files)} فایل پایگاه‌داده سالم است اما هنوز جدولی در آن ثبت نشده است.",
            },
            schemas,
        )

    if empty_tables:
        return (
            {
                "id": "duckdb",
                "title": "پایگاه‌داده تحلیلی (DuckDB)",
                "status": "warning",
                "detail": f"{total_tables} جدول بررسی شد؛ {len(empty_tables)} جدول خالی (بدون ردیف) وجود دارد.",
            },
            schemas,
        )

    return (
        {
            "id": "duckdb",
            "title": "پایگاه‌داده تحلیلی (DuckDB)",
            "status": "healthy",
            "detail": f"سالم و آماده — {total_tables} جدول آماری بدون خطا بررسی شد.",
        },
        schemas,
    )


def _text_has_api_key(txt: str) -> bool:
    if not txt:
        return False
    if re.search(r"AIza[0-9A-Za-z\-_]{20,}", txt):
        return True
    if re.search(r'(?i)"(?:gemini_?api_?key|google_?api_?key|api_?key|openai_?api_?key|openrouter_?api_?key)"\s*:\s*"[^"\s]{14,}"', txt):
        return True
    if re.search(r"(?i)(?:GEMINI_API_KEY|GOOGLE_API_KEY|API_KEY)\s*=\s*['\"]?[^\s'\"#]{14,}", txt):
        return True
    return False


def _detect_api_key_configured() -> bool:
    # A. Environment variables
    for env_k, env_v in os.environ.items():
        if any(tok in env_k.upper() for tok in ("GEMINI", "GOOGLE_API", "GENAI", "OPENROUTER")):
            if len((env_v or "").strip()) >= 14:
                return True

    # B. Runtime js_api settings / initialized AI client (if app is running)
    if _JS_API_REF is not None:
        for meth in ("get_settings", "load_settings", "get_config", "get_ai_status"):
            fn = getattr(_JS_API_REF, meth, None)
            if callable(fn):
                try:
                    res = fn()
                    if _text_has_api_key(json.dumps(res, ensure_ascii=False, default=str)):
                        return True
                    if isinstance(res, dict) and (res.get("has_key") or res.get("connected") or res.get("gemini_ready")):
                        return True
                except Exception:
                    pass
        for attr in ("api_key", "gemini_api_key", "gemini_key", "client", "ai", "agent", "assistant", "llm"):
            val = getattr(_JS_API_REF, attr, None)
            if isinstance(val, str) and len(val.strip()) >= 14:
                return True
            if val is not None and not isinstance(val, (str, int, float, bool, list, dict)):
                for sub in ("api_key", "gemini_api_key", "_api_key", "client", "model"):
                    sv = getattr(val, sub, None)
                    if isinstance(sv, str) and len(sv.strip()) >= 14:
                        return True
                    if sv is not None and sub == "client":
                        return True

    # C. Local project files (data/, root/, src/ config files) & AppData folders
    p = _paths()
    search_dirs = [p["data"], p["root"]]
    for env_dir in ("LOCALAPPDATA", "APPDATA"):
        base_ad = os.environ.get(env_dir)
        if base_ad:
            for sub in ("eHadiPanel", "ImamHadi"):
                cand_d = Path(base_ad) / sub
                if cand_d.exists():
                    search_dirs.append(cand_d)

    exts = {".json", ".env", ".ini", ".cfg", ".toml", ".yaml", ".yml", ".txt"}
    for folder in search_dirs:
        if not folder.exists():
            continue
        for fp in folder.rglob("*"):
            if not fp.is_file():
                continue
            if any(part in {"venv", ".venv", "__pycache__", "node_modules", "logs", "dist", "build", "lancedb"} for part in fp.parts):
                continue
            if fp.name == ".env" or fp.suffix.lower() in exts:
                if fp.stat().st_size > 2 * 1024 * 1024:
                    continue
                try:
                    if _text_has_api_key(fp.read_text(encoding="utf-8", errors="ignore")):
                        return True
                except Exception:
                    pass

    # Check src/ config/ai python files for hardcoded or loaded key / proxy config
    src_dir = p["root"] / "src"
    if src_dir.exists():
        for fp in src_dir.rglob("*.py"):
            if fp.name == "diagnostics.py" or fp.stat().st_size > 512 * 1024:
                continue
            try:
                if _text_has_api_key(fp.read_text(encoding="utf-8", errors="ignore")):
                    return True
            except Exception:
                pass

    # D. SQLite / DuckDB settings tables if any
    for db_fp in p["data"].rglob("*.db") if p["data"].exists() else []:
        try:
            import sqlite3
            con = sqlite3.connect(str(db_fp))
            tbls = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for t in tbls:
                if any(k in t.lower() for k in ("setting", "config", "pref", "key")):
                    rows = con.execute(f'SELECT * FROM "{t}" LIMIT 50').fetchall()
                    if _text_has_api_key(str(rows)):
                        con.close()
                        return True
            con.close()
        except Exception:
            pass

    return False

def _check_ai_connectivity(check_network: bool = False) -> dict:
    has_key = _detect_api_key_configured()
    if not has_key:
        return {
            "id": "ai_config",
            "title": "هسته هوش مصنوعی (Gemini)",
            "status": "warning",
            "detail": "کلید API در تنظیمات یا فایل پیکربندی پیدا نشد؛ بخش دستیار هوشمند نیاز به کلید دارد.",
        }

    if not check_network:
        return {
            "id": "ai_config",
            "title": "هسته هوش مصنوعی (Gemini)",
            "status": "healthy",
            "detail": "کلید API تنظیم شده است (برای تست اتصال اینترنتی، دکمه «تست سلامت کامل» را بزنید).",
        }

    try:
        sock = socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=3.0)
        sock.close()
        return {
            "id": "ai_config",
            "title": "هسته هوش مصنوعی (Gemini)",
            "status": "healthy",
            "detail": "کلید API تنظیم شده و اتصال شبکه به سرور Gemini برقرار است.",
        }
    except Exception:
        return {
            "id": "ai_config",
            "title": "هسته هوش مصنوعی (Gemini)",
            "status": "warning",
            "detail": "کلید API تنظیم شده اما اتصال به سرور Gemini برقرار نشد (احتمالاً اینترنت یا تحریم‌شکن قطع است).",
        }


def _check_storage_and_lancedb() -> tuple[dict, dict]:
    p = _paths()
    # 1. Storage & write permission
    try:
        probe = p["logs"] / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        usage = shutil.disk_usage(str(p["root"]))
        free_gb = round(usage.free / (1024**3), 2)
        if free_gb < 1.0:
            storage_check = {
                "id": "storage",
                "title": "فضای ذخیره‌سازی و پوشه داده‌ها",
                "status": "warning",
                "detail": f"پوشه داده‌ها قابل نوشتن است اما فضای خالی درایو کم است ({free_gb} گیگابایت).",
            }
        else:
            storage_check = {
                "id": "storage",
                "title": "فضای ذخیره‌سازی و پوشه داده‌ها",
                "status": "healthy",
                "detail": f"دسترسی کامل برقرار است — {free_gb} گیگابایت فضای خالی در دسترس.",
            }
    except Exception as exc:
        storage_check = {
            "id": "storage",
            "title": "فضای ذخیره‌سازی و پوشه داده‌ها",
            "status": "error",
            "detail": f"عدم دسترسی نوشتن در پوشه داده‌ها: {exc}",
        }

    # 2. LanceDB / Vector directory
    lance_dirs = [
        d for d in (p["data"] / "lancedb", p["data"] / "lance_db", p["data"] / "vectors", p["root"] / "lancedb")
        if d.exists() and d.is_dir()
    ]
    if lance_dirs:
        lance_check = {
            "id": "lancedb",
            "title": "موتور جستجوی اسناد (LanceDB)",
            "status": "healthy",
            "detail": f"پوشه نمایه اسناد سالم و قابل دسترس است ({lance_dirs[0].name}).",
        }
    else:
        lance_check = {
            "id": "lancedb",
            "title": "موتور جستجوی اسناد (LanceDB)",
            "status": "healthy",
            "detail": "آماده نمایه‌سازی (پس از بارگذاری اسناد متنی ساخته می‌شود).",
        }

    return storage_check, lance_check


def _read_tail_lines(path: Path, max_lines: int = 300) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return [redact_sensitive(l) for l in lines[-max_lines:]]
    except Exception:
        return []


def _check_recent_errors() -> dict:
    p = _paths()
    cutoff = _dt.datetime.now() - _dt.timedelta(hours=24)
    py_err = 0
    js_err = 0

    for line in _read_tail_lines(p["app_log"], 250):
        if "| ERROR |" in line or "Unhandled " in line:
            try:
                dt = _dt.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                if dt >= cutoff:
                    py_err += 1
            except Exception:
                pass

    for line in _read_tail_lines(p["fe_log"], 250):
        if " | " in line:
            try:
                dt = _dt.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                if dt >= cutoff:
                    js_err += 1
            except Exception:
                pass

    total = py_err + js_err
    if total == 0:
        return {
            "id": "recent_errors",
            "title": "ثبت خطاهای ۲۴ ساعت اخیر",
            "status": "healthy",
            "detail": "هیچ خطای پیش‌بینی‌نشده‌ای در ۲۴ ساعت اخیر ثبت نشده است.",
        }
    return {
        "id": "recent_errors",
        "title": "ثبت خطاهای ۲۴ ساعت اخیر",
        "status": "warning",
        "detail": f"{total} خطا در ۲۴ ساعت اخیر ثبت شده ({py_err} پایتون، {js_err} رابط کاربری). در صورت بروز مشکل، فایل گزارش خطا را ارسال کنید.",
    }


def run_health_check(check_network: bool = False) -> dict:
    storage_chk, lance_chk = _check_storage_and_lancedb()
    duck_chk, _ = _audit_duckdb(collect_schema=False)
    ai_chk = _check_ai_connectivity(check_network=bool(check_network))
    err_chk = _check_recent_errors()

    dup_alerts = []
    try:
        dup_alerts = detect_duplicate_files()
    except Exception:
        pass
    dup_detail = (
        "فایل تکراری یا هم‌نسخه یافت نشد."
        if not dup_alerts
        else f"{len(dup_alerts)} مورد فایل مشابه یا تکراری شناسایی شد: "
        + " | ".join(" و ".join(a.get("files") or []) for a in dup_alerts[:3])
    )
    dup_chk = {
        "id": "duplicate_files",
        "title": "سلامت و عدم تکرار فایل‌ها",
        "status": "healthy" if not dup_alerts else "warning",
        "detail": dup_detail,
    }
    checks = [storage_chk, duck_chk, lance_chk, ai_chk, dup_chk, err_chk]
    statuses = [c["status"] for c in checks]
    if "error" in statuses:
        overall = "error"
        summary = "یک یا چند خطای فنی شناسایی شد؛ جزئیات را بررسی کنید."
    elif "warning" in statuses:
        overall = "warning"
        summary = "سامانه فعال است اما مواردی نیاز به توجه دارد."
    else:
        overall = "healthy"
        summary = "همه زیرسیستم‌ها کاملاً سالم و آماده کار هستند."

    return {
        "ok": True,
        "status": overall,
        "summary": summary,
        "app_version": APP_VERSION,
        "timestamp": format_jalali_now(include_time=True, fa_digits=True),
        "timestamp_iso": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "checks": checks,
        "duplicate_files": dup_alerts,
    }


def _fmt_log_ts(raw_line: str) -> str:
    return re.sub(
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:[.,]\d{1,6})?",
        lambda m: iso_to_jalali(m.group(0)[:16]),
        raw_line,
    )


def get_recent_errors(limit: int = 12) -> dict:
    p = _paths()
    items: list[dict] = []
    py_lines = _read_tail_lines(p["app_log"], 300)
    ts_rx = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
    i = 0
    while i < len(py_lines):
        line = py_lines[i]
        if "| ERROR |" in line or "| WARNING |" in line:
            header = _fmt_log_ts(line)
            detail_msg = ""
            if "Traceback (most recent call last)" in line:
                j = i + 1
                last_non_empty = ""
                while j < len(py_lines) and not ts_rx.match(py_lines[j]):
                    s = py_lines[j].strip()
                    if s:
                        last_non_empty = s
                    j += 1
                if last_non_empty:
                    detail_msg = last_non_empty
                    header = header.replace("Traceback (most recent call last):", "").strip()
                i = j
            else:
                i += 1
            full_txt = f"{header} {detail_msg}".strip()
            items.append({"source": "هسته برنامه", "text": full_txt[:320]})
        else:
            i += 1

    for line in _read_tail_lines(p["fe_log"], 200):
        if line.strip():
            items.append({"source": "رابط کاربری", "text": _fmt_log_ts(line)[:320]})

    items = items[-max(1, int(limit)) :]
    items.reverse()
    return {"ok": True, "count": len(items), "items": items}


def clear_error_logs() -> dict:
    """Clears historical error logs cleanly so resolved warnings reset to healthy."""
    try:
        p = _paths()
        with _FE_LOCK:
            for key in ("app_log", "fe_log"):
                fp = p.get(key)
                if fp and fp.exists():
                    try:
                        fp.write_text("", encoding="utf-8")
                    except Exception:
                        pass
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _collect_pkg_versions() -> dict[str, str]:
    pkgs = ["pywebview", "duckdb", "lancedb", "pandas", "openpyxl", "google-genai", "google-generativeai", "Pillow"]
    out: dict[str, str] = {}
    for name in pkgs:
        try:
            out[name] = _meta.version(name)
        except Exception:
            out[name] = "not-installed"
    return out


def export_diagnostic_bundle() -> dict:
    try:
        p = _paths()
        health = run_health_check(check_network=True)
        _, schemas = _audit_duckdb(collect_schema=True)

        desktop = Path.home() / "Desktop"
        out_dir = desktop if desktop.exists() else p["diag"]
        out_dir.mkdir(parents=True, exist_ok=True)

        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = out_dir / f"eHadiPanel_Diagnostic_{stamp}.zip"

        sys_report = {
            "app_version": APP_VERSION,
            "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "frozen": bool(getattr(sys, "frozen", False)),
            "packages": _collect_pkg_versions(),
            "health_check": health,
        }

        readme_fa = (
            "بسته گزارش خطای فنی سامانه eHadiPanel Beta 0.2\n"
            "==============================================\n"
            f"نسخه برنامه: {APP_VERSION}\n"
            f"زمان تهیه گزارش: {health['timestamp']}\n\n"
            "حفظ حریم خصوصی:\n"
            "- هیچ‌گونه متن سند، نام شرکت‌کنندگان، فایل اکسل یا ردیف اطلاعاتی داخل این بسته وجود ندارد.\n"
            "- کلیدهای API و مسیر نام کاربری ویندوز به‌صورت خودکار حذف و سانسور شده‌اند.\n"
            "- تنها خطاهای فنی، نسخه کتابخانه‌ها و ساختار کلی ستون‌ها برای عیب‌یابی سریع قرار داده شده است.\n"
        )

        py_lines = _read_tail_lines(p["app_log"], 600)
        fe_lines = _read_tail_lines(p["fe_log"], 400)

        with zipfile.ZipFile(str(zip_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README_SUPPORT.txt", readme_fa)
            zf.writestr("system_report.json", json.dumps(sys_report, ensure_ascii=False, indent=2))
            zf.writestr("db_schema_only.json", json.dumps(schemas, ensure_ascii=False, indent=2))
            zf.writestr("python_errors.log", "\n".join(py_lines) if py_lines else "(No Python errors logged)")
            zf.writestr("frontend_errors.log", "\n".join(fe_lines) if fe_lines else "(No frontend JS errors logged)")

        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", f"/select,{zip_path}"])
        except Exception:
            pass

        return {
            "ok": True,
            "filename": zip_path.name,
            "path": str(zip_path),
            "size_kb": round(zip_path.stat().st_size / 1024, 1),
        }
    except Exception as exc:
        logging.getLogger("eHadiPanel.Diagnostics").exception("Failed to export diagnostic bundle")
        return {"ok": False, "error": redact_sensitive(str(exc))}


def _bind_api_methods(js_api) -> None:
    global _JS_API_REF
    if js_api is None:
        return
    _JS_API_REF = js_api
    cls = type(js_api)
    methods = {
        "log_frontend_error": lambda self, payload=None: log_frontend_error(payload),
        "run_health_check": lambda self, check_network=False: run_health_check(check_network),
        "export_diagnostic_bundle": lambda self: export_diagnostic_bundle(),
        "get_recent_errors": lambda self, limit=12: get_recent_errors(limit),
        "clear_error_logs": lambda self: clear_error_logs(),
    }
    for name, fn in methods.items():
        if hasattr(js_api, name):
            continue
        try:
            setattr(cls, name, fn)
        except Exception:
            try:
                setattr(js_api, name, types.MethodType(fn, js_api))
            except Exception:
                pass


def install_diagnostics(app_version: str = "Beta 0.2") -> None:
    global APP_VERSION, _INSTALLED
    APP_VERSION = app_version
    _setup_logging()
    _install_excepthooks()
    if _INSTALLED:
        return
    _INSTALLED = True

    try:
        import webview  # type: ignore

        orig_create = webview.create_window
        if not getattr(orig_create, "_eh_diag_wrapped", False):
            def _wrapped_create_window(*args, **kwargs):
                api_obj = kwargs.get("js_api")
                if api_obj is None and len(args) >= 4:
                    api_obj = args[3]
                if api_obj is not None:
                    _bind_api_methods(api_obj)
                return orig_create(*args, **kwargs)

            _wrapped_create_window._eh_diag_wrapped = True  # type: ignore[attr-defined]
            webview.create_window = _wrapped_create_window
    except Exception as exc:
        logging.getLogger("eHadiPanel.Diagnostics").warning("Could not hook webview.create_window: %s", exc)
