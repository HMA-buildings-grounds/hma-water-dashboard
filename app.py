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

# --- 2. SIDEBAR: OPERATIONAL CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
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

# --- 3. THE "CROSS-MONTH" CALCULATION ENGINE ---
raw_data = fetch_live_data()

def process_hma_system(raw_json):
    all_rows = []
    # 1. Combine all sheets into one long timeline
    for sheet_name in sorted(raw_json.keys()): # Sort ensures Feb comes before Mar
        df = pd.DataFrame(raw_json[sheet_name])
        if df.empty: continue
        
        # Identify columns
        d_col = next((c for c in df.columns if "Date" in c), None)
        t_col = next((c for c in df.columns if "Time" in c), None)
        m_col = next((c for c in df.columns if "Meter Reading" in c), None)
        
        if d_col and t_col and m_col:
            df = df[[d_col, t_col, m_col]].copy()
            df.columns = ['Date', 'Time', 'Reading']
            # Fix dates to 2026
            df['Date'] = df['Date'].apply(lambda x: pd.to_datetime(f"{str(x).strip()} 2026", errors='coerce'))
            df['Reading'] = pd.to_numeric(df['Reading'], errors='coerce')
            all_rows.append(df.dropna())

    if not all_rows: return pd.DataFrame()
    
    full_df = pd.concat(all_rows).sort_values(['Date', 'Time']).reset_index(drop=True)
    
    # 2. Perform Subtractions (Even across sheets)
    # Overnight = 8AM Reading - Previous Day 4PM Reading
    # Daytime = 4PM Reading - Same Day 8AM Reading
    full_df['Usage'] = full_df['Reading'].diff()
    
    # 3. Pivot to Day-Level View
    results = []
    for date, group in full_df.groupby(full_df['Date'].dt.date):
        day_data = {'Date': date}
        # 8 AM Row usually holds Overnight Usage
        overnight = group[group['Time'].str.contains('8:00', na=False)]
        # 4 PM Row usually holds Daytime Usage
        daytime = group[group['Time'].str.contains('4:00', na=False)]
        
        day_data['Overnight'] = overnight['Usage'].values[0] if not overnight.empty else 0
        day_data['Daytime'] = daytime['Usage'].values[0] if not daytime.empty else 0
        day_data['Total_24h'] = day_data['Overnight'] + day_data['Daytime']
        results.append(day_data)
        
    return pd.DataFrame(results)

master_df = process_hma_system(raw_data)

# --- 4. DATA MATCHING ---
ov_val, dt_val, total_val, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master_df.empty:
    target_dt = selected_op_date
    match = master_df[master_df['Date'] == target_dt]
    
    if not match.empty:
        row = match.iloc[0]
        ov_val, dt_val, total_val = row['Overnight'], row['Daytime'], row['Total_24h']
        lpcd = (total_val * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# --- 5. UI VIEW ---
st.title("Operational Diagnostics & Performance")

# KPI Top Row (The Three Divisions)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Use", f"{ov_val:.1f} m³", "8:00 AM Reading")
c2.metric("Daytime Use", f"{dt_val:.1f} m³", "4:00 PM Reading")
c3.metric("Total 24h Production", f"{total_val:.1f} m³", help=f"Sum: {ov_val} + {dt_val}")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse")

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    chart_view = st.selectbox("Select Trend View", ["Overlapping Usage (Day vs Night)", "Total LPCD Index", "Efficiency Trend"])
    
    L_BLUE, D_NAVY, L_GREEN = "#85C1E9", "#1B263B", "#82E0AA"

    if not master_df.empty:
        fig = go.Figure()
        
        if "Overlapping" in chart_view:
            # SaaS Style Overlapping Green/Blue Charts
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime'], mode='lines', line_shape='spline', name='Daytime Use', line=dict(width=4, color=L_BLUE), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight'], mode='lines', line_shape='spline', name='Overnight Use', line=dict(width=4, color=L_GREEN), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        
        elif "LPCD" in chart_view:
            master_df['lpcd_plot'] = (master_df['Total_24h'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_plot'], mode='lines', line_shape='spline', name='Daily LPCD', line=dict(width=4, color=D_NAVY), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.1)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=[target_lpcd]*len(master_df), name="WHO Target", line=dict(color="red", dash='dash')))

        # Highlight Selected Point
        if total_val > 0:
            y_val = total_val if "LPCD" not in chart_view else (total_val*1000/campus_pop)
            fig.add_trace(go.Scatter(x=[selected_op_date], y=[y_val], mode='markers', name="Selected Day", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, xaxis=dict(showgrid=False), margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# Data Logs
st.divider()
st.subheader("📥 Data Logs")
st.dataframe(master_df, use_container_width=True)
