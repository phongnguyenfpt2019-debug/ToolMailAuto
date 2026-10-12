"""
auth_service.py
---------------
Xac thuc dang nhap:
- Admin: admin / doitruongsg1
- User: Email co trong danh sach Nhan Su (HR), mat khau do nguoi dung tu dang ky.
Tat ca user/mat khau luu trong bang `login_users` (Danh sach Login).
"""
import os
from datetime import datetime
import database
import nhansu_service

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "doitruongsg1")

# Email duoc cap quyen ADMIN (dang nhap bang mat khau tu dang ky)
ADMIN_EMAILS = set(filter(None, [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "phuongnam.phongnh5@fpt.net").split(",")]))


def is_admin_email(email: str) -> bool:
    return (email or "").strip().lower() in ADMIN_EMAILS


def init_auth_table():
    conn = database.get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_users (
            id BIGSERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT,
            last_login TEXT,
            role TEXT DEFAULT 'USER'
        )
    """)
    # Email mac dinh luon la ADMIN
    for e in ADMIN_EMAILS:
        conn.execute("UPDATE login_users SET role = 'ADMIN' WHERE username = ?", (e,))
    conn.commit()
    conn.close()


def get_role(username: str) -> str:
    if is_admin_email(username):
        return 'ADMIN'
    u = get_user(username)
    return (u.get('role') or 'USER') if u else 'USER'


def set_role(user_id: int, role: str):
    conn = database.get_connection()
    conn.execute("UPDATE login_users SET role = ? WHERE id = ? AND username NOT IN ({})".format(
        ",".join("?" * len(ADMIN_EMAILS))), (role, user_id, *ADMIN_EMAILS))
    conn.commit()
    conn.close()


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def find_hr_by_email(email: str):
    """Tra ve row nhan su neu email co trong HR, nguoc lai None."""
    e = _norm(email)
    if not e:
        return None
    for r in nhansu_service.get_cached_or_fetch():
        if _norm(nhansu_service.get_email(r)) == e:
            return r
    return None


def get_user(username: str):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM login_users WHERE username = ?", (_norm(username),)).fetchone()
    conn.close()
    return dict(row) if row else None


def register_user(username: str, password: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO login_users (username, password, created_at, last_login, role) VALUES (?, ?, ?, ?, ?)",
        (_norm(username), password, now, now, 'ADMIN' if is_admin_email(username) else 'USER'))
    conn.commit()
    conn.close()


def touch_login(username: str):
    conn = database.get_connection()
    conn.execute("UPDATE login_users SET last_login = ? WHERE username = ?",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), _norm(username)))
    conn.commit()
    conn.close()


def list_users():
    conn = database.get_connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, username, password, created_at, last_login, COALESCE(role, 'USER') AS role FROM login_users ORDER BY id ASC").fetchall()]
    conn.close()
    return rows


def update_password(user_id: int, password: str):
    conn = database.get_connection()
    conn.execute("UPDATE login_users SET password = ? WHERE id = ?", (password, user_id))
    conn.commit()
    conn.close()


def delete_user(user_id: int):
    conn = database.get_connection()
    conn.execute("DELETE FROM login_users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
