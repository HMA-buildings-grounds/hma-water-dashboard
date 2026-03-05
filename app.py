import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & CSS ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] * { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 38px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=60)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        return requests.get(api_url).json()
    except:
        return {}

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    st.markdown("<h2 style='text-align:center; color:#1ABB9C;'>HMA WATER</h2>", unsafe_allow_html=True)
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    selected_op_date = st.date_input("Operational Date", value=datetime(2026, 3, 5))
    
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
        
        # Cleanup
        df.columns = [str(c).strip() for c in df.columns]
        df.iloc[:, 0] = df.iloc[:, 0].ffill() # Fixes missing date cells
        
        try:
            d_col = next((c for c in df.columns if "Date" in c), df.columns[0])
            t_col = next((c for c in df.columns if "Time" in c), df.columns[1])
            m_col = next((c for c in df.columns if "Meter Reading" in c), df.columns[2])
            
            for _, row in df.iterrows():
                d_val = str(row[d_col]).strip()
                t_val = str(row[t_col]).strip()
                m_val = str(row[m_col]).strip()
                
                if not d_val or d_val.lower() in ['nan', 'date', '']: continue
                if not m_val or not any(c.isdigit() for c in m_val): continue
                
                m_num = float(re.search(r"[-+]?\d*\.\d+|\d+", m_val).group())
                
                # Create timestamp
                ts = pd.to_datetime(f"{d_val} 2026 {t_val}", errors='coerce')
                if pd.notnull(ts):
                    readings.append({'TS': ts, 'DateOnly': ts.date(), 'IsMorning': '8:00' in t_val, 'Reading': m_num})
        except: continue

    if readings:
        df_readings = pd.DataFrame(readings).sort_values('TS').drop_duplicates('TS').reset_index(drop=True)
        df_readings['Usage'] = df_readings['Reading'].diff().fillna(0)
        df_readings.loc[df_readings['Usage'] < 0, 'Usage'] = 0 
        
        daily_data = []
        for d, g in df_readings.groupby('DateOnly'):
            dt_usage = g[~g['IsMorning']]['Usage'].sum()
            ov_usage = g[g['IsMorning']]['Usage'].sum()
            daily_data.append({'Date': pd.to_datetime(d), 'Daytime': dt_usage, 'Overnight': ov_usage, 'Total': dt_usage + ov_usage})
        master = pd.DataFrame(daily_data)

# --- 4. MATCHING THE CALENDAR ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master.empty:
    match = master[master['Date'].dt.date == selected_op_date]
    if not match.empty:
        ov_v, dt_v, tot_v = match.iloc[0]['Overnight'], match.iloc[0]['Daytime'], match.iloc[0]['Total']
        lpcd = (tot_v * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# --- 5. DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target_lpcd:.1f} vs Target")

st.divider()
v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    view = st.selectbox("Select Trend View", ["Usage Analysis (Day vs Night)", "Total LPCD Index", "Efficiency Trend"])
    if not master.empty:
        fig = go.Figure()
        if "Usage" in view:
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], mode='lines', name='Daytime', fill='tozeroy'))
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], mode='lines', name='Overnight', fill='tozeroy'))
        elif "LPCD" in view:
            master['lpcd_p'] = (master['Total'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], name='24h LPCD'))
            fig.add_trace(go.Scatter(x=master['Date'], y=[target_lpcd]*len(master), name="Target", line=dict(dash='dash')))
        else:
            master['eff_p'] = (target_lpcd / ((master['Total'] * 1000) / campus_pop) * 100).clip(upper=100)
            fig.add_trace(go.Scatter(x=master['Date'], y=master['eff_p'], name='Efficiency %'))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    st.markdown("### Efficiency Status")
    st.plotly_chart(go.Figure(go.Indicator(mode="gauge+number", value=eff, gauge={'axis':{'range':[0,100]}, 'steps':[{'range':[0,50], 'color':"#FFEBEE"}, {'range':[50,85], 'color':"#FFF9C4"}, {'range':[85,100], 'color':"#E8F5E9"}]})), use_container_width=True)

with st.expander("🛠️ View Calculated Background Math"):
    st.dataframe(master, use_container_width=True)
