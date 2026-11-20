import json
import re
from collections import defaultdict
from typing import Any

import duckdb
import lancedb

from src.core.config import Config

PERSIAN_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

COLLECTIVE_KEYWORDS = (
    "جمعی از اساتید",
    "گروهی از اساتید",
    "اساتید",
    "ناشناس",
    "-",
)

EXPENSE_TAXONOMY: list[tuple[str, tuple[str, ...]]] = [
    ("پذیرایی و تشریفات", (
        "پذیرایی", "چای", "قهوه", "نسکافه", "دمنوش", "ناهار", "شام", "صبحانه",
        "غذا", "کترینگ", "رستوران", "میوه", "شیرینی", "کیک", "بستنی", "آب معدنی",
        "شربت", "نوشیدنی", "خوراکی", "سوپرمارکت", "نان", "خرما", "آجیل", "قند",
        "شکر", "لیوان", "ظروف یکبار", "یکبار مصرف", "سفره", "تشریفات", "تغذیه"
    )),
    ("تجهیزات و فناوری", (
        "تجهیز", "لپ تاپ", "لپتاپ", "کامپیوتر", "رایانه", "مانیتور", "نمایشگر",
        "میکروفون", "دوربین", "سه پایه", "پروژکتور", "ویدئو", "تلویزیون", "کابل",
        "هارد", "فلش", "رم", "پرینتر", "چاپگر", "اسکنر", "کولر", "اسپیکر", "باند",
        "صدا", "صوتی", "نور", "سخت افزار", "سیستم", "موبایل", "تبلت", "مودم",
        "روتر", "سوئیچ", "باتری", "شارژر", "آداپتور", "میز", "صندلی", "مبل",
        "تریبون", "وایت برد", "قفسه", "کمد", "وسایل", "دستگاه", "قطعه", "الکترونیک"
    )),
    ("چاپ، تبلیغات و انتشارات", (
        "چاپ", "بنر", "پوستر", "کتاب", "جزوه", "بروشور", "کاتالوگ", "پرینت",
        "فتوکپی", "کپی", "صحافی", "لمینت", "استند", "پلاکارد", "طراحی", "گرافیک",
        "کاغذ", "تونر", "کارتریج", "جوهر", "مهر", "پاکت", "سربرگ", "کارت ویزیت",
        "تبلیغ", "انتشارات", "نشر", "بج سینه", "پرچم"
    )),
    ("نوشت‌افزار و ملزومات اداری", (
        "خودکار", "مداد", "دفتر", "پوشه", "زونکن", "ماژیک", "منگنه", "سوزن",
        "چسب", "کلاسور", "لوازم التحریر", "نوشت افزار", "تحریر", "ملزومات",
        "اداری", "دستمال", "شوینده", "بهداشتی", "کیسه زباله", "مایع دستشویی", "تایپ"
    )),
    ("حق‌التدریس، پژوهش و هدایا", (
        "حق التدریس", "حق الزحمه", "استاد", "سخنران", "مدرس", "هدیه", "هدایا",
        "جایزه", "تقدیر", "لوح", "تندیس", "پژوهش", "تحقیق", "تدوین", "ویراستاری",
        "ترجمه", "فیلمبردار", "عکاس", "عکاسی", "صدابردار", "مجری", "پاداش", "دستمزد"
    )),
    ("ایاب‌وذهاب و حمل‌ونقل", (
        "اسنپ", "تپسی", "آژانس", "تاکسی", "بلیط", "بلیت", "قطار", "پرواز",
        "هواپیما", "اتوبوس", "بنزین", "سوخت", "حمل", "باربری", "پیک", "پست",
        "تیپاکس", "کرایه", "رفت و آمد", "ایاب", "ذهاب", "ماموریت", "سفر", "هتل", "اقامت"
    )),
    ("تأسیسات، تعمیرات و پشتیبانی", (
        "تعمیر", "سرویس", "برق", "لوله", "تاسیسات", "نقاشی", "نظافت", "اینترنت",
        "شارژ ساختمان", "قبض", "آب و برق", "گاز", "تلفن", "اجاره", "امنیت",
        "قفل", "کلید", "ابزار", "لامپ", "پریز", "سیم", "پشتیبانی", "هاست", "دامنه", "اشتراک"
    )),
]

