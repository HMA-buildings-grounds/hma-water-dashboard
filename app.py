import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import re
import io
from datetime import datetime

# ==========================================
# 1. PAGE CONFIG & PRO-BI STYLING
# ==========================================
st.set_page_config(page_title="HMA Water BI Dashboard", layout="wide", page_icon="💧")

# Branding Colors
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#27ae60"
ALERT_RED = "#e74c3c"

# Responsive CSS for Pro-BI Look
st.markdown(f"""
    <style>
    .main {{ background-color: #f4f7f9; }}
    [data-testid="stMetricValue"] {{ font-size: calc(1.5rem + 1vw) !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    .stMetric {{ background-color: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-bottom: 5px solid {HMA_GOLD}; }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-family: 'Segoe UI', sans-serif; }}
    .sidebar .sidebar-content {{ background-color: white; }}
    @media (max-width: 600px) {{ [data-testid="stMetricValue"] {{ font-size: 24px !important; }} }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. MULTI-SHEET DATA ENGINE (OCT - MARCH)
# ==========================================
@st.cache_data(ttl=600)
def load_all_sheets():
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit#gid=1207984195"
    
    # 1. Get all sheet names (Worksheets)
    # Using a workaround to read all tabs
    all_dfs = []
    
    # List of months to crawl
    months = ["Sep 2025", "Oct 2025", "Nov 2025", "Dec 2025", "Jan 2026", "Feb 2026", "Mar 2026"]
    
    for month in months:
        try:
            # Construct sheet name as it appears in your tabs
            sheet_name = f"Water Usage Log ({month})"
            df_raw = conn.read(spreadsheet=url, worksheet=sheet_name, header=None)
            
            # Find the row containing "Date"
            header_row_idx = 0
            for i, row in df_raw.iterrows():
                if 'Date' in [str(v).strip() for v in row.values]:
                    header_row_idx = i
                    break
            
            df = df_raw.iloc[header_row_idx+1:].copy()
            headers = [str(h).strip() for h in df_raw.iloc[header_row_idx].values]
            
            # Fix Duplicate Headers
            clean_headers = []
            for i, h in enumerate(headers):
                val = h if h != 'None' and h != '' else f"Col_{i}"
                clean_headers.append(val)
            df.columns = clean_headers

            # Year extraction for date parsing
            year = "2026" if "2026" in month else "2025"
            
            def parse_date(x):
                try:
                    d = str(x).strip()
                    if not d or d == 'None': return pd.NaT
                    return pd.to_datetime(f"{d} {year}", errors='coerce')
                except: return pd.NaT

            df['Full_Date'] = df['Date'].apply(parse_date)
            df = df.dropna(subset=['Full_Date', 'Time'])

            # Numeric Cleaning
            def clean_num(x):
                try:
                    if isinstance(x, str): return float(re.split(r'\(|\s', x)[0])
                    return float(x)
                except: return 0.0

            usage_col = next((c for c in df.columns if "Usage Since" in c), None)
            booster_col = next((c for c in df.columns if "Booster" in c), None)

            df['Production'] = df[usage_col].apply(clean_num) if usage_col else 0.0
            df['Booster_Reading'] = pd.to_numeric(df[booster_col], errors='coerce').fillna(0.0)
            
            all_dfs.append(df[['Full_Date', 'Production', 'Booster_Reading']])
        except:
            continue # If sheet doesn't exist yet, skip

    if not all_dfs:
        return pd.DataFrame()

    master_df = pd.concat(all_dfs, ignore_index=True)
    daily = master_df.groupby('Full_Date').agg({'Production':'sum', 'Booster_Reading':'max'}).reset_index()
    daily['Distribution'] = daily['Booster_Reading'].diff().fillna(0.0)
    
    # Hardware/Logic Filter for Backwards readings
    daily.loc[daily['Distribution'] < 0, 'Distribution'] = 0
    daily['Rolling_Avg'] = daily['Production'].rolling(window=7, min_periods=1).mean()
    
    return daily.sort_values('Full_Date')

try:
    df_master = load_all_sheets()
except Exception as e:
    st.error(f"BI Engine Error: {e}"); st.stop()

# ==========================================
# 3. SIDEBAR (LOGO, WHO, CONTROLS)
# ==========================================
with st.sidebar:
    # Official HMA Logo
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown("<h3 style='text-align: center; color: #0f233a;'>HMA BI Systems</h3>", unsafe_allow_html=True)
    st.markdown("---")
    
    st.header("🎛️ CONTROLS")
    pop = st.number_input("Campus Population", value=370, step=10)
    savings_target = st.slider("Goal Target (%)", 0, 50, 10)
    
    st.markdown("---")
    st.header("📚 STANDARDS")
    st.markdown(f"""
    <div style="border-left: 5px solid {ALERT_RED}; padding-left: 15px; background-color: #fff5f5; padding: 15px; border-radius: 0 10px 10px 0;">
        <p style="color: {ALERT_RED}; font-weight: 800; margin-bottom: 5px; font-size: 16px;">WHO GUIDELINES</p>
        <p style="font-size: 13px; color: #444;">Ref: Table 5.1, Page 87<br><b>Baseline: 100L / Person / Day</b></p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    selected_date = st.selectbox("📅 Analysis Date", sorted(df_master['Full_Date'].dt.date.unique(), reverse=True))

# ==========================================
# 4. MAIN DASHBOARD (BI ANALYTICS)
# ==========================================
st.title("🌊 WATER INFRASTRUCTURE BI DASHBOARD")
st.markdown(f"**HAILE-MANAS ACADEMY** | BUILDINGS & GROUNDS | {datetime.now().strftime('%B %d, %Y')}")

# Metrics Calculations
day_data = df_master[df_master['Full_Date'].dt.date == selected_date].iloc[0]
prod = day_data['Production']
cons = day_data['Distribution']
lpcd = (cons * 1000) / pop if cons > 0 else 0
eff = (cons / prod * 100) if prod > 0 and cons > 0 else 0
loss = prod - cons if prod > cons else 0

# KPI ROW
k1, k2, k3 = st.columns(3)
with k1:
    st.metric("WHO Standard (LPCD)", f"{lpcd:.0f} L", f"{lpcd-100:.1f} vs WHO", delta_color="inverse")
with k2:
    st.metric("Infrastructure Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Loss", delta_color="inverse")
with k3:
    st.metric("Daily Well Extraction", f"{prod:.1f} m³", f"Goal: -{savings_target}%")

# CHARTS ROW
c_trend, c_gauge = st.columns([2, 1])

with c_trend:
    st.subheader("📈 Annual Production Trend vs Goal")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Production'], name='Actual',
                               line=dict(color=NAVY_BLUE, width=3), fill='tozeroy', fillcolor='rgba(15, 35, 58, 0.05)'))
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg']*(1-savings_target/100), 
                               name='Target', line=dict(color=SUCCESS_GREEN, width=2, dash='dot')))
    fig_t.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0), height=400, template="plotly_white", margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig_t, use_container_width=True)

