import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & THEME ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 38px; font-weight: 800; }
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
    selected_op_date = st.date_input("Operational Date", value=datetime(2025, 12, 12)) # Default to your data date for testing
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("""<div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
        <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
        <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
    </div>""", unsafe_allow_html=True)

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. RE-ENGINEERED DATA CALCULATOR ---
raw_data = fetch_live_data()

def build_hma_master(data_dict):
    all_combined = []
    for sheet_name, rows in data_dict.items():
        df = pd.DataFrame(rows)
        if df.empty: continue
        
        # Extract year from sheet name (e.g., "Sep 2025" -> 2025)
        year_match = re.search(r'20\d{2}', sheet_name)
        sheet_year = year_match.group(0) if year_match else "2026"
        
        # Clean columns
        df.columns = [str(c).strip() for c in df.columns]
        d_col = next((c for c in df.columns if "Date" in c), None)
        t_col = next((c for c in df.columns if "Time" in c), None)
        m_col = next((c for c in df.columns if "Meter Reading" in c), None)
        
        if all([d_col, t_col, m_col]):
            df = df[[d_col, t_col, m_col]].copy()
            df.columns = ['DateRaw', 'TimeRaw', 'Reading']
            # Create full timestamp
            df['Timestamp'] = pd.to_datetime(df['DateRaw'].astype(str) + " " + sheet_year + " " + df['TimeRaw'].astype(str), errors='coerce')
            df['Reading'] = pd.to_numeric(df['Reading'], errors='coerce')
            all_combined.append(df.dropna(subset=['Timestamp', 'Reading']))

    if not all_combined: return pd.DataFrame()

    # Sort globally by time
    full_log = pd.concat(all_combined).sort_values('Timestamp').reset_index(drop=True)
    
    # CALCULATE USAGE (Current Reading minus Previous Reading)
    full_log['Usage'] = full_log['Reading'].diff()
    
    # Identify Time Periods
    full_log['Period'] = full_log['TimeRaw'].apply(lambda x: 'Daytime' if '4:00' in str(x) else 'Overnight')
    full_log['DateOnly'] = full_log['Timestamp'].dt.date
    
    # Pivot to Daily Summary
    daily_summary = []
    for date, group in full_log.groupby('DateOnly'):
        ov = group[group['Period'] == 'Overnight']['Usage'].sum()
        dt = group[group['Period'] == 'Daytime']['Usage'].sum()
        daily_summary.append({
            'Date': date,
            'Overnight': ov,
            'Daytime': dt,
            'Total': ov + dt
        })
    
    return pd.DataFrame(daily_summary)

master_df = build_hma_master(raw_data)

# --- 4. MATCHING LOGIC ---
ov_val, dt_val, total_val, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master_df.empty:
    match = master_df[master_df['Date'] == selected_op_date]
    if not match.empty:
        res = match.iloc[0]
        ov_val, dt_val, total_val = res['Overnight'], res['Daytime'], res['Total']
        lpcd = (total_val * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# Tooltips
lpcd_h = f"({total_val} m³ × 1000) / {campus_pop} pop = {lpcd:.1f} LPCD"
eff_h = f"({target_lpcd} Target / {lpcd:.1f} Actual) × 100 = {eff:.1f}%"

# --- 5. UI VIEW ---
st.title("Operational Diagnostics & Performance")

if total_val == 0:
    st.warning(f"⚠️ No data found for {selected_op_date}. Please select a valid date from the logs.")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Overnight Use", f"{ov_val:.1f} m³", "8:00 AM Delta")
k2.metric("Daytime Use", f"{dt_val:.1f} m³", "4:00 PM Delta")
k3.metric("Total 24h Production", f"{total_val:.1f} m³", help=f"Sum: {ov_val} + {dt_val}")
k4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse", help=lpcd_h)

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    chart_view = st.selectbox("Select Trend View", ["Usage Analysis (Overlapping Day/Night)", "Total LPCD Index", "System Efficiency Trend"])
    
    if not master_df.empty:
        fig = go.Figure()
        if "Usage" in chart_view:
            # Replicating your GREEN reference image style
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime'], mode='lines', line_shape='spline', name='Daytime Use', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight'], mode='lines', line_shape='spline', name='Overnight Use', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        
        elif "LPCD" in chart_view:
            master_df['lpcd_plot'] = (master_df['Total'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_plot'], mode='lines', line_shape='spline', name='Actual LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=[target_lpcd]*len(master_df), name="WHO Target", line=dict(color="red", dash='dash')))

        # FOCUS HIGHLIGHT (Selected Day)
        if total_val > 0:
            y_focus = dt_val if "Usage" in chart_view else (total_val*1000/campus_pop)
            fig.add_trace(go.Scatter(x=[selected_op_date], y=[y_focus], mode='markers', name="Selected Day", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

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

# Data Log View
st.divider()
st.subheader("📋 Calculated Data Log")
st.dataframe(master_df, use_container_width=True)
