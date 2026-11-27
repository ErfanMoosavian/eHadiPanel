# _EHADI_FROZEN_PATCHED
import os as _os, sys as _sys
_os.environ.setdefault("RUST_LOG", "error")
from pathlib import Path as _Path
if getattr(_sys, 'frozen', False):
    _APP_DIR = _Path(_sys.executable).resolve().parent
    _os.chdir(str(_APP_DIR))
    _os.environ['EHADI_BUNDLE_DIR'] = str(_Path(getattr(_sys, '_MEIPASS', _APP_DIR)))
    _os.environ['EHADI_APP_DIR'] = str(_APP_DIR)

# _EHADI_DPI_AWARENESS_V2 (crisp 1:1 native rendering on Windows High-DPI displays)
if _os.name == "nt":
    try:
        import ctypes as _ct_dpi
        try:
            _ct_dpi.windll.user32.SetProcessDpiAwarenessContext(_ct_dpi.c_void_p(-4))
        except Exception:
            try:
                _ct_dpi.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    _ct_dpi.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
    except Exception:
        pass

# _EHADI_PROCESS_SPLASH_FIRST (launch splash BEFORE heavy imports for instant appearance)
import os as _os, sys as _sys, subprocess as _subprocess, tempfile as _tempfile, threading as _threading, time as _time
from pathlib import Path as _Path

if getattr(_sys, "frozen", False):
    _APP_DIR = _Path(_sys.executable).resolve().parent
    _os.chdir(str(_APP_DIR))
    _os.environ["EHADI_BUNDLE_DIR"] = str(_Path(getattr(_sys, "_MEIPASS", _APP_DIR)))
    _os.environ["EHADI_APP_DIR"] = str(_APP_DIR)

if any(str(a).strip().lower() == "--ehadi-splash" for a in _sys.argv):
    _sp_candidates = [
        _Path(getattr(_sys, "_MEIPASS", "")) / "build" if getattr(_sys, "_MEIPASS", None) else None,
        _Path(_sys.executable).resolve().parent / "build" if getattr(_sys, "frozen", False) else None,
        _Path(__file__).resolve().parent / "build",
        _Path("build").resolve(),
    ]
    for _cand in _sp_candidates:
        if _cand and (_cand / "splash_runner.py").exists():
            if str(_cand) not in _sys.path:
                _sys.path.insert(0, str(_cand))
            break
    import splash_runner as _sr
    _sr.main()
    _sys.exit(0)

_SPLASH_READY_FILE = _Path(_tempfile.gettempdir()) / f"ehadi_splash_{_os.getpid()}.stage"
_SPLASH_DONE_FILE = _Path(_tempfile.gettempdir()) / f"ehadi_splash_{_os.getpid()}.done"
_SPLASH_SPAWNED = False

def _set_splash_stage(stage: str) -> None:
    try:
        _SPLASH_READY_FILE.write_text(str(stage), encoding="utf-8")
    except Exception:
        pass

def _launch_ehadi_splash_proc() -> None:
    global _SPLASH_SPAWNED
    try:
        _SPLASH_DONE_FILE.unlink(missing_ok=True)
        _set_splash_stage("0")
        _sp_args = ["--ready-file", str(_SPLASH_READY_FILE), "--parent-pid", str(_os.getpid())]
        if getattr(_sys, "frozen", False):
            _child_env = dict(_os.environ)
            _child_env.pop("PYINSTALLER_RESET_ENVIRONMENT", None)
            _child_env.pop("PYINSTALLER_STRICT_PACKED_LIBS", None)
            # Run child splash from app directory without CREATE_NO_WINDOW suppressing GUI
            _subprocess.Popen(
                [_sys.executable, "--ehadi-splash", *_sp_args],
                cwd=str(_Path(_sys.executable).resolve().parent),
                env=_child_env,
            )
            _SPLASH_SPAWNED = True
        else:
            _runner = _Path(__file__).resolve().parent / "build" / "splash_runner.py"
            if _runner.exists():
                _subprocess.Popen(
                    [_sys.executable, str(_runner), *_sp_args],
                    cwd=str(_Path(__file__).resolve().parent),
                )
                _SPLASH_SPAWNED = True
    except Exception:
        _SPLASH_SPAWNED = False

if not _os.environ.get("EHADI_WEB"):  # web edition: no desktop splash
    _launch_ehadi_splash_proc()

# _EH_DIAGNOSTICS_V43_HOOK
try:
    from src.core.diagnostics import install_diagnostics as _eh_install_diag
    _eh_install_diag(app_version="v0.4.0-beta")
except Exception:
    pass
# _EH_MEMORY_ENGINE_V45_HOOK
try:
    from src.core.memory_engine import install_memory_engine as _eh_install_mem
    _eh_install_mem()
except Exception:
    pass

