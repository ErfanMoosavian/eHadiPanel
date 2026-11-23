import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb
import lancedb

from src.core.config import Config
from src.core.db_manager import (
    classify_non_expense_row,
    clean_excel_cell_value,
    canonical_teacher_core,
    clean_participant_name,
    detect_workgroup_unified,
    get_db_lock,
    is_banner_header_col,
    is_blank_numbered_row,
    is_summary_row_smart,
    match_roster_to_summary_courses,
    parse_jalali_date,
    parse_number_strict,
    promote_banner_headers,
)
from src.core.memory_engine import _clean_for_compare, load_brain_config, resolve_canonical_map, split_joint_names

PERSIAN_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

COLLECTIVE_KEYWORDS = (
    "جمعی از اساتید",
    "گروهی از اساتید",
    "اساتید",
    "ناشناس",
    "-",
)

EXPENSE_CATEGORIES: tuple[str, ...] = (
    "ایاب‌وذهاب و حمل‌ونقل",
    "پذیرایی و تشریفات",
    "چاپ، تبلیغات و انتشارات",
    "تجهیزات، فناوری و سامانه‌های مجازی",
    "تأسیسات، تعمیرات و پشتیبانی",
    "نوشت‌افزار و ملزومات اداری",
    "حق‌التدریس، پژوهش و هدایا",
    "سایر هزینه‌ها",
)

SMART_EXPENSE_RULES: list[tuple[str, list[tuple[str, float, bool]]]] = [
    ("ایاب‌وذهاب و حمل‌ونقل", [
        (r"\bاسنپ\b|اسنپ\s+", 10.0, True),
        (r"\bتپسی\b|پول\s*راننده|حق\s*راننده|آژانس|تاکسی", 10.0, True),
        (r"حمل\s*و\s*نقل|حمل\s*ونقل|باربری|پیک\b|تیپاکس|پست\b", 9.5, True),
        (r"رفت\s*و\s*برگشت|رفت\s*وبرگشت|رفت\s+استاد|برگشت\s+استاد|ایاب\s*و\s*ذهاب|ایاب\s*ذهاب", 9.0, True),
        (r"بلیت|بلیط|قطار|پرواز|هواپیما|اتوبوس|بنزین|سوخت|هتل|اقامت|ماموریت|سفر\b", 8.0, True),
        (r"کرایه(?!\s*(?:صندلی|میز|میکروفون|سالن|تجهیز|سیستم|باند|چادر|ساختمان))", 7.0, True),
    ]),
    ("تأسیسات، تعمیرات و پشتیبانی", [
        (r"شیر\s*آب|آب\s*شیرین\s*کن|تصفیه\s*آب|فیلتر\s*آب|ممبران", 9.5, True),
        (r"قبض\s*(?:برق|آب|گاز|تلفن)|شارژ\s*ساختمان|اجاره\s*(?:ساختمان|مکان|سالن|دفتر)", 9.5, True),
        (r"تعمیر|سرویس\s*(?:کولر|پکیج|ساختمان)|لوله\s*کشی|برق\s*کشی|قفل\b|کلید\b|نقاشی|نظافت|لامپ|پریز|سیم\b|تاسیسات", 8.0, True),
    ]),
    ("چاپ، تبلیغات و انتشارات", [
        (r"کاوه\s*نگار|سامانه\s*پیامک|پیامک|پنل\s*پیامک|تبلیغ|تبلیغات", 9.5, True),
        (r"نصب\s*پوستر|چاپ\s*گواهی|چاپ\s*بنر|بنر\b|پوستر\b|استند\b|پلاکارد", 9.5, True),
        (r"کپی\b|فتوکپی|پرینت|چاپ\b|صحافی|لمینت|بروشور|کاتالوگ|جزوه|انتشارات|نشر\b|سربرگ|کارت\s*ویزیت|مهر\b|بج\s*سینه|پرچم", 8.5, True),
        (r"مجازی\s*دوره|تبلیغ\s*مجازی|اطلاع\s*رسانی", 7.5, True),
    ]),
    ("تجهیزات، فناوری و سامانه‌های مجازی", [
        (r"الو\s*کام|الوکام|سامانه\s*مجازی|ادوبی\s*کانکت|اسکای\s*روم|زوم\b|اینترنت|هاست|دامنه|سرور|اشتراک\s*(?:نرم|سایت|هوش)", 9.5, True),
        (r"کرایه\s*(?:صندلی|میز|میکروفون|باند|صوت|تجهیز)|اجاره\s*(?:تجهیز|صندلی|میکروفون|صوت)", 9.0, True),
        (r"باتری\s*موبایل|تعمیر\s*موبایل|لپ\s*تاپ|لپتاپ|کامپیوتر|رایانه|مانیتور|پرینتر|چاپگر|اسکنر|دوربین|سه\s*پایه|پروژکتور", 8.5, True),
        (r"میکروفون|اسپیکر|باند\b|تجهیزات|تجهیز|صندلی|میز\b|مبل|تریبون|وایت\s*برد|قفسه|کمد|کولر|مودم|روتر|هارد|فلش|کابل|شارژر|آداپتور", 7.5, False),
        (r"موبایل|تبلت|باتری|سیستم\b|سخت\s*افزار|الکترونیک|صوتی", 4.5, False),
    ]),
    ("پذیرایی و تشریفات", [
        (r"پذیرایی\s*دوره|کیک\s*یزدی|شیرینی\s*کشمشی|کترینگ|رستوران|تشریفات|تغذیه", 9.5, True),
        (r"میوه\b|شیرینی|کیک\b|خیار|گوجه|سالاد|ناهار|نهار|شام\b|صبحانه|غذا\b|نان\b|پنیر|کره\b|خرما|آجیل|بستنی", 8.5, True),
        (r"چای\b|قهوه|نسکافه|دمنوش|آب\s*معدنی|شربت|نوشیدنی|قند\b|شکر\b|لیوان|ظروف\s*یکبار|یکبار\s*مصرف|سفره", 8.0, True),
        (r"\bشیر\b(?!\s*آب|ین)", 8.0, True),
        (r"پذیرایی", 5.5, False),
    ]),
    ("نوشت‌افزار و ملزومات اداری", [
        (r"کاغذ\s*a4|کاغذ\b|لوازم\s*التحریر|نوشت\s*افزار|ملزومات\s*اداری", 8.5, True),
        (r"ماژیک|خودکار|مداد|دفتر\b|پوشه|زونکن|کلاسور|منگنه|سوزن|چسب\s*زخم|چسب\b|پاکت\s*زباله|کیسه\s*زباله|دستمال|شوینده|بهداشتی|مایع\s*دستشویی|تونر|کارتریج|جوهر", 8.0, True),
    ]),
    ("حق‌التدریس، پژوهش و هدایا", [
        (r"حق\s*التدریس|حق\s*الزحمه|حق\s*تحقیق|دستمزد|پاداش|تقدیر|لوح\s*تقدیر|تندیس|هدیه|هدایا|جایزه", 9.5, True),
        (r"پژوهش|تحقیق|تدوین|ویراستار|ترجمه|فیلمبردار|عکاس|عکاسی|صدابردار|مجری\b", 8.0, True),
    ]),
]

