import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
from datetime import datetime

# --- 1. SETTINGS & PROFESSIONAL THEME ---
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

# --- 2. SIDEBAR: OPERATIONAL CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    
    # Calendar Input
    selected_op_date = st.date_input("Operational Date", value=datetime.now())
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("""<div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
        <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
        <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
    </div>""", unsafe_allow_html=True)

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. DATA PROCESSING ENGINE ---
raw_data = fetch_live_data()
main_df = pd.DataFrame()
prod_col, cons_col, date_col = None, None, None

for sheet_name, rows in raw_data.items():
    temp_df = pd.DataFrame(rows)
    if not temp_df.empty:
        cols_norm = {c: "".join(str(c).lower().split()) for c in temp_df.columns}
        p_match = [orig for orig, norm in cols_norm.items() if "wellproduction" in norm]
        c_match = [orig for orig, norm in cols_norm.items() if "facilityconsumption" in norm]
        d_match = [orig for orig, norm in cols_norm.items() if "date" in norm]
        if p_match and c_match and d_match:
            main_df = temp_df
            prod_col, cons_col, date_col = p_match[0], c_match[0], d_match[0]
            break

# Initialize Variables
p_val, c_val, lpcd, eff = 0, 0, 0, 0
daily_df = pd.DataFrame()

if not main_df.empty:
    # 1. FORCE DATE CONVERSION (Handling "Mar 1" as 2026)
    main_df[date_col] = pd.to_datetime(main_df[date_col], errors='coerce', dayfirst=False)
    # Correct Year if spreadsheet only says "Mar 1"
    main_df[date_col] = main_df[date_col].apply(lambda d: d.replace(year=2026) if d and d.year < 2026 else d)
    main_df[date_col] = main_df[date_col].dt.date
    
    # 2. CLEAN NUMBERS
    main_df[prod_col] = pd.to_numeric(main_df[prod_col], errors='coerce').fillna(0)
    main_df[cons_col] = pd.to_numeric(main_df[cons_col], errors='coerce').fillna(0)
    
    # 3. AGGREGATE BY DATE (Take Max to get the daily total)
    daily_df = main_df.groupby(date_col).agg({prod_col: 'max', cons_col: 'max'}).reset_index()
    daily_df = daily_df[daily_df[prod_col] > 0].sort_values(by=date_col)
    
    # 4. FETCH SELECTED DATE
    match = daily_df[daily_df[date_col] == selected_op_date]
    if not match.empty:
        row = match.iloc[0]
        p_val, c_val = row[prod_col], row[cons_col]
        lpcd = (c_val * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# Tooltip Calculations
lpcd_h = f"Calculation: (Cons. [{c_val} m³] × 1000) ÷ Pop. [{campus_pop}] = {lpcd:.1f} LPCD."
eff_h = f"Calculation: (Target [{target_lpcd}] ÷ Actual [{lpcd:.1f}]) × 100 = {eff:.1f}% Efficiency."
prod_h = f"Calculation: Total volume extracted from well meter for {selected_op_date} = {p_val} m³."

# --- 4. PERFORMANCE DASHBOARD VIEW ---
st.title("Operational Diagnostics & Performance")

if p_val == 0 and not daily_df.empty:
    st.warning(f"⚠️ No data found for {selected_op_date}. Please select a date with recorded totals.")

k1, k2, k3 = st.columns(3)
k1.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse", help=lpcd_h)
k2.metric("System Efficiency", f"{eff:.1f}%", help=eff_h)
k3.metric("Daily Production", f"{p_val:.1f} m³", help=prod_h)

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    # 5. REVERTED TO DROPDOWN VISUALIZATION
    chart_view = st.selectbox("Select Performance View", 
                              ["Daily LPCD Index (Target vs Actual)", "Usage Trend (Consumption)", "Production Trend", "Efficiency Trend"])
    
    if not daily_df.empty:
        daily_df['lpcd_calc'] = (daily_df[cons_col] * 1000) / campus_pop
        daily_df['efficiency'] = (target_lpcd / daily_df['lpcd_calc'] * 100).fillna(0)
        
        # Color Palette
        L_BLUE, L_GREEN, L_ORANGE = "#85C1E9", "#82E0AA", "#F8C471"

        fig = go.Figure()

        if "LPCD" in chart_view:
            # Overlapping Curved Area Style (SaaS Image Style)
            fig.add_trace(go.Scatter(x=daily_df[date_col], y=daily_df['lpcd_calc'], mode='lines', line_shape='spline', name='Actual LPCD', line=dict(width=4, color=L_BLUE), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=daily_df[date_col], y=[target_lpcd]*len(daily_df), name="WHO Target", line=dict(color="#1B263B", dash='dash', width=2)))
        
        elif "Usage" in chart_view:
            fig.add_trace(go.Scatter(x=daily_df[date_col], y=daily_df[cons_col], mode='lines', line_shape='spline', name='Consumption', line=dict(width=4, color=L_BLUE), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))

        elif "Production" in chart_view:
            fig.add_trace(go.Scatter(x=daily_df[date_col], y=daily_df[prod_col], mode='lines', line_shape='spline', name='Production', line=dict(width=4, color=L_ORANGE), fill='tozeroy', fillcolor='rgba(248, 196, 113, 0.2)'))
        
        else: # Efficiency
            fig.add_trace(go.Scatter(x=daily_df[date_col], y=daily_df['efficiency'], mode='lines', line_shape='spline', name='Efficiency %', line=dict(width=4, color=L_GREEN), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))

        # Highlight Selected Point
        if p_val > 0:
            fig.add_trace(go.Scatter(x=[selected_op_date], y=[lpcd if "LPCD" in chart_view else (eff if "Efficiency" in chart_view else (p_val if "Production" in chart_view else c_val))], mode='markers', name="Selected Day", marker=dict(color='#1B263B', size=15, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    # 1. PROFESSIONAL NEEDLE GAUGE
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B", 'thickness': 0.2},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# Data Download Center
st.divider()
st.subheader("📥 Data Download Center")
if raw_data:
    sel = st.selectbox("Select Log for Download", list(raw_data.keys()))
    df_dl = pd.DataFrame(raw_data[sel])
    c1, c2 = st.columns(2)
    c1.download_button("💾 Download CSV", df_dl.to_csv(index=False), f"{sel}.csv")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df_dl.to_excel(writer, index=False)
    c2.download_button("📂 Download Excel", buf.getvalue(), f"{sel}.xlsx")
