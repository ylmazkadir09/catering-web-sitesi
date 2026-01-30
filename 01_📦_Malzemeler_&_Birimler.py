
import streamlit as st
import pandas as pd
import datetime as dt
from catering.auth import require_login, guard_demo
from catering.db import get_conn
from catering.utils import df_to_excel_bytes, require_cols, simple_table_pdf

require_login()
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Malzemeler & Birimler", layout="wide")
st.title("📦 Malzemeler & Birimler")

def units_df():
    with get_conn() as conn:
        return pd.read_sql_query("SELECT id,name FROM units ORDER BY name", conn)

def materials_df():
    with get_conn() as conn:
        return pd.read_sql_query(
            '''
            SELECT m.id, m.name, u.name AS unit, m.stock_qty, m.min_stock
            FROM materials m JOIN units u ON u.id=m.unit_id
            ORDER BY m.name
            ''', conn)

tab1, tab2 = st.tabs(["➕ Manuel Ekle", "📥📤 Excel"])

with tab1:
    c1,c2 = st.columns([1,2])
    with c1:
        st.subheader("Birim Ekle")
        with st.form("unit_add"):
            uname = st.text_input("Birim adı (kg, lt, adet...)")
            ok = st.form_submit_button("Ekle")
        if ok:
            if uname.strip():
                with get_conn() as conn:
                    conn.execute("INSERT OR IGNORE INTO units(name) VALUES(?)", (uname.strip(),))
                    conn.commit()
                st.success("Birim eklendi.")
                st.rerun()
    with c2:
        st.subheader("Malzeme Ekle")
        u = units_df()
        if u.empty:
            st.info("Önce birim ekle.")
        else:
            umap = dict(zip(u["name"], u["id"]))
            with st.form("mat_add"):
                mname = st.text_input("Malzeme adı")
                unit_name = st.selectbox("Birim", list(umap.keys()))
                qty = st.number_input("Depodaki miktar", min_value=0.0, value=0.0, step=0.5)
                min_stock = st.number_input("Kritik stok (uyarı)", min_value=0.0, value=0.0, step=0.5)
                ok2 = st.form_submit_button("Kaydet")
            if ok2:
                if not mname.strip():
                    st.error("Malzeme adı boş olamaz.")
                else:
                    with get_conn() as conn:
                        conn.execute(
                            '''
                            INSERT INTO materials(name,unit_id,stock_qty,min_stock)
                            VALUES(?,?,?,?)
                            ON CONFLICT(name) DO UPDATE SET
                                unit_id=excluded.unit_id,
                                stock_qty=excluded.stock_qty,
                                min_stock=excluded.min_stock
                            ''',
                            (mname.strip(), int(umap[unit_name]), float(qty), float(min_stock))
                        )
                        conn.commit()
                    st.success("Malzeme kaydedildi (varsa güncellendi).")
                    st.rerun()

    st.divider()
    st.subheader("Liste / Düzenle")
    df = materials_df()
    if df.empty:
        st.info("Henüz malzeme yok.")
    else:
        edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")
        if st.button("💾 Değişiklikleri Kaydet"):
            with get_conn() as conn:
                cur = conn.cursor()
                u = units_df()
                umap = dict(zip(u["name"], u["id"]))
                for _, r in edited.iterrows():
                    if not str(r["name"]).strip():
                        continue
                    unit_name = str(r["unit"]).strip()
                    unit_id = umap.get(unit_name)
                    if not unit_id:
                        cur.execute("INSERT OR IGNORE INTO units(name) VALUES(?)", (unit_name,))
                        cur.execute("SELECT id FROM units WHERE name=?", (unit_name,))
                        unit_id = cur.fetchone()[0]
                    cur.execute(
                        "UPDATE materials SET name=?, unit_id=?, stock_qty=?, min_stock=? WHERE id=?",
                        (str(r["name"]).strip(), int(unit_id), float(r["stock_qty"] or 0), float(r["min_stock"] or 0), int(r["id"]))
                    )
                conn.commit()
            st.success("Kaydedildi.")
            st.rerun()

with tab2:
    st.subheader("Excel ile Malzeme Yükle / İndir")
    st.markdown(
        '''
**Şablon:**
- Sheet **Units**: `name`
- Sheet **Materials**: `name`, `unit`, `stock_qty`, `min_stock`
'''
    )

    template = df_to_excel_bytes({
        "Units": pd.DataFrame({"name":["kg","lt","adet"]}),
        "Materials": pd.DataFrame({"name":["Pirinç"],"unit":["kg"],"stock_qty":[10],"min_stock":[2]})
    })
    st.download_button(
        "⬇️ Örnek Şablon İndir",
        data=template,
        file_name="materials_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    cur_units = units_df()[["name"]]
    cur_mats = materials_df()[["name","unit","stock_qty","min_stock"]]
    cur_bytes = df_to_excel_bytes({"Units": cur_units, "Materials": cur_mats})
    st.download_button(
        "⬇️ Mevcut Veriyi İndir",
        data=cur_bytes,
        file_name="materials_current.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    up = st.file_uploader("📤 Excel yükle", type=["xlsx"])
    if up is not None:
        try:
            sheets = pd.read_excel(up, sheet_name=None)
            with get_conn() as conn:
                cur = conn.cursor()
                if "Units" in sheets:
                    dfu = sheets["Units"].fillna("")
                    require_cols(dfu, ["name"], "Units")
                    for _, r in dfu.iterrows():
                        n = str(r["name"]).strip()
                        if n:
                            cur.execute("INSERT OR IGNORE INTO units(name) VALUES(?)", (n,))
                if "Materials" in sheets:
                    dfm = sheets["Materials"].fillna("")
                    require_cols(dfm, ["name","unit"], "Materials")
                    for _, r in dfm.iterrows():
                        n = str(r["name"]).strip()
                        un = str(r["unit"]).strip()
                        if not n or not un:
                            continue
                        cur.execute("INSERT OR IGNORE INTO units(name) VALUES(?)", (un,))
                        cur.execute("SELECT id FROM units WHERE name=?", (un,))
                        unit_id = cur.fetchone()[0]
                        stock_qty = float(r.get("stock_qty",0) or 0)
                        min_stock = float(r.get("min_stock",0) or 0)
                        cur.execute(
                            '''
                            INSERT INTO materials(name,unit_id,stock_qty,min_stock)
                            VALUES(?,?,?,?)
                            ON CONFLICT(name) DO UPDATE SET
                                unit_id=excluded.unit_id,
                                stock_qty=excluded.stock_qty,
                                min_stock=excluded.min_stock
                            ''',
                            (n, unit_id, stock_qty, min_stock)
                        )
                conn.commit()
            st.success("Excel içe aktarma tamam.")
            st.rerun()
        except Exception as e:
            st.error(f"Excel hatası: {e}")
