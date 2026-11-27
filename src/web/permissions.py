"""Roles, permissions and the RPC allowlist for the local web edition.

Deny by default: an RPC method that is not listed in ``METHOD_PERMS`` or
``DESKTOP_ONLY``/``CLIENT_SIDE`` cannot be called from the browser.
Access is granted to *roles*; a role is a set of permissions, so changing who
is responsible for something means changing a user's role, not code.
"""
from __future__ import annotations

ALL = "*"

ROLES: dict[str, dict] = {
    "admin": {"label": "مدیر ارشد (مدیرعامل / مدیر)", "perms": {ALL}},
    "office_head": {
        "label": "مسئول دفتر",
        "perms": {"dashboard.view", "students.view", "courses.view", "attendance.view", "registration.view", "decisions.view", "summaries.view"},
    },
    "alumni_affairs": {
        "label": "مسئول امور دانش‌آموختگان",
        "perms": {
            "dashboard.view", "students.view", "students.edit", "attendance.view", "attendance.edit",
            "registration.view", "registration.review", "blacklist.view", "blacklist.edit",
            "courses.view", "documents.manage", "summaries.view",
        },
    },
    "course_designer": {
        "label": "مسئول خلاصه دوره‌ها و طراحی آموزشی",
        "perms": {"dashboard.view", "students.view", "attendance.view", "courses.view", "courses.edit", "documents.manage", "summaries.view", "summaries.edit"},
    },
    "executive": {
        "label": "مسئول اجرایی",
        "perms": {"dashboard.view", "students.view", "attendance.view", "courses.view", "summaries.view"},
    },
    "speech_flag": {
        "label": "مسئول دوره خطابه و پرچمداران (موقت)",
        "perms": {"dashboard.view", "students.view", "attendance.view", "courses.view", "summaries.view"},
    },
}


def role_has(role: str, perm: str) -> bool:
    perms = ROLES.get(role, {}).get("perms", set())
    return ALL in perms or perm in perms


