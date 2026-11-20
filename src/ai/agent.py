import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import duckdb
import lancedb
from google import genai
from google.genai import types
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.core.config import Config
from src.core.smart_brain import (
    SafeDuckDBExecutor,
    SemanticSchemaEngine,
    register_persian_macros,
)
from src.core.memory_engine import (
    add_rule as _mem_add_rule,
    build_memory_prompt_block as _mem_prompt_block,
    init_memory_tables as _mem_init,
    rebuild_clean_teacher_layer as _mem_rebuild_teachers,
    save_alias as _mem_save_alias,
)
from src.reports.report_studio import load_branding

logger = logging.getLogger("eHadiPanel.Agent")

PERSIAN_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]

MODE_PROMPTS = {
    "analyst": (
        "حالت فعال: تحلیلگر اجرایی هوشمند. پاسخ‌ها را دقیق، مستند، مستقیم، شفاف و با ساختار حرفه‌ای "
        "(تیتر، بولت‌پوینت، جدول خلاصه و جمع‌بندی عملیاتی) به فارسی روان بنویس و از حاشیه‌گویی پرهیز کن."
    ),
    "board_report": (
        "حالت فعال: تهیه گزارش رسمی هیئت‌مدیره. پاسخ را در قالب یک گزارش مدیریتی رسمی و آماده ارائه شامل "
        "«خلاصه اجرایی»، «یافته‌های کلیدی و آمار دقیق»، «تحلیل روندها و نقاط تمرکز» و «پیشنهادهای عملیاتی» تنظیم کن."
    ),
}


def normalize_fa(text: str) -> str:
    if not text:
        return ""
    text = text.translate(PERSIAN_TO_EN)
    text = (
        text.replace("ي", "ی")
        .replace("ك", "ک")
        .replace("ة", "ه")
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("\u200c", " ")
    )
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


