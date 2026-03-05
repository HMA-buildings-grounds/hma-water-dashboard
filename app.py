import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & BRANDING ---
st.set_page_config(page_title="HMA Water Performance", page_icon="💧", layout="wide")

# Navy Sidebar / White Metric Styling
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 36px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=2)
def fetch_raw_data():
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
    pop = st.number_input("Campus Population", value=250, min_value=1)
    base = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    # The Date you want to see details for
    selected_dt = st.date_input("Operational Date", value=datetime(2025, 12, 12))
    
    st.divider()
    st.markdown("### 📖 Standards\n• [WHO Standards](https://www.who.int)\n• [Sphere Handbook](https://spherestandards.org)")
    
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. DATA CALCULATION ENGINE (Dashboard Cooks the Data) ---
raw_json = fetch_raw_data()

def process_raw_readings(data):
    all_readings = []
    for sheet_name, rows in data.items():
        df = pd.DataFrame(rows)
        if df.empty: continue
        
        # 1. Standardize columns
        df.columns = [str(c).strip() for c in df.columns]
        d_col = next((c for c in df.columns if "Date" in c), None)
        t_col = next((c for c in df.columns if "Time" in c), None)
        r_col = next((c for c in df.columns if "Meter Reading" in c), None)
        
        if all([d_col, t_col, r_col]):
            # Use sheet name to get the year (e.g., "Jan 2026")
            yr_match = re.search(r'20\d{2}', sheet_name)
            yr = yr_match.group(0) if yr_match else "2026"
            
            temp = df[[d_col, t_col, r_col]].copy()
            temp.columns = ['Date', 'Time', 'Reading']
            # Create a full timestamp for chronological subtraction
            temp['Timestamp'] = pd.to_datetime(temp['Date'].astype(str) + " " + yr + " " + temp['Time'].astype(str), errors='coerce')
            temp['Reading'] = pd.to_numeric(temp['Reading'], errors='coerce')
            all_readings.append(temp.dropna())

    if not all_readings: return pd.DataFrame()

    # 2. Sort all readings across all months (Chronological)
    full_timeline = pd.concat(all_readings).sort_values('Timestamp').reset_index(drop=True)
    
    # 3. DO THE MATH: Today - Previous Row
    full_timeline['Delta'] = full_timeline['Reading'].diff()
    full_timeline['DateOnly'] = full_timeline['Timestamp'].dt.date
    
    # 4. CATEGORIZE: 8 AM is Overnight (subtraction from yesterday 4PM)
    #               4 PM is Daytime (subtraction from today 8AM)
    daily_summary = []
    for date, group in full_timeline.groupby('DateOnly'):
        night = group[group['Time'].astype(str).str.contains('8:00', na=False)]['Delta'].sum()
        day = group[group['Time'].astype(str).str.contains('4:00', na=False)]['Delta'].sum()
        daily_summary.append({
            'Date': date,
            'Overnight_m3': night,
            'Daytime_m3': day,
            'Total_24h_m3': night + day
        })
        
    return pd.DataFrame(daily_summary)

master_data = process_raw_readings(raw_json)

# --- 4. MATCH SELECTED DATE TO RESULTS ---
ov, dt, tot, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master_data.empty:
    match = master_data[master_data['Date'] == selected_dt]
    if not match.empty:
        row = match.iloc[0]
        ov, dt, tot = row['Overnight_m3'], row['Daytime_m3'], row['Total_24h_m3']
        lpcd = (tot * 1000) / pop
        eff = (base / lpcd * 100) if lpcd > 0 else 0

# Calculations for ? help icons
lpcd_calc = f"Calculation: (Total 24h [{tot} m³] × 1000) ÷ Population [{pop}] = {lpcd:.1f} LPCD."
eff_calc = f"Calculation: (Baseline Target [{base} LPCD] ÷ Actual LPCD [{lpcd:.1f}]) × 100 = {eff:.1f}% Efficiency."
ov_calc = "The difference between today's 8:00 AM reading and yesterday's 4:00 PM reading."
dt_calc = "The difference between today's 4:00 PM reading and today's 8:00 AM reading."

# --- 5. DASHBOARD VIEW ---
st.title("Operational Diagnostics & Performance")

if tot == 0:
    st.warning(f"No meter readings found for {selected_dt}. Check the table below for available dates.")

# Top Row: The Four Divisions
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov:.1f} m³", help=ov_calc)
c2.metric("Daytime Usage", f"{dt:.1f} m³", help=dt_calc)
c3.metric("Total 24h Usage", f"{tot:.1f} m³", help="Aggregated well production for the day.")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-base:.1f} vs Target", delta_color="inverse", help=lpcd_calc)

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    # THE DROPDOWN VIEW YOU REQUESTED
    view = st.selectbox("Select Performance Trend", 
                        ["Overlapping Usage (Day vs Night)", "Total LPCD Index (24h Basis)", "Efficiency Trend (%)"])
    
    if not master_data.empty:
        fig = go.Figure()
        
        # GREEN/BLUE SAAS STYLE OVERLAPPING CHART
        if "Overlapping" in view:
            fig.add_trace(go.Scatter(x=master_data['Date'], y=master_data['Daytime_m3'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_data['Date'], y=master_data['Overnight_m3'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        
        elif "LPCD" in view:
            master_data['lpcd_p'] = (master_data['Total_24h_m3'] * 1000) / pop
            fig.add_trace(go.Scatter(x=master_data['Date'], y=master_data['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master_data['Date'], y=[base]*len(master_data), name="Target", line=dict(color="red", dash='dash')))
        
        else: # Efficiency
            master_data['eff_p'] = (base / ((master_data['Total_24h_m3'] * 1000) / pop) * 100).fillna(0)
            fig.add_trace(go.Scatter(x=master_data['Date'], y=master_data['eff_p'], mode='lines', line_shape='spline', name='Efficiency %', line=dict(width=4, color='#F8C471'), fill='tozeroy', fillcolor='rgba(248, 196, 113, 0.2)'))

        # HIGHLIGHT SELECTED DATE
        if tot > 0:
            y_val = dt if "Overlapping" in view else (tot*1000/pop if "LPCD" in view else eff)
            fig.add_trace(go.Scatter(x=[selected_dt], y=[y_val], mode='markers', name="Selected Day", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    # NEEDLE GAUGE
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# THE DATA TABLE (Verification)
st.divider()
st.subheader("📋 Calculated Data Log (Direct from Meter Readings)")
st.dataframe(master_data, use_container_width=True)
