import streamlit as st
import pandas as pd
import numpy as np
from entsoe import EntsoePandasClient
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os

# --- КОНФІГУРАЦІЯ ---
st.set_page_config(page_title="EU GRID ANALYTICS", layout="wide", page_icon="🇪🇺")

# --- СТИЛІ ---
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
    .status-time { font-size: 1.2rem; color: #ffaa00; font-weight: bold; background: rgba(34, 34, 34, 0.8); padding: 5px 10px; border-radius: 5px; display: inline-block;}
    .analysis-box { background-color: rgba(26, 26, 26, 0.8); border-left: 4px solid #00ff41; padding: 15px; border-radius: 5px; margin-bottom: 20px;}
    </style>
""", unsafe_allow_html=True)

# --- ПЕРЕВІРКА СЕКРЕТІВ (З ПОКРАЩЕНОЮ ПІДТРИМКОЮ RENDER/STREAMLIT) ---
api_key = st.secrets.get("entsoe_key") or os.environ.get("entsoe_key")
app_password = st.secrets.get("app_password") or os.environ.get("app_password")

if not api_key or not app_password:
    st.error("Критична помилка: Налаштування сервера не знайдені.")
    st.stop()

# --- АВТОРИЗАЦІЯ ---
def check_password():
    if st.session_state.get("password_correct", False): return True
    
    st.markdown("### 🔒 Доступ закрито")
    pwd = st.text_input("🔑 Введіть пароль доступу:", type="password")
    if st.button("Увійти"):
        if pwd == app_password:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("😕 Невірний пароль.")
    return False

if not check_password():
    st.stop()

# --- ДОВІДНИК ---
COUNTRY_INFO = {
    "UA": {"name": "Україна", "tso": "Укренерго", "anom": "Дефіцит, обстріли.", "zone": "UA_IPS"},
    "PL": {"name": "Польща", "tso": "PSE S.A.", "anom": "Вугільна інерція.", "zone": "PL"},
    "DE_LU": {"name": "Німеччина", "tso": "TenneT/Amprion", "anom": "Від'ємні ціни.", "zone": "DE_LU"},
    "HU": {"name": "Угорщина", "tso": "MAVIR", "anom": "Дорогий імпорт.", "zone": "HU"},
    "RO": {"name": "Румунія", "tso": "Transelectrica", "anom": "Посухи.", "zone": "RO"}
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

@st.cache_data(ttl=300)
def fetch_current_data(api_key, country_code):
    client = EntsoePandasClient(api_key=api_key)
    now = pd.Timestamp.now(tz='Europe/Kyiv')
    start = now - timedelta(hours=48)
    end = now + timedelta(hours=1) # Беремо до поточної години
    
    data = {'prices': None, 'load': None, 'imb_p': None, 'imb_v': None, 'gen': None}
    
    try:
        data['prices'] = client.query_day_ahead_prices(country_code, start=start, end=end + timedelta(hours=24))
        data['load'] = client.query_load(country_code, start=start, end=end)
        
        try:
            gen = client.query_generation(country_code, start=start, end=end)
            if isinstance(gen.columns, pd.MultiIndex): gen.columns = gen.columns.get_level_values(0)
            data['gen'] = gen.rename(columns=UA_GEN_MAP)
        except: pass

        try:
            data['imb_p'] = client.query_imbalance_prices(country_code, start=start, end=end)
            data['imb_v'] = client.query_imbalance_volumes(country_code, start=start, end=end)
        except: pass
        
    except Exception as e:
        st.sidebar.error(f"Помилка API: {e}")
    return data

# --- ОСНОВНИЙ ІНТЕРФЕЙС ---
selected_key = st.sidebar.selectbox("Оберіть Зону", list(COUNTRY_INFO.keys()), format_func=lambda x: COUNTRY_INFO[x]['name'])
info = COUNTRY_INFO[selected_key]
zone = info['zone']

now_time = pd.Timestamp.now(tz='Europe/Kyiv')

col_title, col_btn = st.columns([3, 1])
with col_title:
    st.title(f"⚡ {info['name']}")
    st.markdown(f"<div class='status-time'>🕒 Дані на: {now_time.strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

if col_btn.button("🔄 ОНОВИТИ", type="primary", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

live_data = fetch_current_data(api_key, zone)

if live_data['prices'] is not None:
    curr_p = safe_float(live_data['prices'].asof(now_time))
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Спот Ціна", f"{curr_p:.2f} €")
    
    res_share = "N/A"
    if live_data['gen'] is not None:
        latest_gen = live_data['gen'].ffill().iloc[-1]
        green = latest_gen[[c for c in latest_gen.index if any(x in c for x in ['Сонце','Вітер','ГЕС'])]].sum()
        res_share = f"{(green / latest_gen.sum() * 100):.1f}%" if latest_gen.sum() > 0 else "0%"
        
    k2.metric("Частка ВДЕ", res_share)
    k3.metric("Статус", "ONLINE 🟢")

    tabs = st.tabs(["⚖️ Небаланси", "🌱 ВДЕ", "📉 РДН", "🏗️ Генерація"])

    with tabs[0]:
        if live_data['imb_p'] is not None:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            # Ціна небалансу
            fig.add_trace(go.Scatter(x=live_data['imb_p'].index, y=live_data['imb_p'].iloc[:,0], name="Ціна Небалансу", line=dict(color='#ffaa00')), secondary_y=True)
            # Обсяг небалансу
            if live_data['imb_v'] is not None:
                v_vals = live_data['imb_v'].iloc[:,0]
                colors = ['#ff0044' if x < 0 else '#00ff41' for x in v_vals]
                fig.add_trace(go.Bar(x=live_data['imb_v'].index, y=v_vals, name="Обсяг (MW)", marker_color=colors, opacity=0.4), secondary_y=False)
            
            fig.update_layout(template="plotly_dark", height=400, title="Стан балансу (24 год)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Дані небалансів для цієї зони недоступні через API.")

    with tabs[1]:
        if live_data['gen'] is not None:
            g = live_data['gen'].ffill()
            green_cols = [c for c in g.columns if any(x in c for x in ['Сонце','Вітер','ГЕС'])]
            if green_cols:
                fig = go.Figure()
                for c in green_cols:
                    fig.add_trace(go.Scatter(x=g.index, y=g[c], name=c, stackgroup='one'))
                fig.update_layout(template="plotly_dark", title="Профіль ВДЕ", height=400)
                st.plotly_chart(fig, use_container_width=True)

    with tabs[2]:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=live_data['prices'].index, y=live_data['prices'].values, name="Price", line=dict(color='#00ff41')))
        fig.update_layout(template="plotly_dark", title="Ринок на добу наперед (DA)", height=400)
        st.plotly_chart(fig, use_container_width=True)

    with tabs[3]:
        if live_data['gen'] is not None:
            g = live_data['gen'].ffill().iloc[-1].sort_values(ascending=False)
            fig = go.Figure(go.Pie(labels=g.index, values=g.values, hole=.3))
            fig.update_layout(template="plotly_dark", title="Енергомікс")
            st.plotly_chart(fig, use_container_width=True)
else:
    st.warning(f"Неможливо отримати дані для зони {selected_key}. Перевірте доступність API.")
