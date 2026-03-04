import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide")

# --- EXECUTIVE DESIGN SYSTEM ---
COLORS = {"navy": "#0f233a", "gold": "#d4af37", "success": "#0f9d58", "alert": "#d93025", "bg": "#f8f9fa"}

st.markdown(f"""
    <style>
    .stApp {{background-color: {COLORS['bg']};}}
    .metric-card {{background: white; padding: 20px; border-radius: 12px; border-left: 5px solid {COLORS['navy']}; box-shadow: 0 4px 6px rgba(0,0,0,0.1);}}
    h1 {{color: {COLORS['navy']}; font-size: 2.5rem; font-weight: 800;}}
    .stSlider {{padding-top: 10px;}}
    </style>
""", unsafe_allow_html=True)

# --- DATA ENGINE ---
@st.cache_data(ttl=600)
def load_data():
    c = st.secrets["connections"]["mysql"]
    url = f"mysql+pymysql://{c['username']}:{c['password']}@{c['host']}:{c['port']}/{c['database']}"
    engine = create_engine(url, connect_args={"ssl": {"ca": "/etc/ssl/certs/ca-certificates.crt"}})
    df = pd.read_sql("SELECT log_date, well_usage_m3, booster_reading FROM water_logs ORDER BY log_date ASC", engine)
    df['log_date'] = pd.to_datetime(df['log_date'])
    df = df.groupby('log_date').agg({'well_usage_m3':'sum', 'booster_reading':'max'}).reset_index()
    df['Distribution'] = df['booster_reading'].diff().fillna(0)
    df['Efficiency'] = (df['Distribution'] / df['well_usage_m3'].replace(0, np.nan)) * 100
    df['Rolling_Avg'] = df['well_usage_m3'].rolling(30).mean()
    return df

df = load_data()

# --- SIDEBAR ---
with st.sidebar:
    if os.path.exists("assets/HMA_logo_color.jpg"):
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    st.title("Command Center")
    pop = st.number_input("Campus Population", 370)
    goal = st.slider("Conservation Goal Target (%)", 0, 75, 10)
    sel_date = st.selectbox("Operational Date", df['log_date'].dt.date.unique()[::-1])

# --- DASHBOARD LOGIC ---
curr = df[df['log_date'].dt.date == sel_date].iloc[0]
prod = curr['well_usage_m3']
dist = curr['Distribution']
eff = curr['Efficiency']
target_val = curr['Rolling_Avg'] * (1 - goal/100)

# --- MAIN UI ---
st.title("WATER INFRASTRUCTURE EXECUTIVE REPORT")

# KPI ROW
k1, k2, k3 = st.columns(3)
with k1: st.metric("Daily Production", f"{prod:.1f} m³", delta=f"{prod - curr['Rolling_Avg']:.1f} vs Avg")
with k2: st.metric("Conservation Target", f"{target_val:.1f} m³", delta=f"-{goal}% Target")
with k3: st.metric("Campus LPCD", f"{(dist*1000)/pop:.0f} L")

# DIAGNOSTIC GAUGE & INSIGHTS
col1, col2 = st.columns([1, 2])

with col1:
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=eff,
        gauge={'bar': {'color': COLORS['navy']}, 'axis': {'range': [0, 100]}}
    ))
    fig_gauge.update_layout(height=250, margin=dict(t=30, b=0, l=20, r=20))
    st.plotly_chart(fig_gauge, use_container_width=True)
    
    if eff < 70: st.error("⚠️ SYSTEM LEAK DETECTED: Low Efficiency Ratio.")
    else: st.success("✅ SYSTEM OPERATING NORMALLY")

with col2:
    st.subheader("Time-Series Performance")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color=COLORS['navy']))
    fig.add_trace(go.Scatter(x=df['log_date'], y=df['Rolling_Avg']*(1-goal/100), name="Goal Target", 
                             line=dict(color=COLORS['gold'], width=3, dash='dash')))
    fig.update_layout(height=350, template="plotly_white", margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig, use_container_width=True)