class InstitutionalAIAgent:
    """موتور هوش مصنوعی سازمانی با هسته خودترمیم (SmartBrain v44)، نمای تجمیعی DuckDB، محاسبات قطعی و Failover خودکار"""

    def __init__(self):
        Config.ensure_directories()
        self.duckdb_path = str(Config.DUCKDB_PATH)
        self.lancedb_path = str(Config.LANCEDB_PATH)
        self._db_lock = threading.Lock()
        self._cache_lock = threading.Lock()

        self._client: genai.Client | None = None
        self._client_key: str = ""
        self._chunks_cache: list[dict[str, Any]] | None = None
        self._catalog_cache: dict[str, Any] | None = None
        self._no_thinking_models: set[str] = set()
        self._schema_engine = SemanticSchemaEngine(self.duckdb_path)

        self._init_chat_storage()
        try:
            _mem_init(self.duckdb_path)
        except Exception:
            pass

    def _connect_duckdb(self):
        return duckdb.connect(self.duckdb_path)

    def _init_chat_storage(self) -> None:
        with self._db_lock:
            con = self._connect_duckdb()
            try:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id INTEGER PRIMARY KEY,
                        role VARCHAR,
                        content VARCHAR,
                        mode VARCHAR,
                        citations_json VARCHAR,
                        tables_json VARCHAR,
                        tools_json VARCHAR,
                        created_at VARCHAR
                    )
                """)
            finally:
                con.close()

    def invalidate_cache(self) -> None:
        with self._cache_lock:
            self._chunks_cache = None
            self._catalog_cache = None
        try:
            self._schema_engine._cache_sig = None
            self._schema_engine._cached_profiles = []
        except Exception:
            pass

    def reset_client(self) -> None:
        with self._cache_lock:
            self._client = None
            self._client_key = ""

    def _get_client(self, api_key: str) -> genai.Client:
        with self._cache_lock:
            if self._client is not None and self._client_key == api_key:
                return self._client
            try:
                self._client = genai.Client(
                    api_key=api_key,
                    http_options=types.HttpOptions(timeout=45000),
                )
            except Exception:
                self._client = genai.Client(api_key=api_key)
            self._client_key = api_key
            return self._client

    def warmup(self) -> None:
        try:
            self._get_catalog_summary()
            with self._db_lock:
                self._schema_engine.get_profiles()
            self._load_all_chunks()
            key = (Config.GEMINI_API_KEY or "").strip()
            if key and key != "کلید_API_خود_را_اینجا_بگذارید":
                self._get_client(key)
        except Exception as exc:
            logger.warning("Warmup warning: %s", exc)

    def get_chat_history(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._db_lock:
            con = self._connect_duckdb()
            try:
                rows = con.execute("""
                    SELECT id, role, content, mode, citations_json, tables_json, tools_json, created_at
                    FROM chat_history
                    ORDER BY id ASC
                """).fetchall()
            finally:
                con.close()

        items = []
        for r in rows[-limit:]:
            items.append({
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "mode": r[3] or "analyst",
                "citations": json.loads(r[4] or "[]"),
                "tables": json.loads(r[5] or "[]"),
                "tools": json.loads(r[6] or "[]"),
                "created_at": r[7],
            })
        return items

    def clear_chat_history(self) -> dict[str, Any]:
        with self._db_lock:
            con = self._connect_duckdb()
            try:
                con.execute("DELETE FROM chat_history")
            finally:
                con.close()
        return {"ok": True}

    def _save_message(
        self,
        role: str,
        content: str,
        mode: str = "analyst",
        citations: list[dict] | None = None,
        tables: list[dict] | None = None,
        tools: list[str] | None = None,
    ) -> dict[str, Any]:
        now_str = datetime.now().strftime("%H:%M")
        with self._db_lock:
            con = self._connect_duckdb()
            try:
                max_id = con.execute("SELECT COALESCE(MAX(id), 0) FROM chat_history").fetchone()[0]
                new_id = int(max_id) + 1
                con.execute(
                    "INSERT INTO chat_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        new_id,
                        role,
                        content,
                        mode,
                        json.dumps(citations or [], ensure_ascii=False),
                        json.dumps(tables or [], ensure_ascii=False),
                        json.dumps(tools or [], ensure_ascii=False),
                        now_str,
                    ],
                )
            finally:
                con.close()

        return {
            "id": new_id,
            "role": role,
            "content": content,
            "mode": mode,
            "citations": citations or [],
            "tables": tables or [],
            "tools": tools or [],
            "created_at": now_str,
        }

    def _load_all_chunks(self) -> list[dict[str, Any]]:
        with self._cache_lock:
            if self._chunks_cache is not None:
                return self._chunks_cache

        db = lancedb.connect(self.lancedb_path)
        if "document_chunks" not in db.table_names():
            rows: list[dict[str, Any]] = []
        else:
            raw = db.open_table("document_chunks").to_pandas().to_dict(orient="records")
            rows = []
            for r in raw:
                item = dict(r)
                item["_norm"] = normalize_fa(
                    f"{item.get('file_name', '')} {item.get('location', '')} {item.get('content', '')}"
                )
                item["_loc_norm"] = normalize_fa(str(item.get("location", "")))
                item["_file_norm"] = normalize_fa(str(item.get("file_name", "")))
                rows.append(item)

        with self._cache_lock:
            self._chunks_cache = rows
        return rows

    def get_chunk_by_id(self, chunk_id: str) -> dict[str, Any]:
        rows = self._load_all_chunks()
        if not rows:
            return {"ok": False, "error": "بانک متون خالی است."}
        for r in rows:
            if str(r.get("chunk_id")) == str(chunk_id):
                return {
                    "ok": True,
                    "chunk_id": r.get("chunk_id", ""),
                    "file_name": r.get("file_name", ""),
                    "file_path": r.get("file_path", ""),
                    "file_type": r.get("file_type", ""),
                    "location": r.get("location", ""),
                    "content": r.get("content", ""),
                }
        return {"ok": False, "error": "محتوای منبع یافت نشد."}

    def _build_unified_views(
        self, con: duckdb.DuckDBPyConnection, tables_meta: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for t in tables_meta:
            cols = t.get("columns") or []
            if len(cols) < 2:
                continue
            sig = tuple(normalize_fa(c) for c in cols)
            groups.setdefault(sig, []).append(t)

        unified_views: list[dict[str, Any]] = []
        v_idx = 0
        for _sig, grp in groups.items():
            if len(grp) < 2:
                continue
            v_idx += 1
            view_name = f"view_merged_{v_idx}"
            canonical_cols = grp[0]["columns"]

            select_parts = []
            total_rows = 0
            source_tables = []
            for t in grp:
                t_name = t["table_name"]
                f_esc = str(t["file_name"]).replace("'", "''")
                s_esc = str(t["source_sheet"]).replace("'", "''")
                t_cols = t["columns"]
                col_exprs = []
                for orig_col, canon_col in zip(t_cols, canonical_cols):
                    oc = orig_col.replace('"', '""')
                    cc = canon_col.replace('"', '""')
                    col_exprs.append(f'CAST("{oc}" AS VARCHAR) AS "{cc}"')
                select_parts.append(
                    f"SELECT '{f_esc}' AS \"فایل_منبع\", '{s_esc}' AS \"بخش_منبع\", "
                    + ", ".join(col_exprs)
                    + f' FROM "{t_name}"'
                )
                total_rows += int(t.get("rows_count") or 0)
                source_tables.append(t_name)

            try:
                view_sql = f'CREATE OR REPLACE VIEW "{view_name}" AS ' + " UNION ALL ".join(select_parts)
                con.execute(view_sql)
                unified_views.append({
                    "view_name": view_name,
                    "description": f"نمای تجمیعی خودکار شامل {len(grp)} جدول هم‌ساختار ({total_rows} ردیف)",
                    "total_rows": total_rows,
                    "columns": ["فایل_منبع", "بخش_منبع"] + canonical_cols,
                    "source_tables": source_tables,
                })
            except Exception as exc:
                logger.warning("Failed creating unified view %s: %s", view_name, exc)
                continue

        return unified_views

    def _get_catalog_summary(self) -> dict[str, Any]:
        with self._cache_lock:
            if self._catalog_cache is not None:
                return self._catalog_cache

        with self._db_lock:
            con = self._connect_duckdb()
            try:
                files = con.execute("""
                    SELECT file_name, file_type, chunks_count, tables_count, rows_count
                    FROM processed_files
                    WHERE status = 'موفق'
                    ORDER BY file_name
                """).fetchall()
                tables = con.execute("""
                    SELECT table_name, file_name, source_sheet, rows_count, columns_json
                    FROM tabular_catalog
                    ORDER BY file_name, source_sheet
                """).fetchall()

                tables_meta = [
                    {
                        "table_name": t[0],
                        "file_name": t[1],
                        "source_sheet": t[2],
                        "rows_count": t[3],
                        "columns": json.loads(t[4] or "[]"),
                    }
                    for t in tables
                ]
                unified_views = self._build_unified_views(con, tables_meta)
            finally:
                con.close()

        summary = {
            "files": [
                {
                    "file_name": f[0],
                    "file_type": f[1],
                    "chunks_count": f[2],
                    "tables_count": f[3],
                    "rows_count": f[4],
                }
                for f in files
            ],
            "unified_views": unified_views,
            "tables": tables_meta,
        }
        try:
            _mem_rebuild_teachers(self.duckdb_path)
        except Exception as _te:
            logger.warning('Teacher layer refresh skipped: %s', _te)
        with self._cache_lock:
            self._catalog_cache = summary
        return summary

    def _build_scalable_knowledge_map(self, catalog: dict[str, Any], question: str) -> str:
        """Builds a compact, relevance-ranked Semantic Schema + Unified Views map for high-volume datasets."""
        lines: list[str] = []

        files = catalog.get("files") or []
        lines.append(f"### ۱. فهرست فایل‌های پردازش‌شده ({len(files)} فایل)")
        for f in files[:25]:
            lines.append(
                f"- {f['file_name']} ({f['file_type']} | {f['tables_count']} جدول، {f['rows_count']} ردیف، {f['chunks_count']} بخش متنی)"
            )
        if len(files) > 25:
            lines.append(f"- و {len(files) - 25} فایل دیگر...")

        uviews = catalog.get("unified_views") or []
        if uviews:
            lines.append("\n### ۲. نماهای تجمیعی سریع (اولویت اول برای گزارش‌های سراسری)")
            for v in uviews:
                cols_str = "، ".join(f'"{c}"' for c in (v.get("columns") or []))
                lines.append(
                    f'- نمای `"{v["view_name"]}"`: {v["description"]} | ستون‌ها: {cols_str}'
                )

        # Map source_sheet (e.g. "اسلاید 11 (جدول 1)") to actual heading text from LanceDB chunks
        try:
            chunks = self._load_all_chunks()
            sheet_titles: list[str] = []
            seen_sh: set[tuple[str, str]] = set()
            for t in (catalog.get("tables") or [])[:25]:
                fn = str(t.get("file_name") or "")
                sh = str(t.get("source_sheet") or "")
                if not sh or (fn, sh) in seen_sh:
                    continue
                seen_sh.add((fn, sh))
                sh_base = normalize_fa(sh.split("(")[0])
                matched = next(
                    (c for c in chunks if c.get("file_name") == fn and sh_base and sh_base in c.get("_loc_norm", "")),
                    None,
                )
                if matched:
                    raw_c = str(matched.get("content") or "").strip()
                    first_lines = [ln.strip(" #•-*:") for ln in raw_c.splitlines() if ln.strip(" #•-*:")]
                    title_hint = " | ".join(first_lines[:2])[:110] if first_lines else ""
                    if title_hint:
                        sheet_titles.append(f'- «{sh}» ({fn}) => عنوان/موضوع واقعی: {title_hint}')
            if sheet_titles:
                lines.append("\n### ۲.۵. نگاشت عنوان واقعی بخش‌ها و اسلایدها (در گزارش‌ها به‌جای شماره اسلاید از نام واقعی کارگروه/موضوع استفاده کن و اسلایدهای هم‌نام را ادغام کن)")
                lines.extend(sheet_titles)
        except Exception as exc:
            logger.warning("Could not enrich slide titles: %s", exc)

        lines.append(
            "\n### ۲.۶. جدول تمیز و تفکیک‌شده اساتید (`\"smart_teachers_exploded\"`) — ویژه تحلیل اساتید و دوره‌های مشترک\n"
            "- ستون‌ها: `\"فایل_منبع\"`, `\"بخش_منبع\"`, `\"نام_دوره\"`, `\"نام_معیار_استاد\"`, `\"نوع_برگزاری\"` (انفرادی / مشترک / گروهی), `\"تعداد_اساتید_دوره\"`, `\"تعداد_شرکت_کنندگان\"`, `\"سهم_تعدیل_شده_مخاطب\"`, `\"همکاران_مشترک\"`\n"
            "- در این جدول دوره‌های چنداستاده به تفکیک هر استاد شکسته شده، ردیف‌های جمع کل حذف شده و نام‌های معادل تأییدشده اعمال شده‌اند.\n"
            "- هشدار ضد شمارش مضاعف: برای رتبه‌بندی اساتید یا آمار دوره‌های هر استاد (با تفکیک انفرادی و مشترک) حتماً از `\"smart_teachers_exploded\"` استفاده کن؛ اما برای جمع کل شرکت‌کنندگان کل مؤسسه یا کارگروه از `\"view_merged_1\"` (یا `SUM(\"سهم_تعدیل_شده_مخاطب\")`) استفاده کن تا دوره‌های مشترک دوبار شمرده نشوند."
        )
        with self._db_lock:
            semantic_ctx = self._schema_engine.build_prompt_context(
                question=question, max_detailed_tables=12
            )
        lines.append("\n" + semantic_ctx)

        try:
            mem_block = _mem_prompt_block(self.duckdb_path)
            if mem_block:
                lines.append("\n" + mem_block)
        except Exception as exc:
            logger.warning("Could not load memory prompt block: %s", exc)

        return "\n".join(lines)

    def test_connection(self, api_key: str | None = None, model: str | None = None) -> dict[str, Any]:
        key = (api_key if api_key is not None else Config.GEMINI_API_KEY).strip()
        mdl = (model if model is not None else Config.GEMINI_MODEL).strip() or "gemini-3.8-flash"

        if not key or key == "کلید_API_خود_را_اینجا_بگذارید":
            return {"ok": False, "error": "کلید Gemini API وارد نشده است."}

        try:
            client = genai.Client(api_key=key)
            resp = client.models.generate_content(
                model=mdl,
                contents="فقط کلمه «متصل» را برگردان.",
            )
            txt = (resp.text or "").strip()
            return {"ok": True, "message": f"اتصال با مدل {mdl} برقرار است ({txt[:30]})."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _build_thinking_config(self, model_name: str, mode: str):
        low = model_name.lower()
        if model_name in self._no_thinking_models or not hasattr(types, "ThinkingConfig"):
            return None
        if "flash" not in low:
            return None

        try:
            if "gemini-3" in low:
                lvl = "LOW" if mode == "board_report" else "MINIMAL"
                return types.ThinkingConfig(thinking_level=lvl)
            return types.ThinkingConfig(thinking_budget=256 if mode == "board_report" else 0)
        except Exception:
            return None

    @staticmethod
    def _is_failover_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        triggers = (
            "503",
            "unavailable",
            "high demand",
            "overloaded",
            "429",
            "resource_exhausted",
            "quota",
            "404",
            "not_found",
            "timed out",
            "timeout",
        )
        return any(t in msg for t in triggers)

    @staticmethod
    def _build_clean_history_contents(recent_history: list[dict[str, Any]], current_question: str) -> list[types.Content]:
        pairs: list[tuple[str, str]] = []
        pending_user: str | None = None

        for msg in recent_history:
            role = msg.get("role", "")
            text = (msg.get("content") or "").strip()
            if not text:
                continue
            if role == "user":
                pending_user = text[:700]
            elif role == "assistant" and pending_user is not None:
                pairs.append((pending_user, text[:850]))
                pending_user = None

        contents: list[types.Content] = []
        for u_txt, a_txt in pairs[-3:]:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=u_txt)]))
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=a_txt)]))

        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=current_question)]))
        return contents

    def ask(self, question: str, mode: str = "analyst") -> dict[str, Any]:
        return self.ask_stream(question, mode=mode, on_event=None)

    def ask_stream(
        self,
        question: str,
        mode: str = "analyst",
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()

        def emit(ev_type: str, payload: dict[str, Any]) -> None:
            if on_event:
                try:
                    on_event(ev_type, payload)
                except Exception:
                    pass

        try:
            question = (question or "").strip()
            if not question:
                err = "متن پرسش خالی است."
                emit("error", {"error": err})
                return {"ok": False, "error": err}

            api_key = (Config.GEMINI_API_KEY or "").strip()
            if not api_key or api_key == "کلید_API_خود_را_اینجا_بگذارید":
                err = "کلید Gemini API در بخش «تنظیمات سیستم» ثبت نشده است."
                emit("error", {"error": err})
                return {"ok": False, "error": err}

            catalog = self._get_catalog_summary()
            if not catalog["files"]:
                err = "هنوز هیچ سندی در پایگاه داده پردازش نشده است."
                emit("error", {"error": err})
                return {"ok": False, "error": err}

            recent_history = self.get_chat_history(limit=10)
            self._save_message("user", question, mode=mode)

            citations_map: dict[str, dict[str, Any]] = {}
            collected_tables: list[dict[str, Any]] = []
            used_tools: list[str] = []
            state_lock = threading.Lock()
            sql_repair_count = 0

            # Build quick schema lookup for instant Self-Healing error feedback
            table_schema_lookup: dict[str, list[str]] = {}
            for t in catalog.get("tables", []):
                table_schema_lookup[t["table_name"]] = list(t.get("columns") or [])
            for v in catalog.get("unified_views", []):
                table_schema_lookup[v["view_name"]] = list(v.get("columns") or [])
            table_schema_lookup["smart_teachers_exploded"] = [
                "فایل_منبع", "بخش_منبع", "نام_دوره", "نام_استاد_خام", "نام_معیار_استاد",
                "نوع_برگزاری", "تعداد_اساتید_دوره", "تعداد_شرکت_کنندگان", "سهم_تعدیل_شده_مخاطب", "همکاران_مشترک"
            ]

            def record_tool(label: str) -> None:
                with state_lock:
                    if label not in used_tools:
                        used_tools.append(label)
                        emit("tool", {"label": label})

            def search_documents(query: str, top_k: int = 6) -> dict[str, Any]:
                """جست‌وجوی سریع در متن کامل اسناد نمایه‌شده (PDF، Word، PowerPoint، Excel، Access)."""
                record_tool("جست‌وجو در اسناد (LanceDB)")
                emit("status", {"text": f"در حال جست‌وجو در اسناد برای «{query[:28]}»..."})
                chunks = self._load_all_chunks()
                if not chunks:
                    return {"results": []}

                norm_q = normalize_fa(query)
                tokens = [t for t in norm_q.split() if len(t) >= 2]

                scored = []
                for item in chunks:
                    hay = item.get("_norm", "")
                    score = 0.0
                    if norm_q and norm_q in hay:
                        score += 14.0
                    for tok in tokens:
                        cnt = hay.count(tok)
                        if cnt > 0:
                            score += 2.5 + min(cnt, 5) * 0.5
                    scored.append((score, item))

                scored.sort(key=lambda x: x[0], reverse=True)
                k = max(1, min(int(top_k or 6), 12))
                picked = [it for sc, it in scored if sc > 0][:k]
                if not picked:
                    picked = [it for _, it in scored[:min(k, len(scored))]]

                results = []
                for item in picked:
                    cid = str(item.get("chunk_id", ""))
                    with state_lock:
                        citations_map[cid] = {
                            "chunk_id": cid,
                            "file_name": item.get("file_name", ""),
                            "file_path": item.get("file_path", ""),
                            "file_type": item.get("file_type", ""),
                            "location": item.get("location", ""),
                            "snippet": (item.get("content", "") or "")[:240],
                        }
                    results.append({
                        "file_name": item.get("file_name", ""),
                        "location": item.get("location", ""),
                        "content": (item.get("content", "") or "")[:1600],
                    })
                return {"matched": len(results), "results": results}

            def get_document_location(file_name: str, location_keyword: str) -> dict[str, Any]:
                """خواندن مستقیم متن یک اسلاید، صفحه یا شیت مشخص."""
                record_tool("مطالعه دقیق صفحه/اسلاید")
                emit("status", {"text": f"در حال خواندن {location_keyword}..."})
                chunks = self._load_all_chunks()
                f_norm = normalize_fa(file_name)
                l_norm = normalize_fa(location_keyword)
                matched = []

                for item in chunks:
                    if f_norm and f_norm not in item.get("_file_norm", ""):
                        continue
                    if l_norm and l_norm not in item.get("_loc_norm", ""):
                        continue
                    cid = str(item.get("chunk_id", ""))
                    with state_lock:
                        citations_map[cid] = {
                            "chunk_id": cid,
                            "file_name": item.get("file_name", ""),
                            "file_path": item.get("file_path", ""),
                            "file_type": item.get("file_type", ""),
                            "location": item.get("location", ""),
                            "snippet": (item.get("content", "") or "")[:240],
                        }
                    matched.append({
                        "file_name": item.get("file_name", ""),
                        "location": item.get("location", ""),
                        "content": item.get("content", ""),
                    })
                return {"matched": len(matched), "results": matched[:8]}

            def inspect_table_values(
                table_name: str, column_name: str = "", search_hint: str = ""
            ) -> dict[str, Any]:
                """مشاهده نام دقیق ستون‌ها و مقادیر یکتای یک جدول یا نمای تجمیعی برای اطمینان از املای نام اساتید، کارگروه‌ها یا دسته‌بندی‌ها."""
                record_tool("بررسی ساختار و مقادیر جدول")
                t_clean = (table_name or "").strip().strip('"').strip("'")
                if t_clean not in table_schema_lookup:
                    return {
                        "error": f"جدول یا نمای «{t_clean}» یافت نشد.",
                        "available_tables": list(table_schema_lookup.keys())[:20],
                    }

                cols = table_schema_lookup[t_clean]
                if not column_name:
                    return {"table": t_clean, "columns": cols}

                c_clean = column_name.strip().strip('"').strip("'")
                if c_clean not in cols:
                    return {
                        "error": f"ستون «{c_clean}» در جدول «{t_clean}» وجود ندارد.",
                        "valid_columns": cols,
                    }

                safe_t = t_clean.replace('"', '""')
                safe_c = c_clean.replace('"', '""')
                with self._db_lock:
                    con = self._connect_duckdb()
                    try:
                        register_persian_macros(con)
                        if search_hint and search_hint.strip():
                            hint_esc = search_hint.strip().replace("'", "''")
                            q = (
                                f'SELECT "{safe_c}" AS val, COUNT(*) AS cnt '
                                f'FROM "{safe_t}" '
                                f'WHERE "{safe_c}" IS NOT NULL '
                                f"AND fa_norm(\"{safe_c}\") LIKE '%' || fa_norm('{hint_esc}') || '%' "
                                f'GROUP BY "{safe_c}" ORDER BY cnt DESC LIMIT 35'
                            )
                        else:
                            q = (
                                f'SELECT "{safe_c}" AS val, COUNT(*) AS cnt '
                                f'FROM "{safe_t}" '
                                f'WHERE "{safe_c}" IS NOT NULL '
                                f'GROUP BY "{safe_c}" ORDER BY cnt DESC LIMIT 35'
                            )
                        vals = [{"value": r[0], "count": int(r[1])} for r in con.execute(q).fetchall()]
                        return {"table": t_clean, "column": c_clean, "distinct_values": vals}
                    except Exception as exc:
                        return {"error": f"خطا در بررسی مقادیر: {exc}", "valid_columns": cols}
                    finally:
                        con.close()

            def run_sql_query(sql_query: str, title: str = "نتیجه تحلیل جدولی") -> dict[str, Any]:
                """اجرای امن و قطعی کوئری تحلیلی SELECT یا WITH روی جداول و نماهای تجمیعی DuckDB (مجهز به fa_num و fa_norm و خودترمیمی)."""
                nonlocal sql_repair_count
                record_tool("تحلیل آماری هوشمند")
                emit("status", {"text": f"در حال محاسبه دقیق آماری: {title[:32]}..."})

                ok_sql, clean_or_err = SafeDuckDBExecutor.validate_readonly_sql(sql_query)
                if not ok_sql:
                    return {
                        "error": clean_or_err,
                        "self_healing_hint": "فقط یک کوئری خواندنی SELECT یا WITH بدون کاراکتر ; میانی ارسال کن.",
                    }

                clean_sql = clean_or_err
                with self._db_lock:
                    con = self._connect_duckdb()
                    try:
                        register_persian_macros(con)
                        rel = con.execute(clean_sql)
                        columns = [desc[0] for desc in rel.description] if rel.description else []
                        fetched = rel.fetchmany(501)
                        truncated = len(fetched) > 500
                        raw_rows = fetched[:500]

                        formatted_rows = [
                            [
                                "" if v is None else (int(v) if isinstance(v, float) and v.is_integer() else (round(v, 2) if isinstance(v, float) else v))
                                for v in row
                            ]
                            for row in raw_rows[:250]
                        ]
                    except Exception as exc:
                        sql_repair_count += 1
                        logger.warning("SQL self-healing triggered (attempt %d): %s | SQL=%s", sql_repair_count, exc, clean_sql[:300])
                        emit("status", {"text": "در حال اصلاح خودکار کوئری آماری..."})

                        ref_names = list(dict.fromkeys(re.findall(r"\b(?:tbl_[a-f0-9]+|view_merged_\d+)\b", clean_sql)))
                        ref_schemas = {rn: table_schema_lookup[rn] for rn in ref_names if rn in table_schema_lookup}
                        if not ref_schemas:
                            ref_schemas = {k: v for k, v in list(table_schema_lookup.items())[:8]}

                        return {
                            "error": f"خطای DuckDB: {exc}",
                            "referenced_tables_exact_columns": ref_schemas,
                            "self_healing_hint": (
                                "کوئری خطا داد. بدون اطلاع به کاربر، دقیقاً با استفاده از نام واقعی ستون‌های بالا "
                                "(درون دبل‌کوتیشن \"...\")، تبدیل ستون‌های عددی با fa_num(\"ستون\") و فیلتر فارسی با fa_norm(\"ستون\")، "
                                "کوئری را اصلاح کرده و دوباره run_sql_query را اجرا کن."
                            ),
                        }
                    finally:
                        con.close()

                det_stats = SafeDuckDBExecutor.compute_deterministic_stats(columns, raw_rows)

                # Zero-row Persian self-healing hint
                if len(raw_rows) == 0 and "WHERE" in clean_sql.upper():
                    used_fa_norm = "FA_NORM" in clean_sql.upper()
                    sql_repair_count += 1
                    emit("status", {"text": "تطبیق دقیق نتیجه‌ای نداد؛ بررسی شکل‌های نگارشی فارسی..."})
                    return {
                        "total_rows": 0,
                        "columns": columns,
                        "rows": [],
                        "self_healing_hint": (
                            "کوئری ۰ ردیف برگرداند. احتمالاً املای عبارت جستجو در دیتابیس کمی متفاوت است "
                            "(مثلاً نام کوچک/لقب، ی/ي، نیم‌فاصله). "
                            + (
                                "ابتدا با ابزار inspect_table_values مقادیر واقعی ستون را ببین یا عبارت کوتاه‌تر (مثل نام خانوادگی) را با fa_norm و LIKE جستجو کن."
                                if used_fa_norm
                                else "کوئری را با fa_norm(\"ستون\") LIKE '%' || fa_norm('کلمه کلیدی') || '%' اصلاح و دوباره اجرا کن."
                            )
                        ),
                    }

                if columns and formatted_rows:
                    with state_lock:
                        collected_tables.append({
                            "title": title or "نتیجه تحلیل جدولی",
                            "columns": columns,
                            "rows": formatted_rows,
                            "total_rows": len(raw_rows),
                            "sql": clean_sql,
                        })

                used_tbls = list(dict.fromkeys(re.findall(r"\btbl_[a-f0-9]+\b", clean_sql)))
                used_views = list(dict.fromkeys(re.findall(r"\bview_merged_\d+\b", clean_sql)))
                for vn in used_views:
                    v_meta = next((v for v in catalog.get("unified_views", []) if v["view_name"] == vn), None)
                    if v_meta:
                        for st_tbl in v_meta.get("source_tables", [])[:6]:
                            if st_tbl not in used_tbls:
                                used_tbls.append(st_tbl)

                if used_tbls:
                    all_chunks = self._load_all_chunks()
                    for t_name in used_tbls[:6]:
                        meta = next((t for t in catalog["tables"] if t["table_name"] == t_name), None)
                        if not meta:
                            continue
                        f_name = meta["file_name"]
                        s_sheet = meta["source_sheet"]
                        s_norm = normalize_fa(s_sheet.split("(")[0])
                        linked = next(
                            (c for c in all_chunks if c.get("file_name") == f_name and s_norm in c.get("_loc_norm", "")),
                            None,
                        )
                        if linked:
                            cid = str(linked.get("chunk_id", ""))
                            with state_lock:
                                if cid not in citations_map:
                                    citations_map[cid] = {
                                        "chunk_id": cid,
                                        "file_name": f_name,
                                        "file_path": linked.get("file_path", ""),
                                        "file_type": linked.get("file_type", ""),
                                        "location": linked.get("location", s_sheet),
                                        "snippet": (linked.get("content", "") or "")[:240],
                                    }

                resp_payload: dict[str, Any] = {
                    "total_rows": len(raw_rows),
                    "truncated_at_500": truncated,
                    "columns": columns,
                    "rows": formatted_rows[:60],
                    "deterministic_stats": det_stats,
                }
                if truncated:
                    resp_payload["note"] = "خروجی بیش از ۵۰۰ ردیف داشت و محدود شد؛ برای جمع یا شمارش دقیق کل، حتماً از SUM/COUNT/GROUP BY در SQL استفاده کن."
                return resp_payload

            def save_user_rule(rule_text: str, scope: str = "general") -> dict[str, Any]:
                """ذخیره یک قانون دائمی جدید که کاربر در چت آموزش می‌دهد (مثلاً دسته‌بندی فاکتورها، واحد پول یا نحوه تجمیع کارگروه‌ها) تا در تمام گزارش‌های آینده خودکار اعمال شود."""
                record_tool("ثبت قانون دائمی در حافظه")
                emit("status", {"text": "در حال ذخیره قانون جدید در حافظه دائمی..."})
                return _mem_add_rule(rule_text=rule_text, scope=scope, db_path=self.duckdb_path)

            def save_entity_alias(
                canonical_name: str, alias_name: str, entity_type: str = "teacher"
            ) -> dict[str, Any]:
                """ثبت دائمی یکسان بودن دو نام یا عنوان (مثل دو املای متفاوت یک استاد، کارگروه یا فروشنده) تا از این پس آمارشان همیشه تجمیع شود."""
                record_tool("ثبت نام معادل در حافظه")
                emit("status", {"text": f"در حال ذخیره تطبیق «{alias_name[:24]}» به «{canonical_name[:24]}»..."})
                return _mem_save_alias(
                    canonical_name=canonical_name,
                    alias_name=alias_name,
                    entity_type=entity_type,
                    status="approved",
                    confidence=1.0,
                    db_path=self.duckdb_path,
                )

            tool_registry = {
                "search_documents": search_documents,
                "get_document_location": get_document_location,
                "inspect_table_values": inspect_table_values,
                "run_sql_query": run_sql_query,
                "save_user_rule": save_user_rule,
                "save_entity_alias": save_entity_alias,
            }

            mode_instruction = MODE_PROMPTS.get(mode, MODE_PROMPTS["analyst"])
            knowledge_map = self._build_scalable_knowledge_map(catalog, question)

            system_prompt = f"""تو مغز متفکر تحلیلی و دستیار ارشد هوش مصنوعی «پنل مدیریت مؤسسه امام هادی» هستی.
