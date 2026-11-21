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
    r"total|grand\s*total|subtotal|sum|average)$",
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
        FA_DIGITS + AR_DIGITS + "\u064a\u0643\u0623\u0625\u0629\u0624" + ZWNJ,
        EN_DIGITS + EN_DIGITS + "\u06cc\u06a9\u0627\u0627\u0647\u0648 ",
    )
    s = s.translate(trans)
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

        yr_m = re.search(r"\b(13\d{2}|14\d{2})\b", s)
        yr_s = yr_m.group(1) if yr_m else ""
        for idx, mname in enumerate(JALALI_MONTHS, start=1):
            if mname in s:
                return {
                    "year": yr_s, "month": idx, "day": 0,
                    "month_name": mname, "season": month_to_season(idx),
                    "canonical": f"{yr_s}/{idx:02d}" if yr_s else mname, "is_parsed": True,
                }

        for sname, months_t in JALALI_SEASONS.items():
            if sname in s:
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
