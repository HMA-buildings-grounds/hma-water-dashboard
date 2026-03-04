import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine
import io

# --- CONFIG ---
st.set_page_config(page_title="HMA Command Center", layout="wide")

# --- UI ARCHITECTURE (CSS) ---
st.markdown("""
    <style>
    .card { background: #FFFFFF; padding: 1.5rem; border-radius: 10px; border-top: 4px solid #1B263B; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .stMetric { background: #F8F9FA; padding: 10px; border-radius: 8px; }
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

# --- SIDEBAR: OPERATIONAL FILTERS ---
with st.sidebar:
    st.image("assets/HMA_logo_color.jpg", width=150)
    st.markdown("### Infrastructure Parameters")
    pop = st.number_input("Daily Campus Occupancy", 100, 2000, 370)
    
    # WHO Standard: 100 L/c/d is the modern "safe/comfortable" standard for boarding schools
    who_target = st.slider("WHO Standard Baseline (L/c/d)", 50, 150, 100)
    
    st.divider()
    st.markdown("### Data Export")
    # CSV/Excel Logic
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download CSV Dataset", csv, "hma_water_data.csv", "text/csv")

# --- DASHBOARD LAYOUT ---
st.title("💧 Water Infrastructure Command Center")

# Row 1: Global Health
curr = df.iloc[-1]
prod = curr['well_usage_m3']
lpcd = (curr['Distribution'] * 1000) / pop

c1, c2, c3 = st.columns(3)
c1.metric("Production (m³)", f"{prod:.1f}")
c2.metric("Efficiency", f"{(curr['Distribution']/prod)*100:.1f}%")
c3.metric("Per Capita Usage", f"{lpcd:.0f} L/c/d", delta=f"{lpcd-who_target:.0f} vs WHO Target", delta_color="inverse")

# Row 2: Analytics Grid
st.subheader("Performance vs. WHO Benchmarks")
fig = go.Figure()
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Well Source", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Verified Distribution", line=dict(color="#A68A64", width=3)))
fig.add_hline(y=(who_target * pop) / 1000, line_dash="dash", line_color="#941B0C", annotation_text="WHO Standard Limit")

fig.update_layout(template="plotly_white", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# Row 3: Drill-down
with st.expander("Detailed Operational Logs"):
    st.dataframe(df.sort_values('log_date', ascending=False), use_container_width=True)
