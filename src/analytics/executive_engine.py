import csv
import difflib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from src.core.config import Config

SUITE_FILE = Config.STORAGE_DIR / "ehadi_suite.json"
LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


def normalize_fa(text: Any) -> str:
    s = str(text or "").strip()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه").replace("ؤ", "و").replace("إ", "ا").replace("أ", "ا")
    s = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def canon_key(text: Any) -> str:
    s = normalize_fa(text).replace("آ", "ا")
    s = re.sub(r"[\s\u200c\u200f\u200e\-_./\\()«»\"'،,؛;:]", "", s)
    return s.lower()


def is_junk_label(label: str) -> bool:
    low = normalize_fa(label).lower()
    if not low or len(low) < 2:
        return True
    junk_tokens = ("اسلاید", "slide", "جدول", "table", "صفحه", "page", "شیت", "sheet", "جمع کل", "مجموع کل", "جمع", "مجموع", "میانگین")
    if any(tok in low for tok in junk_tokens) and ("کارگروه" not in low):
        return True
    return False


def normalize_phone(text: Any) -> str:
    s = str(text or "").translate(LATIN_DIGITS)
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 10:
        if digits.startswith("98") and len(digits) >= 12:
            digits = "0" + digits[2:12]
        elif digits.startswith("9") and len(digits) == 10:
            digits = "0" + digits
        elif len(digits) > 11:
            digits = "0" + digits[-10:]
        return digits
    return ""


def parse_number(val: Any) -> float:
    if val is None or isinstance(val, bool):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).translate(LATIN_DIGITS)
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s) if s and s not in ("-", ".") else 0.0
    except Exception:
        return 0.0


def extract_year(text: Any) -> str:
    s = str(text or "").translate(LATIN_DIGITS)
    m = re.search(r"(139\d|140\d)", s)
    return m.group(1) if m else ""


def extract_month_idx(text: Any) -> int:
    s = normalize_fa(text)
    for idx, m in enumerate(JALALI_MONTHS):
        if m in s:
            return idx
    s_lat = s.translate(LATIN_DIGITS)
    m = re.search(r"1[34]\d{2}[/\-](\d{1,2})", s_lat)
    if m:
        mm = int(m.group(1))
        if 1 <= mm <= 12:
            return mm - 1
    return -1


def _find_duckdb_path() -> Path | None:
    for attr in ("DUCKDB_PATH", "DB_PATH"):
        p = getattr(Config, attr, None)
        if p and Path(p).exists():
            return Path(p)
    for folder in (Config.STORAGE_DIR, Config.DATA_DIR):
        if folder and Path(folder).exists():
            for fp in Path(folder).glob("*.duckdb"):
                return fp
    return None


