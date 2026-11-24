"""Workgroup -> subgroup taxonomy and its effect on the statistics."""
from __future__ import annotations

import pytest

import src.core.taxonomy as T
from src.core.taxonomy import Taxonomy


@pytest.fixture()
def tax(tmp_path):
    return Taxonomy(tmp_path / "taxonomy.json")


def test_subgroup_rolls_up_into_its_workgroup_or_stands_alone(tax):
    label = "حدیث‌خوانی (انس با الکافی)"
    assert tax.display_group(label, split=False) == "کارگروه حدیث"
    assert tax.display_group(label, split=True) == label
    assert tax.display_group("کارگروه حدیث", split=True) == "کارگروه حدیث"


def test_course_title_keyword_assigns_the_subgroup(tax):
    assert tax.display_group("کارگروه حدیث", "انس با کافی ـ ترم ۲", split=True) == "حدیث‌خوانی (انس با الکافی)"
    assert tax.display_group("کارگروه حدیث", "کتاب التوحید", split=False) == "کارگروه حدیث"
    assert tax.display_group("کارگروه حدیث", "شرح نهج‌البلاغه", split=True) == "کارگروه حدیث"
    # the file's own group wins over a keyword hint
    assert tax.display_group("کارگروه فقه", "انس با کافی", split=True) == "کارگروه فقه"


def test_spelling_variants_match(tax):
    for variant in ("حديث خوانی", "حدیث‌خوانی", "انس با الكافي"):
        assert tax.resolve(variant)["subgroup"] == "حدیث‌خوانی", variant
    assert tax.display_group("چیز ناشناخته") == "چیز ناشناخته"


def test_workgroup_and_subgroup_editing_rules(tax):
    assert tax.save_workgroup("کارگروه اخلاق")["ok"]
    assert not tax.save_workgroup("کارگروه  اخلاق")["ok"]                       # duplicate (spacing-insensitive)
    assert not tax.save_workgroup("کارگروه تازه", old_name="چنین کارگروهی نیست")["ok"]
    assert not tax.save_subgroup("ریزگروه", "کارگروه نامعلوم")["ok"]
    assert tax.save_subgroup("توحید", "کارگروه اخلاق", course_keywords=["توحید ۱"])["ok"]
    assert not tax.save_subgroup("توحید", "کارگروه اخلاق")["ok"]                    # duplicate subgroup is refused, not overwritten
    assert not tax.save_subgroup("کارگروه اخلاق", "کارگروه حدیث")["ok"]          # a subgroup cannot reuse a workgroup name
    assert not tax.delete_workgroup("کارگروه اخلاق")["ok"]                      # still has a subgroup
    assert tax.save_workgroup("کارگروه اخلاق و عرفان", old_name="کارگروه اخلاق")["ok"]
    assert tax.resolve("", "توحید ۱ مقدماتی")["workgroup"] == "کارگروه اخلاق و عرفان"   # rename kept the subgroup attached
    assert tax.delete_subgroup("توحید")["ok"] and tax.delete_workgroup("کارگروه اخلاق و عرفان")["ok"]


def test_persistence_and_corrupt_file(tmp_path):
    p = tmp_path / "t.json"
    a = Taxonomy(p)
    a.save_workgroup("کارگروه نمونه")
    assert Taxonomy(p).resolve("کارگروه نمونه")["workgroup"] == "کارگروه نمونه"
    p.write_text("{not json", encoding="utf-8")
    assert Taxonomy(p).resolve("کارگروه حدیث")["workgroup"] == "کارگروه حدیث"   # falls back to the defaults


# ---- the statistics engine (no DuckDB needed: the data scan is stubbed) ----------------------
def _course(i, title, group, att, hours, sessions, teacher):
    return {"course_uid": f"c{i}", "title": title, "group": group, "teacher": teacher, "year": "1404",
            "attendance": att, "hours": hours, "sessions": sessions, "date": "1404/06/01", "cost": 0,
            "file_name": "f", "source_sheet": "s", "row_index": i}


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "_instance", Taxonomy(tmp_path / "taxonomy.json"))
    from src.analytics.executive_engine import ExecutiveAnalyticsEngine
    e = ExecutiveAnalyticsEngine()
    courses = [
        _course(1, "شرح نهج‌البلاغه", "کارگروه حدیث", 30, 8, 4, "استاد الف"),
        _course(2, "انس با الکافی ترم ۱", "حدیث‌خوانی (انس با الکافی)", 50, 10, 5, "استاد ب"),
        _course(3, "فقه ۱", "کارگروه فقه", 20, 6, 3, "استاد ج"),
    ]
    monkeypatch.setattr(e, "_scan_duckdb", lambda data_mode="clean": (courses, [], []))
    monkeypatch.setattr(e, "_ensure_suite_file", lambda: {})
    return e


def _groups(res):
    return {g["name"]: g for g in res["groups"]}


def test_statistics_roll_subgroup_into_workgroup_by_default(engine):
    res = engine.get_executive_analytics({"data_mode": "raw", "split_subgroups": False})
    g = _groups(res)
    assert set(g) == {"کارگروه حدیث", "کارگروه فقه"}
    assert g["کارگروه حدیث"]["courses"] == 2 and g["کارگروه حدیث"]["hours"] == 18.0     # no double counting, nothing lost
    assert res["filters_meta"]["groups"] == ["کارگروه حدیث", "کارگروه فقه"]


def test_statistics_can_split_the_subgroup(engine):
    res = engine.get_executive_analytics({"data_mode": "raw", "split_subgroups": True})
    g = _groups(res)
    assert set(g) == {"کارگروه حدیث", "حدیث‌خوانی (انس با الکافی)", "کارگروه فقه"}
    assert g["کارگروه حدیث"]["courses"] == 1 and g["حدیث‌خوانی (انس با الکافی)"]["courses"] == 1
    total = sum(x["hours"] for x in res["groups"])
    assert total == 24.0                                                                # same total either way


def test_group_filter_follows_the_toggle(engine):
    rolled = engine.get_executive_analytics({"data_mode": "raw", "group": "کارگروه حدیث", "split_subgroups": False})
    split = engine.get_executive_analytics({"data_mode": "raw", "group": "کارگروه حدیث", "split_subgroups": True})
    assert {c["title"] for c in rolled["filtered_courses"]} == {"شرح نهج‌البلاغه", "انس با الکافی ترم ۱"}
    assert {c["title"] for c in split["filtered_courses"]} == {"شرح نهج‌البلاغه"}
