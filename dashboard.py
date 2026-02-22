import streamlit as st
import pandas as pd
import numpy as np
from entsoe import EntsoePandasClient
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import streamlit as st

# Функція для безпечного отримання секретів без виклику помилки Streamlit
def get_secret(key):
    # 1. Пріоритет для Render (змінні оточення сервера)
    val = os.environ.get(key)
    if val:
        return val
    # 2. Резерв для локальної розробки або Streamlit Cloud
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return None

# Використання
api_key = get_secret("entsoe_key")
app_password = get_secret("app_password")

if not api_key:
    st.error("Критична помилка: 'entsoe_key' не знайдено в налаштуваннях сервера.")
    st.stop()

# --- 1. КОНФІГУРАЦІЯ СТОРІНКИ ---
st.set_page_config(page_title="EU GRID ANALYTICS", layout="wide", page_icon="🇪🇺")

# --- 2. СТИЛІЗАЦІЯ ---
st.markdown("""
    <style>
    .stApp {
        background-image: url("https://raw.githubusercontent.com/boss240/energy-aggregator/main/image_13.png");
        background-size: cover;
        background-repeat: no-repeat;
        background-attachment: fixed;
        color: #e0e0e0;
    }
    h1, h2, h3 { color: #00ff41 !important; font-family: 'Courier New', monospace; }
    div[data-testid="stMetricValue"] > div { font-size: 1.8rem !important; color: #00ffff; text-shadow: 0 0 5px #00ffff; }
    div[data-testid="stMetricLabel"] > div { font-size: 1rem !important; color: #cccccc; }
    .status-time { font-size: 1.2rem; color: #ffaa00; font-weight: bold; background: rgba(34, 34, 34, 0.8); padding: 5px 10px; border-radius: 5px; display: inline-block;}
    .analysis-box { background-color: rgba(26, 26, 26, 0.8); border-left: 4px solid #00ff41; padding: 15px; border-radius: 5px; margin-bottom: 20px;}
    </style>
""", unsafe_allow_html=True)

# --- 3. СЕКРЕТИ ТА АВТОРИЗАЦІЯ (RENDER COMPATIBLE) ---
# Перевіряємо st.secrets (Streamlit Cloud) або os.environ (Render)
api_key = st.secrets.get("entsoe_key") or os.environ.get("entsoe_key")
app_password = st.secrets.get("app_password") or os.environ.get("app_password")

if not api_key or not app_password:
    st.error("Помилка конфігурації: Ключ API або пароль не знайдено.")
    st.stop()

def check_password():
    if st.session_state.get("password_correct", False):
        return True

    def password_entered():
        if st.session_state["password"] == app_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    st.markdown("### 🔒 Обмежений доступ")
    st.text_input("🔑 Введіть пароль доступу:", type="password", on_change=password_entered, key="password")
    
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 Невірний пароль. Спробуйте ще раз.")
    return False

if not check_password():
    st.stop()

# --- 4. ДОВІДНИКИ ---
COUNTRY_INFO = {
    "PL": {"name": "Польща", "tso": "PSE S.A.", "anom": "Вугільна інерція.", "zone": "PL"},
    "UA": {"name": "Україна", "tso": "Укренерго", "anom": "Дефіцит через обстріли.", "zone": "UA_IPS"},
    "DE_LU": {"name": "Німеччина", "tso": "TenneT/Amprion", "anom": "Від’ємні ціни.", "zone": "DE_LU"},
    "HU": {"name": "Угорщина", "tso": "MAVIR", "anom": "Дорогий імпорт.", "zone": "HU"},
    "RO": {"name": "Румунія", "tso": "Transelectrica", "anom": "Гідрозалежність.", "zone": "RO"}
}

UA_GEN_MAP = {
    'Nuclear': 'АЕС', 'Solar': 'Сонце', 'Wind Onshore': 'Вітер',
    'Hydro Water Reservoir': 'ГЕС', 'Fossil Hard coal': 'Вугілля',
    'Fossil Gas': 'Газ', 'Hydro Pumped Storage': 'ГАЕС'
}

def safe_float(val):
    try:
        if isinstance(val, (pd.Series, pd.DataFrame)):
            v = val.values.flatten()
            v = v[~pd.isna(v)]
            return float(v[0]) if len(v) > 0 else 0.0
        return float(val) if not pd.isna(val) else 0.0
    except: return 0.0

