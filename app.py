import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & BRANDING ---
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
def get_raw_data():
    try:
        return requests.get(st.secrets["google_sheets"]["api_url"]).json()
    except: return {}

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("### Operational Controls")
    pop = st.number_input("Campus Population", value=250)
    target = st.number_input("Baseline Target (LPCD)", value=50)
    sel_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("📖 [WHO Standards](https://www.who.int) | [Sphere Handbook](https://spherestandards.org)")
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE ENGINEERING ENGINE ---
raw_json = get_raw_data()

def process_hma_data(json_input):
    all_readings = []
    
    for sheet_name, rows in json_input.items():
        df = pd.DataFrame(rows)
        if df.empty: continue
        
        # Determine Year from sheet name (e.g. "Mar 2026")
        year_match = re.search(r'20\d{2}', sheet_name)
        year = year_match.group(0) if year_match else "2026"
        
        # Standardize columns
        df.columns = [str(c).strip() for c in df.columns]
        d_col = next((c for c in df.columns if "Date" in c), None)
        t_col = next((c for c in df.columns if "Time" in c), None)
        r_col = next((c for c in df.columns if "well" in c.lower() and "meter" in c.lower()), None)
        
        if d_col and t_col and r_col:
            temp = df[[d_col, t_col, r_col]].copy()
            temp.columns = ['D', 'T', 'R']
            # Create a real timestamp for sorting
            temp['Timestamp'] = pd.to_datetime(temp['D'].astype(str) + " " + year + " " + temp['T'].astype(str), errors='coerce')
            temp['Reading'] = pd.to_numeric(temp['R'], errors='coerce')
            all_readings.append(temp.dropna(subset=['Timestamp', 'Reading']))

    if not all_readings:
        return pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

    # Combine everything and sort by time
    full_tape = pd.concat(all_readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
    
    # Calculate difference between this reading and the previous one
    full_tape['Usage'] = full_tape['Reading'].diff()
    
    # Split into Daily Buckets
    daily_stats = []
    full_tape['DateOnly'] = full_tape['Timestamp'].dt.date
    
    for d, g in full_tape.groupby('DateOnly'):
        # Overnight: Usually recorded at 8:00 AM (Reading 8AM - Reading Prev 4PM)
        ov = g[g['T'].astype(str).str.contains('8:00', na=False)]['Usage'].sum()
        # Daytime: Recorded at 4:00 PM (Reading 4PM - Reading 8AM)
        dt = g[g['T'].astype(str).str.contains('4:00', na=False)]['Usage'].sum()
        
        daily_stats.append({
            'Date': d, 
            'Overnight': ov if ov >= 0 else 0, 
            'Daytime': dt if dt >= 0 else 0, 
            'Total': (ov if ov >= 0 else 0) + (dt if dt >= 0 else 0)
        })
    
    return pd.DataFrame(daily_stats)

master = process_hma_data(raw_json)

# --- 4. CALCULATION & MATCHING ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master.empty:
    match = master[master['Date'] == sel_date]
    if not match.empty:
        row = match.iloc[0]
        ov_v, dt_v, tot_v = row['Overnight'], row['Daytime'], row['Total']
        lpcd = (tot_v * 1000) / pop
        eff = (target / lpcd * 100) if lpcd > 0 else 0

# --- 5. UI LAYOUT ---
st.title("Operational Diagnostics & Performance")

# Handle cases where no data exists for selected date
if tot_v == 0 and not master.empty:
    st.warning(f"No meter data found for {sel_date}. Please select a date from the logs below.")

# KPI Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³", help="Subtracts previous 4PM reading from 8AM reading")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³", help="Subtracts 8AM reading from 4PM reading")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³", help="Aggregate Daytime + Overnight")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target:.1f} vs Target", delta_color="inverse")

st.divider()

col_left, col_right = st.columns([2.2, 0.8])

with col_left:
    view = st.selectbox("Select Trend View", ["Usage Analysis (Day vs Night)", "LPCD Performance Index", "Efficiency Status Trend"])
    fig = go.Figure()
    
    if not master.empty:
        if "Usage" in view:
            # Replicating the "Green/Blue Overlapping Area" style
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        elif "LPCD" in view:
            master['lpcd_p'] = (master['Total'] * 1000) / pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=[target]*len(master), name="Baseline Target", line=dict(color="red", dash='dash')))

        # Focus Highlight for selected date
        if tot_v > 0:
            y_focus = dt_v if "Usage" in view else (tot_v*1000/pop)
            fig.add_trace(go.Scatter(x=[sel_date], y=[y_focus], mode='markers', name="Selected Day", marker=dict(color='orange', size=15, line=dict(width=2, color='white'))))

    fig.update_layout(template="plotly_white", height=450, margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# THE DATA WRANGLER LOG (To verify the math)
st.divider()
st.subheader("📋 Engineering Data Log (Calculated from Raw Meter)")
st.dataframe(master, use_container_width=True)

# DOWNLOADS
c_csv, c_xls = st.columns(2)
c_csv.download_button("💾 Download as CSV", master.to_csv(index=False), "HMA_Calculated_Data.csv")
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
    master.to_excel(writer, index=False)
c_xls.download_button("📂 Download as Excel", buffer.getvalue(), "HMA_Calculated_Data.xlsx")
