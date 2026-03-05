import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & CSS FIXES ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

# CSS: Professional SaaS Theme
st.markdown("""
    <style>
    .main { background-color: #F7F7F7; } /* Gentelella Light Gray Background */
    /* Sidebar Background & Text */
    [data-testid="stSidebar"] { background-color: #2A3F54 !important; } /* Gentelella Dark Navy */
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h3 { color: #ECF0F1 !important; }
    /* Fix Input Boxes */[data-testid="stSidebar"] input { color: #2A3F54 !important; background-color: white !important; border-radius: 4px; border: none; }
    /* KPI Metrics Styling */[data-testid="stMetricValue"] { color: #2A3F54; font-size: 38px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-top: 4px solid #1ABB9C; } /* Teal Top Border */
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
        st.markdown("<h2 style='text-align:center; color:#1ABB9C;'>HMA WATER</h2>", unsafe_allow_html=True)
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    selected_op_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    
    # REPLICATED STANDARDS & REFERENCES UI
    st.markdown("""
        <div style="margin-top: -10px;">
            <h3 style="color: #ECF0F1; font-size: 18px; margin-bottom: 15px;">📖 Standards & References</h3>
            <ul style="list-style-type: none; padding-left: 0; line-height: 2.2;">
                <li><a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color: #1ABB9C; text-decoration: none; font-weight: 500;">■ WHO Water Standards</a></li>
                <li><a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color: #1ABB9C; text-decoration: none; font-weight: 500;">🌍 Sphere Handbook Ch.6</a></li>
            </ul>
        </div>
    """, unsafe_allow_html=True)

    st.divider()
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE "RAW READING" ENGINE ---
raw_data = fetch_live_data()
readings =[]

for sheet_name, rows in raw_data.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    year_match = re.search(r'20\d{2}', sheet_name)
    year = year_match.group(0) if year_match else "2026"
    
    df.columns =[str(c).strip() for c in df.columns]
    
    try:
        for _, row in df.iterrows():
            d_val = str(row.iloc[0]).strip()
            t_val = str(row.iloc[1]).strip()
            m_val = str(row.iloc[2]).strip()
            
            if not d_val or d_val.lower() == 'nan': continue
            if not m_val or not any(c.isdigit() for c in m_val): continue
            
            m_num = float(re.search(r"[-+]?\d*\.\d+|\d+", m_val).group())
            
            d_str = f"{d_val} {year} {t_val}" if not re.search(r'20\d{2}', d_val) else f"{d_val} {t_val}"
            ts = pd.to_datetime(d_str, errors='coerce')
            
            if pd.notnull(ts):
                is_morning = True if 'AM' in t_val.upper() or '8:' in t_val else False
                readings.append({'Timestamp': ts, 'DateOnly': ts.date(), 'IsMorning': is_morning, 'Reading': m_num})
    except: continue

if readings:
    df_readings = pd.DataFrame(readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
    df_readings['Usage'] = df_readings['Reading'].diff().fillna(0)
    
    # Clean anomalies (Ignore negative resets or crazy typos over 5000)
    df_readings.loc[(df_readings['Usage'] < 0) | (df_readings['Usage'] > 5000), 'Usage'] = 0 
    
    daily_data =[]
    for d, g in df_readings.groupby('DateOnly'):
        dt_usage = g[~g['IsMorning']]['Usage'].sum()
        ov_usage = g[g['IsMorning']]['Usage'].sum()
        daily_data.append({'Date': pd.to_datetime(d), 'Overnight': ov_usage, 'Daytime': dt_usage, 'Total': dt_usage + ov_usage})
    master = pd.DataFrame(daily_data)
else:
    master = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

# --- 4. MATCHING LOGIC ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0

if not master.empty:
    match = master[master['Date'].dt.date == selected_op_date]
    if not match.empty:
        ov_v = match.iloc[0]['Overnight']
        dt_v = match.iloc[0]['Daytime']
        tot_v = match.iloc[0]['Total']
        lpcd = (tot_v * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# --- 5. DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")

if tot_v == 0 and not master.empty:
    st.warning(f"⚠️ No meter reading data calculated for {selected_op_date.strftime('%B %d, %Y')}.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³", help="Calculated from the 8:00 AM reading.")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³", help="Calculated from the 4:00 PM reading.")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³", help="Total production (Daytime + Overnight).")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target_lpcd:.1f} vs Target", delta_color="inverse", help=f"({tot_v} m³ × 1000) ÷ {campus_pop} pop")

st.divider()

l_col, r_col = st.columns([2.5, 1])

with l_col:
    view = st.selectbox("Select 24h Trend View",["Usage Analysis (Day vs Night)", "Total LPCD Index", "System Efficiency Trend"])
    
    if not master.empty:
        fig = go.Figure()
        
        # GENTELELLA PROFESSIONAL COLOR PALETTE
        TEAL_MAIN = "#1ABB9C"
        TEAL_LIGHT = "rgba(26, 187, 156, 0.3)"
        NAVY_MAIN = "#34495E"
        NAVY_LIGHT = "rgba(52, 73, 94, 0.3)"

        if "Usage" in view:
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], mode='lines', line_shape='spline', name='Daytime Use', line=dict(width=3, color=TEAL_MAIN), fill='tozeroy', fillcolor=TEAL_LIGHT))
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], mode='lines', line_shape='spline', name='Overnight Use', line=dict(width=3, color=NAVY_MAIN), fill='tozeroy', fillcolor=NAVY_LIGHT))
        
        elif "LPCD" in view:
            master['lpcd_p'] = (master['Total'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=3, color=TEAL_MAIN), fill='tozeroy', fillcolor=TEAL_LIGHT))
            fig.add_trace(go.Scatter(x=master['Date'], y=[target_lpcd]*len(master), name="Baseline Target", line=dict(color="#E74C3C", dash='dash', width=2)))
        
        else: # Efficiency
            master['eff_p'] = (target_lpcd / ((master['Total'] * 1000) / campus_pop) * 100).clip(upper=100).fillna(0)
            fig.add_trace(go.Scatter(x=master['Date'], y=master['eff_p'], mode='lines', line_shape='spline', name='Efficiency %', line=dict(width=3, color=TEAL_MAIN), fill='tozeroy', fillcolor=TEAL_LIGHT))

        # Highlight Selected Date Point
        if tot_v > 0:
            y_val = dt_v if "Usage" in view else (lpcd if "LPCD" in view else eff)
            fig.add_trace(go.Scatter(x=[pd.to_datetime(selected_op_date)], y=[y_val], mode='markers+text', name="Selected Date", text=[f"{selected_op_date.strftime('%b %d')}"], textposition="top center", marker=dict(color='#E74C3C', size=12, line=dict(width=2, color='white'))))

        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=420,
            margin=dict(l=0, r=0, t=20, b=0),
            xaxis=dict(showgrid=True, gridcolor='#F0F0F0', zeroline=False),
            yaxis=dict(showgrid=True, gridcolor='#F0F0F0', zeroline=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    # 💥 THE "SMART GATEWAYS" PROFESSIONAL SOLID GAUGE 💥
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", 
        value = eff,
        number = {'suffix': "%", 'font': {'size': 45, 'color': '#2A3F54'}},
        gauge = {
            'axis': {'range':[0, 100], 'tickwidth': 2, 'tickcolor': "white"},
            'bar': {'color': "rgba(0,0,0,0)"}, # Hide the standard curve
            'bgcolor': "white",
            'borderwidth': 0,
            'steps': [
                {'range': [0, 50], 'color': "#E74C3C"},   # Solid Red
                {'range': [50, 85], 'color': "#F39C12"},  # Solid Orange/Yellow
                {'range':[85, 100], 'color': "#1ABB9C"}  # Solid Mint Green
            ],
            'threshold': {
                'line': {'color': "#2A3F54", 'width': 8}, # Thick Black Needle
                'thickness': 0.85, # Length of needle
                'value': eff
            }
        }))
    fig_gauge.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=10))
    st.plotly_chart(fig_gauge, use_container_width=True)

# --- 6. DATA EXPORTS & VERIFICATION ---
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

# THE DEVELOPER TRANSPARENCY LOG
with st.expander("🛠️ View Calculated Background Math (Engineering Verification)"):
    if not master.empty:
        display_master = master.copy()
        display_master['Date'] = pd.to_datetime(display_master['Date']).dt.strftime('%Y-%m-%d')
        st.dataframe(display_master, use_container_width=True)
    else:
        st.info("No data calculated yet.")
