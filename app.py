import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide", page_icon="💧")

# --- EXECUTIVE THEME ---
COLORS = {"navy": "#1B263B", "gold": "#A68A64", "success": "#2D6A4F", "alert": "#941B0C", "bg": "#F8F9FA"}

st.markdown(f"""
    <style>
    .stApp {{background-color: {COLORS['bg']};}}
    .metric-card {{background: white; padding: 20px; border-radius: 12px; border: 1px solid #E2E8F0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);}}
    h1 {{color: {COLORS['navy']}; font-weight: 800; margin-bottom: 20px;}}
    .diag-box {{padding: 15px; border-radius: 8px; margin-bottom: 20px;}}
    </style>
""", unsafe_allow_html=True)

# --- DATA ENGINE ---
@st.cache_data(ttl=600)
def load_data():
    c = st.secrets["connections"]["mysql"]
    url = f"mysql+pymysql://{c['username']}:{c['password']}@{c['host']}:{c['port']}/{c['database']}"
    connect_args = {"ssl": {"ca": "/etc/ssl/certs/ca-certificates.crt"}}
    engine = create_engine(url, connect_args=connect_args)
    
    df = pd.read_sql("SELECT log_date, well_usage_m3, booster_reading FROM water_logs ORDER BY log_date ASC", engine)
    df['log_date'] = pd.to_datetime(df['log_date'])
    df = df.groupby('log_date').agg({'well_usage_m3':'sum', 'booster_reading':'max'}).reset_index()
    df['Distribution'] = df['booster_reading'].diff().fillna(0)
    df['Efficiency'] = (df['Distribution'] / df['well_usage_m3'].replace(0, np.nan)) * 100
    return df

df = load_data()

# --- SIDEBAR ---
with st.sidebar:
    if os.path.exists("assets/HMA_logo_color.jpg"):
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    
    st.markdown("## Operational Controls")
    pop = st.number_input("Campus Population", 370)
    target = st.slider("Conservation Target (%)", 0, 75, 10)
    sel_date = st.selectbox("Operational Date", df['log_date'].dt.date.unique()[::-1])
    
    st.divider()
    st.markdown("### Resources")
    st.markdown("• [WHO Guidelines (Table 5.1)](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("• [Sphere Handbook (Ch 6)](https://handbook.spherestandards.org/en/sphere/#ch006)")

# --- DASHBOARD LOGIC ---
curr = df[df['log_date'].dt.date == sel_date].iloc[0]
prod = curr['well_usage_m3']
dist = curr['Distribution']
eff = curr['Efficiency']
loss = prod - dist if prod > dist else 0

# --- MAIN UI ---
st.title("WATER INFRASTRUCTURE DASHBOARD")

# KPI ROW
c1, c2, c3, c4 = st.columns(4)
c1.metric("Well Production", f"{prod:.1f} m³")
c2.metric("Efficiency Ratio", f"{eff:.1f}%", delta=f"{eff - 80:.1f}% vs Target" if eff < 80 else None, delta_color="inverse")
c3.metric("Per Capita", f"{(dist*1000)/pop:.0f} L/c/d")
c4.metric("Water Loss (Leakage)", f"{loss:.1f} m³", delta="High Loss" if loss > 20 else None, delta_color="inverse")

# DIAGNOSTICS
st.subheader("Operational Diagnostics")
if eff < 70:
    st.error("🚨 CRITICAL: Efficiency below 70%. Immediate inspection of distribution network required.")
elif eff < 85:
    st.warning("⚠️ CAUTION: Efficiency suboptimal. Minor leakage likely present.")
else:
    st.success("✅ System Status: Normal operational range.")

# ADVANCED VISUALIZATION
fig = go.Figure()
# Production Bars
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color=COLORS['navy']))
# Distribution Line
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color=COLORS['gold'], width=3)))
# Leakage Gap Fill
fig.add_trace(go.Scatter(x=df['log_date'], y=df['well_usage_m3'], name="Water Loss (Potential Leak)", 
                         fill='tonexty', fillcolor='rgba(148, 27, 12, 0.2)', line=dict(width=0)))

fig.update_layout(template="plotly_white", margin=dict(l=0,r=0,t=20,b=0), hovermode="x unified", legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

# GAUGE
fig_g = go.Figure(go.Indicator(
    mode="gauge+number", value=eff, title={'text': "Efficiency %"},
    gauge={'axis': {'range': [0, 100]}, 'bar': {'color': COLORS['navy']}, 
           'steps': [{'range': [0, 70], 'color': '#FEE2E2'}, {'range': [70, 85], 'color': '#FEF9C3'}]}))
st.plotly_chart(fig_g, use_container_width=True)
