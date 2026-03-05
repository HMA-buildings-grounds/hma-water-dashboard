import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & CSS FIXES ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    /* Sidebar Background & Text */
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown,[data-testid="stSidebar"] label, [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h3 { color: white !important; }
    /* Fix Input Boxes (Dark text on white background) */
    [data-testid="stSidebar"] input { color: #1B263B !important; background-color: white !important; border-radius: 5px; }
    /* KPI Metrics Styling */[data-testid="stMetricValue"] { color: #1B263B; font-size: 38px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=2)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        return requests.get(api_url).json()
    except:
        return {}

# --- 2. SIDEBAR: OPERATIONAL CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=35, min_value=35, max_value=100)
    selected_op_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("""
        <div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
            <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
            <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
        </div>
    """, unsafe_allow_html=True)

    st.divider()
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE "RAW READING" ENGINE ---
raw_data = fetch_live_data()
readings = []
master = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

if raw_data:
    for sheet_name, rows in raw_data.items():
        df = pd.DataFrame(rows)
        if df.empty: continue
        
        df.columns = [str(c).strip() for c in df.columns]
        df.iloc[:, 0] = df.iloc[:, 0].ffill() # Fix: Fills blank afternoon dates
        
        try:
            idx_date = df.columns.get_loc('Date')
            idx_time = df.columns.get_loc('Time')
            idx_meter = df.columns.get_loc('Water well Meter Reading (m³)')
            
            for _, row in df.iterrows():
                d_val = str(row.iloc[idx_date]).strip()
                t_val = str(row.iloc[idx_time]).strip()
                m_val = str(row.iloc[idx_meter]).strip()
                
                if not d_val or d_val.lower() in ['nan', 'date', '']: continue
                if not m_val or not any(c.isdigit() for c in m_val): continue
                
                m_num = float(re.search(r"[-+]?\d*\.\d+|\d+", m_val).group())
                
                year_match = re.search(r'20\d{2}', sheet_name)
                year = year_match.group(0) if year_match else "2026"
                
                d_str = f"{d_val} {year} {t_val}"
                ts = pd.to_datetime(d_str, errors='coerce')
                
                if pd.notnull(ts):
                    is_morning = '8:00' in t_val or 'AM' in t_val.upper()
                    readings.append({'Timestamp': ts, 'DateOnly': ts.date(), 'IsMorning': is_morning, 'Reading': m_num})
        except: continue

    if readings:
        df_readings = pd.DataFrame(readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
        df_readings['Usage'] = df_readings['Reading'].diff().fillna(0)
        df_readings.loc[df_readings['Usage'] < 0, 'Usage'] = 0 
        
        daily_data = []
        for d, g in df_readings.groupby('DateOnly'):
            dt_usage = g[~g['IsMorning']]['Usage'].sum()
            ov_usage = g[g['IsMorning']]['Usage'].sum()
            daily_data.append({
                'Date': pd.to_datetime(d), 
                'Overnight': ov_usage, 
                'Daytime': dt_usage, 
                'Total': dt_usage + ov_usage
            })
        master = pd.DataFrame(daily_data)

# --- 4. MATCHING THE CALENDAR ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master.empty:
    match = master[master['Date'].dt.date == selected_op_date]
    if not match.empty:
        ov_v = match.iloc[0]['Overnight']
        dt_v = match.iloc[0]['Daytime']
        tot_v = match.iloc[0]['Total']
        lpcd = (tot_v * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# --- 5. DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")
if tot_v == 0 and not master.empty:
    st.warning(f"⚠️ No meter reading data calculated for {selected_op_date.strftime('%B %d, %Y')}.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target_lpcd:.1f} vs Target")

st.divider()
l_col, r_col = st.columns([2.2, 0.8])

with l_col:
    view = st.selectbox("Select 24h Trend View", ["Usage Analysis (Day vs Night)", "Total LPCD Index", "Efficiency Trend"])
    if not master.empty:
        fig = go.Figure()
        if "Usage" in view:
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], name='Daytime Use', fill='tozeroy'))
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], name='Overnight Use', fill='tozeroy'))
        elif "LPCD" in view:
            master['lpcd_p'] = (master['Total'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], name='24h LPCD'))
        else:
            master['eff_p'] = (target_lpcd / ((master['Total'] * 1000) / campus_pop) * 100).clip(upper=100).fillna(0)
            fig.add_trace(go.Scatter(x=master['Date'], y=master['eff_p'], name='Efficiency %'))
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.markdown("### Efficiency Status")
    st.plotly_chart(go.Figure(go.Indicator(mode="gauge+number", value=eff)), use_container_width=True)

with st.expander("🛠️ View Calculated Background Math"):
    if not master.empty:
        st.dataframe(master, use_container_width=True)
