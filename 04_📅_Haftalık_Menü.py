
import streamlit as st
import pandas as pd
import datetime as dt
from catering.auth import require_login, guard_demo
from catering.db import get_conn
from catering.utils import df_to_excel_bytes, require_cols, simple_table_pdf

require_login()
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Haftalık Menü", layout="wide")
st.title("📅 Haftalık Menü Planlama")

def dishes():
    with get_conn() as conn:
        return pd.read_sql_query("SELECT id, name as dish_name FROM dishes ORDER BY name", conn)

ddf = dishes()
if ddf.empty:
    st.info("Önce yemek ekle (03 sayfası).")
    st.stop()

dish_options = ddf["dish_name"].tolist()
id_map = dict(zip(ddf["dish_name"], ddf["id"]))

week_monday = st.date_input(
    "Haftanın Pazartesi tarihi",
    value=dt.date.today() - dt.timedelta(days=dt.date.today().weekday()),
)
if week_monday.weekday() != 0:
    st.warning("Lütfen Pazartesi seç. (Sistem sadece Pazartesi ile haftayı başlatır.)")

days = [week_monday + dt.timedelta(days=i) for i in range(7)]

meal_rules = {"breakfast": 5, "lunch": 5, "dinner": 5, "snack": 3}
meal_labels = {"breakfast": "Kahvaltı", "lunch": "Öğle", "dinner": "Akşam", "snack": "Ara Öğün"}

def existing_for(date_str):
    with get_conn() as conn:
        return pd.read_sql_query(
            '''
            SELECT m.meal_type, d.name as dish_name
            FROM menus m JOIN dishes d ON d.id=m.dish_id
            WHERE m.menu_date=?
            ''',
            conn,
            params=(date_str,),
        )

all_selections = {}

for day in days:
    st.subheader(day.strftime("%Y-%m-%d"))
    ex = existing_for(day.isoformat())
    for meal, maxn in meal_rules.items():
        default = ex[ex["meal_type"] == meal]["dish_name"].tolist() if not ex.empty else []
        sel = st.multiselect(
            f"{meal_labels[meal]} (max {maxn})",
            dish_options,
            default=default,
            key=f"{day}_{meal}",
        )
        all_selections[(day.isoformat(), meal)] = sel[:maxn]
    st.divider()

if st.button("💾 Haftalık Menüyü Kaydet", type="primary"):
    with get_conn() as conn:
        cur = conn.cursor()
        for (date_str, meal), sels in all_selections.items():
            cur.execute("DELETE FROM menus WHERE menu_date=? AND meal_type=?", (date_str, meal))
            for dn in sels:
                cur.execute(
                    "INSERT INTO menus(menu_date, meal_type, dish_id) VALUES(?,?,?)",
                    (date_str, meal, int(id_map[dn])),
                )
        conn.commit()
    st.success("Menü kaydedildi.")