with c_gauge:
    st.subheader("🎯 Recovery Success")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff,
        number={'suffix': "%", 'font': {'size': 60, 'color': NAVY_BLUE}},
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE},
               'steps': [{'range': [0, 70], 'color': "#fadbd8"},
                         {'range': [70, 90], 'color': "#fcf3cf"},
                         {'range': [90, 100], 'color': "#d4efdf"}]}))
    fig_g.update_layout(height=350, margin=dict(t=50, b=0))
    st.plotly_chart(fig_g, use_container_width=True)

# BAR CHART
st.subheader("📊 Full Dataset Distribution Balance (m³)")
fig_b = px.bar(df_master, x='Full_Date', y=['Production', 'Distribution'], 
             barmode='group', color_discrete_map={'Production': '#cfd8dc', 'Distribution': NAVY_BLUE})
fig_b.update_layout(height=400, template="plotly_white", legend=dict(orientation="h", y=1.1, x=0), margin=dict(l=0,r=0,t=20,b=0))
st.plotly_chart(fig_b, use_container_width=True)

# ==========================================
# 5. EXPORT SYSTEM (EXCEL & CSV)
# ==========================================
st.markdown("---")
st.subheader("📥 Infrastructure Data Export")
col_csv, col_xlsx = st.columns(2)

# CSV
csv_data = df_master.to_csv(index=False).encode('utf-8')
col_csv.download_button("Download CSV Dataset", data=csv_data, file_name=f"HMA_Water_Report_{selected_date}.csv", mime='text/csv', use_container_width=True)

# Excel (Now Fixed)
output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_master.to_excel(writer, index=False, sheet_name='Master_Data')
col_xlsx.download_button("Download Excel Report", data=output.getvalue(), file_name=f"HMA_Water_Full_Report.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)

st.caption(f"System Status: Online | Last Refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
