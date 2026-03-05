import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & CSS FIXES ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] * { color: white !important; }
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

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.markdown("<h2 style='text-align:center; color:#1ABB9C;'>HMA WATER</h2>", unsafe_allow_html=True)
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    sel_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("""
        <div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
            <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
            <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
        </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE "RAW READING" ENGINE (Simplified for Stability) ---
raw_data = fetch_live_data()
readings =[]
master = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

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
            
            if not d_val or d_val.lower() in ['nan', 'date', '']: continue
            if not m_val or not any(c.isdigit() for c in m_val): continue
            
            m_num = float(re.search(r"[-+]?\d*\.\d+|\d+", m_val).group())
            
            d_str = f"{d_val} {year} {t_val}" if not re.search(r'20\d{2}', d_val) else f"{d_val} {t_val}"
            ts = pd.to_datetime(d_str, errors='coerce')
            
            if pd.notnull(ts):
                is_morning = '8:00' in t_val or 'AM' in t_val.upper()
                readings.append({'Timestamp': ts, 'DateOnly': ts.date(), 'IsMorning': is_morning, 'Reading': m_num})
    except: continue

if readings:
    df_readings = pd.DataFrame(readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
    df_readings['Usage'] = df_readings['Reading'].diff().fillna(0)
    df_readings.loc[df_readings['Usage'] < 0, 'Usage'] = 0 
    
    daily_data =[]
    for d, g in df_readings.groupby('DateOnly'):
        dt_usage = g[~g['IsMorning']]['Usage'].sum()
        ov_usage = g[g['IsMorning']]['Usage'].sum()
        daily_data.append({'Date': pd.to_datetime(d), 'Overnight': ov_usage, 'Daytime': dt_usage, 'Total': dt_usage + ov_usage})
    master = pd.DataFrame(daily_data)
else:
    master = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

# --- 4. MATCHING THE CALENDAR ---
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
c1.metric("Overnight Usage", f"{ov_v:.1f} m³")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target_lpcd:.1f} vs Target")

st.divider()

l_col, r_col = st.columns([2.2, 0.8])

with l_col:
    view = st.selectbox("Select 24h Trend View",["Usage Analysis (Day vs Night)", "Total LPCD Index", "Efficiency Trend"])
    
    if not master.empty:
        fig = go.Figure()
        
        # --- CHART STYLING ---
        if "Usage" in view:
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], mode='lines', line_shape='spline', name='Daytime Use', line=dict(width=3, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], mode='lines', line_shape='spline', name='Overnight Use', line=dict(width=3, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        elif "LPCD" in view:
            master['lpcd_p'] = (master['Total'] * 1000) / pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=3, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=[target_lpcd]*len(master), name="Baseline Target", line=dict(color="red", dash='dash', width=2)))
        else: # Efficiency
            master['eff_p'] = (target_lpcd / ((master['Total'] * 1000) / pop) * 100).clip(upper=100).fillna(0)
            fig.add_trace(go.Scatter(x=master['Date'], y=master['eff_p'], mode='lines', line_shape='spline', name='Efficiency %', line=dict(width=3, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))

        # Highlight Selected Date Point
        if tot_v > 0:
            y_val = dt_v if "Usage" in view else (lpcd if "LPCD" in view else eff)
            fig.add_trace(go.Scatter(x=[pd.to_datetime(sel_date)], y=[y_val], mode='markers+text', name="Selected Day", text=[f"{sel_date.strftime('%b %d')}"], textposition="top center", marker=dict(color='orange', size=12, line=dict(width=2, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    # PROFESSIONAL GAUGE
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {
            'axis': {'range':[0, 100], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': "rgba(0,0,0,0)"}, # Hides the ugly default bar
            'bgcolor': "white",
            'borderwidth': 1,
            'bordercolor': "#e2e8f0",
            'steps':[
                {'range': [0, 50], 'color': "#E74C3C"},   # Red
                {'range': [50, 85], 'color': "#F39C12"},  # Yellow
                {'range': [85, 100], 'color': "#1ABB9C"} # Mint Green
            ],
            'threshold': {
                'line': {'color': "#2A3F54", 'width': 8}, # Thick Dark Needle
                'thickness': 0.85, 
                'value': eff
            }
        }))
    fig_gauge.update_layout(height=380, margin=dict(l=20, r=20, t=30, b=10))
    st.plotly_chart(fig_gauge, use_container_width=True)

# --- 6. DOWNLOADS & VERIFICATION ---
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

with st.expander("🛠️ View Calculated Background Math (Engineering Verification)"):
    if not master.empty:
        display_master = master.copy()
        display_master['Date'] = display_master['Date'].dt.strftime('%Y-%m-%d')
        st.dataframe(display_master, use_container_width=True)
    else:
        st.info("No calculated data available.")
