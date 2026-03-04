import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide")

# --- EXECUTIVE THEME ---
COLORS = {"navy": "#1B263B", "gold": "#A68A64", "success": "#2D6A4F", "alert": "#941B0C", "bg": "#F8F9FA"}

st.markdown(f"""
    <style>
    .stApp {{background-color: {COLORS['bg']};}}
    .metric-card {{background: white; padding: 20px; border-radius: 8px; border: 1px solid #E2E8F0;}}
    h1, h2 {{color: {COLORS['navy']}; font-weight: 800;}}
    .css-1r6slp0 {{padding-top: 0rem;}} 
    </style>
""", unsafe_allow_html=True)

# --- DATA ENGINE ---
@st.cache_data(ttl=600)
def load_data():
    c = st.secrets["connections"]["mysql"]
    url = f"mysql+pymysql://{c['username']}:{c['password']}@{c['host']}:{c['port']}/{c['database']}"
    # SSL config for TiDB
    connect_args = {"ssl": {"ca": "/etc/ssl/certs/ca-certificates.crt"}}
    engine = create_engine(url, connect_args=connect_args)
    
    query = "SELECT log_date, well_usage_m3, booster_reading FROM water_logs ORDER BY log_date ASC"
    df = pd.read_sql(query, engine)
    
    df['log_date'] = pd.to_datetime(df['log_date'])
    df = df.groupby('log_date').agg({'well_usage_m3':'sum', 'booster_reading':'max'}).reset_index()
    df['Distribution'] = df['booster_reading'].diff().fillna(0)
    df['Efficiency'] = (df['Distribution'] / df['well_usage_m3'].replace(0, np.nan)) * 100
    df['Rolling_Avg'] = df['well_usage_m3'].rolling(30).mean()
    return df

df = load_data()

# --- SIDEBAR: LOGO & CONTROLS ---
with st.sidebar:
    # Use the relative path to the assets folder
    if os.path.exists("assets/HMA_logo_color.jpg"):
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    
    st.header("Executive Controls")
    pop = st.number_input("Campus Population", 370)
    sel_date = st.selectbox("Operational Date", df['log_date'].dt.date.unique()[::-1])
    
    st.divider()
    st.subheader("Reference Standards")
    st.markdown("[WHO Guidelines (Table 5.1)](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("[Sphere Handbook (Ch 6)](https://handbook.spherestandards.org/en/sphere/#ch006)")

# --- DASHBOARD LOGIC ---
curr = df[df['log_date'].dt.date == sel_date].iloc[0]
prod = curr['well_usage_m3']
dist = curr['Distribution']
eff = curr['Efficiency']

# Anomaly Detection Engine
z_score = (prod - curr['Rolling_Avg']) / df['well_usage_m3'].std()

# --- MAIN UI ---
st.title("Water Infrastructure Executive Report")
st.markdown(f"**Data snapshot for:** {sel_date}")

# KPI Row
c1, c2, c3 = st.columns(3)
c1.metric("Well Production", f"{prod:.1f} m³", delta=f"{prod - curr['Rolling_Avg']:.1f} vs Avg")
c2.metric("Efficiency Ratio", f"{eff:.1f}%", help="Booster reading as % of Well Output")
c3.metric("Per Capita Usage", f"{(dist*1000)/pop:.0f} L/c/d")

# Analytical Insight Engine
st.subheader("Operational Diagnostics")
if abs(z_score) > 2:
    st.error(f"**CRITICAL:** Production variance is high. Investigate pump or well integrity.")
elif eff < 75:
    st.warning(f"**CAUTION:** Distribution efficiency is low. Check for downstream leaks or booster meter error.")
else:
    st.success("**OPERATIONAL STATUS: NORMAL**")

# Chart
fig = go.Figure()
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color=COLORS['navy']))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color=COLORS['gold'], width=3)))
fig.update_layout(template="plotly_white", margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)
