"""Manage local-web accounts.  No default passwords are ever created.

  python manage_users.py roles
  python manage_users.py list
  python manage_users.py add USERNAME "نام نمایشی" ROLE      (password is prompted)
  python manage_users.py passwd USERNAME
  python manage_users.py role USERNAME ROLE
  python manage_users.py disable USERNAME | enable USERNAME
"""
from __future__ import annotations

import getpass
import sys

from src.core.config import Config
from src.web.auth import AuthStore
from src.web.permissions import ROLES


def _store() -> AuthStore:
    return AuthStore(Config.DATA_DIR / "web_auth.sqlite3")


def _ask_password() -> str:
    p1 = getpass.getpass("رمز عبور جدید: ")
    if p1 != getpass.getpass("تکرار رمز عبور: "):
        raise ValueError("دو رمز یکسان نیستند.")
    return p1


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "roles":
            for k, v in ROLES.items():
                print(f"{k:16} {v['label']}")
        elif cmd == "list":
            for u in _store().list_users():
                print(f"{u.username:16} {u.role:16} {'فعال' if u.active else 'غیرفعال':8} {u.display_name}")
        elif cmd == "add" and len(args) == 3:
            u = _store().create_user(args[0], args[1], args[2], _ask_password())
            print(f"ساخته شد: {u.username} ({u.role})")
        elif cmd == "passwd" and len(args) == 1:
            _store().set_password(args[0], _ask_password())
            print("رمز عبور تغییر کرد و نشست‌های قبلی بسته شد.")
        elif cmd == "role" and len(args) == 2:
            _store().set_role(args[0], args[1])
            print("نقش تغییر کرد.")
        elif cmd in {"disable", "enable"} and len(args) == 1:
            _store().set_active(args[0], cmd == "enable")
            print("انجام شد.")
        else:
            print(__doc__)
            return 2
    except ValueError as exc:
        print(f"خطا: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
