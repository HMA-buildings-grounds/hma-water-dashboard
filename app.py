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

@st.cache_data(ttl=2)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        return requests.get(api_url).json()
    except:
        return {}

# --- 2. SIDEBAR ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=250, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    
    # User selects date - Dashboard "cooks" data for this day
    selected_op_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("• [WHO Water Standards](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("• [Sphere Handbook Ch.6](https://handbook.spherestandards.org/en/sphere/#ch006)")

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE "ENGINEERING WRANGLE" ENGINE ---
raw_data = fetch_live_data()

def clean_and_wrangle(data_dict):
    all_readings = []
    
    for sheet_name, rows in data_dict.items():
        df = pd.DataFrame(rows)
        if df.empty: continue
        
        # 1. Extract Year from Sheet Title (e.g. "Mar 2026")
        year_match = re.search(r'20\d{2}', sheet_name)
        sheet_year = year_match.group(0) if year_match else "2026"
        
        # 2. Fuzzy Column Detection
        df.columns = [str(c).strip() for c in df.columns]
        d_col = next((c for c in df.columns if "Date" in c), None)
        t_col = next((c for c in df.columns if "Time" in c), None)
        # Specifically looking for the raw meter reading column
        r_col = next((c for c in df.columns if "well" in c.lower() and "reading" in c.lower()), None)
        
        if all([d_col, t_col, r_col]):
            df = df[[d_col, t_col, r_col]].copy()
            df.columns = ['DateRaw', 'TimeRaw', 'Reading']
            # Convert "Mar 1" + "2026" + "8:00 AM" into a real computer timestamp
            df['Timestamp'] = pd.to_datetime(df['DateRaw'].astype(str) + " " + sheet_year + " " + df['TimeRaw'].astype(str), errors='coerce')
            df['Reading'] = pd.to_numeric(df['Reading'], errors='coerce')
            all_readings.append(df.dropna(subset=['Timestamp', 'Reading']))

    if not all_readings: return pd.DataFrame()

    # 3. Create Master Timeline (Sorting Feb -> Mar)
    full_timeline = pd.concat(all_readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
    
    # 4. CALCULATE DELTA (The Subtraction)
    # This automatically subtracts Mar 1 8AM from Feb 28 4PM
    full_timeline['Usage_m3'] = full_timeline['Reading'].diff()
    
    # 5. Group into 24-hour Daily Buckets
    daily_results = []
    full_timeline['DateOnly'] = full_timeline['Timestamp'].dt.date
    
    for date, group in full_timeline.groupby('DateOnly'):
        # Overnight: The delta calculated at the 8:00 AM mark
        ov_usage = group[group['TimeRaw'].astype(str).str.contains('8:00', na=False)]['Usage_m3'].sum()
        # Daytime: The delta calculated at the 4:00 PM mark
        dt_usage = group[group['TimeRaw'].astype(str).str.contains('4:00', na=False)]['Usage_m3'].sum()
        
        daily_results.append({
            'Date': date,
            'Daytime_Usage': dt_usage,
            'Overnight_Usage': ov_usage,
            'Total_24h_Usage': dt_usage + ov_usage
        })
        
    return pd.DataFrame(daily_results)

master_df = clean_and_wrangle(raw_data)

# --- 4. KPI CALCULATIONS ---
ov, dt, tot, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master_df.empty:
    match = master_df[master_df['Date'] == selected_op_date]
    if not match.empty:
        res = match.iloc[0]
        ov, dt, tot = res['Overnight_Usage'], res['Daytime_Usage'], res['Total_24h_Usage']
        lpcd = (tot * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# Formula Descriptions for ? icons
lpcd_help = f"Water Distribution Index (LPCD): (Total 24h Usage [{tot} m³] × 1000) ÷ Population [{campus_pop}] = {lpcd:.1f} Liters per person per day."
eff_help = f"System Efficiency: (Baseline Target [{target_lpcd} LPCD] ÷ Actual LPCD [{lpcd:.1f}]) × 100. Currently {eff:.1f}% of target goal."
ov_help = f"Overnight Usage: Calculated by subtracting the previous day's 4:00 PM meter reading from today's 8:00 AM meter reading."
dt_help = f"Daytime Usage: Calculated by subtracting today's 8:00 AM meter reading from today's 4:00 PM meter reading."

# --- 5. DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")

if tot == 0 and not master_df.empty:
    st.warning(f"No meter readings found for {selected_op_date}. Please check the 'Calculated Data Log' below to see available dates.")

# ROW 1: THE FOUR DIVISIONS
k1, k2, k3, k4 = st.columns(4)
k1.metric("Overnight Usage", f"{ov:.1f} m³", help=ov_help)
k2.metric("Daytime Usage", f"{dt:.1f} m³", help=dt_help)
k3.metric("Total 24h Usage", f"{tot:.1f} m³", help="The aggregate production for the full 24-hour cycle.")
k4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target_lpcd:.1f} vs Target", delta_color="inverse", help=lpcd_help)

st.divider()

# ROW 2: VISUALIZATIONS
v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    # DROPDOWN RESTORED
    chart_view = st.selectbox("Select Performance Trend", 
                              ["Overlapping Usage (Daytime vs Overnight)", "Daily LPCD Index (24h Basis)", "System Efficiency Trend"])
    
    if not master_df.empty:
        fig = go.Figure()
        
        if "Overlapping" in chart_view:
            # SaaS Green/Blue Curved Area Chart
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime_Usage'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight_Usage'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        
        elif "LPCD" in chart_view:
            master_df['lpcd_p'] = (master_df['Total_24h_Usage'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=[target_lpcd]*len(master_df), name="Baseline Target", line=dict(color="red", dash='dash')))

        # Highlight Selected Date in BOLD
        if tot > 0:
            y_val = dt if "Overlapping" in chart_view else (tot*1000/campus_pop if "LPCD" in chart_view else eff)
            fig.add_trace(go.Scatter(x=[selected_op_date], y=[y_val], mode='markers+text', name="Selected Date", text=[f"{selected_op_date}"], textposition="top center", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# THE WRANGLE LOG (For verification)
st.divider()
st.subheader("📋 Calculated Data Log (Engineering View)")
st.write("This table shows the result of the Daytime/Overnight wrangling logic:")
st.dataframe(master_df, use_container_width=True)
