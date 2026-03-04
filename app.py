import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine

# --- PAGE CONFIG ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide")

# --- EXECUTIVE CSS & BRANDING ---
st.markdown("""
    <style>
    .metric-card { background: #FFFFFF; padding: 20px; border-radius: 10px; border-left: 5px solid #1B263B; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .stApp { background-color: #F4F7F6; }
    h1 { color: #1B263B; font-weight: 800; margin-bottom: 0px; }
    .insight-text { font-size: 1.1rem; color: #4A5568; font-style: italic; }
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
    daily = df.groupby('log_date').agg({'well_usage_m3':'sum', 'booster_reading':'max'}).reset_index()
    daily['Consumption'] = daily['booster_reading'].diff().fillna(0)
    daily['Rolling_30d'] = daily['well_usage_m3'].rolling(30).mean()
    return daily

df = load_data()

# --- SIDEBAR: Institutional Context ---
with st.sidebar:
    st.image("https://www.hmacademy.org/wp-content/uploads/2022/10/HMA-Logo.png", width=200)
    st.markdown("### Infrastructure Analytics")
    pop = st.number_input("Campus Population", 370)
    
    st.divider()
    st.subheader("Resources")
    st.markdown("[WHO Guidelines (Table 5.1)](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("[Sphere Handbook (Ch 6)](https://handbook.spherestandards.org/en/sphere/#ch006)")
    st.caption("Buildings & Grounds Division | HMA")

# --- DASHBOARD LOGIC ---
latest = df.iloc[-1]
prod = latest['well_usage_m3']
avg = latest['Rolling_30d']

# --- MAIN UI ---
st.title("Water Infrastructure Overview")
st.write(f"**Latest Operational Data:** {latest['log_date'].strftime('%B %d, %Y')}")

# Insight Module
variance = prod - avg
insight = "Operational performance is stable."
if variance > 15: insight = "⚠️ ALERT: High consumption anomaly detected compared to 30-day average."
elif variance < -15: insight = "✅ Efficiency milestone: Consumption is significantly below rolling average."

st.markdown(f"<div class='insight-text'><b>Managerial Insight:</b> {insight}</div>", unsafe_allow_html=True)

# KPI Metrics
k1, k2, k3 = st.columns(3)
with k1: st.metric("Current Production", f"{prod:.1f} m³", f"{variance:.1f} vs Avg")
with k2: st.metric("Campus LPCD", f"{(latest['Consumption']*1000)/pop:.0f} L")
with k3: st.metric("System Load", f"{(prod/avg)*100:.0f}% of Avg")

# Visuals
st.subheader("Performance Trend Analysis")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df['log_date'], y=df['well_usage_m3'], name="Well Production", line_color="#1B263B", fill='tozeroy'))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Rolling_30d'], name="30-Day Baseline", line=dict(color="#A68A64", dash='dash')))
fig.update_layout(height=400, template="plotly_white", margin=dict(l=0,r=0,t=20,b=0))
st.plotly_chart(fig, use_container_width=True)
