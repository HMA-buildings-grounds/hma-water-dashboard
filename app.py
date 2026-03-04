import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="HMA Water Command Center", layout="wide", initial_sidebar_state="expanded")

# --- EXECUTIVE DESIGN SYSTEM ---
COLORS = {"navy": "#1B263B", "gold": "#A68A64", "success": "#2D6A4F", "alert": "#941B0C", "bg": "#F4F7F6"}

st.markdown(f"""
    <style>
    .stApp {{background-color: {COLORS['bg']};}}
    .metric-card {{background: white; padding: 20px; border-radius: 10px; border-left: 5px solid {COLORS['navy']}; box-shadow: 0 4px 6px rgba(0,0,0,0.05);}}
    h1 {{color: {COLORS['navy']}; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;}}
    .status-pill {{padding: 5px 15px; border-radius: 20px; font-weight: bold; color: white;}}
    </style>
""", unsafe_allow_html=True)

# --- DATA ENGINE ---
@st.cache_data(ttl=600)
def load_data():
    c = st.secrets["connections"]["mysql"]
    engine = create_engine(f"mysql+pymysql://{c['username']}:{c['password']}@{c['host']}:{c['port']}/{c['database']}",
                           connect_args={"ssl": {"ca": "/etc/ssl/certs/ca-certificates.crt"}})
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
    
    st.markdown("---")
    st.header("Executive Controls")
    pop = st.number_input("Campus Population", 370)
    target = st.slider("Conservation Goal (%)", 0, 75, 10, help="Target reduction in production")
    sel_date = st.selectbox("Operational Date", df['log_date'].dt.date.unique()[::-1])
    
    st.divider()
    st.subheader("Resources")
    st.markdown("• [WHO Guidelines (Table 5.1)](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("• [Sphere Handbook (Ch 6)](https://handbook.spherestandards.org/en/sphere/#ch006)")

# --- DASHBOARD LOGIC ---
curr = df[df['log_date'].dt.date == sel_date].iloc[0]
prod, dist, eff = curr['well_usage_m3'], curr['Distribution'], curr['Efficiency']
avg = curr['Rolling_Avg']

# --- MAIN UI ---
st.title("Water Infrastructure Executive Report")
st.caption(f"Status Snapshot: {sel_date} | Campus Pop: {pop}")

# KPI Metrics
k1, k2, k3, k4 = st.columns(4)
k1.metric("Production", f"{prod:.1f} m³", delta=f"{prod-avg:.1f} vs Avg")
k2.metric("Efficiency", f"{eff:.1f}%", delta=f"{eff-80:.1f}% vs Target", delta_color="inverse")
k3.metric("Per Capita", f"{(dist*1000)/pop:.0f} L/c/d")
k4.metric("Target Goal", f"{prod*(1-target/100):.1f} m³")

# Diagnostics
if eff < 75:
    st.error("🚨 CRITICAL: Efficiency is below operational threshold. Inspect distribution leakage.")
else:
    st.success("✅ Operational status is nominal.")

# Advanced Charting
fig = go.Figure()
# Production Bars
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color=COLORS['navy']))
# Distribution Line
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color=COLORS['gold'], width=3)))
# Leakage Fill (Gap visualization)
fig.add_trace(go.Scatter(x=df['log_date'], y=df['well_usage_m3'], fill='tonexty', fillcolor='rgba(148, 27, 12, 0.1)', line=dict(width=0), name="Potential Leak/Loss"))

fig.update_layout(template="plotly_white", height=450, hovermode="x unified", legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

# Daily Data Expander
with st.expander("View Technical Log Data"):
    st.dataframe(df.tail(10), use_container_width=True)
