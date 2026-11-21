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

from src.core.config import Config
from src.core.db_manager import (
    detect_duplicate_files,
    get_db_lock,
    normalize_persian,
)
from src.core.memory_engine import (
    add_rule as _mem_add_rule,
    build_memory_prompt_block as _mem_prompt_block,
    get_teacher_exact_stats as _mem_teacher_stats,
    init_memory_tables as _mem_init,
    load_brain_config as _mem_load_cfg,
    rebuild_clean_teacher_layer as _mem_rebuild_teachers,
    save_alias as _mem_save_alias,
)
from src.core.smart_brain import (
    SafeDuckDBExecutor,
    SemanticSchemaEngine,
    register_persian_macros,
)
from src.reports.report_studio import export_styled_table_excel

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
        "حالت فعال: تحلیلگر اجرایی هوشمند. پاسخ‌ها را دقیق، مستند، مستقیم و بدون حاشیه‌گویی بنویس."
    ),
    "board_report": (
        "حالت فعال: گزارش رسمی مدیریتی. ساختار شامل «خلاصه اجرایی»، «یافته‌های کلیدی»، «تحلیل روندها» و «پیشنهاد عملیاتی» باشد."
    ),
}

LENGTH_PROMPTS = {
    "concise": (
        "قانون اکید اختصار (فوق‌خلاصه): بدون سلام، تعارف یا تکرار سؤال، دقیقاً در همان خط اول عدد یا پاسخ اصلی را بده. "
        "حداکثر در ۲ تا ۴ خط فشرده و شفاف پاسخ بده و از پاراگراف‌های طولانی پرهیز کن. فقط اگر چند ردیف مقایسه‌ای لازم بود یک جدول کوچک بیاور."
    ),
    "balanced": (
        "سبک متعادل: مستقیم با جواب اصلی شروع کن (بدون مقدمه اضافی)، نکات کلیدی را در بولت‌های کوتاه یا جدول جمع‌وجور بیاور و متن را شلوغ نکن."
    ),
    "analytical": (
        "سبک تحلیلی کامل: بدون تعارف، پاسخ جامع شامل آمار دقیق، تفکیک روندها، شفافیت محاسبه و پیشنهاد عملیاتی ارائه کن."
    ),
}

# --- 4-Path Intent Gatekeeper Patterns ---
_GREETING_EXACT = {
    "سلام", "درود", "سلام علیکم", "سلام خوبی", "خوبی", "چطوری", "چه خبر",
    "خسته نباشی", "خسته نباشید", "صبح بخیر", "عصر بخیر", "شب بخیر",
    "مرسی", "ممنون", "سپاس", "متشکرم", "دستت درد نکنه", "دمت گرم", "عالی", "ممنونم",
    "تست", "test", "hi", "hello", "hey", "ping", "ok", "باشه", "اوکی",
}

_AMBIGUOUS_SHORT = {
    "آمار", "گزارش", "اطلاعات", "داده", "داده ها", "جدول", "لیست", "فهرست", "اسناد",
}

_INSTITUTIONAL_KEYWORDS = (
    "دوره", "دورها", "کلاس", "کارگروه", "استاد", "اساتید", "سخنران", "مدرس",
    "مخاطب", "مخاطبان", "مخاطبین", "شرکت کننده", "شرکت کنندگان", "حاضرین", "ثبت نام", "ثبت نامی",
    "مؤسسه", "موسسه", "امام هادی", "فاکتور", "هزینه", "مبلغ", "تومان", "ریال", "بودجه", "مالی", "خرید",
    "سند", "اسناد", "فایل", "اکسل", "اسلاید", "جدول", "دیتابیس", "پایگاه داده",
    "آمار", "تعداد", "مجموع", "جمع کل", "میانگین", "میانه", "نرخ بازگشت", "وفاداری",
    "رتبه", "پرمخاطب", "بیشترین", "کمترین", "مقایسه", "عملکرد", "ساعت تدریس", "ساعات تدریس",
    "تقسیم مساوی", "ساعت کامل", "حیدری", "پرس لاین", "دبیرخانه", "کارنامه", "نفر دوره", "نفردوره",
    "چند دوره", "چند نفر", "چند ساعت", "چند جلسه", "کدام استاد", "کدوم استاد", "کدام کارگروه",
    "گزارش دوره", "گزارش مالی", "گزارش آموزشی", "ادغام", "نام معادل", "قانون",
)

_FOLLOWUP_HINTS = (
    "فقط سال", "فقط کارگروه", "فقط استاد", "با تقسیم مساوی", "با ساعت کامل", "تفکیکی",
    "جدولش", "جزئیاتش", "منابعش", "ادامه", "بیشتر توضیح", "دقیق تر", "نه منظورم", "اون یکی",
    "همون", "همین", "برای سال", "در پاییز", "در بهار", "در تابستان", "در زمستان",
)

_PERSIAN_VOWELS_OR_COMMON = set("اآویهمنرستدکگلبپچجحخعغفقزژشضصطظ")


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


def _is_gibberish(raw_text: str) -> bool:
    """Detects keyboard mash, random symbols, or meaningless strings so the bot never fabricates stats."""
    s = (raw_text or "").strip()
    if not s:
        return True
    norm = normalize_fa(s)
    if not norm:
        return True
    # Pure punctuation / digits without letters
    letters = re.findall(r"[آ-یa-zA-Z]", norm)
    if not letters:
        return True
    # Single character or 2 identical chars
    if len(norm) <= 1 or (len(norm) <= 3 and len(set(norm.replace(" ", ""))) == 1):
        return True
    # Excessive repeated character runs (e.g. "سسسسسسس" or "اااااا")
    if re.search(r"(.)\1{4,}", norm):
        return True
    # Check Latin keyboard mash (no vowels in a long word)
    words = norm.split()
    if all(re.fullmatch(r"[a-z]+", w) for w in words):
        joined = "".join(words)
        if len(joined) >= 5 and not re.search(r"[aeiouy]", joined):
            return True
        if len(words) == 1 and len(joined) >= 6:
            # Known keyboard-row mashing patterns
            rows = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
            if any(sum(1 for ch in joined if ch in r) / len(joined) >= 0.85 for r in rows) and joined not in ("status", "report", "delete", "update", "export", "import", "search", "salary"):
                return True
    # Persian keyboard mash (long single token with high adjacent-key ratio or bizarre consonant cluster)
    if len(words) == 1 and len(words[0]) >= 6 and re.fullmatch(r"[آ-ی]+", words[0]):
        w = words[0]
        fa_rows = ("ضصثقفغعهخحجچ", "شسیبلاتنمکگ", "ظطزرذدپو")
        for r in fa_rows:
            if sum(1 for ch in w if ch in r) / len(w) >= 0.88 and len(set(w)) >= 4:
                # Avoid false positives on real Persian words by checking common endings/bigrams
                if not any(sub in w for sub in ("ان", "ها", "ای", "ار", "ون", "ین", "ات", "ست", "اد", "ور")):
                    return True
    return False


