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

# Navy Sidebar with White Text styling
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 38px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=10) # Refreshes almost instantly (10 seconds)
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
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("""<div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
        <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
        <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
    </div>""", unsafe_allow_html=True)

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. SMART DATA PROCESSING (Fixed Timeline Issue) ---
raw_data = fetch_live_data()
main_df = pd.DataFrame()
prod_col, cons_col, date_col = None, None, None

for sheet_name, rows in raw_data.items():
    temp_df = pd.DataFrame(rows)
    if not temp_df.empty:
        cols_norm = {c: "".join(str(c).lower().split()) for c in temp_df.columns}
        p_match = [orig for orig, norm in cols_norm.items() if "wellproduction" in norm]
        c_match = [orig for orig, norm in cols_norm.items() if "consumption" in norm]
        d_match = [orig for orig, norm in cols_norm.items() if "date" in norm]
        
        if p_match and c_match and d_match:
            main_df = temp_df
            prod_col, cons_col, date_col = p_match[0], c_match[0], d_match[0]
            break

# Initialize variables
p_val, c_val, actual_lpcd, eff = 0.0, 0.0, 0.0, 0.0
daily_df = pd.DataFrame()

if not main_df.empty:
    # 1. CLEAN DATES: Force conversion to datetime to ensure no gaps in the chart
    main_df[date_col] = pd.to_datetime(main_df[date_col], errors='coerce')
    main_df = main_df.dropna(subset=[date_col]) # Remove rows without dates
    
    # 2. CLEAN NUMBERS
    main_df[prod_col] = pd.to_numeric(main_df[prod_col], errors='coerce').fillna(0)
    main_df[cons_col] = pd.to_numeric(main_df[cons_col], errors='coerce').fillna(0)
    
    # 3. FILTER & SORT: Ensure the chart expands with the newest data
    daily_df = main_df[main_df[prod_col] > 0].sort_values(by=date_col).copy()
    
    if not daily_df.empty:
        latest = daily_df.iloc[-1]
        p_val, c_val = latest[prod_col], latest[cons_col]
        actual_lpcd = (c_val * 1000) / campus_pop
        eff = (target_lpcd / actual_lpcd * 100) if actual_lpcd > 0 else 0

# --- 4. DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")

k1, k2, k3 = st.columns(3)
k1.metric("Current LPCD", f"{actual_lpcd:.1f}", f"{actual_lpcd - target_lpcd:.1f} vs Target", delta_color="inverse")
k2.metric("System Efficiency", f"{eff:.1f}%")
k3.metric("Daily Production", f"{p_val:.1f} m³")

st.divider()

v_left, v_right = st.columns([2, 1])

with v_left:
    view = st.selectbox("Select Performance View", 
                        ["Daily LPCD Index (Actual vs Target)", "Volume Comparison (Production vs Consumption)", "Conservation Efficiency Trend"])
    
    # LIGHT BLUE COLOR PALETTE
    L_BLUE, D_NAVY, L_GREEN = "#85C1E9", "#1B263B", "#82E0AA"

    if not daily_df.empty:
        if "LPCD" in view:
            daily_df['lpcd_calc'] = (daily_df[cons_col] * 1000) / campus_pop
            daily_df['Target'] = target_lpcd
            fig = px.area(daily_df, x=date_col, y="lpcd_calc", 
                          title="Liters Per Capita Per Day (LPCD)",
                          color_discrete_sequence=[L_BLUE], template="plotly_white")
            # Add the target line
            fig.add_scatter(x=daily_df[date_col], y=daily_df['Target'], name="WHO Target", line=dict(color=D_NAVY, dash='dash'))
            
        elif "Volume" in view:
            fig = px.bar(daily_df, x=date_col, y=[prod_col, cons_col], barmode="group",
                         title="Volume Analytics (m³)",
                         color_discrete_map={prod_col: D_NAVY, cons_col: L_BLUE}, template="plotly_white")
        else:
            daily_df['efficiency'] = (target_lpcd / ((daily_df[cons_col] * 1000) / campus_pop)) * 100
            fig = px.line(daily_df, x=date_col, y="efficiency", title="Efficiency Index (%)",
                          color_discrete_sequence=[L_GREEN], template="plotly_white")
        
        fig.update_layout(height=400, margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]},
                 'bar': {'color': D_NAVY},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, 
                           {'range': [50, 85], 'color': "#FFF9C4"}, 
                           {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
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
