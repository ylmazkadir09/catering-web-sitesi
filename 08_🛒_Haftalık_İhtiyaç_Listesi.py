
import streamlit as st
import pandas as pd
import datetime as dt
from catering.auth import require_login, guard_demo
from catering.db import get_conn
from catering.utils import df_to_excel_bytes, require_cols, simple_table_pdf

require_login()
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Haftalık İhtiyaç Listesi", layout="wide")
st.title("🛒 Haftalık İhtiyaç Listesi")

monday = st.date_input("Pazartesi seç", value=dt.date.today() - dt.timedelta(days=dt.date.today().weekday()))
if monday.weekday() != 0:
    st.warning("Sadece Pazartesi seçilmeli.")

days = [monday + dt.timedelta(days=i) for i in range(7)]
meal_types = ["breakfast", "lunch", "dinner", "snack"]
meal_labels = {"breakfast": "Kahvaltı", "lunch": "Öğle", "dinner": "Akşam", "snack": "Ara Öğün"}

with get_conn() as conn:
    menu = pd.read_sql_query(
        '''
        SELECT m.menu_date, m.meal_type, d.id as dish_id, d.name as dish_name
        FROM menus m JOIN dishes d ON d.id=m.dish_id
        WHERE m.menu_date BETWEEN ? AND ?
        ORDER BY m.menu_date, m.meal_type, d.name
        ''',
        conn,
        params=(days[0].isoformat(), days[-1].isoformat()),
    )
    recipe = pd.read_sql_query(
        '''
        SELECT ri.dish_id, ri.qty_per_person, m.id as material_id, m.name as material_name,
               u.name as unit, m.stock_qty, m.min_stock
        FROM recipe_items ri
        JOIN materials m ON m.id=ri.material_id
        JOIN units u ON u.id=m.unit_id
        ''',
        conn,
    )

if menu.empty:
    st.info("Bu hafta için menü yok (04 sayfasından planla).")
    st.stop()

st.subheader("Menü Özeti")
st.dataframe(menu[["menu_date", "meal_type", "dish_name"]].replace({"meal_type": meal_labels}), use_container_width=True)

st.subheader("Kişi sayıları (günlük)")
counts_df = pd.DataFrame([{"date": d.isoformat(), "breakfast": 0, "lunch": 0, "dinner": 0, "snack": 0} for d in days])
counts_edited = st.data_editor(
    counts_df,
    use_container_width=True,
    num_rows="fixed",
    column_config={m: st.column_config.NumberColumn(meal_labels[m], min_value=0, step=1) for m in meal_types},
)

if st.button("📌 İhtiyacı Hesapla"):
    usage = []
    for _, cr in counts_edited.iterrows():
        d = cr["date"]
        for meal in meal_types:
            people = int(cr[meal])
            if people <= 0:
                continue
            dishes_meal = menu[(menu["menu_date"] == d) & (menu["meal_type"] == meal)]
            for _, dr in dishes_meal.iterrows():
                dish_id = int(dr["dish_id"])
                part = recipe[recipe["dish_id"] == dish_id]
                for _, r in part.iterrows():
                    usage.append(
                        {
                            "material_id": int(r["material_id"]),
                            "material_name": r["material_name"],
                            "unit": r["unit"],
                            "needed_qty": float(r["qty_per_person"]) * people,
                        }
                    )

    if not usage:
        st.warning("Kişi sayısı girilmedi.")
        st.stop()

    need_df = pd.DataFrame(usage).groupby(["material_id", "material_name", "unit"], as_index=False)["needed_qty"].sum()
    stock_df = recipe[["material_id", "stock_qty", "min_stock"]].drop_duplicates("material_id")
    need_df = need_df.merge(stock_df, on="material_id", how="left")
    need_df["current_qty"] = need_df["stock_qty"].fillna(0)
    need_df["after_qty"] = need_df["current_qty"] - need_df["needed_qty"]
    need_df["critical"] = need_df["after_qty"] < need_df["min_stock"].fillna(0)
    need_df["order_qty"] = (need_df["needed_qty"] - need_df["current_qty"]).clip(lower=0)

    show = need_df[
        ["material_name", "unit", "needed_qty", "current_qty", "min_stock", "after_qty", "critical", "order_qty"]
    ].sort_values(["critical", "material_name"], ascending=[False, True])

    st.subheader("Hesaplanan ihtiyaç (sipariş miktarını düzenleyebilirsin)")
    edited = st.data_editor(
        show,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "order_qty": st.column_config.NumberColumn("Sipariş miktarı", min_value=0.0, step=0.1),
            "critical": st.column_config.CheckboxColumn("Kritik", disabled=True),
        },
    )

    if st.button("✅ Siparişi Onayla ve PDF Al"):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orders(week_monday, created_at) VALUES(?,?)",
                (monday.isoformat(), dt.datetime.utcnow().isoformat()),
            )
            order_id = cur.lastrowid

            mats = pd.read_sql_query("SELECT id,name FROM materials", conn)
            mat_map = dict(zip(mats["name"], mats["id"]))

            for _, r in edited.iterrows():
                mid = mat_map.get(str(r["material_name"]))
                if not mid:
                    continue
                cur.execute(
                    '''
                    INSERT INTO order_items(order_id, material_id, needed_qty, current_qty, order_qty)
                    VALUES(?,?,?,?,?)
                    ''',
                    (order_id, int(mid), float(r["needed_qty"]), float(r["current_qty"]), float(r["order_qty"])),
                )
            conn.commit()

        lines = [f"Hafta Pazartesi: {monday.isoformat()}", "----------------------------------------------"]
        for _, r in edited.iterrows():
            if float(r["order_qty"]) > 0:
                lines.append(f"{r['material_name']} - {float(r['order_qty']):.2f} {r['unit']}")
        pdf = simple_table_pdf("Haftalık Sipariş Listesi", lines)
        st.download_button(
            "⬇️ Sipariş PDF İndir",
            data=pdf,
            file_name=f"siparis_{monday.isoformat()}.pdf",
            mime="application/pdf",
        )
