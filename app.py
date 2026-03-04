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