SECTION_CATEGORY_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("پذیرایی", "تشریفات", "تغذیه"), "پذیرایی و تشریفات"),
    (("تبلیغ", "تبلیغات", "اطلاع رسانی", "رسانه", "چاپ"), "چاپ، تبلیغات و انتشارات"),
    (("حمایت", "ایاب", "حمل", "تردد", "رفت و برگشت"), "ایاب‌وذهاب و حمل‌ونقل"),
    (("تجهیز", "فناوری", "سامانه"), "تجهیزات، فناوری و سامانه‌های مجازی"),
    (("تاسیسات", "تعمیر", "ساختمان", "پشتیبانی"), "تأسیسات، تعمیرات و پشتیبانی"),
    (("حق التدریس", "پژوهش", "هدایا"), "حق‌التدریس، پژوهش و هدایا"),
    (("ملزومات", "نوشت افزار", "اداری"), "نوشت‌افزار و ملزومات اداری"),
]

FIN_AMOUNT_HINTS = (
    "مبلغ کل", "جمع کل", "بهای کل", "قیمت کل", "کل مبلغ", "مبلغ نهایی",
    "قابل پرداخت", "مبلغ هزینه", "مبلغ فاکتور", "مبلغ پرداختی",
    "بدهکار", "برداشت", "هزینه", "مبلغ", "پرداختی", "پرداخت", "خرج", "خروجی",
    "بستانکار", "واریز", "تنخواه", "قیمت", "جمع", "تومان", "ریال", "بها",
    "amount", "total", "cost", "price", "debit", "credit", "expense",
)
FIN_UNIT_PRICE_HINTS = ("قیمت واحد", "بهای واحد", "فی", "نرخ", "مبلغ واحد", "unit price")
FIN_QTY_HINTS = ("تعداد", "مقدار", "وزن", "متراژ", "qty", "quantity", "count")
FIN_ITEM_HINTS = ("شرح", "نام کالا", "کالا", "عنوان", "موضوع", "بابت", "خدمت", "آیتم", "توضیح", "اقلام", "item", "desc")
FIN_CAT_HINTS = ("دسته", "سرفصل", "نوع هزینه", "ردیف بودجه", "گروه هزینه", "بخش", "کارگروه", "category")
FIN_VENDOR_HINTS = ("فروشنده", "فروشگاه", "تامین", "طرف حساب", "ذینفع", "مرکز خرید", "پرداخت به", "شخص", "شرکت", "vendor", "supplier")
FIN_DATE_HINTS = ("تاریخ", "ماه", "سال", "زمان", "روز", "date")
FIN_INV_NO_HINTS = ("شماره فاکتور", "فاکتور", "شماره سند", "شماره رسید", "invoice")


def norm_text(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).translate(PERSIAN_TO_EN)
    s = (
        s.replace("ي", "ی")
        .replace("ك", "ک")
        .replace("ة", "ه")
        .replace("اللّه", "الله")
        .replace("\u200c", " ")
    )
    return re.sub(r"\s+", " ", s).strip()


_SHORT_TOKEN_RX_CACHE: dict[str, re.Pattern] = {}


def _has_fin_token(text: str, tok: str) -> bool:
    """Matches short/ambiguous tokens like 'فی', 'بها', 'برداشت' on word boundaries so 'الکافی' NEVER matches 'فی'."""
    if not text or not tok:
        return False
    if len(tok) <= 3 or tok in ("بها", "نرخ", "خرج", "جمع", "برداشت", "واریز"):
        rx = _SHORT_TOKEN_RX_CACHE.get(tok)
        if rx is None:
            rx = re.compile(rf"(?:^|[\s\-_/()،,.:;])({re.escape(tok)})(?:$|[\s\-_/()،,.:;])")
            _SHORT_TOKEN_RX_CACHE[tok] = rx
        return bool(rx.search(text))
    return tok in text


def _is_person_roster_columns(norm_cols: list[str]) -> bool:
    has_person = any(
        any(k in cn for k in ("نام و نام خانوادگی", "نام خانوادگی", "نام شرکت کننده", "شرکت کننده", "نام دانش پژوه", "دانش پژوه", "نام و فامیل", "طلبه", "فراگیر"))
        for cn in norm_cols
    )
    has_id_or_phone = any(
        any(k in cn for k in ("موبایل", "همراه", "تلفن", "شماره تماس", "کد ملی", "کدملی", "گذرنامه", "پاسپورت", "کد فراگیر", "فیدا", "آمایش", "phone", "mobile", "passport", "fida", "cnic"))
        for cn in norm_cols
    )
    return has_person and has_id_or_phone


def _is_edu_dashboard_summary(norm_cols: list[str], source_sheet: str = "") -> bool:
    sh_n = norm_text(source_sheet)
    if any(k in sh_n for k in ("داشبورد آماری", "کارنامه جامع", "خلاصه کارگروه")):
        return True
    has_wg = any("نام کارگروه" in cn or cn == "کارگروه" for cn in norm_cols)
    has_edu_metrics = sum(
        1 for k in ("تعداد دوره", "مجموع ثبت نام", "افراد یکتا", "مجموع جلسات", "میانگین جلسات", "تعداد کارگروه", "تعداد کل دوره")
        if any(k in cn for cn in norm_cols)
    ) >= 2
    return has_wg and has_edu_metrics


def _is_wg_course_matrix(norm_cols: list[str]) -> bool:
    return (
        _is_person_roster_columns(norm_cols)
        and any(any(k in cn for k in ("شرح دوره", "جزئیات کل دوره", "کارگروه های فعال")) for cn in norm_cols)
        and len(norm_cols) >= 7
    )


def _clean_course_sheet_title(sheet_name: str) -> tuple[str, str]:
    raw = norm_text(sheet_name)
    m = re.match(r"^(\d+)\s*[\-–—ـ.]\s*(.+)$", raw)
    num, title = (m.group(1).strip(), m.group(2).strip()) if m else ("", raw)
    stripped = re.sub(
        r"^(?:لیست\s+(?:حضور\s+و\s+غیاب\s+(?:نهایی\s+)?|حضوری\s+و\s+مجازی\s+)?(?:دوره\s+)?|فهرست\s+(?:حضور\s+و\s+غیاب\s+)?(?:دوره\s+)?)",
        "",
        title,
    ).strip()
    return num, (stripped if len(stripped) >= 3 else title)


