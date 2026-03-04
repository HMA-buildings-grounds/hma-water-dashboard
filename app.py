import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine
from io import BytesIO

# --- PAGE CONFIG ---
st.set_page_config(page_title="HMA Command Center", layout="wide")

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
    df['LPCD'] = (df['Distribution'] * 1000) / 370 # Base calc
    return df

df = load_data()

# --- HEADER & EXPORT ACTIONS ---
col1, col2 = st.columns([3, 1])
col1.title("💧 HMA Water Infrastructure Command Center")
with col2:
    # Logic for Excel/CSV Export
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export Report Data", data=csv, file_name="HMA_Water_Report.csv", mime="text/csv")

# --- GLOBAL FILTERS ---
with st.expander("⚙️ System Filters & Population Calibration", expanded=True):
    c1, c2, c3 = st.columns(3)
    pop = c1.number_input("Actual Daily Campus Population", value=370, min_value=1)
    date_range = c2.date_input("Analysis Window", [df['log_date'].min(), df['log_date'].max()])
    target_lpcd = c3.select_slider("WHO Target LPCD (Modern Boarding)", options=[50, 75, 100, 150], value=100)

# --- KPI RIBBON ---
filtered = df[(df['log_date'].dt.date >= date_range[0]) & (df['log_date'].dt.date <= date_range[1])]
latest = filtered.iloc[-1]
actual_lpcd = (latest['Distribution'] * 1000) / pop

c1, c2, c3, c4 = st.columns(4)
c1.metric("Production", f"{latest['well_usage_m3']:.1f} m³")
c2.metric("Efficiency", f"{(latest['Distribution']/latest['well_usage_m3'])*100:.1f}%")
c3.metric("Actual LPCD", f"{actual_lpcd:.0f} L", delta=f"{actual_lpcd - target_lpcd:.0f} vs Target", delta_color="inverse")
c4.metric("Status", "OPTIMAL" if actual_lpcd <= target_lpcd else "CRITICAL")

# --- CHARTS ---
fig = go.Figure()
fig.add_trace(go.Bar(x=filtered['log_date'], y=filtered['well_usage_m3'], name="Well Source", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=filtered['log_date'], y=filtered['Distribution'], name="Distribution", line=dict(color="#A68A64", width=3)))
fig.add_hline(y=(target_lpcd * pop) / 1000, line_dash="dash", line_color="#941B0C", annotation_text="WHO Target Threshold")
fig.update_layout(template="plotly_white", hovermode="x unified", height=400)
st.plotly_chart(fig, use_container_width=True)
