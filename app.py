import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import re
from datetime import datetime

# --- 1. SETTINGS & BRANDING ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 32px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATA ENGINE ---
@st.cache_data(ttl=600)
def fetch_and_wrangle_data():
    # REPLACE with your actual API endpoint to fetch Google Sheets data
    # Assuming the API returns a dict: {"Sheet Name": [{Date:..., Time:..., Meter Reading (m³):...}, ...]}
    api_url = st.secrets["google_sheets"]["api_url"]
    raw_data = requests.get(api_url).json()
    
    combined_logs = []
    
    for sheet_name, rows in raw_data.items():
        df = pd.DataFrame(rows)
        # Clean column names
        df.columns = [str(c).strip() for c in df.columns]
        
        # Identify columns using regex to be robust against minor naming changes
        d_col = next((c for c in df.columns if re.search(r'date', c, re.I)), None)
        t_col = next((c for c in df.columns if re.search(r'time', c, re.I)), None)
        r_col = next((c for c in df.columns if re.search(r'meter reading', c, re.I)), None)
        
        if d_col and t_col and r_col:
            temp_df = df[[d_col, t_col, r_col]].copy()
            temp_df.columns = ['Date', 'Time', 'Reading']
            
            # Extract Year from sheet name for proper datetime
            year_match = re.search(r'20\d{2}', sheet_name)
            year = year_match.group(0) if year_match else "2026"
            
            # Create timestamp
            temp_df['Timestamp'] = pd.to_datetime(temp_df['Date'].astype(str) + " " + year + " " + temp_df['Time'].astype(str), errors='coerce')
            temp_df['Reading'] = pd.to_numeric(temp_df['Reading'], errors='coerce')
            combined_logs.append(temp_df.dropna(subset=['Timestamp', 'Reading']))

    # Combine all sheets into one Master Timeline
    master_df = pd.concat(combined_logs).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
    
    # CALCULATE DELTA (Usage Since Last Reading)
    master_df['Usage_m3'] = master_df['Reading'].diff()
    
    # GROUP INTO 24H DAILY BUCKETS
    daily_data = []
    master_df['DateOnly'] = master_df['Timestamp'].dt.date
    
    for date, group in master_df.groupby('DateOnly'):
        # Daytime = 4PM reading - 8AM reading
        day = group[group['Timestamp'].dt.hour == 16]['Usage_m3'].sum()
        # Overnight = 8AM reading - Previous 4PM reading
        night = group[group['Timestamp'].dt.hour == 8]['Usage_m3'].sum()
        
        daily_data.append({
            'Date': date,
            'Daytime_Usage': day,
            'Overnight_Usage': night,
            'Total_24h_Usage': day + night
        })
        
    return pd.DataFrame(daily_data)

master_df = fetch_and_wrangle_data()

# --- 3. DASHBOARD UI ---
with st.sidebar:
    st.title("HMA WATER INTEL")
    campus_pop = st.number_input("Campus Population", value=250)
    target_lpcd = st.number_input("Target LPCD", value=50)
    selected_date = st.date_input("Operational Date", value=master_df['Date'].max())

# --- 4. CALCULATION ---
row = master_df[master_df['Date'] == selected_date]
if not row.empty:
    ov, dt, tot = row['Overnight_Usage'].iloc[0], row['Daytime_Usage'].iloc[0], row['Total_24h_Usage'].iloc[0]
    lpcd = (tot * 1000) / campus_pop
    eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0
else:
    ov, dt, tot, lpcd, eff = 0, 0, 0, 0, 0

# Metrics Display
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight", f"{ov:.1f} m³")
c2.metric("Daytime", f"{dt:.1f} m³")
c3.metric("Total 24h", f"{tot:.1f} m³")
c4.metric("LPCD", f"{lpcd:.1f}")

# Charting
fig = go.Figure()
fig.add_trace(go.Bar(x=master_df['Date'], y=master_df['Daytime_Usage'], name="Daytime"))
fig.add_trace(go.Bar(x=master_df['Date'], y=master_df['Overnight_Usage'], name="Overnight"))
fig.update_layout(barmode='stack', template="plotly_white")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Data Log")
st.dataframe(master_df, use_container_width=True)
