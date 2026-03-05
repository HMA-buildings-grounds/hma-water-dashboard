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

# Custom CSS to force visibility on Navy Sidebar
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 34px; font-weight: 800; }
    .stMetric { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    .reference-box { padding: 10px; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; background: rgba(255,255,255,0.05); margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=30)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        return requests.get(api_url).json()
    except:
        return {}

# --- 2. SIDEBAR: BRANDING & CONTROLS ---
with st.sidebar:
    # HMA Logo
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("### Operational Controls")
    
    # Ensuring these are visible on Navy
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    op_date = st.date_input("Operational Date", value=datetime.now())
    
    st.divider()
    
    st.markdown("### 📖 Standards & References")
    st.markdown("""
        <div class="reference-box">
            <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a>
        </div>
        <div class="reference-box">
            <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
        </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. SMART DATA PROCESSING (Fixed 0.0 Issue) ---
raw_data = fetch_live_data()
main_df = pd.DataFrame()
prod_col, cons_col = None, None

# SEARCH ACROSS ALL SHEETS FOR THE RIGHT DATA
for sheet_name, rows in raw_data.items():
    temp_df = pd.DataFrame(rows)
    if not temp_df.empty:
        # Clean column names for matching
        cols = [str(c).lower().strip() for c in temp_df.columns]
        # Look for the specific production and consumption keywords
        if any("well production" in c for c in cols) and any("consumption" in c for c in cols):
            main_df = temp_df
            # Set the actual column names
            prod_col = [c for c in temp_df.columns if "well production" in str(c).lower()][0]
            cons_col = [c for c in temp_df.columns if "consumption" in str(c).lower()][0]
            break

# Initialize variables
p_val, c_val, actual_lpcd, eff = 0.0, 0.0, 0.0, 0.0
daily_df = pd.DataFrame()

if not main_df.empty:
    # Ensure numeric data
    main_df[prod_col] = pd.to_numeric(main_df[prod_col], errors='coerce').fillna(0)
    main_df[cons_col] = pd.to_numeric(main_df[cons_col], errors='coerce').fillna(0)
    
    # Extract totals (where production > 0)
    daily_df = main_df[main_df[prod_col] > 0].copy()
    
    if not daily_df.empty:
        latest = daily_df.iloc[-1]
        p_val = latest[prod_col]
        c_val = latest[cons_col]
        actual_lpcd = (c_val * 1000) / campus_pop
        eff = (target_lpcd / actual_lpcd * 100) if actual_lpcd > 0 else 0

# --- 4. DASHBOARD VIEW ---
st.title("Operational Diagnostics & Performance")

# KPI Row
k1, k2, k3 = st.columns(3)
k1.metric("Current LPCD", f"{actual_lpcd:.1f}", f"{actual_lpcd - target_lpcd:.1f} vs Target", delta_color="inverse")
k2.metric("System Efficiency", f"{eff:.1f}%")
k3.metric("Daily Production", f"{p_val:.1f} m³")

st.divider()

# Advanced Visualizations Row
v_left, v_right = st.columns([2, 1])

with v_left:
    view = st.selectbox("Select Performance View", 
                        ["Daily LPCD Index", "Volume: Production vs Consumption", "Efficiency Trend"])
    
    if not daily_df.empty:
        if "LPCD" in view:
            daily_df['lpcd_calc'] = (daily_df[cons_col] * 1000) / campus_pop
            daily_df['Target'] = target_lpcd
            fig = px.line(daily_df, x="Date", y=["lpcd_calc", "Target"], 
                          title="Liters Per Capita Per Day (LPCD)",
                          color_discrete_sequence=["#85C1E9", "#1B263B"], template="plotly_white")
        elif "Volume" in view:
            fig = px.bar(daily_df, x="Date", y=[prod_col, cons_col], barmode="group",
                         title="Volume Balance (m³)",
                         color_discrete_map={prod_col: "#F8C471", cons_col: "#85C1E9"}, template="plotly_white")
        else:
            daily_df['efficiency'] = (target_lpcd / ((daily_df[cons_col] * 1000) / campus_pop)) * 100
            fig = px.area(daily_df, x="Date", y="efficiency", title="Conservation Efficiency (%)",
                          color_discrete_sequence=["#82E0AA"], template="plotly_white")
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Awaiting historical data sync...")

with v_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]},
                 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#E74C3C"}, 
                           {'range': [50, 85], 'color': "#F4D03F"}, 
                           {'range': [85, 100], 'color': "#27AE60"}]}))
    fig_gauge.update_layout(height=350, margin=dict(l=20,r=20,t=40,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# Data Download Section
st.divider()
st.subheader("📥 Data Download Center")
if raw_data:
    sel = st.selectbox("Select Log for Download", list(raw_data.keys()))
    df_sel = pd.DataFrame(raw_data[sel])
    c_csv, c_xls = st.columns(2)
    c_csv.download_button("💾 Download CSV", df_sel.to_csv(index=False), f"{sel}.csv")
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_sel.to_excel(writer, index=False)
    c_xls.download_button("📂 Download Excel", buffer.getvalue(), f"{sel}.xlsx")
