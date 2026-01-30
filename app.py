
import streamlit as st
from catering.auth import init_auth, login, signup, show_demo_badge

st.set_page_config(page_title="Catering Yönetim", layout="wide")
init_auth()

st.title("🍽️ Catering Yönetim Sistemi")

if "user" in st.session_state:
    show_demo_badge()
    st.success(f"Giriş yapıldı: {st.session_state['user']['username']} ({st.session_state['user']['role']})")
    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("Uygulamaya Git"):
            st.switch_page("pages/01_📦_Malzemeler_&_Birimler.py")
    with c2:
        if st.button("Çıkış Yap"):
            st.session_state.pop("user", None)
            st.rerun()
    st.stop()

tab1, tab2 = st.tabs(["🔑 Giriş", "📝 Kayıt Ol (Demo 15 gün)"])

with tab1:
    st.subheader("Giriş")
    u = st.text_input("Kullanıcı adı")
    p = st.text_input("Parola", type="password")
    if st.button("Giriş Yap", type="primary"):
        try:
            user = login(u, p)
        except PermissionError as e:
            st.error(str(e))
            user = None
        if not user:
            st.error("Kullanıcı adı veya parola yanlış.")
        else:
            st.session_state["user"] = user
            st.success("Giriş başarılı.")
            st.rerun()

with tab2:
    st.subheader("Kayıt Ol")
    first = st.text_input("Ad")
    last = st.text_input("Soyad")
    email = st.text_input("E-posta")
    username = st.text_input("Kullanıcı adı", key="su")
    pw1 = st.text_input("Parola", type="password", key="pw1")
    pw2 = st.text_input("Parola tekrar", type="password", key="pw2")
    if st.button("Kayıt Ol", type="primary"):
        if not all([first.strip(), last.strip(), email.strip(), username.strip(), pw1]):
            st.error("Lütfen tüm alanları doldur.")
        elif pw1 != pw2:
            st.error("Parolalar uyuşmuyor.")
        else:
            try:
                signup(first, last, email, username, pw1)
                st.success("Kayıt başarılı! Şimdi giriş yapabilirsin.")
            except Exception as e:
                st.error(f"Kayıt hatası: {e}")