FIN_AMOUNT_HINTS = (
    "مبلغ کل", "جمع کل", "بهای کل", "قیمت کل", "کل مبلغ", "مبلغ نهایی",
    "قابل پرداخت", "مبلغ", "هزینه", "قیمت", "جمع", "پرداختی", "بدهکار",
    "تومان", "ریال", "بها", "amount", "total", "cost", "price"
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
    s = norm_text(raw_date)
    if not s:
        return fallback
    # الگوی 1403/08/12 یا 1404-02-05
    m = re.search(r"(1[34]\d{2}|20\d{2})[/\-.](\d{1,2})", s)
    if m:
        return f"{m.group(1)}/{int(m.group(2)):02d}"
    # نام ماه شمسی + سال
    months = (
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
    )
    for idx, mn in enumerate(months, start=1):
        if mn in s:
            ym = re.search(r"1[34]\d{2}", s)
            return f"{ym.group(0)}/{idx:02d} ({mn})" if ym else mn
    return s[:16] if len(s) >= 4 else fallback


def categorize_expense(explicit_cat: str, item: str, vendor: str, file_name: str, sheet: str) -> str:
    exp_clean = re.sub(r"\s+", " ", str(explicit_cat or "")).strip()
    if exp_clean and exp_clean not in ("-", "—", "ندارد", "سایر", "متفرقه"):
        return exp_clean

    hay = norm_text(f"{item} {vendor} {sheet} {file_name}")
    for cat_name, keywords in EXPENSE_TAXONOMY:
        for kw in keywords:
            if kw in hay:
                return cat_name
    return "سایر هزینه‌ها"


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
    def _detect_workgroup(file_name: str, source_sheet: str, slide_text: str, sample_courses: str) -> str:
        t_norm = norm_text(slide_text)
        m = re.search(r"کارگروه\s+(دین\s*شناسی|فقه|تاریخ|قرآن|حدیث|[آ-یa-zA-Z0-9\s]{2,22})", t_norm)
        if m:
            wg = re.sub(r"\s+", " ", m.group(1)).strip()
            for stop in ("تربیت", "حدیث خوانی", "دوره", "سطح", "ردیف", "مخاطبین"):
                idx = wg.find(stop)
                if idx > 1:
                    wg = wg[:idx].strip()
            if wg:
                return f"کارگروه {wg}"

        if "انس با الکافی" in t_norm or "انس با الکافی" in norm_text(sample_courses) or "کتاب التوحید" in norm_text(sample_courses):
            return "حدیث‌خوانی (انس با الکافی)"

        courses_norm = norm_text(sample_courses)
        if t_norm.count("تربیت سخنران و مبلغ") >= 2 or any(k in courses_norm for k in ("پرچم", "منبر", "خطابه", "آگاهی بخشی")):
            return "تربیت سخنران و مبلغ"

        clean_sheet = re.sub(r"\s*\(جدول\s*\d+\)", "", str(source_sheet or "")).strip()
        return clean_sheet or file_name

    @staticmethod
    def _detect_finance_columns(columns: list[str], file_name: str, source_sheet: str) -> dict[str, str | None] | None:
        norm_cols = [(c, norm_text(c)) for c in columns]

        amount_col = None
        unit_price_col = None
        qty_col = None
        item_col = None
        cat_col = None
        vendor_col = None
        date_col = None
        inv_no_col = None

        # ابتدا ستون مبلغ کل را با اولویت بالا پیدا کن
        for hint in FIN_AMOUNT_HINTS:
            for orig, cn in norm_cols:
                if hint in cn and not any(u in cn for u in ("واحد", "فی")):
                    amount_col = orig
                    break
            if amount_col:
                break

        for orig, cn in norm_cols:
            if not unit_price_col and any(h in cn for h in FIN_UNIT_PRICE_HINTS):
                unit_price_col = orig
            elif not qty_col and any(h in cn for h in FIN_QTY_HINTS):
                qty_col = orig
            elif not inv_no_col and any(h in cn for h in FIN_INV_NO_HINTS):
                inv_no_col = orig
            elif not date_col and any(h in cn for h in FIN_DATE_HINTS):
                date_col = orig
            elif not vendor_col and any(h in cn for h in FIN_VENDOR_HINTS):
                vendor_col = orig
            elif not cat_col and any(h in cn for h in FIN_CAT_HINTS):
                cat_col = orig
            elif not item_col and any(h in cn for h in FIN_ITEM_HINTS):
                item_col = orig

        if not amount_col and not unit_price_col:
            return None

        # اگر نام ستون مبلغ خیلی کلی (مثل «جمع») بود، مطمئن شو جدول واقعا مالی است
        ctx = norm_text(f"{file_name} {source_sheet} {' '.join(columns)}")
        has_strong_fin_signal = any(
            k in ctx for k in ("مبلغ", "قیمت", "هزینه", "فاکتور", "فی", "تومان", "ریال", "خرید", "صورتحساب", "بودجه", "پرداخت", "مالی", "price", "cost", "amount", "invoice")
        )
        if not has_strong_fin_signal:
            return None

        if not item_col:
            for orig, cn in norm_cols:
                if orig not in (amount_col, unit_price_col, qty_col, date_col, inv_no_col) and "ردیف" not in cn:
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
        course_col = None
        teacher_col = None
        count_col = None
        for c in columns:
            cn = norm_text(c)
            if not course_col and any(k in cn for k in ("نام دوره", "عنوان", "دوره", "برنامه", "موضوع", "نشست")):
                course_col = c
            elif not teacher_col and any(k in cn for k in ("استاد", "مدرس", "سخنران", "مجری")):
                teacher_col = c
            elif not count_col and any(k in cn for k in ("شرکت", "تعداد", "مخاطب", "نفر", "آمار")):
                count_col = c
        return course_col, teacher_col, count_col

    @staticmethod
    def _q(col: str) -> str:
        return '"' + col.replace('"', '""') + '"'

    def get_analytics(self) -> dict[str, Any]:
        con = duckdb.connect(self.duckdb_path)
        try:
            tables_meta = con.execute("""
                SELECT table_name, file_name, source_sheet, rows_count, columns_json
                FROM tabular_catalog
                ORDER BY file_name, source_sheet
            """).fetchall()
        except Exception:
            con.close()
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
        universal_tables: list[dict[str, Any]] = []
        fin_files_found: set[str] = set()
        rial_votes = 0
        toman_votes = 0

        try:
            for tbl_name, file_name, source_sheet, rows_count, cols_json in tables_meta:
                cols = json.loads(cols_json or "[]")
                rc = int(rows_count or 0)
                if not cols or rc <= 0:
                    continue

                domain = "general"
                fin_map = self._detect_finance_columns(cols, file_name, source_sheet)

                if fin_map:
                    domain = "finance"
                    fin_files_found.add(file_name)
                    ctx_curr = norm_text(f"{file_name} {source_sheet} {' '.join(cols)}")
                    if "ریال" in ctx_curr:
                        rial_votes += 1
                    elif "تومان" in ctx_curr:
                        toman_votes += 1

                    # خواندن کل ستون‌های موردنیاز در یک کوئری
                    needed = [c for c in fin_map.values() if c]
                    uniq_cols = list(dict.fromkeys(needed))
                    sel_sql = ", ".join(self._q(c) for c in uniq_cols)
                    rows = con.execute(f'SELECT {sel_sql} FROM "{tbl_name}"').fetchall()
                    idx_map = {c: i for i, c in enumerate(uniq_cols)}

                    def get_v(row_tuple, key_name):
                        col_n = fin_map.get(key_name)
                        if not col_n:
                            return None
                        return row_tuple[idx_map[col_n]]

                    for row in rows:
                        item_txt = re.sub(r"\s+", " ", str(get_v(row, "item") or "")).strip()
                        # حذف ردیف‌های جمع کل پایین فاکتور برای جلوگیری از دوباره‌شماری
                        item_norm = norm_text(item_txt)
                        if item_norm in ("جمع", "جمع کل", "مجموع", "مجموع کل", "قابل پرداخت", "کل", "جمع نهایی", "تخفیف", "مالیات"):
                            continue

                        amt = parse_number(get_v(row, "amount"))
                        qty = parse_number(get_v(row, "qty"))
                        up = parse_number(get_v(row, "unit_price"))

                        if amt is None and up is not None:
                            amt = up * (qty if qty and qty > 0 else 1.0)
                        if amt is None or amt <= 0:
                            continue

                        vendor_txt = re.sub(r"\s+", " ", str(get_v(row, "vendor") or "")).strip()
                        date_txt = re.sub(r"\s+", " ", str(get_v(row, "date") or "")).strip()
                        inv_txt = re.sub(r"\s+", " ", str(get_v(row, "invoice_no") or "")).strip()
                        raw_cat = str(get_v(row, "category") or "")

                        if not item_txt:
                            item_txt = vendor_txt or inv_txt or f"قلم هزینه ({source_sheet})"

                        category = categorize_expense(raw_cat, item_txt, vendor_txt, file_name, source_sheet)
                        period = extract_period_label(date_txt, file_name)

                        fin_records.append({
                            "item": item_txt,
                            "category": category,
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

                        sel_cols = [self._q(course_col)]
                        sel_cols.append(self._q(teacher_col) if teacher_col else "''")
                        sel_cols.append(self._q(count_col))
                        rows = con.execute(f'SELECT {", ".join(sel_cols)} FROM "{tbl_name}"').fetchall()
                        sample_courses = " ".join(str(r[0] or "") for r in rows[:5])
                        workgroup = self._detect_workgroup(file_name, source_sheet, slide_txt, sample_courses)

                        for r in rows:
                            course_name = re.sub(r"\s+", " ", str(r[0] or "")).strip()
                            if not course_name or course_name in ("-", "جمع", "مجموع", "کل"):
                                continue
                            teacher_raw = clean_teacher_name(str(r[1] or ""))
                            num = parse_number(r[2])
                            participants = int(round(num)) if num is not None else None

                            t_norm = norm_text(teacher_raw)
                            is_collective = (
                                not teacher_raw
                                or any(k in t_norm for k in COLLECTIVE_KEYWORDS)
                                or "،" in teacher_raw
                                or " - " in teacher_raw
                                or "/" in teacher_raw
                            )
                            edu_records.append({
                                "course": course_name,
                                "teacher": teacher_raw or "ثبت‌نشده",
                                "teacher_key": teacher_group_key(teacher_raw) if not is_collective else "",
                                "is_collective": is_collective,
                                "participants": participants,
                                "workgroup": workgroup,
                                "file_name": file_name,
                                "source": str(source_sheet or ""),
                            })

                universal_tables.append({
                    "table_name": tbl_name,
                    "file_name": file_name,
                    "source_sheet": str(source_sheet or ""),
                    "rows_count": rc,
                    "columns": cols,
                    "domain": domain,
                })
        finally:
            con.close()

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
                "files": sorted(fin_files),
                "unit": currency_unit,
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

        con = duckdb.connect(self.duckdb_path)
        try:
            meta = con.execute(
                "SELECT file_name, source_sheet, rows_count, columns_json FROM tabular_catalog WHERE table_name = ?",
                [table_name],
            ).fetchone()
            if not meta:
                return {"ok": False, "error": "جدول در کاتالوگ یافت نشد."}

            cols = json.loads(meta[3] or "[]")
            rel = con.execute(f'SELECT * FROM "{table_name}" LIMIT {int(limit)}')
            raw_rows = rel.fetchall()

            # تشخیص خودکار ستون‌های عددی و دسته‌بندی
            numeric_cols: list[str] = []
            text_cols: list[str] = []
            for c_idx, c_name in enumerate(cols):
                sample_vals = [r[c_idx] for r in raw_rows[:40] if r[c_idx] is not None and str(r[c_idx]).strip() not in ("", "-")]
                if not sample_vals:
                    text_cols.append(c_name)
                    continue
                parsed_cnt = sum(1 for v in sample_vals if parse_number(v) is not None)
                if parsed_cnt >= max(1, int(len(sample_vals) * 0.65)) and "ردیف" not in norm_text(c_name):
                    numeric_cols.append(c_name)
                else:
                    text_cols.append(c_name)

            clean_rows = [["" if v is None else str(v) for v in r] for r in raw_rows]
            return {
                "ok": True,
                "table_name": table_name,
                "file_name": meta[0],
                "source_sheet": meta[1],
                "total_rows": int(meta[2] or len(clean_rows)),
                "columns": cols,
                "numeric_columns": numeric_cols,
                "text_columns": text_cols,
                "rows": clean_rows,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            con.close()