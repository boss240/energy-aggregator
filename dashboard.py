import streamlit as st
import pandas as pd
import numpy as np
from entsoe import EntsoePandasClient
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- КОНФІГУРАЦІЯ ---
st.set_page_config(page_title="EU GRID ANALYTICS", layout="wide", page_icon="🇪🇺")

# --- СТИЛІ ---
st.markdown("""
    <style>
    .stApp { background-color: #080808; color: #e0e0e0; }
    h1, h2, h3 { color: #00ff41 !important; font-family: 'Courier New', monospace; }
    div[data-testid="stMetricValue"] > div { font-size: 1.8rem !important; color: #00ffff; text-shadow: 0 0 5px #00ffff; }
    div[data-testid="stMetricLabel"] > div { font-size: 1rem !important; color: #cccccc; }
    .status-time { font-size: 1.2rem; color: #ffaa00; font-weight: bold; background: #222; padding: 5px 10px; border-radius: 5px; display: inline-block;}
    .analysis-box { background-color: #1a1a1a; border-left: 4px solid #00ff41; padding: 15px; border-radius: 5px; margin-bottom: 20px;}
    </style>
""", unsafe_allow_html=True)

# --- ДОВІДНИК ---
COUNTRY_INFO = {
    "PL": {"name": "Польща", "tso": "PSE S.A.", "anom": "Вугільна інерція.", "cause": "80% вугілля.", "zone": "CEN"},
    "UA": {"name": "Україна", "tso": "Укренерго", "anom": "Дефіцит, обстріли.", "cause": "Війна.", "zone": "UA-IPS"},
    "DE_LU": {"name": "Німеччина", "tso": "TenneT/Amprion", "anom": "Від'ємні ціни.", "cause": "Надлишок вітру.", "zone": "CEN"},
    "FR": {"name": "Франція", "tso": "RTE", "anom": "Чутливість до холоду.", "cause": "Атомна енергетика.", "zone": "CEN"},
    "HU": {"name": "Угорщина", "tso": "MAVIR", "anom": "Дорогий імпорт.", "cause": "Дефіцит генерації.", "zone": "CEN"},
    "SK": {"name": "Словаччина", "tso": "SEPS", "anom": "Транзит.", "cause": "Інтеграція CZ-HU.", "zone": "CEN"},
    "RO": {"name": "Румунія", "tso": "Transelectrica", "anom": "Посухи.", "cause": "Гідрозалежність.", "zone": "CEN"},
    "CZ": {"name": "Чехія", "tso": "ČEPS", "anom": "Експорт.", "cause": "АЕС.", "zone": "CEN"},
    "MD": {"name": "Молдова", "tso": "Moldelectrica", "anom": "Дефіцит.", "cause": "Немає генерації.", "zone": "UA-IPS"}
}

# --- АВТО-ВХІД ---
try:
    api_key = st.secrets["entsoe_key"]
except:
    st.error("Помилка: API ключ не знайдено в налаштуваннях сервера (Secrets).")
    st.stop()

# --- SIDEBAR ---
st.sidebar.header("🔐 ПАНЕЛЬ КЕРУВАННЯ")
selected_code = st.sidebar.selectbox("Оберіть Зону", list(COUNTRY_INFO.keys()), format_func=lambda x: f"{x} - {COUNTRY_INFO[x]['name']}")
info = COUNTRY_INFO[selected_code]

# --- МАПІНГ ГЕНЕРАЦІЇ ---
UA_GEN_MAP = {
    'Biomass': 'Біомаса', 'Fossil Brown coal/Lignite': 'Вугілля (Буре)',
    'Fossil Gas': 'Газ', 'Fossil Hard coal': 'Вугілля (Кам.)',
    'Hydro Pumped Storage': 'ГАЕС', 'Hydro Run-of-river and poundage': 'ГЕС (Прот)',
    'Hydro Water Reservoir': 'ГЕС (Вод)', 'Nuclear': 'АЕС',
    'Solar': 'Сонце', 'Wind Offshore': 'Вітер (Море)', 'Wind Onshore': 'Вітер (Суша)',
    'Waste': 'Відходи', 'Other': 'Інше', 'Fossil Oil': 'Мазут', 'Geothermal': 'Геотерм.'
}