# Every call from the browser needs a logged-in user. "auth" = any logged-in user.
METHOD_PERMS: dict[str, str] = {
    # dashboards (NOTE: BI/executive payloads still contain finance sections;
    # per-section filtering is a follow-up)
    "get_dashboard_data": "dashboard.view",
    "get_bi_analytics": "dashboard.view",
    "get_bi_table_data": "dashboard.view",
    "get_executive_analytics": "dashboard.view",
    "get_event_pipelines": "dashboard.view",
    "get_letter_registry": "dashboard.view",
    "get_chunk_preview": "ai.use",
    # finance
    "save_finance_category_rule": "finance.edit",
    # documents / ingestion
    "scan_documents": "documents.manage",
    "save_dropped_chunk": "documents.manage",
    "get_duplicate_files": "documents.manage",
    "delete_registered_letter": "documents.manage",
    # AI assistant: its SQL can read every table, so admin-only for now
    "get_chat_history": "ai.use",
    "clear_chat_history": "ai.use",
    "ask_ai": "ai.use",
    "ask_ai_stream": "ai.use",
    "test_gemini_connection": "settings.edit",
    # settings / branding
    "get_settings": "settings.edit",
    "save_settings": "settings.edit",
    "get_branding_settings": "auth",
    "save_branding_settings": "settings.edit",
    # people
    "get_teacher_profile": "courses.view",
    "save_teacher_meta": "courses.edit",
    "get_participant_profile": "students.view",
    "save_participant_meta": "students.edit",
    "merge_duplicate_records": "students.edit",
    "reject_duplicate_records": "students.edit",
    "resolve_fuzzy_pair": "students.edit",
    "delete_entity_alias": "students.edit",
    "get_teacher_exact_stats": "courses.view",
    "get_audit_rows": "dashboard.view",
    # registration (Porsline)
    "commit_porsline_import": "registration.review",
    "select_and_preview_porsline": "registration.review",   # file comes from a browser upload
    # exports: the server writes into a temp folder and the browser downloads the file
    "export_table_excel": "dashboard.view",
    "export_report_docx": "dashboard.view",
    "export_report_pdf": "dashboard.view",
    "export_executive_report": "dashboard.view",
    "export_attendance_sheet": "attendance.view",
    "export_filtered_participants_excel": "students.view",
    # pickers replaced by browser uploads
    "add_files_dialog": "documents.manage",
    "select_logo_dialog": "settings.edit",
    "select_font_dialog": "settings.edit",
    # taxonomy (web-only services, see services.py)
    "get_taxonomy": "courses.view",
    "save_summary": "summaries.edit",
    "delete_summary": "summaries.edit",
    "get_summary": "summaries.view",
    "list_summaries": "summaries.view",
    "summary_options": "summaries.view",
    "summary_stats": "summaries.view",
    "save_workgroup": "courses.edit",
    "delete_workgroup": "courses.edit",
    "save_subgroup": "courses.edit",
    "delete_subgroup": "courses.edit",
    # events
    "save_event_pipeline": "courses.edit",
    "delete_event_pipeline": "courses.edit",
    # decisions
    "get_decisions": "decisions.view",
    "save_decision_item": "decisions.edit",
    "delete_decision_item": "decisions.edit",
    # memory / brain
    "get_memory_state": "brain.manage",
    "add_user_rule": "brain.manage",
    "delete_user_rule": "brain.manage",
    "get_brain_config": "brain.manage",
    "save_brain_config": "brain.manage",
    "add_compound_name": "brain.manage",
    "delete_compound_name": "brain.manage",
    "set_entity_type_override": "brain.manage",
    "set_hours_policy": "brain.manage",
    "set_course_hour_override": "brain.manage",
    "get_brain_history": "brain.manage",
    "undo_brain_action": "brain.manage",
    "export_brain_config": "brain.manage",
    "import_brain_config": "brain.manage",
    # admin
    "create_backup_now": "backup.run",
    "get_audit_logs": "logs.view",
    "run_health_check": "logs.view",
    "export_diagnostic_bundle": "logs.view",
    "get_recent_errors": "logs.view",
    "clear_error_logs": "logs.view",
    "log_frontend_error": "auth",
    "set_voice_preferences": "auth",
}

# Never callable from the web (no one may erase the audit trail).
FORBIDDEN = {"clear_audit_logs"}

# Window chrome: answered in the browser, never sent to the server.
CLIENT_SIDE = {
    "set_window", "minimize", "close", "get_window_bounds", "set_window_bounds", "toggle_maximize",
    "is_window_maximized", "toggle_maximize_window", "begin_window_resize", "start_window_resize",
    "resize_window_absolute", "toggle_fullscreen_window",
}

# Need a native file dialog / local OS or microphone. Replaced by upload/download
# endpoints in later commits; until then they answer with a clear message.
DESKTOP_ONLY = {
    "open_raw_docs_folder", "open_file_path", "open_registered_file",
    "listen_voice_command", "stop_voice_recording", "process_voice",
}

ALLOWED_UPLOAD_EXT = {".xlsx", ".xls", ".csv", ".docx", ".pptx", ".pdf", ".txt", ".accdb", ".mdb"}

# Methods whose native "open file" dialog is replaced by a browser upload, with the extensions each accepts.
UPLOAD_METHODS: dict[str, set[str]] = {
    "add_files_dialog": {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv", ".accdb", ".mdb"},
    "select_logo_dialog": {".png", ".jpg", ".jpeg", ".webp"},
    "select_font_dialog": {".ttf", ".otf", ".woff2"},
    "select_and_preview_porsline": {".xlsx", ".xls", ".csv"},
}
# Methods whose native "save file" dialog is replaced by a temp folder + browser download.
DOWNLOAD_METHODS = {
    "export_table_excel", "export_report_docx", "export_report_pdf", "export_executive_report",
    "export_attendance_sheet", "export_filtered_participants_excel",
}
UPLOAD_ANY_EXT = ALLOWED_UPLOAD_EXT | {e for v in UPLOAD_METHODS.values() for e in v}
