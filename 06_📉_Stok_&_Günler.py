
import streamlit as st
import pandas as pd
import datetime as dt
from catering.auth import require_login, guard_demo
from catering.db import get_conn
from catering.utils import df_to_excel_bytes, require_cols, simple_table_pdf

require_login()
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Stok & Günler", layout="wide")
st.title("📉 Stok & Kritik Uyarılar")

with get_conn() as conn:
    mats = pd.read_sql_query(
        '''
        SELECT m.name, u.name as unit, m.stock_qty, m.min_stock,
               (m.stock_qty - m.min_stock) as diff
        FROM materials m JOIN units u ON u.id=m.unit_id
        ORDER BY diff ASC, m.name
        ''',
        conn,
    )

if mats.empty:
    st.info("Malzeme yok.")
else:
    st.subheader("Kritik stok altına inenler")
    crit = mats[mats["stock_qty"] < mats["min_stock"]]
    if crit.empty:
        st.success("Kritik stok altına düşen yok ✅")
    else:
        st.dataframe(crit, use_container_width=True)

    st.subheader("Tüm stoklar")
    st.dataframe(mats, use_container_width=True)
