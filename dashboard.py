import streamlit as st
import pandas as pd
import numpy as np
from entsoe import EntsoePandasClient
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os

# --- 1. КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(
    page_title="EU GRID ANALYTICS", 
    layout="wide", 
    page_icon="🇪🇺",
    initial_sidebar_state="collapsed"
)

# --- 2. БЕЗПЕКА ТА КЛЮЧІ (RENDER/CLOUD COMPATIBLE) ---
# Отримуємо ключі або з secrets.toml (Streamlit Cloud), або з Env Vars (Render)
api_key = st.secrets.get("entsoe_key") or os.environ.get("entsoe_key")
app_password = st.secrets.get("app_password") or os.environ.get("app_password")

# Перевірка конфігурації сервера
if not api_key or not app_password:
    st.error("❌ Критична помилка: Налаштування сервера (Environment Variables) не знайдені.")
    st.info("Переконайтеся, що в панелі Render додано: 'entsoe_key' та 'app_password'.")
    st.stop()

# --- 3. АВТОРИЗАЦІЯ ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    # Створюємо форму входу по центру
    _, col_mid, _ = st.columns([1, 2, 1])
    with col_mid:
        st.title("🔐 EU GRID ANALYTICS")
        password_input = st.text_input("Введіть пароль доступу:", type="password")
        if st.button("Увійти") or (password_input and st.session_state.get('last_input') != password_input):
            if password_input == app_password:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Невірний пароль")
    st.stop()

# --- 4. ГОЛОВНИЙ ІНТЕРФЕЙС ---
st.title("🇪🇺 EU GRID ANALYTICS")

# Короткий опис вкладок для користувача
with st.expander("📘 ІНСТРУКЦІЯ ТА ОПИС ВКЛАДОК"):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        * **⚖️ Небаланси**: Відображає ціни (Long/Short) та обсяги у МВт. Допомагає відстежувати стан енергосистеми.
        * **🌱 Зелена Енергія**: Реальний графік генерації сонця, вітру та гідро. Порівняння частки ВДЕ сьогодні, вчора та рік тому.
        """)
    with col2:
        st.markdown("""
        * **📉 РДН (Spot)**: Ціни ринку 'на добу наперед', загальне споживання (Load) та фінансовий оборот.
        * **🏗️ Генерація**: Повний енергомікс (АЕС, ТЕС, ВДЕ) у реальному часі за останні 24 години.
        """)

# --- 5. ЛОГІКА ДАНИХ (ПРИКЛАД) ---
client = EntsoePandasClient(api_key=api_key)

# Кнопка примусового оновлення
if st.button("🔄 ОНОВИТИ ДАНІ"):
    st.cache_data.clear()
    st.rerun()

# Створення вкладок
tabs = st.tabs(["⚖️ Небаланси", "🌱 Зелена Енергія", "📉 РДН (Spot)", "🏗️ Генерація"])

with tabs[0]:
    st.subheader("Моніторинг небалансів")
    st.info("Тут відображатимуться графіки цін та обсягів небалансів.")

with tabs[1]:
    st.subheader("Генерація з відновлюваних джерел")
    st.info("Графіки сонця, вітру та порівняльна таблиця (Сьогодні/Вчора/Рік тому).")

with tabs[2]:
    st.subheader("Ринок на добу наперед (Day-Ahead)")
    st.info("Погодинні ціни РДН та аналіз обсягів споживання.")

with tabs[3]:
    st.subheader("Поточний енергомікс")
    st.info("Структура генерації в реальному часі.")

# --- 6. ПІДВАЛ ---
st.markdown("---")
st.caption(f"Останнє оновлення даних: {datetime.now().strftime('%H:%M:%S')} | Система працює в реальному часі")
