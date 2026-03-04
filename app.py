import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import re

# ==========================================
# 1. PAGE CONFIG & STYLING
# ==========================================
st.set_page_config(page_title="HMA Water Dashboard", layout="wide")

# Institutional Color Palette
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#0f9d58"
ALERT_RED = "#d93025"

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 26px; font-weight: bold; color: #0f233a; }
    .main { background-color: #f8f9fa; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA ENGINE (ROBUST VERSION)
# ==========================================
@st.cache_data(ttl="1h")
def load_and_process_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit#gid=1207984195"
    
    # ዳታውን ማንበብ
    df_raw = conn.read(spreadsheet=url, header=None)
    
    # በሺቱ ውስጥ ሄደሩ ያለበትን መስመር መፈለግ (ብዙውን ጊዜ 'Date' የሚል ቃል ያለበት)
    header_row_idx = 0
    for i, row in df_raw.iterrows():
        if 'Date' in row.values:
            header_row_idx = i
            break
            
    # ትክክለኛውን ዳታ መለየት
    df = df_raw.iloc[header_row_idx+1:].copy()
    headers = df_raw.iloc[header_row_idx].values
    
    # ተመሳሳይ ስም ያላቸውን አምዶች (Duplicate columns) ማስተካከል
    clean_headers = []
    for i, h in enumerate(headers):
        h_str = str(h).strip() if pd.notnull(h) else f"Unnamed_{i}"
        if h_str in clean_headers:
            clean_headers.append(f"{h_str}_{i}")
        else:
            clean_headers.append(h_str)
            
    df.columns = clean_headers

    # ቁጥር ወደ መሆን መቀየር
    def to_num(val):
        try:
            if isinstance(val, str):
                return float(re.split(r'\(|\s', val)[0])
            return float(val)
        except: return np.nan

    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    booster_col = next((c for c in df.columns if "Booster" in c and "Reading" in c), None)

    if usage_col: df['Well_Usage_m3'] = df[usage_col].apply(to_num)
    if booster_col: df['Booster_Reading'] = pd.to_numeric(df[booster_col], errors='coerce')

    # የቀን መረጃን ማስተካከል
    df = df.dropna(subset=['Date'])
    df['Date_Clean'] = pd.to_datetime(df['Date'].astype(str) + " 2026", errors='coerce')
    
    # ዕለታዊ ድምር
    daily = df.groupby('Date_Clean').agg({'Well_Usage_m3':'sum', 'Booster_Reading':'max'}).reset_index()
    daily['Consumption_m3'] = daily['Booster_Reading'].diff()
    
    # ከየካቲት 5 በኋላ ያለውን ብቻ ለኮንሰምፕሽን መጠቀም
    install_date = pd.Timestamp("2026-02-05")
    daily.loc[daily['Date_Clean'] < install_date, 'Consumption_m3'] = np.nan
    daily['Rolling_Avg_30d'] = daily['Well_Usage_m3'].rolling(window=30, min_periods=1).mean()
    
    return daily.dropna(subset=['Date_Clean'])

try:
    df_master = load_and_process_data()
except Exception as e:
    st.error(f"⚠️ ዳታውን ማግኘት አልተቻለም። ስህተት፦ {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR & UI
# ==========================================
with st.sidebar:
    st.title("HMA Controls")
    pop = st.number_input("Population", value=370, step=10)
    savings_target = st.slider("Goal Target (%)", 0, 30, 10)
    selected_date = st.selectbox("Select Date", sorted(df_master['Date_Clean'].dt.date.unique(), reverse=True))

st.title("💧 WATER INFRASTRUCTURE DASHBOARD")
st.markdown(f"**HAILE-MANAS ACADEMY** | Last Updated: {df_master['Date_Clean'].max().date()}")

# KPI Calculations
day_data = df_master[df_master['Date_Clean'].dt.date == selected_date].iloc[0]
prod = day_data['Well_Usage_m3']
cons = day_data['Consumption_m3'] if pd.notnull(day_data['Consumption_m3']) else 0
lpcd = (cons * 1000) / pop if cons > 0 else 0
eff = (cons / prod * 100) if prod > 0 and cons > 0 else 0

col1, col2, col3 = st.columns(3)
col1.metric("WHO Standard (LPCD)", f"{lpcd:.0f} L", f"Vs 100L", delta_color="inverse")
col2.metric("System Efficiency", f"{eff:.1f}%", f"{prod-cons:.1f} m³ Loss", delta_color="inverse")
col3.metric("Daily Production", f"{prod:.1f} m³", f"Target: -{savings_target}%")

# Charts
c1, c2 = st.columns([2, 1])
with c1:
    fig_t = px.line(df_master, x='Date_Clean', y='Well_Usage_m3', title="Production Trend")
    fig_t.update_traces(line_color=NAVY_BLUE)
    st.plotly_chart(fig_t, use_container_width=True)
with c2:
    fig_g = go.Figure(go.Indicator(mode="gauge+number", value=eff, title={'text': "Efficiency %"},
                                   gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE}}))
    st.plotly_chart(fig_g, use_container_width=True)

st.subheader("Daily Distribution Balance")
fig_b = go.Figure()
fig_b.add_trace(go.Bar(x=df_master['Date_Clean'], y=df_master['Well_Usage_m3'], name='Production', marker_color='#cfd8dc'))
fig_b.add_trace(go.Bar(x=df_master['Date_Clean'], y=df_master['Consumption_m3'], name='Distribution', marker_color=NAVY_BLUE))
fig_b.update_layout(barmode='overlay')
st.plotly_chart(fig_b, use_container_width=True)
