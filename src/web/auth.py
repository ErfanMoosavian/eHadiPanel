"""Local-web authentication: users, scrypt password hashes, server-side sessions.

Standard library only (sqlite3 + hashlib.scrypt). No default passwords exist;
accounts are created with ``manage_users.py``.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from src.web.permissions import ROLES

SESSION_TTL = 12 * 3600
MAX_FAILS = 5
LOCK_SECONDS = 300
MIN_PASSWORD_LEN = 8

_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    role: str
    active: bool


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, dk_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._fails: dict[str, list[float]] = {}
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS users(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                  display_name TEXT NOT NULL,
                  role TEXT NOT NULL,
                  pw_hash TEXT NOT NULL,
                  active INTEGER NOT NULL DEFAULT 1,
                  created_at REAL NOT NULL,
                  last_login REAL
                );
                CREATE TABLE IF NOT EXISTS sessions(
                  token_hash TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL REFERENCES users(id),
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL
                );
                """
            )

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            c = sqlite3.connect(self.db_path, timeout=10)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            try:
                yield c
                c.commit()
            finally:
                c.close()

    # ---- users -----------------------------------------------------------
    @staticmethod
    def _user(r: sqlite3.Row) -> User:
        return User(r["id"], r["username"], r["display_name"], r["role"], bool(r["active"]))

    def create_user(self, username: str, display_name: str, role: str, password: str) -> User:
        username = (username or "").strip()
        if not username or not display_name.strip():
            raise ValueError("نام کاربری و نام نمایشی لازم است.")
        if role not in ROLES:
            raise ValueError(f"نقش نامعتبر: {role}")
        if len(password) < MIN_PASSWORD_LEN:
            raise ValueError(f"رمز عبور باید حداقل {MIN_PASSWORD_LEN} نویسه باشد.")
        with self._conn() as c:
            try:
                cur = c.execute(
                    "INSERT INTO users(username,display_name,role,pw_hash,created_at) VALUES(?,?,?,?,?)",
                    (username, display_name.strip(), role, hash_password(password), time.time()),
                )
            except sqlite3.IntegrityError:
                raise ValueError("این نام کاربری قبلاً ثبت شده است.")
            return self._user(c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())

    def list_users(self) -> list[User]:
        with self._conn() as c:
            return [self._user(r) for r in c.execute("SELECT * FROM users ORDER BY id")]

    def set_password(self, username: str, password: str) -> None:
        if len(password) < MIN_PASSWORD_LEN:
            raise ValueError(f"رمز عبور باید حداقل {MIN_PASSWORD_LEN} نویسه باشد.")
        with self._conn() as c:
            cur = c.execute("UPDATE users SET pw_hash=? WHERE username=?", (hash_password(password), username))
            if cur.rowcount == 0:
                raise ValueError("کاربر یافت نشد.")
            c.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)", (username,))

    def set_role(self, username: str, role: str) -> None:
        if role not in ROLES:
            raise ValueError(f"نقش نامعتبر: {role}")
        with self._conn() as c:
            if c.execute("UPDATE users SET role=? WHERE username=?", (role, username)).rowcount == 0:
                raise ValueError("کاربر یافت نشد.")

    def set_active(self, username: str, active: bool) -> None:
        with self._conn() as c:
            if c.execute("UPDATE users SET active=? WHERE username=?", (1 if active else 0, username)).rowcount == 0:
                raise ValueError("کاربر یافت نشد.")
            if not active:
                c.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)", (username,))

    # ---- login / sessions ------------------------------------------------
    def _locked(self, key: str, now: float) -> bool:
        recent = [t for t in self._fails.get(key, []) if now - t < LOCK_SECONDS]
        self._fails[key] = recent
        return len(recent) >= MAX_FAILS

    def login(self, username: str, password: str, client: str = "") -> str | None:
        """Returns a session token, or None. Failed attempts are throttled per user and per client."""
        now = time.time()
        keys = (f"u:{(username or '').lower()}", f"c:{client}")
        with self._lock:
            if any(self._locked(k, now) for k in keys):
                return None
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE username=?", (username or "",)).fetchone()
            # Always run one scrypt so unknown users cost the same as wrong passwords.
            ok = verify_password(password or "", row["pw_hash"] if row else hash_password("x"))
            if not (row and row["active"] and ok):
                with self._lock:
                    for k in keys:
                        self._fails.setdefault(k, []).append(now)
                return None
            with self._lock:
                for k in keys:
                    self._fails.pop(k, None)
            token = secrets.token_urlsafe(32)
            c.execute("INSERT INTO sessions VALUES(?,?,?,?)", (_token_hash(token), row["id"], now, now + SESSION_TTL))
            c.execute("UPDATE users SET last_login=? WHERE id=?", (now, row["id"]))
            c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            return token

    def user_for_token(self, token: str | None) -> User | None:
        if not token:
            return None
        with self._conn() as c:
            r = c.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.expires_at>? AND u.active=1",
                (_token_hash(token), time.time()),
            ).fetchone()
            return self._user(r) if r else None

    def logout(self, token: str | None) -> None:
        if token:
            with self._conn() as c:
                c.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
