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
    detect_workgroup_unified,
    extract_roster_banner_meta,
    is_blank_numbered_row,
    is_banner_header_col,
    is_non_entity_value,
    is_valid_teacher_name,
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


def is_junk_label(label: str) -> bool:
    low = normalize_fa(label).lower()
    if not low or len(low) < 2:
        return True
    if is_non_entity_value(low):
        return True
    junk_tokens = (
        "اسلاید", "slide", "جدول", "table", "صفحه", "page", "شیت", "sheet",
        "جمع کل", "مجموع کل", "جمع", "مجموع", "میانگین", "total", "subtotal", "grand total",
        "ردیف", "مانده از قبل", "مانده قبلی",
    )
    if any(tok in low for tok in junk_tokens) and ("کارگروه" not in low):
        return True
    return False


def normalize_phone(text: Any) -> str:
    s = re.sub(r"\.0+$", "", str(text or "").strip()).translate(LATIN_DIGITS)
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 10:
        if digits.startswith("0098") and len(digits) >= 14:
            digits = "0" + digits[4:14]
        elif digits.startswith("98") and len(digits) >= 12:
            digits = "0" + digits[2:12]
        elif digits.startswith("9") and len(digits) == 10:
            digits = "0" + digits
        elif len(digits) > 11:
            digits = "0" + digits[-10:]
        return digits
    return ""


