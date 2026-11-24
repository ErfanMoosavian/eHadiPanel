"""Course taxonomy: workgroup (کارگروه) -> subgroup (زیرگروه) -> course -> session.

The data files only carry a free-text "group" label per course. This module owns the
institute's *structure*: which workgroups exist, which subgroups belong to which workgroup, and
how raw labels / course titles map onto them, so statistics can be shown either rolled up
(حدیث‌خوانی counted inside کارگروه حدیث) or split (حدیث‌خوانی shown on its own).

Stored as JSON next to the other app data; no extra dependency.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

_PUNCT_RX = re.compile(r"[\s‌‏‎()\[\]{}«»\"'،,.:؛;\-–—_/\\]+")
_FA_FIX = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "ٱ": "ا", "آ": "ا"})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
MAX_NAME = 80

DEFAULT: dict[str, Any] = {
    "version": 1,
    "workgroups": [
        {"name": "کارگروه دین شناسی", "aliases": []},
        {"name": "کارگروه تاریخ", "aliases": []},
        {"name": "کارگروه قرآن", "aliases": []},
        {"name": "کارگروه فقه", "aliases": []},
        {"name": "کارگروه حدیث", "aliases": []},
        {"name": "تربیت سخنران و مبلغ", "aliases": []},
    ],
    "subgroups": [
        {
            "name": "حدیث‌خوانی",
            "label": "حدیث‌خوانی (انس با الکافی)",
            "workgroup": "کارگروه حدیث",
            "aliases": ["انس با الکافی", "انس با کافی", "حدیث خوانی"],
            "course_keywords": ["انس با الکافی", "انس با کافی", "کتاب التوحید"],
        }
    ],
}


def key(text: Any) -> str:
    """Spelling-insensitive comparison key (digits, ی/ک, ZWNJ, spaces, punctuation, case)."""
    s = str(text or "").translate(_FA_FIX).translate(_DIGITS).lower()
    return _PUNCT_RX.sub("", s)


def _clean_list(items: Any) -> list[str]:
    out: list[str] = []
    for x in items or []:
        s = re.sub(r"\s+", " ", str(x or "")).strip()
        if s and key(s) not in {key(o) for o in out}:
            out.append(s[:MAX_NAME])
    return out


class Taxonomy:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data = self._load()

    # ---- persistence -------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data.get("workgroups"), list) and isinstance(data.get("subgroups"), list):
                    return data
            except Exception:
                pass
        data = json.loads(json.dumps(DEFAULT, ensure_ascii=False))
        self._write(data)
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # atomic: a crash never leaves a half-written file

    def _save(self) -> None:
        self._write(self._data)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data, ensure_ascii=False))

    # ---- lookup ------------------------------------------------------------
    def _wg(self, name: str) -> dict | None:
        k = key(name)
        return next((w for w in self._data["workgroups"] if key(w["name"]) == k), None)

    def resolve(self, group_label: str, course_title: str = "") -> dict[str, str | None]:
        """Map a raw label (and optionally a course title) to {"workgroup", "subgroup", "label"}."""
        gk, ck = key(group_label), key(course_title)
        with self._lock:
            sub_hit = None
            if gk:
                for s in self._data["subgroups"]:
                    names = [s["name"], s.get("label") or "", *s.get("aliases", [])]
                    if gk in {key(n) for n in names if n}:
                        sub_hit = s
                        break
            wg_hit = None
            if gk:
                for w in self._data["workgroups"]:
                    if gk in {key(w["name"]), *(key(a) for a in w.get("aliases", []))}:
                        wg_hit = w
                        break
            if sub_hit is None and ck:
                for s in self._data["subgroups"]:
                    if wg_hit is not None and key(wg_hit["name"]) != key(s["workgroup"]):
                        continue  # the file's own group label wins over a keyword hint
                    if any(key(kw) and key(kw) in ck for kw in s.get("course_keywords", [])):
                        sub_hit = s
                        break
            if sub_hit is not None:
                return {"workgroup": sub_hit["workgroup"], "subgroup": sub_hit["name"],
                        "label": sub_hit.get("label") or sub_hit["name"]}
            if wg_hit is not None:
                return {"workgroup": wg_hit["name"], "subgroup": None, "label": wg_hit["name"]}
            return {"workgroup": None, "subgroup": None, "label": None}

    def display_group(self, group_label: str, course_title: str = "", split: bool = False) -> str:
        """The label statistics should use: rolled up into the workgroup, or the subgroup on its own."""
        r = self.resolve(group_label, course_title)
        if r["workgroup"] is None:
            return group_label
        return (r["label"] if (split and r["subgroup"]) else r["workgroup"]) or group_label

    # ---- editing -----------------------------------------------------------
    def save_workgroup(self, name: str, aliases: list[str] | None = None, old_name: str = "") -> dict[str, Any]:
        name = re.sub(r"\s+", " ", str(name or "")).strip()[:MAX_NAME]
        if not name:
            return {"ok": False, "error": "نام کارگروه خالی است."}
        with self._lock:
            existing = self._wg(old_name) if old_name else None
            if old_name and existing is None:
                return {"ok": False, "error": "کارگروه مورد ویرایش پیدا نشد."}
            clash = self._wg(name)
            if clash is not None and clash is not existing:  # adding a name that exists is an error, not an overwrite
                return {"ok": False, "error": "کارگروهی با این نام وجود دارد."}
            if any(key(s["name"]) == key(name) or key(s.get("label") or "") == key(name) for s in self._data["subgroups"]):
                return {"ok": False, "error": "این نام برای یک زیرگروه استفاده شده است."}
            if existing is None:
                self._data["workgroups"].append({"name": name, "aliases": _clean_list(aliases)})
            else:
                if key(existing["name"]) != key(name):  # rename: keep the subgroups attached
                    for s in self._data["subgroups"]:
                        if key(s["workgroup"]) == key(existing["name"]):
                            s["workgroup"] = name
                existing["name"] = name
                if aliases is not None:
                    existing["aliases"] = _clean_list(aliases)
            self._save()
        return {"ok": True}

    def delete_workgroup(self, name: str) -> dict[str, Any]:
        with self._lock:
            w = self._wg(name)
            if w is None:
                return {"ok": False, "error": "کارگروه پیدا نشد."}
            if any(key(s["workgroup"]) == key(w["name"]) for s in self._data["subgroups"]):
                return {"ok": False, "error": "ابتدا زیرگروه‌های این کارگروه را حذف یا منتقل کنید."}
            self._data["workgroups"].remove(w)
            self._save()
        return {"ok": True}

    def save_subgroup(self, name: str, workgroup: str, aliases: list[str] | None = None,
                      course_keywords: list[str] | None = None, label: str = "", old_name: str = "") -> dict[str, Any]:
        name = re.sub(r"\s+", " ", str(name or "")).strip()[:MAX_NAME]
        if not name:
            return {"ok": False, "error": "نام زیرگروه خالی است."}
        with self._lock:
            w = self._wg(workgroup)
            if w is None:
                return {"ok": False, "error": "کارگروه انتخاب‌شده وجود ندارد."}
            existing = next((s for s in self._data["subgroups"] if key(s["name"]) == key(old_name)), None) if old_name else None
            if old_name and existing is None:
                return {"ok": False, "error": "زیرگروه مورد ویرایش پیدا نشد."}
            clash = next((s for s in self._data["subgroups"] if key(s["name"]) == key(name)), None)
            if clash is not None and clash is not existing:
                return {"ok": False, "error": "زیرگروهی با این نام وجود دارد."}
            if self._wg(name) is not None:
                return {"ok": False, "error": "این نام برای یک کارگروه استفاده شده است."}
            rec = {"name": name, "label": (label or "").strip()[:MAX_NAME] or name, "workgroup": w["name"],
                   "aliases": _clean_list(aliases), "course_keywords": _clean_list(course_keywords)}
            if existing is None:
                self._data["subgroups"].append(rec)
            else:
                existing.update(rec if aliases is not None or course_keywords is not None
                                else {k: v for k, v in rec.items() if k not in ("aliases", "course_keywords")})
            self._save()
        return {"ok": True}

    def delete_subgroup(self, name: str) -> dict[str, Any]:
        with self._lock:
            s = next((x for x in self._data["subgroups"] if key(x["name"]) == key(name)), None)
            if s is None:
                return {"ok": False, "error": "زیرگروه پیدا نشد."}
            self._data["subgroups"].remove(s)
            self._save()
        return {"ok": True}


_instance: Taxonomy | None = None
_instance_lock = threading.Lock()


def get_taxonomy() -> Taxonomy:
    """Process-wide instance, stored in the app's storage folder."""
    global _instance
    with _instance_lock:
        if _instance is None:
            from src.core.config import Config
            _instance = Taxonomy(Config.STORAGE_DIR / "taxonomy.json")
        return _instance
