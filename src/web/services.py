"""Web-only features that live beside ``AppAPI`` (the desktop class stays untouched).

A service is any object whose public methods become RPC methods; each one needs a permission
in ``permissions.METHOD_PERMS`` (a test enforces this).
"""
from __future__ import annotations

from typing import Any

from src.core.taxonomy import Taxonomy


class TaxonomyService:
    """Workgroup -> subgroup structure used by the statistics."""

    def __init__(self, api: Any, taxonomy: Taxonomy) -> None:
        self._api, self._tax = api, taxonomy

    def _changed(self, res: dict[str, Any]) -> dict[str, Any]:
        if res.get("ok") and hasattr(self._api, "_invalidate_caches"):
            self._api._invalidate_caches()  # statistics are cached; the structure just changed
        return res

    def get_taxonomy(self) -> dict[str, Any]:
        split = False
        try:
            cfg = self._api.get_brain_config()
            split = bool((cfg.get("config") or {}).get("split_subgroups"))
        except Exception:
            pass
        return {"ok": True, **self._tax.snapshot(), "split_subgroups": split}

    def save_workgroup(self, name: str, aliases: list | None = None, old_name: str = "") -> dict[str, Any]:
        return self._changed(self._tax.save_workgroup(name, aliases, old_name))

    def delete_workgroup(self, name: str) -> dict[str, Any]:
        return self._changed(self._tax.delete_workgroup(name))

    def save_subgroup(self, name: str, workgroup: str, aliases: list | None = None,
                      course_keywords: list | None = None, label: str = "", old_name: str = "") -> dict[str, Any]:
        return self._changed(self._tax.save_subgroup(name, workgroup, aliases, course_keywords, label, old_name))

    def delete_subgroup(self, name: str) -> dict[str, Any]:
        return self._changed(self._tax.delete_subgroup(name))
