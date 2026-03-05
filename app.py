import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import re
from datetime import datetime

# --- 1. SETTINGS & THEME ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] * { color: white !important; }[data-testid="stMetricValue"] { color: #1B263B; font-size: 34px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# THE EXACT URL YOU PROVIDED
API_URL = "https://script.google.com/macros/s/AKfycbyq2flNL4R81o0FYcCY_8aOhmzeNrTTXWOoWVuMHim49PsiwfUF3-N7Cqla2_Ws3aM9bA/exec"

def fetch_data():
    try:
        return requests.get(API_URL).json()
    except:
        return None

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.markdown("<h2 style='text-align:center;'>💧 HMA WATER</h2>", unsafe_allow_html=True)
    
    st.markdown("### Operational Controls")
    pop = st.number_input("Campus Population", value=250, min_value=1)
    target = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    sel_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    if st.button("🔄 FORCE SYNC DATA"):
        st.rerun()

# --- 3. DATA EXTRACTION ENGINE ---
raw_json = fetch_data()
all_readings =[]

st.title("💧 Operational Diagnostics & Performance")

if raw_json is None:
    st.error("🚨 Connection Failed: Could not reach Google Sheets. Please check your internet or Apps Script URL.")
    st.stop()

# Loop through sheets to find data
for sheet_name, rows in raw_json.items():
    if not isinstance(rows, list): continue
    
    # Guess year from sheet name
    yr_match = re.search(r'20\d{2}', sheet_name)
    yr = yr_match.group(0) if yr_match else "2026"
    
    for row in rows:
        if not isinstance(row, dict): continue
        
        # Search for keys dynamically to prevent spelling errors
        d_key = next((k for k in row.keys() if 'date' in str(k).lower()), None)
        t_key = next((k for k in row.keys() if 'time' in str(k).lower() and 'period' not in str(k).lower()), None)
        r_key = next((k for k in row.keys() if 'meter reading' in str(k).lower()), None)
        
        if d_key and t_key and r_key:
            d_val = str(row[d_key]).strip()
            t_val = str(row[t_key]).strip()
            r_val = str(row[r_key]).strip()
            
            # Extract only the numbers from the reading
            match = re.search(r"[-+]?\d*\.\d+|\d+", r_val)
            if match and d_val and t_val:
                ts_str = f"{d_val} {yr} {t_val}"
                try:
                    ts = pd.to_datetime(ts_str)
                    all_readings.append({
                        'Timestamp': ts,
                        'TimeLabel': t_val,
                        'Reading': float(match.group())
                    })
                except: pass

# --- DIAGNOSTIC CHECK ---
if not all_readings:
    st.warning("⚠️ Connected to Google Sheets, but could not find the 'Date', 'Time', and 'Meter Reading' columns.")
    with st.expander("Click here to see what Google Sheets is sending to the app:"):
        st.write(raw_json)
    st.stop()

# --- 4. THE SUBTRACTION MATH ---
# Sort chronologically
master_log = pd.DataFrame(all_readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)

# Current Reading - Previous Reading
master_log['Delta'] = master_log['Reading'].diff()

# Group into 24-hour periods
daily_results = []
for d, group in master_log.groupby(master_log['Timestamp'].dt.date):
    # Overnight = Delta at 8 AM | Daytime = Delta at 4 PM
    ov = group[group['TimeLabel'].str.contains('8', na=False)]['Delta'].sum()
    dt = group[group['TimeLabel'].str.contains('4', na=False)]['Delta'].sum()
    daily_results.append({
        'Date': d,
        'Overnight': ov,
        'Daytime': dt,
        'Total': ov + dt
    })

master_df = pd.DataFrame(daily_results)

# --- 5. MATCHING THE CALENDAR ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master_df.empty:
    match = master_df[master_df['Date'] == sel_date]
    if not match.empty:
        r = match.iloc[0]
        ov_v, dt_v, tot_v = r['Overnight'], r['Daytime'], r['Total']
        lpcd = (tot_v * 1000) / pop
        eff = (target / lpcd * 100) if lpcd > 0 else 0

if tot_v == 0:
    st.info(f"📅 No water usage recorded for {sel_date}. Please select another date.")

# --- 6. KPI METRICS ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³", "8:00 AM Subtraction")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³", "4:00 PM Subtraction")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³", "Daytime + Overnight")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target:.1f} vs Target", delta_color="inverse")

st.divider()

# --- 7. CHARTS & GAUGE ---
l_col, r_col = st.columns([2.2, 0.8])

with l_col:
    view = st.selectbox("Select Trend View", ["Usage Analysis (Day vs Night)", "Total LPCD Index"])
    fig = go.Figure()
    
    if "Usage" in view:
        # Green/Blue SaaS Style
        fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime'], mode='lines', line_shape='spline', name='Daytime Usage', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
        fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight'], mode='lines', line_shape='spline', name='Overnight Usage', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
    else:
        master_df['lpcd_p'] = (master_df['Total'] * 1000) / pop
        fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
        fig.add_trace(go.Scatter(x=master_df['Date'], y=[target]*len(master_df), name="WHO Baseline", line=dict(color="red", dash='dash')))

    # Bold Selected Date
    if tot_v > 0:
        y_val = dt_v if "Usage" in view else (tot_v*1000/pop)
        fig.add_trace(go.Scatter(x=[sel_date], y=[y_val], mode='markers+text', name="Selected", text=["Selected Date"], textposition="top center", marker=dict(color='#1B263B', size=15, line=dict(width=3, color='white'))))

    fig.update_layout(template="plotly_white", height=450, margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B", 'thickness': 0.2},
                 'steps': [{'range':[0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

st.divider()
st.subheader("📋 Raw Data Calculation Log")
st.dataframe(master_df, use_container_width=True)
