import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime, timedelta

# --- 1. SETTINGS & BRANDING ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 32px; font-weight: 800; }
    .stMetric { background: white; padding: 15px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
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
    campus_pop = st.number_input("Campus Population", value=250, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    selected_op_date = st.date_input("Operational Date", value=datetime(2025, 12, 12)) # Example date
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("""<div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
        <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
        <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
    </div>""", unsafe_allow_html=True)

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. DATA WRANGLING ENGINE (Daytime/Overnight Logic) ---
raw_data = fetch_live_data()

def wrangle_hma_data(data_dict):
    all_readings = []
    for sheet_name, rows in data_dict.items():
        df = pd.DataFrame(rows)
        if df.empty: continue
        
        # Determine Year from Sheet Title (e.g., "Jan 2026")
        year_search = re.search(r'20\d{2}', sheet_name)
        year_str = year_search.group(0) if year_search else "2025"
        
        # Standardize Columns
        df.columns = [str(c).strip() for c in df.columns]
        d_col = next((c for c in df.columns if "Date" in c), None)
        t_col = next((c for c in df.columns if "Time" in c), None)
        m_col = next((c for c in df.columns if "Meter Reading" in c), None)
        
        if all([d_col, t_col, m_col]):
            df = df[[d_col, t_col, m_col]].copy()
            df.columns = ['Date', 'Time', 'Reading']
            # Create a real Timestamp for cross-month sorting
            df['Timestamp'] = pd.to_datetime(df['Date'].astype(str) + " " + year_str + " " + df['Time'].astype(str), errors='coerce')
            df['Reading'] = pd.to_numeric(df['Reading'], errors='coerce')
            all_readings.append(df.dropna())

    if not all_readings: return pd.DataFrame()

    # Sort everything globally (Corrects month-to-month gaps)
    full_timeline = pd.concat(all_readings).sort_values('Timestamp').reset_index(drop=True)
    
    # CALCULATE DELTA: Reading[N] - Reading[N-1]
    full_timeline['Usage_m3'] = full_timeline['Reading'].diff()
    full_timeline['DateOnly'] = full_timeline['Timestamp'].dt.date
    
    # CLASSIFY: 8 AM reading is "Overnight" (from previous 4PM); 4 PM is "Daytime"
    processed_days = []
    for date, group in full_timeline.groupby('DateOnly'):
        overnight = group[group['Time'].str.contains('8:00', na=False)]['Usage_m3'].sum()
        daytime = group[group['Time'].str.contains('4:00', na=False)]['Usage_m3'].sum()
        
        processed_days.append({
            'Date': date,
            'Daytime': daytime,
            'Overnight': overnight,
            'Total_24h': daytime + overnight
        })
        
    return pd.DataFrame(processed_days)

master_df = wrangle_hma_data(raw_data)

# --- 4. CALCULATION & HIGHLIGHTING ---
ov_val, dt_val, tot_val, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master_df.empty:
    match = master_df[master_df['Date'] == selected_op_date]
    if not match.empty:
        res = match.iloc[0]
        ov_val, dt_val, tot_val = res['Overnight'], res['Daytime'], res['Total_24h']
        lpcd = (tot_val * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# Calculations for tooltips
ov_help = f"Usage between previous 4:00 PM and today's 8:00 AM."
dt_help = f"Usage between 8:00 AM and 4:00 PM today."
tot_help = f"Aggregate well production for the full 24-hour cycle."
lpcd_help = f"Calculation: ({tot_val} m³ × 1000) / {campus_pop} pop = {lpcd:.1f} LPCD."

# --- 5. UI VIEW ---
st.title("Operational Diagnostics & Performance")

if tot_val == 0:
    st.warning(f"⚠️ No data found for {selected_op_date}. Please select a date with recorded meter readings.")

# Metrics Row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_val:.1f} m³", help=ov_help)
c2.metric("Daytime Usage", f"{dt_val:.1f} m³", help=dt_help)
c3.metric("Total 24h Usage", f"{tot_val:.1f} m³", help=tot_help)
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse", help=lpcd_help)

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    # REVERTED TO DROPDOWN TREND VIEW
    chart_view = st.selectbox("Select Performance Trend", 
                              ["Overlapping Usage (Day vs Night)", "Total LPCD Index (24h)", "System Efficiency Trend"])
    
    if not master_df.empty:
        fig = go.Figure()
        
        if "Overlapping" in chart_view:
            # SaaS Style "Green Chart" interpolation
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        
        elif "LPCD" in chart_view:
            master_df['lpcd_plot'] = (master_df['Total_24h'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_plot'], mode='lines', line_shape='spline', name='Daily LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.1)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=[target_lpcd]*len(master_df), name="Target", line=dict(color="red", dash='dash')))

        # HIGH-END HIGHLIGHT (Bold point for selected date)
        if tot_val > 0:
            y_focus = dt_val if "Usage" in chart_view else (tot_val*1000/campus_pop)
            fig.add_trace(go.Scatter(x=[selected_op_date], y=[y_focus], mode='markers+text', name="Selected", text=[f"{selected_op_date}"], textposition="top center", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

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

# Calculated Data Log
st.divider()
st.subheader("📋 Engineering Data Wrangling (Calculated from Raw Readings)")
st.dataframe(master_df, use_container_width=True)
