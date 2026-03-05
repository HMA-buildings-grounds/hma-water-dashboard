import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
from datetime import datetime

# --- 1. SETTINGS & BRANDING ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

# Custom Professional CSS
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 34px; font-weight: 800; }
    [data-testid="stSidebar"] { background-color: #1B263B; border-right: 1px solid #e2e8f0; }
    .stMetric { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    .reference-box { padding: 10px; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; background: rgba(255,255,255,0.05); margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=60)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        return requests.get(api_url).json()
    except Exception as e:
        return {}

# --- 2. SIDEBAR: OPERATIONAL CONTROLS & REFERENCES ---
with st.sidebar:
    # HMA Logo
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("<h3 style='color: white; font-size: 18px;'>Operational Controls</h3>", unsafe_allow_html=True)
    
    # 3 & 4. DYNAMIC USER INPUTS
    pop_count = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100, help="WHO Std: 35-100")
    op_date = st.date_input("Operational Date", value=datetime.now())
    
    st.divider()
    
    # 2.2. STANDARDS & REFERENCES (Non-Downloadable)
    st.markdown("<h3 style='color: white; font-size: 16px;'>📖 Standards & References</h3>", unsafe_allow_html=True)
    st.markdown(f"""
        <div class="reference-box">
            <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br>
            <small style="color:#ccc;">Guidelines for quality & quantity</small>
        </div>
        <div class="reference-box">
            <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a><br>
            <small style="color:#ccc;">Humanitarian water response</small>
        </div>
        <div class="reference-box">
            <span style="color:#888;">🏗️ LEED Standards</span><br>
            <small style="color:#666;">Future Integration</small>
        </div>
    """, unsafe_allow_html=True)

    st.divider()
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. DATA PROCESSING ---
raw_data = fetch_live_data()
sheet_names = list(raw_data.keys())
main_df = pd.DataFrame(raw_data.get(sheet_names[0] if sheet_names else "", []))

# Define columns and initialize variables to avoid NameErrors
PROD_COL = "Total 24h Well Production (m³)"
CONS_COL = "Total 24h Facility Consumption (m³)"
p_val, c_val, actual_lpcd, efficiency_score = 0.0, 0.0, 0.0, 0.0
daily_df = pd.DataFrame()

if not main_df.empty and PROD_COL in main_df.columns:
    main_df[PROD_COL] = pd.to_numeric(main_df[PROD_COL], errors='coerce').fillna(0)
    main_df[CONS_COL] = pd.to_numeric(main_df[CONS_COL], errors='coerce').fillna(0)
    daily_df = main_df[main_df[PROD_COL] > 0].copy()
    
    if not daily_df.empty:
        latest_row = daily_df.iloc[-1]
        p_val = latest_row[PROD_COL]
        c_val = latest_row[CONS_COL]
        actual_lpcd = (c_val * 1000) / pop_count
        # Efficiency increases as actual LPCD gets closer or lower than target
        efficiency_score = (target_lpcd / actual_lpcd * 100) if actual_lpcd > 0 else 0

# --- 4. MAIN DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")

# KPI Top Row
k1, k2, k3 = st.columns(3)
k1.metric("Current LPCD", f"{actual_lpcd:.1f}", f"{actual_lpcd - target_lpcd:.1f} vs Target", delta_color="inverse")
k2.metric("System Efficiency", f"{efficiency_score:.1f}%", help="Performance relative to Baseline LPCD")
k3.metric("Daily Production", f"{p_val:.1f} m³")

st.divider()

# --- 5. ADVANCED VISUALIZATIONS ---
col_trend, col_gauge = st.columns([2, 1])

with col_trend:
    # 5. Dropdown for various visualizations
    chart_selection = st.selectbox(
        "Select Performance View", 
        ["Daily Projected LPCD vs Actual", "Usage Trend (Consumption)", "Production Trend", "Efficiency Trend"]
    )
    
    L_BLUE, L_GREEN, L_ORANGE = "#85C1E9", "#82E0AA", "#F8C471"

    if not daily_df.empty:
        daily_df['Actual_LPCD'] = (daily_df[CONS_COL] * 1000) / pop_count
        daily_df['Projected_LPCD'] = target_lpcd

        if chart_selection == "Daily Projected LPCD vs Actual":
            fig = px.line(daily_df, x="Date", y=["Actual_LPCD", "Projected_LPCD"], 
                          title="LPCD Performance Index",
                          color_discrete_sequence=[L_BLUE, "#1B263B"], template="plotly_white")
        
        elif chart_selection == "Usage Trend (Consumption)":
            fig = px.area(daily_df, x="Date", y=CONS_COL, title="Daily Facility Consumption (m³)",
                          color_discrete_sequence=[L_BLUE], template="plotly_white")
            
        elif chart_selection == "Production Trend":
            fig = px.area(daily_df, x="Date", y=PROD_COL, title="Daily Well Production (m³)",
                          color_discrete_sequence=[L_ORANGE], template="plotly_white")
            
        else: # Efficiency
            daily_df['Eff'] = (target_lpcd / ((daily_df[CONS_COL] * 1000) / pop_count)) * 100
            fig = px.line(daily_df, x="Date", y="Eff", title="System Efficiency (%)",
                          color_discrete_sequence=[L_GREEN], template="plotly_white")

        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)

with col_gauge:
    # 1. Professional Gauge
    st.markdown(f"### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        domain = {'x': [0, 1], 'y': [0, 1]},
        value = efficiency_score,
        mode = "gauge+number",
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1},
            'bar': {'color': "#1B263B", 'thickness': 0.25}, # The Needle/Bar
            'steps': [
                {'range': [0, 40], 'color': "#E74C3C"},   # Red: Critical Overuse
                {'range': [40, 75], 'color': "#F4D03F"},  # Yellow: Warning
                {'range': [75, 100], 'color': "#27AE60"}  # Green: Efficient
            ],
            'threshold': {
                'line': {'color': "black", 'width': 3},
                'thickness': 0.75,
                'value': 100}
        }))
    fig_gauge.update_layout(height=380, margin=dict(l=20,r=20,t=20,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# 6. VOLUME COMPARISON (Bar Chart)
st.subheader("Volume Comparison: Production vs Consumption (m³)")
if not daily_df.empty:
    fig_vol = px.bar(daily_df, x="Date", y=[PROD_COL, CONS_COL], 
                     barmode="group",
                     color_discrete_map={PROD_COL: L_ORANGE, CONS_COL: L_BLUE},
                     template="plotly_white")
    st.plotly_chart(fig_vol, use_container_width=True)

# 2.1. DOWNLOAD CENTER (Data Logs Only)
st.divider()
st.subheader("📥 Data Download Center")
if raw_data:
    col_sel, col_csv, col_xlsx = st.columns([2, 1, 1])
    target_log = col_sel.selectbox("Select Log for Download", sheet_names)
    df_dl = pd.DataFrame(raw_data[target_log])
    
    # CSV Download
    csv_bytes = df_dl.to_csv(index=False).encode('utf-8')
    col_csv.download_button("💾 Download CSV", data=csv_bytes, file_name=f"{target_log}.csv", mime='text/csv', use_container_width=True)
    
    # Excel Download
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df_dl.to_excel(writer, index=False)
    col_xlsx.download_button("📂 Download Excel", data=buf.getvalue(), file_name=f"{target_log}.xlsx", use_container_width=True)
