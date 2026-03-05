import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & STYLING ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }[data-testid="stSidebar"] * { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 34px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=2)
def get_data():
    try:
        return requests.get(st.secrets["google_sheets"]["api_url"]).json()
    except: return {}

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.markdown("<h2 style='text-align:center;'>HMA WATER</h2>", unsafe_allow_html=True)
        
    st.markdown("### Operational Controls")
    pop = st.number_input("Campus Population", value=400, min_value=1)
    target = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    sel_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("• [WHO Water Standards](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("•[Sphere Handbook Ch.6](https://handbook.spherestandards.org/en/sphere/#ch006)")
    
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE "RAW READING" ENGINE ---
raw_json = get_data()
readings =[]

for sheet_name, rows in raw_json.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    # 1. Safely find the Year for this sheet
    year_match = re.search(r'20\d{2}', sheet_name)
    year = year_match.group(0) if year_match else "2026"
    
    df.columns =[str(c).strip() for c in df.columns]
    d_col = next((c for c in df.columns if "Date" in c), None)
    t_col = next((c for c in df.columns if "Time" in c), None)
    m_col = next((c for c in df.columns if "Meter Reading" in c), None)
    
    if d_col and t_col and m_col:
        for _, row in df.iterrows():
            d_val = str(row[d_col]).strip()
            t_val = str(row[t_col]).strip()
            m_val = str(row[m_col]).strip()
            
            if not d_val or d_val.lower() == 'nan': continue
            if not m_val or not any(c.isdigit() for c in m_val): continue
            
            # 2. Extract only the raw digits from the Meter Reading column
            try:
                m_num = float(re.search(r"[-+]?\d*\.\d+|\d+", m_val).group())
            except: continue
            
            # 3. Create a perfect continuous timestamp
            d_str = f"{d_val} {year} {t_val}" if not re.search(r'20\d{2}', d_val) else f"{d_val} {t_val}"
            
            try:
                ts = pd.to_datetime(d_str)
                # Identify if this is the 8 AM (Morning) or 4 PM (Afternoon) reading
                is_morning = True if 'AM' in t_val.upper() or '8:' in t_val else False
                readings.append({'TS': ts, 'DateOnly': ts.date(), 'IsMorning': is_morning, 'Reading': m_num})
            except: continue

if readings:
    # Sort all readings from Sep 2025 to Mar 2026 chronologically
    df_readings = pd.DataFrame(readings).sort_values('TS').drop_duplicates('TS').reset_index(drop=True)
    
    # THE MATH: Subtract current reading from previous reading
    df_readings['Usage'] = df_readings['Reading'].diff().fillna(0)
    df_readings.loc[df_readings['Usage'] < 0, 'Usage'] = 0 # Ignore negative resets
    
    # 4. Group into 24-Hour daily totals
    daily_data =[]
    for d, g in df_readings.groupby('DateOnly'):
        dt_usage = g[~g['IsMorning']]['Usage'].sum() # Afternoon row holds Daytime Usage
        ov_usage = g[g['IsMorning']]['Usage'].sum()  # Morning row holds Overnight Usage
        
        daily_data.append({
            'Date': pd.to_datetime(d), 
            'Daytime': dt_usage, 
            'Overnight': ov_usage, 
            'Total': dt_usage + ov_usage
        })
    master = pd.DataFrame(daily_data)
else:
    master = pd.DataFrame()

# --- 4. MATCHING THE CALENDAR ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0

if not master.empty:
    # Match the calendar date accurately
    match = master[master['Date'].dt.date == sel_date]
    if not match.empty:
        ov_v = match.iloc[0]['Overnight']
        dt_v = match.iloc[0]['Daytime']
        tot_v = match.iloc[0]['Total']
        lpcd = (tot_v * 1000) / pop
        eff = (target / lpcd * 100) if lpcd > 0 else 0

# --- 5. DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")

if tot_v == 0 and not master.empty:
    st.warning(f"⚠️ No meter reading data calculated for {sel_date.strftime('%B %d, %Y')}.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³", help="Calculated from the 8:00 AM reading.")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³", help="Calculated from the 4:00 PM reading.")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³", help="Total well production for this 24-hour period.")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target:.1f} vs Target", delta_color="inverse", help=f"({tot_v} m³ × 1000) ÷ {pop} pop")

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
            master['lpcd_p'] = (master['Total'] * 1000) / pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=[target]*len(master), name="Baseline Target", line=dict(color="red", dash='dash')))
        
        else: # Efficiency
            master['eff_p'] = (target / ((master['Total'] * 1000) / pop) * 100).clip(upper=100).fillna(0)
            fig.add_trace(go.Scatter(x=master['Date'], y=master['eff_p'], mode='lines', line_shape='spline', name='Efficiency %', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))

        # Highlight Selected Date Point
        if tot_v > 0:
            y_val = dt_v if "Usage" in view else (lpcd if "LPCD" in view else eff)
            fig.add_trace(go.Scatter(x=[pd.to_datetime(sel_date)], y=[y_val], mode='markers+text', name="Selected Date", text=[f"{sel_date.strftime('%b %d')}"], textposition="top center", marker=dict(color='orange', size=15, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range':[0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range':[0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

st.divider()
st.subheader("📋 Verification Data Log")
st.dataframe(master, use_container_width=True)