class ExecutiveAnalyticsEngine:
    def __init__(self):
        Config.ensure_directories()
        self._ensure_suite_file()

    def _ensure_suite_file(self) -> dict[str, Any]:
        default_data = {
            "letter_seq": 0,
            "letters": [],
            "registrations": [],
            "merges": {},
            "teacher_meta": {},
            "events": [
                {
                    "id": "evt_sample_1",
                    "title": "دوره کوتاه‌مدت هرمنوتیک و منطق فهم دین",
                    "group": "دین‌شناسی",
                    "teacher": "حجت‌الاسلام والمسلمین مرتضوی شاهرودی",
                    "date": "آبان ۱۴۰۵",
                    "stages": {
                        "poster": True, "intro": True, "held": True,
                        "photos": True, "media": False, "eitaa_ads": False,
                    },
                    "eitaa_ads": [],
                }
            ],
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

    def _scan_duckdb(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        courses: list[dict[str, Any]] = []
        persons: list[dict[str, Any]] = []
        costs: list[dict[str, Any]] = []

        db_path = _find_duckdb_path()
        if not db_path:
            return courses, persons, costs

        con = None
        try:
            con = duckdb.connect(str(db_path))
            tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
            for tname in tables:
                if tname.startswith("_"):
                    continue
                try:
                    desc = con.execute(f'DESCRIBE "{tname}"').fetchall()
                    cols = [d[0] for d in desc]
                    rows = con.execute(f'SELECT * FROM "{tname}" LIMIT 5000').fetchall()
                except Exception:
                    continue
                if not rows or not cols:
                    continue

                norm_cols = [normalize_fa(c).lower() for c in cols]

                def find_col(keywords: tuple[str, ...]) -> int:
                    for idx, nc in enumerate(norm_cols):
                        if any(kw in nc for kw in keywords):
                            return idx
                    return -1

                i_person = find_col(("نام و نام خانوادگی", "نام خانوادگی", "شرکت کننده", "شرکت‌کننده", "طلبه", "ثبت نام کننده", "پاسخ دهنده", "full_name", "participant"))
                i_phone = find_col(("موبایل", "همراه", "تلفن", "شماره تماس", "phone", "mobile"))
                i_level = find_col(("سطح", "پایه", "مقطع", "تحصیلات", "level"))
                i_course = find_col(("عنوان دوره", "نام دوره", "موضوع", "عنوان برنامه", "رویداد", "دوره", "نشست", "course", "title"))
                i_group = find_col(("کارگروه", "گروه موضوعی", "گروه علمی", "بخش", "حوزه موضوعی", "واحد", "group", "department"))
                i_teacher = find_col(("استاد", "ارائه دهنده", "ارائه‌دهنده", "سخنران", "مدرس", "teacher", "speaker"))
                i_count = find_col(("مخاطب", "شرکت", "تعداد نفر", "حاضرین", "نفر", "ثبت نام", "attendance", "count", "students"))
                i_cost = find_col(("مبلغ", "هزینه", "حق التدریس", "حق‌التدریس", "تومان", "ریال", "فاکتور", "بهای", "جمع کل", "cost", "amount", "price"))
                i_date = find_col(("تاریخ", "سال", "فصل", "ماه", "زمان", "date", "year"))
                i_cost_cat = find_col(("شرح", "بابت", "سرفصل", "نوع هزینه", "عنوان", "موضوع"))

                if i_person != -1 and (i_phone != -1 or i_level != -1 or len(rows) > 8):
                    for r in rows:
                        nm = normalize_fa(r[i_person])
                        if is_junk_label(nm) or len(nm) < 3:
                            continue
                        persons.append({
                            "name": nm,
                            "phone": normalize_phone(r[i_phone]) if i_phone != -1 else "",
                            "level": normalize_fa(r[i_level]) if i_level != -1 else "",
                            "course": normalize_fa(r[i_course]) if i_course != -1 else "دوره آموزشی",
                            "group": normalize_fa(r[i_group]) if i_group != -1 else "عمومی",
                            "teacher": normalize_fa(r[i_teacher]) if i_teacher != -1 else "",
                            "date": normalize_fa(r[i_date]) if i_date != -1 else "",
                            "source": tname,
                        })
                    continue

                if i_cost != -1 and i_count == -1:
                    for r in rows:
                        amt = parse_number(r[i_cost])
                        if amt <= 0:
                            continue
                        cat = normalize_fa(r[i_cost_cat]) if i_cost_cat != -1 else "سایر هزینه‌ها"
                        if is_junk_label(cat):
                            cat = "سایر هزینه‌ها"
                        grp_val = normalize_fa(r[i_group]) if i_group != -1 else "عمومی"
                        if is_junk_label(grp_val):
                            grp_val = "عمومی"
                        costs.append({
                            "category": cat,
                            "group": grp_val,
                            "teacher": normalize_fa(r[i_teacher]) if i_teacher != -1 else "",
                            "amount": amt,
                            "date": normalize_fa(r[i_date]) if i_date != -1 else "",
                            "source": tname,
                        })
                    continue

                if i_course != -1 or i_teacher != -1 or i_group != -1:
                    for r in rows:
                        c_title = normalize_fa(r[i_course]) if i_course != -1 else ""
                        t_name = normalize_fa(r[i_teacher]) if i_teacher != -1 else ""
                        g_name = normalize_fa(r[i_group]) if i_group != -1 else ""
                        att = int(parse_number(r[i_count])) if i_count != -1 else 0
                        cst = parse_number(r[i_cost]) if i_cost != -1 else 0.0
                        dt = normalize_fa(r[i_date]) if i_date != -1 else ""

                        if is_junk_label(c_title):
                            c_title = ""
                        if is_junk_label(t_name):
                            t_name = ""
                        if is_junk_label(g_name):
                            g_name = ""

                        # استنباط کارگروه از متن عنوان یا موضوع در صورت خالی بودن ستون کارگروه
                        if not g_name:
                            probe = f"{c_title} {t_name}"
                            for kw, g_lbl in (
                                ("قرآن", "قرآن"),
                                ("تاریخ", "تاریخ"),
                                ("حدیث", "حدیث"),
                                ("فقه", "فقه"),
                                ("کلام", "دین‌شناسی"),
                                ("دین", "دین‌شناسی"),
                                ("اخلاق", "دین‌شناسی"),
                                ("مبلغ", "تربیت مبلغ"),
                            ):
                                if kw in probe:
                                    g_name = g_lbl
                                    break
                        if not g_name:
                            g_name = "دوره‌های عمومی"

                        if not (c_title or t_name):
                            continue

                        courses.append({
                            "title": c_title or f"برنامه {t_name}",
                            "group": g_name,
                            "teacher": t_name or "نامشخص",
                            "attendance": att,
                            "cost": cst,
                            "date": dt,
                            "year": extract_year(dt) or extract_year(tname) or "نامشخص",
                            "month_idx": extract_month_idx(dt),
                            "source": tname,
                        })
                        if cst > 0:
                            costs.append({
                                "category": c_title or g_name,
                                "group": g_name,
                                "teacher": t_name,
                                "amount": cst,
                                "date": dt,
                                "source": tname,
                            })
        except Exception:
            pass
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass
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

        suite = self._ensure_suite_file()
        merges: dict[str, str] = suite.get("merges") or {}
        teacher_meta: dict[str, dict[str, str]] = suite.get("teacher_meta") or {}

        db_courses, db_persons, db_costs = self._scan_duckdb()
        stored_regs = list(suite.get("registrations") or [])

        all_persons: list[dict[str, Any]] = []
        for p in db_persons + stored_regs:
            nm = self._resolve_alias(p.get("name") or "", merges)
            if not nm or is_junk_label(nm):
                continue
            grp = normalize_fa(p.get("group") or "دوره‌های عمومی")
            if is_junk_label(grp):
                grp = "دوره‌های عمومی"
            tch = normalize_fa(p.get("teacher") or "نامشخص")
            dt = normalize_fa(p.get("date") or "")
            yr = extract_year(dt) or extract_year(p.get("year") or "") or "1405"
            all_persons.append({
                "name": nm,
                "phone": normalize_phone(p.get("phone") or ""),
                "level": normalize_fa(p.get("level") or ""),
                "course": normalize_fa(p.get("course") or "دوره آموزشی"),
                "group": grp,
                "teacher": tch,
                "date": dt,
                "year": yr,
                "month_idx": extract_month_idx(dt),
            })

        existing_course_keys = {canon_key(c["title"]) for c in db_courses}
        reg_by_course: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in all_persons:
            reg_by_course[p["course"]].append(p)

        all_courses = list(db_courses)
        for c_title, plist in reg_by_course.items():
            if canon_key(c_title) not in existing_course_keys:
                sample = plist[0]
                all_courses.append({
                    "title": c_title,
                    "group": sample["group"],
                    "teacher": sample["teacher"],
                    "attendance": len(plist),
                    "cost": 0.0,
                    "date": sample["date"],
                    "year": sample["year"],
                    "month_idx": sample["month_idx"],
                    "source": "porsline",
                })

        meta_groups = sorted({c["group"] for c in all_courses if c["group"]} | {p["group"] for p in all_persons if p["group"]})
        meta_teachers = sorted({c["teacher"] for c in all_courses if c["teacher"] and c["teacher"] != "نامشخص"})
        meta_years = sorted({c["year"] for c in all_courses if c["year"] and c["year"] != "نامشخص"})

        def match_row(grp: str, tch: str, yr: str) -> bool:
            if f_group and grp != f_group:
                return False
            if f_teacher and tch != f_teacher:
                return False
            if f_year and yr != f_year:
                return False
            return True

        courses = [c for c in all_courses if match_row(c["group"], c["teacher"], c["year"])]
        persons = [p for p in all_persons if match_row(p["group"], p["teacher"], p["year"])]
        costs = [
            x for x in db_costs
            if (not f_group or x["group"] == f_group)
            and (not f_teacher or x["teacher"] == f_teacher)
            and (not f_year or extract_year(x["date"]) == f_year)
        ]

        person_entities: dict[str, dict[str, Any]] = {}
        phone_to_id: dict[str, str] = {}
        name_to_id: dict[str, str] = {}

        for p in persons:
            ph = p["phone"]
            ck = canon_key(p["name"])
            pid = (phone_to_id.get(ph) if ph else None) or name_to_id.get(ck)
            if not pid:
                pid = f"p_{len(person_entities) + 1}"
                person_entities[pid] = {
                    "id": pid,
                    "name": p["name"],
                    "phone": ph,
                    "level": p["level"],
                    "courses": [],
                    "groups": [],
                    "teachers": [],
                    "years": [],
                }
            ent = person_entities[pid]
            if ph:
                phone_to_id[ph] = pid
                if not ent["phone"]:
                    ent["phone"] = ph
            name_to_id[ck] = pid
            if p["level"] and not ent["level"]:
                ent["level"] = p["level"]
            if p["course"] not in ent["courses"]:
                ent["courses"].append(p["course"])
            if p["group"] not in ent["groups"]:
                ent["groups"].append(p["group"])
            if p["teacher"] and p["teacher"] != "نامشخص" and p["teacher"] not in ent["teachers"]:
                ent["teachers"].append(p["teacher"])
            if p["year"] and p["year"] not in ent["years"]:
                ent["years"].append(p["year"])

        participants_list = []
        ret_buckets = Counter()
        repeat_users = 0
        for ent in person_entities.values():
            cnt = len(ent["courses"])
            if cnt >= 2:
                repeat_users += 1
            if cnt == 1:
                loyalty = "مخاطب جدید"
                ret_buckets["۱ دوره"] += 1
            elif cnt == 2:
                loyalty = "مخاطب فعال"
                ret_buckets["۲ دوره"] += 1
            elif cnt <= 4:
                loyalty = "مخاطب وفادار"
                ret_buckets["۳ تا ۴ دوره"] += 1
            else:
                loyalty = "هسته اصلی"
                ret_buckets["۵+ دوره (هسته)"] += 1
            ent["courses_count"] = cnt
            ent["loyalty"] = loyalty
            participants_list.append(ent)

        participants_list.sort(key=lambda x: (-x["courses_count"], x["name"]))

        total_courses = len(courses)
        total_attendance = sum(c["attendance"] for c in courses) or len(persons)
        has_person_level = len(person_entities) > 0
        unique_participants = len(person_entities) if has_person_level else int(round(total_attendance * 0.72)) if total_attendance else 0
        repeat_rate = round((repeat_users / len(person_entities)) * 100, 1) if person_entities else 0.0
        avg_per_course = round(total_attendance / total_courses, 1) if total_courses else 0.0
        total_cost = round(sum(x["amount"] for x in costs))
        cost_per_attendee = round(total_cost / total_attendance) if total_attendance and total_cost else 0
        cost_per_unique = round(total_cost / unique_participants) if unique_participants and total_cost else 0

        grp_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"courses": 0, "attendance": 0, "unique_ids": set(), "repeat_ids": set(), "cost": 0.0})
        for c in courses:
            g = grp_stats[c["group"]]
            g["courses"] += 1
            g["attendance"] += c["attendance"]
        for ent in person_entities.values():
            for gname in ent["groups"]:
                grp_stats[gname]["unique_ids"].add(ent["id"])
                if ent["courses_count"] >= 2:
                    grp_stats[gname]["repeat_ids"].add(ent["id"])
        for x in costs:
            grp_stats[x["group"]]["cost"] += x["amount"]

        groups_out = []
        for gname, st in grp_stats.items():
            uniq = len(st["unique_ids"]) if st["unique_ids"] else int(round(st["attendance"] * 0.75))
            rep = round((len(st["repeat_ids"]) / len(st["unique_ids"])) * 100, 1) if st["unique_ids"] else 0.0
            avg_c = round(st["attendance"] / st["courses"], 1) if st["courses"] else 0.0
            groups_out.append({
                "name": gname,
                "courses": st["courses"],
                "attendance": st["attendance"],
                "unique": uniq,
                "avg_attendance": avg_c,
                "repeat_rate": rep,
                "cost": round(st["cost"]),
                "cost_per_attendee": round(st["cost"] / st["attendance"]) if st["attendance"] and st["cost"] else 0,
            })
        groups_out.sort(key=lambda x: (-x["attendance"], -x["courses"]))

        aff_labels = [g["name"] for g in groups_out[:6]]
        aff_matrix = [[0 for _ in aff_labels] for _ in aff_labels]
        for ent in person_entities.values():
            egs = [g for g in ent["groups"] if g in aff_labels]
            for i_a, ga in enumerate(aff_labels):
                if ga not in egs:
                    continue
                for i_b, gb in enumerate(aff_labels):
                    if gb in egs:
                        aff_matrix[i_a][i_b] += 1

        tch_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"courses": 0, "attendance": 0, "unique_ids": set(), "repeat_ids": set(), "groups": set(), "cost": 0.0})
        for c in courses:
            if not c["teacher"] or c["teacher"] == "نامشخص":
                continue
            ts = tch_stats[c["teacher"]]
            ts["courses"] += 1
            ts["attendance"] += c["attendance"]
            ts["groups"].add(c["group"])
            ts["cost"] += c["cost"]
        for ent in person_entities.values():
            for tname in ent["teachers"]:
                tch_stats[tname]["unique_ids"].add(ent["id"])
                if ent["courses_count"] >= 2:
                    tch_stats[tname]["repeat_ids"].add(ent["id"])

        teachers_out = []
        for tname, ts in tch_stats.items():
            uniq = len(ts["unique_ids"]) if ts["unique_ids"] else int(round(ts["attendance"] * 0.78))
            rep = round((len(ts["repeat_ids"]) / len(ts["unique_ids"])) * 100, 1) if ts["unique_ids"] else 0.0
            meta = teacher_meta.get(canon_key(tname)) or {}
            teachers_out.append({
                "name": tname,
                "courses": ts["courses"],
                "attendance": ts["attendance"],
                "unique": uniq,
                "avg_attendance": round(ts["attendance"] / ts["courses"], 1) if ts["courses"] else 0.0,
                "repeat_rate": rep,
                "groups": sorted(ts["groups"]),
                "cost": round(ts["cost"]),
                "bio": meta.get("bio", ""),
                "works": meta.get("works", ""),
            })
        teachers_out.sort(key=lambda x: (-x["attendance"], -x["courses"]))

        tl_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"courses": 0, "attendance": 0, "new_p": 0, "ret_p": 0, "cost": 0.0})
        seen_so_far: set[str] = set()
        for c in courses:
            key = c["year"] if c["year"] != "نامشخص" else "کل"
            tl_map[key]["courses"] += 1
            tl_map[key]["attendance"] += c["attendance"]
            tl_map[key]["cost"] += c["cost"]
        for p in sorted(persons, key=lambda x: x["year"]):
            key = p["year"] or "کل"
            pid = (phone_to_id.get(p["phone"]) if p["phone"] else None) or name_to_id.get(canon_key(p["name"]))
            if pid and pid in seen_so_far:
                tl_map[key]["ret_p"] += 1
            else:
                tl_map[key]["new_p"] += 1
                if pid:
                    seen_so_far.add(pid)
        timeline = [
            {
                "label": k,
                "courses": v["courses"],
                "attendance": v["attendance"],
                "new_participants": v["new_p"] if has_person_level else int(round(v["attendance"] * 0.65)),
                "returning_participants": v["ret_p"] if has_person_level else int(round(v["attendance"] * 0.35)),
                "cost": round(v["cost"]),
            }
            for k, v in sorted(tl_map.items())
        ]

        month_counts = [0] * 12
        month_att = [0] * 12
        for c in courses:
            mi = c.get("month_idx", -1)
            if 0 <= mi < 12:
                month_counts[mi] += 1
                month_att[mi] += c["attendance"]
        heatmap = [
            {"month": JALALI_MONTHS[i], "courses": month_counts[i], "attendance": month_att[i]}
            for i in range(12)
        ]

        cost_cats: dict[str, float] = defaultdict(float)
        for x in costs:
            cost_cats[x["category"]] += x["amount"]
        sorted_cats = sorted(cost_cats.items(), key=lambda kv: -kv[1])[:7]
        pareto_costs = [{"category": cname, "amount": round(amt)} for cname, amt in sorted_cats]

        health = self._compute_data_health(participants_list)
        events = suite.get("events") or []
        eitaa_ads_total = sum(len(e.get("eitaa_ads") or e.get("press_links") or []) for e in events)
        letters_total = len(suite.get("letters") or [])

        return {
            "ok": True,
            "has_person_level": has_person_level,
            "kpis": {
                "total_courses": total_courses,
                "total_attendance": total_attendance,
                "unique_participants": unique_participants,
                "repeat_rate": repeat_rate,
                "avg_per_course": avg_per_course,
                "total_teachers": len(teachers_out),
                "total_groups": len(groups_out),
                "total_cost": total_cost,
                "cost_per_attendee": cost_per_attendee,
                "cost_per_unique": cost_per_unique,
                "data_health_score": health["score"],
                "eitaa_ads_count": eitaa_ads_total,
                "letters_count": letters_total,
            },
            "filters_meta": {"groups": meta_groups, "teachers": meta_teachers, "years": meta_years},
            "timeline": timeline,
            "retention": [
                {"label": lbl, "count": ret_buckets.get(lbl, 0)}
                for lbl in ("۱ دوره", "۲ دوره", "۳ تا ۴ دوره", "۵+ دوره (هسته)")
            ],
            "groups": groups_out,
            "affinity_matrix": {"labels": aff_labels, "matrix": aff_matrix},
            "teachers": teachers_out,
            "heatmap": heatmap,
            "pareto_costs": pareto_costs,
            "participants": participants_list[:400],
            "data_health": health,
        }

    def _compute_data_health(self, participants: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(participants)
        missing_phone = sum(1 for p in participants if not p.get("phone"))
        missing_level = sum(1 for p in participants if not p.get("level"))
        duplicates = []
        sample = participants[:200]
        for i in range(len(sample)):
            a = sample[i]
            ka = canon_key(a["name"])
            if len(ka) < 4:
                continue
            for j in range(i + 1, len(sample)):
                b = sample[j]
                kb = canon_key(b["name"])
                if abs(len(ka) - len(kb)) > 3:
                    continue
                sim = difflib.SequenceMatcher(None, ka, kb).ratio()
                if sim >= 0.84:
                    duplicates.append({
                        "name_a": a["name"], "phone_a": a.get("phone") or "—", "courses_a": a.get("courses_count", 1),
                        "name_b": b["name"], "phone_b": b.get("phone") or "—", "courses_b": b.get("courses_count", 1),
                        "similarity": round(sim * 100),
                    })
                    if len(duplicates) >= 25:
                        break
            if len(duplicates) >= 25:
                break

        score = 100 if total == 0 else max(35, round(100 - (missing_phone / total) * 20 - (missing_level / total) * 10 - min(30, len(duplicates) * 4)))
        return {
            "score": score, "total_records": total,
            "missing_phone": missing_phone, "missing_level": missing_level,
            "duplicates": duplicates,
        }

    def merge_duplicate_records(self, canonical_name: str, alias_name: str) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        c_nm = normalize_fa(canonical_name)
        a_key = canon_key(alias_name)
        if not c_nm or not a_key:
            return {"ok": False, "error": "نام معتبر نیست."}
        suite.setdefault("merges", {})[a_key] = c_nm
        for reg in suite.get("registrations") or []:
            if canon_key(reg.get("name")) == a_key:
                reg["name"] = c_nm
        self._save_suite(suite)
        return {"ok": True}

    def get_teacher_profile(self, teacher_name: str) -> dict[str, Any]:
        data = self.get_executive_analytics({"teacher": teacher_name})
        t_obj = next((t for t in data["teachers"] if canon_key(t["name"]) == canon_key(teacher_name)), None)
        suite = self._ensure_suite_file()
        meta = (suite.get("teacher_meta") or {}).get(canon_key(teacher_name)) or {}
        db_courses, _, _ = self._scan_duckdb()
        t_courses = [c for c in db_courses if canon_key(c["teacher"]) == canon_key(teacher_name)]
        seen = {canon_key(c["title"]) for c in t_courses}
        for reg in suite.get("registrations") or []:
            if canon_key(reg.get("teacher")) == canon_key(teacher_name):
                ct = normalize_fa(reg.get("course"))
                if ct and canon_key(ct) not in seen:
                    seen.add(canon_key(ct))
                    t_courses.append({"title": ct, "group": reg.get("group", ""), "date": reg.get("date", ""), "attendance": 0})
        return {
            "ok": True,
            "name": teacher_name,
            "stats": t_obj or {"courses": len(t_courses), "attendance": 0, "unique": 0, "avg_attendance": 0, "repeat_rate": 0, "groups": [], "cost": 0},
            "bio": meta.get("bio", ""),
            "works": meta.get("works", ""),
            "courses": t_courses,
        }

    def save_teacher_meta(self, teacher_name: str, bio: str, works: str) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        suite.setdefault("teacher_meta", {})[canon_key(teacher_name)] = {
            "name": normalize_fa(teacher_name),
            "bio": str(bio or "").strip(),
            "works": str(works or "").strip(),
        }
        self._save_suite(suite)
        return {"ok": True}

    def get_participant_profile(self, person_key: str) -> dict[str, Any]:
        data = self.get_executive_analytics()
        target = next((p for p in data["participants"] if p["id"] == person_key or canon_key(p["name"]) == canon_key(person_key)), None)
        if not target:
            return {"ok": False, "error": "پرونده مخاطب یافت نشد."}
        return {"ok": True, "participant": target}

    def parse_porsline_file(self, file_path: str) -> dict[str, Any]:
        p = Path(file_path)
        if not p.is_file():
            return {"ok": False, "error": "فایل یافت نشد."}
        headers: list[str] = []
        raw_rows: list[list[Any]] = []
        ext = p.suffix.lower()
        try:
            if ext in (".xlsx", ".xlsm"):
                from openpyxl import load_workbook
                wb = load_workbook(p, read_only=True, data_only=True)
                ws = wb.active
                it = ws.iter_rows(values_only=True)
                first = next(it, None)
                if not first:
                    return {"ok": False, "error": "فایل اکسل خالی است."}
                headers = [normalize_fa(c) for c in first]
                for row in it:
                    if any(cell is not None and str(cell).strip() for cell in row):
                        raw_rows.append(list(row))
                wb.close()
            elif ext == ".csv":
                with p.open("r", encoding="utf-8-sig", errors="replace") as f:
                    reader = csv.reader(f)
                    headers = [normalize_fa(c) for c in next(reader, [])]
                    raw_rows = [r for r in reader if any(str(x).strip() for x in r)]
            else:
                return {"ok": False, "error": "فقط فایل‌های Excel (.xlsx) و CSV پشتیبانی می‌شوند."}
        except Exception as exc:
            return {"ok": False, "error": f"خطا در خواندن فایل: {exc}"}

        if not headers:
            return {"ok": False, "error": "ستون‌های فایل قابل شناسایی نیستند."}

        l_hdrs = [h.lower() for h in headers]
        pick = lambda kws: next((idx for idx, h in enumerate(l_hdrs) if any(k in h for k in kws)), -1)
        i_full = pick(("نام و نام خانوادگی", "نام کامل", "نام خانوادگی", "full name", "name"))
        i_first = pick(("نام کوچک", "نام"))
        i_last = pick(("نام خانوادگی", "فامیل", "شهرت"))
        i_phone = pick(("موبایل", "همراه", "تلفن", "تماس", "شماره", "phone", "mobile"))
        i_level = pick(("سطح", "پایه", "مقطع", "تحصیلات", "حوزه", "level"))

        cur = self.get_executive_analytics()
        known_phones = {x["phone"] for x in cur["participants"] if x.get("phone")}
        known_names = {canon_key(x["name"]) for x in cur["participants"]}

        cleaned = []
        seen_in_file: set[str] = set()
        new_cnt = 0
        ret_cnt = 0
        for row in raw_rows:
            cell_at = lambda idx: normalize_fa(row[idx]) if 0 <= idx < len(row) and row[idx] is not None else ""
            if i_first != -1 and i_last != -1 and i_first != i_last:
                full_name = f"{cell_at(i_first)} {cell_at(i_last)}".strip()
            elif i_full != -1:
                full_name = cell_at(i_full)
            else:
                full_name = cell_at(0)
            if not full_name or len(full_name) < 3:
                continue
            phone = normalize_phone(cell_at(i_phone)) if i_phone != -1 else ""
            level = cell_at(i_level) if i_level != -1 else ""
            dedup_k = phone or canon_key(full_name)
            if dedup_k in seen_in_file:
                continue
            seen_in_file.add(dedup_k)
            is_known = (phone and phone in known_phones) or (canon_key(full_name) in known_names)
            if is_known:
                ret_cnt += 1
            else:
                new_cnt += 1
            cleaned.append({"name": full_name, "phone": phone, "level": level, "is_new": not is_known})

        return {
            "ok": True, "file_name": p.name,
            "suggested_course": p.stem.replace("_", " ").replace("-", " "),
            "total_cleaned": len(cleaned), "new_count": new_cnt, "returning_count": ret_cnt,
            "participants": cleaned,
        }

    def commit_porsline_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        course = normalize_fa(payload.get("course_title") or "دوره جدید")
        group = normalize_fa(payload.get("group") or "دین‌شناسی")
        teacher = normalize_fa(payload.get("teacher") or "نامشخص")
        date_str = normalize_fa(payload.get("date") or "")
        rows = payload.get("participants") or []
        if not rows:
            return {"ok": False, "error": "لیست شرکت‌کنندگان خالی است."}
        regs = list(suite.get("registrations") or [])
        existing = {(canon_key(r.get("course")), r.get("phone") or canon_key(r.get("name"))) for r in regs}
        added = 0
        for r in rows:
            nm = normalize_fa(r.get("name"))
            ph = normalize_phone(r.get("phone"))
            k = (canon_key(course), ph or canon_key(nm))
            if not nm or k in existing:
                continue
            existing.add(k)
            regs.append({
                "name": nm, "phone": ph, "level": normalize_fa(r.get("level")),
                "course": course, "group": group, "teacher": teacher,
                "date": date_str, "year": extract_year(date_str) or "1405",
            })
            added += 1
        suite["registrations"] = regs
        self._save_suite(suite)
        return {"ok": True, "added": added, "total_registrations": len(regs)}

    def get_letters(self) -> list[dict[str, Any]]:
        return list(self._ensure_suite_file().get("letters") or [])

    def delete_letter(self, letter_id: str) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        suite["letters"] = [x for x in (suite.get("letters") or []) if x.get("id") != letter_id]
        self._save_suite(suite)
        return {"ok": True}

    def get_events(self) -> list[dict[str, Any]]:
        events = list(self._ensure_suite_file().get("events") or [])
        for ev in events:
            if "eitaa_ads" not in ev:
                ev["eitaa_ads"] = ev.get("press_links") or []
            st = ev.get("stages") or {}
            if "eitaa_ads" not in st:
                st["eitaa_ads"] = bool(st.get("press")) or bool(ev.get("eitaa_ads"))
            ev["stages"] = st
        return events

    def save_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        suite = self._ensure_suite_file()
        events = list(suite.get("events") or [])
        eid = str(payload.get("id") or f"evt_{int(datetime.now().timestamp() * 1000)}")
        ads = payload.get("eitaa_ads") if "eitaa_ads" in payload else (payload.get("press_links") or [])
        stages = dict(payload.get("stages") or {})
        if ads:
            stages["eitaa_ads"] = True
        item = {
            "id": eid,
            "title": normalize_fa(payload.get("title") or "رویداد بدون عنوان"),
            "group": normalize_fa(payload.get("group") or "دین‌شناسی"),
            "teacher": normalize_fa(payload.get("teacher") or ""),
            "date": normalize_fa(payload.get("date") or ""),
            "stages": stages,
            "eitaa_ads": ads,
        }
        idx = next((i for i, e in enumerate(events) if e.get("id") == eid), -1)
        if idx >= 0:
            events[idx] = item
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


# === EHADI_DEDUP_COURSES_PATCH ===
import re as _eh_re

if not getattr(ExecutiveAnalyticsEngine, "_ehadi_dedup_patched", False):
    _orig_eh_scan = ExecutiveAnalyticsEngine._scan_duckdb

    def _eh_norm_key(val: str) -> str:
        s = str(val or "").replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
        return _eh_re.sub(r"[\s\u200c\-_،,.؛:()«»]+", "", s).lower()

    def _dedup_eh_scan(self, *args, **kwargs):
        res = _orig_eh_scan(self, *args, **kwargs)
        if not isinstance(res, tuple) or not res:
            return res
        courses = res[0] or []
        seen = {}
        for c in courses:
            k_title = _eh_norm_key(c.get("title"))
            k_teacher = _eh_norm_key(c.get("teacher"))
            key = (k_title, k_teacher) if k_title else (str(id(c)), "")
            if key not in seen:
                seen[key] = dict(c)
            else:
                cur = seen[key]
                if int(c.get("attendance") or 0) > int(cur.get("attendance") or 0):
                    cur["attendance"] = c.get("attendance")
                if (not cur.get("group") or cur.get("group") == "نامشخص") and c.get("group"):
                    cur["group"] = c.get("group")
                if (not cur.get("year") or cur.get("year") == "نامشخص") and c.get("year"):
                    cur["year"] = c.get("year")
        return (list(seen.values()), *res[1:])

    ExecutiveAnalyticsEngine._scan_duckdb = _dedup_eh_scan
    ExecutiveAnalyticsEngine._ehadi_dedup_patched = True