def _apply_win32_taskbar_icon():
    try:
        import ctypes as _ct
        _u32 = _ct.windll.user32
        _u32.GetWindowLongW.argtypes = [_ct.c_void_p, _ct.c_int]
        _u32.GetWindowLongW.restype = _ct.c_long
        _u32.SetWindowLongW.argtypes = [_ct.c_void_p, _ct.c_int, _ct.c_long]
        _u32.SetWindowLongW.restype = _ct.c_long
        _u32.SetWindowPos.argtypes = [_ct.c_void_p, _ct.c_void_p, _ct.c_int, _ct.c_int, _ct.c_int, _ct.c_int, _ct.c_uint]
        _u32.SetWindowPos.restype = _ct.c_bool

        _ct.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ImamHadi.eHadiPanel.Beta.02")
        ico = _Path(getattr(_sys, "_MEIPASS", ".")) / "build" / "eHadiPanel.ico"
        if not ico.exists():
            ico = _Path("build/eHadiPanel.ico").resolve()
        hicon_big = _u32.LoadImageW(0, str(ico), 1, 256, 256, 0x0010) if ico.exists() else 0
        hicon_sm = _u32.LoadImageW(0, str(ico), 1, 32, 32, 0x0010 | 0x0040) if ico.exists() else 0

        GWL_STYLE = -16
        WS_MINIMIZEBOX = 0x00020000
        WS_SYSMENU = 0x00080000
        WS_CAPTION = 0x00C00000
        SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0020

        pid = _os.getpid()
        for _ in range(40):
            _time.sleep(0.25)
            found = []
            def _enum_cb(hwnd, lparam):
                if _u32.IsWindowVisible(hwnd):
                    wpid = _ct.c_ulong()
                    _u32.GetWindowThreadProcessId(hwnd, _ct.byref(wpid))
                    if wpid.value == pid:
                        found.append(hwnd)
                return True
            WNDENUMPROC = _ct.WINFUNCTYPE(_ct.c_bool, _ct.c_void_p, _ct.c_void_p)
            _u32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
            for hw in found:
                # Apply crisp taskbar icon
                if hicon_big:
                    _u32.SendMessageW(hw, 0x0080, 1, hicon_big)
                if hicon_sm:
                    _u32.SendMessageW(hw, 0x0080, 0, hicon_sm)
                # Enable click-on-taskbar-icon to minimize/restore while keeping window 100% frameless
                st = _u32.GetWindowLongW(hw, GWL_STYLE)
                new_st = (st | WS_MINIMIZEBOX | WS_SYSMENU) & ~WS_CAPTION
                if new_st != st:
                    _u32.SetWindowLongW(hw, GWL_STYLE, new_st)
                    _u32.SetWindowPos(hw, 0, 0, 0, 0, 0, SWP_FLAGS)
            if found:
                break
    except Exception:
        pass

if not _os.environ.get("EHADI_WEB"):
    _threading.Thread(target=_apply_win32_taskbar_icon, daemon=True).start()

import ctypes
import base64
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
try:
    import webview
except ImportError:  # the web edition does not need pywebview (the native dialogs are replaced by uploads)
    if not os.environ.get("EHADI_WEB"):
        raise
    from types import SimpleNamespace as _NS
    webview = _NS(FileDialog=_NS(OPEN=10, SAVE=30, FOLDER=20), OPEN_DIALOG=10, SAVE_DIALOG=30)
os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--force-high-performance-gpu --enable-gpu-rasterization --enable-zero-copy --ignore-gpu-blocklist",
)


from src.ai.agent import InstitutionalAIAgent
from src.analytics.bi_engine import BIDashboardEngine
from src.analytics.executive_engine import ExecutiveAnalyticsEngine
try:
    from src.voice.voice_copilot import listen_and_execute_voice, process_voice_command, stop_active_recording
except ImportError:  # voice packages are optional (requirements-voice.txt); the web edition blocks voice methods anyway
    if not os.environ.get("EHADI_WEB"):
        raise
    def _no_voice(*a, **k):
        return {"ok": False, "error": "voice packages are not installed"}
    listen_and_execute_voice = process_voice_command = stop_active_recording = _no_voice
from src.reports.report_studio import (
    export_analytics_excel,
    export_attendance_sheet_pdf,
    export_official_docx,
    export_official_pdf,
    get_logo_data_uri,
    install_font_file,
    install_logo_file,
    load_branding,
    save_branding,
)
from src.core.config import BASE_DIR, Config
from src.core.safety import clear_audit_logs, create_snapshot_backup, delete_decision, get_recent_audits, load_decisions, log_audit, save_decision
from src.ingestion.parser import DocumentIngestionEngine


