
import streamlit as st
import pandas as pd
import datetime as dt
from catering.auth import require_login, guard_demo
from catering.db import get_conn
from catering.utils import df_to_excel_bytes, require_cols, simple_table_pdf

require_login()
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Yemek & Reçete", layout="wide")
st.title("🍲 Yemek & Reçete")

def materials():
    with get_conn() as conn:
        return pd.read_sql_query(
            '''
            SELECT m.id, m.name as material_name, u.name as unit
            FROM materials m JOIN units u ON u.id=m.unit_id
            ORDER BY m.name
            ''', conn)

def dishes():
    with get_conn() as conn:
        return pd.read_sql_query("SELECT id, name as dish_name FROM dishes ORDER BY name", conn)

def recipe_items(dish_id:int):
    with get_conn() as conn:
        return pd.read_sql_query(
            '''
            SELECT ri.id, m.name as material_name, ri.qty_per_person, u.name as unit
            FROM recipe_items ri
            JOIN materials m ON m.id=ri.material_id
            JOIN units u ON u.id=m.unit_id
            WHERE ri.dish_id=?
            ORDER BY m.name
            ''', conn, params=(dish_id,))

tab1, tab2, tab3 = st.tabs(["🍽️ Yemekler", "🧾 Tarif", "📥📤 Excel"])

with tab1:
    st.subheader("Manuel yemek ekle")
    with st.form("dish_add"):
        dname = st.text_input("Yemek adı")
        ok = st.form_submit_button("Ekle")
    if ok:
        if dname.strip():
            with get_conn() as conn:
                conn.execute("INSERT OR IGNORE INTO dishes(name) VALUES(?)", (dname.strip(),))
                conn.commit()
            st.success("Yemek kaydedildi.")
            st.rerun()
        else:
            st.error("Yemek adı boş olamaz.")

    st.divider()
    st.subheader("Yemek listesi")
    st.dataframe(dishes(), use_container_width=True)

with tab2:
    st.subheader("Reçete düzenle (maks 30 kalem)")
    ddf = dishes()
    mdf = materials()

    if ddf.empty:
        st.info("Önce yemek ekle.")
    elif mdf.empty:
        st.info("Önce malzeme ekle (01 sayfası).")
    else:
        dish_name = st.selectbox("Yemek seç", ddf["dish_name"].tolist())
        dish_id = int(ddf[ddf["dish_name"] == dish_name].iloc[0]["id"])

        current = recipe_items(dish_id)
        base_rows = current[["material_name", "qty_per_person", "unit"]] if not current.empty else pd.DataFrame(
            columns=["material_name", "qty_per_person", "unit"]
        )

        mats_list = mdf["material_name"].tolist()
        unit_map = dict(zip(mdf["material_name"], mdf["unit"]))

        edited = st.data_editor(
            base_rows,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "material_name": st.column_config.SelectboxColumn("Malzeme", options=mats_list, required=True),
                "qty_per_person": st.column_config.NumberColumn("Kişi başı miktar", min_value=0.0, step=0.1, required=True),
                "unit": st.column_config.TextColumn("Birim", disabled=True),
            },
        )

        if not edited.empty:
            edited["unit"] = edited["material_name"].map(unit_map)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Reçeteyi Kaydet / Güncelle"):
                edited2 = edited.dropna(subset=["material_name", "qty_per_person"]).head(30)
                mid_map = dict(zip(mdf["material_name"], mdf["id"]))
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM recipe_items WHERE dish_id=?", (dish_id,))
                    for _, r in edited2.iterrows():
                        mn = str(r["material_name"]).strip()
                        if not mn:
                            continue
                        qty = float(r["qty_per_person"])
                        cur.execute(
                            "INSERT INTO recipe_items(dish_id, material_id, qty_per_person) VALUES(?,?,?)",
                            (dish_id, int(mid_map[mn]), qty),
                        )
                    conn.commit()
                st.success("Reçete kaydedildi.")
                st.rerun()
        with c2:
            if st.button("🗑️ Reçeteyi Sıfırla"):
                with get_conn() as conn:
                    conn.execute("DELETE FROM recipe_items WHERE dish_id=?", (dish_id,))
                    conn.commit()
                st.success("Silindi.")
                st.rerun()