# --- ФУНКЦІЇ ДАНИХ ---
def safe_float(val):
    try:
        if isinstance(val, (pd.Series, pd.DataFrame)):
            v = val.values.flatten()
            v = v[~np.isnan(v)]
            return float(v[0]) if len(v) > 0 else 0.0
        return float(val)
    except: return 0.0

@st.cache_data(ttl=300)
def fetch_current_data(api_key, country):
    client = EntsoePandasClient(api_key=api_key)
    now = pd.Timestamp.now(tz='Europe/Kyiv')
    start = now - timedelta(hours=48)
    end = now + timedelta(hours=24)
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

    try:
        data['prices'] = get(client.query_day_ahead_prices, country, start=start, end=end)
        data['load'] = get(client.query_load, country, start=start, end=end)
        data['imb_p'] = get(client.query_imbalance_prices, country, start=start, end=end)
        data['imb_v'] = get(client.query_imbalance_volumes, country, start=start, end=end)
        gen = get(client.query_generation, country, start=start, end=end)
        if gen is not None:
            if isinstance(gen.columns, pd.MultiIndex): gen.columns = gen.columns.get_level_values(0)
            gen = gen.groupby(level=0, axis=1).sum().rename(columns=UA_GEN_MAP)
        data['gen'] = gen
    except: pass
    return data

@st.cache_data(ttl=3600)
def fetch_comparison_stats(api_key, country):
    client = EntsoePandasClient(api_key=api_key)
    now = pd.Timestamp.now(tz='Europe/Kyiv')
    dates = {'yesterday': now - timedelta(days=1), 'last_year': now - timedelta(days=365)}
    stats = {}
    for label, date in dates.items():
        s = date.replace(hour=0, minute=0)
        e = date.replace(hour=23, minute=59)
        res = {'prices': None, 'load': None, 'gen': None, 'imb_p': None, 'imb_v': None}
        try:
            res['prices'] = client.query_day_ahead_prices(country, start=s, end=e)
            try: res['load'] = client.query_load(country, start=s, end=e)
            except: pass
            try: res['imb_p'] = client.query_imbalance_prices(country, start=s, end=e)
            except: pass
            try: res['imb_v'] = client.query_imbalance_volumes(country, start=s, end=e)
            except: pass
            gen = client.query_generation(country, start=s, end=e)
            if gen is not None:
                if isinstance(gen.columns, pd.MultiIndex): gen.columns = gen.columns.get_level_values(0)
                gen = gen.groupby(level=0, axis=1).sum().rename(columns=UA_GEN_MAP)
            res['gen'] = gen
        except: pass
        stats[label] = res
    return stats

def analyze_period_change(series, hours=4):
    if series is None or series.empty: return "Немає даних", 0
    now = series.index[-1]
    past = now - timedelta(hours=hours)
    try:
        val_now = safe_float(series.asof(now))
        val_past = safe_float(series.asof(past))
        diff = val_now - val_past
        pct = (diff / val_past * 100) if val_past != 0 else 0
        trend = "📈" if diff > 0 else "📉"
        sign = "+" if diff > 0 else ""
        return f"{trend} {sign}{diff:.1f}€ ({abs(pct):.0f}%)", diff
    except: return "Помилка", 0

# --- MAIN APP ---
now = pd.Timestamp.now(tz='Europe/Kyiv')

# HEADER З КНОПКОЮ ОНОВЛЕННЯ
col_title, col_btn = st.columns([3, 1])
with col_title:
    st.title(f"⚡ {info['name']} ({selected_code})")
    st.markdown(f"<div class='status-time'>🕒 Стан даних на: {now.strftime('%d.%m.%Y %H:%M:%S')}</div>", unsafe_allow_html=True)
