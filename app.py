import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine
import io

st.set_page_config(page_title="HMA Infrastructure Command Center", layout="wide")

# --- CSS: SCADA-Inspired Styling ---
st.markdown("""
    <style>
    .kpi-card {background: #FFFFFF; padding: 1.5rem; border-radius: 8px; border-left: 5px solid #1B263B; box-shadow: 0 2px 4px rgba(0,0,0,0.1);}
    .header-band {background: #1B263B; color: white; padding: 10px 20px; border-radius: 5px; margin-bottom: 20px;}
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

# --- HEADER & GLOBAL FILTERS ---
st.markdown('<div class="header-band"><h1>HMA INFRASTRUCTURE COMMAND CENTER</h1></div>', unsafe_allow_html=True)
col_a, col_b, col_c = st.columns([2, 2, 1])
pop = col_a.number_input("Campus Daily Population", value=370, min_value=1)
sel_date = col_b.selectbox("Operational Snapshot", df['log_date'].dt.date.unique()[::-1])

# --- DOWNLOAD LOGIC ---
csv = df.to_csv(index=False).encode('utf-8')
col_c.download_button("Export Data (CSV)", csv, "HMA_Water_Data.csv", "text/csv")

# --- KPIs ---
curr = df[df['log_date'].dt.date == sel_date].iloc[0]
lpcd = (curr['Distribution'] * 1000) / pop
who_target = 100 # WHO standard for boarding schools

cols = st.columns(4)
cols[0].metric("Production", f"{curr['well_usage_m3']:.1f} m³")
cols[1].metric("Efficiency", f"{(curr['Distribution']/curr['well_usage_m3'])*100:.1f}%")
cols[2].metric("Campus LPCD", f"{lpcd:.0f} L", delta=f"{lpcd - who_target:.0f} vs WHO Target", delta_color="inverse")
cols[3].metric("Loss Volume", f"{curr['well_usage_m3'] - curr['Distribution']:.1f} m³")

# --- ANALYTICAL ENGINE ---
st.subheader("Performance vs. WHO Standard")
fig = go.Figure()
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=df['log_date'], y=[who_target * pop / 1000] * len(df), name="WHO Standard Line", line=dict(color="#941B0C", dash='dash')))
fig.update_layout(template="plotly_white", height=400, hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# --- DIAGNOSTIC LOGS ---
with st.expander("System Integrity Diagnostics"):
    st.table(df.tail(7))
