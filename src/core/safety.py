import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.config import Config
from src.core.db_manager import format_jalali_now, iso_to_jalali

AUDIT_FILE = Config.LOGS_DIR / "audit_log.jsonl"
DECISIONS_FILE = Config.STORAGE_DIR / "decisions.json"


def log_audit(action: str, module: str, status: str = "ok", details: dict[str, Any] | None = None) -> None:
    try:
        Config.ensure_directories()
        entry = {
            "ts": format_jalali_now(include_time=True, fa_digits=True), "ts_iso": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "module": module,
            "status": status,
            "details": details or {},
        }
        with AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def get_recent_audits(limit: int = 50) -> list[dict[str, Any]]:
    if not AUDIT_FILE.exists():
        return []
    lines = AUDIT_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    out = []
    for ln in reversed(lines[-limit:]):
        try:
            rec = json.loads(ln)
            if rec.get("ts") and "-" in str(rec["ts"]) and len(str(rec["ts"])) >= 10 and str(rec["ts"])[:2] in ("19", "20"):
                rec["ts"] = iso_to_jalali(rec["ts"])
            out.append(rec)
        except Exception:
            continue
    return out


def create_snapshot_backup(tag: str = "manual") -> dict[str, Any]:
    try:
        Config.ensure_directories()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_dir = Config.BACKUPS_DIR / f"snap_{tag}_{stamp}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        for fname in ("ehadi.duckdb", "ehadi_suite.json", "branding.json", "decisions.json"):
            src = Config.STORAGE_DIR / fname
            if src.exists():
                shutil.copy2(src, dest_dir / fname)
                copied.append(fname)
        log_audit("backup_snapshot", "safety", "ok", {"tag": tag, "files": copied})
        return {"ok": True, "path": str(dest_dir), "files": copied}
    except Exception as exc:
        log_audit("backup_snapshot", "safety", "error", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}


def load_decisions() -> list[dict[str, Any]]:
    Config.ensure_directories()
    if not DECISIONS_FILE.exists():
        return []
    try:
        return json.loads(DECISIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_decision(payload: dict[str, Any]) -> dict[str, Any]:
    items = load_decisions()
    did = str(payload.get("id") or f"dec_{int(datetime.now().timestamp() * 1000)}")
    item = {
        "id": did,
        "title": str(payload.get("title") or "").strip(),
        "owner": str(payload.get("owner") or "مدیریت").strip(),
        "due": str(payload.get("due") or "").strip(),
        "done": bool(payload.get("done", False)),
        "created_at": payload.get("created_at") or format_jalali_now(include_time=False, fa_digits=True),
    }
    if not item["title"]:
        return {"ok": False, "error": "عنوان تصمیم خالی است."}
    idx = next((i for i, x in enumerate(items) if x.get("id") == did), -1)
    if idx >= 0:
        items[idx] = item
    else:
        items.insert(0, item)
    DECISIONS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    log_audit("decision_saved", "decisions", "ok", {"id": did, "title": item["title"], "done": item["done"]})
    return {"ok": True, "item": item, "decisions": items}


def delete_decision(decision_id: str) -> dict[str, Any]:
    all_items = load_decisions()
    target = next((x for x in all_items if x.get("id") == decision_id), None)
    items = [x for x in all_items if x.get("id") != decision_id]
    DECISIONS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    log_audit("decision_deleted", "decisions", "ok", {"id": decision_id, "title": (target or {}).get("title", "")})
    return {"ok": True, "decisions": items}


def clear_audit_logs() -> dict[str, Any]:
    try:
        if AUDIT_FILE.exists():
            AUDIT_FILE.write_text("", encoding="utf-8")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