وظیفه تو پاسخ‌دهی فوق‌العاده دقیق، مستند، خودترمیم و مدیریتی به فارسی بر اساس داده‌ها و اسناد واقعی است.

{mode_instruction}

{knowledge_map}

قوانین قطعی دقت، مقیاس‌پذیری و خودترمیمی:
1. قانون صفر محاسبه ذهنی: هرگز جمع، میانگین، شمارش یا درصد را ذهنی حساب نکن. برای هر عدد از `run_sql_query` (ترجیحاً با SUM/COUNT/AVG/GROUP BY) استفاده کن و برای جمع‌بندی ردیف‌ها دقیقاً به `deterministic_stats` خروجی ابزار استناد کن.
2. اولویت نماهای تجمیعی: برای پرسش‌های سراسری روی جداول هم‌ساختار (مثل کل دوره‌ها، پرمخاطب‌ترین‌ها یا عملکرد اساتید)، مستقیم روی نمای تجمیعی (مثل `"view_merged_1"`) کوئری بنویس.
3. ماکروهای بومی فارسی:
   - برای تبدیل و محاسبه ستون‌های عددی/متنی حتماً از `fa_num("نام ستون")` استفاده کن.
   - برای جستجو و فیلتر متن‌های فارسی (نام استاد، دوره، کارگروه، شرح فاکتور) حتماً از `fa_norm("نام ستون") LIKE '%' || fa_norm('عبارت') || '%'` استفاده کن.
   - برای تطبیق و شمارش یکتای شرکت‌کنندگان بر اساس موبایل یا کد ملی، حتماً از `fa_mobile("ستون")` و `fa_nid("ستون")` استفاده کن.
   - در جداول مالی و اکسل خام، همیشه ردیف‌های خلاصه/جمع‌بندی پایین فایل (مثل «جمع کل» یا «مجموع») را در WHERE حذف کن تا جمع‌ها دو برابر نشوند، و اگر واحدهای تومان و ریال مخلوط بودند بدون تبدیل جمع نبند.
