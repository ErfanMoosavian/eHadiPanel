from __future__ import annotations

"""
eHadiPanel Smart Entity Brain & Memory Engine (v48.0 Pro — Server-Ready)
- 100% UI-controlled rules, aliases, do-not-merge lists, compound names, honorifics & collective keywords
- Zero hardcoded institutional/person names
- Shared-course hours allocation (equal / full / split + per-course manual overrides)
- Undoable audit history + JSON export/import
- Typo-tolerant entity resolver & deterministic exact teacher stats
"""

from difflib import SequenceMatcher
import hashlib
import json
import logging
from pathlib import Path
import re
import threading
import types
from typing import Any

from src.core.db_manager import (
    INTERNAL_TABLES,
    duckdb_session,
    format_jalali_now,
    is_summary_row_smart,
    normalize_persian,
    parse_jalali_date,
    parse_number_strict,
    JALALI_MONTHS,
    is_banner_header_col,
    is_non_entity_value,
    is_valid_teacher_name,
    promote_banner_headers,
    resolve_default_duckdb_path,
)
from src.core.smart_brain import (
    discover_duckdb_files,
    normalize_persian_text,
    parse_dirty_number,
)

logger = logging.getLogger("eHadiPanel.MemoryEngine")
class _NoOpLock:
    def __enter__(self): return self
    def __exit__(self, *args): return False

_MEM_LOCK = _NoOpLock()  # Unified single-lock architecture via db_manager.get_db_lock()
_INIT_DONE_PATHS: set[str] = set()
_FUZZY_CACHE: dict[str, Any] = {"key": None, "results": []}
_REBUILD_GEN_LOCK = threading.Lock()
_REBUILD_GEN = 0


def _invalidate_fuzzy_cache() -> None:
    _FUZZY_CACHE["key"] = None


def _schedule_teacher_rebuild(db_path: Path | str | None) -> None:
    """Schedules rebuild_clean_teacher_layer in background so UI toggles respond instantly."""
    global _REBUILD_GEN
    with _REBUILD_GEN_LOCK:
        _REBUILD_GEN += 1
        my_gen = _REBUILD_GEN

    def _worker():
        try:
            with _REBUILD_GEN_LOCK:
                if my_gen != _REBUILD_GEN:
                    return
            rebuild_clean_teacher_layer(db_path, force=True)
        except Exception as exc:
            logger.warning("background teacher rebuild skipped: %s", exc)

    threading.Thread(target=_worker, daemon=True).start()
_MEM_HOOKED = False

DEFAULT_HONORIFICS: list[str] = [
    "حجت الاسلام و المسلمین", "حجت الاسلام والمسلمین",
    "حجج الاسلام و المسلمین", "حجج الاسلام والمسلمین",
    "حجت الاسلام", "حجج الاسلام",
    "آیت الله العظمی", "آیت الله",
    "جناب آقای", "سرکار خانم",
    "دکتر", "مهندس", "استاد", "آقای", "خانم", "شیخ", "حاج",
]

DEFAULT_COLLECTIVE_HINTS: list[str] = [
    "جمعی از", "گروهی از", "اساتید مدعو", "پنل تخصصی",
    "میزگرد", "کارگاه گروهی", "تعدادی از", "نامشخص", "ناشناس",
]

DEFAULT_COMMON_SURNAMES: list[str] = [
    "حسینی", "موسوی", "هاشمی", "محمدی", "رضایی", "کریمی",
    "صادقی", "جعفری", "احمدی", "باقری", "علوی", "کاظمی",
    "مهدوی", "صالحی", "حیدری", "طاهری", "امینی", "مرادی",
]

DEFAULT_BRAIN_CONFIG: dict[str, Any] = {
    "honorifics": list(DEFAULT_HONORIFICS),
    "collective_keywords": list(DEFAULT_COLLECTIVE_HINTS),
    "compound_names": [],
    "common_surnames": list(DEFAULT_COMMON_SURNAMES),
    "hours_policy": "equal",          # "equal" | "full" | "split"
    "course_hour_overrides": {},
    "finance_category_rules": {},      # {course_key: {teacher_canonical: hours_float}}
    "entity_type_overrides": {},      # {normalized_raw: "individual" | "collective"}
    "data_mode": "clean",             # "clean" | "raw"
}

PLURAL_PREFIX_RX = re.compile(
    r"^(?:حجج\s*الاسلام(?:\s*و\s*المسلمین)?|اساتید(?:\s*گرامی)?|سخنرانان)\s*[:\-–—]?\s*",
    re.UNICODE,
)

SINGLE_TITLE_WORDS = {"دکتر", "مهندس", "استاد", "شیخ", "آقای", "خانم", "جناب", "سرکار", "حاج"}

TEACHER_COL_HINTS = ("استاد", "سخنران", "مدرس", "ارائه", "teacher", "instructor", "speaker")
COURSE_COL_HINTS = ("نام دوره", "عنوان دوره", "دوره", "عنوان برنامه", "عنوان", "کلاس", "موضوع", "course", "title")
ATTEND_COL_HINTS = ("شرکت کننده", "شرکت کنندگان", "مخاطب", "تعداد نفر", "حاضر", "ثبت نام", "participants", "attendance")
GROUP_COL_HINTS = ("کارگروه", "بخش", "گروه موضوعی", "گروه علمی", "گروه", "دسته", "حوزه", "واحد", "workgroup", "category", "department")
FINANCE_COL_HINTS = ("فروشنده", "طرف حساب", "تامین", "شرکت", "فروشگاه", "شرح", "بابت", "عنوان هزینه", "vendor", "payee")
PERSON_COL_HINTS = ("نام و نام خانوادگی", "نام شرکت", "شرکت کننده", "مخاطب", "پرسنل", "عضو", "full_name", "name")
DATE_COL_HINTS = ("تاریخ", "سال", "فصل", "ماه", "زمان", "date", "year")
HOURS_COL_HINTS = ("ساعت", "مدت", "ساعات", "hours", "duration")
SESSIONS_COL_HINTS = ("جلسه", "تعداد جلسات", "جلسات", "sessions")

HONORIFIC_STRIP_RX = re.compile(
    r"(?:حجت\s*الاسلام(?:\s*و\s*المسلمین)?|حجج\s*الاسلام(?:\s*و\s*المسلمین)?|"
    r"آیت\s*الله(?:\s*العظمی)?|دکتر|مهندس|جناب\s*آقای|آقای|سرکار\s*خانم|خانم|استاد|شیخ|حاج)\s*",
    re.UNICODE,
)


def _resolve_db_path(db_path: Path | str | None = None) -> Path | None:
    p = resolve_default_duckdb_path(db_path)
    if p:
        return p
    dbs = discover_duckdb_files()
    return dbs[0] if dbs else None