with tab3:
    st.subheader("Excel ile Yemek / Reçete İçe Aktar - Dışa Aktar")
    st.markdown(
        '''
**Şablon (2 sheet):**
- **Dishes**: `dish_name`
- **RecipeItems**: `dish_name`, `material_name`, `qty`, `unit` (unit opsiyonel)

> `qty` = kişi başı miktar.
'''
    )

    template = df_to_excel_bytes(
        {
            "Dishes": pd.DataFrame({"dish_name": ["Mercimek Çorbası", "Tavuk Pilav"]}),
            "RecipeItems": pd.DataFrame(
                {
                    "dish_name": ["Mercimek Çorbası", "Mercimek Çorbası", "Tavuk Pilav"],
                    "material_name": ["Kırmızı Mercimek", "Tuz", "Pirinç"],
                    "qty": [0.25, 0.01, 0.20],
                    "unit": ["kg", "kg", "kg"],
                }
            ),
        }
    )
    st.download_button(
        "⬇️ Örnek Şablon İndir",
        data=template,
        file_name="recipes_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    try:
        ddf = dishes()[["dish_name"]]
        with get_conn() as conn:
            items = pd.read_sql_query(
                '''
                SELECT d.name AS dish_name, m.name AS material_name, ri.qty_per_person AS qty, u.name AS unit
                FROM recipe_items ri
                JOIN dishes d ON d.id=ri.dish_id
                JOIN materials m ON m.id=ri.material_id
                JOIN units u ON u.id=m.unit_id
                ORDER BY d.name, m.name
                ''',
                conn,
            )
        cur_bytes = df_to_excel_bytes({"Dishes": ddf, "RecipeItems": items})
        st.download_button(
            "⬇️ Mevcut Veriyi İndir",
            data=cur_bytes,
            file_name="recipes_current.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception:
        pass

    auto_create = st.checkbox("Eksik malzemeleri otomatik oluştur (unit kolonu varsa onu kullanır)", value=False)

    up = st.file_uploader("📤 Excel yükle", type=["xlsx"], key="recipes_upload")
    if up is not None:
        try:
            sheets = pd.read_excel(up, sheet_name=None)
            with get_conn() as conn:
                cur = conn.cursor()

                if "Dishes" in sheets:
                    d = sheets["Dishes"].fillna("")
                    require_cols(d, ["dish_name"], "Dishes")
                    for _, r in d.iterrows():
                        n = str(r["dish_name"]).strip()
                        if n:
                            cur.execute("INSERT OR IGNORE INTO dishes(name) VALUES(?)", (n,))

                if "RecipeItems" in sheets:
                    ri = sheets["RecipeItems"].fillna("")
                    require_cols(ri, ["dish_name", "material_name", "qty"], "RecipeItems")
                    mdf = materials()
                    mid_map = dict(zip(mdf["material_name"], mdf["id"]))

                    for _, r in ri.iterrows():
                        dn = str(r["dish_name"]).strip()
                        mn = str(r["material_name"]).strip()
                        if not dn or not mn:
                            continue
                        try:
                            qty = float(r["qty"])
                        except Exception:
                            continue

                        cur.execute("INSERT OR IGNORE INTO dishes(name) VALUES(?)", (dn,))
                        cur.execute("SELECT id FROM dishes WHERE name=?", (dn,))
                        dish_id = cur.fetchone()[0]
                        mat_id = mid_map.get(mn)
                        if not mat_id:
                            if not auto_create:
                                continue
                            # malzeme yoksa oluştur
                            unit_name = str(r.get("unit", "")).strip()
                            if not unit_name:
                                unit_name = "adet"
                            cur.execute("INSERT OR IGNORE INTO units(name) VALUES(?)", (unit_name,))
                            cur.execute("SELECT id FROM units WHERE name=?", (unit_name,))
                            unit_id = cur.fetchone()[0]
                            cur.execute(
                                "INSERT OR IGNORE INTO materials(name, unit_id, stock_qty, min_stock) VALUES(?,?,0,0)",
                                (mn, unit_id),
                            )
                            # map'i tazele
                            cur.execute("SELECT id FROM materials WHERE name=?", (mn,))
                            mat_id = cur.fetchone()[0]
                            mid_map[mn] = mat_id
                        cur.execute(
                            '''
                            INSERT INTO recipe_items(dish_id,material_id,qty_per_person)
                            VALUES(?,?,?)
                            ON CONFLICT(dish_id,material_id) DO UPDATE SET qty_per_person=excluded.qty_per_person
                            ''',
                            (dish_id, int(mat_id), qty),
                        )

                conn.commit()

            st.success("Excel içe aktarma tamam.")
            st.rerun()

        except Exception as e:
            st.error(f"Excel hatası: {e}")