4. حلقه خودترمیمی بی‌سروصدا: اگر `run_sql_query` خطا داد یا ۰ ردیف برگرداند، هرگز خطای SQL را به کاربر نشان نده و سریع ناامید نشو؛ با کمک `inspect_table_values` یا `referenced_tables_exact_columns` کوئری را اصلاح کن و دوباره اجرا بگیر.
5. هرگز نام فنی جداول (`tbl_...`) یا واژه `SQL` را در متن پاسخ نهایی برای مدیر نیاور؛ به جای آن نام خوانای فایل و اسلاید/شیت منبع را بنویس.
6. قوانین حافظه دائمی و رفع ابهام از کاربر:
   - هرگاه در داده‌ها به نام‌های بسیار شبیه (مثل دو شکل نگارشی یک استاد) یا ابهام در واحد پول (تومان/ریال) یا چند اسلاید مربوط به یک کارگروه برخوردی که هنوز در حافظه ثبت نشده، ضمن ارائه دقیق‌ترین محاسبه ممکن، شفاف به کاربر بگو و بپرس آیا می‌خواهد آن را به عنوان قانون دائمی ذخیره کنی.
   - هرگاه کاربر در چت قانونی به تو یاد داد یا تأیید کرد دو نام یکی هستند، بلافاصله ابزار `save_user_rule` یا `save_entity_alias` را صدا بزن و ثبت دائمی آن را تأیید کن.
   - هنگام مقایسه کارگروه‌ها، از بخش «نگاشت عنوان واقعی بخش‌ها و اسلایدها» استفاده کن تا نام واقعی کارگروه نمایش داده شود و اگر یک کارگروه در دو اسلاید پخش شده، آمار آن‌ها را جمع بزن.
