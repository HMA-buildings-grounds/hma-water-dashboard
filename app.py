import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import datetime
from sqlalchemy import create_engine

# ==========================================
# 1. PAGE CONFIG & EXECUTIVE BRANDING
# ==========================================
st.set_page_config(page_title="HMA Water Dashboard", layout="wide")

# Theme Colors
NAVY_BLUE, HMA_GOLD = "#1B263B", "#A68A64"
SUCCESS_EMERALD, ALERT_CRIMSON = "#2D6A4F", "#941B0C"
OFF_WHITE, SLATE_GRAY = "#F8F9FA", "#4A5568"

st.markdown(f"""<style>.stApp {{background-color: {OFF_WHITE};}} h1, h2 {{color: {NAVY_BLUE};}}</style>""", unsafe_allow_html=True)

# ==========================================
# 2. BULLETPROOF MYSQL CONNECTION
# ==========================================
@st.cache_data(ttl=600)
def load_data():
    try:
        # Access secrets directly
        c = st.secrets["connections"]["mysql"]
        url = f"mysql+pymysql://{c['username']}:{c['password']}@{c['host']}:{c['port']}/{c['database']}"
        
        # TiDB REQUIRES SSL
        connect_args = {"ssl": {"ca": "/etc/ssl/certs/ca-certificates.crt"}}
        engine = create_engine(url, connect_args=connect_args)
        
        query = "SELECT log_date, well_usage_m3, booster_reading FROM water_logs ORDER BY log_date ASC"
        df = pd.read_sql(query, engine)
        
        # Clean Data
        df['log_date'] = pd.to_datetime(df['log_date'])
        daily = df.groupby('log_date').agg({'well_usage_m3':'sum', 'booster_reading':'max'}).reset_index()
        daily['Consumption_m3'] = daily['booster_reading'].diff()
        
        # Filter for post-installation data
        daily.loc[daily['log_date'] < pd.Timestamp("2026-02-05"), 'Consumption_m3'] = np.nan
        daily['Rolling_Avg_30d'] = daily['well_usage_m3'].rolling(window=30).mean()
        daily['Date_Str'] = daily['log_date'].dt.strftime('%Y-%m-%d')
        return daily
    except Exception as e:
        st.error(f"Critical Connection Error: {e}")
        st.stop()

df_master = load_data()

# ==========================================
# 3. DASHBOARD UI
# ==========================================
st.sidebar.title("HMA Water Controls")
pop = st.sidebar.number_input("Population", value=370)
target = st.sidebar.slider("Savings Goal (%)", 0, 30, 10)
selected_date = st.sidebar.selectbox("Date", sorted(df_master['Date_Str'].unique(), reverse=True))

st.title("WATER INFRASTRUCTURE DASHBOARD")
row = df_master[df_master['Date_Str'] == selected_date].iloc[0]

# KPIs
col1, col2, col3 = st.columns(3)
col1.metric("WHO Std (LPCD)", f"{(row['Consumption_m3']*1000)/pop:.0f} L")
col2.metric("Efficiency", f"{(row['Consumption_m3']/row['well_usage_m3'])*100:.1f}%")
col3.metric("Goal", f"{row['well_usage_m3']:.1f} m³")

# Charts
fig = go.Figure()
fig.add_trace(go.Scatter(x=df_master['log_date'], y=df_master['well_usage_m3'], name="Production", line=dict(color=NAVY_BLUE)))
fig.add_trace(go.Scatter(x=df_master['log_date'], y=df_master['Rolling_Avg_30d']*(1-target/100), name="Target", line=dict(color=HMA_GOLD, dash='dash')))
st.plotly_chart(fig, use_container_width=True)