def _canon_bi_wg_name(raw_wg: str) -> str:
    g = norm_text(raw_wg)
    g = re.sub(r"^(?:کارگروه\s+)+", "کارگروه ", g).strip()
    ck = re.sub(r"[\s\u200c()\-_.:،,؛;]+", "", g.replace("آ", "ا"))
    mapping = {
        "فقه": "کارگروه فقه",
        "کارگروهفقه": "کارگروه فقه",
        "دینشناسی": "کارگروه دین شناسی",
        "کارگروهدینشناسی": "کارگروه دین شناسی",
        "تاریخ": "کارگروه تاریخ",
        "کارگروهتاریخ": "کارگروه تاریخ",
        "قران": "کارگروه قرآن",
        "کارگروهقران": "کارگروه قرآن",
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
    return mapping.get(ck, g or "دوره‌های عمومی")


def parse_number(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).translate(PERSIAN_TO_EN)
    s = s.replace(",", "").replace("٬", "").replace("،", "").strip()
    if not s or s in ("-", "—", "–", "ندارد", "ثبت نشده"):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def clean_teacher_name(raw: str) -> str:
    s = re.sub(r"\s+", " ", str(raw or "").replace("\n", " / ")).strip()
    s = s.replace("حجت الاسلام و المسلمین", "حجت‌الاسلام والمسلمین")
    s = s.replace("حجت الاسلام والمسلمین", "حجت‌الاسلام والمسلمین")
    s = s.replace("آیت اللّه", "آیت‌الله").replace("آیت الله", "آیت‌الله")
    return re.sub(r"\s+", " ", s).strip()


def teacher_group_key(name: str) -> str:
    s = norm_text(name)
    for prefix in (
        "حجت الاسلام و المسلمین",
        "حجت الاسلام والمسلمین",
        "حجج الاسلام و المسلمین",
        "حجج الاسلام والمسلمین",
        "آیت الله",
        "دکتر",
        "استاد",
        ":",
    ):
        s = s.replace(prefix, " ")
    return re.sub(r"\s+", " ", s).strip()


def extract_period_label(raw_date: str, fallback: str) -> str:
    jd = parse_jalali_date(raw_date, fallback_text=fallback)
    if jd.get("is_parsed"):
        if jd["year"] and jd["month"]:
            return f"{jd['year']}/{jd['month']:02d} ({jd['month_name']})"
        if jd["canonical"]:
            return jd["canonical"]
    s = norm_text(raw_date)
    return s[:16] if len(s) >= 4 else fallback


def categorize_expense_smart(
    explicit_cat: str,
    item: str,
    vendor: str,
    file_name: str,
    sheet: str,
    section_hint: str = "",
    learned_rules: dict[str, str] | None = None,
) -> dict[str, Any]:
    item_norm = norm_text(item)
    rules_map = learned_rules or {}

    if item_norm and rules_map:
        if item_norm in rules_map:
            return {"category": rules_map[item_norm], "confidence": 1.0, "needs_review": False, "candidates": [rules_map[item_norm]], "reason": "یادگیری‌شده از تأیید کاربر"}
        for rk, rcat in rules_map.items():
            rk_n = norm_text(rk)
            if rk_n and (rk_n == item_norm or (len(rk_n) >= 5 and rk_n in item_norm)):
                return {"category": rcat, "confidence": 0.99, "needs_review": False, "candidates": [rcat], "reason": "یادگیری‌شده از حافظه سامانه"}

    exp_clean = re.sub(r"\s+", " ", str(explicit_cat or "")).strip()
    if exp_clean and exp_clean not in ("-", "—", "ندارد", "سایر", "متفرقه", "بدون فاکتور"):
        return {"category": exp_clean, "confidence": 0.96, "needs_review": False, "candidates": [exp_clean], "reason": "ثبت‌شده در ستون سرفصل فایل"}

    hay = norm_text(f"{item} {vendor}").lower()
    sec_norm = norm_text(section_hint).lower()

    scores: dict[str, float] = {}
    for cat_name, patterns in SMART_EXPENSE_RULES:
        best_w = 0.0
        bonus = 0.0
        for pat, weight, _is_primary in patterns:
            if re.search(pat, hay):
                if weight > best_w:
                    best_w = weight
                else:
                    bonus += weight * 0.12
        if best_w > 0:
            scores[cat_name] = round(best_w + min(bonus, 2.0), 2)

    sec_cat = ""
    if sec_norm and "بدون فاکتور" not in sec_norm:
        for kws, cname in SECTION_CATEGORY_HINTS:
            if any(k in sec_norm for k in kws):
                sec_cat = cname
                break
    if sec_cat:
        if not scores:
            scores[sec_cat] = 6.5
        elif sec_cat in scores:
            scores[sec_cat] = round(scores[sec_cat] + 2.5, 2)
        else:
            scores[sec_cat] = 3.5

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not ranked:
        return {
            "category": "سایر هزینه‌ها",
            "confidence": 0.30,
            "needs_review": True,
            "candidates": list(EXPENSE_CATEGORIES),
            "reason": "کلیدواژه قطعی برای این قلم یافت نشد؛ لطفاً سرفصل دقیق آن را مشخص کنید.",
        }

    top_cat, top_sc = ranked[0]
    second_cat, second_sc = ranked[1] if len(ranked) > 1 else ("", 0.0)

    has_conflict = bool(second_cat) and second_sc >= 4.0 and (top_sc - second_sc) <= 6.0
    is_weak = top_sc < 7.0
    needs_review = has_conflict or is_weak

    cands = [c for c, _ in ranked[:4]]
    for fallback_c in EXPENSE_CATEGORIES:
        if fallback_c not in cands:
            cands.append(fallback_c)

    if has_conflict:
        reason = f"تداخل معنایی بین «{top_cat}» و «{second_cat}» — پیشنهاد هوشمند: «{top_cat}»"
        conf = round(min(0.84, max(0.55, top_sc / (top_sc + second_sc))), 2)
    elif is_weak:
        reason = f"تشخیص بر اساس بخش «{section_hint or 'متن'}» — برای دقت بیشتر تأیید کنید"
        conf = 0.68
    else:
        reason = "تشخیص قطعی"
        conf = 0.95

    return {
        "category": top_cat,
        "confidence": conf,
        "needs_review": needs_review,
        "candidates": cands[:6],
        "reason": reason,
    }


def categorize_expense(explicit_cat: str, item: str, vendor: str, file_name: str, sheet: str) -> str:
    return categorize_expense_smart(explicit_cat, item, vendor, file_name, sheet)["category"]


class BIDashboardEngine:
    """موتور هوش تجاری چنددامنه (آموزشی + مالی/تدارکات + کاوشگر پویا) روی DuckDB و LanceDB"""

    def __init__(self):
        self.duckdb_path = str(Config.DUCKDB_PATH)
        self.lancedb_path = str(Config.LANCEDB_PATH)

    def _load_chunks(self) -> list[dict[str, Any]]:
        try:
            db = lancedb.connect(self.lancedb_path)
            if "document_chunks" not in db.table_names():
                return []
            return db.open_table("document_chunks").to_pandas().to_dict(orient="records")
        except Exception:
            return []

    @staticmethod
    def _detect_workgroup(file_name: str, source_sheet: str, slide_text: str, sample_courses: str, banner_ctx: str = "") -> str:
        return detect_workgroup_unified(file_name, source_sheet, slide_text, sample_courses, banner_ctx)

    @staticmethod
    def _detect_finance_columns(
        columns: list[str],
        file_name: str,
        source_sheet: str,
        banner_ctx: str = "",
        sample_rows: list[tuple] | None = None,
    ) -> dict[str, str | None] | None:
        norm_cols = [(c, norm_text(c)) for c in columns]
        only_norm = [cn for _, cn in norm_cols]

        if _is_edu_dashboard_summary(only_norm, source_sheet) or _is_wg_course_matrix(only_norm):
            return None

        is_roster = _is_person_roster_columns(only_norm)
        if is_roster:
            is_edu_roster = any(any(k in cn for k in ("جلسه", "جلسات", "دوره", "کارگروه", "شهریه", "سطح", "پایه", "حضور")) for cn in only_norm)
            if is_edu_roster:
                return None
            explicit_expense = any(
                any(k in cn for k in ("مبلغ فاکتور", "مبلغ هزینه", "بدهکار", "بستانکار", "فاکتور", "شماره فاکتور"))
                for cn in only_norm
            )
            if not explicit_expense:
                return None

        amount_col = None
        unit_price_col = None
        qty_col = None
        item_col = None
        cat_col = None
        vendor_col = None
        date_col = None
        inv_no_col = None

        for hint in FIN_AMOUNT_HINTS:
            for orig, cn in norm_cols:
                if any(u in cn for u in ("واحد", "فی", "مانده", "شماره", "کد", "موبایل", "تلفن", "گذرنامه", "پاسپورت", "فراگیر", "فیدا", "آمایش", "جلسه", "جلسات", "دوره", "شرح", "نوع", "عنوان", "بابت", "سرفصل", "دسته", "گروه")):
                    continue
                if hint in ("برداشت", "واریز", "جمع", "بها") and len(cn.split()) >= 3:
                    continue
                if _has_fin_token(cn, hint):
                    amount_col = orig
                    break
            if amount_col:
                break

        for orig, cn in norm_cols:
            if not unit_price_col and any(_has_fin_token(cn, h) for h in FIN_UNIT_PRICE_HINTS) and len(cn.split()) <= 3:
                unit_price_col = orig
            elif not qty_col and any(_has_fin_token(cn, h) for h in FIN_QTY_HINTS):
                qty_col = orig
            elif not inv_no_col and any(h in cn for h in FIN_INV_NO_HINTS):
                inv_no_col = orig
            elif not date_col and any(_has_fin_token(cn, h) for h in FIN_DATE_HINTS) and len(cn.split()) <= 3:
                date_col = orig
            elif not vendor_col and any(_has_fin_token(cn, h) for h in FIN_VENDOR_HINTS) and len(cn.split()) <= 3:
                vendor_col = orig
            elif not cat_col and any(_has_fin_token(cn, h) for h in FIN_CAT_HINTS) and len(cn.split()) <= 3:
                cat_col = orig
            elif not item_col and any(h in cn for h in FIN_ITEM_HINTS):
                item_col = orig

        ctx = norm_text(f"{file_name} {source_sheet} {banner_ctx} {' '.join(c for c in columns if len(norm_text(c).split()) <= 3)}")
        strong_fin_tokens = (
            "مبلغ", "قیمت", "هزینه", "فاکتور", "فی", "تومان", "ریال", "خرید",
            "صورتحساب", "صورت حساب", "بودجه", "پرداخت", "مالی", "بدهکار", "بستانکار",
            "برداشت", "واریز", "تنخواه", "خرج", "حسابداری", "تراکنش", "price", "cost", "amount", "invoice"
        )
        has_strong_fin_signal = any(_has_fin_token(ctx, k) for k in strong_fin_tokens)

        if not amount_col and not unit_price_col and has_strong_fin_signal and sample_rows and not is_roster:
            best_col = None
            best_score = -1.0
            for ci, (orig, cn) in enumerate(norm_cols):
                if any(bad in cn for bad in ("ردیف", "شماره", "کد", "تاریخ", "مانده", "موبایل", "تلفن", "سال", "گذرنامه", "پاسپورت", "فراگیر")):
                    continue
                nums = []
                for r in sample_rows[:60]:
                    if ci < len(r):
                        v = parse_number(r[ci])
                        if v is not None and v > 0:
                            nums.append(v)
                if len(nums) >= 2:
                    big_cnt = sum(1 for x in nums if x >= 1000)
                    sc = big_cnt * 3.0 + len(nums)
                    if big_cnt >= 1 and sc > best_score:
                        best_score = sc
                        best_col = orig
            if best_col:
                amount_col = best_col

        if not amount_col and not unit_price_col:
            return None
        if not has_strong_fin_signal:
            return None

        if not item_col:
            for orig, cn in norm_cols:
                if orig not in (amount_col, unit_price_col, qty_col, date_col, inv_no_col) and not any(b in cn for b in ("ردیف", "مانده", "شماره")):
                    item_col = orig
                    break

        return {
            "amount": amount_col,
            "unit_price": unit_price_col,
            "qty": qty_col,
            "item": item_col,
            "category": cat_col,
            "vendor": vendor_col,
            "date": date_col,
            "invoice_no": inv_no_col,
        }

    @staticmethod
    def _detect_education_columns(columns: list[str]) -> tuple[str | None, str | None, str | None]:
        norm_set = [norm_text(c) for c in columns]
        # Attendance roster (نام + نام خانوادگی + موبایل) is person-level, not a summary courses table
        if _is_person_roster_columns(norm_set) or _is_edu_dashboard_summary(norm_set):
            return None, None, None
        course_col = None
        teacher_col = None
        count_col = None
        for c in columns:
            if is_banner_header_col(c):
                continue
            cn = norm_text(c)
            if not course_col and any(k in cn for k in ("نام دوره", "عنوان دوره", "عنوان", "دوره", "برنامه", "موضوع", "نشست")):
                course_col = c
            elif not teacher_col and any(k in cn for k in ("استاد", "مدرس", "سخنران", "مجری")):
                teacher_col = c
            elif not count_col and any(k in cn for k in ("شرکت", "تعداد", "دانش پژوه", "مخاطب", "نفر", "آمار")):
                count_col = c
        return course_col, teacher_col, count_col

    @staticmethod
    def _q(col: str) -> str:
        return '"' + col.replace('"', '""') + '"'

    def get_analytics(self) -> dict[str, Any]:
        _bcfg = load_brain_config(self.duckdb_path)
        _t_alias = resolve_canonical_map("teacher", self.duckdb_path)
        _lk = get_db_lock(self.duckdb_path)
        _lk.acquire()
        con = None
        try:
            con = duckdb.connect(self.duckdb_path)
        except Exception:
            _lk.release()
            return {
                "ok": True,
                "education": {"has_data": False, "records": [], "workgroups": []},
                "finance": {"has_data": False, "records": [], "categories": [], "unit": "تومان", "unstructured_hints": []},
                "universal": {"tables": []},
            }
        try:
            tables_meta = con.execute("""
                SELECT table_name, file_name, source_sheet, rows_count, columns_json
                FROM tabular_catalog
                ORDER BY file_name, source_sheet
            """).fetchall()
        except Exception:
            con.close()
            _lk.release()
            return {
                "ok": True,
                "education": {"has_data": False, "records": [], "workgroups": []},
                "finance": {"has_data": False, "records": [], "categories": [], "unit": "تومان", "unstructured_hints": []},
                "universal": {"tables": []},
            }

        chunks = self._load_chunks()
        slide_texts: dict[tuple[str, str], str] = {}
        unstructured_invoice_hints: list[dict[str, str]] = []
        seen_hint_files: set[str] = set()

        for r in chunks:
            fn = str(r.get("file_name") or "")
            loc = norm_text(r.get("location") or "")
            txt = str(r.get("content") or "")
            slide_texts[(fn, loc)] = txt
            tn = norm_text(f"{fn} {txt[:600]}")
            if fn not in seen_hint_files and any(k in tn for k in ("فاکتور", "صورتحساب", "جمع فاکتور", "مبلغ قابل پرداخت", "تومان", "ریال")):
                seen_hint_files.add(fn)
                unstructured_invoice_hints.append({"file_name": fn, "location": str(r.get("location") or "")})

        edu_records: list[dict[str, Any]] = []
        fin_records: list[dict[str, Any]] = []
        funding_total = 0.0
        opening_balance_total = 0.0
        funding_count = 0
        transfer_fee_total = 0.0
        learned_fin_rules: dict[str, str] = dict(_bcfg.get("finance_category_rules") or {})
        review_map: dict[str, dict[str, Any]] = {}
        universal_tables: list[dict[str, Any]] = []
        fin_files_found: set[str] = set()
        rial_votes = 0
        toman_votes = 0

        try:
            preloaded_tables: list[tuple[str, str, str, list[str], list[tuple], str]] = []
            course_wg_map: dict[str, str] = {}
            roster_clean_counts: dict[str, int] = defaultdict(int)
            has_raw_course_rosters = False

            for tbl_name, file_name, source_sheet, rows_count, cols_json in tables_meta:
                raw_cols = json.loads(cols_json or "[]")
                rc = int(rows_count or 0)
                if not raw_cols or rc <= 0:
                    continue
                try:
                    raw_rows = con.execute(f'SELECT * FROM "{tbl_name}"').fetchall()
                except Exception:
                    continue
                if not raw_rows:
                    continue
                cols, clean_rows, banner_ctx = promote_banner_headers(raw_cols, raw_rows)
                if not cols or not clean_rows:
                    continue
                preloaded_tables.append((tbl_name, file_name, str(source_sheet or ""), cols, clean_rows, banner_ctx))

                only_n = [norm_text(c) for c in cols]
                if _is_wg_course_matrix(only_n):
                    wg_lbl = _canon_bi_wg_name(str(source_sheet or ""))
                    for ci_m, cn_m in enumerate(only_n):
                        if ci_m < 6:
                            continue
                        if any(skip in cn_m for skip in ("ردیف", "نام", "موبایل", "تعداد", "مجموع", "شرح", "جزئیات", "کارگروه")):
                            continue
                        c_key = re.sub(r"\s+", "", norm_text(cols[ci_m]).replace("آ", "ا"))
                        if c_key:
                            course_wg_map[c_key] = wg_lbl
                elif _is_person_roster_columns(only_n) and not _is_edu_dashboard_summary(only_n, str(source_sheet or "")):
                    has_raw_course_rosters = True
                    _, c_clean = _clean_course_sheet_title(str(source_sheet or ""))
                    if c_clean:
                        roster_clean_counts[re.sub(r"\s+", "", c_clean.replace("آ", "ا"))] += 1

            for tbl_name, file_name, source_sheet, cols, clean_rows, banner_ctx in preloaded_tables:
                col_idx_map = {c: i for i, c in enumerate(cols)}
                only_n = [norm_text(c) for c in cols]

                domain = "general"
                fin_map = self._detect_finance_columns(cols, file_name, source_sheet, banner_ctx=banner_ctx, sample_rows=clean_rows)

                if fin_map:
                    domain = "finance"
                    fin_files_found.add(file_name)
                    ctx_curr = norm_text(f"{file_name} {source_sheet} {banner_ctx} {' '.join(cols)}")
                    if "ریال" in ctx_curr:
                        rial_votes += 1
                    elif "تومان" in ctx_curr:
                        toman_votes += 1

                    def get_v(row_tuple, key_name):
                        col_n = fin_map.get(key_name)
                        if not col_n or col_n not in col_idx_map:
                            return None
                        ci = col_idx_map[col_n]
                        return row_tuple[ci] if ci < len(row_tuple) else None

                    # تشخیص هوشمند ستون هزینه واقعی در برابر ستون واریزی/تنخواه (در دفاتر دو ستونه بدهکار/بستانکار یا برداشت/واریز)
                    expense_col = fin_map.get("amount")
                    inflow_col = None
                    if expense_col:
                        an = norm_text(expense_col)
                        paired_col = None
                        for c_cand in cols:
                            if c_cand == expense_col:
                                continue
                            cn = norm_text(c_cand)
                            if (
                                ("بدهکار" in an and "بستانکار" in cn)
                                or ("بستانکار" in an and "بدهکار" in cn)
                                or ("برداشت" in an and "واریز" in cn)
                                or ("واریز" in an and "برداشت" in cn)
                                or ("پرداخت" in an and "دریافت" in cn)
                                or ("دریافت" in an and "پرداخت" in cn)
                            ):
                                paired_col = c_cand
                                break

                        if paired_col and paired_col in col_idx_map:
                            pn = norm_text(paired_col)
                            if ("واریز" in an or "دریافت" in an) and ("برداشت" in pn or "پرداخت" in pn):
                                inflow_col, expense_col = expense_col, paired_col
                            elif ("برداشت" in an or "پرداخت" in an) and ("واریز" in pn or "دریافت" in pn):
                                inflow_col = paired_col
                            else:
                                # بدهکار vs بستانکار: با بررسی محتوای واقعی ردیف‌ها (تنخواه/مانده در برابر خرید و هزینه) ستون درست را انتخاب کن
                                c1_exp, c1_inf = 0, 0
                                c2_exp, c2_inf = 0, 0
                                ci1, ci2 = col_idx_map[expense_col], col_idx_map[paired_col]
                                for r_chk in clean_rows:
                                    if is_summary_row_smart(list(r_chk)):
                                        continue
                                    it_chk = re.sub(r"\s+", " ", str(get_v(r_chk, "item") or "")).strip()
                                    cls_chk = classify_non_expense_row(it_chk)
                                    v1 = parse_number(r_chk[ci1] if ci1 < len(r_chk) else None)
                                    v2 = parse_number(r_chk[ci2] if ci2 < len(r_chk) else None)
                                    if v1 is not None and v1 > 0:
                                        if cls_chk:
                                            c1_inf += 1
                                        else:
                                            c1_exp += 1
                                    if v2 is not None and v2 > 0:
                                        if cls_chk:
                                            c2_inf += 1
                                        else:
                                            c2_exp += 1
                                # ستونی که ردیف‌های هزینه بیشتری دارد (و تنخواه/مانده در آن کمتر است) ستون هزینه واقعی است
                                if (c2_exp - c2_inf * 2) > (c1_exp - c1_inf * 2):
                                    inflow_col, expense_col = expense_col, paired_col
                                else:
                                    inflow_col = paired_col

                    fee_col = next((c for c in cols if any(k in norm_text(c) for k in ("کارمزد", "commission", "fee"))), None)
                    # Determine dominant Jalali year/month from dated rows in this sheet so undated rows (e.g. 'بدون فاکتور')
                    # merge into '1403/11 (بهمن)' instead of creating an orphan 'بهمن' bar!
                    sheet_period_counts: dict[str, int] = defaultdict(int)
                    for r_dt in clean_rows:
                        d_raw = re.sub(r"\s+", " ", str(get_v(r_dt, "date") or "")).strip()
                        if d_raw:
                            jd_p = parse_jalali_date(d_raw)
                            if jd_p.get("is_parsed") and jd_p.get("year") and jd_p.get("month"):
                                sheet_period_counts[f"{jd_p['year']}/{jd_p['month']:02d} ({jd_p['month_name']})"] += 1
                    dominant_sheet_period = (
                        sorted(sheet_period_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                        if sheet_period_counts
                        else ""
                    )
                    current_section = ""
                    no_invoice_section = False

                    for row in clean_rows:
                        if is_blank_numbered_row(list(row)):
                            continue
                        item_txt = re.sub(r"\s+", " ", str(get_v(row, "item") or "")).strip()
                        item_norm = norm_text(item_txt)
                        if is_summary_row_smart(list(row)) or item_norm in ("جمع", "جمع کل", "مجموع", "مجموع کل", "قابل پرداخت", "کل", "جمع نهایی", "تخفیف", "مالیات") or item_norm.startswith("امضا"):
                            continue

                        inf_v = parse_number(row[col_idx_map[inflow_col]] if (inflow_col and inflow_col in col_idx_map and col_idx_map[inflow_col] < len(row)) else None)
                        amt = parse_number(row[col_idx_map[expense_col]] if (expense_col and expense_col in col_idx_map and col_idx_map[expense_col] < len(row)) else None)
                        qty = parse_number(get_v(row, "qty"))
                        up = parse_number(get_v(row, "unit_price"))
                        fee_v = parse_number(row[col_idx_map[fee_col]] if (fee_col and fee_col in col_idx_map and col_idx_map[fee_col] < len(row)) else None)

                        if item_txt and (amt is None or amt <= 0) and (inf_v is None or inf_v <= 0) and (up is None or up <= 0):
                            if "بدون فاکتور" in item_norm:
                                no_invoice_section = True
                                current_section = ""
                            elif len(item_norm) <= 36:
                                current_section = item_txt
                                no_invoice_section = False
                            continue

                        row_kind = classify_non_expense_row(item_txt)

                        if inf_v is not None and inf_v > 0:
                            if row_kind == "opening_balance":
                                opening_balance_total += float(inf_v)
                            else:
                                funding_total += float(inf_v)
                                funding_count += 1

                        if fee_v is not None and fee_v > 0:
                            transfer_fee_total += float(fee_v)

                        if amt is None and up is not None:
                            amt = up * (qty if qty and qty > 0 else 1.0)
                        if amt is None or amt <= 0:
                            continue

                        if row_kind == "opening_balance":
                            opening_balance_total += float(amt)
                            continue
                        if row_kind == "funding":
                            funding_total += float(amt)
                            funding_count += 1
                            continue
                        if row_kind == "transfer_fee":
                            transfer_fee_total += float(amt)
                            continue

                        vendor_txt = re.sub(r"\s+", " ", str(get_v(row, "vendor") or "")).strip()
                        date_txt = re.sub(r"\s+", " ", str(get_v(row, "date") or "")).strip()
                        inv_txt = re.sub(r"\s+", " ", str(get_v(row, "invoice_no") or "")).strip()
                        raw_cat = str(get_v(row, "category") or "")

                        if not item_txt:
                            item_txt = vendor_txt or inv_txt or f"قلم هزینه ({source_sheet})"

                        cls_res = categorize_expense_smart(
                            raw_cat,
                            item_txt,
                            vendor_txt,
                            file_name,
                            source_sheet,
                            section_hint=current_section,
                            learned_rules=learned_fin_rules,
                        )
                        category = cls_res["category"]
                        period = extract_period_label(date_txt, dominant_sheet_period or f"{file_name} {banner_ctx}")

                        if cls_res["needs_review"]:
                            rk = item_norm or item_txt
                            rm = review_map.setdefault(rk, {
                                "item": item_txt,
                                "item_key": rk,
                                "suggested_category": category,
                                "candidates": cls_res["candidates"],
                                "reason": cls_res["reason"],
                                "confidence": cls_res["confidence"],
                                "count": 0,
                                "total_amount": 0.0,
                                "files": set(),
                            })
                            rm["count"] += 1
                            rm["total_amount"] += float(amt)
                            rm["files"].add(file_name)

                        fin_records.append({
                            "item": item_txt,
                            "item_key": item_norm or item_txt,
                            "category": category,
                            "confidence": cls_res["confidence"],
                            "needs_review": bool(cls_res["needs_review"]),
                            "review_reason": cls_res["reason"],
                            "section": current_section,
                            "no_invoice": no_invoice_section,
                            "transfer_fee": round(float(fee_v), 2) if (fee_v is not None and fee_v > 0) else 0.0,
                            "amount": round(float(amt), 2),
                            "qty": round(float(qty), 2) if qty is not None else 1,
                            "unit_price": round(float(up), 2) if up is not None else None,
                            "vendor": vendor_txt or "ثبت‌نشده",
                            "date": date_txt or "—",
                            "period": period,
                            "invoice_no": inv_txt or "—",
                            "file_name": file_name,
                            "source": str(source_sheet or ""),
                        })
                else:
                    if _is_edu_dashboard_summary(only_n, source_sheet):
                        domain = "education"
                    elif _is_wg_course_matrix(only_n):
                        domain = "education"
                        if not has_raw_course_rosters:
                            wg_lbl = _canon_bi_wg_name(source_sheet)
                            for ci_m in range(6, len(cols)):
                                c_hdr = norm_text(cols[ci_m])
                                if not c_hdr or any(sk in c_hdr for sk in ("شرح", "مجموع", "تعداد", "کارگروه")):
                                    continue
                                reg_cnt = 0
                                for r in clean_rows:
                                    if ci_m < len(r):
                                        v_m = parse_number_strict(r[ci_m])
                                        if v_m is not None:
                                            reg_cnt += 1
                                if reg_cnt > 0:
                                    edu_records.append({
                                        "course": c_hdr, "teacher": "ثبت‌نشده", "teachers": [],
                                        "holding_mode": "گروهی", "teacher_key": "",
                                        "is_collective": True, "is_joint": False,
                                        "participants": reg_cnt, "workgroup": wg_lbl,
                                        "file_name": file_name, "source": str(source_sheet or ""), "row_index": ci_m,
                                    })
                    elif _is_person_roster_columns(only_n):
                        domain = "education"
                        c_num, c_clean = _clean_course_sheet_title(source_sheet)
                        if not c_clean or len(c_clean) < 3 or re.fullmatch(r"(?:sheet|برگه|شیت)\s*\d*", c_clean, re.IGNORECASE):
                            _, c_clean = _clean_course_sheet_title(Path(file_name).stem)
                        c_key = re.sub(r"\s+", "", c_clean.replace("آ", "ا"))
                        display_title = f"{c_clean} (دوره {c_num})" if (c_num and roster_clean_counts.get(c_key, 0) > 1) else (c_clean or source_sheet or file_name)
                        workgroup = course_wg_map.get(c_key) or _canon_bi_wg_name(self._detect_workgroup(file_name, source_sheet, "", c_clean, banner_ctx))

                        ci_ph = next((i for i, cn in enumerate(only_n) if any(k in cn for k in ("موبایل", "همراه", "تلفن", "phone", "mobile"))), -1)
                        ci_id = next((i for i, cn in enumerate(only_n) if any(k in cn for k in ("کد ملی", "کدملی", "گذرنامه", "پاسپورت", "فراگیر", "فیدا", "آمایش", "passport"))), -1)
                        ci_nm = next((i for i, cn in enumerate(only_n) if any(k in cn for k in ("نام شرکت کننده", "نام و نام خانوادگی", "شرکت کننده", "نام خانوادگی", "نام"))), -1)
                        ci_ses = next((i for i, cn in enumerate(only_n) if any(k in cn for k in ("تعداد جلسات", "جلسات", "جلسه", "sessions"))), -1)
                        seen_keys: set[str] = set()
                        valid_cnt = 0
                        active_cnt = 0
                        for r in clean_rows:
                            if is_blank_numbered_row(list(r)) or is_summary_row_smart(list(r)):
                                continue
                            nm_v = clean_participant_name(r[ci_nm] if (ci_nm >= 0 and ci_nm < len(r)) else "")
                            ph_v = re.sub(r"\D", "", norm_text(r[ci_ph] if (ci_ph >= 0 and ci_ph < len(r)) else ""))
                            id_v = re.sub(r"[^A-Za-z0-9]", "", norm_text(r[ci_id] if (ci_id >= 0 and ci_id < len(r)) else "")).upper()
                            if not nm_v and not ph_v and not id_v:
                                continue
                            nm_ck = re.sub(r"\s+", "", nm_v.replace("آ", "ا"))
                            rk = f"{nm_ck}|{ph_v or id_v}" if (ph_v or id_v) else nm_ck
                            if rk in seen_keys:
                                continue
                            seen_keys.add(rk)
                            valid_cnt += 1
                            if ci_ses >= 0 and ci_ses < len(r):
                                sv = parse_number_strict(r[ci_ses])
                                if sv is not None and sv > 0:
                                    active_cnt += 1
                        if valid_cnt > 0:
                            edu_records.append({
                                "course": display_title, "teacher": "ثبت‌نشده", "teachers": [],
                                "holding_mode": "گروهی", "teacher_key": "",
                                "is_collective": True, "is_joint": False,
                                "participants": valid_cnt, "active_participants": active_cnt if ci_ses >= 0 else valid_cnt,
                                "workgroup": workgroup,
                                "file_name": file_name, "source": str(source_sheet or ""), "row_index": 1,
                                "_from_roster": True,
                            })
                    else:
                        course_col, teacher_col, count_col = self._detect_education_columns(cols)
                        if course_col and count_col:
                            domain = "education"
                            base_loc = norm_text(str(source_sheet or "").split("(")[0])
                            slide_txt = slide_texts.get((file_name, base_loc), "")
                            if not slide_txt:
                                for (fn, loc), txt in slide_texts.items():
                                    if fn == file_name and base_loc and base_loc in loc:
                                        slide_txt = txt
                                        break

                            ci_c = col_idx_map[course_col]
                            ci_t = col_idx_map[teacher_col] if teacher_col in col_idx_map else -1
                            ci_n = col_idx_map[count_col]
                            ci_g = next(
                                (
                                    i for i, cn in enumerate(only_n)
                                    if i not in (ci_c, ci_t, ci_n)
                                    and any(k in cn for k in ("کارگروه", "گروه موضوعی", "گروه علمی", "حوزه موضوعی", "بخش", "department", "group"))
                                ),
                                -1,
                            )
                            sample_courses = " ".join(str(r[ci_c] or "") for r in clean_rows[:5] if ci_c < len(r))
                            workgroup = _canon_bi_wg_name(self._detect_workgroup(file_name, source_sheet, slide_txt, sample_courses))

                            for r_idx, r in enumerate(clean_rows, start=1):
                                if is_summary_row_smart(list(r)):
                                    continue
                                course_name = re.sub(r"\s+", " ", str(r[ci_c] if ci_c < len(r) else "")).strip()
                                if not course_name or course_name in ("-", "جمع", "مجموع", "کل", "جمع کل", "مجموع کل"):
                                    continue
                                row_g_raw = norm_text(r[ci_g] if (ci_g >= 0 and ci_g < len(r)) else "")
                                row_wg = _canon_bi_wg_name(row_g_raw) if (row_g_raw and row_g_raw not in ("-", "ندارد", "نامشخص")) else workgroup
                                teacher_raw = clean_teacher_name(str(r[ci_t] if (ci_t >= 0 and ci_t < len(r)) else ""))
                                num = parse_number_strict(r[ci_n] if ci_n < len(r) else None)
                                participants = int(round(num)) if num is not None else None
                                mode, parts = split_joint_names(teacher_raw, "teacher", _bcfg)
                                is_collective = (mode == "گروهی")
                                resolved_teachers = [_t_alias.get(_clean_for_compare(pt, "teacher", _bcfg), pt) for pt in parts] if not is_collective else []
                                primary_t = resolved_teachers[0] if len(resolved_teachers) == 1 else (" و ".join(resolved_teachers) if resolved_teachers else (teacher_raw or "ثبت‌نشده"))
                                edu_records.append({
                                    "course": course_name, "teacher": primary_t, "teachers": resolved_teachers,
                                    "holding_mode": mode, "teacher_key": _clean_for_compare(resolved_teachers[0], "teacher", _bcfg) if len(resolved_teachers) == 1 else "",
                                    "is_collective": is_collective, "is_joint": (mode == "مشترک"),
                                    "participants": participants, "workgroup": row_wg,
                                    "file_name": file_name, "source": str(source_sheet or ""), "row_index": r_idx,
                                })
                universal_tables.append({
                    "table_name": tbl_name,
                    "file_name": file_name,
                    "source_sheet": str(source_sheet or ""),
                    "rows_count": len(clean_rows),
                    "columns": cols,
                    "domain": domain,
                })
        finally:
            con.close()
            _lk.release()

        # هم‌ترازی چندمنبعی دوره‌ها در داشبورد BI (جلوگیری از دوبارشماری هنگام وجود هم‌زمان پاورپوینت و اکسل فهرست افراد)
        roster_bi = [(idx, r) for idx, r in enumerate(edu_records) if r.get("_from_roster")]
        summary_bi = [(idx, r) for idx, r in enumerate(edu_records) if not r.get("_from_roster")]
        if roster_bi and summary_bi:
            r_in = [{"id": idx, "title": r["course"], "group": r["workgroup"], "attendance": r.get("participants")} for idx, r in roster_bi]
            s_in = [{"id": idx, "title": r["course"], "group": r["workgroup"], "attendance": r.get("participants")} for idx, r in summary_bi]
            bi_pairs = match_roster_to_summary_courses(r_in, s_in, min_score=0.62)
            drop_r_idxs: set[int] = set()
            for r_idx, (s_idx, _sc) in bi_pairs.items():
                r_rec = edu_records[r_idx]
                s_rec = edu_records[s_idx]
                if s_rec.get("participants") is None and r_rec.get("participants") is not None:
                    s_rec["participants"] = r_rec["participants"]
                if r_rec.get("active_participants") is not None:
                    s_rec["active_participants"] = r_rec["active_participants"]
                drop_r_idxs.add(r_idx)
            if drop_r_idxs:
                edu_records = [r for idx, r in enumerate(edu_records) if idx not in drop_r_idxs]
        for r in edu_records:
            r.pop("_from_roster", None)

        _bi_t_disp: dict[str, str] = {}
        for r in edu_records:
            for tn in (r.get("teachers") or []):
                core = canonical_teacher_core(tn)
                if not core:
                    continue
                prev = _bi_t_disp.get(core)
                if not prev or (len(tn) > len(prev) and "ئ" not in tn) or ("ئ" in prev and "ئ" not in tn):
                    _bi_t_disp[core] = tn
        if _bi_t_disp:
            for r in edu_records:
                if r.get("teachers"):
                    new_ts = []
                    seen_c: set[str] = set()
                    for tn in r["teachers"]:
                        core = canonical_teacher_core(tn)
                        if core and core not in seen_c:
                            seen_c.add(core)
                            new_ts.append(_bi_t_disp.get(core, tn))
                    r["teachers"] = new_ts
                    if len(new_ts) == 1:
                        r["teacher"] = new_ts[0]
                    elif len(new_ts) > 1:
                        r["teacher"] = " و ".join(new_ts)

        # مرتب‌سازی کارگروه‌های آموزشی
        wg_totals: dict[str, int] = defaultdict(int)
        for rec in edu_records:
            wg_totals[rec["workgroup"]] += int(rec["participants"] or 0)
        workgroups = sorted(wg_totals.keys(), key=lambda w: wg_totals[w], reverse=True)

        # مرتب‌سازی سرفصل‌های مالی
        cat_totals: dict[str, float] = defaultdict(float)
        fin_files: set[str] = set()
        for rec in fin_records:
            cat_totals[rec["category"]] += float(rec["amount"] or 0)
            fin_files.add(rec["file_name"])
        categories = sorted(cat_totals.keys(), key=lambda c: cat_totals[c], reverse=True)

        currency_unit = "ریال" if (rial_votes > toman_votes) else "تومان"
        # فقط اسناد متنی فاکتوری که هنوز جدول مالی‌شان استخراج نشده
        pending_hints = [h for h in unstructured_invoice_hints if h["file_name"] not in fin_files_found]

        return {
            "ok": True,
            "education": {
                "has_data": len(edu_records) > 0,
                "records": edu_records,
                "workgroups": workgroups,
            },
            "finance": {
                "has_data": len(fin_records) > 0,
                "records": fin_records,
                "categories": categories,
                "all_categories": list(EXPENSE_CATEGORIES),
                "files": sorted(fin_files),
                "unit": currency_unit,
                "funding_total": round(funding_total, 2),
                "opening_balance_total": round(opening_balance_total, 2),
                "funding_count": funding_count,
                "transfer_fee_total": round(transfer_fee_total, 2),
                "needs_review_items": sorted(
                    [
                        {
                            "item": v["item"],
                            "item_key": v["item_key"],
                            "suggested_category": v["suggested_category"],
                            "candidates": v["candidates"],
                            "reason": v["reason"],
                            "confidence": v["confidence"],
                            "count": v["count"],
                            "total_amount": round(v["total_amount"], 2),
                            "files": sorted(v["files"]),
                        }
                        for v in review_map.values()
                    ],
                    key=lambda x: -x["total_amount"],
                ),
                "unstructured_hints": pending_hints[:6],
            },
            "universal": {
                "tables": universal_tables,
            },
        }

    def get_table_dynamic_data(self, table_name: str, limit: int = 500) -> dict[str, Any]:
        """بارگذاری مستقیم هر جدول از DuckDB برای تحلیل پویا در لنز کاوشگر"""
        if not re.fullmatch(r"tbl_[a-f0-9]+", str(table_name or "")):
            return {"ok": False, "error": "نام جدول نامعتبر است."}

        with get_db_lock(self.duckdb_path):
            return self._get_table_dynamic_data_locked(table_name, limit)

    def _get_table_dynamic_data_locked(self, table_name: str, limit: int = 500) -> dict[str, Any]:
        con = duckdb.connect(self.duckdb_path)
        try:
            meta = con.execute(
                "SELECT file_name, source_sheet, rows_count, columns_json FROM tabular_catalog WHERE table_name = ?",
                [table_name],
            ).fetchone()
            if not meta:
                return {"ok": False, "error": "جدول در کاتالوگ یافت نشد."}

            raw_cols = json.loads(meta[3] or "[]")
            rel = con.execute(f'SELECT * FROM "{table_name}" LIMIT {int(limit)}')
            raw_rows = rel.fetchall()

            cols, promoted_rows, banner_ctx = promote_banner_headers(raw_cols, raw_rows)

            # تشخیص هوشمند ستون‌های عددی تحلیلی (حذف ردیف متوالی، موبایل، کد ملی، شماره سند، سال و تاریخ)
            non_metric_hdr_hints = ("ردیف", "شماره", "موبایل", "همراه", "تلفن", "کد ملی", "کدملی", "گذرنامه", "پاسپورت", "فراگیر", "فیدا", "آمایش", "کد", "تاریخ", "سال", "id", "phone", "mobile", "passport", "fida", "cnic")
            numeric_cols: list[str] = []
            text_cols: list[str] = []
            for c_idx, c_name in enumerate(cols):
                cn = norm_text(c_name).lower()
                sample_vals = [
                    r[c_idx] for r in promoted_rows[:50]
                    if c_idx < len(r) and r[c_idx] is not None and str(r[c_idx]).strip() not in ("", "-", "—")
                ]
                if not sample_vals:
                    text_cols.append(c_name)
                    continue

                # Never classify row-index, phone, national-id, or date columns as numeric metrics
                if any(h in cn for h in non_metric_hdr_hints):
                    text_cols.append(c_name)
                    continue

                # Check phone-like values (09xxxxxxxxx)
                phone_like = sum(1 for v in sample_vals if re.fullmatch(r"0?9\d{9}", re.sub(r"\D", "", norm_text(v))))
                if phone_like >= max(2, int(len(sample_vals) * 0.5)):
                    text_cols.append(c_name)
                    continue

                parsed_vals = [parse_number(v) for v in sample_vals]
                valid_nums = [x for x in parsed_vals if x is not None]
                # Check if column is just sequential row numbers (1, 2, 3, 4, ...)
                is_seq_index = (
                    len(valid_nums) >= 4
                    and all(abs(valid_nums[k] - round(valid_nums[k])) < 1e-6 for k in range(min(8, len(valid_nums))))
                    and all(valid_nums[k + 1] - valid_nums[k] == 1 for k in range(min(5, len(valid_nums) - 1)))
                )
                if len(valid_nums) >= max(1, int(len(sample_vals) * 0.65)) and not is_seq_index:
                    numeric_cols.append(c_name)
                else:
                    text_cols.append(c_name)

            # Prioritize true analytical metrics (مبلغ/هزینه/بدهکار/شرکت‌کننده/ساعت) before binary/session columns
            def _metric_priority(cname: str) -> int:
                cn = norm_text(cname).lower()
                if any(k in cn for k in ("مبلغ", "بدهکار", "بستانکار", "هزینه", "قیمت", "جمع", "برداشت", "واریز", "شرکت", "مخاطب", "تعداد", "ساعت")):
                    return 0
                if re.search(r"\d{2}/\d{2}", cn):
                    return 2
                return 1
            numeric_cols.sort(key=_metric_priority)

            clean_rows = [
                ["" if (v is None or str(v).lower() == "nan") else str(clean_excel_cell_value(v)).strip() for v in r]
                for r in promoted_rows
                if not is_blank_numbered_row(list(r))
            ]
            return {
                "ok": True,
                "table_name": table_name,
                "file_name": meta[0],
                "source_sheet": meta[1],
                "banner_title": banner_ctx,
                "total_rows": len(clean_rows),
                "columns": cols,
                "numeric_columns": numeric_cols,
                "text_columns": text_cols,
                "rows": clean_rows,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            con.close()