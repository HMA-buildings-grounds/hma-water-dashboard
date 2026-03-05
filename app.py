import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.graph_objects as go
import requests
import io
from datetime import datetime

# --- 1. CONFIGURATION & UI ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 32px; font-weight: 800; }
    .stMetric { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=2)
def get_live_data():
    try:
        url = st.secrets["google_sheets"]["api_url"]
        return requests.get(url).json()
    except: return {}

# --- 2. SIDEBAR ---
with st.sidebar:
    st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    st.markdown("### Operational Controls")
    pop = st.number_input("Campus Population", value=250)
    target = st.number_input("Baseline Target (LPCD)", value=50)
    sel_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE "NO-FAIL" CALCULATION ENGINE ---
raw_json = get_live_data()
all_readings = []

for sheet_name, rows in raw_json.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    # We ignore column names and use POSITION
    # Column 0 = Date | Column 1 = Time | Column 2 = Meter Reading
    try:
        # Extract the year from the sheet name (e.g., "Mar 2026")
        year = "".join(filter(str.isdigit, sheet_name))
        if not year: year = "2026"
        
        for _, row in df.iterrows():
            d_val = str(row.iloc[0]).strip()
            t_val = str(row.iloc[1]).strip()
            r_val = str(row.iloc[2]).strip()
            
            # Only process if we have a reading
            if r_val and r_val.replace('.','',1).isdigit():
                # Combine Date + Year + Time
                ts_str = f"{d_val} {year} {t_val}"
                ts = pd.to_datetime(ts_str, errors='coerce')
                if pd.notnull(ts):
                    all_readings.append({'TS': ts, 'Time': t_val, 'Reading': float(r_val)})
    except: continue

if all_readings:
    full = pd.DataFrame(all_readings).sort_values('TS').drop_duplicates('TS').reset_index(drop=True)
    # Perform the subtraction between rows
    full['Delta'] = full['Reading'].diff()
    
    daily_results = []
    for d, g in full.groupby(full['TS'].dt.date):
        # 8:00 AM reading records the OVERNIGHT use
        ov = g[g['Time'].str.contains('8:00', na=False)]['Delta'].sum()
        # 4:00 PM reading records the DAYTIME use
        dt = g[g['Time'].str.contains('4:00', na=False)]['Delta'].sum()
        daily_results.append({'Date': d, 'Overnight': ov, 'Daytime': dt, 'Total': ov+dt})
    
    master = pd.DataFrame(daily_results)
else:
    master = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

# --- 4. KPI MATCHING ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master.empty:
    match = master[master['Date'] == sel_date]
    if not match.empty:
        res = match.iloc[0]
        ov_v, dt_v, tot_v = res['Overnight'], res['Daytime'], res['Total']
        lpcd = (tot_v * 1000) / pop
        eff = (target / lpcd * 100) if lpcd > 0 else 0

# --- 5. MAIN UI ---
st.title("Operational Diagnostics & Performance")

if tot_v == 0:
    st.warning(f"No data for {sel_date}. Please select a date from the logs.")

# Metric Division
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³", help="Calculated from 8:00 AM Reading")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³", help="Calculated from 4:00 PM Reading")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³", help="Sum of Day + Night")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target:.1f} vs Target", delta_color="inverse", help=f"({tot_v}m³ * 1000) / {pop} pop")

st.divider()

l_col, r_col = st.columns([2.2, 0.8])

with l_col:
    # THE DROPDOWN IS BACK
    view = st.selectbox("Select Trend View", ["Usage Analysis (Day vs Night)", "Total LPCD Index", "Efficiency Trend"])
    fig = go.Figure()
    
    if not master.empty:
        if "Usage" in view:
            # Overlapping Green/Blue Area Chart
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        elif "LPCD" in view:
            master['lpcd_p'] = (master['Total'] * 1000) / pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=[target]*len(master), name="Baseline", line=dict(color="red", dash='dash')))
        
        # Highlight selected date
        if tot_v > 0:
            y_val = dt_v if "Usage" in view else (tot_v*1000/pop)
            fig.add_trace(go.Scatter(x=[sel_date], y=[y_val], mode='markers', name="Focus", marker=dict(color='orange', size=15, line=dict(width=2, color='white'))))

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

st.divider()
st.subheader("📋 Calculated Engineering Log")
st.dataframe(master, use_container_width=True)
