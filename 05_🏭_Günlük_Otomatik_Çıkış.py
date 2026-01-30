
import streamlit as st
import pandas as pd
import datetime as dt
from catering.auth import require_login, guard_demo
from catering.db import get_conn
from catering.utils import df_to_excel_bytes, require_cols, simple_table_pdf

require_login()
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Günlük Otomatik Çıkış", layout="wide")
st.title("🏭 Günlük Otomatik Malzeme Çıkışı")

meal_labels = {"breakfast": "Kahvaltı", "lunch": "Öğle", "dinner": "Akşam", "snack": "Ara Öğün"}

date = st.date_input("Tarih seç", value=dt.date.today())

def menu_for(d):
    with get_conn() as conn:
        return pd.read_sql_query(
            '''
            SELECT m.meal_type, d.name as dish_name, d.id as dish_id
            FROM menus m JOIN dishes d ON d.id=m.dish_id
            WHERE m.menu_date=?
            ORDER BY m.meal_type, d.name
            ''',
            conn,
            params=(d,),
        )

menu = menu_for(date.isoformat())
if menu.empty:
    st.info("Bu tarihte menü yok (04 sayfasından planla).")
    st.stop()

st.subheader("Menü")
st.dataframe(menu[["meal_type", "dish_name"]].replace({"meal_type": meal_labels}), use_container_width=True)

st.subheader("Kişi sayıları")
counts = {}
cols = st.columns(4)
for i, (meal, label) in enumerate(meal_labels.items()):
    with cols[i]:
        counts[meal] = st.number_input(label, min_value=0, value=0, step=1, key=f"c_{meal}")

with get_conn() as conn:
    recipe = pd.read_sql_query(
        '''
        SELECT ri.dish_id, m.name as material_name, m.id as material_id, u.name as unit, ri.qty_per_person
        FROM recipe_items ri
        JOIN materials m ON m.id=ri.material_id
        JOIN units u ON u.id=m.unit_id
        ''',
        conn,
    )

usage = []
for meal, people in counts.items():
    if people <= 0:
        continue
    dishes_meal = menu[menu["meal_type"] == meal]
    for _, row in dishes_meal.iterrows():
        dish_id = int(row["dish_id"])
        part = recipe[recipe["dish_id"] == dish_id]
        for _, r in part.iterrows():
            usage.append(
                {
                    "material_id": int(r["material_id"]),
                    "material_name": r["material_name"],
                    "unit": r["unit"],
                    "qty": float(r["qty_per_person"]) * int(people),
                }
            )

if not usage:
    st.info("Kişi sayısı girince tüketim hesaplanır.")
    st.stop()

dfu = pd.DataFrame(usage).groupby(["material_id", "material_name", "unit"], as_index=False)["qty"].sum()

st.subheader("Hesaplanan tüketim (düzenlenebilir)")
edited = st.data_editor(
    dfu,
    use_container_width=True,
    num_rows="fixed",
    column_config={"qty": st.column_config.NumberColumn("Çıkış miktarı", min_value=0.0, step=0.1)},
)

if st.button("✅ Onayla ve Depodan Düş", type="primary"):
    with get_conn() as conn:
        cur = conn.cursor()
        for _, r in edited.iterrows():
            mid = int(r["material_id"])
            qty = float(r["qty"])
            cur.execute("SELECT stock_qty FROM materials WHERE id=?", (mid,))
            stock = float(cur.fetchone()[0])
            if stock < qty:
                st.error(f"Stok yetersiz: {r['material_name']} (stok {stock}, istenen {qty})")
                st.stop()

        for _, r in edited.iterrows():
            mid = int(r["material_id"])
            qty = float(r["qty"])
            cur.execute("UPDATE materials SET stock_qty = stock_qty - ? WHERE id=?", (qty, mid))
            cur.execute(
                '''
                INSERT INTO stock_moves(move_date, material_id, direction, qty, ref_type, ref_id, note)
                VALUES(?,?,?,?,?,?,?)
                ''',
                (date.isoformat(), mid, "out", qty, "auto_out", date.isoformat(), "Günlük otomatik çıkış"),
            )
        conn.commit()

    st.success("Çıkış yapıldı.")
    st.rerun()
