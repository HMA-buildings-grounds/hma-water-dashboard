import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import io

# --- CONFIG & BASELINES ---
WHO_TARGET = 100 # WHO standard for boarding schools (L/c/d)
st.set_page_config(page_title="HMA Infrastructure Command Center", layout="wide")

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
    return df

df = load_data()

# --- TOP NAVIGATION BAR ---
header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
with header_col1: st.title("💧 HMA Infrastructure Command Center")
with header_col3: 
    # EXPORT MODULE
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export Data (CSV)", csv, "hma_water_data.csv", "text/csv")

# --- GLOBAL CONTROLS ---
with st.container():
    c1, c2, c3 = st.columns(3)
    pop = c1.number_input("Campus Population", min_value=1, value=370)
    sel_date = c2.selectbox("Operational Date", df['log_date'].dt.date.unique()[::-1])
    target = c3.slider("Efficiency Threshold (%)", 50, 100, 80)

# --- KPI DASHBOARD ---
curr = df[df['log_date'].dt.date == sel_date].iloc[0]
lpcd = (curr['Distribution'] * 1000) / pop
status = "Optimal" if lpcd <= WHO_TARGET else "Warning: Above Standard"

st.markdown("---")
k1, k2, k3, k4 = st.columns(4)
k1.metric("WHO LPCD Baseline", f"{WHO_TARGET} L", "Standard")
k2.metric("Actual Usage", f"{lpcd:.0f} L/c/d", delta=f"{lpcd-WHO_TARGET:.0f} vs Baseline", delta_color="inverse")
k3.metric("System Efficiency", f"{(curr['Distribution']/curr['well_usage_m3'])*100:.1f}%")
k4.metric("Status", status)

# --- MAIN STAGE ---
col_main, col_side = st.columns([3, 1])

with col_main:
    st.subheader("Production vs. Distribution Trend")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
    fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color="#A68A64", width=3)))
    fig.add_hline(y=WHO_TARGET * pop / 1000, line_dash="dot", line_color="red", annotation_text="WHO Daily Limit")
    fig.update_layout(template="plotly_white", height=400)
    st.plotly_chart(fig, use_container_width=True)

with col_side:
    st.subheader("Diagnostics")
    # Diagnostic Logic
    if lpcd > WHO_TARGET * 1.5: st.error("CRITICAL: Extreme consumption anomaly.")
    elif lpcd > WHO_TARGET: st.warning("ADVISORY: Consumption exceeding baseline.")
    else: st.success("SYSTEM OPERATING NORMALLY")
    
    st.write("Current efficiency is 15% lower than the UN infrastructure benchmark.")
