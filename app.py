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
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }[data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 36px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=2)
def fetch_live_data():
    try:
        return requests.get(st.secrets["google_sheets"]["api_url"]).json()
    except:
        return {}

# --- 2. SIDEBAR: CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.markdown("<h2 style='text-align:center; color:white;'>💧 HMA WATER</h2>", unsafe_allow_html=True)
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=250, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    
    # Select Date
    selected_op_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("• <a href='https://www.who.int/publications/i/item/9789241549950' target='_blank' style='color:#85C1E9;'>WHO Water Standards</a>", unsafe_allow_html=True)
    st.markdown("• <a href='https://handbook.spherestandards.org/en/sphere/#ch006' target='_blank' style='color:#85C1E9;'>Sphere Handbook Ch.6</a>", unsafe_allow_html=True)

    st.divider()
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE PURE MATH ENGINE ---
raw_data = fetch_live_data()
all_readings =[]

for sheet_name, rows in raw_data.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    # Safely find the Year from the Sheet Name
    year_match = re.search(r'20\d{2}', sheet_name)
    sheet_year = year_match.group(0) if year_match else "2026"
    
    df.columns =[str(c).strip().lower() for c in df.columns]
    
    # Find columns by checking headers
    d_col = next((c for c in df.columns if 'date' == c), None)
    t_col = next((c for c in df.columns if 'time' == c and 'period' not in c), None)
    r_col = next((c for c in df.columns if 'meter reading' in c), None)
    
    if d_col and t_col and r_col:
        for _, row in df.iterrows():
            d_val = str(row[d_col]).strip()
            t_val = str(row[t_col]).strip()
            r_val = str(row[r_col]).strip()
            
            if d_val and t_val and r_val and r_val.lower() != 'nan':
                # Extract the pure number from the reading
                r_match = re.search(r"[-+]?\d*\.\d+|\d+", r_val)
                if r_match:
                    r_num = float(r_match.group())
                    # Build exact Date string
                    ts_str = f"{d_val} {sheet_year} {t_val}"
                    ts = pd.to_datetime(ts_str, errors='coerce')
                    
                    if pd.notnull(ts):
                        all_readings.append({'Timestamp': ts, 'Date': ts.date(), 'Time': t_val, 'Reading': r_num})

if all_readings:
    # 1. Sort history perfectly chronologically
    history = pd.DataFrame(all_readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
    
    # 2. Subtract Current Reading from Previous Reading
    history['Usage'] = history['Reading'].diff().fillna(0)
    
    # 3. SPIKE PROTECTION: If usage jumps by >1000 (missing months), ignore it
    history.loc[(history['Usage'] < 0) | (history['Usage'] > 1000), 'Usage'] = 0
    
    # 4. Group by Day
    daily_stats =[]
    for dt_date, grp in history.groupby('Date'):
        ov = grp[grp['Time'].str.contains('8', na=False)]['Usage'].sum()
        dt = grp[grp['Time'].str.contains('4', na=False)]['Usage'].sum()
        daily_stats.append({
            'Date': pd.to_datetime(dt_date),
            'Overnight': ov,
            'Daytime': dt,
            'Total': ov + dt
        })
    master_df = pd.DataFrame(daily_stats)
else:
    master_df = pd.DataFrame()

# --- 4. MATCH THE CALENDAR DATE ---
ov_val, dt_val, tot_val, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
target_dt = pd.to_datetime(selected_op_date)

if not master_df.empty:
    match = master_df[master_df['Date'] == target_dt]
    if not match.empty:
        res = match.iloc[0]
        ov_val, dt_val, tot_val = res['Overnight'], res['Daytime'], res['Total']
        lpcd = (tot_val * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# --- 5. UI DASHBOARD ---
st.title("Operational Diagnostics & Performance")

if tot_val == 0 and not master_df.empty:
    st.warning(f"⚠️ No usage recorded for {selected_op_date.strftime('%B %d, %Y')}. Displaying 0.0.")

# Top KPIs
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_val:.1f} m³", "8:00 AM Reading")
c2.metric("Daytime Usage", f"{dt_val:.1f} m³", "4:00 PM Reading")
c3.metric("Total 24h Usage", f"{tot_val:.1f} m³", help="Total Volume for selected day.")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse", help=f"({tot_val} m³ × 1000) ÷ {campus_pop} pop")

st.divider()

col_L, col_R = st.columns([2.2, 0.8])

with col_L:
    # Restored Advanced Dropdown
    view = st.selectbox("Select Trend View", ["Usage Analysis (Day vs Night)", "Total LPCD Index"])
    
    if not master_df.empty:
        fig = go.Figure()
        
        if "Usage" in view:
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        else:
            master_df['lpcd_p'] = (master_df['Total'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_p'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=[target_lpcd]*len(master_df), name="Baseline Target", line=dict(color="red", dash='dash')))

        # Highlight Selected Date on Chart
        if tot_val > 0:
            y_focus = dt_val if "Usage" in view else lpcd
            fig.add_trace(go.Scatter(x=[target_dt], y=[y_focus], mode='markers+text', name="Selected", text=[f"{selected_op_date.strftime('%b %d')}"], textposition="top center", marker=dict(color='orange', size=15, line=dict(width=2, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with col_R:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range':[85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# Data Download Center
st.divider()
st.subheader("📥 Data Download Center")
if raw_data:
    sel = st.selectbox("Select Raw Log for Download", list(raw_data.keys()))
    df_dl = pd.DataFrame(raw_data[sel])
    c_csv, c_xls = st.columns(2)
    c_csv.download_button("💾 Download Selected Month (CSV)", df_dl.to_csv(index=False), f"{sel}.csv")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df_dl.to_excel(writer, index=False)
    c_xls.download_button("📂 Download Selected Month (Excel)", buf.getvalue(), f"{sel}.xlsx")

# Developer Transparency Log (so you can see the math worked)
with st.expander("🛠️ View Calculated Background Math (Engineering Verification)"):
    st.dataframe(master_df)