7. پاسخ نهایی را به فارسی فصیح، با تیترهای تمیز، بولت‌پوینت و جدول Markdown منظم ارائه کن.
"""

            contents = self._build_clean_history_contents(recent_history, question)
            client = self._get_client(api_key)
            primary_model = (Config.GEMINI_MODEL or "gemini-3.8-flash").strip()
            candidate_models = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
            model_idx = 0

            def make_config(mdl: str, use_thinking: bool) -> types.GenerateContentConfig:
                kwargs: dict[str, Any] = {
                    "system_instruction": system_prompt,
                    "tools": [search_documents, run_sql_query, inspect_table_values, get_document_location, save_user_rule, save_entity_alias],
                    "temperature": 0.15,
                }
                if hasattr(types, "AutomaticFunctionCallingConfig"):
                    kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
                if use_thinking:
                    tc = self._build_thinking_config(mdl, mode)
                    if tc is not None:
                        kwargs["thinking_config"] = tc
                return types.GenerateContentConfig(**kwargs)

            def run_stream_once(mdl: str, use_thinking: bool):
                raw_parts: list[Any] = []
                fcs: list[Any] = []
                txt_chunks: list[str] = []
                stream = client.models.generate_content_stream(
                    model=mdl,
                    contents=contents,
                    config=make_config(mdl, use_thinking),
                )
                for chunk in stream:
                    cands = getattr(chunk, "candidates", None) or []
                    if not cands:
                        continue
                    content_obj = getattr(cands[0], "content", None)
                    parts = getattr(content_obj, "parts", None) or []
                    for part in parts:
                        raw_parts.append(part)
                        fc = getattr(part, "function_call", None)
                        if fc:
                            fcs.append(fc)
                        elif getattr(part, "text", None):
                            if getattr(part, "thought", False):
                                continue
                            txt_chunks.append(part.text)
                            emit("token", {"text": part.text})
                return raw_parts, fcs, txt_chunks

            emit("status", {"text": f"در حال ارتباط با {candidate_models[model_idx]}..."})

            final_text_parts: list[str] = []
            for _round in range(8):
                raw_model_parts: list[Any] = []
                function_calls: list[Any] = []
                turn_text_chunks: list[str] = []

                while True:
                    active_model = candidate_models[model_idx]
                    use_thinking = active_model not in self._no_thinking_models
                    try:
                        raw_model_parts, function_calls, turn_text_chunks = run_stream_once(
                            active_model, use_thinking
                        )
                        if active_model != primary_model:
                            record_tool(f"مدل فعال: {active_model}")
                        break
                    except Exception as stream_exc:
                        err_low = str(stream_exc).lower()
                        if use_thinking and ("thinking" in err_low or "invalid_argument" in err_low or "400" in err_low):
                            self._no_thinking_models.add(active_model)
                            continue
                        if self._is_failover_error(stream_exc) and not turn_text_chunks and (model_idx + 1) < len(candidate_models):
                            model_idx += 1
                            next_model = candidate_models[model_idx]
                            emit("status", {"text": f"سرور {active_model} موقتاً شلوغ است؛ انتقال خودکار به {next_model}..."})
                            continue
                        raise

                if turn_text_chunks:
                    final_text_parts.extend(turn_text_chunks)

                if not function_calls:
                    break

                contents.append(types.Content(role="model", parts=raw_model_parts))

                def exec_one(fc_obj):
                    fn_name = fc_obj.name
                    fn_args = dict(fc_obj.args or {})
                    fn = tool_registry.get(fn_name)
                    if not fn:
                        res = {"error": f"ابزار ناشناخته: {fn_name}"}
                    else:
                        try:
                            res = fn(**fn_args)
                            if not isinstance(res, dict):
                                res = {"result": res}
                        except Exception as ex:
                            logger.exception("Tool %s failed", fn_name)
                            res = {"error": str(ex)}
                    fr_kwargs = {"name": fn_name, "response": res}
                    fc_id = getattr(fc_obj, "id", None)
                    if fc_id:
                        fr_kwargs["id"] = fc_id
                    return types.Part(function_response=types.FunctionResponse(**fr_kwargs))

                if len(function_calls) == 1:
                    response_parts = [exec_one(function_calls[0])]
                else:
                    with ThreadPoolExecutor(max_workers=min(4, len(function_calls))) as pool:
                        response_parts = list(pool.map(exec_one, function_calls))

                contents.append(types.Content(role="user", parts=response_parts))
                emit("status", {"text": "در حال تحلیل نتایج و نگارش پاسخ نهایی..."})

            if sql_repair_count > 0:
                record_tool(f"خودترمیمی خودکار ({sql_repair_count})")

            answer_text = "".join(final_text_parts).strip()
            if not answer_text and collected_tables:
                first_t = collected_tables[0]
                t_cols = first_t.get("columns") or []
                t_rows = first_t.get("rows") or []
                if t_cols and t_rows:
                    hdr = "| " + " | ".join(str(c) for c in t_cols) + " |"
                    sep = "| " + " | ".join("---" for _ in t_cols) + " |"
                    body = "\n".join(
                        "| " + " | ".join(str(v) for v in r) + " |" for r in t_rows[:25]
                    )
                    answer_text = f"### {first_t.get('title', 'نتیجه تحلیل')}\n\n{hdr}\n{sep}\n{body}"
            if not answer_text:
                answer_text = "پاسخی از مدل دریافت نشد. لطفاً سوال را مجدد ارسال کنید."

            citations_list = list(citations_map.values())[:8]
            saved_ai = self._save_message(
                role="assistant",
                content=answer_text,
                mode=mode,
                citations=citations_list,
                tables=collected_tables,
                tools=used_tools,
            )
            elapsed = round(time.perf_counter() - t0, 1)
            emit("done", {"message": saved_ai, "elapsed": elapsed})
            return {"ok": True, "message": saved_ai, "elapsed": elapsed}

        except Exception as exc:
            logger.exception("InstitutionalAIAgent.ask_stream error")
            if self._is_failover_error(exc):
                err_msg = "سرورهای گوگل در حال حاضر با ترافیک بالا مواجه هستند و همه مدل‌های جایگزین نیز موقتاً شلوغ بودند. لطفاً چند ثانیه دیگر دوباره امتحان کنید."
            else:
                err_msg = f"خطا در ارتباط با Gemini: {exc}"
            emit("error", {"error": err_msg})
            return {"ok": False, "error": err_msg}

    @staticmethod
    def export_table_to_excel(table_data: dict[str, Any], dest_path: Path) -> str:
        wb = Workbook()
        ws = wb.active
        raw_title = re.sub(r'[\\/*?:\[\]]', '', str(table_data.get("title") or "گزارش"))[:28].strip()
        ws.title = raw_title or "گزارش"
        ws.views.sheetView[0].rightToLeft = True

        columns = table_data.get("columns", [])
        rows = table_data.get("rows", [])

        header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        _br = load_branding()
        _ef = str(_br.get("excel_font") or "Tahoma").strip() or "Tahoma"
        _et = str(table_data.get("title") or _br.get("excel_default_title") or "گزارش").strip()
        ws.title = re.sub(r'[\\/*?:\[\]]', '', _et)[:28].strip() or "گزارش"
        header_font = Font(name=_ef, size=11, bold=True, color="FFFFFF")
        body_font = Font(name=_ef, size=10, color="1E293B")
        zebra_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        thin = Side(border_style="thin", color="CBD5E1")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        ws.append(columns)
        ws.row_dimensions[1].height = 28
        for col_idx in range(1, len(columns) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border

        for r_idx, row in enumerate(rows, start=2):
            cleaned_row = []
            for val in row:
                if isinstance(val, (int, float)):
                    cleaned_row.append(val)
                    continue
                s = str(val).strip() if val is not None else ""
                s_en = s.translate(PERSIAN_TO_EN).replace(",", "").replace("٬", "")
                if re.fullmatch(r"-?\d+", s_en):
                    cleaned_row.append(int(s_en))
                elif re.fullmatch(r"-?\d+\.\d+", s_en):
                    cleaned_row.append(float(s_en))
                else:
                    cleaned_row.append(val)

            ws.append(cleaned_row)
            ws.row_dimensions[r_idx].height = 22
            for c_idx in range(1, len(columns) + 1):
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.font = body_font
                cell.border = border
                cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
                if r_idx % 2 == 1:
                    cell.fill = zebra_fill

        for col_idx in range(1, len(columns) + 1):
            col_letter = get_column_letter(col_idx)
            max_len = max(
                (len(str(ws.cell(row=r, column=col_idx).value or "")) for r in range(1, ws.max_row + 1)),
                default=12,
            )
            ws.column_dimensions[col_letter].width = min(max(max_len + 6, 14), 48)

        wb.save(dest_path)
        return str(dest_path)
