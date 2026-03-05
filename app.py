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
st.set_page_config(page_title="HMA Water Analytics", page_icon="💧", layout="wide")

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

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    try: st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except: st.title("HMA ACADEMY")
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=250, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    selected_op_date = st.date_input("Operational Date", value=datetime.now())
    
    st.divider()
    st.markdown("### 📖 Standards\n• [WHO Standards](https://www.who.int)\n• [Sphere Handbook](https://spherestandards.org)")
    
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE MASTER DATA WRANGLER ---
raw_data = fetch_live_data()

def get_clean_master(data_dict):
    full_list = []
    for sheet_name, rows in data_dict.items():
        df = pd.DataFrame(rows)
        if df.empty: continue
        
        # 1. CLEAN HEADERS (Remove line breaks, spaces, and (m³))
        df.columns = [re.sub(r'[^a-zA-Z0-9]', '', str(c).lower()) for c in df.columns]
        
        # 2. IDENTIFY COLUMNS BY KEYWORDS
        d_col = next((c for c in df.columns if "date" in c), None)
        t_col = next((c for c in df.columns if "time" in c), None)
        m_col = next((c for c in df.columns if "meterreading" in c), None)
        
        if all([d_col, t_col, m_col]):
            # Extract Year from sheet name
            yr = re.search(r'20\d{2}', sheet_name)
            yr_val = yr.group(0) if yr else "2026"
            
            sub_df = df[[d_col, t_col, m_col]].copy()
            sub_df.columns = ['date_raw', 'time_raw', 'reading_raw']
            
            # Create Timestamp
            sub_df['ts'] = pd.to_datetime(sub_df['date_raw'].astype(str) + " " + yr_val + " " + sub_df['time_raw'].astype(str), errors='coerce')
            sub_df['reading'] = pd.to_numeric(sub_df['reading_raw'], errors='coerce')
            full_list.append(sub_df.dropna(subset=['ts', 'reading']))

    if not full_list: return pd.DataFrame()

    # 3. GLOBAL CHRONOLOGICAL CALCULATION
    master = pd.concat(full_list).sort_values('ts').reset_index(drop=True)
    
    # Delta Calculation (Current Reading - Previous Reading)
    master['delta'] = master['reading'].diff()
    
    # 4. GROUP INTO 24H BASIS
    final_days = []
    for d, group in master.groupby(master['ts'].dt.date):
        # Overnight = 8:00 AM reading's delta
        overnight = group[group['time_raw'].astype(str).str.contains('8:00')]['delta'].sum()
        # Daytime = 4:00 PM reading's delta
        daytime = group[group['time_raw'].astype(str).str.contains('4:00')]['delta'].sum()
        
        final_days.append({
            'Date': d,
            'Overnight_m3': overnight,
            'Daytime_m3': daytime,
            'Total_24h_m3': overnight + daytime
        })
    return pd.DataFrame(final_days)

# Process the data
master_df = get_clean_master(raw_data)

# --- 4. KPI CALCULATIONS ---
ov, dt, tot, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0

if not master_df.empty:
    target_dt = selected_op_date
    match = master_df[master_df['Date'] == target_dt]
    if not match.empty:
        row = match.iloc[0]
        ov, dt, tot = row['Overnight_m3'], row['Daytime_m3'], row['Total_24h_m3']
        lpcd = (tot * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# --- 5. UI DISPLAY ---
st.title("Operational Diagnostics & Performance")

if tot == 0:
    st.warning(f"⚠️ No readings found for {selected_op_date}. Please check the Spreadsheet.")

# 1. THE THREE DIVISIONS (24hr basis)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Overnight Use", f"{ov:.1f} m³", "8 AM reading delta")
k2.metric("Daytime Use", f"{dt:.1f} m³", "4 PM reading delta")
k3.metric("Total 24h Usage", f"{tot:.1f} m³", help="Combined day + night")
k4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse")

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    view = st.selectbox("Select Performance Trend", ["Overlapping Usage (Day vs Night)", "LPCD Index Trend"])
    
    if not master_df.empty:
        fig = go.Figure()
        if "Overlapping" in view:
            # SaaS Style curved area
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime_m3'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight_m3'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        else:
            master_df['lpcd_p'] = (master_df['Total_24h_m3'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_p'], mode='lines', line_shape='spline', name='Actual LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=[target_lpcd]*len(master_df), name="WHO Target", line=dict(color="red", dash='dash')))

        # HIGHLIGHT SELECTED DATE
        if tot > 0:
            y_val = dt if "Overlapping" in view else (tot*1000/campus_pop)
            fig.add_trace(go.Scatter(x=[selected_op_date], y=[y_val], mode='markers', name="Selected", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# Wrangling Log (For User verification)
with st.expander("🔍 See Engineering Wrangling Calculations"):
    st.dataframe(master_df, use_container_width=True)