# --- 5. ФУНКЦІЇ ОТРИМАННЯ ДАНИХ ---
@st.cache_data(ttl=300)
def fetch_current_data(api_key, country):
    client = EntsoePandasClient(api_key=api_key)
    now_ts = pd.Timestamp.now(tz='Europe/Kyiv')
    start = now_ts - timedelta(hours=48)
    end = now_ts + timedelta(hours=24)
    data = {}
    
    def get(func, *args, **kwargs):
        try:
            res = func(*args, **kwargs)
            if res is not None:
                if res.index.tz is None: res.index = res.index.tz_localize('UTC').tz_convert('Europe/Kyiv')
                else: res.index = res.index.tz_convert('Europe/Kyiv')
                return res[~res.index.duplicated(keep='last')]
        except: return None
        return None

    data['prices'] = get(client.query_day_ahead_prices, country, start=start, end=end)
    data['load'] = get(client.query_load, country, start=start, end=end)
    data['imb_p'] = get(client.query_imbalance_prices, country, start=start, end=end)
    data['imb_v'] = get(client.query_imbalance_volumes, country, start=start, end=end)
    
    gen = get(client.query_generation, country, start=start, end=end)
    if gen is not None:
        if isinstance(gen.columns, pd.MultiIndex): 
            gen.columns = gen.columns.get_level_values(0)
        data['gen'] = gen.rename(columns=UA_GEN_MAP)
    return data

# --- 6. ОСНОВНИЙ ІНТЕРФЕЙС ---
now_curr = pd.Timestamp.now(tz='Europe/Kyiv')
selected_code = st.sidebar.selectbox("Оберіть зону", list(COUNTRY_INFO.keys()), format_func=lambda x: f"{x} - {COUNTRY_INFO[x]['name']}")
info = COUNTRY_INFO[selected_code]

col_title, col_btn = st.columns([3, 1])
with col_title:
    st.title(f"⚡ {info['name']} (EC GRID)")
    st.markdown(f"<div class='status-time'>🕒 Час оновлення: {now_curr.strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

if col_btn.button("🔄 ОНОВИТИ ДАНІ", type="primary", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

with st.spinner(f"📡 Завантаження даних ENTSO-E для зони {selected_code}..."):
    live_data = fetch_current_data(api_key, info['zone'])

if live_data.get('prices') is not None:
    curr_price = safe_float(live_data['prices'].asof(now_curr))
    
    # МЕТРИКИ ВЕРХНЬОГО РІВНЯ
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Спот ціна", f"{curr_price:.2f} €")
    
    res_share = "N/A"
    if live_data.get('gen') is not None:
        latest_gen = live_data['gen'].ffill().iloc[-1]
        green = latest_gen[[c for c in latest_gen.index if any(x in c for x in ['Сонце','Вітер','ГЕС'])]].sum()
        res_share = f"{(green / latest_gen.sum() * 100):.1f}%" if latest_gen.sum() > 0 else "0%"
    
    k2.metric("Частка ВДЕ", res_share)
    k3.metric("Статус", "ONLINE 🟢")
    k4.metric("Зона", selected_code)

    tabs = st.tabs(["⚖️ Небаланси", "🌱 Зелена Енергія", "📉 РДН", "🏗️ Генерація"])

    with tabs[0]:
        st.info("📊 Візуалізація небалансів (Single vs Dual Pricing)")
        if live_data['imb_p'] is not None:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            imb_p_df = live_data['imb_p'].ffill()
            fig.add_trace(go.Scatter(x=imb_p_df.index, y=imb_p_df.iloc[:,0], name="Ціна небалансу", line=dict(color='#ffaa00')), secondary_y=True)
            
            if live_data['imb_v'] is not None:
                imb_v_vals = live_data['imb_v'].iloc[:,0]
                colors = ['#ff0044' if x < 0 else '#00ff41' for x in imb_v_vals]
                fig.add_trace(go.Bar(x=live_data['imb_v'].index, y=imb_v_vals, marker_color=colors, name="Обсяг (MW)", opacity=0.4), secondary_y=False)
            
            fig.update_layout(template="plotly_dark", height=450, title="Небаланси (останні 24г)")
            st.plotly_chart(fig, use_container_width=True)

    with tabs[1]:
        if live_data.get('gen') is not None:
            g = live_data['gen'].ffill()
            green_cols = [c for c in g.columns if any(x in c for x in ['Сонце','Вітер','ГЕС'])]
            if green_cols:
                fig = go.Figure()
                for c in green_cols:
                    fig.add_trace(go.Scatter(x=g.index, y=g[c], name=c, stackgroup='one'))
                fig.update_layout(template="plotly_dark", title="Виробництво ВДЕ", height=450)
                st.plotly_chart(fig, use_container_width=True)

    with tabs[2]:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=live_data['prices'].index, y=live_data['prices'].values, name="РДН Ціна", line=dict(color='#00ff41')))
        fig.update_layout(template="plotly_dark", title="Ціни Day-Ahead", height=450)
        st.plotly_chart(fig, use_container_width=True)

    with tabs[3]:
        if live_data.get('gen') is not None:
            last_gen_mix = live_data['gen'].ffill().iloc[-1].sort_values(ascending=False)
            fig = go.Figure(go.Pie(labels=last_gen_mix.index, values=last_gen_mix.values, hole=.3))
            fig.update_layout(template="plotly_dark", title="Енергомікс")
            st.plotly_chart(fig, use_container_width=True)
else:
    st.warning(f"Дані для зони {selected_code} тимчасово недоступні.")

