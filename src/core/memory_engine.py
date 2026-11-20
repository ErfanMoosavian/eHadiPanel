from __future__ import annotations

import datetime as _dt
from difflib import SequenceMatcher
import logging
from pathlib import Path
import re
import threading
import types
from typing import Any

import duckdb

from src.core.smart_brain import (
    discover_duckdb_files,
    normalize_persian_text,
    parse_dirty_number,
)

logger = logging.getLogger("eHadiPanel.MemoryEngine")
_MEM_LOCK = threading.Lock()
_MEM_HOOKED = False

INTERNAL_TABLES = {
    "chat_history",
    "processed_files",
    "tabular_catalog",
    "user_rules",
    "entity_aliases",
    "app_settings",
    "diagnostics_log",
    "smart_teachers_exploded",
}

HONORIFIC_STRIP_RX = re.compile(
    r"(?:حجت\s*الاسلام(?:\s*و\s*المسلمین)?|حجج\s*الاسلام(?:\s*و\s*المسلمین)?|"
    r"آیت\s*الله(?:\s*العظمی)?|دکتر|مهندس|جناب\s*آقای|آقای|سرکار\s*خانم|خانم|استاد|شیخ|حاج)\s*",
    re.UNICODE,
)

PLURAL_PREFIX_RX = re.compile(
    r"^(?:حجج\s*الاسلام(?:\s*و\s*المسلمین)?|اساتید(?:\s*گرامی)?|سخنرانان)\s*[:\-–—]?\s*",
    re.UNICODE,
)

SUMMARY_ROW_RX = re.compile(
    r"^(?:جمع\s*کل|مجموع(?:\s*کل)?|جمع\s*صفحه|جمع|کل\s*مؤسسه|کل\s*موسسه|total|grand\s*total|subtotal|sum)$",
    re.IGNORECASE,
)

COLLECTIVE_HINTS = (
    "جمعی از",
    "گروهی از",
    "اساتید مدعو",
    "پنل تخصصی",
    "میزگرد",
    "کارگاه گروهی",
    "تعدادی از",
    "نامشخص",
    "ناشناس",
)

COMMON_SURNAMES = {
    "حسینی", "موسوی", "هاشمی", "محمدی", "رضایی", "کریمی",
    "صادقی", "جعفری", "احمدی", "باقری", "علوی", "کاظمی",
    "مهدوی", "صالحی", "حیدری", "طاهری", "امینی", "مرادی",
}

SINGLE_TITLE_WORDS = {"دکتر", "مهندس", "استاد", "شیخ", "آقای", "خانم", "جناب", "سرکار"}

TEACHER_COL_HINTS = ("استاد", "سخنران", "مدرس", "ارائه", "teacher", "instructor")
COURSE_COL_HINTS = ("نام دوره", "عنوان دوره", "دوره", "عنوان", "کلاس", "موضوع", "course", "title")
ATTEND_COL_HINTS = ("شرکت کننده", "شرکت کنندگان", "مخاطب", "تعداد نفر", "حاضر", "participants", "attendance")
GROUP_COL_HINTS = ("کارگروه", "بخش", "گروه", "دسته", "حوزه", "واحد", "workgroup", "category", "department")
FINANCE_COL_HINTS = ("فروشنده", "طرف حساب", "تامین", "شرکت", "فروشگاه", "شرح", "بابت", "عنوان هزینه", "vendor", "payee")
PERSON_COL_HINTS = ("نام و نام خانوادگی", "نام شرکت", "شرکت کننده", "مخاطب", "پرسنل", "عضو", "full_name", "name")


def _resolve_db_path(db_path: Path | str | None = None) -> Path | None:
    if db_path:
        p = Path(db_path)
        if p.parent.exists():
            return p
    try:
        from src.core.config import Config
        cfg_db = Path(Config.DUCKDB_PATH)
        if cfg_db.exists():
            return cfg_db
        if cfg_db.parent.exists():
            return cfg_db
    except Exception:
        pass
    dbs = discover_duckdb_files()
    return dbs[0] if dbs else None


