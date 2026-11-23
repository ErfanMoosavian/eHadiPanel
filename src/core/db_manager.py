from __future__ import annotations

"""
eHadiPanel Core DB & Jalali Utility Hub (v48.0 Pro — Server-Ready / Zero UI Coupling)
Provides thread-safe DuckDB access, unified Persian/Jalali normalization,
summary-row detection, and duplicate-file auditing.
"""

from contextlib import contextmanager
from datetime import datetime
import hashlib
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Iterator

logger = logging.getLogger("eHadiPanel.DBManager")

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EN_DIGITS = "0123456789"
TO_EN_TRANS = str.maketrans(FA_DIGITS + AR_DIGITS, EN_DIGITS + EN_DIGITS)
TO_FA_TRANS = str.maketrans(EN_DIGITS + AR_DIGITS, FA_DIGITS + FA_DIGITS)
ZWNJ = "\u200c"

JALALI_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند",
)

JALALI_SEASONS = {
    "بهار": (1, 2, 3),
    "تابستان": (4, 5, 6),
    "پاییز": (7, 8, 9),
    "پائیز": (7, 8, 9),
    "زمستان": (10, 11, 12),
}

INTERNAL_TABLES = frozenset({
    "chat_history",
    "processed_files",
    "tabular_catalog",
    "user_rules",
    "entity_aliases",
    "app_settings",
    "diagnostics_log",
    "smart_teachers_exploded",
    "entity_brain_config",
    "entity_brain_history",
    "_meta_teacher_sig",
})

SUMMARY_ROW_RX = re.compile(
    r"^(?:جمع\s*کل|مجموع(?:\s*کل)?|جمع\s*صفحه|جمع\s*نهایی|جمع\s*فرعی|تجمیع(?:\s*کل)?|"
    r"جمع|کل\s*مؤسسه|کل\s*موسسه|کل|میانگین\s*کل|میانگین|قابل\s*پرداخت|"
    r"امضاء?(?:\s+.*)?|باقیمانده|مانده\s*نهایی|total|grand\s*total|subtotal|sum|average)$",
    re.IGNORECASE,
)

_LOCKS_GUARD = threading.Lock()
_DB_LOCKS: dict[str, threading.RLock] = {}


def get_db_lock(db_path: Path | str) -> threading.RLock:
    key = str(Path(db_path).resolve()).lower()
    with _LOCKS_GUARD:
        lk = _DB_LOCKS.get(key)
        if lk is None:
            lk = threading.RLock()
            _DB_LOCKS[key] = lk
        return lk


def to_en_digits(text: Any) -> str:
    return str(text or "").translate(TO_EN_TRANS)


def to_fa_digits(text: Any) -> str:
    return str(text or "").translate(TO_FA_TRANS)


def normalize_persian(text: Any) -> str:
    if text is None:
        return ""
    s = re.sub(r"[\u064b-\u065f\u0670\u0640]+", "", str(text))
    trans = str.maketrans(
        FA_DIGITS + AR_DIGITS + "\u064a\u0649\u06d2\u0643\u0623\u0625\u0629\u06be\u06c1\u06c0\u0624" + ZWNJ,
        EN_DIGITS + EN_DIGITS + "\u06cc\u06cc\u06cc\u06a9\u0627\u0627\u0647\u0647\u0647\u0647\u0648 ",
    )
    s = s.translate(trans)
    return re.sub(r"\s+", " ", s).strip()


def clean_participant_name(raw: Any) -> str:
    """Cleans participant names from noisy Excel/Porsline exports (including Afghan/Pakistani/Indian Urdu/Arabic names)."""
    s = normalize_persian(raw)
    if not s:
        return ""
    # Strip random 2-6 char alphanumeric export prefixes like '69qY سید حسین طاهری'
    s = re.sub(r"^[A-Za-z0-9]{2,6}\s+(?=[\u0600-\u06FF])", "", s)
    # Strip status prefixes and trailing markers
    s = re.sub(r"^(?:تایید\s*شده|تائید\s*شده|تاییدشده)\s*[:\-ـ]?\s*", "", s)
    s = s.replace("*", "").replace("•", " ")
    s = re.sub(r"\s+", " ", s).strip(" -–—،,؛;:.")
    # Deduplicate accidental repeated trailing surname ('محمد امیری امیری' -> 'محمد امیری', 'نقی پور نقی پور' -> 'نقی پور')
    toks = s.split()
    if len(toks) >= 4 and toks[-2:] == toks[-4:-2]:
        toks = toks[:-2]
    elif len(toks) >= 3 and toks[-1] == toks[-2]:
        toks = toks[:-1]
    return " ".join(toks).strip()


_TEACHER_HONORIFIC_STRIP_RX = re.compile(
    r"^(?:حجج\s*الاسلام\s*(?:و\s*المسلمین)?|حجت\s*الاسلام\s*(?:و\s*المسلمین)?|"
    r"آیت\s*الله(?:\s*العظمی)?|ایت\s*الله(?:\s*العظمی)?|"
    r"دکتر|استاد|مهندس|جناب\s*آقای|جناب\s*اقای|آقای|اقای|خانم|سرکار\s*خانم)\s+"
)


def canonical_teacher_core(raw: Any) -> str:
    """Strips clerical/academic honorifics and normalizes ئ/آ/spacing for exact teacher deduplication (zero false merges)."""
    s = normalize_persian(raw).replace("ئ", "ی").replace("آ", "ا")
    if not s:
        return ""
    for _ in range(4):
        s2 = _TEACHER_HONORIFIC_STRIP_RX.sub("", s).strip(" :.-–—،,")
        if s2 == s:
            break
        s = s2
    return re.sub(r"\s+", " ", s).strip()


