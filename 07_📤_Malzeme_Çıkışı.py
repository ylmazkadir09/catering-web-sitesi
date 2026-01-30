
import streamlit as st
import pandas as pd
import datetime as dt
from catering.auth import require_login, guard_demo
from catering.db import get_conn
from catering.utils import df_to_excel_bytes, require_cols, simple_table_pdf

require_login()
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Malzeme Çıkışı", layout="wide")
st.title("📤 Malzeme Çıkışı")

with get_conn() as conn:
    mats = pd.read_sql_query(
        '''
        SELECT m.id, m.name as material_name, u.name as unit, m.stock_qty
        FROM materials m JOIN units u ON u.id=m.unit_id
        ORDER BY m.name
        ''',
        conn,
    )

if mats.empty:
    st.info("Önce malzeme ekle.")
    st.stop()

mid_map = dict(zip(mats["material_name"], mats["id"]))
unit_map = dict(zip(mats["material_name"], mats["unit"]))
stock_map = dict(zip(mats["material_name"], mats["stock_qty"]))

date = st.date_input("Tarih", value=dt.date.today())
mat = st.selectbox("Malzeme", mats["material_name"].tolist())
st.caption(f"Birim: {unit_map[mat]} | Stok: {stock_map[mat]}")
qty = st.number_input("Çıkış miktarı", min_value=0.0, value=0.0, step=0.1)
note = st.text_input("Açıklama (opsiyonel)")

if st.button("Çıkış Yap", type="primary"):
    if qty <= 0:
        st.error("Miktar 0 olamaz.")
    else:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT stock_qty FROM materials WHERE id=?", (int(mid_map[mat]),))
            stock = float(cur.fetchone()[0])
            if stock < float(qty):
                st.error(f"Stok yetersiz (stok {stock})")
                st.stop()
            cur.execute("UPDATE materials SET stock_qty = stock_qty - ? WHERE id=?", (float(qty), int(mid_map[mat])))
            cur.execute(
                '''
                INSERT INTO stock_moves(move_date, material_id, direction, qty, ref_type, ref_id, note)
                VALUES(?,?,?,?,?,?,?)
                ''',
                (date.isoformat(), int(mid_map[mat]), "out", float(qty), "manual_out", "", note.strip()),
            )
            conn.commit()
        st.success("Çıkış yapıldı.")
        st.rerun()
