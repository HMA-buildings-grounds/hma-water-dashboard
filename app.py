import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & CSS FIXES ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide")

# CSS: Fixed the white-on-white input boxes and enhanced the sidebar layout
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    /* Sidebar Background */[data-testid="stSidebar"] { background-color: #1B263B !important; }
    /* Sidebar Text Elements */
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, 
    [data-testid="stSidebar"] p,[data-testid="stSidebar"] label { color: white !important; }
    /* Reset Input Boxes to be readable (Dark text on White background) */
    [data-testid="stSidebar"] input { color: #1B263B !important; background-color: white !important; border-radius: 5px; }
    /* KPI Metrics Styling */
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 34px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=2)
def get_data():
    try:
        return requests.get(st.secrets["google_sheets"]["api_url"]).json()
    except: return {}

# --- 2. SIDEBAR ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.markdown("<h2 style='text-align:center; color:white;'>HMA WATER</h2>", unsafe_allow_html=True)
        
    st.markdown("### Operational Controls")
    pop = st.number_input("Campus Population", value=250, min_value=1)
    target = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    sel_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    
    # REPLICATED STANDARDS & REFERENCES UI (From your screenshot)
    st.markdown("""
        <div style="margin-top: -10px;">
            <h3 style="color: white; font-size: 18px; margin-bottom: 15px;">📖 Standards & References</h3>
            <ul style="list-style-type: none; padding-left: 0; line-height: 2.2;">
                <li><a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color: white; text-decoration: underline; font-size: 15px;">• WHO Water Standards</a></li>
                <li><a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color: white; text-decoration: underline; font-size: 15px;">• Sphere Handbook Ch.6</a></li>
            </ul>
        </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE "RAW READING" ENGINE ---
raw_json = get_data()
readings =[]

for sheet_name, rows in raw_json.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    # Extract Year
    year_match = re.search(r'20\d{2}', sheet_name)
    year = year_match.group(0) if year_match else "2026"
    
    df.columns = [str(c).strip() for c in df.columns]
    
    for _, row in df.iterrows():
        try:
            d_val = str(row.iloc[0]).strip() # Date
            t_val = str(row.iloc[1]).strip() # Time
            m_val = str(row.iloc[2]).strip() # Reading
            
            if not d_val or d_val.lower() == 'nan': continue
            
            # Extract numbers from Reading cell
            m_num = float(re.search(r"[-+]?\d*\.\d+|\d+", m_val).group())
            
            # Form standard Timestamp
            d_str = f"{d_val} {year} {t_val}" if not re.search(r'20\d{2}', d_val) else f"{d_val} {t_val}"
            ts = pd.to_datetime(d_str)
            
            is_morning = True if 'AM' in t_val.upper() or '8:' in t_val else False
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
        daily_data.append({
            'Date': pd.to_datetime(d), 
            'Daytime': dt_usage, 
            'Overnight': ov_usage, 
            'Total': dt_usage + ov_usage
        })
    master = pd.DataFrame(daily_data)
else:
    master = pd.DataFrame()

# --- 4. MATCHING LOGIC ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0

if not master.empty:
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
    st.warning(f"⚠️ No meter reading calculations generated for {sel_date.strftime('%B %d, %Y')}.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³", help="Calculated from the 8:00 AM reading.")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³", help="Calculated from the 4:00 PM reading.")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³", help="Total production (Daytime + Overnight).")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd-target:.1f} vs Target", delta_color="inverse", help=f"({tot_v} m³ × 1000) ÷ {pop} pop")

st.divider()

l_col, r_col = st.columns([2.2, 0.8])

with l_col:
    view = st.selectbox("Select 24h Trend View",["Usage Analysis (Day vs Night)", "Total LPCD Index", "System Efficiency Trend"])
    
    if not master.empty:
        fig = go.Figure()
        
        if "Usage" in view:
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Daytime'], mode='lines', line_shape='spline', name='Daytime Use', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=master['Overnight'], mode='lines', line_shape='spline', name='Overnight Use', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        elif "LPCD" in view:
            master['lpcd_p'] = (master['Total'] * 1000) / pop
            fig.add_trace(go.Scatter(x=master['Date'], y=master['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master['Date'], y=[target]*len(master), name="Baseline Target", line=dict(color="red", dash='dash', width=2)))
        else:
            master['eff_p'] = (target / ((master['Total'] * 1000) / pop) * 100).clip(upper=100).fillna(0)
            fig.add_trace(go.Scatter(x=master['Date'], y=master['eff_p'], mode='lines', line_shape='spline', name='Efficiency %', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))

        if tot_v > 0:
            y_val = dt_v if "Usage" in view else (lpcd if "LPCD" in view else eff)
            fig.add_trace(go.Scatter(x=[pd.to_datetime(sel_date)], y=[y_val], mode='markers+text', name="Selected Date", text=[f"{sel_date.strftime('%b %d')}"], textposition="top center", marker=dict(color='#1B263B', size=16, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
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

# --- 6. DEVELOPER LOG & EXPORTS ---
st.divider()

# Developer Transparency Log (As Requested)
with st.expander("🛠️ View Calculated Background Math (Engineering Verification)"):
    if not master.empty:
        # Format date strictly to YYYY-MM-DD to remove the 00:00:00 output
        display_master = master.copy()
        display_master['Date'] = pd.to_datetime(display_master['Date']).dt.strftime('%Y-%m-%d')
        st.dataframe(display_master, use_container_width=True)
    else:
        st.info("No data calculated yet.")

st.subheader("📥 Data Download Center")
if raw_data:
    sel = st.selectbox("Select Log for Download", list(raw_data.keys()))
    df_dl = pd.DataFrame(raw_data[sel])
    c1, c2 = st.columns(2)
    c1.download_button("💾 Download CSV", df_dl.to_csv(index=False), f"{sel}.csv")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df_dl.to_excel(writer, index=False)
    c2.download_button("📂 Download Excel", buf.getvalue(), f"{sel}.xlsx")
