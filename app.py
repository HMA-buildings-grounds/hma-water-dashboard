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
st.set_page_config(page_title="HMA Water Infrastructure Dashboard", layout="wide")

# Branding Colors
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#0f9d58"
ALERT_RED = "#d93025"

# Custom CSS for "Card" look
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 28px; font-weight: bold; color: #0f233a; }
    .main { background-color: #f8f9fa; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA ENGINE (FIXED FOR HMA SHEET)
# ==========================================
@st.cache_data(ttl="1h")
def load_and_process_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    # ማሳሰቢያ፡ ያንተን ትክክለኛ የሺት ሊንክ እዚህ ጋር አስገብቻለሁ
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit#gid=1207984195"
    df_raw = conn.read(spreadsheet=url)
    
    # የሺቱን ርዕስ ጥሎ ትክክለኛውን ሄደር (Date, Time...) ለማግኘት፡
    df = df_raw.copy()
    # ትክክለኛው ሄደር ያለው በሁለተኛው መስመር ላይ ነው
    df.columns = df.iloc[0] 
    df = df[1:].reset_index(drop=True)
    
    # የአምዶችን ስም ማጽዳት (Spaces ካሉ ለማጥፋት)
    df.columns = [str(c).strip() for c in df.columns]

    def to_num(val):
        try: return float(re.split(r'\(|\s', str(val))[0])
        except: return np.nan

    # አምዶቹን መፈለግ
    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    booster_col = next((c for c in df.columns if "Booster" in c and "Reading" in c), None)
    time_col = "Time" if "Time" in df.columns else df.columns[1]

    if usage_col: df['Well_Usage_m3'] = df[usage_col].apply(to_num)
    if booster_col: df['Booster_Reading'] = pd.to_numeric(df[booster_col], errors='coerce')

    # ሰዓቱን መለየት (8:00 AM እና 4:00 PM ብቻ)
    df = df[df[time_col].isin(['8:00 AM', '4:00 PM'])].copy()
    
    df['Date_Clean'] = pd.to_datetime(df['Date'] + " 2026", errors='coerce')
    
    daily = df.groupby('Date_Clean').agg({'Well_Usage_m3':'sum', 'Booster_Reading':'max'}).reset_index()
    daily['Consumption_m3'] = daily['Booster_Reading'].diff()
    
    install_date = pd.Timestamp("2026-02-05")
    daily.loc[daily['Date_Clean'] < install_date, 'Consumption_m3'] = np.nan
    daily['Rolling_Avg_30d'] = daily['Well_Usage_m3'].rolling(window=30).mean()
    
    return daily.dropna(subset=['Date_Clean'])

try:
    df_master = load_and_process_data()
except Exception as e:
    st.error(f"Data Loading Error: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR CONTROLS
# ==========================================
with st.sidebar:
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", width=150) # HMA Logo
    st.header("CONTROLS")
    pop = st.number_input("Population", value=370, step=10)
    savings_target = st.slider("Goal Target (%)", 0, 30, 10)
    
    st.header("STANDARDS")
    st.info("WHO Baseline: 100L/day")
    
    available_dates = sorted(df_master['Date_Clean'].dt.date.unique(), reverse=True)
    selected_date = st.selectbox("Select Date", available_dates)

# ==========================================
# 4. MAIN DASHBOARD UI
# ==========================================
st.title("💧 WATER INFRASTRUCTURE DASHBOARD")
st.markdown(f"<p style='color: gray;'>HAILE-MANAS ACADEMY | BUILDINGS & GROUNDS | Last Updated: {df_master['Date_Clean'].max().date()}</p>", unsafe_allow_html=True)

# Filter data for selected date
current_data = df_master[df_master['Date_Clean'].dt.date == selected_date].iloc[0]
prod = current_data['Well_Usage_m3']
cons = current_data['Consumption_m3'] if not np.isnan(current_data['Consumption_m3']) else 0
lpcd = (cons * 1000) / pop if pop > 0 and cons > 0 else 0
eff = (cons / prod * 100) if prod > 0 and cons > 0 else 0
loss = prod - cons if cons > 0 else 0

# KPI ROW
kpi1, kpi2, kpi3 = st.columns(3)

with kpi1:
    st.metric("WHO Standard (LPCD)", f"{lpcd:.0f} L", f"{lpcd-100:.0f} vs Target", delta_color="inverse")
with kpi2:
    st.metric("Infrastructure Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Loss", delta_color="inverse")
with kpi3:
    st.metric("Conservation Goal", f"{prod:.1f} m³", f"Target: -{savings_target}%")

# CHARTS ROW
col_graph, col_gauge = st.columns([2, 1])

with col_graph:
    st.subheader("Production Trend vs. Goal")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=df_master['Date_Clean'], y=df_master['Well_Usage_m3'], name='Actual',
                               line=dict(color=NAVY_BLUE, width=2), fill='tozeroy'))
    fig_t.add_trace(go.Scatter(x=df_master['Date_Clean'], y=df_master['Rolling_Avg_30d']*(1-savings_target/100), name='Target',
                               line=dict(color=SUCCESS_GREEN, dash='dash')))
    fig_t.update_layout(margin=dict(l=0,r=0,t=20,b=0), height=350, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_t, use_container_width=True)

with col_gauge:
    st.subheader("Metering Success")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff,
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE}}))
    fig_g.update_layout(margin=dict(l=20,r=20,t=40,b=0), height=300)
    st.plotly_chart(fig_g, use_container_width=True)

# BAR CHART
st.subheader("Daily Distribution Balance (Production vs Consumption)")
fig_b = go.Figure()
fig_b.add_trace(go.Bar(x=df_master['Date_Clean'], y=df_master['Well_Usage_m3'], name='Well Production', marker_color='#cfd8dc'))
fig_b.add_trace(go.Bar(x=df_master['Date_Clean'], y=df_master['Consumption_m3'], name='Booster Distribution', marker_color=NAVY_BLUE))
fig_b.update_layout(barmode='overlay', height=300, margin=dict(l=0,r=0,t=20,b=0))
st.plotly_chart(fig_b, use_container_width=True)