class AppAPI:
    def __init__(self):
        self._window = None
        self._maximized = False
        self.engine = DocumentIngestionEngine()
        self.agent = InstitutionalAIAgent()
        self.bi = BIDashboardEngine()
        self.exec_engine = ExecutiveAnalyticsEngine()
        self._bi_cache = None
        self._exec_cache: dict[str, dict] = {}
        self._exec_cache_lock = threading.Lock()
        self._warmed_up = False

    def _invalidate_caches(self):
        self._bi_cache = None
        with self._exec_cache_lock:
            self._exec_cache.clear()

    def set_window(self, window):
        self._window = window

    def minimize(self):
        if self._window:
            self._window.minimize()

    def close(self):
        if self._window:
            self._window.destroy()

    def get_dashboard_data(self):
        return self.engine.get_dashboard_stats()

    def get_bi_analytics(self, force: bool = False):
        if force or self._bi_cache is None:
            self._bi_cache = self.bi.get_analytics()
        return self._bi_cache

    def get_bi_table_data(self, table_name: str):
        return self.bi.get_table_dynamic_data(table_name)

    def save_finance_category_rule(self, item_key: str, category: str):
        from src.core.memory_engine import save_finance_category_rule as _save_fcr
        res = _save_fcr(item_key, category)
        if res.get("ok"):
            self._invalidate_caches()
        return res

    def scan_documents(self):
        self._invalidate_caches()
        data = self.engine.ingest_all()
        self.agent.invalidate_cache()
        def _refresh_after_scan():
            try:
                from src.core.memory_engine import rebuild_clean_teacher_layer
                rebuild_clean_teacher_layer(force=True)
            except Exception:
                pass
            self.agent.warmup()
        threading.Thread(target=_refresh_after_scan, daemon=True).start()
        try:
            log_audit("docs_scanned", "docs", "ok", {"files": data.get("total_files", 0), "tables": data.get("total_tables", 0)})
        except Exception:
            pass
        return data

    def open_raw_docs_folder(self):
        Config.ensure_directories()
        os.startfile(str(Config.RAW_DOCS_DIR))
        return {"ok": True}

    def open_file_path(self, file_path: str):
        try:
            p = Path(file_path)
            if p.exists():
                os.startfile(str(p))
                return {"ok": True}
            return {"ok": False, "error": "فایل در مسیر مشخص‌شده یافت نشد."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_dropped_chunk(self, file_name: str, chunk_b64: str, is_first: bool):
        try:
            Config.ensure_directories()
            safe_name = Path(str(file_name or "").replace("\\", "/")).name.strip()
            if not safe_name or safe_name in (".", ".."):
                return {"ok": False, "error": "نام فایل نامعتبر است."}
            dest = (Config.RAW_DOCS_DIR / safe_name).resolve()
            if dest.parent != Config.RAW_DOCS_DIR.resolve():
                return {"ok": False, "error": "مسیر فایل مجاز نیست."}
            mode = "wb" if is_first else "ab"
            raw_bytes = base64.b64decode(chunk_b64) if chunk_b64 else b""
            with open(dest, mode) as f:
                f.write(raw_bytes)
            return {"ok": True, "file_name": safe_name}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def add_files_dialog(self):
        if not self._window:
            return {"copied": 0, "error": "پنجره برنامه هنوز آماده نیست."}
        try:
            if hasattr(webview, "FileDialog"):
                dialog_type = webview.FileDialog.OPEN
            else:
                dialog_type = getattr(webview, "OPEN_DIALOG", 10)

            file_types = (
                "Supported Documents (*.pdf;*.docx;*.pptx;*.xlsx;*.xls;*.csv;*.accdb;*.mdb)",
                "All Files (*.*)",
            )
            selected = self._window.create_file_dialog(
                dialog_type, allow_multiple=True, file_types=file_types
            )
            if not selected:
                return {"copied": 0}

            Config.ensure_directories()
            copied = 0
            for src_path in selected:
                p = Path(src_path)
                if p.is_file():
                    dest = Config.RAW_DOCS_DIR / p.name
                    if p.resolve() != dest.resolve():
                        shutil.copy2(p, dest)
                    copied += 1
            return {"copied": copied}
        except Exception as exc:
            return {"copied": 0, "error": str(exc)}

    def get_chat_history(self):
        return self.agent.get_chat_history()

    def clear_chat_history(self):
        return self.agent.clear_chat_history()

    def ask_ai(self, question: str, mode: str = "analyst", route_mode: str = "auto", length_mode: str = "concise"):
        return self.agent.ask(question, mode=mode, route_mode=route_mode, length_mode=length_mode)

    def ask_ai_stream(self, stream_id: str, question: str, mode: str = "analyst", route_mode: str = "auto", length_mode: str = "concise"):
        token_buf: list[str] = []
        buf_lock = threading.Lock()
        last_flush = [0.0]

        def push_js(ev_type: str, payload: dict):
            if not self._window:
                return
            packet = {"stream_id": stream_id, "type": ev_type, "data": payload}
            js_literal = (
                json.dumps(packet, ensure_ascii=False)
                .replace("\u2028", "\\u2028")
                .replace("\u2029", "\\u2029")
            )
            try:
                self._window.evaluate_js(
                    f"window.__onAiStreamEvent && window.__onAiStreamEvent({js_literal})"
                )
            except Exception:
                pass

        def flush_tokens():
            with buf_lock:
                if not token_buf:
                    return
                chunk = "".join(token_buf)
                token_buf.clear()
                last_flush[0] = time.perf_counter()
            push_js("token", {"text": chunk})

        def emit_to_ui(ev_type: str, payload: dict):
            if ev_type == "token":
                txt = payload.get("text", "")
                if not txt:
                    return
                should_flush = False
                with buf_lock:
                    token_buf.append(txt)
                    if (time.perf_counter() - last_flush[0]) >= 0.022 or len(token_buf) >= 3:
                        should_flush = True
                if should_flush:
                    flush_tokens()
            else:
                flush_tokens()
                push_js(ev_type, payload)

        threading.Thread(
            target=self.agent.ask_stream,
            args=(question, mode, emit_to_ui, route_mode, length_mode),
            daemon=True,
        ).start()
        return {"ok": True, "stream_id": stream_id}

    def get_chunk_preview(self, chunk_id: str):
        return self.agent.get_chunk_by_id(chunk_id)

    def export_table_excel(self, table_data: dict):
        if not self._window:
            return {"ok": False, "error": "پنجره آماده نیست."}
        try:
            if hasattr(webview, "FileDialog"):
                save_dialog = webview.FileDialog.SAVE
            else:
                save_dialog = getattr(webview, "SAVE_DIALOG", 30)

            clean_name = re.sub(r'[\\/*?:"<>|]', '', str(table_data.get("title") or "گزارش_مؤسسه")).strip()
            stamp = datetime.now().strftime("%Y%m%d_%H%M")
            default_filename = f"{clean_name[:40]}_{stamp}.xlsx"

            result = self._window.create_file_dialog(
                save_dialog,
                directory=str(BASE_DIR),
                save_filename=default_filename,
                file_types=("Excel Workbook (*.xlsx)",),
            )
            if not result:
                return {"ok": False, "cancelled": True}

            target = result[0] if isinstance(result, (list, tuple)) else result
            dest = Path(str(target))
            if dest.suffix.lower() != ".xlsx":
                dest = dest.with_suffix(".xlsx")

            saved_path = self.agent.export_table_to_excel(table_data, dest)
            return {"ok": True, "path": saved_path}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_settings(self):
        key = Config.GEMINI_API_KEY
        if key == "کلید_API_خود_را_اینجا_بگذارید":
            key = ""
        return {"api_key": key, "model": Config.GEMINI_MODEL}

    def save_settings(self, api_key: str, model: str):
        content = f'GEMINI_API_KEY="{api_key}"\nGEMINI_MODEL="{model}"\n'
        try:
            Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            (Config.DATA_DIR / ".env").write_text(content, encoding="utf-8")
        except Exception:
            pass
        try:
            (BASE_DIR / ".env").write_text(content, encoding="utf-8")
        except Exception:
            pass
        os.environ["GEMINI_API_KEY"] = api_key
        os.environ["GEMINI_MODEL"] = model
        Config.GEMINI_API_KEY = api_key
        Config.GEMINI_MODEL = model
        self.agent.reset_client()
        return {"ok": True}

    def test_gemini_connection(self, api_key: str, model: str):
        return self.agent.test_connection(api_key=api_key, model=model)



    # --- فاز ۵: تنظیمات سربرگ، لوگو و خروجی رسمی Word / PDF ---
    def get_branding_settings(self):
        b = load_branding()
        return {"ok": True, "branding": b, "logo_data_uri": get_logo_data_uri(b.get("logo_path", ""))}

    def save_branding_settings(self, payload: dict):
        b = save_branding(payload or {})
        return {"ok": True, "branding": b, "logo_data_uri": get_logo_data_uri(b.get("logo_path", ""))}

    def select_logo_dialog(self):
        if not self._window:
            return {"ok": False, "error": "پنجره آماده نیست."}
        try:
            dialog_type = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else getattr(webview, "OPEN_DIALOG", 10)
            selected = self._window.create_file_dialog(
                dialog_type, allow_multiple=False, file_types=("Logo Images (*.png;*.jpg;*.jpeg;*.webp)",)
            )
            if not selected:
                return {"ok": False, "cancelled": True}
            return install_logo_file(str(selected[0]))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    
    def select_font_dialog(self, font_label: str = ""):
        if not self._window:
            return {"ok": False, "error": "پنجره آماده نیست."}
        try:
            dialog_type = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else getattr(webview, "OPEN_DIALOG", 10)
            selected = self._window.create_file_dialog(
                dialog_type, allow_multiple=False, file_types=("Font Files (*.ttf;*.otf;*.woff2)",)
            )
            if not selected:
                return {"ok": False, "cancelled": True}
            return install_font_file(str(selected[0]), custom_name=font_label or None)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def export_report_docx(self, payload: dict):
        if not self._window:
            return {"ok": False, "error": "پنجره آماده نیست."}
        try:
            save_dialog = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else getattr(webview, "SAVE_DIALOG", 30)
            clean_name = re.sub(r'[\\/*?:"<>|]', '', str((payload or {}).get("title") or "گزارش_رسمی_مؤسسه")).strip()
            default_fn = f"{clean_name[:40]}_{datetime.now().strftime('%Y%m%d_%H%M')}.docx"
            result = self._window.create_file_dialog(
                save_dialog, directory=str(BASE_DIR), save_filename=default_fn, file_types=("Word Document (*.docx)",)
            )
            if not result:
                return {"ok": False, "cancelled": True}
            target = Path(str(result[0] if isinstance(result, (list, tuple)) else result))
            if target.suffix.lower() != ".docx":
                target = target.with_suffix(".docx")
            saved = export_official_docx(payload or {}, target)
            return {"ok": True, "path": saved}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def export_report_pdf(self, payload: dict):
        if not self._window:
            return {"ok": False, "error": "پنجره آماده نیست."}
        try:
            save_dialog = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else getattr(webview, "SAVE_DIALOG", 30)
            clean_name = re.sub(r'[\\/*?:"<>|]', '', str((payload or {}).get("title") or "گزارش_رسمی_مؤسسه")).strip()
            default_fn = f"{clean_name[:40]}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            result = self._window.create_file_dialog(
                save_dialog, directory=str(BASE_DIR), save_filename=default_fn, file_types=("PDF Document (*.pdf)",)
            )
            if not result:
                return {"ok": False, "cancelled": True}
            target = Path(str(result[0] if isinstance(result, (list, tuple)) else result))
            if target.suffix.lower() != ".pdf":
                target = target.with_suffix(".pdf")
            return export_official_pdf(payload or {}, target)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


    # --- v3.0 Pro: کنترل بومی پنجره ویندوزی (ریسایز ۸ جهته Win32 و تمام‌صفحه) ---

    def get_window_bounds(self):
        if not self._window:
            return {"ok": False}
        try:
            native = getattr(self._window, "native", None)
            if native is not None:
                b = native.Bounds
                return {"ok": True, "x": int(b.X), "y": int(b.Y), "w": int(b.Width), "h": int(b.Height)}
        except Exception:
            pass
        return {"ok": False}

    def set_window_bounds(self, x: int, y: int, width: int, height: int):
        if not self._window:
            return {"ok": False}
        try:
            native = getattr(self._window, "native", None)
            if native is not None:
                from System import Action

                nx, ny = int(x), int(y)
                nw, nh = max(1024, int(width)), max(680, int(height))
                native.BeginInvoke(Action(lambda: native.SetBounds(nx, ny, nw, nh)))
                return {"ok": True}
        except Exception:
            pass
        return {"ok": False}

    def toggle_maximize(self):
        return self.toggle_maximize_window()

    def is_window_maximized(self):
        # Thread-safe, zero-blocking read (updated on UI thread by SizeChanged/_toggle)
        return {"ok": True, "maximized": bool(self._maximized)}

    def toggle_maximize_window(self):
        if not self._window:
            return {"ok": False}
        try:
            native = getattr(self._window, "native", None)
            if native is not None:
                from System import Action
                from System.Windows.Forms import FormWindowState, Screen

                def _toggle():
                    try:
                        hwnd = int(native.Handle.ToInt64())
                        wa = Screen.FromControl(native).WorkingArea
                        native.MaximizedBounds = wa
                        if native.WindowState == FormWindowState.Maximized:
                            native.WindowState = FormWindowState.Normal
                            self._maximized = False
                            pref = ctypes.c_int(2)
                        else:
                            native.WindowState = FormWindowState.Maximized
                            self._maximized = True
                            pref = ctypes.c_int(1)
                        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
                        no_border = ctypes.c_uint(0xFFFFFFFE)
                        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(no_border), ctypes.sizeof(no_border))
                    except Exception:
                        pass

                native.BeginInvoke(Action(_toggle))
                return {"ok": True}
            self._window.toggle_fullscreen()
            self._maximized = not self._maximized
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def begin_window_resize(self, direction: str):
        hit_map = {
            "left": 10,
            "right": 11,
            "top": 12,
            "top-left": 13,
            "top-right": 14,
            "bottom": 15,
            "bottom-left": 16,
            "bottom-right": 17,
            "move": 2,
        }
        dir_low = str(direction or "").lower()
        ht = hit_map.get(dir_low)
        if not ht or not self._window:
            return {"ok": False}
        if dir_low != "move" and self._maximized:
            return {"ok": False, "blocked": "maximized"}
        try:
            native = getattr(self._window, "native", None)
            if native is not None:
                from System import Action
                from System.Windows.Forms import FormWindowState

                def _do_hit():
                    try:
                        from System.Windows.Forms import Cursor
                        hwnd = int(native.Handle.ToInt64())
                        if native.WindowState == FormWindowState.Maximized:
                            if dir_low != "move":
                                self._maximized = True
                                return
                            # Smooth Chrome/Win11-style restore-on-drag from maximized state
                            cur = Cursor.Position
                            old_w = max(1, int(native.Width))
                            rx = max(0.08, min(0.92, (cur.X - int(native.Left)) / float(old_w)))
                            native.WindowState = FormWindowState.Normal
                            self._maximized = False
                            new_w = max(800, int(native.Width))
                            native.Left = int(cur.X - new_w * rx)
                            native.Top = max(0, int(cur.Y - 18))
                            try:
                                pref = ctypes.c_int(2)
                                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
                            except Exception:
                                pass
                        # Only start drag if left mouse button is still physically held
                        if (ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000) == 0:
                            return
                        ctypes.windll.user32.ReleaseCapture()
                        ctypes.windll.user32.SendMessageW(hwnd, 0x00A1, ht, 0)
                    except Exception:
                        pass

                native.BeginInvoke(Action(_do_hit))
                return {"ok": True, "mode": "win32"}
        except Exception:
            pass
        return {"ok": False, "mode": "fallback"}

    def start_window_resize(self, direction: str):
        return self.begin_window_resize(direction)

    def resize_window_absolute(self, width: int, height: int):
        if not self._window:
            return {"ok": False}
        try:
            self._window.resize(max(1024, int(width)), max(680, int(height)))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def toggle_fullscreen_window(self):
        if not self._window:
            return {"ok": False}
        try:
            self._window.toggle_fullscreen()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}




    # ==================== v6.0 Pro: مرکز آمار، پرس‌لاین، دبیرخانه، چرخه رویدادها و پرونده ۳۶۰ ====================
    def get_executive_analytics(self, filters: dict | None = None):
        f_raw = dict(filters or {})
        force = bool(f_raw.pop("_force", False) or f_raw.pop("force", False))
        key = json.dumps(
            {
                "group": str(f_raw.get("group") or ""),
                "teacher": str(f_raw.get("teacher") or ""),
                "year": str(f_raw.get("year") or ""),
                "data_mode": str(f_raw.get("data_mode") or ""),
                "hours_policy": str(f_raw.get("hours_policy") or ""),
                "split_subgroups": str(f_raw.get("split_subgroups", "")),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        if not force:
            with self._exec_cache_lock:
                cached = self._exec_cache.get(key)
            if cached is not None:
                return cached
        res = self.exec_engine.get_executive_analytics(f_raw)
        if isinstance(res, dict) and res.get("ok"):
            with self._exec_cache_lock:
                if len(self._exec_cache) > 24:
                    self._exec_cache.clear()
                self._exec_cache[key] = res
        return res

    def get_teacher_profile(self, name: str):
        cached_t = self.get_executive_analytics({"teacher": name})
        return self.exec_engine.get_teacher_profile(name, precomputed=cached_t)

    def save_teacher_meta(self, name: str, bio: str, works: str):
        self._invalidate_caches()
        return self.exec_engine.save_teacher_meta(name, bio, works)

    def get_participant_profile(self, key: str):
        cached_all = self.get_executive_analytics({})
        return self.exec_engine.get_participant_profile(key, precomputed=cached_all)

    def save_participant_meta(self, profile_key: str, meta: dict):
        self._invalidate_caches()
        return self.exec_engine.save_participant_meta(profile_key, meta or {})

    def export_filtered_participants_excel(self, payload: dict):
        if not self._window:
            return {"ok": False, "error": "پنجره آماده نیست."}
        try:
            st = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else getattr(webview, "SAVE_DIALOG", 20)
            fname = f"eHadi_Participants_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            sel = self._window.create_file_dialog(st, save_filename=fname, file_types=("Excel Files (*.xlsx)",))
            if not sel:
                return {"ok": False, "cancelled": True}
            dest = Path(sel[0] if isinstance(sel, (list, tuple)) else str(sel))
            if dest.suffix.lower() != ".xlsx":
                dest = dest.with_suffix(".xlsx")
            from src.reports.report_studio import export_styled_table_excel
            rows = (payload or {}).get("rows") or []
            cols = (payload or {}).get("columns") or [
                "ردیف", "نام و نام خانوادگی", "شماره تماس", "کد ملی / گذرنامه (اتباع)", "سطح",
                "تعداد دوره", "جلسات حاضر", "کل جلسات", "نرخ حضور (%)",
                "سابقه حضور", "امتیاز مشارکت", "کارگروه‌ها", "برچسب‌ها", "یادداشت",
            ]
            title = str((payload or {}).get("title") or "فهرست دانش‌پژوهان یکتاسازی‌شده مؤسسه")
            out_p = export_styled_table_excel({"title": title, "columns": cols, "rows": rows}, dest)
            if Path(out_p).exists():
                os.startfile(out_p)
            return {"ok": True, "path": str(out_p), "count": len(rows)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def merge_duplicate_records(self, canonical_name: str, alias_name: str):
        self._invalidate_caches()
        return self.exec_engine.merge_duplicate_records(canonical_name, alias_name)

    def reject_duplicate_records(self, name_a: str, name_b: str):
        self._invalidate_caches()
        return self.exec_engine.reject_duplicate_records(name_a, name_b)

    def select_and_preview_porsline(self):
        if not self._window:
            return {"ok": False, "error": "پنجره آماده نیست."}
        try:
            dt = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else getattr(webview, "OPEN_DIALOG", 10)
            sel = self._window.create_file_dialog(dt, allow_multiple=False, file_types=("Excel and CSV Files (*.xlsx;*.xls;*.csv)", "All Files (*.*)"))
            if not sel:
                return {"ok": False, "cancelled": True}
            return self.exec_engine.parse_porsline_file(str(sel[0]))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def commit_porsline_import(self, payload: dict):
        self._invalidate_caches()
        return self.exec_engine.commit_porsline_import(payload)

    def export_attendance_sheet(self, payload: dict):
        if not self._window:
            return {"ok": False, "error": "پنجره آماده نیست."}
        try:
            st = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else getattr(webview, "SAVE_DIALOG", 20)
            fname = f"Attendance_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            sel = self._window.create_file_dialog(st, save_filename=fname, file_types=("PDF Files (*.pdf)",))
            if not sel:
                return {"ok": False, "cancelled": True}
            dest = Path(sel[0] if isinstance(sel, (list, tuple)) else str(sel))
            if dest.suffix.lower() != ".pdf":
                dest = dest.with_suffix(".pdf")
            res = export_attendance_sheet_pdf(payload, dest)
            if res.get("ok") and Path(res["path"]).exists():
                os.startfile(res["path"])
            return res
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def export_executive_report(self, payload: dict):
        if not self._window:
            return {"ok": False, "error": "پنجره آماده نیست."}
        fmt = str((payload or {}).get("format") or "pdf").lower()
        ext_map = {"pdf": (".pdf", "PDF Files (*.pdf)"), "docx": (".docx", "Word Files (*.docx)"), "xlsx": (".xlsx", "Excel Files (*.xlsx)")}
        ext, ftype = ext_map.get(fmt, (".pdf", "PDF Files (*.pdf)"))
        try:
            st = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else getattr(webview, "SAVE_DIALOG", 20)
            fname = f"eHadi_Analytics_{datetime.now().strftime('%Y%m%d_%H%M')}{ext}"
            sel = self._window.create_file_dialog(st, save_filename=fname, file_types=(ftype,))
            if not sel:
                return {"ok": False, "cancelled": True}
            dest = Path(sel[0] if isinstance(sel, (list, tuple)) else str(sel))
            if dest.suffix.lower() != ext:
                dest = dest.with_suffix(ext)
            if fmt == "xlsx":
                analytics = self.get_executive_analytics(payload.get("filters") or {})
                res = export_analytics_excel(analytics, dest)
                if res.get("ok"):
                    os.startfile(res["path"])
                return res
            if fmt == "docx":
                out_p = export_official_docx(payload, dest)
                if Path(out_p).exists():
                    os.startfile(out_p)
                return {"ok": True, "path": out_p}
            res = export_official_pdf(payload, dest)
            if res.get("ok") and Path(res["path"]).exists():
                os.startfile(res["path"])
            return res
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_letter_registry(self):
        return {"ok": True, "letters": self.exec_engine.get_letters()}

    def delete_registered_letter(self, letter_id: str):
        self._invalidate_caches()
        return self.exec_engine.delete_letter(letter_id)

    def open_registered_file(self, file_path: str, reveal_folder: bool = False):
        p = Path(str(file_path or ""))
        if not p.exists():
            return {"ok": False, "error": "فایل در مسیر ثبت‌شده یافت نشد."}
        try:
            if reveal_folder:
                import subprocess
                subprocess.Popen(["explorer", "/select,", str(p)])
            else:
                os.startfile(str(p))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_event_pipelines(self):
        return {"ok": True, "events": self.exec_engine.get_events()}

    def save_event_pipeline(self, payload: dict):
        return self.exec_engine.save_event(payload)

    def delete_event_pipeline(self, event_id: str):
        self._invalidate_caches()
        return self.exec_engine.delete_event(event_id)



    def listen_voice_command(self, engine: str | None = None, tts_enabled: bool = True):
        return listen_and_execute_voice(engine=engine, tts_enabled=tts_enabled)

    def stop_voice_recording(self):
        return stop_active_recording()

    def process_voice(self, audio_b64: str, engine: str | None = None, mime_type: str = "audio/wav"):
        return process_voice_command(audio_b64, engine=engine, mime_type=mime_type)

    def set_voice_preferences(self, engine: str, tts_enabled: bool):
        from src.reports.report_studio import save_branding
        updated = save_branding({"voice_engine": engine, "voice_tts": bool(tts_enabled)})
        return {"ok": True, "voice_engine": updated.get("voice_engine"), "voice_tts": updated.get("voice_tts")}


    def get_decisions(self):
        return {"ok": True, "decisions": load_decisions()}

    def save_decision_item(self, payload: dict):
        return save_decision(payload or {})

    def delete_decision_item(self, decision_id: str):
        return delete_decision(decision_id)

    def create_backup_now(self):
        return create_snapshot_backup("manual")

    def get_audit_logs(self):
        return {"ok": True, "logs": get_recent_audits(60)}

    def clear_audit_logs(self):
        return clear_audit_logs()

    def get_memory_state(self):
        from src.core.memory_engine import get_memory_state as _gms
        return _gms()

    def add_user_rule(self, rule_text: str = "", scope: str = "general"):
        from src.core.memory_engine import add_rule as _ar
        return _ar(rule_text, scope)

    def delete_user_rule(self, rule_id: int = 0):
        from src.core.memory_engine import delete_rule as _dr
        return _dr(int(rule_id))

    def resolve_fuzzy_pair(self, canonical_name: str = "", alias_name: str = "", entity_type: str = "teacher", decision: str = "approved", confidence: float = 1.0):
        from src.core.memory_engine import save_alias as _sa
        self._invalidate_caches()
        self.agent.invalidate_cache()
        return _sa(
            canonical_name=canonical_name,
            alias_name=alias_name,
            entity_type=entity_type,
            status=("approved" if decision == "approved" else "rejected"),
            confidence=float(confidence or 1.0),
        )

    def delete_entity_alias(self, alias_id: int = 0):
        from src.core.memory_engine import delete_alias as _da
        self._invalidate_caches()
        return _da(int(alias_id))

    # --- Beta 0.2: هسته هوشمند موجودیت‌ها (کنترل ۱۰۰٪ از رابط کاربری)، سیاست ساعات و حسابرسی ---
    def get_brain_config(self):
        from src.core.memory_engine import load_brain_config as _lbc
        return {"ok": True, "config": _lbc()}

    def save_brain_config(self, payload: dict | None = None):
        from src.core.memory_engine import save_brain_config as _sbc
        self._invalidate_caches()
        self.agent.invalidate_cache()
        return _sbc(payload or {})

    def add_compound_name(self, name: str = ""):
        from src.core.memory_engine import add_compound_name as _acn
        self._invalidate_caches()
        self.agent.invalidate_cache()
        return _acn(name)

    def delete_compound_name(self, name: str = ""):
        from src.core.memory_engine import delete_compound_name as _dcn
        self._invalidate_caches()
        self.agent.invalidate_cache()
        return _dcn(name)

    def set_entity_type_override(self, raw_name: str = "", entity_mode: str = "auto"):
        from src.core.memory_engine import set_entity_type_override as _seto
        self._invalidate_caches()
        self.agent.invalidate_cache()
        return _seto(raw_name, entity_mode)

    def set_hours_policy(self, policy: str = "equal"):
        from src.core.memory_engine import set_hours_policy as _shp
        self._invalidate_caches()
        self.agent.invalidate_cache()
        return _shp(policy)

    def set_course_hour_override(self, course_key: str = "", teacher_shares: dict | None = None):
        from src.core.memory_engine import set_course_hour_override as _scho
        self._invalidate_caches()
        self.agent.invalidate_cache()
        return _scho(course_key, teacher_shares)

    def get_brain_history(self, limit: int = 30):
        from src.core.memory_engine import get_brain_history as _gbh
        return {"ok": True, "history": _gbh(int(limit))}

    def undo_brain_action(self, history_id: int = 0):
        from src.core.memory_engine import undo_brain_action as _uba
        self._invalidate_caches()
        self.agent.invalidate_cache()
        return _uba(int(history_id))

    def export_brain_config(self):
        from src.core.memory_engine import export_brain_json as _ebj
        return _ebj()

    def import_brain_config(self, raw_json: str = ""):
        from src.core.memory_engine import import_brain_json as _ibj
        self._invalidate_caches()
        self.agent.invalidate_cache()
        return _ibj(raw_json)

    def get_teacher_exact_stats(self, teacher_name: str = "", hours_policy: str = ""):
        from src.core.memory_engine import get_teacher_exact_stats as _gtes
        return _gtes(teacher_name, hours_policy)

    def get_audit_rows(self, entity_type: str = "teacher", entity_name: str = ""):
        return self.exec_engine.get_audit_rows(entity_type, entity_name)

    def get_duplicate_files(self):
        from src.core.db_manager import detect_duplicate_files as _ddf
        return {"ok": True, "alerts": _ddf()}

    def run_health_check(self, check_network: bool = False):
        from src.core.diagnostics import run_health_check as _rhc
        return _rhc(check_network)

    def export_diagnostic_bundle(self):
        from src.core.diagnostics import export_diagnostic_bundle as _edb
        return _edb()

    def get_recent_errors(self, limit: int = 12):
        from src.core.diagnostics import get_recent_errors as _gre
        return _gre(limit)

    def clear_error_logs(self):
        from src.core.diagnostics import clear_error_logs as _cel
        return _cel()

    def log_frontend_error(self, payload=None):
        from src.core.diagnostics import log_frontend_error as _lfe
        return _lfe(payload)



def _enable_native_dwm_animations(window, api=None):
    try:
        native = getattr(window, "native", None)
        if native is None:
            return
        from System import Action, EventHandler
        from System.Drawing import Color
        from System.Windows.Forms import FormBorderStyle, FormWindowState, Screen

        def _apply():
            try:
                native.FormBorderStyle = getattr(FormBorderStyle, "None")
                native.BackColor = Color.FromArgb(10, 11, 15)
                native.MaximizedBounds = Screen.FromControl(native).WorkingArea
                hwnd = int(native.Handle.ToInt64())
                dark = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
                no_border = ctypes.c_uint(0xFFFFFFFE)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(no_border), ctypes.sizeof(no_border))
                round_pref = ctypes.c_int(2)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(round_pref), ctypes.sizeof(round_pref))

                def _on_size_changed(sender, args):
                    # NEVER call evaluate_js() on the WinForms UI thread (causes instant deadlock!)
                    try:
                        if api is not None:
                            api._maximized = bool(native.WindowState == FormWindowState.Maximized)
                    except Exception:
                        pass

                native.SizeChanged += EventHandler(_on_size_changed)
                _on_size_changed(None, None)
            except Exception:
                pass

        native.BeginInvoke(Action(_apply))
    except Exception:
        pass


def main():
    _set_splash_stage("1")
    api = AppAPI()
    _set_splash_stage("2")
    html_path = Path(__file__).resolve().parent / "src" / "ui" / "web" / "index.html"
    clean_title = re.sub(
        r"\s*(?:Enterprise|v?\d+(?:\.\d+)*\s*(?:Pro)?)\s*",
        " ",
        str(getattr(Config, "APP_NAME", "پنل مدیریت مؤسسه امام هادی")),
        flags=re.IGNORECASE,
    ).strip() or "پنل مدیریت مؤسسه امام هادی"

    window = webview.create_window(
        title=clean_title,
        url=str(html_path),
        js_api=api,
        width=1280,
        height=800,
        min_size=(1000, 660),
        frameless=True,
        resizable=True,
        easy_drag=False,
        hidden=bool(_SPLASH_SPAWNED),
        background_color="#050811",
    )
    api.set_window(window)
    _set_splash_stage("3")

    def _reveal_main_when_splash_done():
        try:
            _set_splash_stage("READY")
            if _SPLASH_SPAWNED:
                t_start = time.monotonic()
                while (time.monotonic() - t_start) < 2.2:
                    if _SPLASH_DONE_FILE.exists() or not _SPLASH_READY_FILE.exists():
                        break
                    time.sleep(0.025)
                try:
                    window.show()
                except Exception:
                    pass
                try:
                    native = getattr(window, "native", None)
                    if native is not None:
                        from System import Action
                        def _bring_front():
                            try:
                                native.Show()
                                native.BringToFront()
                                native.Activate()
                            except Exception:
                                pass
                        native.BeginInvoke(Action(_bring_front))
                except Exception:
                    pass
        finally:
            try:
                _SPLASH_DONE_FILE.unlink(missing_ok=True)
            except Exception:
                pass

    def _on_window_shown():
        _enable_native_dwm_animations(window, api)
        if _SPLASH_SPAWNED:
            threading.Thread(target=_reveal_main_when_splash_done, daemon=True).start()
        if not getattr(api, "_warmed_up", False):
            api._warmed_up = True
            def _bg_warmup_all():
                try:
                    api.get_executive_analytics({})
                except Exception:
                    pass
                try:
                    api.agent.warmup()
                except Exception:
                    pass
            threading.Thread(target=_bg_warmup_all, daemon=True).start()

    window.events.shown += _on_window_shown
    webview.start()


if __name__ == "__main__":
    main()