def normalize_nid(text: Any) -> str:
    s = re.sub(r"\.0+$", "", str(text or "").strip()).translate(LATIN_DIGITS)
    digits = re.sub(r"\D", "", s)
    return digits.zfill(10) if 8 <= len(digits) <= 10 else ""


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

                    def find_col(keywords: tuple[str, ...]) -> int:
                        for idx, nc in enumerate(norm_cols):
                            if is_banner_header_col(cols[idx]):
                                continue
                            if any(kw in nc for kw in keywords):
                                return idx
                        return -1

                    i_first_name = next((idx for idx, nc in enumerate(norm_cols) if nc in ("نام", "first name", "name") and not is_banner_header_col(cols[idx])), -1)
                    i_last_name = next((idx for idx, nc in enumerate(norm_cols) if ("نام خانوادگی" in nc or "فامیل" in nc or nc == "last name") and not is_banner_header_col(cols[idx])), -1)
                    i_person = find_col(("نام و نام خانوادگی", "نام خانوادگی", "شرکت کننده", "شرکت‌کننده", "طلبه", "ثبت نام کننده", "پاسخ دهنده", "full_name", "participant"))
                    i_phone = find_col(("موبایل", "همراه", "تلفن", "شماره تماس", "phone", "mobile"))
                    i_nid = find_col(("کد ملی", "کدملی", "شماره ملی", "national"))
                    i_level = find_col(("سطح", "پایه", "مقطع", "تحصیلات", "level"))
                    i_course = find_col(("عنوان دوره", "نام دوره", "موضوع", "عنوان برنامه", "رویداد", "دوره", "نشست", "course", "title"))
                    i_group = find_col(("کارگروه", "گروه موضوعی", "گروه علمی", "بخش", "حوزه موضوعی", "واحد", "group", "department"))
                    i_teacher = find_col(("استاد", "ارائه دهنده", "ارائه‌دهنده", "سخنران", "مدرس", "teacher", "speaker"))
                    i_count = find_col(("مخاطب", "شرکت", "تعداد نفر", "حاضرین", "نفر", "ثبت نام", "attendance", "count", "students"))
                    i_hours = find_col(("ساعت", "ساعات", "مدت", "hours", "duration"))
                    i_sessions = find_col(("جلسه", "تعداد جلسات", "جلسات", "sessions"))
                    i_cost = find_col(("مبلغ کل", "بدهکار", "برداشت", "مبلغ", "هزینه", "حق التدریس", "حق‌التدریس", "پرداختی", "پرداخت", "بستانکار", "تنخواه", "خرج", "تومان", "ریال", "فاکتور", "بهای", "جمع کل", "cost", "amount", "price"))
                    i_date = find_col(("تاریخ", "سال", "فصل", "ماه", "زمان", "date", "year"))
                    i_cost_cat = find_col(("شرح", "بابت", "سرفصل", "نوع هزینه", "عنوان", "موضوع"))

                    if (i_person != -1 or (i_first_name != -1 and i_last_name != -1)) and (i_phone != -1 or i_nid != -1 or i_level != -1):
                        roster_course, roster_teacher = extract_roster_banner_meta(banner_ctx, fn, sh)
                        reserved_cols = {
                            c_i for c_i in (i_person, i_first_name, i_last_name, i_phone, i_nid, i_level, i_course, i_group, i_teacher, i_date, i_cost, i_count, i_hours, i_sessions)
                            if c_i != -1
                        }
                        if norm_cols and any(k in norm_cols[0] for k in ("ردیف", "شماره", "no", "id")):
                            reserved_cols.add(0)
                        session_cols = _detect_session_columns(cols, reserved_cols)

                        for r_idx, r in enumerate(rows, start=1):
                            if is_blank_numbered_row(list(r)):
                                continue
                            if is_summary_row_smart(list(r)):
                                continue
                            if i_first_name != -1 and i_last_name != -1 and i_first_name != i_last_name:
                                fn_p = normalize_fa(r[i_first_name] if i_first_name < len(r) else "")
                                ln_p = normalize_fa(r[i_last_name] if i_last_name < len(r) else "")
                                nm = f"{fn_p} {ln_p}".strip()
                            else:
                                nm = normalize_fa(r[i_person] if (i_person != -1 and i_person < len(r)) else "")
                            if is_junk_label(nm) or len(nm) < 3:
                                continue
                            dt_raw = normalize_fa(r[i_date]) if (i_date != -1 and i_date < len(r)) else ""
                            jd = parse_jalali_date(dt_raw, fallback_text=f"{fn} {sh} {banner_ctx}")
                            t_cell = normalize_fa(r[i_teacher]) if (i_teacher != -1 and i_teacher < len(r)) else ""
                            if not is_valid_teacher_name(t_cell):
                                t_cell = roster_teacher

                            sess_marks = []
                            s_att = s_late = s_exc = s_abs = 0
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

                            persons.append({
                                "name": nm, "phone": normalize_phone(r[i_phone]) if (i_phone != -1 and i_phone < len(r)) else "",
                                "nid": normalize_nid(r[i_nid]) if (i_nid != -1 and i_nid < len(r)) else "",
                                "level": normalize_fa(r[i_level]) if (i_level != -1 and i_level < len(r)) else "",
                                "course": normalize_fa(r[i_course]) if (i_course != -1 and i_course < len(r)) else (roster_course or sh or Path(fn).stem or "دوره آموزشی"),
                                "group": normalize_fa(r[i_group]) if (i_group != -1 and i_group < len(r)) else detect_workgroup_unified(fn, sh, "", roster_course or "", banner_ctx),
                                "teacher": t_cell,
                                "date": jd["canonical"] or dt_raw, "year": jd["year"] or "نامشخص",
                                "month_idx": (jd["month"] - 1) if 1 <= jd["month"] <= 12 else -1,
                                "season": jd["season"], "source": tname, "file_name": fn, "source_sheet": sh, "row_index": r_idx,
                                "sessions_total": len(session_cols),
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
            "تربیتمبلغ": "تربیت سخنران و مبلغ",
            "تربیتسخنران": "تربیت سخنران و مبلغ",
            "تربیتسخنرانومبلغ": "تربیت سخنران و مبلغ",
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

        existing_course_keys = {canon_key(c["title"]) for c in db_courses}
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

        for c_title, plist in reg_by_course.items():
            if canon_key(c_title) not in existing_course_keys:
                sample = plist[0]
                mode, t_list = _resolve_course_teachers(sample["teacher"])
                all_courses.append({
                    "course_uid": f"porsline#{canon_key(c_title)}", "title": c_title,
                    "group": sample["group"], "teacher": sample["teacher"],
                    "holding_mode": mode, "teachers_resolved": t_list,
                    "attendance": len(plist), "attendance_valid": True,
                    "hours": 0.0, "sessions": 0, "cost": 0.0,
                    "date": sample["date"], "year": sample["year"], "month_idx": sample["month_idx"],
                    "season": "", "source": "porsline", "file_name": "ورودی پرس‌لاین", "source_sheet": "", "row_index": 0,
                })

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
                if c_ck not in dst["course_map"] or c_obj["sessions_total"] > dst["course_map"][c_ck]["sessions_total"]:
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

            matched_pids = []
            for m_pid in (nid_to_id.get(nid) if nid else None, phone_to_id.get(ph) if ph else None, name_to_id.get(ck)):
                if m_pid and m_pid in person_entities and m_pid not in matched_pids:
                    matched_pids.append(m_pid)

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
            c_ck = canon_key(c_title)
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
            if c_ck not in ent["course_map"] or s_tot > ent["course_map"][c_ck]["sessions_total"]:
                ent["course_map"][c_ck] = c_rec
            if p["group"] and p["group"] not in ent["groups"]:
                ent["groups"].append(p["group"])
            for tn in (p.get("teachers_list") or ([p["teacher"]] if p["teacher"] and p["teacher"] != "نامشخص" else [])):
                if tn and tn != "نامشخص" and tn not in ent["teachers"]:
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
            ent["profile_key"] = f"ph:{ent['phone']}" if ent["phone"] else (f"nid:{ent['nid']}" if ent["nid"] else f"nm:{canon_key(ent['name'])}")

            cnt = len(ent["courses"])
            if cnt >= 2:
                repeat_users += 1
            if cnt <= 1:
                loyalty, b, l_rank = "مخاطب جدید", "۱ دوره", 1
            elif cnt == 2:
                loyalty, b, l_rank = "مخاطب فعال", "۲ دوره", 2
            elif cnt <= 4:
                loyalty, b, l_rank = "مخاطب وفادار", "۳ تا ۴ دوره", 3
            else:
                loyalty, b, l_rank = "هسته اصلی", "۵+ دوره (هسته)", 4
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

        aff_labels = [g["name"] for g in groups_out[:6]]
        aff_matrix = [[0 for _ in aff_labels] for _ in aff_labels]
        cross_group_people = 0
        for ent in person_entities.values():
            if len(ent["groups"]) >= 2:
                cross_group_people += 1
            egs = [g for g in ent["groups"] if g in aff_labels]
            for i_a, ga in enumerate(aff_labels):
                if ga in egs:
                    for i_b, gb in enumerate(aff_labels):
                        if gb in egs:
                            aff_matrix[i_a][i_b] += 1

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
            "retention": [{"label": lbl, "count": ret_buckets.get(lbl, 0)} for lbl in ("۱ دوره", "۲ دوره", "۳ تا ۴ دوره", "۵+ دوره (هسته)")],
            "groups": groups_out, "affinity_matrix": {"labels": aff_labels, "matrix": aff_matrix},
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

        duplicates, sample = [], participants[:200]
        for i in range(len(sample)):
            a, ka = sample[i], canon_key(sample[i]["name"])
            if len(ka) < 4:
                continue
            pa, na = (a.get("phone") or "").strip(), (a.get("nid") or "").strip()
            wa = a["name"].split()
            for j in range(i + 1, len(sample)):
                b, kb = sample[j], canon_key(sample[j]["name"])
                if abs(len(ka) - len(kb)) > 3:
                    continue
                if tuple(sorted([ka, kb])) in rejected_pairs:
                    continue
                pb, nb = (b.get("phone") or "").strip(), (b.get("nid") or "").strip()
                # Never flag two people with distinct valid phone numbers or distinct NIDs as duplicates!
                if pa and pb and pa != pb:
                    continue
                if na and nb and na != nb:
                    continue
                # If both have surname words, require surname similarity >= 0.72 so shared first names don't collide
                wb = b["name"].split()
                if len(wa) >= 2 and len(wb) >= 2:
                    sur_sim = difflib.SequenceMatcher(None, canon_key(wa[-1]), canon_key(wb[-1])).ratio()
                    if sur_sim < 0.72:
                        continue
                sim = difflib.SequenceMatcher(None, ka, kb).ratio()
                if sim >= 0.85:
                    duplicates.append({"name_a": a["name"], "phone_a": pa or "—", "courses_a": a.get("courses_count", 1), "name_b": b["name"], "phone_b": pb or "—", "courses_b": b.get("courses_count", 1), "similarity": round(sim * 100)})
                    if len(duplicates) >= 25:
                        break
            if len(duplicates) >= 25:
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

    def get_teacher_profile(self, teacher_name: str) -> dict[str, Any]:
        an = self.get_executive_analytics({"teacher": teacher_name})
        t_info = next((t for t in an["teachers"] if canon_key(t["name"]) == canon_key(teacher_name)), None)
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

    def get_participant_profile(self, person_key: str) -> dict[str, Any]:
        an = self.get_executive_analytics()
        target = next(
            (
                p for p in an["participants"]
                if p["id"] == person_key
                or p.get("profile_key") == person_key
                or (p.get("phone") and p["phone"] == person_key)
                or canon_key(p["name"]) == canon_key(person_key)
            ),
            None,
        )
        return {"ok": True, "participant": target} if target else {"ok": False, "error": "مخاطب مورد نظر یافت نشد."}

    def save_participant_meta(self, profile_key: str, meta: dict[str, Any]) -> dict[str, Any]:
        pk = str(profile_key or "").strip()
        if not pk:
            return {"ok": False, "error": "شناسه مخاطب نامعتبر است."}
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
        store[pk] = {
            "phone": normalize_phone(meta.get("phone") or ""),
            "nid": normalize_nid(meta.get("nid") or ""),
            "level": normalize_fa(meta.get("level") or ""),
            "tags": clean_tags[:12],
            "notes": str(meta.get("notes") or "").strip()[:1500],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
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
        i_nid = pick(("کد ملی", "کدملی", "شماره ملی", "national"))

        existing_an = self.get_executive_analytics()
        known_phones = {x["phone"]: x for x in existing_an["participants"] if x.get("phone")}
        known_names = {canon_key(x["name"]): x for x in existing_an["participants"]}

        reserved_p = {idx for idx in (i_full, i_first, i_last, i_phone, i_level, i_nid) if idx != -1}
        if norm_h and any(k in norm_h[0] for k in ("ردیف", "شماره", "no", "id")):
            reserved_p.add(0)
        p_sess_cols = _detect_session_columns(headers, reserved_p)

        parsed, new_cnt, ret_cnt = [], 0, 0
        for r in rows:
            if is_blank_numbered_row(list(r)) or is_summary_row_smart(list(r)):
                continue
            if i_full != -1 and i_full < len(r):
                name = normalize_fa(r[i_full])
            else:
                fn_p = normalize_fa(r[i_first]) if (i_first != -1 and i_first < len(r)) else ""
                ln_p = normalize_fa(r[i_last]) if (i_last != -1 and i_last < len(r)) else ""
                name = f"{fn_p} {ln_p}".strip()
            if len(name) < 3 or is_junk_label(name):
                continue
            ph = normalize_phone(r[i_phone]) if (i_phone != -1 and i_phone < len(r)) else ""
            lvl = normalize_fa(r[i_level]) if (i_level != -1 and i_level < len(r)) else ""
            nid = normalize_nid(r[i_nid]) if (i_nid != -1 and i_nid < len(r)) else ""
            prev = (known_phones.get(ph) if ph else None) or known_names.get(canon_key(name))
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

            parsed.append({
                "name": name, "phone": ph, "nid": nid, "level": lvl,
                "is_new": is_new, "prev_courses": prev["courses_count"] if prev else 0,
                "sessions_total": len(p_sess_cols), "sessions_attended": s_att,
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
            "new_count": new_cnt,
            "returning_count": ret_cnt,
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
