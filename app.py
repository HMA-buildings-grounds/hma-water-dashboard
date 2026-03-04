import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import io

# --- PAGE SETUP ---
st.set_page_config(page_title="HMA Infrastructure Command", layout="wide")

# --- CSS: SCADA-Inspired Industrial Aesthetic ---
st.markdown("""
    <style>
    .kpi-card {background: #ffffff; border-radius: 6px; padding: 15px; border-left: 4px solid #1B263B; box-shadow: 0 2px 4px rgba(0,0,0,0.1);}
    .header-band {background: #1B263B; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;}
    .stApp {background-color: #F8F9FA;}
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
    df['LPCD'] = (df['Distribution'] * 1000) / 370 # Dynamic calc
    return df

df = load_data()

# --- TOP NAVIGATION BAR ---
header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
with header_col1: st.title("💧 HMA Infrastructure Command")
with header_col2: pop = st.number_input("Campus Occupancy", 370, 1000)
with header_col3:
    # EXPORT MODULE
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export CSV", csv, "HMA_Water_Data.csv", "text/csv")

# --- ANALYTICAL DASHBOARD ---
# WHO/Sphere Standard for Boarding Schools: ~100L per person per day
WHO_BASELINE = 100 

# Metric calculation with dynamic population
latest = df.iloc[-1]
current_lpcd = (latest['Distribution'] * 1000) / pop

c1, c2, c3 = st.columns(3)
c1.markdown(f"<div class='kpi-card'><b>Well Production</b><br><span style='font-size:24px'>{latest['well_usage_m3']:.1f} m³</span></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='kpi-card'><b>System Efficiency</b><br><span style='font-size:24px'>{(latest['Distribution']/latest['well_usage_m3'])*100:.1f}%</span></div>", unsafe_allow_html=True)
c3.metric("Per Capita (LPCD)", f"{current_lpcd:.0f} L", delta=f"{current_lpcd - WHO_BASELINE:.1f} vs WHO Std", delta_color="inverse")

# --- INTERACTIVE VISUALIZATION ---
st.subheader("Time-Series Infrastructure Load")
fig = go.Figure()
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color="#A68A64", width=3)))
fig.add_hline(y=WHO_BASELINE * pop / 1000, line_dash="dot", line_color="#941B0C", annotation_text="WHO Standard Limit")

fig.update_layout(template="plotly_white", hovermode="x unified", legend=dict(orientation="h"))
st.plotly_chart(fig, use_container_width=True)

# --- ACTIONABLE DIAGNOSTICS ---
st.subheader("Operational Diagnostics")
if current_lpcd > 120:
    st.warning("⚠️ High Consumption: Current per-capita usage significantly exceeds WHO boarding school baseline (100L). Initiate water-saving protocols.")
elif current_lpcd < 80:
    st.success("✅ Water conservation measures active.")
else:
    st.info("ℹ️ Consumption within standard operating parameters.")
