import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import io

st.set_page_config(page_title="HMA Command Center", layout="wide")

# --- CSS: SCADA-Inspired Industrial Design ---
st.markdown("""
    <style>
    .metric-card {background: #FFFFFF; border-left: 5px solid #1B263B; padding: 15px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);}
    .header-box {background: #1B263B; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;}
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
    return df

df = load_data()

# --- HEADER & GLOBAL ACTIONS ---
col_head1, col_head2 = st.columns([3, 1])
with col_head1: st.title("💧 HMA Water Command Center")
with col_head2:
    # EXPORT MODULE
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export Data (CSV)", csv, "water_data.csv", "text/csv")

# --- SIDEBAR: DYNAMIC CONTROLS ---
with st.sidebar:
    st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    st.subheader("Facility Parameters")
    pop = st.number_input("Campus Population", min_value=1, value=370)
    
    # WHO Standards (100 LPCD Baseline)
    st.divider()
    st.markdown("### Compliance Baselines")
    st.info("WHO Target: 100 L/c/d (Modern Boarding School)")

# --- DASHBOARD LOGIC ---
latest = df.iloc[-1]
lpcd = (latest['Distribution'] * 1000) / pop
who_target = 100

# --- KPI GRID ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Production", f"{latest['well_usage_m3']:.1f} m³")
k2.metric("Distribution", f"{latest['Distribution']:.1f} m³")
k3.metric("Efficiency", f"{(latest['Distribution']/latest['well_usage_m3'])*100:.1f}%")
k4.metric("Per Capita (LPCD)", f"{lpcd:.0f} L", delta=f"{lpcd - who_target:.1f} vs WHO Std", delta_color="inverse")

# --- ADVANCED DIAGNOSTICS ---
if lpcd > 120: st.error("🚨 ALERT: High usage detected. Per-capita consumption exceeds WHO recommended ceiling.")
elif lpcd > 100: st.warning("⚠️ WARNING: Usage above WHO optimal baseline.")
else: st.success("✅ System Status: Compliant with WHO Standards.")

# --- ANALYTICAL VISUALIZATION ---
fig = go.Figure()
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color="#A68A64", width=3)))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['well_usage_m3'], name="Loss Gap", fill='tonexty', fillcolor='rgba(148, 27, 12, 0.2)', line=dict(width=0)))
fig.update_layout(height=450, template="plotly_white", hovermode="x unified", legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)
