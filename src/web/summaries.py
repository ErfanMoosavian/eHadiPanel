"""Course-session summaries (خلاصه جلسه) and the statistics built on them.

Stored in a small SQLite file (``session_summaries.sqlite3``) next to the auth store, so the
analytics engines (DuckDB / LanceDB) are untouched. Every summary belongs to one course session;
the workgroup is resolved through the taxonomy, so the same roll-up / split switch applies.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from src.core.taxonomy import Taxonomy, key

MAX_TEXT = 8000
STATUSES = ("draft", "final")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS summaries(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  course TEXT NOT NULL, workgroup TEXT NOT NULL DEFAULT '', subgroup TEXT NOT NULL DEFAULT '',
  session_no INTEGER NOT NULL DEFAULT 1, session_date TEXT NOT NULL DEFAULT '',
  teacher TEXT NOT NULL DEFAULT '', topic TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '', key_points TEXT NOT NULL DEFAULT '[]', homework TEXT NOT NULL DEFAULT '',
  registered INTEGER, present INTEGER,
  teacher_rating REAL, content_rating REAL, notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft',
  author TEXT NOT NULL DEFAULT '', author_name TEXT NOT NULL DEFAULT '',
  created REAL NOT NULL, updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sum_course ON summaries(course);
"""


def _int(v: Any, lo: int, hi: int) -> int | None:
    if v in (None, ""):
        return None
    try:
        n = int(float(str(v).translate(_DIGITS)))
    except (TypeError, ValueError):
        raise ValueError("عدد نامعتبر است.")
    if not lo <= n <= hi:
        raise ValueError(f"عدد باید بین {lo} و {hi} باشد.")
    return n


def _rating(v: Any) -> float | None:
    n = _int(v, 1, 5)
    return None if n is None else float(n)


def _text(v: Any, limit: int = MAX_TEXT) -> str:
    return str(v or "").strip()[:limit]


class SummaryStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def run(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock, self._conn() as c:
            return c.execute(sql, args).fetchall()

    def exec(self, sql: str, args: tuple = ()) -> int:
        with self._lock, self._conn() as c:
            cur = c.execute(sql, args)
            return cur.lastrowid or 0


def _row(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    try:
        d["key_points"] = json.loads(d.get("key_points") or "[]")
    except ValueError:
        d["key_points"] = []
    d["attendance_rate"] = (round(100 * d["present"] / d["registered"], 1)
                            if d.get("registered") and d.get("present") is not None else None)
    return d


class SummaryService:
    """RPC methods (each needs an entry in ``permissions.METHOD_PERMS``)."""

    def __init__(self, store: SummaryStore, taxonomy: Taxonomy, api: Any = None) -> None:
        self._s, self._tax, self._api = store, taxonomy, api

    # -- helpers
    @staticmethod
    def _user() -> tuple[str, str]:
        from src.web import server  # lazy: the server module owns the per-call context
        u = getattr(server._ctx, "user", None)
        return (getattr(u, "username", "") or "", getattr(u, "display_name", "") or "")

    def _split(self) -> bool:
        try:
            cfg = self._api.get_brain_config()
            return bool((cfg.get("config") or {}).get("split_subgroups"))
        except Exception:
            return False

    # -- CRUD
    def save_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            course = _text(data.get("course"), 200)
            if not course:
                return {"ok": False, "error": "نام دوره الزامی است."}
            sid = _int(data.get("id"), 1, 10**9)
            wg_label = _text(data.get("workgroup"), 120)
            res = self._tax.resolve(wg_label, course)
            workgroup = res.get("workgroup") or wg_label
            subgroup = res.get("subgroup") or ""
            registered, present = _int(data.get("registered"), 0, 100000), _int(data.get("present"), 0, 100000)
            if registered is not None and present is not None and present > registered:
                return {"ok": False, "error": "تعداد حاضران از تعداد ثبت‌نامی‌ها بیشتر است."}
            points = [p for p in (_text(x, 400) for x in (data.get("key_points") or [])[:30]) if p]
            status = data.get("status") if data.get("status") in STATUSES else "draft"
            row = (course, workgroup or "", subgroup or "", _int(data.get("session_no"), 1, 500) or 1,
                   _text(data.get("session_date"), 20).translate(_DIGITS), _text(data.get("teacher"), 120),
                   _text(data.get("topic"), 300), _text(data.get("summary")), json.dumps(points, ensure_ascii=False),
                   _text(data.get("homework"), 2000), registered, present,
                   _rating(data.get("teacher_rating")), _rating(data.get("content_rating")),
                   _text(data.get("notes"), 2000), status)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        now = time.time()
        if sid:
            if not self._s.run("SELECT id FROM summaries WHERE id=?", (sid,)):
                return {"ok": False, "error": "خلاصه پیدا نشد."}
            self._s.exec("""UPDATE summaries SET course=?,workgroup=?,subgroup=?,session_no=?,session_date=?,teacher=?,topic=?,
                summary=?,key_points=?,homework=?,registered=?,present=?,teacher_rating=?,content_rating=?,notes=?,status=?,
                updated=? WHERE id=?""", (*row, now, sid))
            return {"ok": True, "id": sid}
        username, name = self._user()
        new_id = self._s.exec("""INSERT INTO summaries(course,workgroup,subgroup,session_no,session_date,teacher,topic,summary,
            key_points,homework,registered,present,teacher_rating,content_rating,notes,status,author,author_name,created,updated)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (*row, username, name, now, now))
        return {"ok": True, "id": new_id}

    def get_summary(self, summary_id: int) -> dict[str, Any]:
        rows = self._s.run("SELECT * FROM summaries WHERE id=?", (int(summary_id or 0),))
        return {"ok": True, "summary": _row(rows[0])} if rows else {"ok": False, "error": "خلاصه پیدا نشد."}

    def delete_summary(self, summary_id: int) -> dict[str, Any]:
        self._s.exec("DELETE FROM summaries WHERE id=?", (int(summary_id or 0),))
        return {"ok": True}

    def list_summaries(self, course: str = "", workgroup: str = "", teacher: str = "", query: str = "",
                       status: str = "", limit: int = 200) -> dict[str, Any]:
        rows = [_row(r) for r in self._s.run("SELECT * FROM summaries ORDER BY course, session_no, id")]
        split = self._split()
        for r in rows:
            r["group"] = self._tax.display_group(r["workgroup"], r["course"], split)
        q = key(query)
        out = []
        for r in rows:
            if course and r["course"] != course: continue
            if workgroup and workgroup not in (r["group"], r["workgroup"]): continue
            if teacher and key(teacher) != key(r["teacher"]): continue
            if status and r["status"] != status: continue
            if q and q not in key(" ".join([r["course"], r["teacher"], r["topic"], r["summary"], " ".join(r["key_points"])])):
                continue
            out.append(r)
        limit = max(1, min(int(limit or 200), 1000))
        return {"ok": True, "total": len(out), "items": out[-limit:] if len(out) > limit else out}

    def summary_options(self) -> dict[str, Any]:
        courses = [r["course"] for r in self._s.run("SELECT DISTINCT course FROM summaries ORDER BY course")]
        teachers = [r["teacher"] for r in self._s.run("SELECT DISTINCT teacher FROM summaries WHERE teacher<>'' ORDER BY teacher")]
        return {"ok": True, "courses": courses, "teachers": teachers,
                "workgroups": [w["name"] for w in self._tax.snapshot().get("workgroups", [])]}

    # -- statistics
    def summary_stats(self) -> dict[str, Any]:
        """Attendance curve per course, workgroup / teacher roll-ups, content-quality averages and data gaps."""
        rows = [_row(r) for r in self._s.run("SELECT * FROM summaries ORDER BY course, session_no")]
        split = self._split()

        def avg(xs: list[float]) -> float | None:
            xs = [x for x in xs if x is not None]
            return round(sum(xs) / len(xs), 2) if xs else None

        def block(items: list[dict]) -> dict[str, Any]:
            return {"sessions": len(items), "final": sum(1 for i in items if i["status"] == "final"),
                    "avg_attendance": avg([i["attendance_rate"] for i in items]),
                    "avg_teacher_rating": avg([i["teacher_rating"] for i in items]),
                    "avg_content_rating": avg([i["content_rating"] for i in items])}

        by_course: dict[str, list[dict]] = {}
        by_group: dict[str, list[dict]] = {}
        by_teacher: dict[str, list[dict]] = {}
        for r in rows:
            by_course.setdefault(r["course"], []).append(r)
            by_group.setdefault(self._tax.display_group(r["workgroup"], r["course"], split) or "بدون کارگروه", []).append(r)
            if r["teacher"]:
                by_teacher.setdefault(r["teacher"], []).append(r)

        courses = []
        for name, items in by_course.items():
            curve = [{"session_no": i["session_no"], "attendance": i["attendance_rate"]} for i in items]
            rates = [c["attendance"] for c in curve if c["attendance"] is not None]
            nos = sorted({i["session_no"] for i in items})
            gaps = [n for n in range(nos[0], nos[-1] + 1) if n not in nos] if nos else []
            courses.append({"course": name, "group": self._tax.display_group(items[0]["workgroup"], name, split),
                            **block(items), "curve": curve, "missing_sessions": gaps,
                            "drop_from_first": round(rates[0] - rates[-1], 1) if len(rates) >= 2 else None})
        courses.sort(key=lambda c: c["course"])
        return {"ok": True, "total": len(rows), "overall": block(rows), "courses": courses,
                "groups": [{"group": g, **block(v)} for g, v in sorted(by_group.items())],
                "teachers": [{"teacher": t, **block(v)} for t, v in sorted(by_teacher.items())],
                "low_attendance": [{"course": c["course"], "avg_attendance": c["avg_attendance"]}
                                   for c in courses if c["avg_attendance"] is not None and c["avg_attendance"] < 60],
                "drafts": sum(1 for r in rows if r["status"] == "draft")}
