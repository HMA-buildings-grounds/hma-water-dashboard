import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & THEME ---
# This adds the 💧 icon back to the browser tab
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

# NO CACHING - FORCE DATA TO UPDATE
def get_data_from_bridge():
    try:
        url = st.secrets["google_sheets"]["api_url"]
        return requests.get(url).json()
    except:
        return {}

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("💧 HMA WATER")
    
    st.markdown("### Operational Controls")
    pop = st.number_input("Campus Population", value=250, min_value=1)
    target = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    # Default to Mar 1 for testing
    sel_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    if st.button("🔄 FORCE RE-SYNC DATA"):
        st.rerun()

# --- 3. THE "BRUTE FORCE" DATA ENGINE ---
raw_json = get_data_from_bridge()
all_readings = []

for sheet_name, rows in raw_json.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    # Try to find the year in the sheet name
    yr = "2026" if "2026" in sheet_name else "2025"
    
    for _, row in df.iterrows():
        try:
            # Look for numbers in the row
            # We assume: Col 0 = Date, Col 1 = Time, Col 2 = Reading
            d_raw = str(row.iloc[0]).strip()
            t_raw = str(row.iloc[1]).strip()
            r_raw = str(row.iloc[2]).strip()
            
            # Extract just the numbers from the reading (ignore "44 (13259-13215)")
            r_clean = re.findall(r"[-+]?\d*\.\d+|\d+", r_raw)
            
            if d_raw and t_raw and r_clean:
                # Merge into a proper timestamp
                ts_str = f"{d_raw} {yr} {t_raw}"
                ts = pd.to_datetime(ts_str, errors='coerce')
                if pd.notnull(ts):
                    all_readings.append({
                        'Timestamp': ts,
                        'TimeLabel': t_raw,
                        'Reading': float(r_clean[0])
                    })
        except:
            continue

# --- 4. THE WRANGLING (Subtraction Logic) ---
if all_readings:
    # Sort everything by time
    master_log = pd.DataFrame(all_readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
    
    # CALCULATE DELTA (Reading minus Previous Reading)
    master_log['Delta'] = master_log['Reading'].diff()
    
    # Group into 24-hour Daily View
    daily_results = []
    for d, group in master_log.groupby(master_log['Timestamp'].dt.date):
        # Overnight = Delta at 8:00 AM | Daytime = Delta at 4:00 PM
        ov = group[group['TimeLabel'].str.contains('8:00', na=False)]['Delta'].sum()
        dt = group[group['TimeLabel'].str.contains('4:00', na=False)]['Delta'].sum()
        daily_results.append({
            'Date': d, 
            'Overnight': ov, 
            'Daytime': dt, 
            'Total': ov + dt
        })
    master_df = pd.DataFrame(daily_results)
else:
    master_df = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

# --- 5. MATCH SELECTED DATE ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master_df.empty:
    match = master_df[master_df['Date'] == sel_date]
    if not match.empty:
        r = match.iloc[0]
        ov_v, dt_v, tot_v = r['Overnight'], r['Daytime'], r['Total']
        lpcd = (tot_v * 1000) / pop
        eff = (target / lpcd * 100) if lpcd > 0 else 0

# Calculations for tooltips
lpcd_h = f"Calculation: ({tot_v} m³ total × 1000) ÷ {pop} people = {lpcd:.1f} LPCD"
eff_h = f"Calculation: ({target} Baseline ÷ {lpcd:.1f} Actual) × 100 = {eff:.1f}%"

# --- 6. DASHBOARD UI ---
st.title("💧 Operational Diagnostics & Performance")

if tot_v == 0 and not master_df.empty:
    st.warning(f"No valid data found for {sel_date}. Please select a date with recorded meter readings.")

# KPI Row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Use", f"{ov_v:.1f} m³", "8:00 AM Delta")
c2.metric("Daytime Use", f"{dt_v:.1f} m³", "4:00 PM Delta")
c3.metric("Total 24h Production", f"{tot_v:.1f} m³", help="Aggregate of Day + Night readings")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target:.1f} vs Target", delta_color="inverse", help=lpcd_h)

st.divider()

# --- 7. VISUALIZATIONS ---
l_col, r_col = st.columns([2.2, 0.8])

with l_col:
    # THE DROPDOWN IS BACK
    chart_view = st.selectbox("Select View", ["Usage Analysis (Day vs Night)", "Total LPCD Index", "Efficiency Trend"])
    
    if not master_df.empty:
        fig = go.Figure()
        
        if "Usage" in chart_view:
            # Overlapping Curved Area Style (GREEN REFERENCE STYLE)
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        
        elif "LPCD" in chart_view:
            master_df['lpcd_p'] = (master_df['Total'] * 1000) / pop
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=[target]*len(master_df), name="WHO Baseline", line=dict(color="red", dash='dash')))

        # Highlight selected date
        if tot_v > 0:
            y_focus = dt_v if "Usage" in chart_view else (tot_v*1000/pop)
            fig.add_trace(go.Scatter(x=[sel_date], y=[y_focus], mode='markers', name="Selected", marker=dict(color='orange', size=15, line=dict(width=2, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# THE CALCULATED DATA LOG (Engineering Verification)
st.divider()
st.subheader("📋 Calculated Engineering Log")
st.write("This table shows the raw math performed by the dashboard engine:")
st.dataframe(master_df, use_container_width=True)
