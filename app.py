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
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 36px; font-weight: 800; }
    [data-testid="stSidebar"] { background-color: #1B263B; border-right: 1px solid #e2e8f0; }
    .stMetric { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    .download-card { padding: 10px; border: 1px solid #eee; border-radius: 8px; margin-bottom: 5px; background: #fff; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=60)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        return requests.get(api_url).json()
    except Exception as e:
        st.error(f"Sync Error: {e}")
        return {}

# --- 2. SIDEBAR: OPERATIONAL CONTROLS & DOWNLOADS ---
with st.sidebar:
    # HMA Logo
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("<h3 style='color: white; font-size: 18px;'>Operational Controls</h3>", unsafe_allow_html=True)
    
    # User Inputs
    pop_count = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100, help="WHO Average: 35-100")
    op_date = st.date_input("Operational Date", value=datetime.now())
    
    st.divider()
    
    # DOWNLOAD & STANDARDS CENTER
    st.markdown("<h3 style='color: white; font-size: 16px;'>📁 Download Center</h3>", unsafe_allow_html=True)
    
    # Standards Links (Icons simulated with emojis)
    st.markdown(f"📖 [WHO Water Standards](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown(f"🌍 [Sphere Handbook Ch.6](https://handbook.spherestandards.org/en/sphere/#ch006)")
    st.markdown(f"🏗️ LEED Standards (Future)")

    st.divider()
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. DATA PROCESSING ---
raw_data = fetch_live_data()
sheet_names = list(raw_data.keys())
main_df = pd.DataFrame(raw_data.get(sheet_names[0] if sheet_names else "", []))

# Clean headers and define columns
PROD_COL = "Total 24h Well Production (m³)"
CONS_COL = "Total 24h Facility Consumption (m³)"

if not main_df.empty and PROD_COL in main_df.columns:
    main_df[PROD_COL] = pd.to_numeric(main_df[PROD_COL], errors='coerce').fillna(0)
    main_df[CONS_COL] = pd.to_numeric(main_df[CONS_COL], errors='coerce').fillna(0)
    
    # Filtering for daily summary rows
    daily_df = main_df[main_df[PROD_COL] > 0].copy()
    
    if not daily_df.empty:
        latest = daily_df.iloc[-1]
        actual_lpcd = (latest[CONS_COL] * 1000) / pop_count
        efficiency_score = (target_lpcd / actual_lpcd * 100) if actual_lpcd > 0 else 0
    else:
        actual_lpcd, efficiency_score = 0, 0
else:
    actual_lpcd, efficiency_score = 0, 0

# --- 4. MAIN DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")

# KPI Top Row
k1, k2, k3 = st.columns(3)
k1.metric("Current LPCD", f"{actual_lpcd:.1f}", f"{actual_lpcd - target_lpcd:.1f} vs Target", delta_color="inverse")
k2.metric("System Efficiency", f"{efficiency_score:.1f}%", help="Based on Baseline LPCD")
k3.metric("Daily Production", f"{latest[PROD_COL] if not daily_df.empty else 0} m³")

st.divider()

# --- 5. ADVANCED VISUALIZATIONS ---
col_trend, col_gauge = st.columns([2, 1])

with col_trend:
    chart_selection = st.selectbox(
        "Select Visualization Layer", 
        ["Daily Projected LPCD vs Actual", "Usage Trend (Consumption)", "Production Trend", "Efficiency Trend"]
    )
    
    # Custom Colors
    L_BLUE = "#85C1E9"
    L_GREEN = "#82E0AA"
    L_ORANGE = "#F8C471"

    if not daily_df.empty:
        daily_df['Actual_LPCD'] = (daily_df[CONS_COL] * 1000) / pop_count
        daily_df['Projected_LPCD'] = target_lpcd

        if chart_selection == "Daily Projected LPCD vs Actual":
            fig = px.line(daily_df, x="Date", y=["Actual_LPCD", "Projected_LPCD"], 
                          title="LPCD: Target vs Actual Performance",
                          color_discrete_sequence=[L_BLUE, "#1B263B"], template="plotly_white")
        
        elif chart_selection == "Usage Trend (Consumption)":
            fig = px.area(daily_df, x="Date", y=CONS_COL, title="Facility Consumption Over Time",
                          color_discrete_sequence=[L_GREEN], template="plotly_white")
            
        elif chart_selection == "Production Trend":
            fig = px.area(daily_df, x="Date", y=PROD_COL, title="Well Water Production Trend",
                          color_discrete_sequence=[L_ORANGE], template="plotly_white")
            
        else: # Efficiency
            daily_df['Eff'] = (target_lpcd / ((daily_df[CONS_COL] * 1000) / pop_count)) * 100
            fig = px.line(daily_df, x="Date", y="Eff", title="System Efficiency Trend (%)",
                          color_discrete_sequence=["#0D9488"], template="plotly_white")

        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

with col_gauge:
    st.markdown(f"### Efficiency Status")
    # Professional Gauge with Needle Logic
    fig_gauge = go.Figure(go.Indicator(
        domain = {'x': [0, 1], 'y': [0, 1]},
        value = efficiency_score,
        mode = "gauge+number",
        title = {'text': "Conservation Index", 'font': {'size': 18}},
        gauge = {
            'axis': {'range': [0, 120], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "#1B263B"}, # The needle/bar
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 50], 'color': "#E74C3C"},   # Red (Critical Overuse)
                {'range': [50, 85], 'color': "#F4D03F"},  # Yellow (Warning)
                {'range': [85, 120], 'color': "#27AE60"}  # Green (Efficient)
            ],
            'threshold': {
                'line': {'color': "black", 'width': 4},
                'thickness': 0.75,
                'value': 100}
        }))
    
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=20,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

st.divider()

# --- 6. VOLUME COMPARISON ---
st.subheader("Volume Comparison: Production vs Consumption (m³)")
if not daily_df.empty:
    fig_vol = px.bar(daily_df, x="Date", y=[PROD_COL, CONS_COL], 
                     barmode="group",
                     title="Daily Volume Balance",
                     color_discrete_map={PROD_COL: L_ORANGE, CONS_COL: L_BLUE},
                     template="plotly_white")
    st.plotly_chart(fig_vol, use_container_width=True)

# --- 7. DATA LOGS & EXPORTS ---
st.divider()
st.subheader("📊 Log Management & Exports")
if raw_data:
    # Selector for logs
    target = st.selectbox("Select Facility Data Log", list(raw_data.keys()))
    df_final = pd.DataFrame(raw_data[target])
    
    st.dataframe(df_final, use_container_width=True)
    
    # EXPORT BUTTONS
    c1, c2 = st.columns(2)
    
    # CSV Export
    csv_bytes = df_final.to_csv(index=False).encode('utf-8')
    c1.download_button("💾 Download as CSV", data=csv_bytes, file_name=f"{target}.csv", mime='text/csv')
    
    # Excel Export
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, sheet_name='DataLog', index=False)
    c2.download_button("📂 Download as Excel (.xlsx)", data=buffer.getvalue(), file_name=f"{target}.xlsx", mime='application/vnd.ms-excel')