def init_memory_tables(db_path: Path | str | None = None) -> None:
    p = _resolve_db_path(db_path)
    if not p:
        return
    p_key = str(p.resolve())
    if p_key in _INIT_DONE_PATHS and p.exists():
        return
    with _MEM_LOCK:
        try:
            with duckdb_session(p) as con:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS user_rules (
                        id INTEGER PRIMARY KEY, scope VARCHAR, rule_text VARCHAR,
                        is_active BOOLEAN DEFAULT TRUE, created_at VARCHAR
                    )
                """)
                con.execute("""
                    CREATE TABLE IF NOT EXISTS entity_aliases (
                        id INTEGER PRIMARY KEY, entity_type VARCHAR, canonical_name VARCHAR,
                        alias_name VARCHAR, status VARCHAR, confidence DOUBLE, created_at VARCHAR
                    )
                """)
                con.execute("""
                    CREATE TABLE IF NOT EXISTS entity_brain_config (
                        cfg_key VARCHAR PRIMARY KEY, cfg_json VARCHAR, updated_at VARCHAR
                    )
                """)
                con.execute("""
                    CREATE TABLE IF NOT EXISTS entity_brain_history (
                        id INTEGER PRIMARY KEY, action_type VARCHAR, summary VARCHAR,
                        undo_json VARCHAR, created_at VARCHAR, is_undone BOOLEAN DEFAULT FALSE
                    )
                """)
            _INIT_DONE_PATHS.add(p_key)
        except Exception as exc:
            logger.warning("init_memory_tables warning: %s", exc)


def is_summary_row(values: list[Any]) -> bool:
    return is_summary_row_smart(values)


def _record_history(con, action_type: str, summary: str, undo_payload: dict[str, Any]) -> None:
    try:
        mx = con.execute("SELECT COALESCE(MAX(id), 0) FROM entity_brain_history").fetchone()[0]
        nid = int(mx) + 1
        con.execute(
            "INSERT INTO entity_brain_history VALUES (?, ?, ?, ?, ?, FALSE)",
            [nid, action_type[:40], summary[:220], json.dumps(undo_payload, ensure_ascii=False), format_jalali_now(True, True)],
        )
    except Exception as exc:
        logger.debug("history log skipped: %s", exc)


def load_brain_config(db_path: Path | str | None = None) -> dict[str, Any]:
    cfg = {k: (list(v) if isinstance(v, list) else (dict(v) if isinstance(v, dict) else v)) for k, v in DEFAULT_BRAIN_CONFIG.items()}
    p = _resolve_db_path(db_path)
    if not p or not p.exists():
        return cfg
    init_memory_tables(p)
    try:
        with duckdb_session(p) as con:
            for k, vjson in con.execute("SELECT cfg_key, cfg_json FROM entity_brain_config").fetchall():
                if k in cfg:
                    try:
                        cfg[k] = json.loads(vjson)
                    except Exception:
                        pass
    except Exception as exc:
        logger.warning("load_brain_config fallback to default: %s", exc)
    if cfg.get("hours_policy") not in ("equal", "full", "split"):
        cfg["hours_policy"] = "equal"
    if cfg.get("data_mode") not in ("clean", "raw"):
        cfg["data_mode"] = "clean"
    return cfg


def save_brain_config(payload: dict[str, Any], db_path: Path | str | None = None, record_undo: bool = True) -> dict[str, Any]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}

    prev_cfg = load_brain_config(p)
    new_cfg = dict(prev_cfg)

    for list_key in ("honorifics", "collective_keywords", "compound_names", "common_surnames"):
        if list_key in payload and isinstance(payload[list_key], list):
            cleaned, seen = [], set()
            for item in payload[list_key]:
                s = normalize_persian(item)
                if s and s not in seen:
                    seen.add(s)
                    cleaned.append(s)
            new_cfg[list_key] = cleaned

    if "hours_policy" in payload and payload["hours_policy"] in ("equal", "full", "split"):
        new_cfg["hours_policy"] = payload["hours_policy"]
    if "data_mode" in payload and payload["data_mode"] in ("clean", "raw"):
        new_cfg["data_mode"] = payload["data_mode"]
    if "course_hour_overrides" in payload and isinstance(payload["course_hour_overrides"], dict):
        new_cfg["course_hour_overrides"] = payload["course_hour_overrides"]
    if "finance_category_rules" in payload and isinstance(payload["finance_category_rules"], dict):
        cleaned_fin = {}
        for k, v in payload["finance_category_rules"].items():
            kn = normalize_persian(k)
            vn = str(v or "").strip()
            if kn and vn:
                cleaned_fin[kn] = vn
        new_cfg["finance_category_rules"] = cleaned_fin
    if "entity_type_overrides" in payload and isinstance(payload["entity_type_overrides"], dict):
        cleaned_ov = {}
        for k, v in payload["entity_type_overrides"].items():
            kn = normalize_persian(k)
            if kn and v in ("individual", "collective"):
                cleaned_ov[kn] = v
        new_cfg["entity_type_overrides"] = cleaned_ov

    now_j = format_jalali_now(True, True)
    with _MEM_LOCK:
        with duckdb_session(p) as con:
            for k, v in new_cfg.items():
                con.execute("DELETE FROM entity_brain_config WHERE cfg_key = ?", [k]); con.execute("INSERT INTO entity_brain_config VALUES (?, ?, ?)", [k, json.dumps(v, ensure_ascii=False), now_j])
            if record_undo:
                _record_history(con, "config_update", "بروزرسانی تنظیمات هسته هوشمند موجودیت‌ها", {"type": "restore_config", "prev_config": prev_cfg})

    fuzzy_keys_changed = any(
        k in payload for k in ("honorifics", "collective_keywords", "compound_names", "common_surnames", "entity_type_overrides")
    )
    if fuzzy_keys_changed:
        _invalidate_fuzzy_cache()

    teacher_keys_changed = any(
        k in payload for k in ("honorifics", "collective_keywords", "compound_names", "common_surnames", "hours_policy", "course_hour_overrides", "entity_type_overrides")
    )
    if teacher_keys_changed:
        _schedule_teacher_rebuild(p)
    return {"ok": True, "config": new_cfg}


def add_compound_name(name: str, db_path: Path | str | None = None) -> dict[str, Any]:
    s = normalize_persian(name)
    if len(s.split()) < 2:
        return {"ok": False, "error": "نام مرکب باید حداقل شامل دو بخش باشد."}
    cfg = load_brain_config(db_path)
    items = list(cfg.get("compound_names") or [])
    if s not in items:
        items.append(s)
    return save_brain_config({"compound_names": items}, db_path=db_path)


def delete_compound_name(name: str, db_path: Path | str | None = None) -> dict[str, Any]:
    s = normalize_persian(name)
    cfg = load_brain_config(db_path)
    items = [x for x in (cfg.get("compound_names") or []) if normalize_persian(x) != s]
    return save_brain_config({"compound_names": items}, db_path=db_path)


def set_entity_type_override(raw_name: str, entity_mode: str, db_path: Path | str | None = None) -> dict[str, Any]:
    s = normalize_persian(raw_name)
    if not s:
        return {"ok": False, "error": "عبارت خالی است."}
    cfg = load_brain_config(db_path)
    ov = dict(cfg.get("entity_type_overrides") or {})
    if entity_mode == "auto" or not entity_mode:
        ov.pop(s, None)
    elif entity_mode in ("individual", "collective"):
        ov[s] = entity_mode
    else:
        return {"ok": False, "error": "نوع موجودیت نامعتبر است."}
    return save_brain_config({"entity_type_overrides": ov}, db_path=db_path)


def set_hours_policy(policy: str, db_path: Path | str | None = None) -> dict[str, Any]:
    if policy not in ("equal", "full", "split"):
        return {"ok": False, "error": "سیاست ساعات باید یکی از equal، full یا split باشد."}
    return save_brain_config({"hours_policy": policy}, db_path=db_path)


def set_course_hour_override(course_key: str, teacher_shares: dict[str, float] | None, db_path: Path | str | None = None) -> dict[str, Any]:
    ck = normalize_persian(course_key)
    if not ck:
        return {"ok": False, "error": "شناسه یا عنوان دوره معتبر نیست."}
    cfg = load_brain_config(db_path)
    ov = dict(cfg.get("course_hour_overrides") or {})
    if not teacher_shares:
        ov.pop(ck, None)
    else:
        cleaned = {}
        for tname, hrs in teacher_shares.items():
            tn = normalize_persian(tname)
            hn = parse_number_strict(hrs)
            if tn and hn is not None and hn >= 0:
                cleaned[tn] = round(float(hn), 2)
        if cleaned:
            ov[ck] = cleaned
        else:
            ov.pop(ck, None)
    return save_brain_config({"course_hour_overrides": ov}, db_path=db_path)




def save_finance_category_rule(item_key: str, category: str, db_path: Path | str | None = None) -> dict[str, Any]:
    """Saves a user-confirmed finance category rule permanently into brain config."""
    k_clean = normalize_persian(item_key).strip()
    cat_clean = str(category or "").strip()
    if not k_clean or not cat_clean:
        return {"ok": False, "error": "شرح هزینه یا سرفصل نامعتبر است."}
    cfg = load_brain_config(db_path)
    rules_map = dict(cfg.get("finance_category_rules") or {})
    rules_map[k_clean] = cat_clean
    save_brain_config({"finance_category_rules": rules_map}, db_path=db_path, record_undo=True)
    return {"ok": True, "item": k_clean, "category": cat_clean, "rules": rules_map}


def delete_finance_category_rule(item_key: str, db_path: Path | str | None = None) -> dict[str, Any]:
    k_clean = normalize_persian(item_key).strip()
    cfg = load_brain_config(db_path)
    rules_map = dict(cfg.get("finance_category_rules") or {})
    if k_clean in rules_map:
        del rules_map[k_clean]
        save_brain_config({"finance_category_rules": rules_map}, db_path=db_path, record_undo=True)
    return {"ok": True, "rules": rules_map}


def _build_honorific_regex(honorifics: list[str] | None = None) -> re.Pattern:
    items = honorifics or DEFAULT_HONORIFICS
    cleaned = sorted([normalize_persian(h) for h in items if normalize_persian(h)], key=len, reverse=True)
    if not cleaned:
        return HONORIFIC_STRIP_RX
    return re.compile(r"(?:" + "|".join(re.escape(h).replace(r"\ ", r"\s*") for h in cleaned) + r")\s*", re.UNICODE)


def _is_collective_entry(raw: str, cfg: dict[str, Any] | None = None) -> bool:
    s = normalize_persian(raw)
    if not s:
        return True
    conf = cfg or DEFAULT_BRAIN_CONFIG
    ov = conf.get("entity_type_overrides") or {}
    if s in ov:
        return ov[s] == "collective"
    hints = conf.get("collective_keywords") or DEFAULT_COLLECTIVE_HINTS
    return any(normalize_persian(k) in s for k in hints if k)


def _clean_for_compare(text: str, entity_type: str, cfg: dict[str, Any] | None = None) -> str:
    s = normalize_persian(text).lower()
    if entity_type in ("teacher", "person"):
        rx = _build_honorific_regex((cfg or {}).get("honorifics")) if cfg else HONORIFIC_STRIP_RX
        s = rx.sub(" ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def split_joint_names(raw: str, entity_type: str = "teacher", cfg: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    conf = cfg or DEFAULT_BRAIN_CONFIG
    txt = normalize_persian(raw)
    if not txt:
        return "گروهی", []

    ov = conf.get("entity_type_overrides") or {}
    if txt in ov:
        return ("گروهی", [txt]) if ov[txt] == "collective" else ("انفرادی", [txt])

    if _is_collective_entry(txt, conf):
        return "گروهی", [txt]
    if entity_type not in ("teacher", "person"):
        return "انفرادی", [txt]

    work = PLURAL_PREFIX_RX.sub("", txt).strip(" :،,-–—/")
    if not work:
        return "گروهی", [txt]

    atomic_reverse: dict[str, str] = {}
    atomic_patterns = [
        (r"حجت\s*الاسلام\s*و\s*المسلمین", "__HOJ_W__", "حجت الاسلام و المسلمین"),
        (r"حجت\s*الاسلام", "__HOJ__", "حجت الاسلام"),
        (r"آیت\s*الله\s*العظمی", "__AYAT_O__", "آیت الله العظمی"),
        (r"آیت\s*الله", "__AYAT__", "آیت الله"),
        (r"جناب\s*آقای", "__JENAB__", "جناب آقای"),
        (r"سرکار\s*خانم", "__SARKAR__", "سرکار خانم"),
    ]
    title_tokens = set(SINGLE_TITLE_WORDS)
    for pat, tok_key, display_val in atomic_patterns:
        work = re.sub(pat, f" {tok_key} ", work)
        atomic_reverse[tok_key] = display_val
        title_tokens.add(tok_key)

    for idx_h, h in enumerate(sorted(conf.get("honorifics") or [], key=len, reverse=True)):
        hn = normalize_persian(h)
        if not hn:
            continue
        if len(hn.split()) == 1:
            title_tokens.add(hn)
        elif hn not in atomic_reverse.values():
            tk = f"__UHON_{idx_h}__"
            pat_h = re.escape(hn).replace(r"\ ", r"\s*")
            if re.search(pat_h, work):
                work = re.sub(pat_h, f" {tk} ", work)
                atomic_reverse[tk] = hn
                title_tokens.add(tk)

    for idx_c, cname in enumerate(sorted(conf.get("compound_names") or [], key=len, reverse=True)):
        cn = normalize_persian(cname)
        if len(cn.split()) < 2:
            continue
        tk = f"__CMP_{idx_c}__"
        pat_c = re.escape(cn).replace(r"\ ", r"\s+")
        if re.search(pat_c, work):
            work = re.sub(pat_c, f" {tk} ", work)
            atomic_reverse[tk] = cn

    raw_chunks = re.split(r"\s*[،,/؛\n]\s*|\s+[\-–—]\s+", work)
    people: list[str] = []
    for chunk in raw_chunks:
        tokens = [t.strip(" :.-") for t in chunk.split() if t.strip(" :.-")]
        if not tokens:
            continue
        cur: list[str] = []
        seen_name_word = False
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "و" and seen_name_word and (i + 1) < len(tokens):
                rem = tokens[i + 1 :]
                if any(rt not in title_tokens and rt != "و" for rt in rem):
                    if cur:
                        people.append(" ".join(atomic_reverse.get(x, x) for x in cur))
                    cur = []
                    seen_name_word = False
                    i += 1
                    continue
            if tok in title_tokens and seen_name_word:
                if cur:
                    people.append(" ".join(atomic_reverse.get(x, x) for x in cur))
                cur = [tok]
                seen_name_word = False
                i += 1
                continue
            cur.append(tok)
            if tok not in title_tokens and tok != "و":
                seen_name_word = True
            i += 1
        if cur:
            people.append(" ".join(atomic_reverse.get(x, x) for x in cur))

    clean_people: list[str] = []
    seen_cores: set[str] = set()
    for p in people:
        p_clean = re.sub(r"\s+", " ", p).strip()
        core = _clean_for_compare(p_clean, entity_type, conf)
        if len(core) < 2:
            continue
        if core not in seen_cores:
            seen_cores.add(core)
            clean_people.append(p_clean)

    if not clean_people:
        return "گروهی", [txt]
    return ("مشترک" if len(clean_people) > 1 else "انفرادی"), clean_people


def list_rules(db_path: Path | str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return []
    with _MEM_LOCK:
        with duckdb_session(p) as con:
            q = "SELECT id, scope, rule_text, is_active, created_at FROM user_rules"
            if active_only:
                q += " WHERE is_active = TRUE"
            q += " ORDER BY id DESC"
            return [
                {"id": int(r[0]), "scope": str(r[1] or "general"), "rule_text": str(r[2] or ""), "is_active": bool(r[3]), "created_at": str(r[4] or "")}
                for r in con.execute(q).fetchall()
            ]


def add_rule(rule_text: str, scope: str = "general", db_path: Path | str | None = None) -> dict[str, Any]:
    txt = (rule_text or "").strip()
    if len(txt) < 4:
        return {"ok": False, "error": "متن قانون خیلی کوتاه است."}
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}

    norm_new = normalize_persian(txt)
    for ex in list_rules(p, active_only=True):
        if normalize_persian(ex["rule_text"]) == norm_new:
            return {"ok": True, "already_exists": True, "rule": ex}

    now_s = format_jalali_now(True, True)
    with _MEM_LOCK:
        with duckdb_session(p) as con:
            nid = int(con.execute("SELECT COALESCE(MAX(id), 0) FROM user_rules").fetchone()[0]) + 1
            con.execute("INSERT INTO user_rules VALUES (?, ?, ?, TRUE, ?)", [nid, (scope or "general").strip()[:40], txt, now_s])
            _record_history(con, "add_rule", f"افزودن قانون: {txt[:60]}", {"type": "delete_rule", "rule_id": nid})
    return {"ok": True, "rule": {"id": nid, "scope": scope, "rule_text": txt, "is_active": True, "created_at": now_s}}


def delete_rule(rule_id: int, db_path: Path | str | None = None) -> dict[str, Any]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}
    with _MEM_LOCK:
        with duckdb_session(p) as con:
            old = con.execute("SELECT scope, rule_text, created_at FROM user_rules WHERE id = ?", [int(rule_id)]).fetchone()
            con.execute("DELETE FROM user_rules WHERE id = ?", [int(rule_id)])
            if old:
                _record_history(con, "delete_rule", f"حذف قانون: {str(old[1])[:60]}", {"type": "restore_rule", "id": int(rule_id), "scope": old[0], "rule_text": old[1], "created_at": old[2]})
    return {"ok": True}


def list_aliases(status: str | None = None, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return []
    with _MEM_LOCK:
        with duckdb_session(p) as con:
            if status:
                rows = con.execute(
                    "SELECT id, entity_type, canonical_name, alias_name, status, confidence, created_at FROM entity_aliases WHERE status = ? ORDER BY id DESC",
                    [status],
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT id, entity_type, canonical_name, alias_name, status, confidence, created_at FROM entity_aliases ORDER BY id DESC"
                ).fetchall()
            return [
                {"id": int(r[0]), "entity_type": str(r[1] or "general"), "canonical_name": str(r[2] or ""), "alias_name": str(r[3] or ""), "status": str(r[4] or "approved"), "confidence": float(r[5] or 1.0), "created_at": str(r[6] or "")}
                for r in rows
            ]


def resolve_canonical_map(entity_type: str = "teacher", db_path: Path | str | None = None) -> dict[str, str]:
    cfg = load_brain_config(db_path)
    approved = [a for a in list_aliases(status="approved", db_path=db_path) if a["entity_type"] == entity_type]
    direct_core: dict[str, str] = {}
    core_to_display: dict[str, str] = {}
    for a in approved:
        c_disp = a["canonical_name"].strip()
        c_core = _clean_for_compare(c_disp, entity_type, cfg)
        a_core = _clean_for_compare(a["alias_name"], entity_type, cfg)
        if c_core and a_core:
            direct_core[a_core] = c_core
            core_to_display[c_core] = c_disp
    resolved: dict[str, str] = {}
    for start_core in set(direct_core.keys()) | set(core_to_display.keys()):
        cur, visited = start_core, {start_core}
        while cur in direct_core and direct_core[cur] not in visited:
            cur = direct_core[cur]
            visited.add(cur)
        resolved[start_core] = core_to_display.get(cur, cur)
    return resolved


def save_alias(canonical_name: str, alias_name: str, entity_type: str = "teacher", status: str = "approved", confidence: float = 1.0, db_path: Path | str | None = None) -> dict[str, Any]:
    c_clean, a_clean = (canonical_name or "").strip(), (alias_name or "").strip()
    if not c_clean or not a_clean:
        return {"ok": False, "error": "نام اصلی و نام معادل هر دو الزامی هستند."}
    if normalize_persian(c_clean) == normalize_persian(a_clean) and c_clean == a_clean:
        return {"ok": False, "error": "دو عبارت کاملاً یکسان هستند."}
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}

    cfg = load_brain_config(p)
    st = status if status in ("approved", "rejected") else "approved"
    et = (entity_type or "general").strip()[:30]
    now_s = format_jalali_now(True, True)
    existing = list_aliases(db_path=p)
    pair_key = tuple(sorted([_clean_for_compare(c_clean, et, cfg), _clean_for_compare(a_clean, et, cfg)]))
    updated_id = None

    with _MEM_LOCK:
        with duckdb_session(p) as con:
            for ex in existing:
                ex_key = tuple(sorted([_clean_for_compare(ex["canonical_name"], et, cfg), _clean_for_compare(ex["alias_name"], et, cfg)]))
                if ex_key == pair_key and ex["entity_type"] == et:
                    con.execute("UPDATE entity_aliases SET canonical_name = ?, alias_name = ?, status = ?, created_at = ? WHERE id = ?", [c_clean, a_clean, st, now_s, ex["id"]])
                    updated_id = ex["id"]
                    _record_history(con, "update_alias", f"{'ادغام' if st == 'approved' else 'منع ادغام'}: «{a_clean}» ← «{c_clean}»", {"type": "restore_alias", "row": ex})
                    break
            if updated_id is None:
                updated_id = int(con.execute("SELECT COALESCE(MAX(id), 0) FROM entity_aliases").fetchone()[0]) + 1
                con.execute("INSERT INTO entity_aliases VALUES (?, ?, ?, ?, ?, ?, ?)", [updated_id, et, c_clean, a_clean, st, float(confidence), now_s])
                _record_history(con, "add_alias", f"{'ادغام' if st == 'approved' else 'منع ادغام'}: «{a_clean}» ← «{c_clean}»", {"type": "delete_alias", "alias_id": updated_id})

    _invalidate_fuzzy_cache()
    if et == "teacher":
        _schedule_teacher_rebuild(p)
    return {"ok": True, "id": updated_id}


def delete_alias(alias_id: int, db_path: Path | str | None = None) -> dict[str, Any]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}
    with _MEM_LOCK:
        with duckdb_session(p) as con:
            old = con.execute("SELECT id, entity_type, canonical_name, alias_name, status, confidence, created_at FROM entity_aliases WHERE id = ?", [int(alias_id)]).fetchone()
            con.execute("DELETE FROM entity_aliases WHERE id = ?", [int(alias_id)])
            if old:
                _record_history(con, "delete_alias", f"حذف تطبیق: «{old[3]}» / «{old[2]}»", {"type": "restore_alias", "row": {"id": int(old[0]), "entity_type": old[1], "canonical_name": old[2], "alias_name": old[3], "status": old[4], "confidence": float(old[5] or 1.0), "created_at": old[6]}})
    _invalidate_fuzzy_cache()
    _schedule_teacher_rebuild(p)
    return {"ok": True}


def get_brain_history(limit: int = 40, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return []
    with _MEM_LOCK:
        with duckdb_session(p) as con:
            rows = con.execute("SELECT id, action_type, summary, created_at, is_undone FROM entity_brain_history ORDER BY id DESC LIMIT ?", [int(limit)]).fetchall()
            return [{"id": int(r[0]), "action_type": str(r[1] or ""), "summary": str(r[2] or ""), "created_at": str(r[3] or ""), "is_undone": bool(r[4])} for r in rows]


def undo_brain_action(history_id: int, db_path: Path | str | None = None) -> dict[str, Any]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}
    with _MEM_LOCK:
        with duckdb_session(p) as con:
            row = con.execute("SELECT id, undo_json, is_undone FROM entity_brain_history WHERE id = ?", [int(history_id)]).fetchone()
            if not row:
                return {"ok": False, "error": "رکورد تاریخچه یافت نشد."}
            if row[2]:
                return {"ok": False, "error": "این تغییر قبلاً بازگردانی شده است."}
            payload = json.loads(row[1] or "{}")
            utype = payload.get("type")
            if utype == "delete_alias":
                con.execute("DELETE FROM entity_aliases WHERE id = ?", [int(payload["alias_id"])])
            elif utype == "restore_alias":
                r = payload["row"]
                con.execute("DELETE FROM entity_aliases WHERE id = ?", [int(r["id"])]); con.execute("INSERT INTO entity_aliases VALUES (?, ?, ?, ?, ?, ?, ?)", [int(r["id"]), r["entity_type"], r["canonical_name"], r["alias_name"], r["status"], float(r.get("confidence", 1.0)), r.get("created_at", "")])
            elif utype == "delete_rule":
                con.execute("DELETE FROM user_rules WHERE id = ?", [int(payload["rule_id"])])
            elif utype == "restore_rule":
                con.execute("DELETE FROM user_rules WHERE id = ?", [int(payload["id"])]); con.execute("INSERT INTO user_rules VALUES (?, ?, ?, TRUE, ?)", [int(payload["id"]), payload["scope"], payload["rule_text"], payload.get("created_at", "")])
            elif utype == "restore_config":
                now_j = format_jalali_now(True, True)
                for k, v in (payload.get("prev_config") or {}).items():
                    con.execute("DELETE FROM entity_brain_config WHERE cfg_key = ?", [k]); con.execute("INSERT INTO entity_brain_config VALUES (?, ?, ?)", [k, json.dumps(v, ensure_ascii=False), now_j])
            else:
                return {"ok": False, "error": "نوع بازگردانی پشتیبانی نمی‌شود."}
            con.execute("UPDATE entity_brain_history SET is_undone = TRUE WHERE id = ?", [int(history_id)])
    _invalidate_fuzzy_cache()
    _schedule_teacher_rebuild(p)
    return {"ok": True}


def export_brain_json(db_path: Path | str | None = None) -> dict[str, Any]:
    p = _resolve_db_path(db_path)
    bundle = {
        "schema_version": "ehadi_brain_v2",
        "exported_at": format_jalali_now(True, True),
        "config": load_brain_config(p),
        "rules": list_rules(p, active_only=False),
        "aliases": list_aliases(status=None, db_path=p),
    }
    return {"ok": True, "json": json.dumps(bundle, ensure_ascii=False, indent=2), "bundle": bundle}


def import_brain_json(raw_json: str, db_path: Path | str | None = None) -> dict[str, Any]:
    try:
        bundle = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        if not isinstance(bundle, dict):
            return {"ok": False, "error": "فرمت JSON معتبر نیست."}
    except Exception as exc:
        return {"ok": False, "error": f"خطا در خواندن JSON: {exc}"}
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}
    imported_counts = {"rules": 0, "aliases": 0, "config": False}
    if isinstance(bundle.get("config"), dict):
        save_brain_config(bundle["config"], db_path=p, record_undo=True)
        imported_counts["config"] = True
    for r in bundle.get("rules") or []:
        if isinstance(r, dict) and r.get("rule_text"):
            res = add_rule(r["rule_text"], r.get("scope", "general"), db_path=p)
            if res.get("ok") and not res.get("already_exists"):
                imported_counts["rules"] += 1
    for a in bundle.get("aliases") or []:
        if isinstance(a, dict) and a.get("canonical_name") and a.get("alias_name"):
            res = save_alias(a["canonical_name"], a["alias_name"], a.get("entity_type", "teacher"), a.get("status", "approved"), float(a.get("confidence", 1.0)), db_path=p)
            if res.get("ok"):
                imported_counts["aliases"] += 1
    _invalidate_fuzzy_cache()
    _schedule_teacher_rebuild(p)
    return {"ok": True, "imported": imported_counts}


def _teacher_layer_signature(db_path: Path, con=None) -> str:
    try:
        st = db_path.stat()
        aliases, cfgs = [], []
        if con is not None:
            tbls = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
            if "entity_aliases" in tbls:
                aliases = con.execute("SELECT entity_type, canonical_name, alias_name, status FROM entity_aliases WHERE entity_type = 'teacher'").fetchall()
            if "entity_brain_config" in tbls:
                cfgs = con.execute("SELECT cfg_key, cfg_json FROM entity_brain_config ORDER BY cfg_key").fetchall()
        return hashlib.md5(f"{st.st_mtime_ns}:{st.st_size}:{aliases}:{cfgs}".encode("utf-8")).hexdigest()
    except Exception:
        return ""


def rebuild_clean_teacher_layer(db_path: Path | str | None = None, force: bool = False) -> dict[str, Any]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "rows": 0}
    cfg = load_brain_config(p)
    hours_policy = cfg.get("hours_policy", "equal")
    hour_overrides: dict[str, dict[str, float]] = cfg.get("course_hour_overrides") or {}
    alias_map = resolve_canonical_map("teacher", p)

    with _MEM_LOCK:
        with duckdb_session(p) as con:
            if not force:
                try:
                    tbls_chk = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
                    if "smart_teachers_exploded" in tbls_chk and "_meta_teacher_sig" in tbls_chk:
                        cols_chk = {c[0] for c in con.execute("DESCRIBE smart_teachers_exploded").fetchall()}
                        if "شماره_ردیف_منبع" in cols_chk and "ساعت_سهم_استاد" in cols_chk:
                            saved_sig = con.execute("SELECT sig FROM _meta_teacher_sig LIMIT 1").fetchone()
                            cur_sig = _teacher_layer_signature(p, con)
                            if saved_sig and saved_sig[0] == cur_sig and cur_sig:
                                rc = con.execute("SELECT COUNT(*) FROM smart_teachers_exploded").fetchone()[0]
                                return {"ok": True, "rows": int(rc), "cached": True}
                except Exception:
                    pass

            tables = [str(r[0]) for r in con.execute("SHOW TABLES").fetchall()]
            cat_map: dict[str, tuple[str, str]] = {}
            if "tabular_catalog" in tables:
                for tn, fn, sh in con.execute("SELECT table_name, file_name, source_sheet FROM tabular_catalog").fetchall():
                    cat_map[str(tn)] = (str(fn or ""), str(sh or ""))

            raw_records: list[dict[str, Any]] = []
            core_freq_display: dict[str, dict[str, int]] = {}

            for tname in tables:
                if tname.lower() in INTERNAL_TABLES or tname.lower().startswith("view_"):
                    continue
                safe_t = tname.replace('"', '""')
                try:
                    raw_cols = [str(c[0]) for c in con.execute(f'DESCRIBE "{safe_t}"').fetchall()]
                    raw_rows = con.execute(f'SELECT * FROM "{safe_t}"').fetchall()
                except Exception:
                    continue
                cols, rows, banner_ctx = promote_banner_headers(raw_cols, raw_rows)
                if not cols or not rows:
                    continue
                def _find(hints):
                    return next((c for c in cols if not is_banner_header_col(c) and any(h in normalize_persian(c).lower() for h in hints)), None)
                t_col, c_col, a_col = _find(TEACHER_COL_HINTS), _find(COURSE_COL_HINTS), _find(ATTEND_COL_HINTS)
                if not t_col or (not c_col and not a_col):
                    continue
                g_col, d_col, h_col, s_col = _find(GROUP_COL_HINTS), _find(DATE_COL_HINTS), _find(HOURS_COL_HINTS), _find(SESSIONS_COL_HINTS)
                idx_of = {c: i for i, c in enumerate(cols)}
                fn, sh = cat_map.get(tname, (tname, ""))
                for r_idx, r in enumerate(rows, start=1):
                    if is_summary_row_smart(list(r)):
                        continue
                    raw_teacher = str(r[idx_of[t_col]] or "").strip()
                    if not raw_teacher or not is_valid_teacher_name(raw_teacher):
                        continue
                    course_title = str(r[idx_of[c_col]] or "").strip() if c_col else ""
                    att_val = parse_number_strict(r[idx_of[a_col]]) if a_col else None
                    wg_val = str(r[idx_of[g_col]] or "").strip() if g_col else ""
                    dt_raw = str(r[idx_of[d_col]] or "").strip() if d_col else ""
                    hrs_val = parse_number_strict(r[idx_of[h_col]]) if h_col else None
                    ses_val = parse_number_strict(r[idx_of[s_col]]) if s_col else None
                    jdate = parse_jalali_date(dt_raw, fallback_text=f"{fn} {sh}")
                    mode, parts = split_joint_names(raw_teacher, "teacher", cfg)
                    raw_records.append({
                        "course_uid": f"{tname}#{r_idx}", "fn": fn, "sh": sh, "tname": tname, "row_idx": r_idx,
                        "course_title": course_title, "workgroup": wg_val, "jdate": jdate, "raw_teacher": raw_teacher,
                        "att_val": att_val, "hrs_val": hrs_val if (hrs_val is not None and hrs_val >= 0) else 0.0,
                        "ses_val": int(round(ses_val)) if (ses_val is not None and ses_val >= 0) else 0, "mode": mode, "parts": parts,
                    })
                    if mode != "گروهی":
                        for pt in parts:
                            core = _clean_for_compare(pt, "teacher", cfg)
                            if core:
                                d = core_freq_display.setdefault(core, {})
                                d[pt] = d.get(pt, 0) + 1

            default_display = {core: sorted(dmap.items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0] for core, dmap in core_freq_display.items()}

            con.execute("DROP TABLE IF EXISTS smart_teachers_exploded")
            con.execute("""
                CREATE TABLE smart_teachers_exploded (
                    "شناسه_دوره_یکتا" VARCHAR, "فایل_منبع" VARCHAR, "بخش_منبع" VARCHAR,
                    "جدول_منبع" VARCHAR, "شماره_ردیف_منبع" INTEGER, "نام_دوره" VARCHAR,
                    "کارگروه" VARCHAR, "تاریخ_شمسی" VARCHAR, "سال_شمسی" VARCHAR,
                    "ماه_شمسی" INTEGER, "فصل_شمسی" VARCHAR, "نام_استاد_خام" VARCHAR,
                    "نام_معیار_استاد" VARCHAR, "نوع_برگزاری" VARCHAR, "تعداد_اساتید_دوره" INTEGER,
                    "تعداد_شرکت_کنندگان" DOUBLE, "مخاطب_معتبر" BOOLEAN, "سهم_تعدیل_شده_مخاطب" DOUBLE,
                    "تعداد_جلسات" INTEGER, "ساعت_کل_دوره" DOUBLE, "ساعت_سهم_استاد" DOUBLE,
                    "ساعت_مستقل" DOUBLE, "ساعت_مشترک" DOUBLE, "همکاران_مشترک" VARCHAR, "سیاست_ساعت" VARCHAR
                )
            """)

            out_rows: list[tuple] = []
            counts = {"انفرادی": 0, "مشترک": 0, "گروهی": 0}
            for rec in raw_records:
                mode, parts = rec["mode"], rec["parts"]
                att_val, att_valid = rec["att_val"], (rec["att_val"] is not None)
                att_num = float(att_val) if att_valid else 0.0
                hrs, ses, jd = float(rec["hrs_val"]), int(rec["ses_val"]), rec["jdate"]

                if mode == "گروهی" or not parts:
                    counts["گروهی"] += 1
                    out_rows.append((
                        rec["course_uid"], rec["fn"], rec["sh"], rec["tname"], rec["row_idx"],
                        rec["course_title"], rec["workgroup"], jd["canonical"], jd["year"], jd["month"], jd["season"],
                        rec["raw_teacher"], rec["raw_teacher"], "گروهی", 1,
                        (att_num if att_valid else None), att_valid, (att_num if att_valid else 0.0),
                        ses, hrs, hrs, 0.0, hrs, "", hours_policy,
                    ))
                    continue

                resolved_names = [alias_map.get(_clean_for_compare(pt, "teacher", cfg)) or default_display.get(_clean_for_compare(pt, "teacher", cfg), pt) for pt in parts]
                n_t = max(1, len(resolved_names))
                adj_att = round(att_num / n_t, 4) if att_valid else 0.0
                counts[mode] = counts.get(mode, 0) + n_t
                manual_map = hour_overrides.get(rec["course_uid"]) or hour_overrides.get(normalize_persian(rec["course_title"])) or {}

                for idx_t, canon in enumerate(resolved_names):
                    peers = "، ".join(x for j, x in enumerate(resolved_names) if j != idx_t)
                    c_norm, c_core = normalize_persian(canon), _clean_for_compare(canon, "teacher", cfg)
                    m_hrs = next((float(mv) for mk, mv in manual_map.items() if normalize_persian(mk) == c_norm or _clean_for_compare(mk, "teacher", cfg) == c_core), None)
                    if m_hrs is not None:
                        eff_hrs, pol_used = round(m_hrs, 2), "manual"
                    elif mode == "انفرادی" or n_t == 1:
                        eff_hrs, pol_used = round(hrs, 2), hours_policy
                    elif hours_policy == "full":
                        eff_hrs, pol_used = round(hrs, 2), "full"
                    else:
                        eff_hrs, pol_used = round(hrs / n_t, 2), hours_policy

                    hrs_ind = round(eff_hrs, 2) if mode == "انفرادی" else 0.0
                    hrs_jnt = round(eff_hrs if m_hrs is not None else (hrs if hours_policy in ("full", "split") else hrs / n_t), 2) if mode == "مشترک" else 0.0
                    out_rows.append((
                        rec["course_uid"], rec["fn"], rec["sh"], rec["tname"], rec["row_idx"],
                        rec["course_title"], rec["workgroup"], jd["canonical"], jd["year"], jd["month"], jd["season"],
                        rec["raw_teacher"], canon, mode, n_t,
                        (att_num if att_valid else None), att_valid, adj_att,
                        ses, hrs, eff_hrs, hrs_ind, hrs_jnt, peers, pol_used,
                    ))

            if out_rows:
                con.executemany("INSERT INTO smart_teachers_exploded VALUES (" + ", ".join(["?"] * 25) + ")", out_rows)
            con.execute("CREATE TABLE IF NOT EXISTS _meta_teacher_sig (sig VARCHAR); DELETE FROM _meta_teacher_sig; INSERT INTO _meta_teacher_sig VALUES (?)", [_teacher_layer_signature(p, con)])
            return {"ok": True, "rows": len(out_rows), "breakdown": counts, "hours_policy": hours_policy}


def _phonetic_fa(s: str) -> str:
    s = normalize_persian(s).lower()
    s = re.sub(r"[ثص]", "س", s)
    s = re.sub(r"[ذضظ]", "ز", s)
    return s.replace("ط", "ت").replace("ح", "ه").replace("غ", "ق").replace("ع", "ا")


def resolve_query_entity(query_name: str, entity_type: str = "teacher", db_path: Path | str | None = None, candidates_override: list[str] | None = None) -> dict[str, Any]:
    cfg = load_brain_config(db_path)
    q_core = _clean_for_compare(query_name, entity_type, cfg)
    if len(q_core) < 2:
        return {"matched": False, "exact": False, "ambiguous": False, "canonical": "", "candidates": []}

    known: list[str] = []
    if candidates_override is not None:
        known = list(dict.fromkeys(str(x).strip() for x in candidates_override if str(x).strip()))
    else:
        p = _resolve_db_path(db_path)
        if p and p.exists():
            try:
                rebuild_clean_teacher_layer(p)
                with duckdb_session(p) as con:
                    tbls = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
                    if entity_type == "teacher" and "smart_teachers_exploded" in tbls:
                        rows = con.execute('SELECT DISTINCT "نام_معیار_استاد" FROM smart_teachers_exploded WHERE "نوع_برگزاری" != \'گروهی\' AND "نام_معیار_استاد" IS NOT NULL').fetchall()
                        known = [str(r[0]).strip() for r in rows if r[0]]
            except Exception as exc:
                logger.warning("resolve_query_entity DB lookup skipped: %s", exc)
    if not known:
        return {"matched": False, "exact": False, "ambiguous": False, "canonical": "", "candidates": []}

    alias_map = resolve_canonical_map(entity_type, db_path) if candidates_override is None else {}
    if q_core in alias_map:
        return {"matched": True, "exact": True, "ambiguous": False, "canonical": alias_map[q_core], "confidence": 1.0, "candidates": [{"name": alias_map[q_core], "score": 1.0}]}

    q_phon, q_tokens = _phonetic_fa(q_core), q_core.split()
    scored: list[tuple[float, bool, str]] = []
    for disp in known:
        d_core = _clean_for_compare(disp, entity_type, cfg)
        if not d_core:
            continue
        if q_core == d_core:
            return {"matched": True, "exact": True, "ambiguous": False, "canonical": disp, "confidence": 1.0, "candidates": [{"name": disp, "score": 1.0}]}
        d_tokens = d_core.split()
        exact_sub = (q_core in d_core and len(q_core) >= 4) or (all(t in d_tokens for t in q_tokens) and len(q_tokens) >= 1)
        seq = SequenceMatcher(None, q_core, d_core).ratio()
        seq_phon = SequenceMatcher(None, q_phon, _phonetic_fa(d_core)).ratio()
        tok_sim = sum(max(SequenceMatcher(None, qt, dt).ratio() for dt in d_tokens) for qt in q_tokens) / len(q_tokens) if (q_tokens and d_tokens) else 0.0
        score = max(seq, seq_phon * 0.96, tok_sim * 0.94, (0.93 if exact_sub else 0.0))
        if score >= 0.72:
            scored.append((round(score, 4), exact_sub, disp))

    if not scored:
        return {"matched": False, "exact": False, "ambiguous": False, "canonical": "", "candidates": []}

    scored.sort(key=lambda x: (-x[0], -int(x[1]), len(x[2])))
    top_score, top_sub, top_name = scored[0]
    cands = [{"name": nm, "score": sc} for sc, _, nm in scored[:5]]
    if len(scored) >= 2:
        sec_score, sec_sub, _ = scored[1]
        if (top_sub and sec_sub and top_score == sec_score) or (abs(top_score - sec_score) <= 0.04 and top_score < 0.96):
            return {"matched": False, "exact": False, "ambiguous": True, "canonical": "", "confidence": top_score, "candidates": cands}

    return {"matched": True, "exact": bool(top_sub and top_score >= 0.93 and _clean_for_compare(top_name, entity_type, cfg) == q_core), "ambiguous": False, "canonical": top_name, "confidence": top_score, "candidates": cands}


def get_teacher_exact_stats(teacher_name: str, hours_policy: str = "", db_path: Path | str | None = None) -> dict[str, Any]:
    p = _resolve_db_path(db_path)
    if not p or not p.exists():
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}
    rebuild_clean_teacher_layer(p)
    cfg = load_brain_config(p)
    active_policy = hours_policy if hours_policy in ("equal", "full", "split") else cfg.get("hours_policy", "equal")

    res_ent = resolve_query_entity(teacher_name, entity_type="teacher", db_path=p)
    if res_ent.get("ambiguous"):
        return {"ok": True, "ambiguous": True, "query": teacher_name, "candidates": [c["name"] for c in res_ent.get("candidates") or []], "message": "چند نام مشابه در اسناد یافت شد؛ لطفاً مشخص کنید کدام استاد مدنظر است."}
    if not res_ent.get("matched"):
        return {"ok": True, "found": False, "query": teacher_name, "message": f"در اسناد فعلی مؤسسه موردی برای «{teacher_name}» یافت نشد."}

    canonical = res_ent["canonical"]
    resolution_note = f"آمار بر اساس نزدیک‌ترین نام ثبت‌شده («{canonical}») محاسبه شد." if (not res_ent.get("exact") and normalize_persian(teacher_name) != normalize_persian(canonical)) else ""
    hour_overrides: dict[str, dict[str, float]] = cfg.get("course_hour_overrides") or {}
    c_norm, c_core = normalize_persian(canonical), _clean_for_compare(canonical, "teacher", cfg)

    with duckdb_session(p) as con:
        rows = con.execute("""
            SELECT "شناسه_دوره_یکتا", "فایل_منبع", "بخش_منبع", "شماره_ردیف_منبع",
                   "نام_دوره", "کارگروه", "تاریخ_شمسی", "نوع_برگزاری",
                   "تعداد_اساتید_دوره", "تعداد_شرکت_کنندگان", "مخاطب_معتبر",
                   "سهم_تعدیل_شده_مخاطب", "تعداد_جلسات", "ساعت_کل_دوره", "همکاران_مشترک"
            FROM smart_teachers_exploded
            WHERE "نام_معیار_استاد" = ?
            ORDER BY "تاریخ_شمسی" DESC, "نام_دوره" ASC
        """, [canonical]).fetchall()

    ind_c = jnt_c = valid_att = total_ses = 0
    att_raw = att_adj = hrs_ind = hrs_jnt_full = hrs_jnt_eq = hrs_eff = 0.0
    details = []
    for cuid, fn, sh, ridx, ctitle, wg, jdt, mode, nt, att, att_ok, adj_att, ses, chrs, peers in rows:
        nt, chrs, ses = max(1, int(nt or 1)), float(chrs or 0.0), int(ses or 0)
        total_ses += ses
        if att_ok and att is not None:
            valid_att += 1
            att_raw += float(att)
            att_adj += float(adj_att or 0.0)
        manual_map = hour_overrides.get(str(cuid)) or hour_overrides.get(normalize_persian(ctitle)) or {}
        m_hrs = next((float(mv) for mk, mv in manual_map.items() if normalize_persian(mk) == c_norm or _clean_for_compare(mk, "teacher", cfg) == c_core), None)
        if mode == "انفرادی":
            ind_c += 1
            eff = m_hrs if m_hrs is not None else chrs
            hrs_ind += eff
            hrs_eff += eff
        else:
            jnt_c += 1
            hrs_jnt_full += (m_hrs if m_hrs is not None else chrs)
            hrs_jnt_eq += (m_hrs if m_hrs is not None else chrs / nt)
            eff = m_hrs if m_hrs is not None else (chrs if active_policy == "full" else chrs / nt)
            hrs_eff += eff
        details.append({
            "course_uid": str(cuid), "course": str(ctitle or "بدون عنوان"), "workgroup": str(wg or ""),
            "date": str(jdt or ""), "mode": str(mode), "teacher_count": nt, "peers": str(peers or ""),
            "attendance": (int(round(att)) if (att_ok and att is not None) else None), "sessions": ses,
            "course_hours": round(chrs, 2), "teacher_hours": round(eff, 2),
            "file_name": str(fn or ""), "source_sheet": str(sh or ""), "row_index": int(ridx or 0),
        })

    policy_labels = {"equal": "تقسیم مساوی ساعات در دوره‌های مشترک", "full": "ثبت ساعت کامل دوره برای هر استاد", "split": "نمایش تفکیکی ساعات مستقل و مشترک"}
    return {
        "ok": True, "found": True, "ambiguous": False, "canonical_name": canonical, "resolution_note": resolution_note,
        "total_courses": ind_c + jnt_c, "independent_courses": ind_c, "joint_courses": jnt_c,
        "total_attendance_raw": int(round(att_raw)), "adjusted_attendance": round(att_adj, 1),
        "valid_attendance_courses": valid_att, "missing_attendance_courses": (ind_c + jnt_c) - valid_att,
        "total_sessions": total_ses, "hours_policy": active_policy, "hours_policy_label": policy_labels.get(active_policy, active_policy),
        "hours_independent": round(hrs_ind, 2), "hours_joint_full": round(hrs_jnt_full, 2),
        "hours_joint_equal": round(hrs_jnt_eq, 2), "hours_effective": round(hrs_eff, 2), "courses": details,
    }


def _compound_match_bonus(ca: str, cb: str, entity_type: str, common_surnames: set[str]) -> tuple[float, str]:
    wa, wb = [w for w in ca.split() if len(w) >= 2], [w for w in cb.split() if len(w) >= 2]
    if not wa or not wb or not (set(wa) & set(wb)):
        return 0.0, ""
    short_w, long_w = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    short_s, long_s = set(short_w), set(long_w)
    if len(short_s) >= 2 and short_s.issubset(long_s):
        return 0.90, ""
    if len(short_s) == 1 and short_s.issubset(long_s) and len(long_s) <= 4:
        tok = next(iter(short_s))
        if len(tok) >= 3 and entity_type in ("teacher", "person"):
            if len(long_w) >= 2 and tok != long_w[-1]:
                return 0.0, ""
            if tok in common_surnames:
                return 0.75, "احتیاط: نام خانوادگی پرتکرار؛ پیش از ادغام بررسی کنید یک شخص هستند یا خیر"
            return 0.84, ""
    if entity_type in ("teacher", "person") and len(wa) >= 2 and len(wb) >= 2:
        if wa[-1] != wb[-1] and not (len(wa[-1]) >= 4 and len(wb[-1]) >= 4 and (wa[-1] in wb[-1] or wb[-1] in wa[-1])):
            return 0.0, ""
    stem_hits = [x for x in short_s for y in long_s if len(x) >= 4 and len(y) >= 4 and (x in y or y in x)]
    if stem_hits and len(short_s) <= 3:
        if entity_type in ("teacher", "person") and stem_hits[0] in common_surnames:
            if len(wa) >= 2 and len(wb) >= 2:
                return 0.0, ""
            return 0.74, "احتیاط: نام خانوادگی پرتکرار؛ پیش از ادغام بررسی کنید یک شخص هستند یا خیر"
        return 0.81, ""
    return 0.0, ""


def _fuzzy_score(a: str, b: str, entity_type: str, cfg: dict[str, Any] | None = None) -> tuple[float, str]:
    if is_non_entity_value(a) or is_non_entity_value(b):
        return 0.0, ""
    na, nb = normalize_persian(a), normalize_persian(b)
    # Never suggest merging two labels that differ in numbers/dates (e.g. different invoice periods or levels)
    nums_a, nums_b = re.findall(r"\d+", na), re.findall(r"\d+", nb)
    if (nums_a or nums_b) and nums_a != nums_b:
        return 0.0, ""
    # Never suggest merging two labels that mention different Persian months (e.g. آبان vs بهمن)
    months_a = {m for m in JALALI_MONTHS if m in na}
    months_b = {m for m in JALALI_MONTHS if m in nb}
    if (months_a or months_b) and months_a != months_b:
        return 0.0, ""
    ca, cb = _clean_for_compare(a, entity_type, cfg), _clean_for_compare(b, entity_type, cfg)
    if not ca or not cb or ca == cb:
        return 0.0, ""
    ta, tb = set(ca.split()), set(cb.split())
    if not ta or not tb:
        return 0.0, ""
    inter = ta & tb
    seq_ratio = SequenceMatcher(None, ca, cb).ratio()
    jaccard = len(inter) / len(ta | tb)
    GENERIC = {"کارگروه", "گروه", "بخش", "دوره", "کلاس", "جمعی", "اساتید", "خرید", "هزینه", "فاکتور", "سید", "محمد", "علی", "حسین", "حسن", "رضا", "مهدی"}
    meaningful = [w for w in inter if len(w) >= 3 and w not in GENERIC]
    if meaningful:
        score = max(seq_ratio, seq_ratio * 0.55 + jaccard * 0.45)
    elif seq_ratio >= 0.86 and min(len(ca), len(cb)) >= 6:
        score = seq_ratio
    else:
        return 0.0, ""
    common_sn = set((cfg or DEFAULT_BRAIN_CONFIG).get("common_surnames") or DEFAULT_COMMON_SURNAMES)
    bonus, caution = _compound_match_bonus(ca, cb, entity_type, common_sn)
    if bonus > score:
        score = bonus
    elif not meaningful and entity_type in ("teacher", "person") and seq_ratio < 0.88:
        return 0.0, ""
    return round(min(0.98, score), 3), caution


def _classify_column(col_name: str) -> str | None:
    if is_banner_header_col(col_name):
        return None
    cn = normalize_persian(col_name).lower()
    if any(k in cn for k in ("تاریخ", "شماره", "ردیف", "موبایل", "تلفن", "کد ملی", "مبلغ", "مانده", "بدهکار", "بستانکار")):
        return None
    if any(k in cn for k in TEACHER_COL_HINTS):
        return "teacher"
    if any(k in cn for k in GROUP_COL_HINTS):
        return "workgroup"
    if any(k in cn for k in FINANCE_COL_HINTS):
        return "finance"
    if any(k in cn for k in PERSON_COL_HINTS):
        return "person"
    return None


def scan_fuzzy_candidates(db_path: Path | str | None = None, min_score: float = 0.73, max_results: int = 30) -> list[dict[str, Any]]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return []
    cfg = load_brain_config(p)
    all_aliases = list_aliases(db_path=p)
    try:
        with duckdb_session(p) as con_chk:
            data_tbls = sorted(
                str(r[0]) for r in con_chk.execute("SHOW TABLES").fetchall()
                if str(r[0]).lower() not in INTERNAL_TABLES and not str(r[0]).lower().startswith("view_")
            )
            tbl_counts = []
            for dt in data_tbls:
                try:
                    c_val = con_chk.execute(f'SELECT COUNT(*) FROM "{dt.replace(chr(34), chr(34)*2)}"').fetchone()[0]
                    tbl_counts.append((dt, int(c_val)))
                except Exception:
                    tbl_counts.append((dt, -1))
    except Exception:
        tbl_counts = []
    fuzzy_sig_payload = {
        "p": str(p.resolve()),
        "tbls": tbl_counts,
        "aliases": [(a["entity_type"], a["canonical_name"], a["alias_name"], a["status"]) for a in all_aliases],
        "honorifics": cfg.get("honorifics") or [],
        "collective_keywords": cfg.get("collective_keywords") or [],
        "compound_names": cfg.get("compound_names") or [],
        "common_surnames": cfg.get("common_surnames") or [],
        "entity_type_overrides": cfg.get("entity_type_overrides") or {},
        "min_score": min_score,
        "max_results": max_results,
    }
    cache_key = hashlib.md5(json.dumps(fuzzy_sig_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    if _FUZZY_CACHE.get("key") == cache_key:
        return list(_FUZZY_CACHE.get("results") or [])

    decided = {
        (ex["entity_type"], *sorted([_clean_for_compare(ex["canonical_name"], ex["entity_type"], cfg), _clean_for_compare(ex["alias_name"], ex["entity_type"], cfg)]))
        for ex in all_aliases
    }
    core_buckets: dict[str, dict[str, dict[str, Any]]] = {"teacher": {}, "workgroup": {}, "finance": {}, "person": {}}
    with _MEM_LOCK:
        with duckdb_session(p) as con:
            for tname in [str(r[0]) for r in con.execute("SHOW TABLES").fetchall()]:
                if tname.lower() in INTERNAL_TABLES or tname.lower().startswith("view_"):
                    continue
                safe_t = tname.replace('"', '""')
                try:
                    raw_cols = [str(c[0]) for c in con.execute(f'DESCRIBE "{safe_t}"').fetchall()]
                    raw_rows = con.execute(f'SELECT * FROM "{safe_t}" LIMIT 4000').fetchall()
                except Exception:
                    continue
                cols, clean_rows, _ = promote_banner_headers(raw_cols, raw_rows)
                if not cols or not clean_rows:
                    continue
                for c_idx, cname in enumerate(cols):
                    etype = _classify_column(cname)
                    if not etype:
                        continue
                    val_counts: dict[str, int] = {}
                    for r in clean_rows:
                        if c_idx < len(r) and r[c_idx] is not None:
                            sv = str(r[c_idx]).strip()
                            if sv:
                                val_counts[sv] = val_counts.get(sv, 0) + 1
                    for sv, cnt in sorted(val_counts.items(), key=lambda kv: -kv[1])[:200]:
                        if len(sv) < 3 or len(sv) > 90 or is_summary_row_smart([sv]) or is_non_entity_value(sv):
                            continue
                        if etype == "teacher" and not is_valid_teacher_name(sv):
                            continue
                        mode, parts = split_joint_names(sv, etype, cfg)
                        if mode == "گروهی":
                            continue
                        for pt in parts:
                            core = _clean_for_compare(pt, etype, cfg)
                            if len(core) < 3:
                                continue
                            entry = core_buckets[etype].setdefault(core, {"count": 0, "displays": {}})
                            entry["count"] += int(cnt)
                            entry["displays"][pt] = entry["displays"].get(pt, 0) + int(cnt)

    type_labels = {"teacher": "استاد / سخنران", "workgroup": "کارگروه / دسته‌بندی", "finance": "شرح / فروشنده مالی", "person": "مخاطب / پرسنل"}
    candidates, seen = [], set()
    for etype, cmap in core_buckets.items():
        cores = sorted(cmap.keys(), key=lambda c: (-cmap[c]["count"], len(c)))[:140]
        for i in range(len(cores)):
            for j in range(i + 1, len(cores)):
                ca, cb = cores[i], cores[j]
                pk = (etype, min(ca, cb), max(ca, cb))
                if pk in decided or pk in seen:
                    continue
                disp_a = sorted(cmap[ca]["displays"].items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]
                disp_b = sorted(cmap[cb]["displays"].items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]
                score, caution = _fuzzy_score(disp_a, disp_b, etype, cfg)
                if score < min_score:
                    continue
                seen.add(pk)
                cnt_a, cnt_b = cmap[ca]["count"], cmap[cb]["count"]
                sug, ali = (disp_a, disp_b) if (cnt_a > cnt_b or (cnt_a == cnt_b and len(ca) >= len(cb))) else (disp_b, disp_a)
                candidates.append({
                    "entity_type": etype, "entity_label": type_labels.get(etype, etype),
                    "item_a": disp_a, "count_a": cnt_a, "item_b": disp_b, "count_b": cnt_b,
                    "suggested_canonical": sug, "alias_candidate": ali, "confidence": round(score * 100), "caution": caution,
                })
    candidates.sort(key=lambda x: (-x["confidence"], -(x["count_a"] + x["count_b"])))
    res_list = candidates[:max_results]
    _FUZZY_CACHE["key"] = cache_key
    _FUZZY_CACHE["results"] = list(res_list)
    return res_list


def build_memory_prompt_block(db_path: Path | str | None = None) -> str:
    rules = list_rules(db_path, active_only=True)
    aliases = list_aliases(status="approved", db_path=db_path)
    rejected = list_aliases(status="rejected", db_path=db_path)
    cfg = load_brain_config(db_path)
    compounds = cfg.get("compound_names") or []
    pol = cfg.get("hours_policy", "equal")
    pol_txt = {"equal": "تقسیم مساوی", "full": "ساعت کامل برای هر استاد", "split": "نمایش تفکیکی"}.get(pol, pol)
    lines = [f"### تنظیمات فعال هسته هوشمند (سیاست ساعات دوره‌های مشترک: {pol_txt}):"]
    if compounds:
        lines.append("نام‌های مرکب محافظت‌شده: " + "، ".join(compounds[:40]))
    if rules:
        lines.append("قوانین ثبت‌شده کاربر:")
        lines.extend(f"- [{r['scope']}] {r['rule_text']}" for r in rules[:40])
    if aliases:
        lines.append("نام‌های معادل تأییدشده:")
        lines.extend(f'- ({a["entity_type"]}) «{a["alias_name"]}» ≡ «{a["canonical_name"]}»' for a in aliases[:60])
    if rejected:
        lines.append("قوانین منع ادغام (هرگز ادغام نشوند):")
        lines.extend(f'- «{rj["canonical_name"]}» ≠ «{rj["alias_name"]}»' for rj in rejected[:30])
    return "\n".join(lines)


def get_memory_state() -> dict[str, Any]:
    try:
        return {
            "ok": True, "rules": list_rules(active_only=True),
            "aliases": list_aliases(status="approved"), "rejected": list_aliases(status="rejected"),
            "pending": (pend := scan_fuzzy_candidates()), "pending_count": len(pend),
            "config": load_brain_config(), "history": get_brain_history(limit=30),
        }
    except Exception as exc:
        logger.exception("get_memory_state failed")
        return {"ok": False, "error": str(exc), "rules": [], "aliases": [], "rejected": [], "pending": [], "pending_count": 0, "config": dict(DEFAULT_BRAIN_CONFIG), "history": []}


def _bind_memory_api(js_api) -> None:
    if js_api is None:
        return
    cls = type(js_api)
    methods = {
        "get_memory_state": lambda self: get_memory_state(),
        "add_user_rule": lambda self, rule_text="", scope="general": add_rule(rule_text, scope),
        "delete_user_rule": lambda self, rule_id=0: delete_rule(int(rule_id)),
        "resolve_fuzzy_pair": lambda self, canonical_name="", alias_name="", entity_type="teacher", decision="approved", confidence=1.0: save_alias(canonical_name, alias_name, entity_type, ("approved" if decision == "approved" else "rejected"), float(confidence or 1.0)),
        "delete_entity_alias": lambda self, alias_id=0: delete_alias(int(alias_id)),
        "get_brain_config": lambda self: {"ok": True, "config": load_brain_config()},
        "save_brain_config": lambda self, payload=None: save_brain_config(payload or {}),
        "add_compound_name": lambda self, name="": add_compound_name(name),
        "delete_compound_name": lambda self, name="": delete_compound_name(name),
        "set_entity_type_override": lambda self, raw_name="", entity_mode="auto": set_entity_type_override(raw_name, entity_mode),
        "set_hours_policy": lambda self, policy="equal": set_hours_policy(policy),
        "set_course_hour_override": lambda self, course_key="", teacher_shares=None: set_course_hour_override(course_key, teacher_shares),
        "get_brain_history": lambda self, limit=30: {"ok": True, "history": get_brain_history(int(limit))},
        "undo_brain_action": lambda self, history_id=0: undo_brain_action(int(history_id)),
        "export_brain_config": lambda self: export_brain_json(),
        "import_brain_config": lambda self, raw_json="": import_brain_json(raw_json),
        "get_teacher_exact_stats": lambda self, teacher_name="", hours_policy="": get_teacher_exact_stats(teacher_name, hours_policy),
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


def install_memory_engine() -> None:
    global _MEM_HOOKED
    init_memory_tables()
    try:
        rebuild_clean_teacher_layer()
    except Exception as exc:
        logger.warning("Initial smart_teachers_exploded build skipped: %s", exc)
    if _MEM_HOOKED:
        return
    _MEM_HOOKED = True
    try:
        import webview  # type: ignore
        orig_create = webview.create_window
        if not getattr(orig_create, "_eh_mem_wrapped", False):
            def _wrapped_create_window(*args, **kwargs):
                api_obj = kwargs.get("js_api") or (args[3] if len(args) >= 4 else None)
                if api_obj is not None:
                    _bind_memory_api(api_obj)
                return orig_create(*args, **kwargs)
            _wrapped_create_window._eh_mem_wrapped = True  # type: ignore[attr-defined]
            webview.create_window = _wrapped_create_window
    except Exception as exc:
        logger.warning("Could not hook webview.create_window for memory engine: %s", exc)