def parse_number_strict(val: Any) -> float | None:
    """Distinguishes real zero (0 / '۰') from missing/blank/dash ('-', 'ندارد', '', None)."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        if val != val:
            return None
        return float(val)
    s = normalize_persian(val)
    if not s or s in ("-", "—", "–", "ندارد", "ثبت نشده", "ثبت‌نشده", "نامشخص", "خالی", "null", "none", "nan"):
        return None
    if re.search(r"\d{2,4}[/\-]\d{1,2}[/\-]\d{1,4}", s):
        return None
    s = s.replace("\u066b", ".").replace("\u066c", "").replace(",", "").replace("،", "").replace("٬", "")
    cleaned = re.sub(r"[^0-9.\-]", "", s)
    if not cleaned or cleaned in {".", "-", "-."}:
        return None
    if cleaned.count(".") > 1 or cleaned.count("-") > 1:
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


def is_summary_row_smart(values: list[Any]) -> bool:
    non_empty = [normalize_persian(v).strip(" :.-–—()[]") for v in values if v is not None and str(v).strip() != ""]
    if not non_empty:
        return True
    for s in non_empty[:3]:
        if s and SUMMARY_ROW_RX.match(s):
            return True
        if s.startswith(("جمع کل", "مجموع کل", "جمع نهایی", "grand total")):
            return True
    return False


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return int(jy), int(jm), int(jd)


def month_to_season(month_num: int) -> str:
    if 1 <= month_num <= 3:
        return "بهار"
    if 4 <= month_num <= 6:
        return "تابستان"
    if 7 <= month_num <= 9:
        return "پاییز"
    if 10 <= month_num <= 12:
        return "زمستان"
    return ""


def parse_jalali_date(raw: Any, fallback_text: str = "") -> dict[str, Any]:
    combined = normalize_persian(raw)
    fb = normalize_persian(fallback_text)

    def _try_parse(s: str) -> dict[str, Any] | None:
        if not s:
            return None
        m_full = re.search(r"\b(13\d{2}|14\d{2}|20\d{2})[/\-.](\d{1,2})[/\-.](\d{1,2})\b", s)
        if m_full:
            y, mo, d = int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3))
            if y >= 1900 and 1 <= mo <= 12 and 1 <= d <= 31:
                jy, jm, jd = gregorian_to_jalali(y, mo, d)
            elif 1300 <= y <= 1499 and 1 <= mo <= 12 and 1 <= d <= 31:
                jy, jm, jd = y, mo, d
            else:
                jy, jm, jd = 0, 0, 0
            if jy:
                return {
                    "year": str(jy), "month": jm, "day": jd,
                    "month_name": JALALI_MONTHS[jm - 1], "season": month_to_season(jm),
                    "canonical": f"{jy}/{jm:02d}/{jd:02d}", "is_parsed": True,
                }

        m_short = re.search(r"\b(0[0-9]|9[0-9])[/\-.](\d{1,2})[/\-.](\d{1,2})\b", s)
        if m_short:
            yy, mo, d = int(m_short.group(1)), int(m_short.group(2)), int(m_short.group(3))
            jy = (1400 + yy) if yy <= 20 else (1300 + yy)
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return {
                    "year": str(jy), "month": mo, "day": d,
                    "month_name": JALALI_MONTHS[mo - 1], "season": month_to_season(mo),
                    "canonical": f"{jy}/{mo:02d}/{d:02d}", "is_parsed": True,
                }

        m_ym = re.search(r"\b(13\d{2}|14\d{2}|20\d{2})[/\-.](\d{1,2})\b", s)
        if m_ym:
            y, mo = int(m_ym.group(1)), int(m_ym.group(2))
            if 1 <= mo <= 12:
                jy, jm, _ = gregorian_to_jalali(y, mo, 15) if y >= 1900 else (y, mo, 1)
                return {
                    "year": str(jy), "month": jm, "day": 0,
                    "month_name": JALALI_MONTHS[jm - 1], "season": month_to_season(jm),
                    "canonical": f"{jy}/{jm:02d}", "is_parsed": True,
                }

        s_no_span = re.sub(r"\b(?:13|14)\d{2}\s*(?:[-–—_/]|تا|الی)\s*(?:13|14)\d{2}\b", " ", s)
        yr_m = re.search(r"\b(13\d{2}|14\d{2})\b", s_no_span)
        yr_s = yr_m.group(1) if yr_m else ""
        # Strict word-boundary matching so 'دی' NEVER matches inside 'دین'/'حدیث'/'احمدی'/'توحید'
        # and 'مهر'/'آذر'/'آبان'/'تیر' NEVER match inside surnames or course titles!
        for idx, mname in enumerate(JALALI_MONTHS, start=1):
            if re.search(rf"(?:^|[\s\-_/()،,.:;0-9])({re.escape(mname)}(?:\s*ماه)?)(?:$|[\s\-_/()،,.:;0-9])", s):
                return {
                    "year": yr_s, "month": idx, "day": 0,
                    "month_name": mname, "season": month_to_season(idx),
                    "canonical": f"{yr_s}/{idx:02d}" if yr_s else mname, "is_parsed": True,
                }

        for sname, months_t in JALALI_SEASONS.items():
            if re.search(rf"(?:^|[\s\-_/()،,.:;0-9])({re.escape(sname)})(?:$|[\s\-_/()،,.:;0-9])", s):
                clean_s = "پاییز" if sname == "پائیز" else sname
                return {
                    "year": yr_s, "month": months_t[0], "day": 0,
                    "month_name": "", "season": clean_s,
                    "canonical": f"{clean_s} {yr_s}".strip(), "is_parsed": True,
                }

        if yr_s:
            return {
                "year": yr_s, "month": 0, "day": 0,
                "month_name": "", "season": "", "canonical": yr_s, "is_parsed": True,
            }
        return None

    parsed = _try_parse(combined) or _try_parse(fb)
    if parsed:
        return parsed
    return {"year": "", "month": 0, "day": 0, "month_name": "", "season": "", "canonical": "", "is_parsed": False}


def format_jalali_now(include_time: bool = True, fa_digits: bool = True) -> str:
    now = datetime.now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    out = f"{jy}/{jm:02d}/{jd:02d}"
    if include_time:
        out += f" - {now.strftime('%H:%M')}"
    return to_fa_digits(out) if fa_digits else out


def iso_to_jalali(iso_str: str, fa_digits: bool = True) -> str:
    s = str(iso_str or "").strip()
    if not s:
        return ""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}:\d{2}))?", s)
    if not m:
        return to_fa_digits(s) if fa_digits else s
    gy, gm, gd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    tm = m.group(4) or ""
    if gy >= 1900:
        jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
        res = f"{jy}/{jm:02d}/{jd:02d}" + (f" ساعت {tm}" if tm else "")
    else:
        res = f"{gy}/{gm:02d}/{gd:02d}" + (f" ساعت {tm}" if tm else "")
    return to_fa_digits(res) if fa_digits else res


def resolve_default_duckdb_path(explicit: Path | str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if p.parent.exists():
            return p
    try:
        from src.core.config import Config
        cfg_db = Path(Config.DUCKDB_PATH)
        if cfg_db.exists() or cfg_db.parent.exists():
            return cfg_db
    except Exception:
        pass
    root = Path(__file__).resolve().parents[2]
    for folder in (root / "data" / "storage", root / "data", root):
        if folder.exists():
            for fp in sorted(folder.glob("*.duckdb")):
                if fp.is_file():
                    return fp
    return None


@contextmanager
def duckdb_session(
    db_path: Path | str | None = None,
    read_only: bool = False,
    retries: int = 4,
    with_macros: bool = False,
) -> Iterator[Any]:
    import duckdb  # type: ignore

    target = resolve_default_duckdb_path(db_path)
    if target is None:
        raise FileNotFoundError("مسیر پایگاه‌داده DuckDB یافت نشد.")

    lk = get_db_lock(target)
    with lk:
        con = None
        last_err: Exception | None = None
        for attempt in range(max(1, retries)):
            try:
                con = duckdb.connect(str(target), read_only=read_only)
                break
            except Exception as exc:
                last_err = exc
                if read_only:
                    try:
                        con = duckdb.connect(str(target))
                        break
                    except Exception as exc2:
                        last_err = exc2
                time.sleep(0.08 * (attempt + 1))
        if con is None:
            raise last_err or RuntimeError("اتصال به پایگاه‌داده DuckDB برقرار نشد.")
        try:
            if with_macros:
                try:
                    from src.core.smart_brain import register_persian_macros
                    register_persian_macros(con)
                except Exception:
                    pass
            yield con
        finally:
            try:
                con.close()
            except Exception:
                pass


def detect_duplicate_files(db_path: Path | str | None = None) -> list[dict[str, Any]]:
    target = resolve_default_duckdb_path(db_path)
    if not target or not target.exists():
        return []

    alerts: list[dict[str, Any]] = []
    try:
        with duckdb_session(target) as con:
            tables = {str(r[0]) for r in con.execute("SHOW TABLES").fetchall()}
            if "processed_files" not in tables:
                return []
            rows = con.execute(
                "SELECT file_name, file_hash, file_type, tables_count, rows_count "
                "FROM processed_files WHERE status = 'موفق' ORDER BY file_name"
            ).fetchall()

            by_hash: dict[str, list[str]] = {}
            by_stem: dict[str, list[dict[str, Any]]] = {}
            for fn, fhash, ftype, tcnt, rcnt in rows:
                fn_s = str(fn or "")
                fh_s = str(fhash or "")
                if fh_s:
                    by_hash.setdefault(fh_s, []).append(fn_s)
                stem = Path(fn_s).stem
                clean_stem = normalize_persian(stem).lower()
                clean_stem = re.sub(
                    r"(?:نسخه\s*\d+|ویرایش\s*\d+|نهایی|جدید|اصلاح\s*شده|اصلاحی|کپی|copy|final|new|v\d+|\(\d+\)|\d{4})$",
                    "",
                    clean_stem,
                ).strip(" _-–—.")
                if len(clean_stem) >= 4:
                    by_stem.setdefault(clean_stem, []).append({
                        "file_name": fn_s,
                        "rows_count": int(rcnt or 0),
                        "tables_count": int(tcnt or 0),
                    })

            seen_pairs: set[tuple[str, str]] = set()
            for fh, fnames in by_hash.items():
                if len(fnames) > 1:
                    key = tuple(sorted(fnames[:2]))
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        alerts.append({
                            "type": "exact_duplicate",
                            "severity": "high",
                            "files": fnames,
                            "reason": "محتوای این فایل‌ها کاملاً یکسان است (احتمال دوباره‌شماری آمار).",
                        })

            for stem, items in by_stem.items():
                if len(items) > 1:
                    fnames = [x["file_name"] for x in items]
                    key = tuple(sorted(fnames[:2]))
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        alerts.append({
                            "type": "multi_version",
                            "severity": "medium",
                            "files": fnames,
                            "reason": f"چند نسخه با نام بسیار مشابه («{stem}») هم‌زمان در پایگاه داده وجود دارد.",
                        })

            if "tabular_catalog" in tables:
                trows = con.execute(
                    "SELECT file_name, source_sheet, rows_count, columns_json FROM tabular_catalog"
                ).fetchall()
                sig_map: dict[str, set[str]] = {}
                for fn, sh, rc, cjson in trows:
                    if int(rc or 0) < 3:
                        continue
                    sig = hashlib.md5(f"{rc}|{cjson}".encode("utf-8")).hexdigest()
                    sig_map.setdefault(sig, set()).add(str(fn or ""))
                for sig, fset in sig_map.items():
                    if len(fset) > 1:
                        flist = sorted(fset)
                        key = (flist[0], flist[1])
                        if key not in seen_pairs:
                            seen_pairs.add(key)
                            alerts.append({
                                "type": "identical_table_structure",
                                "severity": "medium",
                                "files": flist,
                                "reason": "جداول با تعداد ردیف و ستون‌های کاملاً یکسان در چند فایل مختلف یافت شد.",
                            })
    except Exception as exc:
        logger.warning("detect_duplicate_files failed: %s", exc)
    return alerts[:20]


# ==================== Smart Excel Banner-Header Promotion & Entity Guards ====================

_PLACEHOLDER_COL_RX = re.compile(r"^(?:ستون[_\s]*\d+|unnamed[:\s]*\d*|column[_\s]*\d*|col[_\s]*\d*|f\d+)$", re.IGNORECASE)
_PURE_NUM_OR_CODE_RX = re.compile(r"^[\s\d۰-۹٠-٩.,/\-:+()%#]+(?:ریال|تومان|نفر|جلسه|ساعت|روز|ماه)?\s*$")
_DATE_OR_RANGE_RX = re.compile(
    r"(?:از\s*تاریخ|تا\s*تاریخ|مورخ|الی\s*[\d۰-۹]|سال\s*[\d۰-۹]{4}|\b(?:13|14)\d{2}[/\-]\d{1,2}(?:[/\-]\d{1,2})?\b|\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b)"
)
_BANNER_PHRASE_RX = re.compile(
    r"(?:لیست\s*حضور|فهرست\s*حضور|صورتحساب|صورت\s*حساب|گزارش\s*مالی|گزارش\s*عملکرد|از\s*تاریخ|بسمه\s*تعالی|مؤسسه\s*علمی|موسسه\s*علمی)"
)

KNOWN_HEADER_TOKENS = (
    "ردیف", "شماره", "نام", "نام خانوادگی", "نام و نام خانوادگی", "موبایل", "همراه", "تلفن",
    "کد ملی", "کدملی", "سطح", "پایه", "تحصیلات",
    "شرح", "شرح کالا", "شرح هزینه", "کالا", "بابت", "موضوع", "عنوان", "عنوان دوره", "نام دوره", "دوره",
    "مبلغ", "مبلغ کل", "جمع", "جمع کل", "قیمت", "قیمت واحد", "فی", "تعداد", "مقدار", "واحد",
    "بدهکار", "بستانکار", "برداشت", "واریز", "مانده", "هزینه", "پرداخت", "پرداختی", "تنخواه", "خروجی",
    "تاریخ", "سند", "شماره سند", "شماره فاکتور", "فاکتور", "فروشنده", "فروشگاه", "طرف حساب", "ذینفع",
    "کارگروه", "بخش", "گروه", "دسته", "سرفصل", "استاد", "مدرس", "سخنران", "ارائه دهنده",
    "دانش پژوه", "مخاطب", "شرکت کننده", "شرکت کنندگان", "حاضرین", "ساعت", "جلسه", "جلسات", "توضیحات", "توضیح",
    "row", "id", "name", "phone", "mobile", "date", "amount", "total", "price", "cost", "qty", "description", "category",
)


def is_placeholder_col(col_name: Any) -> bool:
    s = normalize_persian(col_name)
    return (not s) or bool(_PLACEHOLDER_COL_RX.match(s))


def is_banner_header_col(col_name: Any) -> bool:
    s = normalize_persian(col_name)
    if not s:
        return True
    if len(s) > 42:
        return True
    if _BANNER_PHRASE_RX.search(s) or _DATE_OR_RANGE_RX.search(s):
        return True
    return False


def is_non_entity_value(val: Any) -> bool:
    """True if value is a date, date-range, pure number, phone, code, or banner sentence (NOT a teacher/group/vendor)."""
    s = normalize_persian(val)
    if not s or len(s) < 2:
        return True
    if _PURE_NUM_OR_CODE_RX.match(s):
        return True
    if _DATE_OR_RANGE_RX.search(s):
        return True
    if _BANNER_PHRASE_RX.search(s):
        return True
    # Reject phone numbers / national IDs
    digits_only = re.sub(r"\D", "", s)
    if len(digits_only) >= 7 and len(digits_only) >= len(s.replace(" ", "")) * 0.65:
        return True
    # Reject values with no letters at all
    if not re.search(r"[آ-یa-zA-Z]", s):
        return True
    return False


def is_valid_teacher_name(val: Any) -> bool:
    s = normalize_persian(val)
    if is_non_entity_value(s):
        return False
    if len(s) < 3 or len(s) > 165:
        return False
    low = s.lower()
    if low in ("ردیف", "نام", "نام خانوادگی", "شماره", "موبایل", "تلفن", "شماره موبایل", "شرح", "مبلغ", "تاریخ", "توضیحات", "نامشخص", "ناشناس", "ندارد"):
        return False
    return True


def _header_row_score(cells: list[Any]) -> tuple[float, int, int]:
    """Returns (score, keyword_hits, non_empty_short_text_count)."""
    non_empty = [normalize_persian(c) for c in cells if c is not None and str(c).strip() != ""]
    if len(non_empty) < 2:
        return 0.0, 0, len(non_empty)
    kw_hits = 0
    short_txt = 0
    pure_num = 0
    long_cells = 0
    for s in non_empty:
        if _PURE_NUM_OR_CODE_RX.match(s):
            pure_num += 1
            continue
        if len(s) > 40:
            long_cells += 1
            continue
        short_txt += 1
        low = s.lower()
        if any(k == low or (len(k) >= 3 and k in low) for k in KNOWN_HEADER_TOKENS):
            kw_hits += 1
    if pure_num > len(non_empty) * 0.5 or long_cells > len(non_empty) * 0.4:
        return 0.0, kw_hits, short_txt
    score = kw_hits * 3.0 + short_txt * 0.8 - pure_num * 1.5 - long_cells * 2.0
    return score, kw_hits, short_txt


def promote_banner_headers(cols: list[str], rows: list[tuple | list]) -> tuple[list[str], list[tuple], str]:
    """
    Detects Excel/tabular tables whose row 0 was a title/date banner (leaving col names as
    ['لیست حضور و غیاب ...', 'ستون_2', 'ستون_3', ...]) and promotes the true header row
    from rows[:8] cleanly while preserving the banner text as context metadata.
    """
    if not cols or not rows:
        return list(cols or []), [tuple(r) for r in (rows or [])], ""

    placeholder_cnt = sum(1 for c in cols if is_placeholder_col(c))
    banner_cnt = sum(1 for c in cols if is_banner_header_col(c))
    cur_score, cur_kw, _ = _header_row_score(cols)

    needs_scan = (
        placeholder_cnt >= max(1, int(len(cols) * 0.35))
        or banner_cnt >= 1
        or cur_kw == 0
    )
    if not needs_scan:
        return list(cols), [tuple(r) for r in rows], ""

    best_idx = -1
    best_score = cur_score
    best_kw = cur_kw
    scan_limit = min(8, len(rows))
    for i in range(scan_limit):
        sc, kw, stxt = _header_row_score(list(rows[i]))
        if kw >= 2 and sc > best_score + 1.5:
            best_score = sc
            best_kw = kw
            best_idx = i
        elif placeholder_cnt >= max(2, int(len(cols) * 0.45)) and best_idx == -1 and stxt >= 2 and sc >= 3.0:
            best_score = sc
            best_kw = kw
            best_idx = i

    if best_idx < 0:
        return list(cols), [tuple(r) for r in rows], ""

    # Gather banner text from original cols & rows above best_idx
    banner_parts: list[str] = []
    for c in cols:
        sc = normalize_persian(c)
        if sc and not is_placeholder_col(sc):
            banner_parts.append(sc)
    for r in rows[:best_idx]:
        for cell in r:
            sc = normalize_persian(cell)
            if sc and len(sc) >= 3:
                banner_parts.append(sc)
    banner_ctx = " | ".join(dict.fromkeys(banner_parts))

    # Build clean deduplicated column names from rows[best_idx]
    raw_hdr = list(rows[best_idx])
    new_cols: list[str] = []
    seen: dict[str, int] = {}
    for idx in range(len(cols)):
        raw_v = raw_hdr[idx] if idx < len(raw_hdr) else ""
        name = re.sub(r"\s+", " ", str(raw_v or "").replace("\r", " ").replace("\n", " ")).strip()
        if not name or name.lower() in ("none", "nan"):
            name = f"ستون_{idx + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        new_cols.append(name)

    rem_rows = [tuple(r) for r in rows[best_idx + 1:]]
    # Drop completely empty rows
    rem_rows = [r for r in rem_rows if any(v is not None and str(v).strip() != "" for v in r)]

    # Drop completely empty placeholder columns (e.g. trailing unnamed blank columns)
    keep_idxs = []
    for ci, cname in enumerate(new_cols):
        if not is_placeholder_col(cname):
            keep_idxs.append(ci)
        else:
            if any(ci < len(r) and r[ci] is not None and str(r[ci]).strip() != "" for r in rem_rows[:50]):
                keep_idxs.append(ci)
    if keep_idxs and len(keep_idxs) < len(new_cols):
        new_cols = [new_cols[i] for i in keep_idxs]
        rem_rows = [tuple(r[i] if i < len(r) else "" for i in keep_idxs) for r in rem_rows]

    return new_cols, rem_rows, banner_ctx


def extract_roster_banner_meta(banner_ctx: str, file_name: str = "", source_sheet: str = "") -> tuple[str, str]:
    """Extracts (course_title, teacher_name) from attendance sheet banners like 'لیست حضور و غیاب «در آستان امام هادی» ( استاد توران و نصیری )'."""
    combined = normalize_persian(f"{banner_ctx} {source_sheet} {Path(file_name).stem if file_name else ''}")
    course_title = ""
    teacher_name = ""

    # Extract teacher inside parentheses e.g. "( استاد توران و نصیری )" or "(جمعی از اساتید)"
    m_t = re.search(r"[\(\[]\s*([^)\]]{3,70})[\)\]]", combined)
    if m_t:
        inner = re.sub(r"\s+", " ", m_t.group(1)).strip()
        if any(k in inner for k in ("جمعی از اساتید", "گروهی از اساتید", "اساتید")):
            teacher_name = inner
        elif any(k in inner for k in ("استاد", "دکتر", "حجت", "آیت", "مدرس", "سخنران")):
            cand_t = re.sub(r"^(?:استاد|اساتید|مدرس|سخنران|ارائه\s*دهنده)\s*[:\-]?\s*", "", inner).strip()
            if is_valid_teacher_name(cand_t):
                teacher_name = cand_t

    # Extract course inside guillemets «...», else prefer descriptive source_sheet over file_name.stem
    m_c = re.search(r"«([^»]{3,90})»", combined)
    if m_c:
        course_title = m_c.group(1).strip()
    else:
        sh_clean = normalize_persian(source_sheet or "")
        sh_clean = re.sub(r"^\d+\s*[\-–—ـ.]\s*", "", sh_clean).strip()
        sh_stripped = re.sub(
            r"^(?:لیست\s+(?:حضور\s+و\s+غیاب\s+(?:نهایی\s+)?|حضوری\s+و\s+مجازی\s+)?(?:دوره\s+)?|فهرست\s+(?:حضور\s+و\s+غیاب\s+)?(?:دوره\s+)?)",
            "",
            sh_clean,
        ).strip()
        if len(sh_stripped) >= 3:
            sh_clean = sh_stripped
        is_generic_sh = (
            not sh_clean
            or len(sh_clean) < 3
            or bool(re.fullmatch(r"(?:sheet|برگه|شیت|جدول|table|page|صفحه)\s*\d*", sh_clean, re.IGNORECASE))
            or sh_clean.startswith("اسلاید ")
        )
        if not is_generic_sh:
            course_title = sh_clean
        elif file_name:
            stem = normalize_persian(Path(file_name).stem)
            stem = re.sub(r"^\d+\s*[\-–—ـ.]\s*", "", stem).strip()
            course_title = stem

    return course_title, teacher_name


_OPENING_BAL_RX = re.compile(
    r"^(?:مانده(?:\s*از)?\s*(?:ماه|دوره|سال|صفحه)?\s*قبل(?:ی)?|مانده\s*اول\s*دوره|"
    r"نقل\s*(?:از|به)\s*(?:صفحه|قبل|بعد)|موجودی\s*اول\s*دوره|افتتاحیه)\b"
)
_FUNDING_EXACT_RX = re.compile(
    r"^(?:تنخواه(?:\s*گردان)?|شارژ\s*تنخواه|واریز(?:ی)?\s*(?:تنخواه|وجه|نقدی|به\s*حساب|حساب)?|"
    r"دریافت(?:ی)?\s*(?:تنخواه|وجه|نقدی|از\s*حساب)?|تامین\s*تنخواه|افزایش\s*تنخواه|"
    r"برگشت\s*تنخواه|استرداد\s*تنخواه|تسویه\s*تنخواه|انتقال\s*وجه|وجه\s*تنخواه|تنخواه\s*(?:آبان|بهمن|مهر|دی|آذر|اسفند|فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|ماه)?)(?:\s*[\d۰-۹/\-()]*)$"
)


def classify_non_expense_row(item_text: Any) -> str:
    """
    Returns:
      - 'opening_balance' for carried-over balances like 'مانده از ماه قبل'
      - 'funding' for petty-cash top-ups/inflows like 'تنخواه', 'شارژ تنخواه', 'واریز تنخواه'
      - '' for genuine expenses (including purchases like 'خرید پذیرایی از تنخواه')
    """
    s = normalize_persian(item_text).strip(" :.-–—()[]،,")
    if not s:
        return ""
    if _OPENING_BAL_RX.search(s):
        return "opening_balance"
    # Genuine purchase phrases even if mentioning تنخواه must stay expenses
    if any(k in s for k in ("خرید", "پرداخت بابت", "بابت خرید", "کرایه", "پذیرایی", "چاپ", "حق التدریس", "تعمیر", "تجهیز", "هدیه", "ملزومات", "قبض", "اجاره")):
        return ""
    if _FUNDING_EXACT_RX.match(s):
        return "funding"
    if s.startswith(("شارژ تنخواه", "واریز تنخواه", "دریافت تنخواه", "دریافتی تنخواه", "تامین تنخواه", "افزایش تنخواه", "مانده تنخواه", "مانده از ماه", "مانده ماه قبل", "مانده دوره قبل")):
        return "funding" if "تنخواه" in s else "opening_balance"
    if re.search(r"^(?:کارمزد|هزینه\s*کارمزد)\s*(?:انتقال|بانکی|پایا|ساتنا|کارت\s*به\s*کارت|شبا|حواله)?\b", s):
        return "transfer_fee"
    return ""


def is_non_expense_accounting_row(item_text: Any) -> bool:
    return bool(classify_non_expense_row(item_text))


def clean_excel_cell_value(val: Any, font_name: str = "") -> Any:
    """Normalizes Wingdings checkmarks ('ü' -> '✓'), trims trailing whitespace."""
    if val is None:
        return ""
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return ""
        if "ü" in s or (font_name.lower() == "wingdings" and s == "ü"):
            s = s.replace("ü", "✓").strip()
            s = re.sub(r"([^\s✓])✓", r"\1 ✓", s)
        return s
    return val


def is_blank_numbered_row(values: list[Any]) -> bool:
    """True if a row ONLY has a row index (e.g. 48, 49, 50) and all other columns are empty."""
    non_empty = [(i, str(v).strip()) for i, v in enumerate(values) if v is not None and str(v).strip() not in ("", "nan", "None")]
    if not non_empty:
        return True
    if len(non_empty) == 1 and non_empty[0][0] == 0:
        s0 = normalize_persian(non_empty[0][1])
        if re.fullmatch(r"\d+(?:\.0)?", s0):
            return True
    return False


def detect_workgroup_unified(
    file_name: str,
    source_sheet: str,
    slide_text: str = "",
    sample_courses: str = "",
    banner_ctx: str = "",
) -> str:
    """Unified workgroup detector shared across BI Dashboard, Executive Analytics & Boardroom."""
    t_norm = normalize_persian(f"{slide_text} {banner_ctx}")
    t_norm = re.sub(r"(?:کارگروه\s+){2,}", "کارگروه ", t_norm)
    m = re.search(r"کارگروه\s+(دین\s*شناسی|فقه|تاریخ|قرآن|حدیث|[آ-یa-zA-Z0-9\s]{2,22})", t_norm)
    if m:
        wg = re.sub(r"\s+", " ", m.group(1)).strip()
        wg = re.sub(r"^کارگروه\s+", "", wg).strip()
        for stop in ("تربیت", "حدیث خوانی", "دوره", "سطح", "ردیف", "مخاطبین"):
            idx = wg.find(stop)
            if idx > 1:
                wg = wg[:idx].strip()
        if wg:
            return f"کارگروه {wg}"

    courses_norm = normalize_persian(f"{sample_courses} {banner_ctx} {source_sheet} {file_name}")
    courses_norm = re.sub(r"(?:کارگروه\s+){2,}", "کارگروه ", courses_norm)
    if "انس با الکافی" in t_norm or "انس با الکافی" in courses_norm or "انس با کافی" in courses_norm or "کتاب التوحید" in courses_norm:
        return "حدیث‌خوانی (انس با الکافی)"
    if (
        t_norm.count("تربیت سخنران و مبلغ") >= 2
        or "تربیت سخنران" in courses_norm
        or "تربیت مبلغ" in courses_norm
        or any(k in courses_norm for k in ("پرچم", "منبر", "خطابه", "آگاهی بخشی", "محرم", "فاطمیه"))
    ):
        return "تربیت سخنران و مبلغ"

    topic_map = (
        (("قرآن", "قران", "تفسیر", "تدبر", "قرائات", "مصحف", "بینامتنیت", "استنادهای قرآنی", "استناد های قرآنی", "تعدد"), "کارگروه قرآن"),
        (("حدیث", "بحار", "الکافی", "نهج البلاغه", "صحیفه", "نقل معنا", "نسخه پژوهی", "روایت", "روایی"), "کارگروه حدیث"),
        (("فقه", "اصول", "احکام", "اجتهاد", "تقلی", "استنباط", "رمز ارز", "رمزارز", "بورس", "ارتداد", "نوآوران"), "کارگروه فقه"),
        (("تاریخ", "سیره", "در آستان", "بر آستان", "برآستان", "تشیع", "ائمه", "سقیفه", "صحابه", "امامان شیعی", "کارگزاران", "جنگ ها", "پیامبر", "میراث تاریخی", "کتب تاریخی", "منبع شناسی"), "کارگروه تاریخ"),
        (("دین شناسی", "کلام", "عقاید", "اعتقادی", "اخلاق", "معارف", "فلسفه", "امامت", "هرمنوتیک", "کثرت", "تکثر", "شر و خداباوری", "تجربه دینی", "برداشت های", "مدرنیته", "استضعاف", "الهیات", "افعال خدا", "معرفت خدا"), "کارگروه دین شناسی"),
    )
    best_lbl = ""
    best_hits = 0
    for kws, label in topic_map:
        hits = sum(1 for kw in kws if kw in courses_norm)
        if hits > best_hits:
            best_hits = hits
            best_lbl = label
    if best_lbl:
        return best_lbl

    clean_sheet = re.sub(r"\s*\(جدول\s*\d+\)", "", str(source_sheet or "")).strip()
    if clean_sheet and not is_non_entity_value(clean_sheet) and clean_sheet.lower() not in ("sheet1", "sheet2", "نهایی", "جدول", "اسلاید"):
        if not any(tok in clean_sheet for tok in ("اسلاید", "جدول", "صفحه")):
            return clean_sheet
    return "دوره‌های عمومی"


# ==============================================================================
# Cross-Source Course Reconciliation Engine (Shared by BI & Executive Analytics)
# ==============================================================================
import difflib as _difflib

_COURSE_STOP_WORDS = frozenset({
    "در", "از", "به", "با", "و", "بر", "های", "ها", "قسمت", "مساله", "مسأله",
    "بازخوانی", "نگاهی", "دوره", "نشست", "کتاب", "دریچه", "موضوع", "شناسی",
    "ماهیت", "تخصصی", "کوتاه", "مدت", "نهایی", "کامل", "علیه", "علیهم", "السلام",
    "صلی", "الله", "اله", "سلم", "امام", "استان",
})
_PERSIAN_ORDINAL_PAIRS = (
    ("سیزدهم", "13"), ("دوازدهم", "12"), ("یازدهم", "11"), ("دهم", "10"),
    ("نهم", "9"), ("هشتم", "8"), ("هفتم", "7"), ("ششم", "6"),
    ("پنجم", "5"), ("چهارم", "4"), ("سوم", "3"), ("دوم", "2"), ("اول", "1"),
)
# Mutually exclusive named entities/books that MUST NEVER cross-match even if surrounding words match!
_DISTINCT_SUBJECT_MARKERS = (
    "هادی", "حسن عسکری", "سید افرینش", "امیر مومنان", "امیرمومنان", "فاطمیه", "محرم",
    "الکافی", "بحارالانوار", "بحار الانوار", "نهج البلاغه", "صحیفه",
    "التوحید", "العقل", "الایمان",
)


def _stem_course_tok(w: str) -> str:
    return re.sub(r"(?:های|ها|یی|ی)$", "", w) if len(w) > 4 else w


def _norm_course_for_match(title: Any) -> str:
    s = normalize_persian(title).replace("آ", "ا")
    if not s:
        return ""
    s = re.sub(r"\(دوره\s*\d+\)\s*$", "", s).strip()
    s = s.replace("پرچم داران", "پرچمداران").replace("ان سوی", "انسوی").replace("میراث تاریخی", "تاریخی").replace("بحار الانوار", "بحارالانوار")
    s = re.sub(
        r"^(?:لیست\s+(?:حضور\s+و\s+غیاب\s+(?:نهایی\s+)?|حضوری\s+و\s+مجازی\s+)?(?:دوره\s+)?|نشست\s+تخصصی\s+|نشست\s+|دوره\s+)",
        "",
        s,
    )
    s = re.sub(r"\s+(?:نهایی|کامل)$", "", s)
    # Strip punctuation/parentheses FIRST so '(قسمت یازدهم)' cleanly converts 'یازدهم' -> '11'!
    s = re.sub(r"[^\w\u0600-\u06FF]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not any(k in s for k in ("پرچمداران", "قسمت", "محرم", "الکافی", "التوحید")):
        s = re.sub(r"([^\s\d])\d+$", r"\1", s)
    for w_ord, d_ord in _PERSIAN_ORDINAL_PAIRS:
        s = re.sub(rf"(?:^|\s){w_ord}(?:$|\s)", f" {d_ord} ", s)
    return re.sub(r"\s+", " ", s).strip()


def _canon_wg_key(wg: Any) -> str:
    g = normalize_persian(wg).replace("آ", "ا")
    g = re.sub(r"^(?:کارگروه\s+)+", "", g).strip()
    ck = re.sub(r"\s+", "", g)
    if "انسباالکافی" in ck or "حدیثخوانی" in ck:
        return "انسباالکافی"
    if "سخنران" in ck or "مبلغ" in ck:
        return "سخنرانومبلغ"
    return ck


def _extract_subject_markers(norm_title: str) -> set[str]:
    found = set()
    for mk in _DISTINCT_SUBJECT_MARKERS:
        if mk in norm_title:
            found.add(mk)
    return found


def score_course_title_pair(
    roster_title: str,
    summary_title: str,
    roster_group: str = "",
    summary_group: str = "",
    roster_att: int | None = None,
    summary_att: int | None = None,
) -> float:
    """Computes [0..1] similarity between a roster course title and a summary course title."""
    na = _norm_course_for_match(roster_title)
    nb = _norm_course_for_match(summary_title)
    ca, cb = na.replace(" ", ""), nb.replace(" ", "")
    if not ca or not cb:
        return 0.0

    # Guard 1: Distinct named Imam/book/occasion markers MUST NOT cross-match (e.g. امام هادی != امام حسن عسکری)
    ma, mb = _extract_subject_markers(na), _extract_subject_markers(nb)
    if ma and mb and not (ma & mb):
        return 0.0

    # Guard 2: Distinct series numbers MUST NOT cross-match (e.g. قسمت 1 != قسمت 2)
    da, db = re.findall(r"\d+", na), re.findall(r"\d+", nb)
    if da and db and da != db:
        return 0.0
    series_pen = -0.18 if ((da and not db and da != ["1"]) or (db and not da and db != ["1"])) else 0.0

    wga, wgb = _canon_wg_key(roster_group), _canon_wg_key(summary_group)
    both_wg_known = bool(wga and wgb and "عمومی" not in wga and "عمومی" not in wgb)
    same_wg = (wga == wgb) if both_wg_known else True

    if ca == cb:
        base = 1.0
    elif len(ca) >= 6 and (cb.startswith(ca) or ca.startswith(cb)):
        base = 0.94
    else:
        ta = {_stem_course_tok(w) for w in na.split() if len(w) >= 2 and w not in _COURSE_STOP_WORDS}
        tb = {_stem_course_tok(w) for w in nb.split() if len(w) >= 2 and w not in _COURSE_STOP_WORDS}
        if not ta or not tb:
            return 0.0
        matched_a = 0
        for wa in ta:
            if wa in tb or any((wb.startswith(wa) or wa.startswith(wb)) for wb in tb if min(len(wa), len(wb)) >= 4):
                matched_a += 1
        if matched_a == 0:
            return 0.0
        cont = matched_a / max(1, min(len(ta), len(tb)))
        jacc = matched_a / max(1, len(ta) + len(tb) - matched_a)
        seq = _difflib.SequenceMatcher(None, ca, cb).ratio()
        base = max(seq, cont * 0.68 + jacc * 0.32)

    att_bonus = 0.0
    if roster_att and summary_att and roster_att > 0 and summary_att > 0:
        ratio = min(float(roster_att), float(summary_att)) / max(float(roster_att), float(summary_att))
        if ratio >= 0.80:
            att_bonus = 0.07
        elif ratio <= 0.45:
            att_bonus = -0.05

    wg_adj = (0.06 if (both_wg_known and same_wg) else (-0.18 if (both_wg_known and not same_wg) else 0.0))
    return round(max(0.0, min(0.999, base + wg_adj + series_pen + att_bonus)), 3)


def match_roster_to_summary_courses(
    roster_items: list[dict[str, Any]],
    summary_items: list[dict[str, Any]],
    min_score: float = 0.62,
) -> dict[Any, tuple[Any, float]]:
    """
    1-to-1 optimal matcher linking person-level roster courses to summary courses (PPTX / Excel summary).
    Each item dict needs: {'id', 'title', 'group', 'attendance'}.
    Returns {roster_id: (summary_id, confidence_score)}.
    """
    if not roster_items or not summary_items:
        return {}

    matched: dict[Any, tuple[Any, float]] = {}
    used_r: set[Any] = set()
    used_s: set[Any] = set()

    # Step 1: Ordered pairing for multi-part truncated Excel tab collisions like 'انس با الکافی؛کتاب التوحید (دوره 71)'
    series_buckets: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
    for ri in roster_items:
        t_raw = normalize_persian(ri.get("title") or "")
        m_num = re.search(r"\(دوره\s*(\d+)\)\s*$", t_raw)
        if m_num:
            base_t = t_raw[:m_num.start()].strip()
            sub_topic = re.split(r"[؛;:]", base_t)[-1].strip() if any(ch in base_t for ch in "؛;:") else base_t
            sub_key = re.sub(r"\s+", "", sub_topic.replace("آ", "ا"))
            if len(sub_key) >= 4:
                series_buckets.setdefault((sub_key, _canon_wg_key(ri.get("group") or "")), []).append((int(m_num.group(1)), ri))

    for (sub_key, wg_k), r_group_list in series_buckets.items():
        if len(r_group_list) < 2:
            continue
        r_group_list.sort(key=lambda x: x[0])
        s_cands = []
        for si in summary_items:
            if si["id"] in used_s:
                continue
            s_wg_k = _canon_wg_key(si.get("group") or "")
            if wg_k and s_wg_k and "عمومی" not in wg_k and "عمومی" not in s_wg_k and wg_k != s_wg_k:
                continue
            s_ck = re.sub(r"\s+", "", normalize_persian(si.get("title") or "").replace("آ", "ا"))
            if sub_key in s_ck:
                s_cands.append(si)
        if len(s_cands) >= 2:
            for (_, ri), si in zip(r_group_list, s_cands):
                matched[ri["id"]] = (si["id"], 0.99)
                used_r.add(ri["id"])
                used_s.add(si["id"])

    # Step 2: Best-first greedy matching for all remaining courses
    cands: list[tuple[float, Any, Any]] = []
    for ri in roster_items:
        if ri["id"] in used_r:
            continue
        for si in summary_items:
            if si["id"] in used_s:
                continue
            sc = score_course_title_pair(
                ri.get("title") or "",
                si.get("title") or "",
                ri.get("group") or "",
                si.get("group") or "",
                ri.get("attendance"),
                si.get("attendance"),
            )
            if sc >= min_score:
                cands.append((sc, ri["id"], si["id"]))

    cands.sort(key=lambda x: -x[0])
    for sc, rid, sid in cands:
        if rid in used_r or sid in used_s:
            continue
        matched[rid] = (sid, sc)
        used_r.add(rid)
        used_s.add(sid)

    return matched
