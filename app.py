import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & CSS FIXES ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

# CSS: Fixed white-on-white inputs, Sidebar styling, and Metric cards
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    /* Sidebar Background & Text */
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown,[data-testid="stSidebar"] label, [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h3 { color: white !important; }
    /* Fix Input Boxes (Dark text on white background) */
    [data-testid="stSidebar"] input { color: #1B263B !important; background-color: white !important; border-radius: 5px; }
    /* KPI Metrics Styling */[data-testid="stMetricValue"] { color: #1B263B; font-size: 38px; font-weight: 800; }
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
    selected_op_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("""<div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
        <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
        <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
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
    
    # Safely find the Year for this sheet
    year_match = re.search(r'20\d{2}', sheet_name)
    year = year_match.group(0) if year_match else "2026"
    
    df.columns =[str(c).strip() for c in df.columns]
    
    # Identify columns by their position/index (0, 1, 2) to ignore naming errors
    try:
        for _, row in df.iterrows():
            d_val = str(row.iloc[0]).strip()
            t_val = str(row.iloc[1]).strip()
            m_val = str(row.iloc[2]).strip()
            
            if not d_val or d_val.lower() == 'nan': continue
            if not m_val or not any(c.isdigit() for c in m_val): continue
            
            # Extract only the raw digits from the Meter Reading column
            m_num = float(re.search(r"[-+]?\d*\.\d+|\d+", m_val).group())
            
            # Create a perfect continuous timestamp
            d_str = f"{d_val} {year} {t_val}" if not re.search(r'20\d{2}', d_val) else f"{d_val} {t_val}"
            ts = pd.to_datetime(d_str, errors='coerce')
            
            if pd.notnull(ts):
                # Identify if this is the 8 AM (Morning) or 4 PM (Afternoon) reading
                is_morning = True if 'AM' in t_val.upper() or '8:' in t_val else False
                readings.append({'Timestamp': ts, 'DateOnly': ts.date(), 'IsMorning': is_morning, 'Reading': m_num})
    except: continue

if readings:
    # Sort all readings chronologically
    df_readings = pd.DataFrame(readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
    
    # THE MATH: Subtract current reading from previous reading
    df_readings['Usage'] = df_readings['Reading'].diff().fillna(0)
    df_readings.loc[df_readings['Usage'] < 0, 'Usage'] = 0 # Ignore negative resets
    
    # Group into 24-Hour daily totals
    daily_data =[]
    for d, g in df_readings.groupby('DateOnly'):
        dt_usage = g[~g['IsMorning']]['Usage'].sum() # Afternoon row holds Daytime Usage
        ov_usage = g[g['IsMorning']]['Usage'].sum()  # Morning row holds Overnight Usage
        
        daily_data.append({
            'Date': pd.to_datetime(d), 
            'Overnight': ov_usage, 
            'Daytime': dt_usage, 
            'Total': dt_usage + ov_usage
        })
    master = pd.DataFrame(daily_data)
else:
    master = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

# --- 4. MATCHING THE CALENDAR ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0

if not master.empty:
    # Match the calendar date accurately
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
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³", help="Total well production for this 24-hour period.")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target_lpcd:.1f} vs Target", delta_color="inverse", help=f"({tot_v} m³ × 1000) ÷ {campus_pop} pop")

st.divider()

l_col, r_col = st.columns([2.2, 0.8])

with l_col:
    view = st.selectbox("Select 24h Trend View",["Usage Analysis (Day vs Night)", "Total LPCD Index", "Efficiency Trend"])
    
    if not master.empty:
        fig = go.Figure()
        
        if "Usage" in view:
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], mode='lines', line_shape='spline', name='Daytime Use', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], mode='lines', line_shape='spline', name='Overnight Use', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        
        elif "LPCD" in view:
            master['lpcd_p'] = (master['Total'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=[target_lpcd]*len(master), name="Baseline Target", line=dict(color="red", dash='dash')))
        
        else: # Efficiency
            master['eff_p'] = (target_lpcd / ((master['Total'] * 1000) / campus_pop) * 100).clip(upper=100).fillna(0)
            fig.add_trace(go.Scatter(x=master['Date'], y=master['eff_p'], mode='lines', line_shape='spline', name='Efficiency %', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))

        # Highlight Selected Date Point
        if tot_v > 0:
            y_val = dt_v if "Usage" in view else (lpcd if "LPCD" in view else eff)
            fig.add_trace(go.Scatter(x=[pd.to_datetime(selected_op_date)], y=[y_val], mode='markers+text', name="Selected Date", text=[f"{selected_op_date.strftime('%b %d')}"], textposition="top center", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    # RESTORED PROFESSIONAL PASTEL GAUGE
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {
            'axis': {'range':[0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "#1B263B", 'thickness': 0.25},
            'bgcolor': "white",
            'borderwidth': 1,
            'bordercolor': "#e2e8f0",
            'steps': [
                {'range': [0, 50], 'color': "#FADBD8"},  # Soft Red
                {'range': [50, 85], 'color': "#FCF3CF"}, # Soft Yellow
                {'range': [85, 100], 'color': "#D5F5E3"} # Soft Green
            ]
        }))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
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

# THE DEVELOPER TRANSPARENCY LOG (No 00:00:00)
with st.expander("🛠️ View Calculated Background Math (Engineering Verification)"):
    if not master.empty:
        display_master = master.copy()
        # Formats the date cleanly
        display_master['Date'] = display_master['Date'].dt.strftime('%Y-%m-%d')
        st.dataframe(display_master, use_container_width=True)
    else:
        st.info("No data calculated yet.")
