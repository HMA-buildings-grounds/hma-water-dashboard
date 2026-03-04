import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine

# --- CONFIG ---
st.set_page_config(page_title="HMA Command Center", layout="wide")

# --- UI LOGIC ---
def get_who_target(pop):
    """Sphere Handbook/WHO standard for high-service boarding: ~100 L/c/d"""
    return 100 

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
    return df

df = load_data()

# --- SIDEBAR: COMMAND CENTER ---
with st.sidebar:
    st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    st.markdown("## ⚙️ Command Center")
    pop = st.number_input("Daily Campus Occupancy", 370, help="Total personnel on-site")
    target_lpcd = st.slider("WHO Standard Target (L/c/d)", 50, 150, 100)
    
    st.divider()
    st.markdown("### Data Export")
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download CSV Dataset", csv, "hma_water_data.csv", "text/csv")
    
# --- MAIN DASHBOARD ---
st.title("💧 Water Infrastructure Management")

# KPI GRID
curr = df.iloc[-1]
lpcd = (curr['Distribution'] * 1000) / pop
c1, c2, c3, c4 = st.columns(4)
c1.metric("Production", f"{curr['well_usage_m3']:.1f} m³")
c2.metric("Efficiency", f"{curr['Efficiency']:.1f}%")
c3.metric("Per Capita (L/c/d)", f"{lpcd:.0f}", delta=f"{lpcd-target_lpcd:.1f} vs WHO Target")
c4.metric("Water Loss", f"{curr['well_usage_m3'] - curr['Distribution']:.1f} m³")

# DIAGNOSTICS (THE COMMANDER)
st.markdown("---")
col_a, col_b = st.columns([3, 1])
with col_a:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
    fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color="#A68A64", width=3)))
    fig.update_layout(height=400, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

with col_b:
    st.subheader("Diagnostics")
    if lpcd > target_lpcd: st.error("🚨 OVER CONSUMPTION: Per capita usage exceeds WHO boarding school benchmarks.")
    else: st.success("✅ CONSUMPTION: Within international compliance standards.")
    
    # Efficiency Gauge
    fig_g = go.Figure(go.Indicator(mode="gauge+number", value=curr['Efficiency'], 
                                   gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"}}))
    fig_g.update_layout(height=250)
    st.plotly_chart(fig_g, use_container_width=True)
