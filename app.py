import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import os

# --- PAGE SETUP ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide", page_icon="💧")

# --- EXECUTIVE CSS STYLING ---
st.markdown("""
    <style>
    .stApp {background-color: #F4F7F6;}
    .main-title {font-size: 2.5rem; color: #1B263B; font-weight: 800; border-bottom: 2px solid #A68A64; padding-bottom: 10px;}
    .metric-card {background: white; padding: 20px; border-radius: 12px; border: 1px solid #E2E8F0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);}
    .stSlider {padding-top: 10px;}
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
    return df

df = load_data()

# --- SIDEBAR: LOGO & INTERACTIVE CONTROLS ---
with st.sidebar:
    if os.path.exists("assets/HMA_logo_color.jpg"):
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    
    st.markdown("## Executive Controls")
    pop = st.number_input("Campus Population", 370)
    target = st.slider("Goal Target (%)", 0, 75, 10, help="Conservation goal for daily production")
    sel_date = st.selectbox("Operational Date", df['log_date'].dt.date.unique()[::-1])
    
    st.divider()
    st.subheader("Reference Standards")
    st.markdown("• [WHO Guidelines (Table 5.1)](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("• [Sphere Handbook (Ch 6)](https://handbook.spherestandards.org/en/sphere/#ch006)")

# --- DASHBOARD LOGIC ---
curr = df[df['log_date'].dt.date == sel_date].iloc[0]
prod = curr['well_usage_m3']
dist = curr['Distribution']
eff = curr['Efficiency']
target_val = prod * (1 - target/100)

# --- MAIN UI ---
st.markdown("<h1 class='main-title'>WATER INFRASTRUCTURE EXECUTIVE REPORT</h1>", unsafe_allow_html=True)

# KPI Row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Well Production", f"{prod:.1f} m³")
c2.metric("Efficiency", f"{eff:.1f}%")
c3.metric("Per Capita", f"{(dist*1000)/pop:.0f} L/c/d")
c4.metric("Target Goal", f"{target_val:.1f} m³")

# Advanced Diagnostic Section
st.subheader("Operational Diagnostics")
if eff < 70:
    st.error("⚠️ CRITICAL: Efficiency below 70%. Inspect distribution network for leaks.")
else:
    st.success("✅ System Status: Stable")

# Interactive Charts
fig = go.Figure()
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color="#A68A64", width=3)))
fig.add_hline(y=target_val, line_dash="dash", line_color="#941B0C", annotation_text="Conservation Goal")
fig.update_layout(template="plotly_white", hovermode="x unified", legend=dict(orientation="h"))
st.plotly_chart(fig, use_container_width=True)

# Gauge Chart for Efficiency
fig_g = go.Figure(go.Indicator(
    mode = "gauge+number", value = eff,
    domain = {'x': [0, 1], 'y': [0, 1]},
    gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"}},
    title = {'text': "Efficiency %"}))
st.plotly_chart(fig_g, use_container_width=True)
