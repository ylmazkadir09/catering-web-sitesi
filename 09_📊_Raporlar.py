
import streamlit as st
import pandas as pd
import datetime as dt
from catering.auth import require_login, guard_demo
from catering.db import get_conn
from catering.utils import df_to_excel_bytes, require_cols, simple_table_pdf

require_login()
guard_demo()
user = st.session_state.get("user")

st.set_page_config(page_title="Raporlar", layout="wide")
st.title("📊 Raporlar")

tab1, tab2, tab3, tab4 = st.tabs(
    ["a) Kullanılan Malzeme", "b) Giren Malzeme", "c) Kişi Başı Maliyet", "d) Haftalık Menü PDF"]
)

def weighted_unit_prices(conn):
    df = pd.read_sql_query("SELECT material_id, qty, total_amount FROM invoice_items", conn)
    if df.empty:
        return {}
    g = df.groupby("material_id").apply(lambda x: (x["total_amount"].sum() / x["qty"].sum()) if x["qty"].sum() > 0 else 0)
    return g.to_dict()

with tab1:
    st.subheader("Tarihe göre kullanılan malzeme raporu (çıkış)")
    d1 = st.date_input("Başlangıç", value=dt.date.today() - dt.timedelta(days=7), key="u1")
    d2 = st.date_input("Bitiş", value=dt.date.today(), key="u2")
    with get_conn() as conn:
        df = pd.read_sql_query(
            '''
            SELECT sm.move_date, m.name as material_name, u.name as unit, sm.qty, sm.ref_type, sm.note
            FROM stock_moves sm
            JOIN materials m ON m.id=sm.material_id
            JOIN units u ON u.id=m.unit_id
            WHERE sm.direction='out' AND sm.move_date BETWEEN ? AND ?
            ORDER BY sm.move_date, material_name
            ''',
            conn,
            params=(d1.isoformat(), d2.isoformat()),
        )
    st.dataframe(df, use_container_width=True)
    if not df.empty:
        x = df_to_excel_bytes({"UsedMaterials": df})
        st.download_button(
            "⬇️ Excel indir",
            data=x,
            file_name="kullanilan_malzeme.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with tab2:
    st.subheader("Tarihe göre giren malzeme raporu (fatura)")
    d1 = st.date_input("Başlangıç", value=dt.date.today() - dt.timedelta(days=30), key="i1")
    d2 = st.date_input("Bitiş", value=dt.date.today(), key="i2")
    with get_conn() as conn:
        df = pd.read_sql_query(
            '''
            SELECT inv.invoice_date, inv.invoice_no, m.name as material_name, u.name as unit,
                   ii.qty, ii.total_amount, ii.unit_price
            FROM invoice_items ii
            JOIN invoices inv ON inv.id=ii.invoice_id
            JOIN materials m ON m.id=ii.material_id
            JOIN units u ON u.id=m.unit_id
            WHERE inv.invoice_date BETWEEN ? AND ?
            ORDER BY inv.invoice_date, inv.invoice_no
            ''',
            conn,
            params=(d1.isoformat(), d2.isoformat()),
        )
    st.dataframe(df, use_container_width=True)
    if not df.empty:
        x = df_to_excel_bytes({"IncomingMaterials": df})
        st.download_button(
            "⬇️ Excel indir",
            data=x,
            file_name="giren_malzeme.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with tab3:
    st.subheader("Kişi başı maliyet raporu (tahmini)")
    st.caption("Birim fiyatlar faturalardan ağırlıklı ortalama alınır.")
    date = st.date_input("Tarih", value=dt.date.today(), key="cdate")

    with get_conn() as conn:
        menu = pd.read_sql_query(
            '''
            SELECT m.meal_type, d.id as dish_id, d.name as dish_name
            FROM menus m JOIN dishes d ON d.id=m.dish_id
            WHERE m.menu_date=?
            ''',
            conn,
            params=(date.isoformat(),),
        )
        recipe = pd.read_sql_query(
            '''
            SELECT ri.dish_id, ri.qty_per_person, m.id as material_id, m.name as material_name
            FROM recipe_items ri
            JOIN materials m ON m.id=ri.material_id
            ''',
            conn,
        )
        prices = weighted_unit_prices(conn)

    if menu.empty:
        st.info("Bu tarihte menü yok.")
    else:
        meal_types = ["breakfast", "lunch", "dinner", "snack"]
        meal_labels = {"breakfast": "Kahvaltı", "lunch": "Öğle", "dinner": "Akşam", "snack": "Ara Öğün"}
        cols = st.columns(4)
        counts = {}
        for i, mt in enumerate(meal_types):
            with cols[i]:
                counts[mt] = st.number_input(meal_labels[mt], min_value=0, value=0, step=1, key=f"pc_{mt}")

        if st.button("Hesapla"):
            total_cost = 0.0
            total_people = 0
            detail = []

            for mt, people in counts.items():
                if people <= 0:
                    continue
                total_people += people
                dishes_meal = menu[menu["meal_type"] == mt]
                for _, dr in dishes_meal.iterrows():
                    dish_id = int(dr["dish_id"])
                    part = recipe[recipe["dish_id"] == dish_id]
                    for _, r in part.iterrows():
                        mid = int(r["material_id"])
                        qty = float(r["qty_per_person"]) * people
                        unit_price = float(prices.get(mid, 0))
                        cost = qty * unit_price
                        total_cost += cost
                        detail.append([dr["dish_name"], r["material_name"], qty, unit_price, cost])

            if total_people == 0:
                st.warning("Kişi sayısı gir.")
            else:
                per_person = total_cost / total_people
                st.success(f"Toplam maliyet: {total_cost:.2f} TL | Kişi başı: {per_person:.2f} TL")
                ddf = pd.DataFrame(detail, columns=["yemek", "malzeme", "miktar", "birim_fiyat", "tutar"])
                st.dataframe(ddf, use_container_width=True)

with tab4:
    st.subheader("Tarihe göre haftalık menü çıktısı")
    monday = st.date_input(
        "Pazartesi seç",
        value=dt.date.today() - dt.timedelta(days=dt.date.today().weekday()),
        key="wm",
    )
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    with get_conn() as conn:
        menu = pd.read_sql_query(
            '''
            SELECT m.menu_date, m.meal_type, d.name as dish_name
            FROM menus m JOIN dishes d ON d.id=m.dish_id
            WHERE m.menu_date BETWEEN ? AND ?
            ORDER BY m.menu_date, m.meal_type, d.name
            ''',
            conn,
            params=(days[0].isoformat(), days[-1].isoformat()),
        )

    if menu.empty:
        st.info("Bu hafta menü yok.")
    else:
        meal_tr = {"breakfast": "Kahvaltı", "lunch": "Öğle", "dinner": "Akşam", "snack": "Ara Öğün"}
        menu_show = menu.copy()
        menu_show["meal_type"] = menu_show["meal_type"].replace(meal_tr)
        st.dataframe(menu_show, use_container_width=True)

        lines = [f"Hafta: {days[0].isoformat()} - {days[-1].isoformat()}", ""]
        for d in days:
            lines.append(d.isoformat())
            sub = menu_show[menu_show["menu_date"] == d.isoformat()]
            if sub.empty:
                lines.append("  (Boş)")
            else:
                for mt in ["Kahvaltı", "Öğle", "Akşam", "Ara Öğün"]:
                    items = sub[sub["meal_type"] == mt]["dish_name"].tolist()
                    if items:
                        lines.append(f"  {mt}: " + ", ".join(items))
            lines.append("")

        pdf = simple_table_pdf("Haftalık Menü", lines)
        st.download_button(
            "⬇️ Menü PDF İndir",
            data=pdf,
            file_name=f"menu_{monday.isoformat()}.pdf",
            mime="application/pdf",
        )
