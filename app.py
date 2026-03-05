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

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 38px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=10)
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
    
    # THE CALENDAR (Operational Date)
    selected_date = st.date_input("Operational Date", value=datetime.now())
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("""<div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
        <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
        <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
    </div>""", unsafe_allow_html=True)

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. DATA PROCESSING ---
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
    main_df[date_col] = pd.to_datetime(main_df[date_col], errors='coerce').dt.date
    main_df[prod_col] = pd.to_numeric(main_df[prod_col], errors='coerce').fillna(0)
    main_df[cons_col] = pd.to_numeric(main_df[cons_col], errors='coerce').fillna(0)
    
    # Filter for valid daily logs and sort
    daily_df = main_df[main_df[prod_col] > 0].sort_values(by=date_col).copy()
    
    if not daily_df.empty:
        # COHERENT CALENDAR LOGIC: 
        # Find data for the date selected in the sidebar
        target_row = daily_df[daily_df[date_col] == selected_date]
        
        if not target_row.empty:
            active_row = target_row.iloc[-1]
            st.success(f"Showing data for selected date: {selected_date}")
        else:
            # Fallback to the latest available data if selected date isn't found
            active_row = daily_df.iloc[-1]
            st.warning(f"No data for {selected_date}. Showing latest log from {active_row[date_col]}.")
            
        p_val, c_val = active_row[prod_col], active_row[cons_col]
        actual_lpcd = (c_val * 1000) / campus_pop
        eff = (target_lpcd / actual_lpcd * 100) if actual_lpcd > 0 else 0

# --- 4. DASHBOARD VIEW ---
st.title("Operational Diagnostics & Performance")

k1, k2, k3 = st.columns(3)
k1.metric("Current LPCD", f"{actual_lpcd:.1f}", f"{actual_lpcd - target_lpcd:.1f} vs Target", delta_color="inverse")
k2.metric("System Efficiency", f"{eff:.1f}%")
k3.metric("Daily Production", f"{p_val:.1f} m³")

st.divider()

v_left, v_right = st.columns([2, 1])

with v_left:
    view = st.selectbox("Select Performance View", 
                        ["Daily LPCD Index (Actual vs Target)", "Volume Comparison (Production vs Consumption)"])
    
    L_BLUE, D_NAVY, HIGHLIGHT = "#85C1E9", "#1B263B", "#FF5733"

    if not daily_df.empty:
        if "LPCD" in view:
            daily_df['lpcd_calc'] = (daily_df[cons_col] * 1000) / campus_pop
            fig = px.area(daily_df, x=date_col, y="lpcd_calc", 
                          title=f"Liters Per Capita Per Day (Highlighting {selected_date})",
                          color_discrete_sequence=[L_BLUE], template="plotly_white")
            
            # Add Target Line
            fig.add_scatter(x=daily_df[date_col], y=[target_lpcd]*len(daily_df), name="WHO Target", line=dict(color=D_NAVY, dash='dash'))
            
            # HIGHLIGHT SELECTED DATE: Bold Vertical Line and Point
            fig.add_vline(x=selected_date, line_width=3, line_dash="solid", line_color=HIGHLIGHT)
            fig.add_scatter(x=[selected_date], y=[actual_lpcd], mode='markers', marker=dict(color=HIGHLIGHT, size=12), name="Selected Day")
            
        else:
            fig = px.bar(daily_df, x=date_col, y=[prod_col, cons_col], barmode="group",
                         title="Volume Analytics (m³)",
                         color_discrete_map={prod_col: D_NAVY, cons_col: L_BLUE}, template="plotly_white")
            # Highlight selected date bar group
            fig.add_vline(x=selected_date, line_width=20, line_color=HIGHLIGHT, opacity=0.1)

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
