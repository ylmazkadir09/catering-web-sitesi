from __future__ import annotations
import hashlib
import datetime as dt
import streamlit as st

from .db import get_conn, ensure_seed_admin, init_db

def _hash_password(pw: str) -> str:
    # simple salted hash for demo (use bcrypt/argon2 in production)
    salt = "catering_salt_v3"
    return hashlib.sha256((salt + pw).encode("utf-8")).hexdigest()

def init_auth():
    init_db()
    ensure_seed_admin(password_hash=_hash_password("admin123"))

def signup(first_name: str, last_name: str, email: str, username: str, password: str):
    now = dt.datetime.utcnow()
    expires = (dt.date.today() + dt.timedelta(days=15)).isoformat()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users(first_name,last_name,email,username,password_hash,role,created_at,demo_expires_at,last_login_at,is_active)
            VALUES(?,?,?,?,?,'demo',?,?,NULL,1)
            """,
            (
                first_name.strip(),
                last_name.strip(),
                email.strip().lower(),
                username.strip(),
                _hash_password(password),
                now.isoformat(),
                expires,
            ),
        )
        conn.commit()

def refresh_user(user_id: int) -> dict | None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id=?", (int(user_id),))
        row = cur.fetchone()
        return dict(row) if row else None

def demo_days_left(user: dict) -> int | None:
    if not user or user.get("role") == "admin":
        return None
    exp = user.get("demo_expires_at")
    if not exp:
        return None
    try:
        exp_date = dt.date.fromisoformat(exp)
        return (exp_date - dt.date.today()).days
    except Exception:
        return None

def is_demo_expired(user: dict) -> bool:
    days = demo_days_left(user)
    return days is not None and days < 0

def is_active(user: dict) -> bool:
    # default active
    try:
        return int(user.get("is_active", 1)) == 1
    except Exception:
        return True

def login(username: str, password: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=?", (username.strip(),))
        row = cur.fetchone()
        if not row:
            return None
        if row["password_hash"] != _hash_password(password):
            return None

        user = dict(row)

        # inactive?
        if not is_active(user):
            raise PermissionError("Bu kullanıcı pasif durumda. Admin ile iletişime geç.")
        # demo expired?
        if is_demo_expired(user):
            raise PermissionError("Demo süren dolmuş 😕 (15 gün). Admin ile giriş yapabilir veya lisans alabilirsin.")

        cur.execute("UPDATE users SET last_login_at=? WHERE id=?", (dt.datetime.utcnow().isoformat(), row["id"]))
        conn.commit()
        return user

def require_login():
    if "user" not in st.session_state:
        st.switch_page("app.py")

def show_demo_badge():
    user = st.session_state.get("user")
    if not user:
        return
    if user.get("role") == "admin":
        return
    days = demo_days_left(user)
    if days is None:
        return
    if days < 0:
        st.sidebar.error("Demo bitti")
    else:
        st.sidebar.info(f"🎟️ Demo: {days} gün kaldı")

def guard_demo():
    user = st.session_state.get("user")
    if not user:
        return

    # refresh from DB so admin changes apply immediately
    fresh = refresh_user(user["id"])
    if fresh:
        st.session_state["user"] = fresh
        user = fresh

    # show badge always for demo users
    show_demo_badge()

    if not is_active(user):
        st.error("Hesabın pasif durumda. Admin ile iletişime geç.")
        st.stop()

    if is_demo_expired(user):
        st.error("Demo süren dolmuş 😕 (15 gün). Admin ile giriş yapabilir veya lisans alabilirsin.")
        st.stop()
