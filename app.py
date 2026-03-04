import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="HMA Infrastructure Command Center", layout="wide")

# --- GLOBAL VARIABLES & WHO TARGETS ---
WHO_TARGET_LPCD = 100 # WHO standard for Boarding Schools (L/c/d)

# --- DATA ENGINE (Polished) ---
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

# --- HEADER & EXPORT ACTIONS ---
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.title("💧 HMA Water Infrastructure Command Center")
with col_head2:
    # Export Module
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export Dataset (CSV)", csv, "hma_water_data.csv", "text/csv")

# --- SIDEBAR: DYNAMIC CONTROLS ---
with st.sidebar:
    st.markdown("### Executive Parameters")
    pop = st.number_input("Campus Population", min_value=1, value=370, step=1)
    # The slider now ranges to 75% as requested
    target = st.slider("Conservation Goal (%)", 0, 75, 10)
    
    st.divider()
    st.markdown("### WHO Standards Baseline")
    st.info(f"Target: {WHO_TARGET_LPCD} L/c/d")
    st.markdown("[WHO Guidelines (Table 5.1)](https://www.who.int/publications/i/item/9789241549950)")

# --- KPI CALCULATION ---
curr = df.iloc[-1]
prod = curr['well_usage_m3']
dist = curr['Distribution']
lpcd = (dist * 1000) / pop
variance = lpcd - WHO_TARGET_LPCD

# --- GRID DASHBOARD ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Well Output", f"{prod:.1f} m³")
k2.metric("Efficiency", f"{curr['Efficiency']:.1f}%")
k3.metric("LPCD (Per Capita)", f"{lpcd:.0f} L", delta=f"{variance:.0f} vs WHO", delta_color="inverse")
k4.metric("Leakage Gap", f"{prod - dist:.1f} m³", delta="High Loss" if (prod-dist) > 20 else None, delta_color="inverse")

# --- INTERACTIVE VISUALIZATION ---
st.subheader("Time-Series Performance Diagnostics")
fig = go.Figure()
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color="#A68A64", width=3)))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['well_usage_m3'], name="Potential Loss", fill='tonexty', fillcolor='rgba(148, 27, 12, 0.2)', line=dict(width=0)))
fig.update_layout(template="plotly_white", height=400, hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
