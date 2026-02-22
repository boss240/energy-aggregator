import streamlit as st
import os

# 1. Отримання ключів (Render Priority)
api_key = os.environ.get("entsoe_key")
app_password = os.environ.get("app_password")

# 2. Перевірка авторизації
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 EU GRID")
    pwd = st.text_input("Пароль:", type="password")
    if st.button("Увійти"):
        if pwd == app_password:
            st.session_state.auth = True
            st.rerun()
        else: st.error("❌")
    st.stop()

# 3. Основний інтерфейс
st.title("🇪🇺 EU GRID ANALYTICS")

tabs = st.tabs(["⚖️ Небаланси", "🌱 ВДЕ", "📉 РДН", "🏗️ Мікс"])

with tabs[0]: st.write("Дані небалансів оновлюються...")
with tabs[1]: st.write("Графіки сонця та вітру...")
with tabs[2]: st.write("Ціни Spot (Day-Ahead)...")
with tabs[3]: st.write("Поточна генерація...")

if st.button("🔄 ОНОВИТИ"):
    st.cache_data.clear()
    st.rerun()
