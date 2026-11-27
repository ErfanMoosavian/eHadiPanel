import pytest

from src.core.taxonomy import Taxonomy
from src.web.summaries import SummaryService, SummaryStore


@pytest.fixture()
def svc(tmp_path):
    return SummaryService(SummaryStore(tmp_path / "s.sqlite3"), Taxonomy(tmp_path / "t.json"), api=None)


def mk(svc, course="دوره قرآن", no=1, reg=40, pres=30, **kw):
    d = {"course": course, "session_no": no, "registered": reg, "present": pres, "workgroup": "کارگروه قرآن", **kw}
    r = svc.save_summary(d)
    assert r["ok"], r
    return r["id"]


def test_validation(svc):
    assert not svc.save_summary({"course": ""})["ok"]
    assert not svc.save_summary({"course": "x", "registered": 5, "present": 9})["ok"]       # present > registered
    assert not svc.save_summary({"course": "x", "teacher_rating": 9})["ok"]
    assert not svc.save_summary({"course": "x", "session_no": "abc"})["ok"]
    assert not svc.save_summary({"course": "x", "id": 999})["ok"]                            # unknown id


def test_persian_digits_and_crud(svc):
    sid = mk(svc, session_no="۳", session_date="۱۴۰۵/۰۸/۲۰", key_points=["الف", " ", "ب"])
    s = svc.get_summary(sid)["summary"]
    assert s["session_no"] == 3 and s["session_date"] == "1405/08/20" and s["key_points"] == ["الف", "ب"]
    assert svc.save_summary({"id": sid, "course": "دوره قرآن", "topic": "تازه"})["ok"]
    assert svc.get_summary(sid)["summary"]["topic"] == "تازه"
    svc.delete_summary(sid)
    assert not svc.get_summary(sid)["ok"]


def test_subgroup_resolved_from_course_title(svc):
    sid = mk(svc, course="انس با الکافی ۲", workgroup="")
    s = svc.get_summary(sid)["summary"]
    assert s["workgroup"] == "کارگروه حدیث" and s["subgroup"] == "حدیث‌خوانی"


def test_filters(svc):
    mk(svc, "الف", 1, teacher="استاد ۱", topic="نماز")
    mk(svc, "ب", 1, teacher="استاد ۲", topic="روزه", status="final")
    assert svc.list_summaries()["total"] == 2
    assert svc.list_summaries(course="الف")["total"] == 1
    assert svc.list_summaries(query="روزه")["total"] == 1
    assert svc.list_summaries(status="final")["total"] == 1
    assert svc.list_summaries(teacher="استاد ۲")["total"] == 1


def test_stats(svc):
    mk(svc, "دوره الف", 1, 100, 90, teacher="م", teacher_rating=5)
    mk(svc, "دوره الف", 2, 100, 70, teacher="م", teacher_rating=3)
    mk(svc, "دوره الف", 4, 100, 50, teacher="م")                      # session 3 was never recorded
    mk(svc, "دوره ب", 1, 100, 40, status="final")
    st = svc.summary_stats()
    a = next(c for c in st["courses"] if c["course"] == "دوره الف")
    assert a["avg_attendance"] == 70.0 and a["missing_sessions"] == [3] and a["drop_from_first"] == 40.0
    assert a["avg_teacher_rating"] == 4.0
    assert [x["course"] for x in st["low_attendance"]] == ["دوره ب"]
    assert st["drafts"] == 3 and st["overall"]["final"] == 1
    assert st["teachers"][0]["teacher"] == "م"
