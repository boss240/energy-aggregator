import streamlit as st
import pandas as pd
from entsoe import EntsoePandasClient
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="EU GRID ANALYTICS", layout="wide", page_icon="🇪🇺")

# --- 2. БЕЗПЕКА ТА КЛЮЧІ ---
api_key = os.environ.get("entsoe_key")
app_password = os.environ.get("app_password")

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 EU GRID ANALYTICS")
    pwd = st.text_input("Введіть пароль доступу:", type="password")
    if st.button("Увійти"):
        if pwd == app_password:
            st.session_state.auth = True
            st.rerun()
        else: st.error("Невірний пароль")
    st.stop()

# --- 3. ПІДДКЛЮЧЕННЯ ДО ENTSO-E ---
client = EntsoePandasClient(api_key=api_key)
country_code = 'UA_IPS' # Країна за замовчуванням (можна змінити на PL, DE, RO тощо)

# Часові межі (за останні 24 години)
end = pd.Timestamp(datetime.now(), tz='Europe/Kiev')
start = end - pd.Timedelta(days=1)

# --- 4. ГОЛОВНИЙ ІНТЕРФЕЙС ---
st.title("🇪🇺 EU GRID ANALYTICS")

# Створення вкладок
tabs = st.tabs(["⚖️ Небаланси", "🌱 ВДЕ", "📉 РДН (Spot)", "🏗️ Мікс"])

# --- ВКЛАДКА: НЕБАЛАНСИ ---
with tabs[0]:
    st.subheader("Ціни небалансів (Imbalance Prices)")
    try:
        data = client.query_imbalance_prices(country_code, start=start, end=end)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data.index, y=data['Short'], name='Price Short (Дефіцит)', line=dict(color='#FF4B4B')))
        fig.add_trace(go.Scatter(x=data.index, y=data['Long'], name='Price Long (Надлишок)', line=dict(color='#00CC96')))
        fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.info(f"Дані небалансів наразі недоступні для {country_code}")

# --- ВКЛАДКА: ВДЕ (СОНЦЕ/ВІТЕР) ---
with tabs[1]:
    st.subheader("Генерація ВДЕ (MW)")
    try:
        gen = client.query_generation(country_code, start=start, end=end)
        vde_cols = [c for c in gen.columns if 'Solar' in c or 'Wind' in c]
        if vde_cols:
            fig_vde = go.Figure()
            for col in vde_cols:
                fig_vde.add_trace(go.Scatter(x=gen.index, y=gen[col], name=col, fill='tozeroy'))
            fig_vde.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig_vde, use_container_width=True)
        else: st.write("Дані ВДЕ не знайдені.")
    except: st.error("Помилка завантаження даних генерації.")

# --- ВКЛАДКА: РДН (SPOT PRICES) ---
with tabs[2]:
    st.subheader("Ціни Day-Ahead (EUR/MWh)")
    try:
        prices = client.query_day_ahead_prices(country_code, start=start, end=end)
        fig_p = go.Figure(go.Scatter(x=prices.index, y=prices, name='DA Price', line=dict(color='#AB63FA', width=3)))
        fig_p.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_p, use_container_width=True)
    except: st.error("Дані РДН недоступні.")

# --- ВКЛАДКА: МІКС ---
with tabs[3]:
    st.subheader("Структура генерації")
    try:
        gen = client.query_generation(country_code, start=start, end=end)
        latest = gen.iloc[-1].dropna()
        fig_pie = go.Figure(data=[go.Pie(labels=latest.index, values=latest.values, hole=.3)])
        fig_pie.update_layout(template="plotly_dark", height=450)
        st.plotly_chart(fig_pie, use_container_width=True)
    except: st.write("Дані міксу недоступні.")

# --- БІЧНА ПАНЕЛЬ ТА ОНОВЛЕННЯ ---
st.sidebar.title("Налаштування")
if st.sidebar.button("🔄 ОНОВИТИ ДАНІ"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.write(f"Останнє оновлення: {datetime.now().strftime('%H:%M:%S')}")
