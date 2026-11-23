import csv
import difflib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.config import Config
from src.core.db_manager import (
    INTERNAL_TABLES,
    JALALI_MONTHS,
    detect_duplicate_files,
    duckdb_session,
    is_summary_row_smart,
    normalize_persian,
    parse_jalali_date,
    parse_number_strict,
    classify_non_expense_row,
    clean_excel_cell_value,
    canonical_teacher_core,
    clean_participant_name,
    detect_workgroup_unified,
    extract_roster_banner_meta,
    is_blank_numbered_row,
    is_banner_header_col,
    is_non_entity_value,
    is_valid_teacher_name,
    match_roster_to_summary_courses,
    promote_banner_headers,
    resolve_default_duckdb_path,
)
from src.core.memory_engine import (
    _clean_for_compare,
    load_brain_config,
    resolve_canonical_map,
    save_alias,
    split_joint_names,
)

SUITE_FILE = Config.STORAGE_DIR / "ehadi_suite.json"
LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_fa(text: Any) -> str:
    return normalize_persian(text)


def canon_key(text: Any) -> str:
    s = normalize_fa(text).replace("آ", "ا")
    s = re.sub(r"[\s\u200c\u200f\u200e\-_./\\()«»\"'،,؛;:]", "", s)
    return s.lower()


_JUNK_EXACT_OR_STRUCT_RX = re.compile(
    r"^(?:"
    r"(?:اسلاید|slide|جدول|table|صفحه|page|شیت|sheet|ردیف|برگه)\s*(?:\d+(?:\s*\([^)]*\))?)?|"
    r"(?:جمع|مجموع)(?:\s*(?:کل|نهایی|جزئی|فرعی))?|"
    r"میانگین|معدل|total|subtotal|grand\s*total|"
    r"مانده(?:\s*از)?\s*(?:قبل|قبلی|ماه\s*قبل|دوره\s*قبل)"
    r")$"
)


def is_junk_label(label: str) -> bool:
    low = normalize_fa(label).lower().strip(" :.-–—()[]")
    if not low or len(low) < 2:
        return True
    if is_non_entity_value(low):
        return True
    if "کارگروه" in low:
        return False
    if _JUNK_EXACT_OR_STRUCT_RX.match(low):
        return True
    if low.startswith(("جمع کل", "مجموع کل", "جمع نهایی", "مانده از قبل", "مانده قبلی", "grand total", "subtotal")):
        return True
    return False


def normalize_phone(text: Any) -> str:
    """Normalizes Iranian mobile numbers (09xxxxxxxxx) and preserves international numbers (+92/+93/+964...) cleanly."""
    raw = re.sub(r"\.0+$", "", str(text or "").strip()).translate(LATIN_DIGITS)
    if not raw:
        return ""
    # If cell contains multiple numbers separated by / or ، or , or - (space-padded), inspect each candidate first
    parts = [p.strip() for p in re.split(r"[/،,;\n]+|\s+-\s+", raw) if p.strip()]
    for part in parts:
        has_plus = part.lstrip().startswith("+")
        digits = re.sub(r"\D", "", part)
        if not digits:
            continue
        # Iranian mobile: 00989xxxxxxxxx (14), 989xxxxxxxxx (12), 09xxxxxxxxx (11), 9xxxxxxxxx (10)
        if digits.startswith("00989") and len(digits) == 14:
            return "0" + digits[4:]
        if digits.startswith("989") and len(digits) == 12:
            return "0" + digits[2:]
        if digits.startswith("09") and len(digits) == 11:
            return digits
        if digits.startswith("9") and len(digits) == 10:
            return "0" + digits
        # International mobile/WhatsApp (e.g. +93 Afghanistan, +92 Pakistan, +91 India, +964 Iraq, +961 Lebanon)
        if (has_plus or digits.startswith("00")) and 10 <= len(digits) <= 15:
            clean_intl = digits[2:] if digits.startswith("00") else digits
            if clean_intl.startswith("989") and len(clean_intl) == 12:
                return "0" + clean_intl[2:]
            return "+" + clean_intl
        # Iranian landline (025..., 021...)
        if digits.startswith("0") and len(digits) == 11:
            return digits
    # Fallback: search for embedded Iranian mobile pattern inside noisy text
    m_ir = re.search(r"(?:0098|98|0)?(9\d{9})", re.sub(r"[\s\-()]", "", raw))
    if m_ir:
        return "0" + m_ir.group(1)
    return ""


def classify_identity_doc(text: Any) -> tuple[str, str]:
    """
    Normalizes and classifies Iranian National IDs AND foreign national identity documents:
      - Iranian National ID (کد ملی): 8-10 digits -> ('nid', 10-digit zero-padded)
      - Foreign FIDA / Faragir / Amayesh / Pakistani CNIC (کد فراگیر اتباع / فیدا / آمایش): 11-14 digits -> ('fida', digits)
      - International Passport (گذرنامه / پاسپورت اتباع افغان، پاکستانی، هندی، عراقی...):
        alphanumeric containing Latin letters + digits (6-14 chars, e.g. P01234567, OA1234567, AB1234567) -> ('passport', UPPER_ALNUM)
    """
    raw = re.sub(r"\.0+$", "", str(text or "").strip()).translate(LATIN_DIGITS)
    if not raw or raw in ("-", "—", "–", "ندارد", "ثبت نشده", "ثبت‌نشده", "نامشخص", "null", "none", "nan"):
        return "", ""
    alnum = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not alnum:
        return "", ""
    letters = re.findall(r"[A-Z]", alnum)
    digits = re.sub(r"\D", "", alnum)
    if 1 <= len(letters) <= 4 and len(digits) >= 5 and 6 <= len(alnum) <= 14:
        return "passport", alnum
    if alnum.isdigit():
        if 8 <= len(digits) <= 10:
            return "nid", digits.zfill(10)
        if 11 <= len(digits) <= 14:
            if len(digits) == 11 and digits.startswith("09"):
                return "", ""
            return "fida", digits
    return "", ""


def normalize_nid(text: Any) -> str:
    """Returns normalized National ID, FIDA/Faragir code, or Foreign Passport number."""
    _, val = classify_identity_doc(text)
    return val


def _detect_session_columns(cols: list[str], reserved_idxs: set[int]) -> list[tuple[int, str]]:
    """Detects attendance session columns like '1\\n03/17', '2\\n05/27', 'جلسه 1', 'روز 2', '03/17'."""
    out: list[tuple[int, str]] = []
    for idx, raw_c in enumerate(cols):
        if idx in reserved_idxs:
            continue
        cn = normalize_fa(raw_c).translate(LATIN_DIGITS)
        if not cn:
            continue
        one_line = re.sub(r"\s+", " ", cn).strip()
        is_sess = bool(
            re.search(r"\b\d{1,2}/\d{1,2}\b", one_line)
            or re.search(r"^(?:جلسه|روز|نشست|session|day)\s*\d{1,2}\b", one_line, re.IGNORECASE)
            or re.fullmatch(r"\d{1,2}\s+\d{1,2}/\d{1,2}", one_line)
            or (re.fullmatch(r"\d{1,2}", one_line) and idx >= 3)
        )
        if is_sess:
            lbl = one_line
            m_sd = re.fullmatch(r"(\d{1,2})\s+(\d{1,2}/\d{1,2})", one_line)
            if m_sd:
                lbl = f"جلسه {m_sd.group(1)} ({m_sd.group(2)})"
            elif re.fullmatch(r"\d{1,2}", one_line):
                lbl = f"جلسه {one_line}"
            out.append((idx, lbl))
    return out


def _classify_session_cell(val: Any) -> tuple[str, str]:
    """Classifies an attendance sheet cell into (present|late|excused|spam|absent, clean_label)."""
    cleaned = str(clean_excel_cell_value(val) or "").strip()
    if not cleaned:
        return "absent", "غایب"
    low = normalize_fa(cleaned).translate(LATIN_DIGITS).lower()
    if low in ("-", "—", "0", "غ", "غایب", "غیبت", "خیر", "no", "absent", "nan", "none"):
        return "absent", "غایب"
    if "تاخیر" in low or "تأخیر" in low or "late" in low:
        return "late", cleaned
    if any(tok in low for tok in ("✓", "✔", "☑", "ü", "حاضر", "حضور", "بله", "yes", "ok", "present")) or low in ("1", "ح", "x", "+"):
        return "present", "حاضر"
    if "هرزنامه" in low or "اسپم" in low or "spam" in low:
        return "spam", "هرزنامه"
    if any(tok in low for tok in ("ع پ", "ع.پ", "عذر", "موجه", "عتبات", "مسافرت", "سفر", "کسالت", "بیمار", "مشکل", "شهرستان", "ماموریت", "مرخصی", "کار", "امتحان", "excused")):
        return "excused", cleaned
    return "excused", cleaned


def parse_number(val: Any) -> float:
    n = parse_number_strict(val)
    return float(n) if n is not None else 0.0


def extract_year(text: Any) -> str:
    return parse_jalali_date(text).get("year") or ""


def extract_month_idx(text: Any) -> int:
    m = int(parse_jalali_date(text).get("month") or 0)
    return (m - 1) if 1 <= m <= 12 else -1


def _find_duckdb_path() -> Path | None:
    p = resolve_default_duckdb_path()
    return p if (p and p.exists()) else None


def _compute_median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    mid = len(s) // 2
    return round(float(s[mid]), 1) if len(s) % 2 == 1 else round(float(s[mid - 1] + s[mid]) / 2.0, 1)


def _compute_workload_balance(counts: list[float]) -> dict[str, Any]:
    valid = sorted(float(x) for x in counts if x and x > 0)
    n = len(valid)
    if n <= 1:
        return {"score": 100, "top3_share_pct": 100.0 if n == 1 else 0.0, "label": "محدود"}
    total = sum(valid)
    if total <= 0:
        return {"score": 100, "top3_share_pct": 0.0, "label": "نامشخص"}
    weighted = sum((i + 1) * v for i, v in enumerate(valid))
    gini = (2.0 * weighted) / (n * total) - (n + 1.0) / n
    balance = max(0, min(100, round((1.0 - max(0.0, gini)) * 100)))
    top3 = round((sum(valid[-3:]) / total) * 100, 1)
    lbl = "متوازن" if balance >= 70 else ("نسبتاً متمرکز" if balance >= 45 else "تمرکز بالا روی چند استاد")
    return {"score": balance, "top3_share_pct": top3, "label": lbl}


