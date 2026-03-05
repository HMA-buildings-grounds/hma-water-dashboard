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

@st.cache_data(ttl=2) # Near-instant refresh
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
    
    # The Calendar
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

# --- 3. SMART DATA AGGREGATION ---
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

if not main_df.empty:
    # 1. Clean Dates and convert to Date objects
    main_df[date_col] = pd.to_datetime(main_df[date_col], errors='coerce').dt.date
    # 2. Convert values to numeric
    main_df[prod_col] = pd.to_numeric(main_df[prod_col], errors='coerce').fillna(0)
    main_df[cons_col] = pd.to_numeric(main_df[cons_col], errors='coerce').fillna(0)
    
    # 3. AGGREGATE BY DATE (This combines morning and afternoon rows)
    # This ensures March 1 data is visible even if it's on a different row
    daily_df = main_df.groupby(date_col).agg({prod_col: 'sum', cons_col: 'sum'}).reset_index()
    daily_df = daily_df.sort_values(by=date_col)
    
    # 4. Filter out empty dates
    daily_df = daily_df[(daily_df[prod_col] > 0) | (daily_df[cons_col] > 0)]
    
    # 5. Fetch Data for Selected Date
    # We compare date object to date object
    row_data = daily_df[daily_df[date_col] == selected_op_date]
    
    if not row_data.empty:
        display_data = row_data.iloc[0]
        status_msg = f"Showing data for: {selected_op_date}"
    else:
        # If user selects a date with no data, show the latest available
        display_data = daily_df.iloc[-1] if not daily_df.empty else None
        status_msg = f"⚠️ No data for {selected_op_date}. Showing latest: {display_data[date_col] if display_data is not None else 'N/A'}"

# --- 4. CALCULATIONS ---
if display_data is not None:
    p_val, c_val = display_data[prod_col], display_data[cons_col]
    lpcd = (c_val * 1000) / campus_pop
    eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0
else:
    p_val, c_val, lpcd, eff = 0, 0, 0, 0

# --- 5. PERFORMANCE DASHBOARD ---
st.title("Operational Diagnostics & Performance")
st.caption(status_msg)

k1, k2, k3 = st.columns(3)
k1.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse", 
          help=f"Calculation: ({c_val} m³ x 1000) / {campus_pop} Population")
k2.metric("System Efficiency", f"{eff:.1f}%", help=f"Calculation: ({target_lpcd} Target / {lpcd:.1f} Actual) x 100")
k3.metric("Daily Production", f"{p_val:.1f} m³", help=f"Calculation: Total volume from well meter for this date.")

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    st.subheader("Operational Diagnostics Trend")
    
    if not daily_df.empty:
        daily_df['lpcd_calc'] = (daily_df[cons_col] * 1000) / campus_pop
        
        fig = go.Figure()

        # Curved Area Trend (The "SaaS" Wave Style)
        fig.add_trace(go.Scatter(
            x=daily_df[date_col], y=daily_df['lpcd_calc'],
            mode='lines', line_shape='spline',
            name='LPCD Trend', line=dict(width=4, color='rgba(13, 148, 136, 0.6)'),
            fill='tozeroy', fillcolor='rgba(13, 148, 136, 0.1)'
        ))

        # WHO Target Line
        fig.add_trace(go.Scatter(
            x=daily_df[date_col], y=[target_lpcd]*len(daily_df),
            name="WHO Target", line=dict(color="#1B263B", dash='dash', width=2)
        ))

        # Selected Date Highlight (The Bold Point)
        if display_data is not None:
            fig.add_trace(go.Scatter(
                x=[display_data[date_col]], y=[lpcd],
                mode='markers+text', name="Selected Day",
                text=[f"{lpcd:.1f}"], textposition="top center",
                marker=dict(color='#1B263B', size=14, line=dict(width=3, color='white'))
            ))

        fig.update_layout(
            template="plotly_white", height=480,
            xaxis=dict(showgrid=False, title="Timeline"), 
            yaxis=dict(title="Liters per Capita"),
            margin=dict(l=0, r=0, t=20, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
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
