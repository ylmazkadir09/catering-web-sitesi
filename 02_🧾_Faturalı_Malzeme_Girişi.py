
import streamlit as st
import pandas as pd
import datetime as dt
from catering.auth import require_login, guard_demo
from catering.db import get_conn
from catering.utils import df_to_excel_bytes, require_cols, simple_table_pdf

require_login()
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Faturalı Malzeme Girişi", layout="wide")
st.title("🧾 Faturalı Malzeme Girişi")

def materials():
    with get_conn() as conn:
        return pd.read_sql_query(
            '''
            SELECT m.id, m.name as material_name, u.name as unit, m.stock_qty
            FROM materials m JOIN units u ON u.id=m.unit_id
            ORDER BY m.name
            ''', conn)

mdf = materials()
if mdf.empty:
    st.info("Önce malzeme ekle (01 sayfası).")
    st.stop()

with st.form("inv_form"):
    invoice_no = st.text_input("Fatura numarası")
    inv_date = st.date_input("Tarih", value=dt.date.today())
    st.caption("Aşağıya en fazla 50 satır ekleyebilirsin.")
    df = pd.DataFrame(columns=["material_name","unit","qty","total_amount","unit_price"])
    edited = st.data_editor(
        df, num_rows="dynamic", use_container_width=True,
        column_config={
            "material_name": st.column_config.SelectboxColumn("Malzeme", options=mdf["material_name"].tolist(), required=True),
            "unit": st.column_config.TextColumn("Birim", disabled=True),
            "qty": st.column_config.NumberColumn("Giriş miktarı", min_value=0.0, step=0.1, required=True),
            "total_amount": st.column_config.NumberColumn("Toplam tutar (TL)", min_value=0.0, step=0.1, required=True),
            "unit_price": st.column_config.NumberColumn("Birim fiyat (otomatik)", disabled=True),
        }
    )

    unit_map = dict(zip(mdf["material_name"], mdf["unit"]))
    if not edited.empty:
        edited["unit"] = edited["material_name"].map(unit_map)
        edited["unit_price"] = edited.apply(
            lambda r: (float(r["total_amount"])/float(r["qty"])) if (r.get("qty") and float(r["qty"])>0) else 0,
            axis=1
        )

    total_invoice = float(edited["total_amount"].fillna(0).sum()) if "total_amount" in edited else 0.0
    st.markdown(f"### 🧾 Fatura toplamı: **{total_invoice:.2f} TL**")

    ok = st.form_submit_button("✅ Kaydet")

if ok:
    if not invoice_no.strip():
        st.error("Fatura numarası boş olamaz.")
        st.stop()

    rows = edited.dropna(subset=["material_name","qty","total_amount"]).head(50)
    if rows.empty:
        st.error("En az 1 malzeme satırı ekle.")
        st.stop()

    mid_map = dict(zip(mdf["material_name"], mdf["id"]))
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO invoices(invoice_no, invoice_date) VALUES(?,?)",
            (invoice_no.strip(), inv_date.isoformat())
        )
        inv_id = cur.lastrowid

        for _, r in rows.iterrows():
            mat_id = int(mid_map[str(r["material_name"])])
            qty = float(r["qty"])
            total = float(r["total_amount"])
            unit_price = (total/qty) if qty > 0 else 0

            cur.execute(
                '''
                INSERT INTO invoice_items(invoice_id, material_id, qty, total_amount, unit_price)
                VALUES(?,?,?,?,?)
                ''',
                (inv_id, mat_id, qty, total, unit_price)
            )

            cur.execute("UPDATE materials SET stock_qty = stock_qty + ? WHERE id=?", (qty, mat_id))

            cur.execute(
                '''
                INSERT INTO stock_moves(move_date, material_id, direction, qty, ref_type, ref_id, note)
                VALUES(?,?,?,?,?,?,?)
                ''',
                (inv_date.isoformat(), mat_id, "in", qty, "invoice", str(inv_id), invoice_no.strip())
            )

        conn.commit()

    st.success("Fatura kaydedildi ve stoklar güncellendi.")
    st.rerun()
