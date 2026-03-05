import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io
from datetime import datetime

# --- 1. THEME & FORCE VISIBILITY ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] * { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 32px; font-weight: 800; }
    .stMetric { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=2)
def get_data():
    try:
        res = requests.get(st.secrets["google_sheets"]["api_url"])
        return res.json()
    except: return {}

# --- 2. SIDEBAR ---
with st.sidebar:
    st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    st.markdown("### Operational Controls")
    pop = st.number_input("Campus Population", value=250)
    target = st.number_input("Baseline Target (LPCD)", value=50)
    sel_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    if st.button("🔄 FORCE REFRESH DATA"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE "RAW MATH" ENGINE ---
raw_json = get_data()
readings_list = []

for sheet_name, rows in raw_json.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    # Identify Year from Sheet Name
    year = "2026" if "2026" in sheet_name else "2025"
    
    # We look at the FIRST 3 COLUMNS ONLY (Date, Time, Reading)
    for _, row in df.iterrows():
        try:
            d_raw = str(row.iloc[0]).strip() # Date
            t_raw = str(row.iloc[1]).strip() # Time
            r_raw = str(row.iloc[2]).strip() # Reading
            
            # Clean the reading (remove any text like "m3")
            r_val = "".join(c for c in r_raw if c.isdigit() or c == '.')
            
            if d_raw and t_raw and r_val:
                ts = pd.to_datetime(f"{d_raw} {year} {t_raw}", errors='coerce')
                if pd.notnull(ts):
                    readings_list.append({'TS': ts, 'Time': t_raw, 'Reading': float(r_val)})
        except: continue

if readings_list:
    # A. Sort all readings by time globally
    full = pd.DataFrame(readings_list).sort_values('TS').drop_duplicates('TS').reset_index(drop=True)
    
    # B. The Math: Current Reading minus Previous Reading
    full['Delta'] = full['Reading'].diff()
    
    # C. Group by Date
    daily_stats = []
    for d, group in full.groupby(full['TS'].dt.date):
        # Overnight: Usually captured at 8:00 AM
        ov = group[group['Time'].str.contains('8', na=False)]['Delta'].sum()
        # Daytime: Usually captured at 4:00 PM
        dt = group[group['Time'].str.contains('4', na=False)]['Delta'].sum()
        daily_stats.append({'Date': d, 'Overnight': ov, 'Daytime': dt, 'Total': ov + dt})
    
    master = pd.DataFrame(daily_stats)
else:
    master = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

# --- 4. CALCULATION MATCHING ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master.empty:
    row = master[master['Date'] == sel_date]
    if not row.empty:
        ov_v, dt_v, tot_v = row.iloc[0]['Overnight'], row.iloc[0]['Daytime'], row.iloc[0]['Total']
        lpcd = (tot_v * 1000) / pop
        eff = (target / lpcd * 100) if lpcd > 0 else 0

# Tooltips
lpcd_h = f"Calculation: ({tot_v} m³ total × 1000) ÷ {pop} people = {lpcd:.1f} LPCD"
eff_h = f"Calculation: ({target} Target LPCD ÷ {lpcd:.1f} Actual LPCD) × 100 = {eff:.1f}%"

# --- 5. DASHBOARD LAYOUT ---
st.title("Operational Diagnostics & Performance")

if tot_v == 0:
    st.warning(f"No meter data found for {sel_date}. Please check the log below.")

# KPI Row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³", "8:00 AM Reading")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³", "4:00 PM Reading")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³", help="Aggregated well production for the day.")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target:.1f} vs Target", delta_color="inverse", help=lpcd_h)

st.divider()

# --- 6. VISUALIZATIONS ---
l_col, r_col = st.columns([2.2, 0.8])

with l_col:
    # THE DROPDOWN IS BACK
    view = st.selectbox("Select Trend View", ["Usage Analysis (Day vs Night)", "Total LPCD Index", "Efficiency Trend"])
    
    if not master.empty:
        fig = go.Figure()
        if "Usage" in view:
            # SaaS Overlapping Style
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        elif "LPCD" in view:
            master['lpcd_p'] = (master['Total'] * 1000) / pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=[target]*len(master), name="Baseline", line=dict(color="red", dash='dash')))
        
        # Highlight Selected Date in BOLD
        if tot_v > 0:
            y_val = dt_v if "Usage" in view else (tot_v*1000/pop)
            fig.add_trace(go.Scatter(x=[sel_date], y=[y_val], mode='markers', name="Selected", marker=dict(color='orange', size=15, line=dict(width=2, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# THE DEBUG LOG (Verification)
st.divider()
st.subheader("📋 Engineering Data Log")
st.write("If this table is empty, the app cannot find your Meter Reading column.")
st.dataframe(master, use_container_width=True)