with col_btn:
    st.write("") # Відступ
    if st.button("🔄 ОНОВИТИ ДАНІ", type="primary", use_container_width=True):
        st.cache_data.clear() # Очищаємо кеш, щоб завантажити свіжі дані
        st.rerun() # Перезавантажуємо сторінку

with st.expander(f"ℹ️ ДОСЬЄ: {info['name']}", expanded=False):
    c1, c2 = st.columns(2)
    c1.markdown(f"**ОСП:** {info['tso']}")
    c2.markdown(f"**Аномалії:** {info['anom']}")

with st.spinner(f"📡 З'єднання з ENTSO-E ({selected_code}). Отримання свіжих даних..."):
    live_data = fetch_current_data(api_key, selected_code)
    hist_data = fetch_comparison_stats(api_key, selected_code)

today_start = now.replace(hour=0, minute=0)
data_today = {k: (v.loc[today_start:] if v is not None else None) for k, v in live_data.items()}

# --- БЛОК АВТОМАТИЧНОГО АНАЛІЗУ ---
if live_data['prices'] is not None and hist_data['yesterday']['prices'] is not None:
    try:
        y_avg = safe_float(hist_data['yesterday']['prices'].mean())
        y_max = safe_float(hist_data['yesterday']['prices'].max())
        t_avg = safe_float(data_today['prices'].mean()) if data_today['prices'] is not None else 0
        t_now = safe_float(live_data['prices'].asof(now))
        
        st.markdown(f"""
        <div class='analysis-box'>
            <b>📝 КОРОТКИЙ АНАЛІЗ РИНКУ:</b><br>
            🔸 <b>Минула доба:</b> Середня ціна на РДН становила {y_avg:.2f} €, досягаючи максимуму {y_max:.2f} €.<br>
            🔸 <b>Поточна доба:</b> Середня ціна наразі формується на рівні {t_avg:.2f} €, а поточна спот-ціна становить {t_now:.2f} €.
        </div>
        """, unsafe_allow_html=True)
    except: pass