def classify_chat_intent(
    question: str,
    route_mode: str = "auto",
    recent_history: list[dict[str, Any]] | None = None,
    known_entities: set[str] | None = None,
) -> dict[str, Any]:
    """
    4-Path Smart Gatekeeper:
    Returns {intent: 'greeting'|'gibberish'|'ambiguous_short'|'institutional'|'free', hours_override: str}
    """
    q_clean = (question or "").strip()
    q_norm = normalize_fa(q_clean)

    # Detect inline hours policy override inside question
    hours_ov = ""
    if "تقسیم مساوی" in q_norm or "مساوی حساب" in q_norm:
        hours_ov = "equal"
    elif "ساعت کامل" in q_norm or "کامل حساب" in q_norm:
        hours_ov = "full"
    elif "تفکیکی" in q_norm and "ساعت" in q_norm:
        hours_ov = "split"

    # Explicit user route locks override auto-detection (except pure gibberish)
    if route_mode == "free":
        if _is_gibberish(q_clean):
            return {"intent": "gibberish", "hours_override": ""}
        return {"intent": "free", "hours_override": ""}

    if _is_gibberish(q_clean):
        return {"intent": "gibberish", "hours_override": ""}

    if q_norm in _GREETING_EXACT or (len(q_norm.split()) <= 3 and any(q_norm.startswith(g + " ") and len(q_norm) <= 18 for g in ("سلام", "مرسی", "ممنون", "خسته نباشی"))):
        if not any(kw in q_norm for kw in _INSTITUTIONAL_KEYWORDS):
            return {"intent": "greeting", "hours_override": ""}

    if route_mode == "institutional":
        if q_norm in _AMBIGUOUS_SHORT:
            return {"intent": "ambiguous_short", "hours_override": hours_ov}
        return {"intent": "institutional", "hours_override": hours_ov}

    # --- AUTO mode ---
    if q_norm in _AMBIGUOUS_SHORT:
        return {"intent": "ambiguous_short", "hours_override": hours_ov}

    # 1. Institutional keyword match
    if any(kw in q_norm for kw in _INSTITUTIONAL_KEYWORDS):
        return {"intent": "institutional", "hours_override": hours_ov}

    # 2. Known entity (teacher/file/workgroup token) match
    if known_entities:
        q_tokens = [t for t in q_norm.split() if len(t) >= 4]
        for tok in q_tokens:
            if tok in known_entities:
                return {"intent": "institutional", "hours_override": hours_ov}

    # 3. Short follow-up to an institutional conversation
    if recent_history and any(h in q_norm for h in _FOLLOWUP_HINTS):
        last_ai = next((m for m in reversed(recent_history) if m.get("role") == "assistant"), None)
        if last_ai and (last_ai.get("response_scope") == "institutional" or last_ai.get("tables") or last_ai.get("citations")):
            return {"intent": "institutional", "hours_override": hours_ov}

    # 4. Otherwise -> completely free general assistant (zero DB touch!)
    return {"intent": "free", "hours_override": ""}


