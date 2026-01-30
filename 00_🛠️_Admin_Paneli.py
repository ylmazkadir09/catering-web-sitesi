import streamlit as st
import pandas as pd
import datetime as dt

from catering.auth import require_login, guard_demo
from catering.db import get_conn

require_login()
# admin should not be blocked by demo guard, but it also refreshes user + checks is_active
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Admin Paneli", layout="wide")
st.title("🛠️ Admin Paneli")

if not user or user.get("role") != "admin":
    st.error("Bu sayfa sadece admin içindir.")
    st.stop()

def users_df():
    with get_conn() as conn:
        return pd.read_sql_query(
            """
            SELECT id, first_name, last_name, email, username, role, demo_expires_at, is_active, created_at, last_login_at
            FROM users
            ORDER BY role DESC, created_at DESC
            """,
            conn,
        )

st.caption("Kullanıcıları aktif/pasif yapabilir, demo kullanıcıların kalan gününü görebilirsin.")

df = users_df()
if df.empty:
    st.info("Kayıtlı kullanıcı yok.")
    st.stop()

# demo kalan gün hesabı
def calc_days_left(exp):
    if not exp:
        return None
    try:
        return (dt.date.fromisoformat(exp) - dt.date.today()).days
    except Exception:
        return None

df["demo_days_left"] = df.apply(lambda r: calc_days_left(r["demo_expires_at"]) if r["role"]!="admin" else None, axis=1)
show = df[["id","username","first_name","last_name","email","role","demo_expires_at","demo_days_left","is_active","last_login_at"]]
st.dataframe(show, use_container_width=True)

st.divider()
st.subheader("Aktif/Pasif Güncelle")

user_map = {f"{r.username} ({r.first_name} {r.last_name})": int(r.id) for r in df.itertuples()}
label = st.selectbox("Kullanıcı seç", list(user_map.keys()))
uid = user_map[label]
row = df[df["id"] == uid].iloc[0]

if row["role"] == "admin":
    st.warning("Admin hesabını pasif yapmanı önermiyorum. (Yine de istersen yapabilirsin.)")

active = st.checkbox("Aktif", value=bool(int(row["is_active"])))
if st.button("💾 Kaydet", type="primary"):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_active=? WHERE id=?", (1 if active else 0, uid))
        conn.commit()
    st.success("Kaydedildi.")
    st.rerun()