# --- МЕТРИКИ ---
if live_data['prices'] is not None:
    curr_price = safe_float(live_data['prices'].asof(now))
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Спот Ціна", f"{curr_price:.2f} €", help="Поточна ціна електроенергії на РДН")
    
    res_txt = "N/A"
    if live_data['gen'] is not None:
        try:
            g_now = live_data['gen'].iloc[live_data['gen'].index.get_indexer([now], method='nearest')[0]]
            green_cols = [c for c in g_now.index if any(x in c for x in ['Вітер','Сонце','ГЕС','Біо'])]
            res_share = (g_now[green_cols].sum() / g_now.sum() * 100)
            res_txt = f"{res_share:.1f}%"
        except: pass
    k2.metric("Частка ВДЕ", res_txt, help="Відсоток зеленої енергетики в міксі")
    
    trend_txt, _ = analyze_period_change(live_data['prices'])
    k3.metric("Тренд (4г)", trend_txt, help="Зміна ціни за останні 4 години")
    k4.metric("Статус", "ONLINE 🟢", help="Зв'язок із сервером встановлено")

    tabs = st.tabs(["⚖️ Небаланси", "🌱 Зелена Енергія", "📉 РДН (Spot)", "🏗️ Генерація"])

    # TAB 1: IMBALANCE
    with tabs[0]:
        # --- ПОЯСНЕННЯ ПРАВИЛ ЄС ---
        st.info("💡 **Чому на графіку одна або дві лінії?** Згідно з новими правилами ЄС (Electricity Balancing Guideline), більшість країн перейшли на **«Єдину ціну небалансу» (Single Pricing)** — лінія одна, ціна штрафу однакова як для профіциту, так і для дефіциту. Проте деякі зони ще використовують стару систему **подвійних цін (Dual Pricing)**, де відображаються окремі ціни для Long (надлишок) та Short (нестача).")
        
        col_g, col_a = st.columns([2, 1])
        with col_a:
            st.markdown("#### 📊 Аналіз")
            imb_trend, _ = analyze_period_change(live_data['imb_p'])
            st.info(f"Тренд ціни (4г): {imb_trend}")
            
            if data_today['imb_p'] is not None:
                try:
                    p_max = safe_float(data_today['imb_p'].max())
                    p_min = safe_float(data_today['imb_p'].min())
                    st.write(f"**Спред:** {(p_max - p_min):.2f} €")
                except: pass
            
            def get_imb_stats(d):
                if d is None: return ["-"] * 5
                p_avg = safe_float(d['imb_p'].mean()) if d['imb_p'] is not None else 0
                v_max_l = safe_float(d['imb_v'].max()) if d['imb_v'] is not None else 0
                v_max_s = safe_float(d['imb_v'].min()) if d['imb_v'] is not None else 0
                p_max = safe_float(d['imb_p'].max()) if d['imb_p'] is not None else 0
                p_min = safe_float(d['imb_p'].min()) if d['imb_p'] is not None else 0
                return [f"{p_max:.1f} €", f"{p_min:.1f} €", f"{p_avg:.1f} €", f"{v_max_l:.0f} MW", f"{v_max_s:.0f} MW"]

            df_imb = pd.DataFrame({
                "Показник": ["Макс. Ціна", "Мін. Ціна", "Сер. Ціна", "Макс. Профіцит (+)", "Макс. Дефіцит (-)"],
                "Сьогодні": get_imb_stats(data_today),
                "Вчора": get_imb_stats(hist_data['yesterday']),
                "Рік тому": get_imb_stats(hist_data['last_year'])
            })
            st.table(df_imb)

        with col_g:
            if live_data['imb_p'] is not None:
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                df_p = live_data['imb_p'].loc[now-timedelta(hours=24):now].fillna(method='ffill').fillna(0)
                
                if isinstance(df_p, pd.DataFrame) and len(df_p.columns) > 1:
                    labels = ["Long (Надлишок)", "Short (Дефіцит)"]
                    for i, c in enumerate(df_p.columns):
                        name = labels[i] if i < 2 else str(c)
                        fig.add_trace(go.Scatter(x=df_p.index, y=df_p[c], name=f"Ціна {name}", line=dict(width=2)), secondary_y=True)
                else:
                    y_vals = df_p.values.flatten() if isinstance(df_p, pd.DataFrame) else df_p.values
                    fig.add_trace(go.Scatter(x=df_p.index, y=y_vals, name="Ціна (Єдина)", line=dict(color='#ffaa00', width=2)), secondary_y=True)
                
                if live_data['imb_v'] is not None:
                    df_v = live_data['imb_v'].loc[now-timedelta(hours=24):now].fillna(0)
                    vals = df_v.values.flatten()
                    cols = ['#ff0044' if x<0 else '#00ff41' for x in vals]
                    fig.add_trace(go.Bar(x=df_v.index, y=vals, marker_color=cols, name="Обсяг (MW)", opacity=0.5), secondary_y=False)
                fig.update_layout(template="plotly_dark", height=450, title="Небаланси (24 год)", margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig, use_container_width=True)

    # TAB 2: GREEN
    with tabs[1]:
        st.markdown("### 🌱 Аналіз ВДЕ")
        def calc_res_stats(dataset):
            if (dataset is None or dataset.get('gen') is None or dataset['gen'].empty): return ["-"] * 6
            gen = dataset['gen'].fillna(0)
            green_cols = [c for c in gen.columns if any(x in c for x in ['Вітер','Сонце','ГЕС','Біо'])]
            total_mw = safe_float(gen.sum().sum())
            green_mw = safe_float(gen[green_cols].sum().sum())
            share_res = (green_mw / total_mw * 100) if total_mw > 0 else 0
            avg_p = safe_float(dataset['prices'].mean()) if dataset.get('prices') is not None else 0
            est_val = green_mw * avg_p / 1000000 
            def safe_sum(term):
                cols = [c for c in gen.columns if term in c]
                return safe_float(gen[cols].sum().sum()) if cols else 0
            return [f"{share_res:.1f}%", f"{green_mw/1000:.1f} GWh", f"{est_val:.2f} млн €",
                    f"{(safe_sum('Сонце')/green_mw*100 if green_mw else 0):.0f}%",
                    f"{(safe_sum('Вітер')/green_mw*100 if green_mw else 0):.0f}%",
                    f"{(safe_sum('ГЕС')/green_mw*100 if green_mw else 0):.0f}%"]

        c1, c2 = st.columns([1, 2])
        with c1:
            df_res = pd.DataFrame({
                "Показник": ["Частка ВДЕ", "Обсяг", "Вартість (Est.)", "Сонце (Mix)", "Вітер (Mix)", "Гідро (Mix)"],
                "Сьогодні": calc_res_stats(data_today),
                "Вчора": calc_res_stats(hist_data['yesterday']),
                "Рік тому": calc_res_stats(hist_data['last_year'])
            })
            st.table(df_res)
        with c2:
            if data_today['gen'] is not None and not data_today['gen'].empty:
                g = data_today['gen'].fillna(0)
                green = [c for c in g.columns if any(x in c for x in ['Вітер','Сонце','ГЕС','Біо'])]
                if green:
                    fig = go.Figure()
                    for c in green: 
                        if g[c].sum() > 0:
                            fig.add_trace(go.Scatter(x=g.index, y=g[c], name=c, stackgroup='one'))
                    fig.update_layout(template="plotly_dark", title="Профіль ВДЕ (Сьогодні)", height=400, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig, use_container_width=True)

    # TAB 3: SPOT
    with tabs[2]:
        st.markdown("### 📉 РДН")
        def calc_dam_stats(dataset):
            if dataset is None or dataset.get('prices') is None: return ["-"] * 5
            p = dataset['prices'].fillna(method='ffill')
            l = dataset.get('load')
            avg, mn, mx = safe_float(p.mean()), safe_float(p.min()), safe_float(p.max())
            vol_gwh = safe_float(l.sum()) / 1000 if l is not None else 0
            cost_m = 0
            if l is not None:
                try:
                    if isinstance(p, pd.DataFrame): p = p.iloc[:,0]
                    if isinstance(l, pd.DataFrame): l = l.iloc[:,0]
                    comb = pd.concat([p, l], axis=1).dropna()
                    cost_m = safe_float((comb.iloc[:,0] * comb.iloc[:,1]).sum()) / 1000000
                except: pass
            return [f"{mn:.2f} €", f"{mx:.2f} €", f"{avg:.2f} €", f"{vol_gwh:.1f} GWh", f"{cost_m:.2f} млн €"]

        df_dam = pd.DataFrame({
            "Показник": ["Мін. Ціна", "Макс. Ціна", "Сер. Ціна", "Обсяг (Load)", "Оборот Ринку"],
            "Сьогодні": calc_dam_stats(data_today),
            "Вчора": calc_dam_stats(hist_data['yesterday']),
            "Рік тому": calc_dam_stats(hist_data['last_year'])
        })
        st.table(df_dam)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=live_data['prices'].index, y=live_data['prices'].values, name="Ціна", line=dict(color='#00ff41', width=2)))
        fig.update_layout(template="plotly_dark", height=350, title="Динаміка РДН", margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)

    # TAB 4: GEN
    with tabs[3]:
        st.markdown("### 🏗️ Генерація")
        if live_data['gen'] is not None:
            g = live_data['gen'].loc[now-timedelta(hours=24):now].fillna(0)
            if not g.empty:
                last_row = g.iloc[-1].sort_values(ascending=False)
                st.write(f"**Поточний мікс:**")
                cols = st.columns(5)
                for i, (k, v) in enumerate(last_row.head(5).items()):
                    cols[i].metric(k, f"{v:.0f} MW")
            fig = go.Figure()
            for c in g.columns:
                if g[c].sum() > 500: fig.add_trace(go.Scatter(x=g.index, y=g[c], name=c, stackgroup='one'))
            fig.update_layout(template="plotly_dark", height=450, title="Стек Генерації (24 год)", margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)
        else: st.warning("Дані відсутні")
else:
    st.warning(f"❌ Дані для зони {selected_code} тимчасово недоступні.")