def _group_citations_by_file(citations_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Groups multiple rows/locations from the same file into a single clean citation entry."""
    grouped: dict[str, dict[str, Any]] = {}
    for c in citations_map.values():
        fn = str(c.get("file_name") or "سند")
        loc = str(c.get("location") or "").strip()
        if fn not in grouped:
            grouped[fn] = {
                "chunk_id": c.get("chunk_id", ""),
                "file_name": fn,
                "file_path": c.get("file_path", ""),
                "file_type": c.get("file_type", ""),
                "location": loc,
                "locations": [loc] if loc else [],
                "snippet": c.get("snippet", ""),
            }
        else:
            if loc and loc not in grouped[fn]["locations"]:
                grouped[fn]["locations"].append(loc)
                grouped[fn]["location"] = " ، ".join(grouped[fn]["locations"][:6]) + (
                    f" (+{len(grouped[fn]['locations']) - 6})" if len(grouped[fn]["locations"]) > 6 else ""
                )
    return list(grouped.values())[:8]


class InstitutionalAIAgent:
    """موتور هوش مصنوعی سازمانی v48.0 Pro با دروازه‌بان ۴مسیره، تفکیک مطلق مؤسسه از آزاد، خودترمیمی SQL و کنترل اختصار"""

    def __init__(self):
        Config.ensure_directories()
        self.duckdb_path = str(Config.DUCKDB_PATH)
        self.lancedb_path = str(Config.LANCEDB_PATH)
        self._db_lock = get_db_lock(self.duckdb_path)
        self._cache_lock = threading.Lock()

        self._client: genai.Client | None = None
        self._client_key: str = ""
        self._chunks_cache: list[dict[str, Any]] | None = None
        self._catalog_cache: dict[str, Any] | None = None
        self._known_entity_tokens: set[str] | None = None
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
                        created_at VARCHAR,
                        meta_json VARCHAR DEFAULT '{}'
                    )
                """)
                cols = {c[0] for c in con.execute("DESCRIBE chat_history").fetchall()}
                if "meta_json" not in cols:
                    try:
                        con.execute("ALTER TABLE chat_history ADD COLUMN meta_json VARCHAR DEFAULT '{}'")
                    except Exception:
                        pass
            finally:
                con.close()

    def invalidate_cache(self) -> None:
        with self._cache_lock:
            self._chunks_cache = None
            self._catalog_cache = None
            self._known_entity_tokens = None
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
                self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=45000))
            except Exception:
                self._client = genai.Client(api_key=api_key)
            self._client_key = api_key
            return self._client

    def warmup(self) -> None:
        try:
            self._get_catalog_summary()
            self._get_known_entity_tokens()
            with self._db_lock:
                self._schema_engine.get_profiles()
            self._load_all_chunks()
            key = (Config.GEMINI_API_KEY or "").strip()
            if key and key != "کلید_API_خود_را_اینجا_بگذارید":
                self._get_client(key)
        except Exception as exc:
            logger.warning("Warmup warning: %s", exc)

    def _get_known_entity_tokens(self) -> set[str]:
        with self._cache_lock:
            if self._known_entity_tokens is not None:
                return self._known_entity_tokens
        tokens: set[str] = set()
        try:
            with self._db_lock:
                con = self._connect_duckdb()
                try:
                    tbls = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
                    if "smart_teachers_exploded" in tbls:
                        rows = con.execute('SELECT DISTINCT "نام_معیار_استاد", "کارگروه" FROM smart_teachers_exploded LIMIT 300').fetchall()
                        for t, w in rows:
                            for txt in (t, w):
                                for tok in normalize_fa(str(txt or "")).split():
                                    if len(tok) >= 4 and tok not in ("حجت", "الاسلام", "المسلمین", "استاد", "دکتر", "کارگروه", "آقای", "خانم"):
                                        tokens.add(tok)
                finally:
                    con.close()
        except Exception:
            pass
        with self._cache_lock:
            self._known_entity_tokens = tokens
        return tokens

    def get_chat_history(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._db_lock:
            con = self._connect_duckdb()
            try:
                cols = {c[0] for c in con.execute("DESCRIBE chat_history").fetchall()}
                if "meta_json" in cols:
                    rows = con.execute("""
                        SELECT id, role, content, mode, citations_json, tables_json, tools_json, created_at, meta_json
                        FROM chat_history ORDER BY id ASC
                    """).fetchall()
                else:
                    rows = [(*r, "{}") for r in con.execute("""
                        SELECT id, role, content, mode, citations_json, tables_json, tools_json, created_at
                        FROM chat_history ORDER BY id ASC
                    """).fetchall()]
            finally:
                con.close()

        items = []
        for r in rows[-limit:]:
            meta = {}
            try:
                meta = json.loads(r[8] or "{}")
            except Exception:
                meta = {}
            cites = json.loads(r[4] or "[]")
            tbls = json.loads(r[5] or "[]")
            scope = meta.get("response_scope") or ("institutional" if (cites or tbls) else "free")
            items.append({
                "id": r[0], "role": r[1], "content": r[2], "mode": r[3] or "analyst",
                "citations": cites, "tables": tbls, "tools": json.loads(r[6] or "[]"),
                "created_at": r[7], "response_scope": scope,
                "kpis": meta.get("kpis") or [], "length_mode": meta.get("length_mode") or "concise",
                "transparency": meta.get("transparency") or "",
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
        response_scope: str = "institutional",
        kpis: list[dict[str, str]] | None = None,
        length_mode: str = "concise",
        transparency: str = "",
    ) -> dict[str, Any]:
        now_str = datetime.now().strftime("%H:%M")
        meta = {
            "response_scope": response_scope,
            "kpis": kpis or [],
            "length_mode": length_mode,
            "transparency": transparency,
        }
        with self._db_lock:
            con = self._connect_duckdb()
            try:
                max_id = con.execute("SELECT COALESCE(MAX(id), 0) FROM chat_history").fetchone()[0]
                new_id = int(max_id) + 1
                cols = {c[0] for c in con.execute("DESCRIBE chat_history").fetchall()}
                if "meta_json" in cols:
                    con.execute(
                        "INSERT INTO chat_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [new_id, role, content, mode, json.dumps(citations or [], ensure_ascii=False), json.dumps(tables or [], ensure_ascii=False), json.dumps(tools or [], ensure_ascii=False), now_str, json.dumps(meta, ensure_ascii=False)],
                    )
                else:
                    con.execute(
                        "INSERT INTO chat_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        [new_id, role, content, mode, json.dumps(citations or [], ensure_ascii=False), json.dumps(tables or [], ensure_ascii=False), json.dumps(tools or [], ensure_ascii=False), now_str],
                    )
            finally:
                con.close()

        return {
            "id": new_id, "role": role, "content": content, "mode": mode,
            "citations": citations or [], "tables": tables or [], "tools": tools or [],
            "created_at": now_str, "response_scope": response_scope,
            "kpis": kpis or [], "length_mode": length_mode, "transparency": transparency,
        }

    def _load_all_chunks(self) -> list[dict[str, Any]]:
        with self._cache_lock:
            if self._chunks_cache is not None:
                return self._chunks_cache
        try:
            db = lancedb.connect(self.lancedb_path)
            if "document_chunks" not in db.table_names():
                rows: list[dict[str, Any]] = []
            else:
                raw = db.open_table("document_chunks").to_pandas().to_dict(orient="records")
                rows = []
                for r in raw:
                    item = dict(r)
                    item["_norm"] = normalize_fa(f"{item.get('file_name', '')} {item.get('location', '')} {item.get('content', '')}")
                    item["_loc_norm"] = normalize_fa(str(item.get("location", "")))
                    item["_file_norm"] = normalize_fa(str(item.get("file_name", "")))
                    rows.append(item)
        except Exception:
            rows = []
        with self._cache_lock:
            self._chunks_cache = rows
        return rows

    def get_chunk_by_id(self, chunk_id: str) -> dict[str, Any]:
        rows = self._load_all_chunks()
        if not rows:
            return {"ok": False, "error": "بانک متون خالی است."}
        for r in rows:
            if str(r.get("chunk_id")) == str(chunk_id):
                return {"ok": True, "chunk_id": r.get("chunk_id", ""), "file_name": r.get("file_name", ""), "file_path": r.get("file_path", ""), "file_type": r.get("file_type", ""), "location": r.get("location", ""), "content": r.get("content", "")}
        return {"ok": False, "error": "محتوای منبع یافت نشد."}

    def _build_unified_views(self, con: duckdb.DuckDBPyConnection, tables_meta: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for t in tables_meta:
            cols = t.get("columns") or []
            if len(cols) >= 2:
                groups.setdefault(tuple(normalize_fa(c) for c in cols), []).append(t)

        unified_views: list[dict[str, Any]] = []
        v_idx = 0
        for _sig, grp in groups.items():
            if len(grp) < 2:
                continue
            v_idx += 1
            view_name = f"view_merged_{v_idx}"
            canonical_cols = grp[0]["columns"]
            select_parts, total_rows, source_tables = [], 0, []
            for t in grp:
                t_name = t["table_name"]
                f_esc, s_esc = str(t["file_name"]).replace("'", "''"), str(t["source_sheet"]).replace("'", "''")
                col_exprs = [f'CAST("{oc.replace(chr(34), chr(34)*2)}" AS VARCHAR) AS "{cc.replace(chr(34), chr(34)*2)}"' for oc, cc in zip(t["columns"], canonical_cols)]
                select_parts.append(f"SELECT '{f_esc}' AS \"فایل_منبع\", '{s_esc}' AS \"بخش_منبع\", " + ", ".join(col_exprs) + f' FROM "{t_name}"')
                total_rows += int(t.get("rows_count") or 0)
                source_tables.append(t_name)
            try:
                con.execute(f'CREATE OR REPLACE VIEW "{view_name}" AS ' + " UNION ALL ".join(select_parts))
                unified_views.append({"view_name": view_name, "description": f"نمای تجمیعی خودکار ({len(grp)} جدول، {total_rows} ردیف)", "total_rows": total_rows, "columns": ["فایل_منبع", "بخش_منبع"] + canonical_cols, "source_tables": source_tables})
            except Exception as exc:
                logger.warning("Failed creating unified view %s: %s", view_name, exc)
        return unified_views

    def _get_catalog_summary(self) -> dict[str, Any]:
        with self._cache_lock:
            if self._catalog_cache is not None:
                return self._catalog_cache
        files, tables_meta, unified_views = [], [], []
        with self._db_lock:
            con = self._connect_duckdb()
            try:
                tbls = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
                if "processed_files" in tbls:
                    files = con.execute("SELECT file_name, file_type, chunks_count, tables_count, rows_count FROM processed_files WHERE status = 'موفق' ORDER BY file_name").fetchall()
                if "tabular_catalog" in tbls:
                    tables = con.execute("SELECT table_name, file_name, source_sheet, rows_count, columns_json FROM tabular_catalog ORDER BY file_name, source_sheet").fetchall()
                    tables_meta = [{"table_name": t[0], "file_name": t[1], "source_sheet": t[2], "rows_count": t[3], "columns": json.loads(t[4] or "[]")} for t in tables]
                    unified_views = self._build_unified_views(con, tables_meta)
            finally:
                con.close()

        summary = {
            "files": [{"file_name": f[0], "file_type": f[1], "chunks_count": f[2], "tables_count": f[3], "rows_count": f[4]} for f in files],
            "unified_views": unified_views, "tables": tables_meta,
        }
        try:
            _mem_rebuild_teachers(self.duckdb_path)
        except Exception:
            pass
        with self._cache_lock:
            self._catalog_cache = summary
        return summary

    def _build_scalable_knowledge_map(self, catalog: dict[str, Any], question: str) -> str:
        lines: list[str] = []
        files = catalog.get("files") or []
        lines.append(f"### ۱. فایل‌های پردازش‌شده ({len(files)} فایل)")
        for f in files[:25]:
            lines.append(f"- {f['file_name']} ({f['file_type']} | {f['tables_count']} جدول، {f['rows_count']} ردیف)")
        if len(files) > 25:
            lines.append(f"- و {len(files) - 25} فایل دیگر...")

        uviews = catalog.get("unified_views") or []
        if uviews:
            lines.append("\n### ۲. نماهای تجمیعی سریع")
            for v in uviews:
                cols_str = "، ".join(f'"{c}"' for c in (v.get("columns") or []))
                lines.append(f'- نمای `"{v["view_name"]}"`: {v["description"]} | ستون‌ها: {cols_str}')

        lines.append(
            "\n### ۳. جدول تمیز اساتید و دوره‌ها (`\"smart_teachers_exploded\"`)\n"
            "- ستون‌ها: `\"شناسه_دوره_یکتا\"`, `\"فایل_منبع\"`, `\"بخش_منبع\"`, `\"شماره_ردیف_منبع\"`, `\"نام_دوره\"`, `\"کارگروه\"`, "
            "`\"تاریخ_شمسی\"`, `\"سال_شمسی\"`, `\"فصل_شمسی\"`, `\"نام_معیار_استاد\"`, `\"نوع_برگزاری\"` (انفرادی/مشترک/گروهی), "
            "`\"تعداد_اساتید_دوره\"`, `\"تعداد_شرکت_کنندگان\"`, `\"مخاطب_معتبر\"`, `\"سهم_تعدیل_شده_مخاطب\"`, `\"تعداد_جلسات\"`, "
            "`\"ساعت_کل_دوره\"`, `\"ساعت_سهم_استاد\"`, `\"ساعت_مستقل\"`, `\"ساعت_مشترک\"`, `\"همکاران_مشترک\"`\n"
            "- برای آمار دقیق هر استاد، اولویت اول فراخوانی ابزار قطعی `get_teacher_exact_stats_tool` است (تحمل غلط تایپی و اعمال سیاست ساعات مشترک)."
        )
        with self._db_lock:
            lines.append("\n" + self._schema_engine.build_prompt_context(question=question, max_detailed_tables=10))
        try:
            mem_block = _mem_prompt_block(self.duckdb_path)
            if mem_block:
                lines.append("\n" + mem_block)
        except Exception:
            pass
        return "\n".join(lines)

    def test_connection(self, api_key: str | None = None, model: str | None = None) -> dict[str, Any]:
        key = (api_key if api_key is not None else Config.GEMINI_API_KEY).strip()
        mdl = (model if model is not None else Config.GEMINI_MODEL).strip() or "gemini-3.8-flash"
        if not key or key == "کلید_API_خود_را_اینجا_بگذارید":
            return {"ok": False, "error": "کلید Gemini API وارد نشده است."}
        try:
            client = genai.Client(api_key=key)
            resp = client.models.generate_content(model=mdl, contents="فقط کلمه «متصل» را برگردان.")
            return {"ok": True, "message": f"اتصال با مدل {mdl} برقرار است ({(resp.text or '').strip()[:30]})."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _build_thinking_config(self, model_name: str, mode: str):
        low = model_name.lower()
        if model_name in self._no_thinking_models or not hasattr(types, "ThinkingConfig") or "flash" not in low:
            return None
        try:
            if "gemini-3" in low:
                return types.ThinkingConfig(thinking_level=("LOW" if mode == "board_report" else "MINIMAL"))
            return types.ThinkingConfig(thinking_budget=256 if mode == "board_report" else 0)
        except Exception:
            return None

    @staticmethod
    def _is_failover_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(t in msg for t in ("503", "unavailable", "high demand", "overloaded", "429", "resource_exhausted", "quota", "404", "not_found", "timed out", "timeout"))

    @staticmethod
    def _build_clean_history_contents(recent_history: list[dict[str, Any]], current_question: str, target_scope: str) -> list[types.Content]:
        """Strictly isolates institutional history from free-chat history to prevent cross-contamination."""
        pairs: list[tuple[str, str]] = []
        pending_user: str | None = None
        for msg in recent_history:
            role = msg.get("role", "")
            text = (msg.get("content") or "").strip()
            if not text:
                continue
            scope = msg.get("response_scope") or "institutional"
            if role == "user":
                pending_user = text[:650]
            elif role == "assistant" and pending_user is not None:
                if scope == target_scope:
                    pairs.append((pending_user, text[:750]))
                pending_user = None
        contents: list[types.Content] = []
        for u_txt, a_txt in pairs[-3:]:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=u_txt)]))
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=a_txt)]))
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=current_question)]))
        return contents

    def ask(self, question: str, mode: str = "analyst", route_mode: str = "auto", length_mode: str = "concise") -> dict[str, Any]:
        return self.ask_stream(question, mode=mode, on_event=None, route_mode=route_mode, length_mode=length_mode)

    def ask_stream(
        self,
        question: str,
        mode: str = "analyst",
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        route_mode: str = "auto",
        length_mode: str = "concise",
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

            route_mode = route_mode if route_mode in ("auto", "institutional", "free") else "auto"
            length_mode = length_mode if length_mode in ("concise", "balanced", "analytical") else "concise"

            recent_history = self.get_chat_history(limit=12)
            known_ents = self._get_known_entity_tokens()
            gate = classify_chat_intent(question, route_mode=route_mode, recent_history=recent_history, known_entities=known_ents)
            intent = gate["intent"]
            inline_hours_policy = gate.get("hours_override") or ""

            # --- Fast local responses for gibberish / greetings / bare ambiguous 1-word queries (ZERO DB noise!) ---
            if intent in ("gibberish", "greeting", "ambiguous_short"):
                scope = "institutional" if intent == "ambiguous_short" else "free"
                self._save_message("user", question, mode=mode, response_scope=scope, length_mode=length_mode)
                if intent == "gibberish":
                    reply = "متوجه منظورت نشدم. اگر آمار یا گزارشی از اسناد مؤسسه می‌خواهی، یا کار عمومی (مثل نگارش نامه و ایده‌پردازی) داری، مستقیم بگو تا دقیق انجام بدهم."
                elif intent == "greeting":
                    q_n = normalize_fa(question)
                    if any(w in q_n for w in ("مرسی", "ممنون", "سپاس", "متشکر", "دمت گرم", "دستت درد")):
                        reply = "خواهش می‌کنم؛ هر زمان سؤال آماری یا کار دیگری داشتی در خدمتم."
                    elif "تست" in q_n or q_n in ("test", "ping"):
                        reply = "سامانه آماده است. سؤال آماری از اسناد مؤسسه یا هر درخواست عمومی دیگری داری بپرس."
                    else:
                        reply = "سلام! در خدمتم. چه آمار از اسناد مؤسسه بخواهی و چه کار عمومی (نگارش، ویرایش یا ایده‌پردازی)، مستقیم بگو."
                else:
                    reply = "دقیقاً کدام بخش از آمار مؤسسه را می‌خواهی؟ (مثلاً: «آمار دوره‌های یک استاد»، «مقایسه کارگروه‌ها» یا «گزارش هزینه‌ها»)"
                emit("token", {"text": reply})
                saved = self._save_message("assistant", reply, mode=mode, citations=[], tables=[], tools=[], response_scope=scope, length_mode=length_mode)
                elapsed = round(time.perf_counter() - t0, 1)
                emit("done", {"message": saved, "elapsed": elapsed})
                return {"ok": True, "message": saved, "elapsed": elapsed}

            api_key = (Config.GEMINI_API_KEY or "").strip()
            if not api_key or api_key == "کلید_API_خود_را_اینجا_بگذارید":
                err = "کلید Gemini API در بخش «تنظیمات سیستم» ثبت نشده است."
                emit("error", {"error": err})
                return {"ok": False, "error": err}

            client = self._get_client(api_key)
            primary_model = (Config.GEMINI_MODEL or "gemini-3.8-flash").strip()
            candidate_models = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]

            # ==================== PATH A: PURE FREE / GENERAL ASSISTANT (ZERO DB TOUCH) ====================
            if intent == "free":
                self._save_message("user", question, mode=mode, response_scope="free", length_mode=length_mode)
                len_rule = LENGTH_PROMPTS.get(length_mode, LENGTH_PROMPTS["concise"])
                free_sys = (
                    "تو یک دستیار هوش مصنوعی همه‌کاره، دقیق و خوش‌فکر به زبان فارسی هستی.\n"
                    f"{len_rule}\n"
                    "قوانین حیاتی:\n"
                    "1. این گفتگو در حالت «عمومی / آزاد» است؛ هیچ آماری درباره مؤسسه امام هادی از خودت نساز و ادعای دسترسی به اسناد داخلی در این حالت نکن.\n"
                    "2. اگر کاربر وسط این گفتگوی آزاد عدد یا آمار دقیق مؤسسه را خواست، خیلی کوتاه بگو حالت «اسناد مؤسسه» را فعال کند یا مستقیماً نام دوره/استاد را بپرسد.\n"
                    "3. پاسخ را مستقیم، تمیز، بدون مقدمه اضافی و خوانا بنویس."
                )
                contents = self._build_clean_history_contents(recent_history, question, target_scope="free")
                emit("status", {"text": "در حال پاسخ‌گویی..."})

                final_parts: list[str] = []
                model_idx = 0
                while True:
                    active_model = candidate_models[model_idx]
                    use_thinking = active_model not in self._no_thinking_models
                    try:
                        kw: dict[str, Any] = {"system_instruction": free_sys, "temperature": 0.45}
                        if use_thinking:
                            tc = self._build_thinking_config(active_model, mode)
                            if tc is not None:
                                kw["thinking_config"] = tc
                        stream = client.models.generate_content_stream(model=active_model, contents=contents, config=types.GenerateContentConfig(**kw))
                        for chunk in stream:
                            cands = getattr(chunk, "candidates", None) or []
                            if not cands:
                                continue
                            for part in (getattr(getattr(cands[0], "content", None), "parts", None) or []):
                                if getattr(part, "text", None) and not getattr(part, "thought", False):
                                    final_parts.append(part.text)
                                    emit("token", {"text": part.text})
                        break
                    except Exception as ex:
                        el = str(ex).lower()
                        if use_thinking and ("thinking" in el or "invalid_argument" in el or "400" in el):
                            self._no_thinking_models.add(active_model)
                            continue
                        if self._is_failover_error(ex) and not final_parts and (model_idx + 1) < len(candidate_models):
                            model_idx += 1
                            continue
                        raise

                answer_text = "".join(final_parts).strip() or "پاسخی دریافت نشد؛ لطفاً دوباره ارسال کن."
                saved_ai = self._save_message("assistant", answer_text, mode=mode, citations=[], tables=[], tools=[], response_scope="free", length_mode=length_mode)
                elapsed = round(time.perf_counter() - t0, 1)
                emit("done", {"message": saved_ai, "elapsed": elapsed})
                return {"ok": True, "message": saved_ai, "elapsed": elapsed}

            # ==================== PATH B: INSTITUTIONAL DATA ENGINE (STRICT GROUNDING) ====================
            catalog = self._get_catalog_summary()
            if not catalog["files"]:
                self._save_message("user", question, mode=mode, response_scope="institutional", length_mode=length_mode)
                reply = "هنوز هیچ سندی در پایگاه داده مؤسسه پردازش نشده است. برای آمار رسمی ابتدا فایل‌ها را در بخش اسناد بارگذاری و اسکن کن."
                emit("token", {"text": reply})
                saved = self._save_message("assistant", reply, mode=mode, citations=[], tables=[], tools=[], response_scope="institutional", length_mode=length_mode)
                emit("done", {"message": saved, "elapsed": round(time.perf_counter() - t0, 1)})
                return {"ok": True, "message": saved}

            self._save_message("user", question, mode=mode, response_scope="institutional", length_mode=length_mode)

            citations_map: dict[str, dict[str, Any]] = {}
            collected_tables: list[dict[str, Any]] = []
            used_tools: list[str] = []
            extracted_kpis: list[dict[str, str]] = []
            transparency_notes: list[str] = []
            state_lock = threading.Lock()
            sql_repair_count = 0

            table_schema_lookup: dict[str, list[str]] = {}
            for t in catalog.get("tables", []):
                table_schema_lookup[t["table_name"]] = list(t.get("columns") or [])
            for v in catalog.get("unified_views", []):
                table_schema_lookup[v["view_name"]] = list(v.get("columns") or [])
            table_schema_lookup["smart_teachers_exploded"] = [
                "شناسه_دوره_یکتا", "فایل_منبع", "بخش_منبع", "جدول_منبع", "شماره_ردیف_منبع",
                "نام_دوره", "کارگروه", "تاریخ_شمسی", "سال_شمسی", "ماه_شمسی", "فصل_شمسی",
                "نام_استاد_خام", "نام_معیار_استاد", "نوع_برگزاری", "تعداد_اساتید_دوره",
                "تعداد_شرکت_کنندگان", "مخاطب_معتبر", "سهم_تعدیل_شده_مخاطب",
                "تعداد_جلسات", "ساعت_کل_دوره", "ساعت_سهم_استاد", "ساعت_مستقل", "ساعت_مشترک", "همکاران_مشترک", "سیاست_ساعت",
            ]

            def record_tool(label: str) -> None:
                with state_lock:
                    if label not in used_tools:
                        used_tools.append(label)
                        emit("tool", {"label": label})

            def get_teacher_exact_stats_tool(teacher_name: str, hours_policy: str = "") -> dict[str, Any]:
                """دریافت آمار قطعی و دقیق یک استاد (با تحمل غلط تایپی، تفکیک دوره مستقل/مشترک، سیاست ساعات و ردیف‌های منبع)."""
                record_tool("آمار دقیق استاد")
                pol = hours_policy or inline_hours_policy
                emit("status", {"text": f"محاسبه آمار دقیق «{teacher_name[:24]}»..."})
                res = _mem_teacher_stats(teacher_name=teacher_name, hours_policy=pol, db_path=self.duckdb_path)
                if res.get("ok") and res.get("found"):
                    with state_lock:
                        extracted_kpis.clear()
                        extracted_kpis.extend([
                            {"label": "کل دوره‌ها", "value": str(res["total_courses"])},
                            {"label": "مستقل", "value": str(res["independent_courses"])},
                            {"label": "مشترک", "value": str(res["joint_courses"])},
                            {"label": "نفر-دوره", "value": f"{res['total_attendance_raw']:,}"},
                        ])
                        if res.get("hours_effective", 0) > 0:
                            extracted_kpis.append({"label": "ساعت تدریس", "value": str(res["hours_effective"])})
                        if res.get("resolution_note"):
                            transparency_notes.append(res["resolution_note"])
                        transparency_notes.append(f"مبنای ساعات مشترک: {res['hours_policy_label']}")
                        for c_item in res.get("courses") or []:
                            fn = c_item.get("file_name") or ""
                            loc = f"{c_item.get('source_sheet', '')} (ردیف {c_item.get('row_index', 0)})".strip()
                            if fn:
                                cid = f"row::{fn}::{loc}"
                                citations_map[cid] = {"chunk_id": cid, "file_name": fn, "file_path": "", "file_type": "table", "location": loc, "snippet": c_item.get("course", "")}
                return res

            def search_documents(query: str, top_k: int = 6) -> dict[str, Any]:
                """جست‌وجوی سریع در متن کامل اسناد نمایه‌شده."""
                record_tool("جست‌وجو در اسناد")
                emit("status", {"text": f"جست‌وجو در اسناد برای «{query[:26]}»..."})
                chunks = self._load_all_chunks()
                if not chunks:
                    return {"matched": 0, "results": []}
                norm_q = normalize_fa(query)
                tokens = [t for t in norm_q.split() if len(t) >= 2]
                scored = []
                for item in chunks:
                    hay = item.get("_norm", "")
                    sc = (14.0 if (norm_q and norm_q in hay) else 0.0) + sum(2.5 + min(hay.count(tok), 5) * 0.5 for tok in tokens if hay.count(tok) > 0)
                    if sc > 0:
                        scored.append((sc, item))
                scored.sort(key=lambda x: x[0], reverse=True)
                picked = [it for _, it in scored[:max(1, min(int(top_k or 6), 10))]]
                if not picked:
                    return {"matched": 0, "results": [], "note": "در اسناد فعلی مورد مرتبطی پیدا نشد."}
                results = []
                for item in picked:
                    cid = str(item.get("chunk_id", ""))
                    with state_lock:
                        citations_map[cid] = {"chunk_id": cid, "file_name": item.get("file_name", ""), "file_path": item.get("file_path", ""), "file_type": item.get("file_type", ""), "location": item.get("location", ""), "snippet": (item.get("content", "") or "")[:200]}
                    results.append({"file_name": item.get("file_name", ""), "location": item.get("location", ""), "content": (item.get("content", "") or "")[:1400]})
                return {"matched": len(results), "results": results}

            def get_document_location(file_name: str, location_keyword: str) -> dict[str, Any]:
                """خواندن مستقیم متن یک اسلاید، صفحه یا شیت مشخص."""
                record_tool("مطالعه صفحه/اسلاید")
                chunks = self._load_all_chunks()
                f_norm, l_norm = normalize_fa(file_name), normalize_fa(location_keyword)
                matched = []
                for item in chunks:
                    if (f_norm and f_norm not in item.get("_file_norm", "")) or (l_norm and l_norm not in item.get("_loc_norm", "")):
                        continue
                    cid = str(item.get("chunk_id", ""))
                    with state_lock:
                        citations_map[cid] = {"chunk_id": cid, "file_name": item.get("file_name", ""), "file_path": item.get("file_path", ""), "file_type": item.get("file_type", ""), "location": item.get("location", ""), "snippet": (item.get("content", "") or "")[:200]}
                    matched.append({"file_name": item.get("file_name", ""), "location": item.get("location", ""), "content": item.get("content", "")})
                return {"matched": len(matched), "results": matched[:6]}

            def inspect_table_values(table_name: str, column_name: str = "", search_hint: str = "") -> dict[str, Any]:
                """مشاهده نام دقیق ستون‌ها و مقادیر یکتای یک جدول یا نمای تجمیعی."""
                record_tool("بررسی مقادیر جدول")
                t_clean = (table_name or "").strip().strip('"').strip("'")
                if t_clean not in table_schema_lookup:
                    return {"error": f"جدول «{t_clean}» یافت نشد.", "available_tables": list(table_schema_lookup.keys())[:20]}
                cols = table_schema_lookup[t_clean]
                if not column_name:
                    return {"table": t_clean, "columns": cols}
                c_clean = column_name.strip().strip('"').strip("'")
                if c_clean not in cols:
                    return {"error": f"ستون «{c_clean}» وجود ندارد.", "valid_columns": cols}
                safe_t, safe_c = t_clean.replace('"', '""'), c_clean.replace('"', '""')
                with self._db_lock:
                    con = self._connect_duckdb()
                    try:
                        register_persian_macros(con)
                        if search_hint and search_hint.strip():
                            h_esc = search_hint.strip().replace("'", "''")
                            q = f'SELECT "{safe_c}" AS val, COUNT(*) AS cnt FROM "{safe_t}" WHERE "{safe_c}" IS NOT NULL AND fa_norm("{safe_c}") LIKE \'%\' || fa_norm(\'{h_esc}\') || \'%\' GROUP BY "{safe_c}" ORDER BY cnt DESC LIMIT 30'
                        else:
                            q = f'SELECT "{safe_c}" AS val, COUNT(*) AS cnt FROM "{safe_t}" WHERE "{safe_c}" IS NOT NULL GROUP BY "{safe_c}" ORDER BY cnt DESC LIMIT 30'
                        return {"table": t_clean, "column": c_clean, "distinct_values": [{"value": r[0], "count": int(r[1])} for r in con.execute(q).fetchall()]}
                    except Exception as exc:
                        return {"error": f"خطا در بررسی مقادیر: {exc}", "valid_columns": cols}
                    finally:
                        con.close()

            def run_sql_query(sql_query: str, title: str = "نتیجه تحلیل جدولی") -> dict[str, Any]:
                """اجرای امن و قطعی کوئری SELECT/WITH روی جداول DuckDB با ماکروهای فارسی و خودترمیمی."""
                nonlocal sql_repair_count
                record_tool("محاسبه دقیق آماری")
                emit("status", {"text": f"محاسبه آماری: {title[:30]}..."})
                ok_sql, clean_or_err = SafeDuckDBExecutor.validate_readonly_sql(sql_query)
                if not ok_sql:
                    return {"error": clean_or_err, "self_healing_hint": "فقط یک کوئری SELECT یا WITH معتبر ارسال کن."}
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
                        formatted_rows = [["" if v is None else (int(v) if isinstance(v, float) and v.is_integer() else (round(v, 2) if isinstance(v, float) else v)) for v in row] for row in raw_rows[:250]]
                    except Exception as exc:
                        sql_repair_count += 1
                        ref_names = list(dict.fromkeys(re.findall(r"\b(?:tbl_[a-f0-9]+|view_merged_\d+|smart_teachers_exploded)\b", clean_sql)))
                        ref_schemas = {rn: table_schema_lookup[rn] for rn in ref_names if rn in table_schema_lookup} or {k: v for k, v in list(table_schema_lookup.items())[:8]}
                        return {"error": f"خطای DuckDB: {exc}", "referenced_tables_exact_columns": ref_schemas, "self_healing_hint": "کوئری را با نام دقیق ستون‌های بالا و ماکروهای fa_num/fa_norm اصلاح کن."}
                    finally:
                        con.close()

                det_stats = SafeDuckDBExecutor.compute_deterministic_stats(columns, raw_rows)
                if len(raw_rows) == 0 and "WHERE" in clean_sql.upper():
                    sql_repair_count += 1
                    return {"total_rows": 0, "columns": columns, "rows": [], "self_healing_hint": "۰ ردیف برگشت؛ با inspect_table_values یا get_teacher_exact_stats_tool املای دقیق را بررسی کن و اگر واقعاً در اسناد نبود، صادقانه بگو مورد مرتبطی پیدا نشد."}

                if columns and formatted_rows:
                    with state_lock:
                        collected_tables.append({"title": title or "نتیجه تحلیل", "columns": columns, "rows": formatted_rows, "total_rows": len(raw_rows), "sql": clean_sql})

                used_tbls = list(dict.fromkeys(re.findall(r"\btbl_[a-f0-9]+\b", clean_sql)))
                for vn in list(dict.fromkeys(re.findall(r"\bview_merged_\d+\b", clean_sql))):
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
                        f_name, s_sheet = meta["file_name"], meta["source_sheet"]
                        s_norm = normalize_fa(s_sheet.split("(")[0])
                        linked = next((c for c in all_chunks if c.get("file_name") == f_name and s_norm in c.get("_loc_norm", "")), None)
                        cid = str(linked.get("chunk_id", "")) if linked else f"tbl::{f_name}::{s_sheet}"
                        with state_lock:
                            if cid not in citations_map:
                                citations_map[cid] = {
                                    "chunk_id": cid, "file_name": f_name,
                                    "file_path": linked.get("file_path", "") if linked else "",
                                    "file_type": linked.get("file_type", "table") if linked else "table",
                                    "location": (linked.get("location", s_sheet) if linked else s_sheet),
                                    "snippet": ((linked.get("content", "") or "")[:200] if linked else ""),
                                }

                return {"total_rows": len(raw_rows), "truncated_at_500": truncated, "columns": columns, "rows": formatted_rows[:60], "deterministic_stats": det_stats}

            def save_user_rule(rule_text: str, scope: str = "general") -> dict[str, Any]:
                """ذخیره قانون دائمی کاربر در حافظه."""
                record_tool("ثبت قانون دائمی")
                return _mem_add_rule(rule_text=rule_text, scope=scope, db_path=self.duckdb_path)

            def save_entity_alias(canonical_name: str, alias_name: str, entity_type: str = "teacher") -> dict[str, Any]:
                """ذخیره دائمی یکسان بودن دو نام در حافظه."""
                record_tool("ثبت نام معادل")
                return _mem_save_alias(canonical_name=canonical_name, alias_name=alias_name, entity_type=entity_type, status="approved", confidence=1.0, db_path=self.duckdb_path)

            tool_registry = {
                "get_teacher_exact_stats_tool": get_teacher_exact_stats_tool,
                "search_documents": search_documents,
                "get_document_location": get_document_location,
                "inspect_table_values": inspect_table_values,
                "run_sql_query": run_sql_query,
                "save_user_rule": save_user_rule,
                "save_entity_alias": save_entity_alias,
            }

            mode_instruction = MODE_PROMPTS.get(mode, MODE_PROMPTS["analyst"])
            length_instruction = LENGTH_PROMPTS.get(length_mode, LENGTH_PROMPTS["concise"])
            knowledge_map = self._build_scalable_knowledge_map(catalog, question)
            hours_hint = f"\nدر این پرسش کاربر مبنای ساعات را روی «{inline_hours_policy}» درخواست کرده است؛ حتماً در ابزار اعمال کن و زیر پاسخ یک خط مبنا را بنویس." if inline_hours_policy else ""

            system_prompt = f"""تو دستیار هوشمند ارشد «پنل مدیریت مؤسسه امام هادی» هستی.
{mode_instruction}
{length_instruction}{hours_hint}

{knowledge_map}

قوانین قطعی دقت و شفافیت:
1. انحصار آمار به اسناد مؤسسه: هر عدد، شمارش، درصد یا آمار فقط و فقط باید از خروجی ابزارها استخراج شود. هرگز عدد حدسی یا ذهنی نده؛ اگر در اسناد فعلی موجود نیست، صریح بگو «این آمار در اسناد فعلی مؤسسه موجود نیست».
2. آمار اساتید: برای هر سؤال درباره یک استاد مشخص، اول `get_teacher_exact_stats_tool` را صدا بزن تا غلط تایپی، دوره‌های مستقل/مشترک و سیاست ساعات دقیقاً محاسبه شود.
3. تفکیک نفر-دوره از مخاطب یکتا: هرگز جمع شرکت‌کنندگان دوره‌ها را به‌عنوان «مخاطب منحصربه‌فرد» اعلام نکن مگر با لیست اسامی/تماس شمارش شده باشد.
4. خودترمیمی بی‌سروصدا: خطاهای SQL یا نام‌های فنی (`tbl_...` یا واژه SQL) را هرگز در متن پاسخ نیاور.
5. پرهیز از پرگویی: بدون سلام، بدون مقدمه و بدون تکرار سؤال، مستقیم جواب اصلی را در خط اول بده.
"""

            contents = self._build_clean_history_contents(recent_history, question, target_scope="institutional")
            model_idx = 0

            def make_config(mdl: str, use_thinking: bool) -> types.GenerateContentConfig:
                kwargs: dict[str, Any] = {
                    "system_instruction": system_prompt,
                    "tools": [get_teacher_exact_stats_tool, run_sql_query, inspect_table_values, search_documents, get_document_location, save_user_rule, save_entity_alias],
                    "temperature": 0.12,
                }
                if hasattr(types, "AutomaticFunctionCallingConfig"):
                    kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
                if use_thinking:
                    tc = self._build_thinking_config(mdl, mode)
                    if tc is not None:
                        kwargs["thinking_config"] = tc
                return types.GenerateContentConfig(**kwargs)

            def run_stream_once(mdl: str, use_thinking: bool):
                raw_parts, fcs, txt_chunks = [], [], []
                stream = client.models.generate_content_stream(model=mdl, contents=contents, config=make_config(mdl, use_thinking))
                for chunk in stream:
                    cands = getattr(chunk, "candidates", None) or []
                    if not cands:
                        continue
                    for part in (getattr(getattr(cands[0], "content", None), "parts", None) or []):
                        raw_parts.append(part)
                        fc = getattr(part, "function_call", None)
                        if fc:
                            fcs.append(fc)
                        elif getattr(part, "text", None) and not getattr(part, "thought", False):
                            txt_chunks.append(part.text)
                            emit("token", {"text": part.text})
                return raw_parts, fcs, txt_chunks

            emit("status", {"text": "در حال بررسی اسناد مؤسسه..."})
            final_text_parts: list[str] = []
            for _round in range(8):
                raw_model_parts, function_calls, turn_text_chunks = [], [], []
                while True:
                    active_model = candidate_models[model_idx]
                    use_thinking = active_model not in self._no_thinking_models
                    try:
                        raw_model_parts, function_calls, turn_text_chunks = run_stream_once(active_model, use_thinking)
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
                            emit("status", {"text": f"انتقال خودکار به {candidate_models[model_idx]}..."})
                            continue
                        raise

                if turn_text_chunks:
                    final_text_parts.extend(turn_text_chunks)
                if not function_calls:
                    break

                contents.append(types.Content(role="model", parts=raw_model_parts))

                def exec_one(fc_obj):
                    fn_name, fn_args = fc_obj.name, dict(fc_obj.args or {})
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
                    fr_kw = {"name": fn_name, "response": res}
                    if getattr(fc_obj, "id", None):
                        fr_kw["id"] = fc_obj.id
                    return types.Part(function_response=types.FunctionResponse(**fr_kw))

                if len(function_calls) == 1:
                    response_parts = [exec_one(function_calls[0])]
                else:
                    with ThreadPoolExecutor(max_workers=min(4, len(function_calls))) as pool:
                        response_parts = list(pool.map(exec_one, function_calls))

                contents.append(types.Content(role="user", parts=response_parts))
                emit("status", {"text": "تنظیم پاسخ نهایی..."})

            if sql_repair_count > 0:
                record_tool(f"خودترمیمی ({sql_repair_count})")

            answer_text = "".join(final_text_parts).strip()
            if not answer_text and collected_tables:
                first_t = collected_tables[0]
                t_cols, t_rows = first_t.get("columns") or [], first_t.get("rows") or []
                if t_cols and t_rows:
                    hdr = "| " + " | ".join(str(c) for c in t_cols) + " |"
                    sep = "| " + " | ".join("---" for _ in t_cols) + " |"
                    body = "\n".join("| " + " | ".join(str(v) for v in r) + " |" for r in t_rows[:25])
                    answer_text = f"### {first_t.get('title', 'نتیجه تحلیل')}\n\n{hdr}\n{sep}\n{body}"
            if not answer_text:
                answer_text = "پاسخی از مدل دریافت نشد. لطفاً دوباره ارسال کن."

            citations_list = _group_citations_by_file(citations_map)
            trans_summary = " | ".join(dict.fromkeys(transparency_notes))
            saved_ai = self._save_message(
                role="assistant", content=answer_text, mode=mode,
                citations=citations_list, tables=collected_tables, tools=used_tools,
                response_scope="institutional", kpis=extracted_kpis,
                length_mode=length_mode, transparency=trans_summary,
            )
            elapsed = round(time.perf_counter() - t0, 1)
            emit("done", {"message": saved_ai, "elapsed": elapsed})
            return {"ok": True, "message": saved_ai, "elapsed": elapsed}

        except Exception as exc:
            logger.exception("InstitutionalAIAgent.ask_stream error")
            err_msg = (
                "سرورهای گوگل موقتاً شلوغ هستند؛ لطفاً چند ثانیه دیگر دوباره امتحان کن."
                if self._is_failover_error(exc)
                else f"خطا در ارتباط با Gemini: {exc}"
            )
            emit("error", {"error": err_msg})
            return {"ok": False, "error": err_msg}

    @staticmethod
    def export_table_to_excel(table_data: dict[str, Any], dest_path: Path) -> str:
        return export_styled_table_excel(table_data, dest_path)