class ExecutiveAnalyticsEngine:
    def __init__(self):
        Config.ensure_directories()
        self._ensure_suite_file()

    def _ensure_suite_file(self) -> dict[str, Any]:
        default_data = {
            "letter_seq": 0, "letters": [], "registrations": [],
            "merges": {}, "teacher_meta": {}, "events": [],
        }
        if not SUITE_FILE.exists():
            SUITE_FILE.write_text(json.dumps(default_data, ensure_ascii=False, indent=2), encoding="utf-8")
            return default_data
        try:
            data = json.loads(SUITE_FILE.read_text(encoding="utf-8"))
            for k, v in default_data.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            SUITE_FILE.write_text(json.dumps(default_data, ensure_ascii=False, indent=2), encoding="utf-8")
            return default_data

    def _save_suite(self, data: dict[str, Any]) -> None:
        SUITE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


    def _load_slide_texts(self) -> dict[tuple[str, str], str]:
        slide_texts: dict[tuple[str, str], str] = {}
        try:
            import lancedb
            db = lancedb.connect(str(Config.LANCEDB_PATH))
            if "document_chunks" not in db.table_names():
                return slide_texts
            rows = db.open_table("document_chunks").to_pandas().to_dict(orient="records")
            for r in rows:
                fn = str(r.get("file_name") or "")
                loc = normalize_fa(str(r.get("location") or ""))
                txt = str(r.get("content") or "")
                if fn and loc:
                    slide_texts[(fn, loc)] = (slide_texts.get((fn, loc), "") + "\n" + txt).strip()
        except Exception:
            pass
        return slide_texts

    def _scan_duckdb(self, data_mode: str = "clean") -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        courses, persons, costs = [], [], []
        db_path = _find_duckdb_path()
        slide_texts = self._load_slide_texts()
        brain_cfg_local = load_brain_config()
        learned_fin_rules = dict(brain_cfg_local.get("finance_category_rules") or {})
        if not db_path:
            return courses, persons, costs

        try:
            with duckdb_session(db_path) as con:
                tables = [str(r[0]) for r in con.execute("SHOW TABLES").fetchall()]
                cat_map: dict[str, tuple[str, str]] = {}
                if "tabular_catalog" in tables:
                    for tn, fn, sh in con.execute("SELECT table_name, file_name, source_sheet FROM tabular_catalog").fetchall():
                        cat_map[str(tn)] = (str(fn or tn), str(sh or ""))

                _ID_DOC_KWS = (
                    "کد ملی", "کدملی", "شماره ملی", "گذرنامه", "پاسپورت", "شماره گذرنامه", "شماره پاسپورت",
                    "کد فراگیر", "کد یکتا", "کد اتباع", "فیدا", "آمایش", "شناسه هویتی", "شماره مدرک",
                    "national", "passport", "fida", "cnic",
                )
                _PERSON_KWS = (
                    "نام و نام خانوادگی", "نام خانوادگی", "نام شرکت کننده", "شرکت کننده", "شرکت‌کننده",
                    "دانش پژوه", "دانش‌پژوه", "طلبه", "فراگیر", "ثبت نام کننده", "پاسخ دهنده", "full_name", "participant",
                )
                _PHONE_KWS = ("موبایل", "همراه", "تلفن", "شماره تماس", "phone", "mobile")

                preloaded_db: list[tuple[str, str, str, list[str], list[tuple], str, list[str]]] = []
                course_wg_map: dict[str, str] = {}
                roster_clean_counts: Counter = Counter()
                has_raw_rosters = False

                def _is_summary_tbl(nc_list: list[str], sh_name: str) -> bool:
                    sh_n = normalize_fa(sh_name)
                    if any(k in sh_n for k in ("داشبورد آماری", "کارنامه جامع", "خلاصه کارگروه")):
                        return True
                    has_wg = any("نام کارگروه" in nc or nc == "کارگروه" for nc in nc_list)
                    m_cnt = sum(1 for k in ("تعداد دوره", "مجموع ثبت نام", "افراد یکتا", "مجموع جلسات", "میانگین جلسات") if any(k in nc for nc in nc_list))
                    return has_wg and m_cnt >= 2

                def _is_matrix_tbl(nc_list: list[str]) -> bool:
                    has_p = any(any(k in nc for k in _PERSON_KWS) for nc in nc_list)
                    has_ph = any(any(k in nc for k in _PHONE_KWS + _ID_DOC_KWS) for nc in nc_list)
                    has_desc = any(any(k in nc for k in ("شرح دوره", "جزئیات کل دوره", "کارگروه های فعال")) for nc in nc_list)
                    return has_p and has_ph and has_desc and len(nc_list) >= 7

                def _split_sheet_num(sh_name: str) -> tuple[str, str]:
                    s_n = normalize_fa(sh_name)
                    m = re.match(r"^(\d+)\s*[\-–—ـ.]\s*(.+)$", s_n)
                    return (m.group(1).strip(), m.group(2).strip()) if m else ("", s_n)

                for tname in tables:
                    if tname.startswith("_") or tname.lower() in INTERNAL_TABLES or tname.lower().startswith("view_"):
                        continue
                    safe_t = tname.replace('"', '""')
                    try:
                        cols = [str(d[0]) for d in con.execute(f'DESCRIBE "{safe_t}"').fetchall()]
                        rows = con.execute(f'SELECT * FROM "{safe_t}" LIMIT 10000').fetchall()
                    except Exception:
                        continue
                    if not rows or not cols:
                        continue
                    fn, sh = cat_map.get(tname, (tname, ""))
                    cols, rows, banner_ctx = promote_banner_headers(cols, rows)
                    if not cols or not rows:
                        continue
                    norm_cols = [normalize_fa(c).lower() for c in cols]
                    preloaded_db.append((tname, fn, sh, cols, rows, banner_ctx, norm_cols))

                    if _is_matrix_tbl(norm_cols):
                        wg_raw = re.sub(r"^(?:کارگروه\s+)+", "کارگروه ", normalize_fa(sh)).strip()
                        for ci_m, nc_m in enumerate(norm_cols):
                            if ci_m < 6:
                                continue
                            if any(sk in nc_m for sk in ("ردیف", "نام", "موبایل", "تعداد", "مجموع", "شرح", "جزئیات", "کارگروه")):
                                continue
                            c_ck = canon_key(cols[ci_m])
                            if c_ck:
                                course_wg_map[c_ck] = wg_raw
                    elif not _is_summary_tbl(norm_cols, sh):
                        has_p = any(any(k in nc for k in _PERSON_KWS) for nc in norm_cols) or (
                            any(nc in ("نام", "first name", "name") for nc in norm_cols)
                            and any("نام خانوادگی" in nc or "فامیل" in nc for nc in norm_cols)
                        )
                        has_id = any(any(k in nc for k in _PHONE_KWS + _ID_DOC_KWS) for nc in norm_cols)
                        if has_p and has_id:
                            has_raw_rosters = True
                            _, sh_clean = _split_sheet_num(sh)
                            if sh_clean:
                                roster_clean_counts[canon_key(sh_clean)] += 1

                for tname, fn, sh, cols, rows, banner_ctx, norm_cols in preloaded_db:
                    if _is_summary_tbl(norm_cols, sh):
                        continue

                    if _is_matrix_tbl(norm_cols):
                        if has_raw_rosters:
                            continue
                        wg_lbl = re.sub(r"^(?:کارگروه\s+)+", "کارگروه ", normalize_fa(sh)).strip()
                        ci_nm_m = next((i for i, nc in enumerate(norm_cols) if any(k in nc for k in _PERSON_KWS)), 1)
                        ci_ph_m = next((i for i, nc in enumerate(norm_cols) if any(k in nc for k in _PHONE_KWS)), 2)
                        ci_id_m = next((i for i, nc in enumerate(norm_cols) if any(k in nc for k in _ID_DOC_KWS)), -1)
                        course_col_idxs = [
                            i for i in range(6, len(cols))
                            if not any(sk in norm_cols[i] for sk in ("شرح", "مجموع", "تعداد", "کارگروه"))
                        ]
                        col_max_s = {}
                        for ci_c in course_col_idxs:
                            mv = 0
                            for r in rows:
                                if ci_c < len(r):
                                    v = parse_number_strict(r[ci_c])
                                    if v is not None and v > mv:
                                        mv = int(round(v))
                            col_max_s[ci_c] = mv
                        for r_idx, r in enumerate(rows, start=1):
                            if is_blank_numbered_row(list(r)) or is_summary_row_smart(list(r)):
                                continue
                            nm = clean_participant_name(r[ci_nm_m] if ci_nm_m < len(r) else "")
                            if is_junk_label(nm) or len(nm) < 3:
                                continue
                            ph_v = normalize_phone(r[ci_ph_m] if ci_ph_m < len(r) else "")
                            nid_v = normalize_nid(r[ci_id_m] if (ci_id_m != -1 and ci_id_m < len(r)) else "")
                            for ci_c in course_col_idxs:
                                if ci_c >= len(r):
                                    continue
                                v = parse_number_strict(r[ci_c])
                                if v is None:
                                    continue
                                att_v = max(0, int(round(v)))
                                tot_v = col_max_s.get(ci_c, 0)
                                persons.append({
                                    "name": nm, "phone": ph_v, "nid": nid_v, "level": "",
                                    "course": normalize_fa(cols[ci_c]), "group": wg_lbl,
                                    "teacher": "نامشخص", "date": "", "year": "نامشخص",
                                    "month_idx": -1, "season": "", "source": tname,
                                    "file_name": fn, "source_sheet": sh, "row_index": r_idx,
                                    "sessions_total": tot_v, "sessions_attended": att_v,
                                    "sessions_late": 0, "sessions_excused": 0,
                                    "sessions_absent": max(0, tot_v - att_v), "session_marks": [],
                                })
                        continue

                    def find_col(keywords: tuple[str, ...]) -> int:
                        for idx, nc in enumerate(norm_cols):
                            if is_banner_header_col(cols[idx]):
                                continue
                            if any(kw in nc for kw in keywords):
                                return idx
                        return -1

                    i_first_name = next((idx for idx, nc in enumerate(norm_cols) if nc in ("نام", "first name", "name") and not is_banner_header_col(cols[idx])), -1)
                    i_last_name = next((idx for idx, nc in enumerate(norm_cols) if ("نام خانوادگی" in nc or "فامیل" in nc or nc == "last name") and not is_banner_header_col(cols[idx])), -1)
                    i_person = find_col(_PERSON_KWS)
                    i_phone = find_col(_PHONE_KWS)
                    i_nid = find_col(_ID_DOC_KWS)
                    i_level = find_col(("سطح", "پایه", "مقطع", "تحصیلات", "level"))
                    i_course = find_col(("عنوان دوره", "نام دوره", "موضوع", "عنوان برنامه", "رویداد", "دوره", "نشست", "course", "title"))
                    i_group = find_col(("کارگروه", "گروه موضوعی", "گروه علمی", "بخش", "حوزه موضوعی", "واحد", "group", "department"))
                    i_teacher = find_col(("استاد", "ارائه دهنده", "ارائه‌دهنده", "سخنران", "مدرس", "teacher", "speaker"))
                    i_count = find_col(("دانش پژوه", "دانش‌پژوه", "مخاطب", "تعداد نفر", "حاضرین", "نفر", "ثبت نام", "attendance", "students"))
                    if i_count == -1 and i_person == -1:
                        i_count = find_col(("شرکت", "count"))
                    i_hours = find_col(("ساعت", "ساعات", "مدت", "hours", "duration"))
                    i_sessions = find_col(("تعداد جلسات", "جلسات", "جلسه", "sessions"))
                    i_cost = -1
                    _COST_DESC_EXCL = ("شرح", "نوع", "عنوان", "بابت", "سرفصل", "دسته", "گروه", "شماره", "ردیف", "تاریخ", "کد", "موبایل", "تلفن", "مانده", "واحد", "فی")
                    _COST_HINTS_PRIO = (
                        "مبلغ کل", "جمع کل", "مبلغ هزینه", "مبلغ پرداختی", "بدهکار", "برداشت",
                        "مبلغ", "تومان", "ریال", "بستانکار", "تنخواه", "پرداختی", "حق التدریس",
                        "حق‌التدریس", "هزینه", "cost", "amount", "price",
                    )
                    for _ch in _COST_HINTS_PRIO:
                        for _ci_k, _nc_k in enumerate(norm_cols):
                            if is_banner_header_col(cols[_ci_k]) or len(_nc_k.split()) > 3:
                                continue
                            if any(ex_w in _nc_k for ex_w in _COST_DESC_EXCL):
                                continue
                            if _ch in _nc_k:
                                i_cost = _ci_k
                                break
                        if i_cost != -1:
                            break
                    if i_cost == -1:
                        for _ci_k, _nc_k in enumerate(norm_cols):
                            if _nc_k in ("برداشت", "پرداخت", "خرج", "بها"):
                                i_cost = _ci_k
                                break
                    i_date = find_col(("تاریخ", "سال", "فصل", "ماه", "زمان", "date", "year"))
                    i_cost_cat = find_col(("شرح", "بابت", "سرفصل", "نوع هزینه", "عنوان", "موضوع"))

                    if (i_person != -1 or (i_first_name != -1 and i_last_name != -1)) and (i_phone != -1 or i_nid != -1 or i_level != -1):
                        roster_course, roster_teacher = extract_roster_banner_meta(banner_ctx, fn, sh)
                        sh_num, sh_clean = _split_sheet_num(sh)
                        base_course = roster_course or sh_clean or Path(fn).stem or "دوره آموزشی"
                        base_ck = canon_key(sh_clean or base_course)
                        if sh_num and roster_clean_counts.get(base_ck, 0) > 1:
                            resolved_sheet_course = f"{base_course} (دوره {sh_num})"
                        else:
                            resolved_sheet_course = base_course
                        mapped_wg = course_wg_map.get(base_ck) or course_wg_map.get(canon_key(base_course)) or ""

                        reserved_cols = {
                            c_i for c_i in (i_person, i_first_name, i_last_name, i_phone, i_nid, i_level, i_course, i_group, i_teacher, i_date, i_cost, i_count, i_hours, i_sessions)
                            if c_i != -1
                        }
                        if norm_cols and any(k in norm_cols[0] for k in ("ردیف", "شماره", "no", "id")):
                            reserved_cols.add(0)
                        session_cols = _detect_session_columns(cols, reserved_cols)

                        numeric_course_max_sess = 0
                        if not session_cols and i_sessions != -1:
                            _pos_sess_vals: list[int] = []
                            for r_s in rows:
                                if i_sessions < len(r_s):
                                    sv_s = parse_number_strict(r_s[i_sessions])
                                    if sv_s is not None and 0 < sv_s <= 120:
                                        _pos_sess_vals.append(int(round(sv_s)))
                            if _pos_sess_vals:
                                _mx_s = max(_pos_sess_vals)
                                numeric_course_max_sess = _mx_s
                                # Guard against single-row typo outlier (e.g. 42 rows = 1 session, 1 typo row = 2)
                                if len(_pos_sess_vals) >= 10 and _pos_sess_vals.count(_mx_s) == 1:
                                    _below_mx = [v for v in _pos_sess_vals if v < _mx_s]
                                    if _below_mx:
                                        _sec_mx = max(_below_mx)
                                        if _below_mx.count(_sec_mx) >= len(_pos_sess_vals) * 0.5:
                                            numeric_course_max_sess = _sec_mx

                        sheet_seen_person: dict[tuple[str, str], int] = {}
                        for r_idx, r in enumerate(rows, start=1):
                            if is_blank_numbered_row(list(r)):
                                continue
                            if is_summary_row_smart(list(r)):
                                continue
                            if i_first_name != -1 and i_last_name != -1 and i_first_name != i_last_name:
                                fn_p = normalize_fa(r[i_first_name] if i_first_name < len(r) else "")
                                ln_p = normalize_fa(r[i_last_name] if i_last_name < len(r) else "")
                                nm = clean_participant_name(f"{fn_p} {ln_p}")
                            else:
                                nm = clean_participant_name(r[i_person] if (i_person != -1 and i_person < len(r)) else "")
                            if is_junk_label(nm) or len(nm) < 3:
                                continue
                            dt_raw = normalize_fa(r[i_date]) if (i_date != -1 and i_date < len(r)) else ""
                            jd = parse_jalali_date(dt_raw, fallback_text=f"{fn} {sh} {banner_ctx}")
                            t_cell = normalize_fa(r[i_teacher]) if (i_teacher != -1 and i_teacher < len(r)) else ""
                            if not is_valid_teacher_name(t_cell):
                                t_cell = roster_teacher

                            sess_marks = []
                            s_tot = s_att = s_late = s_exc = s_abs = 0
                            if session_cols:
                                s_tot = len(session_cols)
                                for sc_idx, sc_lbl in session_cols:
                                    raw_v = r[sc_idx] if sc_idx < len(r) else ""
                                    st_kind, st_lbl = _classify_session_cell(raw_v)
                                    sess_marks.append({"label": sc_lbl, "status": st_kind, "raw": st_lbl})
                                    if st_kind == "present":
                                        s_att += 1
                                    elif st_kind == "late":
                                        s_att += 1
                                        s_late += 1
                                    elif st_kind == "excused":
                                        s_exc += 1
                                    else:
                                        s_abs += 1
                            elif i_sessions != -1 and i_sessions < len(r):
                                sv_num = parse_number_strict(r[i_sessions])
                                if sv_num is not None and sv_num >= 0:
                                    s_att = int(round(sv_num))
                                    s_tot = max(numeric_course_max_sess, s_att)
                                    s_abs = max(0, s_tot - s_att)

                            ph_norm = normalize_phone(r[i_phone]) if (i_phone != -1 and i_phone < len(r)) else ""
                            nid_norm = normalize_nid(r[i_nid]) if (i_nid != -1 and i_nid < len(r)) else ""
                            c_row_title = normalize_fa(r[i_course]) if (i_course != -1 and i_course < len(r)) else resolved_sheet_course
                            g_row = (
                                normalize_fa(r[i_group])
                                if (i_group != -1 and i_group < len(r))
                                else (mapped_wg or detect_workgroup_unified(fn, sh, "", base_course, banner_ctx))
                            )

                            dup_k = (canon_key(nm), ph_norm or nid_norm)
                            if dup_k[1] and dup_k in sheet_seen_person:
                                prev_i = sheet_seen_person[dup_k]
                                if s_att > persons[prev_i]["sessions_attended"]:
                                    persons[prev_i]["sessions_attended"] = s_att
                                    persons[prev_i]["sessions_total"] = max(persons[prev_i]["sessions_total"], s_tot)
                                    persons[prev_i]["sessions_absent"] = max(0, persons[prev_i]["sessions_total"] - s_att)
                                continue

                            sheet_seen_person[dup_k] = len(persons)
                            persons.append({
                                "name": nm, "phone": ph_norm,
                                "nid": nid_norm,
                                "level": normalize_fa(r[i_level]) if (i_level != -1 and i_level < len(r)) else "",
                                "course": c_row_title,
                                "group": g_row,
                                "teacher": t_cell,
                                "date": jd["canonical"] or dt_raw, "year": jd["year"] or "نامشخص",
                                "month_idx": (jd["month"] - 1) if 1 <= jd["month"] <= 12 else -1,
                                "season": jd["season"], "source": tname, "file_name": fn, "source_sheet": sh, "row_index": r_idx,
                                "sessions_total": s_tot,
                                "sessions_attended": s_att,
                                "sessions_late": s_late,
                                "sessions_excused": s_exc,
                                "sessions_absent": s_abs,
                                "session_marks": sess_marks,
                            })
                        continue

                    if i_cost != -1 and i_count == -1 and i_course == -1:
                        # اگر هر دو ستون بدهکار و بستانکار وجود داشت، ستون هزینه واقعی را انتخاب کن
                        eff_cost_idx = i_cost
                        c_cur = norm_cols[i_cost]
                        pair_idx = -1
                        for ci_p, nc_p in enumerate(norm_cols):
                            if ci_p == i_cost or is_banner_header_col(cols[ci_p]):
                                continue
                            if (("بدهکار" in c_cur and "بستانکار" in nc_p) or ("بستانکار" in c_cur and "بدهکار" in nc_p)
                                or ("برداشت" in c_cur and "واریز" in nc_p) or ("واریز" in c_cur and "برداشت" in nc_p)):
                                pair_idx = ci_p
                                break
                        if pair_idx != -1:
                            if ("واریز" in c_cur or "دریافت" in c_cur) and ("برداشت" in norm_cols[pair_idx] or "پرداخت" in norm_cols[pair_idx]):
                                eff_cost_idx = pair_idx
                            elif not (("برداشت" in c_cur or "پرداخت" in c_cur) and ("واریز" in norm_cols[pair_idx] or "دریافت" in norm_cols[pair_idx])):
                                s1, s2 = 0, 0
                                for r_chk in rows:
                                    if is_summary_row_smart(list(r_chk)):
                                        continue
                                    it_chk = normalize_fa(r_chk[i_cost_cat]) if (i_cost_cat != -1 and i_cost_cat < len(r_chk)) else ""
                                    is_non_exp = bool(classify_non_expense_row(it_chk))
                                    v1 = parse_number_strict(r_chk[i_cost] if i_cost < len(r_chk) else None)
                                    v2 = parse_number_strict(r_chk[pair_idx] if pair_idx < len(r_chk) else None)
                                    if v1 is not None and v1 > 0:
                                        s1 += (-2 if is_non_exp else 1)
                                    if v2 is not None and v2 > 0:
                                        s2 += (-2 if is_non_exp else 1)
                                if s2 > s1:
                                    eff_cost_idx = pair_idx

                        unit_probe_txt = normalize_fa(f"{' '.join(cols)} {banner_ctx} {fn} {sh}")
                        row_unit_hint = "ریال" if "ریال" in unit_probe_txt else ("تومان" if "تومان" in unit_probe_txt else "")
                        for r_idx, r in enumerate(rows, start=1):
                            if is_summary_row_smart(list(r)) or is_blank_numbered_row(list(r)):
                                continue
                            raw_desc = normalize_fa(r[i_cost_cat]) if (i_cost_cat != -1 and i_cost_cat < len(r)) else ""
                            if raw_desc in ("جمع", "جمع کل", "مجموع", "مجموع کل", "جمع نهایی") or classify_non_expense_row(raw_desc) or raw_desc.startswith("امضا"):
                                continue
                            amt_opt = parse_number_strict(r[eff_cost_idx] if eff_cost_idx < len(r) else None)
                            if amt_opt is None or amt_opt <= 0:
                                continue
                            try:
                                from src.analytics.bi_engine import categorize_expense_smart
                                cat = categorize_expense_smart("", raw_desc, "", fn, sh, learned_rules=learned_fin_rules)["category"]
                            except Exception:
                                cat = raw_desc or "سایر هزینه‌ها"
                            if is_junk_label(cat):
                                cat = "سایر هزینه‌ها"
                            grp_val = normalize_fa(r[i_group]) if (i_group != -1 and i_group < len(r)) else "عمومی"
                            if is_junk_label(grp_val):
                                grp_val = "عمومی"
                            dt_raw = normalize_fa(r[i_date]) if (i_date != -1 and i_date < len(r)) else ""
                            jd = parse_jalali_date(dt_raw, fallback_text=f"{fn} {sh} {banner_ctx}")
                            costs.append({
                                "category": cat, "group": grp_val,
                                "teacher": normalize_fa(r[i_teacher]) if (i_teacher != -1 and i_teacher < len(r)) else "",
                                "amount": float(amt_opt), "date": jd["canonical"] or dt_raw, "year": jd["year"] or "",
                                "source": tname, "file_name": fn, "source_sheet": sh, "row_index": r_idx, "unit_hint": row_unit_hint,
                            })
                        continue

                    if i_course != -1 or i_teacher != -1 or i_group != -1:
                        base_loc = normalize_fa(str(sh or "").split("(")[0])
                        slide_txt = slide_texts.get((fn, base_loc), "")
                        if not slide_txt and base_loc:
                            for (s_fn, s_loc), s_txt in slide_texts.items():
                                if s_fn == fn and base_loc in s_loc:
                                    slide_txt = s_txt
                                    break
                        sample_course_str = " ".join(
                            normalize_fa(rr[i_course]) for rr in rows[:6]
                            if i_course != -1 and i_course < len(rr) and rr[i_course]
                        )
                        table_wg_inferred = detect_workgroup_unified(fn, sh, slide_txt, sample_course_str, banner_ctx)
                        for r_idx, r in enumerate(rows, start=1):
                            if data_mode == "clean" and is_summary_row_smart(list(r)):
                                continue
                            c_title = normalize_fa(r[i_course]) if i_course != -1 else ""
                            t_name = normalize_fa(r[i_teacher]) if i_teacher != -1 else ""
                            g_name = normalize_fa(r[i_group]) if i_group != -1 else ""
                            att_opt = parse_number_strict(r[i_count]) if i_count != -1 else None
                            hrs_opt = parse_number_strict(r[i_hours]) if i_hours != -1 else None
                            ses_opt = parse_number_strict(r[i_sessions]) if i_sessions != -1 else None
                            cst_opt = parse_number_strict(r[i_cost]) if i_cost != -1 else None
                            dt_raw = normalize_fa(r[i_date]) if i_date != -1 else ""
                            jd = parse_jalali_date(dt_raw, fallback_text=f"{fn} {sh} {banner_ctx}")

                            if is_junk_label(c_title):
                                c_title = ""
                            if is_junk_label(t_name) or not is_valid_teacher_name(t_name):
                                t_name = ""
                            if is_junk_label(g_name):
                                g_name = ""

                            if not g_name:
                                if table_wg_inferred and table_wg_inferred != "دوره‌های عمومی":
                                    g_name = table_wg_inferred
                                else:
                                    g_name = detect_workgroup_unified(fn, sh, slide_txt, f"{c_title} {t_name}", banner_ctx)
                            if not (c_title or t_name):
                                continue

                            cst = float(cst_opt) if (cst_opt is not None and cst_opt > 0) else 0.0
                            courses.append({
                                "course_uid": f"{tname}#{r_idx}", "title": c_title or f"برنامه {t_name}",
                                "group": g_name, "teacher": t_name or "نامشخص",
                                "attendance": int(round(att_opt)) if att_opt is not None else 0,
                                "attendance_valid": att_opt is not None,
                                "hours": round(float(hrs_opt), 2) if (hrs_opt is not None and hrs_opt >= 0) else 0.0,
                                "sessions": int(round(ses_opt)) if (ses_opt is not None and ses_opt >= 0) else 0,
                                "cost": cst, "date": jd["canonical"] or dt_raw, "year": jd["year"] or "نامشخص",
                                "month_idx": (jd["month"] - 1) if 1 <= jd["month"] <= 12 else -1,
                                "season": jd["season"], "source": tname, "file_name": fn, "source_sheet": sh, "row_index": r_idx,
                            })
                            if cst > 0:
                                costs.append({
                                    "category": c_title or g_name, "group": g_name, "teacher": t_name,
                                    "amount": cst, "date": jd["canonical"] or dt_raw, "year": jd["year"] or "",
                                    "source": tname, "file_name": fn, "source_sheet": sh, "row_index": r_idx,
                                })
        except Exception:
            pass

        if data_mode == "clean" and courses:
            seen: dict[tuple[str, str, str], dict[str, Any]] = {}
            for c in courses:
                k_t, k_tch, k_yr = canon_key(c.get("title")), canon_key(c.get("teacher")), str(c.get("year") or "")
                key = (k_t, k_tch, k_yr) if k_t else (c["course_uid"], "", "")
                if key not in seen:
                    seen[key] = dict(c)
                else:
                    cur = seen[key]
                    if c.get("attendance_valid") and (not cur.get("attendance_valid") or c["attendance"] > cur["attendance"]):
                        cur["attendance"], cur["attendance_valid"] = c["attendance"], True
                    if c.get("hours", 0) > cur.get("hours", 0):
                        cur["hours"] = c["hours"]
                    if c.get("sessions", 0) > cur.get("sessions", 0):
                        cur["sessions"] = c["sessions"]
            courses = list(seen.values())

        return courses, persons, costs

    def _resolve_alias(self, name: str, merges: dict[str, str]) -> str:
        n = normalize_fa(name)
        ck = canon_key(n)
        for _ in range(5):
            if ck in merges:
                n = normalize_fa(merges[ck])
                ck = canon_key(n)
            else:
                break
        return n

    def get_executive_analytics(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        flt = filters or {}
        f_group = normalize_fa(flt.get("group") or "")
        f_teacher = normalize_fa(flt.get("teacher") or "")
        f_year = str(flt.get("year") or "").translate(LATIN_DIGITS).strip()

        brain_cfg = load_brain_config()
        data_mode = str(flt.get("data_mode") or brain_cfg.get("data_mode") or "clean")
        if data_mode not in ("clean", "raw"):
            data_mode = "clean"
        hours_policy = str(flt.get("hours_policy") or brain_cfg.get("hours_policy") or "equal")
        if hours_policy not in ("equal", "full", "split"):
            hours_policy = "equal"

        teacher_alias_map = resolve_canonical_map("teacher") if data_mode == "clean" else {}
        wg_alias_map = resolve_canonical_map("workgroup") if data_mode == "clean" else {}
        hour_overrides: dict[str, dict[str, float]] = brain_cfg.get("course_hour_overrides") or {}

        suite = self._ensure_suite_file()
        merges: dict[str, str] = suite.get("merges") or {}
        teacher_meta: dict[str, dict[str, str]] = suite.get("teacher_meta") or {}

        db_courses, db_persons, db_costs = self._scan_duckdb(data_mode=data_mode)
        stored_regs = list(suite.get("registrations") or [])

        _WG_CANON_MAP = {
            "دینشناسی": "کارگروه دین شناسی",
            "کارگروهدینشناسی": "کارگروه دین شناسی",
            "تاریخ": "کارگروه تاریخ",
            "کارگروهتاریخ": "کارگروه تاریخ",
            "قران": "کارگروه قرآن",
            "کارگروهقران": "کارگروه قرآن",
            "فقه": "کارگروه فقه",
            "کارگروهفقه": "کارگروه فقه",
            "حدیث": "کارگروه حدیث",
            "کارگروهحدیث": "کارگروه حدیث",
            "کارگروهکارگروهحدیث": "کارگروه حدیث",
            "تربیتمبلغ": "تربیت سخنران و مبلغ",
            "تربیتسخنران": "تربیت سخنران و مبلغ",
            "تربیتسخنرانومبلغ": "تربیت سخنران و مبلغ",
            "کارگروهتربیتسخنرانومبلغ": "تربیت سخنران و مبلغ",
            "انسباالکافی": "حدیث‌خوانی (انس با الکافی)",
            "کارگروهانسباالکافی": "حدیث‌خوانی (انس با الکافی)",
            "حدیثخوانیانسباالکافی": "حدیث‌خوانی (انس با الکافی)",
        }

        def _canon_wg(g: str) -> str:
            gn = normalize_fa(g or "دوره‌های عمومی")
            ck = canon_key(gn)
            if ck in _WG_CANON_MAP:
                gn = _WG_CANON_MAP[ck]
            if data_mode == "clean":
                c = _clean_for_compare(gn, "workgroup", brain_cfg)
                if c in wg_alias_map:
                    return wg_alias_map[c]
            return gn

        def _resolve_course_teachers(raw_t: str) -> tuple[str, list[str]]:
            if not raw_t or raw_t == "نامشخص":
                return "گروهی", []
            if data_mode == "raw":
                return "انفرادی", [raw_t]
            mode, parts = split_joint_names(raw_t, "teacher", brain_cfg)
            if mode == "گروهی":
                return "گروهی", [raw_t]
            return mode, [teacher_alias_map.get(_clean_for_compare(pt, "teacher", brain_cfg), pt) for pt in parts]

        all_persons: list[dict[str, Any]] = []
        for p in db_persons + stored_regs:
            nm = self._resolve_alias(p.get("name") or "", merges)
            if not nm or is_junk_label(nm):
                continue
            grp = _canon_wg(p.get("group") or "دوره‌های عمومی")
            if is_junk_label(grp):
                grp = "دوره‌های عمومی"
            tch_raw = normalize_fa(p.get("teacher") or "نامشخص")
            _, tch_parts = _resolve_course_teachers(tch_raw)
            dt = normalize_fa(p.get("date") or "")
            jd = parse_jalali_date(dt, fallback_text=str(p.get("year") or ""))
            all_persons.append({
                "name": nm, "raw_name": normalize_fa(p.get("name") or nm),
                "phone": normalize_phone(p.get("phone") or ""),
                "nid": normalize_nid(p.get("nid") or ""), "level": normalize_fa(p.get("level") or ""),
                "course": normalize_fa(p.get("course") or "دوره آموزشی"), "group": grp,
                "teacher": tch_parts[0] if len(tch_parts) == 1 else tch_raw, "teachers_list": tch_parts,
                "date": jd["canonical"] or dt, "year": jd["year"] or extract_year(p.get("year") or "") or "نامشخص",
                "month_idx": (jd["month"] - 1) if 1 <= jd["month"] <= 12 else -1,
                "file_name": str(p.get("file_name") or "ورودی پرس‌لاین"),
                "sessions_total": int(p.get("sessions_total") or 0),
                "sessions_attended": int(p.get("sessions_attended") or 0),
                "sessions_late": int(p.get("sessions_late") or 0),
                "sessions_excused": int(p.get("sessions_excused") or 0),
                "sessions_absent": int(p.get("sessions_absent") or 0),
                "session_marks": list(p.get("session_marks") or []),
            })

        valid_p8_index: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
        _vp_names: dict[str, set[str]] = defaultdict(set)
        for p in all_persons:
            ph = p.get("phone") or ""
            if len(ph) == 11 and ph.startswith("09") and not ph.startswith("098"):
                nk = re.sub(r"^(?:سید|سیده|شیخ)", "", canon_key(p.get("name") or ""))
                if nk:
                    _vp_names[ph].add(nk)
        for ph, nks in _vp_names.items():
            valid_p8_index[ph[1:9]].append((ph, nks))

        _098_names: dict[str, set[str]] = defaultdict(set)
        for p in all_persons:
            ph = p.get("phone") or ""
            if len(ph) == 11 and ph.startswith("0989"):
                nk = re.sub(r"^(?:سید|سیده|شیخ)", "", canon_key(p.get("name") or ""))
                if nk:
                    _098_names[ph].add(nk)
        phone_098_fix: dict[str, str] = {}
        for ph098, nks098 in _098_names.items():
            cands = valid_p8_index.get(ph098[3:], [])
            for cand_ph, cand_nks in cands:
                if (nks098 & cand_nks) or any(a in b or b in a for a in nks098 for b in cand_nks if len(a) >= 4 and len(b) >= 4):
                    phone_098_fix[ph098] = cand_ph
                    break
        if phone_098_fix:
            for p in all_persons:
                if p.get("phone") in phone_098_fix:
                    p["phone"] = phone_098_fix[p["phone"]]

        reg_by_course: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in all_persons:
            reg_by_course[p["course"]].append(p)

        all_courses: list[dict[str, Any]] = []
        for c in db_courses:
            cc = dict(c)
            cc["group"] = _canon_wg(cc.get("group") or "دوره‌های عمومی")
            mode, t_list = _resolve_course_teachers(cc.get("teacher") or "")
            cc["holding_mode"], cc["teachers_resolved"] = mode, t_list
            all_courses.append(cc)

        roster_match_inputs = [
            {
                "id": c_title,
                "title": c_title,
                "group": plist[0]["group"] if plist else "",
                "attendance": len(plist),
            }
            for c_title, plist in reg_by_course.items()
        ]
        summary_match_inputs = [
            {
                "id": idx_c,
                "title": cc.get("title") or "",
                "group": cc.get("group") or "",
                "attendance": int(cc["attendance"]) if (cc.get("attendance_valid") and int(cc.get("attendance") or 0) > 0) else None,
            }
            for idx_c, cc in enumerate(all_courses)
        ]
        roster_to_summary = match_roster_to_summary_courses(roster_match_inputs, summary_match_inputs, min_score=0.62)
        source_discrepancies: list[dict[str, Any]] = []

        for c_title, plist in reg_by_course.items():
            max_roster_sess = max((int(x.get("sessions_total") or 0) for x in plist), default=0)
            if c_title in roster_to_summary:
                s_idx, match_sc = roster_to_summary[c_title]
                sc_obj = all_courses[s_idx]
                prev_sum_att = int(sc_obj.get("attendance") or 0) if sc_obj.get("attendance_valid") else 0
                if not sc_obj.get("attendance_valid") or prev_sum_att <= 0:
                    sc_obj["attendance"] = len(plist)
                    sc_obj["attendance_valid"] = True
                elif abs(prev_sum_att - len(plist)) >= 5:
                    source_discrepancies.append({
                        "course": sc_obj.get("title") or c_title,
                        "roster_title": c_title,
                        "group": sc_obj.get("group") or "",
                        "summary_count": prev_sum_att,
                        "roster_count": len(plist),
                        "diff": prev_sum_att - len(plist),
                        "confidence": round(match_sc * 100),
                    })
                if max_roster_sess > int(sc_obj.get("sessions") or 0):
                    sc_obj["sessions"] = max_roster_sess
                sc_obj["roster_attendance"] = len(plist)

                s_title = sc_obj.get("title") or c_title
                s_grp = sc_obj.get("group") or (plist[0]["group"] if plist else "دوره‌های عمومی")
                s_tch = sc_obj.get("teacher") or ""
                s_tlist = list(sc_obj.get("teachers_resolved") or [])
                s_dt = sc_obj.get("date") or ""
                s_yr = sc_obj.get("year") or "نامشخص"
                s_mi = sc_obj.get("month_idx", -1)
                for p_row in plist:
                    if len(s_title) >= len(p_row.get("course") or ""):
                        p_row["course"] = s_title
                    if s_grp and s_grp != "دوره‌های عمومی":
                        p_row["group"] = s_grp
                    if (not p_row.get("teacher") or p_row["teacher"] == "نامشخص") and s_tch and s_tch != "نامشخص":
                        p_row["teacher"] = s_tlist[0] if len(s_tlist) == 1 else s_tch
                        p_row["teachers_list"] = list(s_tlist)
                    if not p_row.get("date") and s_dt:
                        p_row["date"] = s_dt
                    if (not p_row.get("year") or p_row["year"] == "نامشخص") and s_yr and s_yr != "نامشخص":
                        p_row["year"] = s_yr
                    if p_row.get("month_idx", -1) < 0 <= s_mi:
                        p_row["month_idx"] = s_mi
            else:
                sample = plist[0]
                mode, t_list = _resolve_course_teachers(sample["teacher"])
                all_courses.append({
                    "course_uid": f"roster#{canon_key(c_title)}", "title": c_title,
                    "group": sample["group"], "teacher": sample["teacher"],
                    "holding_mode": mode, "teachers_resolved": t_list,
                    "attendance": len(plist), "attendance_valid": True,
                    "hours": 0.0, "sessions": max_roster_sess, "cost": 0.0,
                    "date": sample["date"], "year": sample["year"], "month_idx": sample["month_idx"],
                    "season": "", "source": sample.get("source") or "roster",
                    "file_name": sample.get("file_name") or "فهرست دوره‌ها", "source_sheet": "", "row_index": 0,
                })

        if data_mode == "clean":
            _tch_canon_disp: dict[str, str] = {}
            for _cc in all_courses:
                for _tn in (_cc.get("teachers_resolved") or []):
                    _core = canonical_teacher_core(_tn)
                    if not _core:
                        continue
                    _prev = _tch_canon_disp.get(_core)
                    if not _prev or (len(_tn) > len(_prev) and "ئ" not in _tn) or ("ئ" in _prev and "ئ" not in _tn):
                        _tch_canon_disp[_core] = _tn
            if _tch_canon_disp:
                for _cc in all_courses:
                    if _cc.get("holding_mode") != "گروهی" and _cc.get("teachers_resolved"):
                        _dedup_t: list[str] = []
                        _seen_tc: set[str] = set()
                        for _tn in _cc["teachers_resolved"]:
                            _core = canonical_teacher_core(_tn)
                            if _core and _core not in _seen_tc:
                                _seen_tc.add(_core)
                                _dedup_t.append(_tch_canon_disp.get(_core, _tn))
                        _cc["teachers_resolved"] = _dedup_t
                        if len(_dedup_t) == 1:
                            _cc["teacher"] = _dedup_t[0]
                        elif len(_dedup_t) > 1:
                            _cc["teacher"] = " و ".join(_dedup_t)
                for _pp in all_persons:
                    if _pp.get("teachers_list"):
                        _dedup_p: list[str] = []
                        _seen_pc: set[str] = set()
                        for _tn in _pp["teachers_list"]:
                            _core = canonical_teacher_core(_tn)
                            if _core and _core not in _seen_pc:
                                _seen_pc.add(_core)
                                _dedup_p.append(_tch_canon_disp.get(_core, _tn))
                        _pp["teachers_list"] = _dedup_p
                        if len(_dedup_p) == 1:
                            _pp["teacher"] = _dedup_p[0]
                        elif len(_dedup_p) > 1:
                            _pp["teacher"] = " و ".join(_dedup_p)

        meta_groups = sorted({c["group"] for c in all_courses if c["group"]} | {p["group"] for p in all_persons if p["group"]})
        meta_teachers = sorted({tn for c in all_courses if c.get("holding_mode") != "گروهی" for tn in (c.get("teachers_resolved") or []) if tn and tn != "نامشخص"})
        meta_years = sorted({c["year"] for c in all_courses if c["year"] and c["year"] != "نامشخص"})

        f_group_ck = canon_key(f_group) if f_group else ""
        f_teacher_ck = canon_key(f_teacher) if f_teacher else ""
        f_teacher_core = _clean_for_compare(f_teacher, "teacher", brain_cfg) if f_teacher else ""
        f_teacher_alias = teacher_alias_map.get(f_teacher_core, f_teacher) if f_teacher_core else f_teacher
        f_teacher_alias_ck = canon_key(f_teacher_alias) if f_teacher_alias else ""

        def _match_group(g_val: str) -> bool:
            if not f_group:
                return True
            gn = _canon_wg(g_val or "")
            return gn == f_group or canon_key(gn) == f_group_ck

        def _match_teacher(raw_t: str, resolved_list: list[str] | None = None) -> bool:
            if not f_teacher:
                return True
            cands = list(resolved_list or [])
            if raw_t:
                cands.append(raw_t)
                _, extra_parts = _resolve_course_teachers(raw_t)
                cands.extend(extra_parts)
            for cand in cands:
                cn = normalize_fa(cand or "")
                if not cn or cn == "نامشخص":
                    continue
                if cn == f_teacher or cn == f_teacher_alias:
                    return True
                ck = canon_key(cn)
                if ck and (ck == f_teacher_ck or (f_teacher_alias_ck and ck == f_teacher_alias_ck)):
                    return True
                ccore = _clean_for_compare(cn, "teacher", brain_cfg)
                if ccore and f_teacher_core and ccore == f_teacher_core:
                    return True
            return False

        courses = [c for c in all_courses if _match_group(c.get("group", "")) and _match_teacher(c.get("teacher", ""), c.get("teachers_resolved")) and (not f_year or c["year"] == f_year)]
        persons = [p for p in all_persons if _match_group(p.get("group", "")) and _match_teacher(p.get("teacher", ""), p.get("teachers_list")) and (not f_year or p["year"] == f_year)]
        costs = [x for x in db_costs if _match_group(x.get("group", "")) and _match_teacher(x.get("teacher", ""), None) and (not f_year or (x.get("year") or extract_year(x["date"])) == f_year)]

        person_alias_map = resolve_canonical_map("person") if data_mode == "clean" else {}
        participant_meta_store = dict(suite.get("participant_meta") or {})

        def _merge_entities(dst: dict[str, Any], src: dict[str, Any]) -> None:
            if not dst["phone"] and src["phone"]:
                dst["phone"] = src["phone"]
            if not dst["nid"] and src["nid"]:
                dst["nid"] = src["nid"]
            if not dst["level"] and src["level"]:
                dst["level"] = src["level"]
            if len(src["name"]) > len(dst["name"]) and " " in src["name"]:
                dst["name"] = src["name"]
            for v in src["name_variants"]:
                if v not in dst["name_variants"]:
                    dst["name_variants"].append(v)
            for c_ck, c_obj in src["course_map"].items():
                if c_ck not in dst["course_map"] or (c_obj["sessions_total"], c_obj["sessions_attended"]) > (dst["course_map"][c_ck]["sessions_total"], dst["course_map"][c_ck]["sessions_attended"]):
                    dst["course_map"][c_ck] = c_obj
            for g in src["groups"]:
                if g not in dst["groups"]:
                    dst["groups"].append(g)
            for t in src["teachers"]:
                if t not in dst["teachers"]:
                    dst["teachers"].append(t)
            for y in src["years"]:
                if y not in dst["years"]:
                    dst["years"].append(y)

        person_entities: dict[str, dict[str, Any]] = {}
        nid_to_id: dict[str, str] = {}
        phone_to_id: dict[str, str] = {}
        name_to_id: dict[str, str] = {}

        for p in persons:
            raw_nm = p.get("raw_name") or p["name"]
            nm_core = _clean_for_compare(p["name"], "person", brain_cfg)
            disp_nm = person_alias_map.get(nm_core, p["name"]) if nm_core else p["name"]
            nid, ph, ck = p.get("nid") or "", p["phone"], canon_key(disp_nm)

            def _compatible_entity(existing_pid: str | None, name_only: bool = False) -> bool:
                if not existing_pid or existing_pid not in person_entities:
                    return False
                e_cur = person_entities[existing_pid]
                if nid and e_cur["nid"] and nid != e_cur["nid"]:
                    return False
                if ph and e_cur["phone"] and ph != e_cur["phone"]:
                    return False
                # Never merge solely by name when both records carry strong IDs (e.g., phone vs passport) with no shared ID!
                if name_only and (ph or nid) and (e_cur["phone"] or e_cur["nid"]):
                    return False
                return True

            matched_pids = []
            cand_nid = nid_to_id.get(nid) if nid else None
            cand_ph = phone_to_id.get(ph) if ph else None
            if _compatible_entity(cand_nid):
                matched_pids.append(cand_nid)
            if _compatible_entity(cand_ph) and cand_ph not in matched_pids:
                matched_pids.append(cand_ph)
            if not matched_pids:
                cand_nm = name_to_id.get(ck) if ck else None
                if _compatible_entity(cand_nm, name_only=True):
                    matched_pids.append(cand_nm)

            if not matched_pids:
                pid = f"p_{len(person_entities) + 1}"
                person_entities[pid] = {
                    "id": pid, "name": disp_nm, "phone": ph, "nid": nid, "level": p["level"],
                    "name_variants": [raw_nm] if raw_nm else [],
                    "course_map": {}, "courses": [], "groups": [], "teachers": [], "years": [],
                }
            else:
                pid = matched_pids[0]
                for extra_pid in matched_pids[1:]:
                    if extra_pid in person_entities:
                        _merge_entities(person_entities[pid], person_entities[extra_pid])
                        for d_map in (nid_to_id, phone_to_id, name_to_id):
                            for k_m, v_m in list(d_map.items()):
                                if v_m == extra_pid:
                                    d_map[k_m] = pid
                        del person_entities[extra_pid]

            ent = person_entities[pid]
            if raw_nm and raw_nm not in ent["name_variants"]:
                ent["name_variants"].append(raw_nm)
            if len(disp_nm) > len(ent["name"]) and " " in disp_nm:
                ent["name"] = disp_nm
            if nid:
                nid_to_id[nid] = pid
                ent["nid"] = ent["nid"] or nid
            if ph:
                phone_to_id[ph] = pid
                ent["phone"] = ent["phone"] or ph
            if ck:
                name_to_id[ck] = pid
            ent["level"] = ent["level"] or p["level"]

            c_title = p["course"]
            _t_ck = canon_key(p.get("teacher") or "") if (p.get("teacher") and p.get("teacher") != "نامشخص") else ""
            c_ck = f"{canon_key(c_title)}|{_t_ck}" if _t_ck else canon_key(c_title)
            s_tot = int(p.get("sessions_total") or 0)
            s_att = int(p.get("sessions_attended") or 0)
            c_rec = {
                "course": c_title,
                "group": p["group"],
                "teacher": p["teacher"],
                "date": p["date"] or "",
                "year": p["year"] if p["year"] != "نامشخص" else "",
                "file_name": p.get("file_name") or "",
                "sessions_total": s_tot,
                "sessions_attended": s_att,
                "sessions_late": int(p.get("sessions_late") or 0),
                "sessions_excused": int(p.get("sessions_excused") or 0),
                "sessions_absent": int(p.get("sessions_absent") or 0),
                "attendance_rate": round((s_att / s_tot) * 100, 1) if s_tot > 0 else None,
                "session_marks": list(p.get("session_marks") or []),
            }
            if c_ck not in ent["course_map"] or (s_tot, s_att) > (ent["course_map"][c_ck]["sessions_total"], ent["course_map"][c_ck]["sessions_attended"]):
                ent["course_map"][c_ck] = c_rec
            if p["group"] and p["group"] not in ent["groups"]:
                ent["groups"].append(p["group"])
            for tn in (p.get("teachers_list") or ([p["teacher"]] if p["teacher"] and p["teacher"] != "نامشخص" else [])):
                if tn and tn != "نامشخص" and tn not in ent["teachers"] and not any(k in tn for k in ("جمعی از", "گروهی از", "تعدادی از", "اساتید مدعو", "پنل تخصصی", "میزگرد", "ناشناس")):
                    ent["teachers"].append(tn)
            if p["year"] and p["year"] != "نامشخص" and p["year"] not in ent["years"]:
                ent["years"].append(p["year"])

        participants_list, ret_buckets, repeat_users = [], Counter(), 0
        for ent in person_entities.values():
            c_details = list(ent["course_map"].values())
            c_details.sort(key=lambda x: (x.get("year") or "", x.get("date") or "", x.get("course") or ""), reverse=True)
            ent["course_details"] = c_details
            ent["courses"] = [c["course"] for c in c_details]
            del ent["course_map"]

            meta = (
                (participant_meta_store.get(f"ph:{ent['phone']}") if ent["phone"] else None)
                or (participant_meta_store.get(f"nid:{ent['nid']}") if ent["nid"] else None)
                or participant_meta_store.get(f"nm:{canon_key(ent['name'])}")
                or {}
            )
            if meta.get("phone"):
                ent["phone"] = normalize_phone(meta["phone"]) or ent["phone"]
            if meta.get("nid"):
                ent["nid"] = normalize_nid(meta["nid"]) or ent["nid"]
            if meta.get("level"):
                ent["level"] = normalize_fa(meta["level"])
            ent["notes"] = str(meta.get("notes") or "").strip()
            ent["tags"] = [str(t).strip() for t in (meta.get("tags") or []) if str(t).strip()]
            v_stat = str(meta.get("vetting_status") or "normal").strip().lower()
            if v_stat not in ("normal", "approved", "graylist", "blacklist"):
                v_stat = "normal"
            ent["vetting_status"] = v_stat
            ent["vetting_reason"] = str(meta.get("vetting_reason") or "").strip()
            ent["vetting_updated_at"] = str(meta.get("vetting_updated_at") or "").strip()
            ent["profile_key"] = f"ph:{ent['phone']}" if ent["phone"] else (f"nid:{ent['nid']}" if ent["nid"] else f"nm:{canon_key(ent['name'])}")

            cnt = len(ent["courses"])
            if cnt >= 2:
                repeat_users += 1
            if cnt <= 1:
                loyalty, b, l_rank = "جدیدالورود", "۱ دوره (جدیدالورود)", 1
            elif cnt == 2:
                loyalty, b, l_rank = "نیمه‌فعال", "۲ دوره (نیمه‌فعال)", 2
            elif cnt <= 4:
                loyalty, b, l_rank = "فعال", "۳ تا ۴ دوره (فعال)", 3
            elif cnt <= 7:
                loyalty, b, l_rank = "مستمر", "۵ تا ۷ دوره (مستمر)", 4
            else:
                loyalty, b, l_rank = "ثابت", "۸+ دوره (ثابت)", 5
            ret_buckets[b] += 1

            tot_s = sum(c["sessions_total"] for c in c_details)
            att_s = sum(c["sessions_attended"] for c in c_details)
            late_s = sum(c["sessions_late"] for c in c_details)
            exc_s = sum(c["sessions_excused"] for c in c_details)
            abs_s = sum(c["sessions_absent"] for c in c_details)
            att_rate = round((att_s / tot_s) * 100, 1) if tot_s > 0 else None

            c_score = min(50.0, cnt * 14.0)
            a_score = (att_rate * 0.38) if att_rate is not None else 18.0
            g_score = min(12.0, len(ent["groups"]) * 4.0)
            eng_score = int(round(min(100.0, c_score + a_score + g_score)))

            ent["courses_count"] = cnt
            ent["groups_count"] = len(ent["groups"])
            ent["teachers_count"] = len(ent["teachers"])
            ent["loyalty"] = loyalty
            ent["loyalty_rank"] = l_rank
            ent["total_sessions"] = tot_s
            ent["attended_sessions"] = att_s
            ent["late_sessions"] = late_s
            ent["excused_sessions"] = exc_s
            ent["absent_sessions"] = abs_s
            ent["attendance_rate"] = att_rate
            ent["engagement_score"] = eng_score
            zero_c_cnt = sum(1 for c in c_details if int(c.get("sessions_total") or 0) > 0 and int(c.get("sessions_attended") or 0) == 0)
            ent["zero_courses_count"] = zero_c_cnt
            # Refined smart auto-graylist hint: ONLY triggers when overall attendance is genuinely weak (never flags 70%+ active regulars!)
            auto_gray_reason = ""
            if ent["vetting_status"] == "normal":
                if tot_s >= 4 and att_rate is not None and att_rate < 40.0:
                    auto_gray_reason = f"غیبت بالا (نرخ حضور {round(att_rate)}٪ در {tot_s} جلسه)"
                elif zero_c_cnt >= 2 and (att_rate is None or att_rate < 55.0):
                    auto_gray_reason = f"{zero_c_cnt} دوره ثبت‌نام بدون حضور (نرخ حضور کل {round(att_rate) if att_rate is not None else 0}٪)"
            ent["auto_graylist_reason"] = auto_gray_reason
            id_t, id_clean = classify_identity_doc(ent.get("nid") or "")
            ent["nid"] = id_clean or ent.get("nid") or ""
            ent["id_type"] = id_t
            ent["last_year"] = sorted(ent["years"])[-1] if ent["years"] else ""
            ent["merged_variants"] = [v for v in ent["name_variants"] if v != ent["name"]]
            participants_list.append(ent)

        participants_list.sort(key=lambda x: (-x["courses_count"], -(x["attendance_rate"] if x["attendance_rate"] is not None else -1), x["name"]))

        total_courses = len(courses)
        joint_courses_total = sum(1 for c in courses if c.get("holding_mode") == "مشترک")
        collective_courses_total = sum(1 for c in courses if c.get("holding_mode") == "گروهی")
        valid_att_values = [float(c["attendance"]) for c in courses if c.get("attendance_valid")]
        missing_att_courses = sum(1 for c in courses if not c.get("attendance_valid"))
        total_attendance = int(round(sum(valid_att_values))) or len(persons)
        total_hours = round(sum(float(c.get("hours") or 0.0) for c in courses), 2)
        total_sessions = sum(int(c.get("sessions") or 0) for c in courses)

        has_person_level = len(person_entities) > 0
        unique_participants = len(person_entities) if has_person_level else 0
        repeat_rate = round((repeat_users / len(person_entities)) * 100, 1) if person_entities else 0.0
        avg_per_course = round(sum(valid_att_values) / len(valid_att_values), 1) if valid_att_values else 0.0
        median_per_course = _compute_median(valid_att_values)

        total_cost = round(sum(x["amount"] for x in costs))
        cost_per_attendee = round(total_cost / total_attendance) if total_attendance and total_cost else 0
        cost_per_unique = round(total_cost / unique_participants) if unique_participants and total_cost else 0
        unit_hints = [x.get("unit_hint") for x in costs if x.get("unit_hint")]
        if unit_hints:
            cost_unit = Counter(unit_hints).most_common(1)[0][0]
        else:
            med_c = _compute_median([x["amount"] for x in costs]) if costs else 0.0
            cost_unit = "ریال" if med_c >= 500000 else "تومان"

        parsed_dates = sum(1 for c in courses if c.get("year") and c["year"] != "نامشخص")
        att_cov = (len(valid_att_values) / total_courses) if total_courses else 1.0
        date_cov = (parsed_dates / total_courses) if total_courses else 1.0
        dup_files = detect_duplicate_files()
        data_confidence_pct = max(25, min(100, round((att_cov * 55 + date_cov * 25 + 20) - min(20.0, len(dup_files) * 7.0))))

        grp_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"courses": 0, "attendance": 0, "att_vals": [], "hours": 0.0, "sessions": 0, "unique_ids": set(), "repeat_ids": set(), "cost": 0.0})
        for c in courses:
            g = grp_stats[c["group"]]
            g["courses"] += 1
            if c.get("attendance_valid"):
                g["attendance"] += c["attendance"]
                g["att_vals"].append(float(c["attendance"]))
            g["hours"] += float(c.get("hours") or 0.0)
            g["sessions"] += int(c.get("sessions") or 0)
        for ent in person_entities.values():
            for gname in ent["groups"]:
                grp_stats[gname]["unique_ids"].add(ent["id"])
                if ent["courses_count"] >= 2:
                    grp_stats[gname]["repeat_ids"].add(ent["id"])
        for x in costs:
            cg = _canon_wg(x["group"])
            if cg and cg not in ("عمومی", "دوره‌های عمومی") and cg in grp_stats:
                grp_stats[cg]["cost"] += x["amount"]

        groups_out = []
        for gname, st in grp_stats.items():
            uniq = len(st["unique_ids"]) if st["unique_ids"] else 0
            rep = round((len(st["repeat_ids"]) / len(st["unique_ids"])) * 100, 1) if st["unique_ids"] else 0.0
            groups_out.append({
                "name": gname, "courses": st["courses"], "attendance": st["attendance"],
                "unique": uniq, "unique_verified": bool(st["unique_ids"]),
                "avg_attendance": round(sum(st["att_vals"]) / len(st["att_vals"]), 1) if st["att_vals"] else 0.0,
                "median_attendance": _compute_median(st["att_vals"]),
                "hours": round(st["hours"], 2), "sessions": st["sessions"],
                "repeat_rate": rep, "cost": round(st["cost"]),
                "cost_per_attendee": round(st["cost"] / st["attendance"]) if st["attendance"] and st["cost"] else 0,
            })
        groups_out.sort(key=lambda x: (-x["attendance"], -x["courses"]))

        aff_labels = [g["name"] for g in groups_out[:8]]
        aff_matrix = [[0 for _ in aff_labels] for _ in aff_labels]
        aff_active_matrix = [[0 for _ in aff_labels] for _ in aff_labels]
        cross_group_people = 0
        for ent in person_entities.values():
            if len(ent["groups"]) >= 2:
                cross_group_people += 1
            egs = set(g for g in ent["groups"] if g in aff_labels)
            act_egs = {
                c.get("group") for c in (ent.get("course_details") or [])
                if c.get("group") in aff_labels and int(c.get("sessions_attended") or 0) > 0
            }
            for i_a, ga in enumerate(aff_labels):
                if ga in egs:
                    for i_b, gb in enumerate(aff_labels):
                        if gb in egs:
                            aff_matrix[i_a][i_b] += 1
                if ga in act_egs:
                    for i_b, gb in enumerate(aff_labels):
                        if gb in act_egs:
                            aff_active_matrix[i_a][i_b] += 1

        tch_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"courses": 0, "independent_courses": 0, "joint_courses": 0, "attendance": 0, "adjusted_attendance": 0.0, "att_vals": [], "sessions": 0, "hours_independent": 0.0, "hours_joint": 0.0, "hours_effective": 0.0, "unique_ids": set(), "repeat_ids": set(), "groups": set(), "cost": 0.0, "source_refs": []})
        for c in courses:
            mode, t_list = c.get("holding_mode", "انفرادی"), c.get("teachers_resolved") or []
            if mode == "گروهی" or not t_list:
                continue
            nt, chrs = max(1, len(t_list)), float(c.get("hours") or 0.0)
            manual_map = hour_overrides.get(c["course_uid"]) or hour_overrides.get(normalize_fa(c["title"])) or {}
            for tname in t_list:
                if not tname or tname == "نامشخص":
                    continue
                tn_low = normalize_fa(tname).lower()
                if any(ckw in tn_low for ckw in ("گروهی از", "جمعی از", "تعدادی از", "اساتید مدعو", "پنل تخصصی", "میزگرد", "کارگاه گروهی", "ناشناس")):
                    continue
                if f_teacher and not _match_teacher(tname, [tname]):
                    continue
                ts = tch_stats[tname]
                ts["courses"] += 1
                ts["independent_courses" if (mode == "انفرادی" or nt == 1) else "joint_courses"] += 1
                if c.get("attendance_valid"):
                    ts["attendance"] += c["attendance"]
                    ts["adjusted_attendance"] += c["attendance"] / nt
                    ts["att_vals"].append(float(c["attendance"]))
                ts["sessions"] += int(c.get("sessions") or 0)
                ts["groups"].add(c["group"])
                ts["cost"] += c["cost"] / nt

                tn_norm, tn_core = normalize_fa(tname), _clean_for_compare(tname, "teacher", brain_cfg)
                m_hrs = next((float(mv) for mk, mv in manual_map.items() if normalize_fa(mk) == tn_norm or _clean_for_compare(mk, "teacher", brain_cfg) == tn_core), None)
                if mode == "انفرادی" or nt == 1:
                    eff = m_hrs if m_hrs is not None else chrs
                    ts["hours_independent"] += eff
                    ts["hours_effective"] += eff
                else:
                    eff = m_hrs if m_hrs is not None else (chrs if hours_policy == "full" else chrs / nt)
                    ts["hours_joint"] += (m_hrs if m_hrs is not None else (chrs if hours_policy in ("full", "split") else chrs / nt))
                    ts["hours_effective"] += eff
                if len(ts["source_refs"]) < 30:
                    ts["source_refs"].append({"course": c["title"], "mode": mode, "file_name": c.get("file_name", ""), "source_sheet": c.get("source_sheet", ""), "row_index": c.get("row_index", 0)})

        for ent in person_entities.values():
            for tname in ent["teachers"]:
                if tname in tch_stats:
                    tch_stats[tname]["unique_ids"].add(ent["id"])
                    if ent["courses_count"] >= 2:
                        tch_stats[tname]["repeat_ids"].add(ent["id"])

        teachers_out = []
        for tname, ts in tch_stats.items():
            meta = teacher_meta.get(canon_key(tname)) or {}
            teachers_out.append({
                "name": tname, "courses": ts["courses"],
                "independent_courses": ts["independent_courses"], "joint_courses": ts["joint_courses"],
                "attendance": ts["attendance"], "adjusted_attendance": round(ts["adjusted_attendance"], 1),
                "unique": len(ts["unique_ids"]), "unique_verified": bool(ts["unique_ids"]),
                "avg_attendance": round(sum(ts["att_vals"]) / len(ts["att_vals"]), 1) if ts["att_vals"] else 0.0,
                "median_attendance": _compute_median(ts["att_vals"]), "sessions": ts["sessions"],
                "hours_independent": round(ts["hours_independent"], 2), "hours_joint": round(ts["hours_joint"], 2),
                "hours_effective": round(ts["hours_effective"], 2), "hours_policy": hours_policy,
                "repeat_rate": round((len(ts["repeat_ids"]) / len(ts["unique_ids"])) * 100, 1) if ts["unique_ids"] else 0.0,
                "groups": sorted(ts["groups"]), "cost": round(ts["cost"]),
                "bio": meta.get("bio", ""), "works": meta.get("works", ""), "source_refs": ts["source_refs"],
            })
        teachers_out.sort(key=lambda x: (-x["courses"], -x["attendance"]))
        workload_balance = _compute_workload_balance([t["courses"] for t in teachers_out])

        tl_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"courses": 0, "attendance": 0, "new_p": 0, "ret_p": 0, "cost": 0.0})
        seen_so_far: set[str] = set()
        for c in courses:
            key = c["year"] if c["year"] != "نامشخص" else "نامشخص"
            tl_map[key]["courses"] += 1
            if c.get("attendance_valid"):
                tl_map[key]["attendance"] += c["attendance"]
            tl_map[key]["cost"] += c["cost"]
        for p in sorted(persons, key=lambda x: x["year"]):
            key = p["year"] or "نامشخص"
            pid = (nid_to_id.get(p.get("nid") or "") if p.get("nid") else None) or (phone_to_id.get(p["phone"]) if p["phone"] else None) or name_to_id.get(canon_key(p["name"]))
            if pid and pid in seen_so_far:
                tl_map[key]["ret_p"] += 1
            else:
                tl_map[key]["new_p"] += 1
                if pid:
                    seen_so_far.add(pid)
        timeline = [{"label": k, "courses": v["courses"], "attendance": v["attendance"], "new_participants": v["new_p"] if has_person_level else 0, "returning_participants": v["ret_p"] if has_person_level else 0, "cost": round(v["cost"])} for k, v in sorted(tl_map.items())]

        month_counts, month_att = [0] * 12, [0] * 12
        for c in courses:
            mi = c.get("month_idx", -1)
            if 0 <= mi < 12:
                month_counts[mi] += 1
                if c.get("attendance_valid"):
                    month_att[mi] += c["attendance"]
        heatmap = [{"month": JALALI_MONTHS[i], "courses": month_counts[i], "attendance": month_att[i]} for i in range(12)]

        cost_cats: dict[str, float] = defaultdict(float)
        for x in costs:
            cost_cats[x["category"]] += x["amount"]
        pareto_costs = [{"category": cname, "amount": round(amt)} for cname, amt in sorted(cost_cats.items(), key=lambda kv: -kv[1])[:7]]

        health = self._compute_data_health(participants_list, dup_files, missing_att_courses, total_courses)
        health["source_discrepancies"] = sorted(source_discrepancies, key=lambda d: -abs(d["diff"]))
        events = suite.get("events") or []
        return {
            "ok": True, "data_mode": data_mode, "hours_policy": hours_policy, "has_person_level": has_person_level,
            "kpis": {
                "total_courses": total_courses, "joint_courses": joint_courses_total, "collective_courses": collective_courses_total,
                "total_attendance": total_attendance, "person_courses": total_attendance,
                "unique_participants": unique_participants, "unique_verified": has_person_level,
                "repeat_rate": repeat_rate, "avg_per_course": avg_per_course, "median_per_course": median_per_course,
                "missing_attendance_courses": missing_att_courses, "total_hours": total_hours, "total_sessions": total_sessions,
                "total_teachers": len(teachers_out), "total_groups": len(groups_out),
                "total_cost": total_cost, "cost_per_attendee": cost_per_attendee, "cost_per_unique": cost_per_unique, "cost_unit": cost_unit,
                "data_health_score": health["score"], "data_confidence_pct": data_confidence_pct,
                "cross_group_overlap_count": cross_group_people, "workload_balance": workload_balance,
                "eitaa_ads_count": sum(len(e.get("eitaa_ads") or e.get("press_links") or []) for e in events),
                "letters_count": len(suite.get("letters") or []),
            },
            "filters_meta": {"groups": meta_groups, "teachers": meta_teachers, "years": meta_years},
            "timeline": timeline,
            "retention": [{"label": lbl, "count": ret_buckets.get(lbl, 0)} for lbl in ("۱ دوره (جدیدالورود)", "۲ دوره (نیمه‌فعال)", "۳ تا ۴ دوره (فعال)", "۵ تا ۷ دوره (مستمر)", "۸+ دوره (ثابت)")],
            "groups": groups_out, "affinity_matrix": {"labels": aff_labels, "matrix": aff_matrix, "active_matrix": aff_active_matrix},
            "teachers": teachers_out, "heatmap": heatmap, "pareto_costs": pareto_costs,
            "participants": participants_list[:5000], "participants_total": len(participants_list), "cost_unit": cost_unit, "data_health": health,
            "filtered_courses": [
                {"title": c.get("title", ""), "group": c.get("group", ""), "teacher": c.get("teacher", ""), "attendance": int(c.get("attendance") or 0), "hours": float(c.get("hours") or 0.0), "sessions": int(c.get("sessions") or 0), "year": c.get("year", ""), "mode": c.get("holding_mode", "انفرادی")}
                for c in sorted(courses, key=lambda x: (-int(x.get("attendance") or 0), x.get("title", "")))[:60]
            ],
        }

    def get_audit_rows(self, entity_type: str = "teacher", entity_name: str = "") -> dict[str, Any]:
        courses, _, _ = self._scan_duckdb(data_mode="clean")
        brain_cfg = load_brain_config()
        alias_map = resolve_canonical_map("teacher")
        target = normalize_fa(entity_name)
        target_core = _clean_for_compare(target, entity_type, brain_cfg)
        matched = []
        for c in courses:
            if entity_type == "group":
                if target and normalize_fa(c.get("group")) != target:
                    continue
            elif entity_type == "course":
                if target and target not in normalize_fa(c.get("title")):
                    continue
            else:
                _, parts = split_joint_names(c.get("teacher") or "", "teacher", brain_cfg)
                resolved = [alias_map.get(_clean_for_compare(pt, "teacher", brain_cfg), pt) for pt in parts]
                cores = [_clean_for_compare(x, "teacher", brain_cfg) for x in resolved]
                if target and target not in resolved and target_core not in cores:
                    continue
            matched.append({
                "course_uid": c["course_uid"], "course": c["title"], "teacher_raw": c["teacher"],
                "group": c["group"], "date": c["date"] or "—",
                "attendance": c["attendance"] if c.get("attendance_valid") else None,
                "hours": c.get("hours", 0.0), "sessions": c.get("sessions", 0),
                "file_name": c.get("file_name", ""), "source_sheet": c.get("source_sheet", ""), "row_index": c.get("row_index", 0),
            })
        return {"ok": True, "entity_type": entity_type, "entity_name": entity_name, "count": len(matched), "rows": matched[:200]}

    def _compute_data_health(self, participants: list[dict[str, Any]], duplicate_files: list[dict[str, Any]] | None = None, missing_att_courses: int = 0, total_courses: int = 0) -> dict[str, Any]:
        total = len(participants)
        missing_phone = sum(1 for p in participants if not p.get("phone"))
        missing_level = sum(1 for p in participants if not p.get("level"))
        rejected_pairs: set[tuple[str, str]] = set()
        try:
            from src.core.memory_engine import list_aliases
            for ex in list_aliases(status="rejected"):
                if ex.get("entity_type") == "person":
                    rejected_pairs.add(tuple(sorted([canon_key(ex["canonical_name"]), canon_key(ex["alias_name"])])))
        except Exception:
            pass
        for pair in (self._ensure_suite_file().get("rejected_duplicates") or []):
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                rejected_pairs.add(tuple(sorted([canon_key(pair[0]), canon_key(pair[1])])))

        duplicates: list[dict[str, Any]] = []
        seen_dup_pairs: set[tuple[str, str]] = set()
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p_item in participants:
            ka = canon_key(p_item["name"])
            if len(ka) < 4:
                continue
            ws_p = p_item["name"].split()
            sur_k = canon_key(ws_p[-1])[:3] if len(ws_p) >= 2 else ka[:3]
            buckets[f"{ka[:2]}|{sur_k}"].append(p_item)
            buckets[f"pre|{ka[:4]}"].append(p_item)

        for b_list in buckets.values():
            if len(b_list) < 2:
                continue
            for i in range(len(b_list)):
                a = b_list[i]
                ka = canon_key(a["name"])
                pa, na = (a.get("phone") or "").strip(), (a.get("nid") or "").strip()
                wa = a["name"].split()
                for j in range(i + 1, len(b_list)):
                    b = b_list[j]
                    kb = canon_key(b["name"])
                    if ka == kb or abs(len(ka) - len(kb)) > 3:
                        continue
                    pair_k = tuple(sorted([ka, kb]))
                    if pair_k in rejected_pairs or pair_k in seen_dup_pairs:
                        continue
                    pb, nb = (b.get("phone") or "").strip(), (b.get("nid") or "").strip()
                    if pa and pb and pa != pb:
                        continue
                    if na and nb and na != nb:
                        continue
                    wb = b["name"].split()
                    if len(wa) >= 2 and len(wb) >= 2:
                        sur_sim = difflib.SequenceMatcher(None, canon_key(wa[-1]), canon_key(wb[-1])).ratio()
                        if sur_sim < 0.72:
                            continue
                    sim = difflib.SequenceMatcher(None, ka, kb).ratio()
                    if sim >= 0.85:
                        seen_dup_pairs.add(pair_k)
                        duplicates.append({"name_a": a["name"], "phone_a": pa or "—", "courses_a": a.get("courses_count", 1), "name_b": b["name"], "phone_b": pb or "—", "courses_b": b.get("courses_count", 1), "similarity": round(sim * 100)})
                        if len(duplicates) >= 40:
                            break
                if len(duplicates) >= 40:
                    break
            if len(duplicates) >= 40:
                break
        dup_files = duplicate_files if duplicate_files is not None else detect_duplicate_files()
        penalty = (0.0 if total == 0 else ((missing_phone / total) * 18 + (missing_level / total) * 8 + min(24, len(duplicates) * 4)))
        if total_courses > 0:
            penalty += (missing_att_courses / total_courses) * 20
        penalty += min(18, len(dup_files) * 6)
        return {"score": max(30, min(100, round(100 - penalty))), "total_records": total, "missing_phone": missing_phone, "missing_level": missing_level, "missing_attendance_courses": missing_att_courses, "duplicates": duplicates, "duplicate_files": dup_files}

    def merge_duplicate_records(self, canonical_name: str, alias_name: str) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        c_nm, a_key = normalize_fa(canonical_name), canon_key(alias_name)
        if not c_nm or not a_key:
            return {"ok": False, "error": "نام معتبر نیست."}
        suite.setdefault("merges", {})[a_key] = c_nm
        for reg in suite.get("registrations") or []:
            if canon_key(reg.get("name")) == a_key:
                reg["name"] = c_nm
        self._save_suite(suite)
        try:
            save_alias(canonical_name=c_nm, alias_name=alias_name, entity_type="person", status="approved")
        except Exception:
            pass
        return {"ok": True}

    def reject_duplicate_records(self, name_a: str, name_b: str) -> dict[str, Any]:
        na, nb = normalize_fa(name_a), normalize_fa(name_b)
        if not na or not nb:
            return {"ok": False, "error": "نام معتبر نیست."}
        suite = self._ensure_suite_file()
        rej = list(suite.get("rejected_duplicates") or [])
        pair_k = sorted([canon_key(na), canon_key(nb)])
        if not any(isinstance(x, list) and sorted([canon_key(x[0]), canon_key(x[1])]) == pair_k for x in rej if len(x) == 2):
            rej.append([na, nb])
        suite["rejected_duplicates"] = rej
        self._save_suite(suite)
        try:
            save_alias(canonical_name=na, alias_name=nb, entity_type="person", status="rejected")
        except Exception:
            pass
        return {"ok": True}

    def get_teacher_profile(self, teacher_name: str, precomputed: dict[str, Any] | None = None) -> dict[str, Any]:
        an = precomputed if (isinstance(precomputed, dict) and precomputed.get("ok")) else self.get_executive_analytics({"teacher": teacher_name})
        t_core = canonical_teacher_core(teacher_name)
        t_info = next(
            (
                t for t in an["teachers"]
                if canon_key(t["name"]) == canon_key(teacher_name)
                or (t_core and canonical_teacher_core(t["name"]) == t_core)
            ),
            None,
        )
        meta = (self._ensure_suite_file().get("teacher_meta") or {}).get(canon_key(teacher_name)) or {}
        if not t_info:
            t_info = {"name": teacher_name, "courses": 0, "independent_courses": 0, "joint_courses": 0, "attendance": 0, "unique": 0, "avg_attendance": 0, "repeat_rate": 0, "groups": [], "cost": 0, "hours_effective": 0, "sessions": 0}
        t_info["bio"], t_info["works"] = meta.get("bio", ""), meta.get("works", "")
        return {"ok": True, "teacher": t_info, "timeline": an["timeline"], "participants": an["participants"][:80], "groups": an["groups"], "audit_rows": self.get_audit_rows("teacher", teacher_name).get("rows") or []}

    def save_teacher_meta(self, teacher_name: str, bio: str, works: str) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        suite.setdefault("teacher_meta", {})[canon_key(teacher_name)] = {"name": normalize_fa(teacher_name), "bio": str(bio or "").strip(), "works": str(works or "").strip()}
        self._save_suite(suite)
        return {"ok": True}

    def get_participant_profile(self, person_key: str, precomputed: dict[str, Any] | None = None) -> dict[str, Any]:
        an = precomputed if (isinstance(precomputed, dict) and precomputed.get("ok")) else self.get_executive_analytics()
        pk_s = str(person_key or "").strip()
        target = next(
            (
                p for p in an["participants"]
                if (p.get("profile_key") and p["profile_key"] == pk_s)
                or p["id"] == pk_s
                or (p.get("phone") and p["phone"] == pk_s)
                or (p.get("nid") and p["nid"] == pk_s)
                or canon_key(p["name"]) == canon_key(pk_s)
            ),
            None,
        )
        return {"ok": True, "participant": target} if target else {"ok": False, "error": "دانش‌پژوه مورد نظر یافت نشد."}

    def save_participant_meta(self, profile_key: str, meta: dict[str, Any]) -> dict[str, Any]:
        pk = str(profile_key or "").strip()
        if not pk:
            return {"ok": False, "error": "شناسه دانش‌پژوه نامعتبر است."}
        suite = self._ensure_suite_file()
        store = dict(suite.get("participant_meta") or {})
        raw_tags = meta.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in re.split(r"[,،\n]+", raw_tags) if t.strip()]
        clean_tags = []
        for t in raw_tags:
            ts = normalize_fa(t)
            if ts and ts not in clean_tags:
                clean_tags.append(ts)
        prev_m = dict(store.get(pk) or {})
        v_stat = str(meta.get("vetting_status") if "vetting_status" in meta else prev_m.get("vetting_status") or "normal").strip().lower()
        if v_stat not in ("normal", "approved", "graylist", "blacklist"):
            v_stat = "normal"
        v_reason = str(meta.get("vetting_reason") if "vetting_reason" in meta else prev_m.get("vetting_reason") or "").strip()[:400]
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        v_changed = (v_stat != prev_m.get("vetting_status")) or (v_reason != prev_m.get("vetting_reason"))
        store[pk] = {
            "phone": normalize_phone(meta.get("phone") if "phone" in meta else prev_m.get("phone") or ""),
            "nid": normalize_nid(meta.get("nid") if "nid" in meta else prev_m.get("nid") or ""),
            "level": normalize_fa(meta.get("level") if "level" in meta else prev_m.get("level") or ""),
            "tags": clean_tags[:12] if "tags" in meta else list(prev_m.get("tags") or []),
            "notes": str(meta.get("notes") if "notes" in meta else prev_m.get("notes") or "").strip()[:1500],
            "vetting_status": v_stat,
            "vetting_reason": v_reason,
            "vetting_updated_at": now_ts if v_changed else str(prev_m.get("vetting_updated_at") or now_ts),
            "updated_at": now_ts,
        }
        suite["participant_meta"] = store
        self._save_suite(suite)
        return {"ok": True, "profile_key": pk, "meta": store[pk]}

    def parse_porsline_file(self, file_path: str) -> dict[str, Any]:
        p = Path(file_path)
        if not p.exists():
            return {"ok": False, "error": "فایل انتخاب‌شده یافت نشد."}
        raw_rows: list[list[Any]] = []
        try:
            suf = p.suffix.lower()
            if suf == ".csv":
                with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
                    raw_rows = list(csv.reader(f))
            elif suf == ".xls":
                import pandas as pd
                df_xls = pd.read_excel(p, sheet_name=0, header=None)
                raw_rows = [["" if pd.isna(v) else clean_excel_cell_value(v) for v in row] for row in df_xls.itertuples(index=False, name=None)]
            else:
                from openpyxl import load_workbook
                wb = load_workbook(p, read_only=True, data_only=True)
                raw_rows = [[clean_excel_cell_value(v) for v in r] for r in wb.active.iter_rows(values_only=True)]
                wb.close()
        except Exception as exc:
            return {"ok": False, "error": f"خطا در خواندن فایل: {exc}"}

        raw_rows = [r for r in raw_rows if any(v is not None and str(v).strip() != "" for v in r)]
        if not raw_rows:
            return {"ok": False, "error": "فایل خالی یا فاقد سرتیتر معتبر است."}

        init_cols = [normalize_fa(h) if (h is not None and str(h).strip()) else f"ستون_{i + 1}" for i, h in enumerate(raw_rows[0])]
        headers, rows, banner_ctx = promote_banner_headers(init_cols, raw_rows[1:])
        headers = [normalize_fa(h) for h in headers]
        if not headers:
            return {"ok": False, "error": "فایل خالی یا فاقد سرتیتر معتبر است."}

        norm_h = [h.lower() for h in headers]

        def pick(kws, exclude_idxs=()):
            return next((idx for idx, h in enumerate(norm_h) if idx not in exclude_idxs and any(k in h for k in kws)), -1)

        i_full = pick(("نام و نام خانوادگی", "نام کامل", "شرکت کننده", "full_name", "fullname"))
        i_last = pick(("نام خانوادگی", "فامیل", "last_name", "last name")) if i_full == -1 else -1
        i_first = -1
        if i_full == -1:
            # Prefer exact 'نام' / 'نام کوچک' and NEVER collide with i_last ('نام خانوادگی')
            i_first = next((idx for idx, h in enumerate(norm_h) if idx != i_last and h in ("نام", "نام کوچک", "first_name", "first name", "name")), -1)
            if i_first == -1:
                i_first = pick(("نام کوچک", "نام"), exclude_idxs=(i_last,))

        i_phone = pick(("موبایل", "همراه", "تلفن", "تماس", "phone", "mobile"))
        i_level = pick(("سطح", "پایه", "مقطع", "تحصیلات", "level"))
        i_nid = pick(("کد ملی", "کدملی", "شماره ملی", "گذرنامه", "پاسپورت", "شماره گذرنامه", "شماره پاسپورت", "کد فراگیر", "کد یکتا", "کد اتباع", "فیدا", "آمایش", "national", "passport", "fida", "cnic"))
        i_sess_num = pick(("تعداد جلسات", "جلسات حضور", "جلسات", "sessions"))

        existing_an = self.get_executive_analytics()
        known_nids = {x["nid"]: x for x in existing_an["participants"] if x.get("nid")}
        known_phones = {x["phone"]: x for x in existing_an["participants"] if x.get("phone")}
        known_names = {canon_key(x["name"]): x for x in existing_an["participants"]}
        meta_store_pl = dict(self._ensure_suite_file().get("participant_meta") or {})

        reserved_p = {idx for idx in (i_full, i_first, i_last, i_phone, i_level, i_nid, i_sess_num) if idx != -1}
        if norm_h and any(k in norm_h[0] for k in ("ردیف", "شماره", "no", "id")):
            reserved_p.add(0)
        p_sess_cols = _detect_session_columns(headers, reserved_p)

        parsed, new_cnt, ret_cnt, black_cnt, gray_cnt = [], 0, 0, 0, 0
        for r in rows:
            if is_blank_numbered_row(list(r)) or is_summary_row_smart(list(r)):
                continue
            if i_full != -1 and i_full < len(r):
                name = clean_participant_name(r[i_full])
            else:
                fn_p = normalize_fa(r[i_first]) if (i_first != -1 and i_first < len(r)) else ""
                ln_p = normalize_fa(r[i_last]) if (i_last != -1 and i_last < len(r)) else ""
                name = clean_participant_name(f"{fn_p} {ln_p}")
            if len(name) < 3 or is_junk_label(name):
                continue
            ph = normalize_phone(r[i_phone]) if (i_phone != -1 and i_phone < len(r)) else ""
            lvl = normalize_fa(r[i_level]) if (i_level != -1 and i_level < len(r)) else ""
            nid = normalize_nid(r[i_nid]) if (i_nid != -1 and i_nid < len(r)) else ""
            prev = (known_nids.get(nid) if nid else None) or (known_phones.get(ph) if ph else None) or known_names.get(canon_key(name))
            direct_meta = (
                (meta_store_pl.get(f"ph:{ph}") if ph else None)
                or (meta_store_pl.get(f"nid:{nid}") if nid else None)
                or meta_store_pl.get(f"nm:{canon_key(name)}")
                or {}
            )
            v_stat_p = (prev.get("vetting_status") if prev else None) or str(direct_meta.get("vetting_status") or "normal")
            v_reason_p = (prev.get("vetting_reason") if prev else "") or str(direct_meta.get("vetting_reason") or "")
            auto_gray_p = (prev.get("auto_graylist_reason") if prev else "") or ""
            if v_stat_p == "blacklist":
                black_cnt += 1
            elif v_stat_p == "graylist" or auto_gray_p:
                gray_cnt += 1
            is_new = prev is None
            new_cnt += int(is_new)
            ret_cnt += int(not is_new)

            s_marks = []
            s_att = s_late = s_exc = s_abs = 0
            for sc_idx, sc_lbl in p_sess_cols:
                raw_v = r[sc_idx] if sc_idx < len(r) else ""
                st_k, st_l = _classify_session_cell(raw_v)
                s_marks.append({"label": sc_lbl, "status": st_k, "raw": st_l})
                if st_k == "present":
                    s_att += 1
                elif st_k == "late":
                    s_att += 1
                    s_late += 1
                elif st_k == "excused":
                    s_exc += 1
                else:
                    s_abs += 1

            s_tot_row = len(p_sess_cols)
            if not p_sess_cols and i_sess_num != -1 and i_sess_num < len(r):
                sv_p = parse_number_strict(r[i_sess_num])
                if sv_p is not None and sv_p >= 0:
                    s_att = int(round(sv_p))
                    s_tot_row = max(s_att, 1 if s_att > 0 else 0)
            parsed.append({
                "name": name, "phone": ph, "nid": nid, "level": lvl,
                "is_new": is_new, "prev_courses": prev["courses_count"] if prev else 0,
                "prev_attendance_rate": prev.get("attendance_rate") if prev else None,
                "vetting_status": v_stat_p,
                "vetting_reason": v_reason_p,
                "auto_graylist_reason": auto_gray_p,
                "default_approved": v_stat_p != "blacklist",
                "profile_key": (prev.get("profile_key") if prev else "") or (f"ph:{ph}" if ph else (f"nid:{nid}" if nid else f"nm:{canon_key(name)}")),
                "sessions_total": s_tot_row, "sessions_attended": s_att,
                "sessions_late": s_late, "sessions_excused": s_exc, "sessions_absent": s_abs,
                "session_marks": s_marks,
            })

        sug_course, sug_teacher = extract_roster_banner_meta(banner_ctx, p.name, "")
        return {
            "ok": True,
            "file_name": p.name,
            "suggested_course": sug_course,
            "suggested_teacher": sug_teacher,
            "total": len(parsed),
            "total_cleaned": len(parsed),
            "new_count": new_cnt,
            "returning_count": ret_cnt,
            "blacklisted_count": black_cnt,
            "graylisted_count": gray_cnt,
            "participants": parsed,
        }

    def commit_porsline_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        course, group, teacher = normalize_fa(payload.get("course_title") or "دوره جدید"), normalize_fa(payload.get("group") or "کارگروه دین شناسی"), normalize_fa(payload.get("teacher") or "نامشخص")
        date_str = normalize_fa(payload.get("date") or "")
        jd = parse_jalali_date(date_str)
        yr = jd["year"] or str(parse_jalali_date(datetime.now().strftime("%Y-%m-%d"))["year"])
        items = payload.get("participants") or []
        if not items:
            return {"ok": False, "error": "لیست شرکت‌کنندگان خالی است."}
        regs = list(suite.get("registrations") or [])
        for it in items:
            regs.append({"name": normalize_fa(it.get("name")), "phone": normalize_phone(it.get("phone")), "nid": normalize_nid(it.get("nid")), "level": normalize_fa(it.get("level")), "course": course, "group": group, "teacher": teacher, "date": jd["canonical"] or date_str, "year": yr, "sessions_total": int(it.get("sessions_total") or 0), "sessions_attended": int(it.get("sessions_attended") or 0), "sessions_late": int(it.get("sessions_late") or 0), "sessions_excused": int(it.get("sessions_excused") or 0), "sessions_absent": int(it.get("sessions_absent") or 0), "session_marks": list(it.get("session_marks") or [])})
        suite["registrations"] = regs
        self._save_suite(suite)
        return {"ok": True, "added": len(items)}

    def get_letters(self) -> list[dict[str, Any]]:
        return list((self._ensure_suite_file().get("letters") or []))

    def delete_letter(self, letter_id: str) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        suite["letters"] = [x for x in (suite.get("letters") or []) if x.get("id") != letter_id]
        self._save_suite(suite)
        return {"ok": True}

    def get_events(self) -> list[dict[str, Any]]:
        events = list(self._ensure_suite_file().get("events") or [])
        for ev in events:
            st = ev.get("stages") or {}
            if "eitaa_ads" not in st and "press" in st:
                st["eitaa_ads"] = bool(st.get("press"))
            ev["stages"] = st
            if "eitaa_ads" not in ev and "press_links" in ev:
                ev["eitaa_ads"] = list(ev.get("press_links") or [])
        return events

    def save_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        events = list(suite.get("events") or [])
        eid = str(payload.get("id") or f"evt_{int(datetime.now().timestamp() * 1000)}")
        ads_list = payload.get("eitaa_ads") if "eitaa_ads" in payload else (payload.get("press_links") or [])
        item = {"id": eid, "title": normalize_fa(payload.get("title") or "رویداد جدید"), "group": normalize_fa(payload.get("group") or "عمومی"), "teacher": normalize_fa(payload.get("teacher") or ""), "date": normalize_fa(payload.get("date") or ""), "stages": payload.get("stages") or {"poster": False, "intro": False, "held": False, "photos": False, "media": False, "eitaa_ads": False}, "eitaa_ads": ads_list or []}
        for i, ev in enumerate(events):
            if ev.get("id") == eid:
                events[i] = item
                break
        else:
            events.insert(0, item)
        suite["events"] = events
        self._save_suite(suite)
        return {"ok": True, "event": item}

    def delete_event(self, event_id: str) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        suite["events"] = [e for e in (suite.get("events") or []) if e.get("id") != event_id]
        self._save_suite(suite)
        return {"ok": True}
