import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime, timedelta

# --- 1. SETTINGS & BRANDING ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 32px; font-weight: 800; }
    .stMetric { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=2)
def get_raw_data():
    try:
        return requests.get(st.secrets["google_sheets"]["api_url"]).json()
    except: return {}

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    st.markdown("### Operational Controls")
    pop = st.number_input("Campus Population", value=250)
    target = st.number_input("Baseline Target (LPCD)", value=50)
    sel_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("📖 [WHO Standards](https://www.who.int) | [Sphere Handbook](https://spherestandards.org)")
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE CALCULATION ENGINE (8AM & 4PM LOGIC) ---
raw_json = get_raw_data()
all_data = []

# Combine all sheets and fix dates
for sheet in raw_json.values():
    df = pd.DataFrame(sheet)
    if not df.empty:
        df.columns = [str(c).strip() for c in df.columns]
        d_col = next((c for c in df.columns if "Date" in c), None)
        t_col = next((c for c in df.columns if "Time" in c), None)
        r_col = next((c for c in df.columns if "Meter Reading" in c), None)
        if d_col and t_col and r_col:
            df = df[[d_col, t_col, r_col]].copy()
            df.columns = ['D', 'T', 'R']
            # Convert "Mar 1" to real date
            df['DT'] = pd.to_datetime(df['D'].astype(str) + " 2026 " + df['T'].astype(str), errors='coerce')
            all_data.append(df.dropna())

if all_data:
    full = pd.concat(all_data).sort_values('DT').drop_duplicates('DT').reset_index(drop=True)
    full['Usage'] = full['R'].diff() # This is the magic subtraction
    
    # Organize into 24-hr buckets
    daily_stats = []
    for d, g in full.groupby(full['DT'].dt.date):
        # Overnight = Delta at 8AM row | Daytime = Delta at 4PM row
        ov = g[g['T'].str.contains('8:00', na=False)]['Usage'].sum()
        dt = g[g['T'].str.contains('4:00', na=False)]['Usage'].sum()
        daily_stats.append({'Date': d, 'Overnight': ov, 'Daytime': dt, 'Total': ov+dt})
    
    master = pd.DataFrame(daily_stats)
else:
    master = pd.DataFrame()

# --- 4. DISPLAY LOGIC ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master.empty:
    row = master[master['Date'] == sel_date]
    if not row.empty:
        ov_v, dt_v, tot_v = row.iloc[0]['Overnight'], row.iloc[0]['Daytime'], row.iloc[0]['Total']
        lpcd = (tot_v * 1000) / pop
        eff = (target / lpcd * 100) if lpcd > 0 else 0

# --- 5. UI LAYOUT ---
st.title("Operational Diagnostics & Performance")

# KPI Row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³", help="Today 8AM Reading - Yesterday 4PM Reading")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³", help="Today 4PM Reading - Today 8AM Reading")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³", help="The aggregate of Daytime and Overnight usage.")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target:.1f} vs Target", delta_color="inverse", help=f"({tot_v}m³ * 1000) / {pop} pop")

st.divider()

col_left, col_right = st.columns([2.2, 0.8])

with col_left:
    view = st.selectbox("Select View", ["Usage Analysis (Day vs Night)", "LPCD Trend", "Efficiency Trend"])
    fig = go.Figure()
    
    if "Usage" in view:
        # SMOOTH GREEN/BLUE OVERLAPPING AREA CHART
        fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
        fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
    elif "LPCD" in view:
        master['lpcd_p'] = (master['Total'] * 1000) / pop
        fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], mode='lines', line_shape='spline', name='LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
    
    # Highlight Selected Date
    if tot_v > 0:
        fig.add_trace(go.Scatter(x=[sel_date], y=[dt_v if "Usage" in view else (tot_v*1000/pop)], mode='markers', name="Selected", marker=dict(color='orange', size=15, line=dict(width=2, color='white'))))
    
    fig.update_layout(template="plotly_white", height=450, margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# EXPORTS
st.divider()
st.subheader("📥 Download Center")
if not master.empty:
    c_csv, c_xls = st.columns(2)
    c_csv.download_button("💾 Download Data as CSV", master.to_csv(index=False), "HMA_Water_Data.csv")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        master.to_excel(writer, index=False)
    c_xls.download_button("📂 Download Data as Excel", buffer.getvalue(), "HMA_Water_Data.xlsx")