def init_memory_tables(db_path: Path | str | None = None) -> None:
    p = _resolve_db_path(db_path)
    if not p:
        return
    with _MEM_LOCK:
        con = duckdb.connect(str(p))
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS user_rules (
                    id INTEGER PRIMARY KEY,
                    scope VARCHAR,
                    rule_text VARCHAR,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at VARCHAR
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS entity_aliases (
                    id INTEGER PRIMARY KEY,
                    entity_type VARCHAR,
                    canonical_name VARCHAR,
                    alias_name VARCHAR,
                    status VARCHAR,
                    confidence DOUBLE,
                    created_at VARCHAR
                )
                """
            )
        finally:
            con.close()


def is_summary_row(values: list[Any]) -> bool:
    """Detects Excel footer rows like 'جمع کل' / 'مجموع' so they never double totals."""
    for v in values:
        s = normalize_persian_text(v).strip(" :.-–—")
        if s and SUMMARY_ROW_RX.match(s):
            return True
    return False


def _is_collective_entry(raw: str) -> bool:
    s = normalize_persian_text(raw)
    if not s:
        return True
    return any(k in s for k in COLLECTIVE_HINTS)


def _clean_for_compare(text: str, entity_type: str) -> str:
    s = normalize_persian_text(text).lower()
    if entity_type in ("teacher", "person"):
        s = HONORIFIC_STRIP_RX.sub(" ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def split_joint_names(raw: str, entity_type: str = "teacher") -> tuple[str, list[str]]:
    """
    Token State-Machine splitter for messy Persian teacher/person cells.
    Returns (holding_mode, list_of_individual_names) where holding_mode in {'انفرادی', 'مشترک', 'گروهی'}.
    Never breaks atomic clerical honorifics like 'حجت الاسلام و المسلمین' or multi-word surnames.
    """
    txt = normalize_persian_text(raw)
    if not txt:
        return "گروهی", []
    if _is_collective_entry(txt):
        return "گروهی", [txt]
    if entity_type not in ("teacher", "person"):
        return "انفرادی", [txt]

    # 1. Strip leading plural header ("حجج الاسلام و المسلمین:")
    had_plural = bool(PLURAL_PREFIX_RX.match(txt))
    work = PLURAL_PREFIX_RX.sub("", txt).strip(" :،,-–—/")
    if not work:
        return "گروهی", [txt]

    # 2. Protect atomic multi-word clerical titles before tokenizing
    work = re.sub(r"حجت\s*الاسلام\s*و\s*المسلمین", " __HOJ_W__ ", work)
    work = re.sub(r"حجت\s*الاسلام", " __HOJ__ ", work)
    work = re.sub(r"آیت\s*الله\s*العظمی", " __AYAT_O__ ", work)
    work = re.sub(r"آیت\s*الله", " __AYAT__ ", work)
    work = re.sub(r"جناب\s*آقای", " __JENAB__ ", work)
    work = re.sub(r"سرکار\s*خانم", " __SARKAR__ ", work)

    ATOMIC_REVERSE = {
        "__HOJ_W__": "حجت الاسلام و المسلمین",
        "__HOJ__": "حجت الاسلام",
        "__AYAT_O__": "آیت الله العظمی",
        "__AYAT__": "آیت الله",
        "__JENAB__": "جناب آقای",
        "__SARKAR__": "سرکار خانم",
    }
    ALL_TITLES = set(ATOMIC_REVERSE.keys()) | SINGLE_TITLE_WORDS

    # 3. Split on strong explicit separators first
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
            # Handle conjunction "و" ONLY if followed by a title (e.g. "استاد هاشمی و استاد رضایی")
            if tok == "و" and seen_name_word and (i + 1) < len(tokens) and tokens[i + 1] in ALL_TITLES:
                if cur:
                    people.append(" ".join(ATOMIC_REVERSE.get(x, x) for x in cur))
                cur = []
                seen_name_word = False
                i += 1
                continue

            # If a new title appears AFTER we have already seen name words -> start new person!
            if tok in ALL_TITLES and seen_name_word:
                if cur:
                    people.append(" ".join(ATOMIC_REVERSE.get(x, x) for x in cur))
                cur = [tok]
                seen_name_word = False
                i += 1
                continue

            cur.append(tok)
            if tok not in ALL_TITLES and tok != "و":
                seen_name_word = True
            i += 1

        if cur:
            people.append(" ".join(ATOMIC_REVERSE.get(x, x) for x in cur))

    # Filter out title-only junk fragments & deduplicate preserving order
    clean_people: list[str] = []
    seen_cores: set[str] = set()
    for p in people:
        p_clean = re.sub(r"\s+", " ", p).strip()
        core = _clean_for_compare(p_clean, entity_type)
        if len(core) < 2:
            continue
        if core not in seen_cores:
            seen_cores.add(core)
            clean_people.append(p_clean)

    if not clean_people:
        return "گروهی", [txt]
    if len(clean_people) > 1 or had_plural:
        return ("مشترک" if len(clean_people) > 1 else "انفرادی"), clean_people
    return "انفرادی", clean_people


def list_rules(db_path: Path | str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return []
    with _MEM_LOCK:
        con = duckdb.connect(str(p))
        try:
            q = "SELECT id, scope, rule_text, is_active, created_at FROM user_rules"
            if active_only:
                q += " WHERE is_active = TRUE"
            q += " ORDER BY id DESC"
            rows = con.execute(q).fetchall()
            return [
                {
                    "id": int(r[0]),
                    "scope": str(r[1] or "general"),
                    "rule_text": str(r[2] or ""),
                    "is_active": bool(r[3]),
                    "created_at": str(r[4] or ""),
                }
                for r in rows
            ]
        finally:
            con.close()


def add_rule(rule_text: str, scope: str = "general", db_path: Path | str | None = None) -> dict[str, Any]:
    txt = (rule_text or "").strip()
    if len(txt) < 4:
        return {"ok": False, "error": "متن قانون خیلی کوتاه است."}
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}

    norm_new = normalize_persian_text(txt)
    for ex in list_rules(db_path, active_only=True):
        if normalize_persian_text(ex["rule_text"]) == norm_new:
            return {"ok": True, "already_exists": True, "rule": ex}

    now_s = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    with _MEM_LOCK:
        con = duckdb.connect(str(p))
        try:
            mx = con.execute("SELECT COALESCE(MAX(id), 0) FROM user_rules").fetchone()[0]
            nid = int(mx) + 1
            con.execute(
                "INSERT INTO user_rules VALUES (?, ?, ?, TRUE, ?)",
                [nid, (scope or "general").strip()[:40], txt, now_s],
            )
        finally:
            con.close()

    return {
        "ok": True,
        "rule": {"id": nid, "scope": scope, "rule_text": txt, "is_active": True, "created_at": now_s},
    }


def delete_rule(rule_id: int, db_path: Path | str | None = None) -> dict[str, Any]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}
    with _MEM_LOCK:
        con = duckdb.connect(str(p))
        try:
            con.execute("DELETE FROM user_rules WHERE id = ?", [int(rule_id)])
        finally:
            con.close()
    return {"ok": True}


def list_aliases(status: str | None = None, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return []
    with _MEM_LOCK:
        con = duckdb.connect(str(p))
        try:
            if status:
                rows = con.execute(
                    "SELECT id, entity_type, canonical_name, alias_name, status, confidence, created_at "
                    "FROM entity_aliases WHERE status = ? ORDER BY id DESC",
                    [status],
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT id, entity_type, canonical_name, alias_name, status, confidence, created_at "
                    "FROM entity_aliases ORDER BY id DESC"
                ).fetchall()
            return [
                {
                    "id": int(r[0]),
                    "entity_type": str(r[1] or "general"),
                    "canonical_name": str(r[2] or ""),
                    "alias_name": str(r[3] or ""),
                    "status": str(r[4] or "approved"),
                    "confidence": float(r[5] or 1.0),
                    "created_at": str(r[6] or ""),
                }
                for r in rows
            ]
        finally:
            con.close()


def resolve_canonical_map(entity_type: str = "teacher", db_path: Path | str | None = None) -> dict[str, str]:
    """
    Builds a cycle-safe transitive alias map (A -> B -> C resolves both A and B to C).
    Keys are honorific-stripped normalized core names for rock-solid matching.
    """
    approved = [a for a in list_aliases(status="approved", db_path=db_path) if a["entity_type"] == entity_type]
    direct_core: dict[str, str] = {}
    core_to_display: dict[str, str] = {}

    for a in approved:
        c_disp = a["canonical_name"].strip()
        c_core = _clean_for_compare(c_disp, entity_type)
        a_core = _clean_for_compare(a["alias_name"], entity_type)
        if not c_core or not a_core:
            continue
        direct_core[a_core] = c_core
        core_to_display[c_core] = c_disp

    resolved: dict[str, str] = {}
    for start_core in set(direct_core.keys()) | set(core_to_display.keys()):
        cur = start_core
        visited = {cur}
        while cur in direct_core and direct_core[cur] not in visited:
            cur = direct_core[cur]
            visited.add(cur)
        resolved[start_core] = core_to_display.get(cur, cur)
    return resolved


def save_alias(
    canonical_name: str,
    alias_name: str,
    entity_type: str = "teacher",
    status: str = "approved",
    confidence: float = 1.0,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    c_clean = (canonical_name or "").strip()
    a_clean = (alias_name or "").strip()
    if not c_clean or not a_clean:
        return {"ok": False, "error": "نام اصلی و نام معادل هر دو الزامی هستند."}
    if normalize_persian_text(c_clean) == normalize_persian_text(a_clean) and c_clean == a_clean:
        return {"ok": False, "error": "دو عبارت کاملاً یکسان هستند."}

    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}

    st = status if status in ("approved", "rejected") else "approved"
    et = (entity_type or "general").strip()[:30]
    now_s = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    existing = list_aliases(db_path=db_path)
    pair_key = tuple(sorted([_clean_for_compare(c_clean, et), _clean_for_compare(a_clean, et)]))
    updated_id = None

    with _MEM_LOCK:
        con = duckdb.connect(str(p))
        try:
            for ex in existing:
                ex_key = tuple(sorted([_clean_for_compare(ex["canonical_name"], et), _clean_for_compare(ex["alias_name"], et)]))
                if ex_key == pair_key and ex["entity_type"] == et:
                    con.execute(
                        "UPDATE entity_aliases SET canonical_name = ?, alias_name = ?, status = ?, created_at = ? WHERE id = ?",
                        [c_clean, a_clean, st, now_s, ex["id"]],
                    )
                    updated_id = ex["id"]
                    break
            if updated_id is None:
                mx = con.execute("SELECT COALESCE(MAX(id), 0) FROM entity_aliases").fetchone()[0]
                updated_id = int(mx) + 1
                con.execute(
                    "INSERT INTO entity_aliases VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [updated_id, et, c_clean, a_clean, st, float(confidence), now_s],
                )
        finally:
            con.close()

    if et == "teacher":
        try:
            rebuild_clean_teacher_layer(db_path)
        except Exception as exc:
            logger.warning("Could not refresh smart_teachers_exploded after save_alias: %s", exc)

    return {"ok": True, "id": updated_id}


def delete_alias(alias_id: int, db_path: Path | str | None = None) -> dict[str, Any]:
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "error": "پایگاه‌داده یافت نشد."}
    with _MEM_LOCK:
        con = duckdb.connect(str(p))
        try:
            con.execute("DELETE FROM entity_aliases WHERE id = ?", [int(alias_id)])
        finally:
            con.close()
    try:
        rebuild_clean_teacher_layer(db_path)
    except Exception:
        pass
    return {"ok": True}


def _teacher_layer_signature(db_path: Path, con=None) -> str:
    try:
        st = db_path.stat()
        aliases = []
        if con is not None:
            tbls = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
            if "entity_aliases" in tbls:
                aliases = con.execute(
                    "SELECT entity_type, canonical_name, alias_name, status FROM entity_aliases WHERE entity_type = 'teacher'"
                ).fetchall()
        return f"{st.st_mtime_ns}:{st.st_size}:{hash(tuple(aliases))}"
    except Exception:
        return ""


def rebuild_clean_teacher_layer(db_path: Path | str | None = None, force: bool = False) -> dict[str, Any]:
    """
    Materializes clean `smart_teachers_exploded` DuckDB table without altering raw source tables:
    - Filters out Excel footer/summary rows ('جمع کل', 'مجموع')
    - Splits joint/multi-teacher courses via Token State-Machine
    - Applies transitive approved `entity_aliases` + automatic honorific unification
    - Computes `سهم_تعدیل_شده_مخاطب` (= attendance / teacher_count) to prevent double-counting
    """
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return {"ok": False, "rows": 0}

    if not force:
        try:
            _c_chk = duckdb.connect(str(p))
            try:
                _tbls_chk = {r[0] for r in _c_chk.execute("SHOW TABLES").fetchall()}
                if "smart_teachers_exploded" in _tbls_chk and "_meta_teacher_sig" in _tbls_chk:
                    _saved_sig = _c_chk.execute("SELECT sig FROM _meta_teacher_sig LIMIT 1").fetchone()
                    _cur_sig = _teacher_layer_signature(p, _c_chk)
                    if _saved_sig and _saved_sig[0] == _cur_sig and _cur_sig:
                        _rc = _c_chk.execute("SELECT COUNT(*) FROM smart_teachers_exploded").fetchone()[0]
                        return {"ok": True, "rows": int(_rc), "cached": True}
            finally:
                _c_chk.close()
        except Exception:
            pass
    alias_map = resolve_canonical_map("teacher", db_path)

    with _MEM_LOCK:
        con = duckdb.connect(str(p))
        try:
            tables = [str(r[0]) for r in con.execute("SHOW TABLES").fetchall()]
            cat_map: dict[str, tuple[str, str]] = {}
            if "tabular_catalog" in tables:
                for tn, fn, sh in con.execute("SELECT table_name, file_name, source_sheet FROM tabular_catalog").fetchall():
                    cat_map[str(tn)] = (str(fn or ""), str(sh or ""))

            # Pass 1: Read raw course rows & pick preferred display label for each exact core name
            raw_records: list[tuple[str, str, str, str, float, str, list[str]]] = []
            core_freq_display: dict[str, dict[str, int]] = {}

            for tname in tables:
                if tname.lower() in INTERNAL_TABLES or tname.lower().startswith("view_"):
                    continue
                safe_t = tname.replace('"', '""')
                try:
                    cols = [str(c[0]) for c in con.execute(f'DESCRIBE "{safe_t}"').fetchall()]
                except Exception:
                    continue

                t_col = next((c for c in cols if any(h in normalize_persian_text(c).lower() for h in TEACHER_COL_HINTS)), None)
                c_col = next((c for c in cols if any(h in normalize_persian_text(c).lower() for h in COURSE_COL_HINTS)), None)
                a_col = next((c for c in cols if any(h in normalize_persian_text(c).lower() for h in ATTEND_COL_HINTS)), None)
                if not t_col or (not c_col and not a_col):
                    continue

                sel_cols = [t_col]
                if c_col:
                    sel_cols.append(c_col)
                if a_col:
                    sel_cols.append(a_col)
                q_cols = ", ".join(f'"{c.replace(chr(34), chr(34)*2)}"' for c in sel_cols)
                try:
                    rows = con.execute(f'SELECT {q_cols} FROM "{safe_t}"').fetchall()
                except Exception:
                    continue

                fn, sh = cat_map.get(tname, (tname, ""))
                for r in rows:
                    if is_summary_row(list(r)):
                        continue
                    raw_teacher = str(r[0] or "").strip()
                    if not raw_teacher:
                        continue
                    idx = 1
                    course_title = str(r[idx] or "").strip() if c_col else ""
                    if c_col:
                        idx += 1
                    att_val = parse_dirty_number(r[idx]) if a_col else None
                    att_num = float(att_val) if att_val is not None else 0.0

                    mode, parts = split_joint_names(raw_teacher, "teacher")
                    raw_records.append((fn, sh, course_title, raw_teacher, att_num, mode, parts))
                    if mode != "گروهی":
                        for pt in parts:
                            core = _clean_for_compare(pt, "teacher")
                            if core:
                                d = core_freq_display.setdefault(core, {})
                                d[pt] = d.get(pt, 0) + 1

            # Choose nicest default display name per core (prefers most frequent, then longest with honorific)
            default_display: dict[str, str] = {}
            for core, dmap in core_freq_display.items():
                best = sorted(dmap.items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]
                default_display[core] = best

            # Pass 2: Materialize smart_teachers_exploded
            con.execute("DROP TABLE IF EXISTS smart_teachers_exploded")
            con.execute(
                """
                CREATE TABLE smart_teachers_exploded (
                    "فایل_منبع" VARCHAR,
                    "بخش_منبع" VARCHAR,
                    "نام_دوره" VARCHAR,
                    "نام_استاد_خام" VARCHAR,
                    "نام_معیار_استاد" VARCHAR,
                    "نوع_برگزاری" VARCHAR,
                    "تعداد_اساتید_دوره" INTEGER,
                    "تعداد_شرکت_کنندگان" DOUBLE,
                    "سهم_تعدیل_شده_مخاطب" DOUBLE,
                    "همکاران_مشترک" VARCHAR
                )
                """
            )

            out_rows: list[tuple] = []
            counts = {"انفرادی": 0, "مشترک": 0, "گروهی": 0}
            for fn, sh, course_title, raw_teacher, att_num, mode, parts in raw_records:
                if mode == "گروهی" or not parts:
                    counts["گروهی"] += 1
                    out_rows.append((fn, sh, course_title, raw_teacher, raw_teacher, "گروهی", 1, att_num, att_num, ""))
                    continue

                resolved_names = []
                for pt in parts:
                    core = _clean_for_compare(pt, "teacher")
                    canon = alias_map.get(core) or default_display.get(core, pt)
                    resolved_names.append(canon)

                n_t = max(1, len(resolved_names))
                adj_att = round(att_num / n_t, 4)
                counts[mode] = counts.get(mode, 0) + n_t
                for idx_t, canon in enumerate(resolved_names):
                    peers = "، ".join(x for j, x in enumerate(resolved_names) if j != idx_t)
                    out_rows.append((fn, sh, course_title, raw_teacher, canon, mode, n_t, att_num, adj_att, peers))

            if out_rows:
                con.executemany(
                    "INSERT INTO smart_teachers_exploded VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    out_rows,
                )

            con.execute("CREATE TABLE IF NOT EXISTS _meta_teacher_sig (sig VARCHAR); DELETE FROM _meta_teacher_sig; INSERT INTO _meta_teacher_sig VALUES (?)", [_teacher_layer_signature(p, con)])
            return {"ok": True, "rows": len(out_rows), "breakdown": counts}
        finally:
            con.close()



def _compound_match_bonus(ca: str, cb: str, entity_type: str) -> tuple[float, str]:
    """
    Scores genuine variant pairs (full name vs short/partial name or spelling variant)
    while preventing false matches on distinct first names ('اکبر روستایی' vs 'علی اکبر بابایی')
    and avoiding noisy pair explosions across distinct multi-word names sharing a common surname.
    """
    wa = [w for w in ca.split() if len(w) >= 2]
    wb = [w for w in cb.split() if len(w) >= 2]
    if not wa or not wb:
        return 0.0, ""

    sa, sb = set(wa), set(wb)
    overlap = sa & sb
    if not overlap:
        return 0.0, ""

    short_w, long_w = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    short_s, long_s = set(short_w), set(long_w)

    # 1. Exact multi-word subset (e.g., "هاشمی گلپایگانی" inside "سیدرضا هاشمی گلپایگانی")
    if len(short_s) >= 2 and short_s.issubset(long_s):
        return 0.90, ""

    # 2. Single-token name inside a longer name: only if token is NOT a pure common given-name collision
    #    unless the last token (surname) matches.
    if len(short_s) == 1 and short_s.issubset(long_s) and len(long_s) <= 4:
        tok = next(iter(short_s))
        if len(tok) >= 3 and entity_type in ("teacher", "person"):
            # If tok only matched a non-final given name while last names differ, reject
            if len(long_w) >= 2 and tok != long_w[-1]:
                return 0.0, ""
            if tok in COMMON_SURNAMES:
                return 0.75, "احتیاط: نام خانوادگی پرتکرار؛ پیش از ادغام بررسی کنید یک شخص هستند یا خیر"
            return 0.84, ""

    # 3. Stem match: require matching surname/tail token to avoid "اکبر روستایی" vs "علی اکبر بابایی"
    if entity_type in ("teacher", "person") and len(wa) >= 2 and len(wb) >= 2:
        if wa[-1] != wb[-1] and not (len(wa[-1]) >= 4 and len(wb[-1]) >= 4 and (wa[-1] in wb[-1] or wb[-1] in wa[-1])):
            return 0.0, ""

    stem_hits = sum(1 for x in short_s for y in long_s if len(x) >= 4 and len(y) >= 4 and (x in y or y in x))
    if stem_hits >= 1 and len(short_s) <= 3:
        hit_tok = next((x for x in short_s for y in long_s if len(x) >= 4 and len(y) >= 4 and (x in y or y in x)), "")
        if entity_type in ("teacher", "person") and hit_tok in COMMON_SURNAMES:
            # If both sides already have distinct qualifiers (e.g. "حسینی شیرازی" vs "حسینی قمی"), suppress noise
            if len(wa) >= 2 and len(wb) >= 2:
                return 0.0, ""
            return 0.74, "احتیاط: نام خانوادگی پرتکرار؛ پیش از ادغام بررسی کنید یک شخص هستند یا خیر"
        return 0.81, ""

    return 0.0, ""


def _fuzzy_score(a: str, b: str, entity_type: str) -> tuple[float, str]:
    """Returns (similarity_score_0_to_1, optional_caution_label)."""
    ca = _clean_for_compare(a, entity_type)
    cb = _clean_for_compare(b, entity_type)
    if not ca or not cb or ca == cb:
        return 0.0, ""

    ta = set(ca.split())
    tb = set(cb.split())
    if not ta or not tb:
        return 0.0, ""

    inter = ta & tb
    seq_ratio = SequenceMatcher(None, ca, cb).ratio()
    jaccard = len(inter) / len(ta | tb)

    GENERIC_WORDS = {
        "کارگروه", "گروه", "بخش", "دوره", "کلاس", "جمعی", "اساتید",
        "خرید", "هزینه", "فاکتور", "سید", "محمد", "علی", "حسین", "حسن", "رضا", "مهدی",
    }
    meaningful_inter = [w for w in inter if len(w) >= 3 and w not in GENERIC_WORDS]

    caution = ""
    score = 0.0
    if meaningful_inter:
        score = max(seq_ratio, (seq_ratio * 0.55 + jaccard * 0.45))
    elif seq_ratio >= 0.87 and min(len(ca), len(cb)) >= 7:
        score = seq_ratio
    else:
        return 0.0, ""

    bonus_score, bonus_caution = _compound_match_bonus(ca, cb, entity_type)
    if bonus_score > score:
        score = bonus_score
    elif not meaningful_inter and entity_type in ("teacher", "person"):
        return 0.0, ""

    if bonus_caution and not caution:
        caution = bonus_caution
    return round(min(0.98, score), 3), caution


def _classify_column(col_name: str) -> str | None:
    cn = normalize_persian_text(col_name).lower()
    if any(k in cn for k in TEACHER_COL_HINTS):
        return "teacher"
    if any(k in cn for k in GROUP_COL_HINTS):
        return "workgroup"
    if any(k in cn for k in FINANCE_COL_HINTS):
        return "finance"
    if any(k in cn for k in PERSON_COL_HINTS):
        return "person"
    return None


def scan_fuzzy_candidates(
    db_path: Path | str | None = None,
    min_score: float = 0.73,
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """
    Splits joint teacher cells FIRST, deduplicates trivial honorific variants automatically,
    and surfaces ONLY genuine ambiguous pairs for Human-in-the-Loop approval.
    """
    init_memory_tables(db_path)
    p = _resolve_db_path(db_path)
    if not p:
        return []

    decided_pairs: set[tuple[str, str, str]] = set()
    for ex in list_aliases(db_path=db_path):
        et = ex["entity_type"]
        k = tuple(sorted([_clean_for_compare(ex["canonical_name"], et), _clean_for_compare(ex["alias_name"], et)]))
        decided_pairs.add((et, k[0], k[1]))

    # Map: entity_type -> core_name -> {"count": int, "displays": {raw: count}}
    core_buckets: dict[str, dict[str, dict[str, Any]]] = {
        "teacher": {}, "workgroup": {}, "finance": {}, "person": {}
    }

    with _MEM_LOCK:
        con = duckdb.connect(str(p))
        try:
            tables = [str(r[0]) for r in con.execute("SHOW TABLES").fetchall()]
            for tname in tables:
                if tname.lower() in INTERNAL_TABLES or tname.lower().startswith("view_"):
                    continue
                safe_t = tname.replace('"', '""')
                try:
                    cols = [str(c[0]) for c in con.execute(f'DESCRIBE "{safe_t}"').fetchall()]
                except Exception:
                    continue
                for cname in cols:
                    etype = _classify_column(cname)
                    if not etype:
                        continue
                    safe_c = cname.replace('"', '""')
                    try:
                        rows = con.execute(
                            f'SELECT CAST("{safe_c}" AS VARCHAR) AS v, COUNT(*) AS cnt '
                            f'FROM "{safe_t}" WHERE "{safe_c}" IS NOT NULL '
                            f'GROUP BY v ORDER BY cnt DESC LIMIT 200'
                        ).fetchall()
                    except Exception:
                        continue
                    for val, cnt in rows:
                        sv = str(val or "").strip()
                        if len(sv) < 3 or len(sv) > 120 or is_summary_row([sv]):
                            continue
                        mode, parts = split_joint_names(sv, etype)
                        if mode == "گروهی":
                            continue
                        for pt in parts:
                            core = _clean_for_compare(pt, etype)
                            if len(core) < 3:
                                continue
                            entry = core_buckets[etype].setdefault(core, {"count": 0, "displays": {}})
                            entry["count"] += int(cnt)
                            entry["displays"][pt] = entry["displays"].get(pt, 0) + int(cnt)
        finally:
            con.close()

    type_labels = {
        "teacher": "استاد / سخنران",
        "workgroup": "کارگروه / دسته‌بندی",
        "finance": "شرح / فروشنده مالی",
        "person": "مخاطب / پرسنل",
    }

    candidates: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str]] = set()

    for etype, cmap in core_buckets.items():
        cores = sorted(cmap.keys(), key=lambda c: (-cmap[c]["count"], len(c)))[:140]
        n = len(cores)
        for i in range(n):
            for j in range(i + 1, n):
                ca, cb = cores[i], cores[j]
                pk = (etype, min(ca, cb), max(ca, cb))
                if pk in decided_pairs or pk in seen_pairs:
                    continue

                disp_a = sorted(cmap[ca]["displays"].items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]
                disp_b = sorted(cmap[cb]["displays"].items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]

                score, caution = _fuzzy_score(disp_a, disp_b, etype)
                if score < min_score:
                    continue

                seen_pairs.add(pk)
                cnt_a, cnt_b = cmap[ca]["count"], cmap[cb]["count"]
                if cnt_a > cnt_b:
                    suggested_canonical, alias_val = disp_a, disp_b
                elif cnt_b > cnt_a:
                    suggested_canonical, alias_val = disp_b, disp_a
                else:
                    suggested_canonical, alias_val = (disp_a, disp_b) if len(ca) >= len(cb) else (disp_b, disp_a)

                candidates.append(
                    {
                        "entity_type": etype,
                        "entity_label": type_labels.get(etype, etype),
                        "item_a": disp_a,
                        "count_a": cnt_a,
                        "item_b": disp_b,
                        "count_b": cnt_b,
                        "suggested_canonical": suggested_canonical,
                        "alias_candidate": alias_val,
                        "confidence": round(score * 100),
                        "caution": caution,
                    }
                )

    candidates.sort(key=lambda x: (-x["confidence"], -(x["count_a"] + x["count_b"])))
    return candidates[:max_results]


def build_memory_prompt_block(db_path: Path | str | None = None) -> str:
    rules = list_rules(db_path, active_only=True)
    aliases = list_aliases(status="approved", db_path=db_path)
    rejected = list_aliases(status="rejected", db_path=db_path)

    if not rules and not aliases and not rejected:
        return ""

    lines = ["### حافظه قوانین دائمی و تطبیق نام‌های تأییدشده توسط کاربر (لازم‌الاجرا در همه تحلیل‌ها):"]
    if rules:
        lines.append("قوانین ثبت‌شده:")
        for r in rules[:40]:
            lines.append(f"- [{r['scope']}] {r['rule_text']}")

    if aliases:
        lines.append("\nنام‌ها و دسته‌بندی‌های معادل (در جدول smart_teachers_exploded خودکار اعمال شده‌اند؛ در سایر جداول نیز یکی حساب شوند):")
        for a in aliases[:60]:
            lines.append(f'- ({a["entity_type"]}) «{a["alias_name"]}» ≡ «{a["canonical_name"]}»')

    if rejected:
        lines.append("\nموارد مجزا (کاربر تأیید کرده این جفت‌ها یکی نیستند؛ هرگز ادغامشان نکن):")
        for rj in rejected[:30]:
            lines.append(f'- «{rj["canonical_name"]}» ≠ «{rj["alias_name"]}»')

    return "\n".join(lines)


def get_memory_state() -> dict[str, Any]:
    try:
        rules = list_rules(active_only=True)
        aliases = list_aliases(status="approved")
        pending = scan_fuzzy_candidates()
        return {
            "ok": True,
            "rules": rules,
            "aliases": aliases,
            "pending": pending,
            "pending_count": len(pending),
        }
    except Exception as exc:
        logger.exception("get_memory_state failed")
        return {"ok": False, "error": str(exc), "rules": [], "aliases": [], "pending": [], "pending_count": 0}


def _bind_memory_api(js_api) -> None:
    if js_api is None:
        return
    cls = type(js_api)
    methods = {
        "get_memory_state": lambda self: get_memory_state(),
        "add_user_rule": lambda self, rule_text="", scope="general": add_rule(rule_text, scope),
        "delete_user_rule": lambda self, rule_id=0: delete_rule(int(rule_id)),
        "resolve_fuzzy_pair": lambda self, canonical_name="", alias_name="", entity_type="teacher", decision="approved", confidence=1.0: save_alias(
            canonical_name=canonical_name,
            alias_name=alias_name,
            entity_type=entity_type,
            status=("approved" if decision == "approved" else "rejected"),
            confidence=float(confidence or 1.0),
        ),
        "delete_entity_alias": lambda self, alias_id=0: delete_alias(int(alias_id)),
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
                api_obj = kwargs.get("js_api")
                if api_obj is None and len(args) >= 4:
                    api_obj = args[3]
                if api_obj is not None:
                    _bind_memory_api(api_obj)
                return orig_create(*args, **kwargs)

            _wrapped_create_window._eh_mem_wrapped = True  # type: ignore[attr-defined]
            webview.create_window = _wrapped_create_window
    except Exception as exc:
        logger.warning("Could not hook webview.create_window for memory engine: %s", exc)
