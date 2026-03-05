import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & BRANDING ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }[data-testid="stSidebar"] { background-color: #1B263B !important; }[data-testid="stSidebar"] * { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 38px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# DIRECT CONNECTION (No Cache issues)
def fetch_live_data():
    try:
        url = st.secrets["google_sheets"]["api_url"]
        return requests.get(url).json()
    except:
        return {}

# --- 2. SIDEBAR: OPERATIONAL CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.markdown("<h2 style='text-align:center;'>💧 HMA WATER</h2>", unsafe_allow_html=True)
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=250, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    
    # CALENDAR SELECTOR
    selected_op_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("•[WHO Water Standards](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("• [Sphere Handbook Ch.6](https://handbook.spherestandards.org/en/sphere/#ch006)")

    st.divider()
    if st.button("🔄 Sync Live Data"):
        st.rerun()

# --- 3. DATA ENGINE (FIXED THE FEB 27 BUG) ---
raw_data = fetch_live_data()

PROD_COL = "Total 24h Well Production (m³)"
CONS_COL = "Total 24h Facility Consumption (m³)"

all_months_data =[]

# This loop stitches all your tabs (Jan, Feb, Mar) together
for sheet_name, rows in raw_data.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    df.columns =[str(c).strip() for c in df.columns]
    
    # Check if this tab has the required columns
    if PROD_COL in df.columns and CONS_COL in df.columns and "Date" in df.columns:
        # Get the year from the sheet name
        year_match = re.search(r'20\d{2}', sheet_name)
        year = year_match.group(0) if year_match else "2026"
        
        # Create a clean date format so the chart doesn't stop
        df['CleanDate'] = pd.to_datetime(df['Date'].astype(str) + " " + year, errors='coerce').dt.date
        
        # Convert values to numbers
        df[PROD_COL] = pd.to_numeric(df[PROD_COL], errors='coerce').fillna(0)
        df[CONS_COL] = pd.to_numeric(df[CONS_COL], errors='coerce').fillna(0)
        
        # Only keep rows that have daily totals entered
        valid_rows = df[df[PROD_COL] > 0]
        all_months_data.append(valid_rows)

if all_months_data:
    # Combine everything into one long, continuous timeline
    daily_df = pd.concat(all_months_data).sort_values('CleanDate').drop_duplicates('CleanDate')
else:
    daily_df = pd.DataFrame()

# --- 4. CALCULATION & CALENDAR MATCHING ---
p_val, c_val, lpcd, eff = 0.0, 0.0, 0.0, 0.0

if not daily_df.empty:
    # Find the data for the specific day you selected in the sidebar
    match = daily_df[daily_df['CleanDate'] == selected_op_date]
    if not match.empty:
        p_val = match.iloc[0][PROD_COL]
        c_val = match.iloc[0][CONS_COL]
        
        # Run calculations
        lpcd = (c_val * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# --- 5. UI DASHBOARD ---
st.title("Operational Diagnostics & Performance")

if p_val == 0:
    st.warning(f"⚠️ No data found for {selected_op_date}. Please select a date that has data in the spreadsheet.")

# THE 3 KPI CARDS (Restored)
k1, k2, k3 = st.columns(3)
k1.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse", help=f"({c_val} m³ × 1000) ÷ {campus_pop} pop")
k2.metric("System Efficiency", f"{eff:.1f}%", help=f"({target_lpcd} Target ÷ {lpcd:.1f} Actual) × 100")
k3.metric("Daily Production", f"{p_val:.1f} m³", help="Total 24h Well Production")

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    # THE DROPDOWN CHART
    chart_view = st.selectbox("Select Performance View",["Volume Trend (Production vs Consumption)", "Daily LPCD Index (Target vs Actual)"])
    
    if not daily_df.empty:
        fig = go.Figure()
        
        if "Volume" in chart_view:
            # Overlapping SaaS Style (Blue/Green)
            fig.add_trace(go.Scatter(x=daily_df['CleanDate'], y=daily_df[PROD_COL], mode='lines', line_shape='spline', name='Production', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=daily_df['CleanDate'], y=daily_df[CONS_COL], mode='lines', line_shape='spline', name='Consumption', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        else:
            # LPCD Chart
            daily_df['lpcd_plot'] = (daily_df[CONS_COL] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=daily_df['CleanDate'], y=daily_df['lpcd_plot'], mode='lines', line_shape='spline', name='Actual LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.1)'))
            fig.add_trace(go.Scatter(x=daily_df['CleanDate'], y=[target_lpcd]*len(daily_df), name="WHO Target", line=dict(color="red", dash='dash')))

        # Highlight the Selected Date from the Calendar
        if p_val > 0:
            y_mark = c_val if "Volume" in chart_view else lpcd
            fig.add_trace(go.Scatter(x=[selected_op_date], y=[y_mark], mode='markers+text', name="Selected", text=[f"{selected_op_date}"], textposition="top center", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, xaxis=dict(showgrid=False), margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    # THE PROFESSIONAL GAUGE
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range':[0, 100]}, 'bar': {'color': "#1B263B", 'thickness': 0.2},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range':[50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# --- 6. DATA DOWNLOAD CENTER ---
st.divider()
st.subheader("📥 Data Download Center")
if raw_data:
    sel_sheet = st.selectbox("Select Log for Download", list(raw_data.keys()))
    df_dl = pd.DataFrame(raw_data[sel_sheet])
    c1, c2 = st.columns(2)
    c1.download_button("💾 Download CSV", df_dl.to_csv(index=False), f"{sel_sheet}.csv")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df_dl.to_excel(writer, index=False)
    c2.download_button("📂 Download Excel", buf.getvalue(), f"{sel_sheet}.xlsx")
