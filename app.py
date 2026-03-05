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
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 32px; font-weight: 800; }
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

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=250, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    selected_date = st.date_input("Operational Date", value=datetime(2025, 12, 12))
    
    st.divider()
    st.markdown("### 📖 Standards\n• [WHO Standards](https://www.who.int)\n• [Sphere Handbook](https://spherestandards.org)")
    
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE CALCULATION ENGINE ---
raw_data = fetch_live_data()

def calculate_hma_metrics(data_dict):
    all_readings = []
    for sheet_name, rows in data_dict.items():
        df = pd.DataFrame(rows)
        if df.empty: continue
        
        # Determine Year
        year_match = re.search(r'20\d{2}', sheet_name)
        yr = year_match.group(0) if year_match else "2026"
        
        # Clean columns
        df.columns = [str(c).strip() for c in df.columns]
        d_col = next((c for c in df.columns if "Date" in c), None)
        t_col = next((c for c in df.columns if "Time" in c), None)
        r_col = next((c for c in df.columns if "Meter Reading" in c), None)
        
        if all([d_col, t_col, r_col]):
            df = df[[d_col, t_col, r_col]].copy()
            df.columns = ['D', 'T', 'Reading']
            df['TS'] = pd.to_datetime(df['D'].astype(str) + " " + yr + " " + df['T'].astype(str), errors='coerce')
            df['Reading'] = pd.to_numeric(df['Reading'], errors='coerce')
            all_readings.append(df.dropna())

    if not all_readings: return pd.DataFrame()

    # 1. Sort all readings globally (Feb flows into Mar)
    full = pd.concat(all_readings).sort_values('TS').drop_duplicates('TS').reset_index(drop=True)
    
    # 2. Difference between readings
    full['Delta'] = full['Reading'].diff()
    
    # 3. Aggregate to Daily
    daily_stats = []
    full['DateOnly'] = full['TS'].dt.date
    for d, g in full.groupby('DateOnly'):
        ov = g[g['T'].astype(str).str.contains('8:00', na=False)]['Delta'].sum()
        dt = g[g['T'].astype(str).str.contains('4:00', na=False)]['Delta'].sum()
        daily_stats.append({'Date': d, 'Overnight': ov, 'Daytime': dt, 'Total': ov+dt})
        
    return pd.DataFrame(daily_stats)

master_df = calculate_hma_metrics(raw_data)

# --- 4. KPI MATCHING ---
ov, dt, tot, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master_df.empty:
    match = master_df[master_df['Date'] == selected_date]
    if not match.empty:
        row = match.iloc[0]
        ov, dt, tot = row['Overnight'], row['Daytime'], row['Total']
        lpcd = (tot * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# Tooltips
ov_h = "Formula: (Today 8:00 AM Reading) - (Yesterday 4:00 PM Reading)"
dt_h = "Formula: (Today 4:00 PM Reading) - (Today 8:00 AM Reading)"
tot_h = f"Formula: Overnight [{ov}] + Daytime [{dt}] = {tot} m³"
lpcd_h = f"Formula: ({tot} m³ × 1000) / {campus_pop} pop = {lpcd:.1f} LPCD"

# --- 5. UI DISPLAY ---
st.title("Operational Diagnostics & Performance")

if tot == 0:
    st.warning(f"No readings found for {selected_date}. Select a date from your log.")

# Top KPIs
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov:.1f} m³", help=ov_h)
c2.metric("Daytime Usage", f"{dt:.1f} m³", help=dt_h)
c3.metric("Total 24hr Usage", f"{tot:.1f} m³", help=tot_h)
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target_lpcd:.1f} vs Target", delta_color="inverse", help=lpcd_h)

st.divider()

# Charts
v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    chart_view = st.selectbox("Select Performance Trend", 
                              ["Day vs Night Usage (Overlapping)", "Daily LPCD Index (24h)", "Efficiency Status Trend"])
    
    if not master_df.empty:
        fig = go.Figure()
        if "Overlapping" in chart_view:
            # SaaS Smooth Green Style
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        
        elif "LPCD" in chart_view:
            master_df['lpcd_p'] = (master_df['Total'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=[target_lpcd]*len(master_df), name="Baseline", line=dict(color="red", dash='dash')))

        # Highlight Selected Date
        if tot > 0:
            y_val = dt if "Overlapping" in chart_view else (tot*1000/campus_pop)
            fig.add_trace(go.Scatter(x=[selected_date], y=[y_val], mode='markers', name="Focus", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

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

# Calculation Log for Transparency
st.divider()
st.subheader("📋 Final Calculation Log")
st.dataframe(master_df, use_container_width=True)
