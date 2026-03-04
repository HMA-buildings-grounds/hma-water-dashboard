import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import datetime
import re
import io

# ==========================================
# 1. PAGE CONFIG & PRO-BI STYLING
# ==========================================
st.set_page_config(page_title="HMA Water BI Dashboard", layout="wide", page_icon="💧")

# Institutional Branding Colors
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#27ae60"
ALERT_RED = "#e74c3c"
BACKGROUND_COLOR = "#f4f7f9"

# Professional CSS for Large Fonts and Cards
st.markdown(f"""
    <style>
    .main {{ background-color: {BACKGROUND_COLOR}; }}
    [data-testid="stMetricValue"] {{ font-size: 40px !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    [data-testid="stMetricLabel"] {{ font-size: 18px !important; font-weight: 600 !important; color: #5f6368; }}
    .stMetric {{ background-color: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-bottom: 5px solid {HMA_GOLD}; }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-family: 'Segoe UI', sans-serif; }}
    .sidebar .sidebar-content {{ background-color: white; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA ENGINE (ROBUST & MARCH-READY)
# ==========================================
@st.cache_data(ttl=600)
def load_hma_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit#gid=1207984195"
    df_raw = conn.read(spreadsheet=url, header=None)
    
    # Find the header row (the one containing "Date")
    header_row_idx = 0
    for i, row in df_raw.iterrows():
        if 'Date' in [str(v).strip() for v in row.values]:
            header_row_idx = i
            break
            
    df = df_raw.iloc[header_row_idx+1:].copy()
    headers = [str(h).strip() for h in df_raw.iloc[header_row_idx].values]
    
    # Fix Duplicate Headers (The cause of the error)
    clean_headers = []
    counts = {}
    for h in headers:
        name = h if h != 'None' and h != '' else "Column"
        if name in counts:
            counts[name] += 1
            clean_headers.append(f"{name}_{counts[name]}")
        else:
            counts[name] = 1
            clean_headers.append(name)
    df.columns = clean_headers

    # Robust Date Parsing for 2026 (Supports March)
    def parse_date(x):
        try:
            d_str = str(x).strip()
            if not d_str or d_str == 'None': return pd.NaT
            # Attempt to parse (e.g., "Feb 1" to "Feb 1 2026")
            return pd.to_datetime(d_str + " 2026", errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(parse_date)
    df = df.dropna(subset=['Full_Date'])

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

    # Daily aggregation
    daily = df.groupby('Full_Date').agg({'Production':'sum', 'Booster_Reading':'max'}).reset_index()
    daily['Distribution'] = daily['Booster_Reading'].diff().fillna(0.0)
    
    # Meter install filter (Feb 5, 2026)
    install_date = pd.Timestamp("2026-02-05")
    daily.loc[daily['Full_Date'] < install_date, 'Distribution'] = np.nan
    
    daily['Rolling_Avg'] = daily['Production'].rolling(window=7, min_periods=1).mean()
    return daily.sort_values('Full_Date')

# Load data
try:
    df_master = load_hma_data()
except Exception as e:
    st.error(f"BI Engine Error: {e}"); st.stop()

# ==========================================
# 3. SIDEBAR (LOGO & CONTROLS)
# ==========================================
with st.sidebar:
    # HMA Logo
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown("---")
    st.header("🎛️ CONTROLS")
    pop = st.number_input("Campus Population", value=370, step=10)
    savings_target = st.slider("Goal Target (%)", 0, 50, 10)
    
    st.markdown("---")
    st.header("📚 STANDARDS")
    st.markdown(f"""
    <div style="border-left: 5px solid {ALERT_RED}; padding-left: 15px; background-color: #fff5f5; padding-top: 10px; padding-bottom: 10px; border-radius: 0 10px 10px 0;">
        <p style="color: {ALERT_RED}; font-weight: 800; margin-bottom: 5px; font-size: 16px;">WHO GUIDELINES</p>
        <p style="font-size: 13px; color: #444; line-height: 1.4;">Ref: Table 5.1, Page 87<br><b>Baseline: 100L / Person / Day</b></p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    selected_date = st.selectbox("📅 Analysis Date", sorted(df_master['Full_Date'].dt.date.unique(), reverse=True))

# ==========================================
# 4. MAIN DASHBOARD UI (BI STYLE)
# ==========================================
st.title("🌊 WATER INFRASTRUCTURE BI DASHBOARD")
st.markdown(f"**HAILE-MANAS ACADEMY** | BUILDINGS & GROUNDS | *Report Status: Live 24/7*")

# Filter for selected date
day_data = df_master[df_master['Full_Date'].dt.date == selected_date].iloc[0]
prod = day_data['Production']
cons = day_data['Distribution'] if pd.notnull(day_data['Distribution']) else 0.0
lpcd = (cons * 1000) / pop if cons > 0 else 0
eff = (cons / prod * 100) if prod > 0 and cons > 0 else 0
loss = prod - cons if cons > 0 else 0

# --- KPI ROW (Bigger Fonts) ---
k1, k2, k3 = st.columns(3)
with k1:
    st.metric("WHO Standard (LPCD)", f"{lpcd:.0f} L", f"{lpcd-100:.1f} vs Target", delta_color="inverse")
with k2:
    st.metric("System Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Daily Loss", delta_color="inverse")
with k3:
    st.metric("Daily Well Production", f"{prod:.1f} m³", f"Goal: -{savings_target}%")

st.markdown("<br>", unsafe_allow_html=True)

# --- CHARTS ROW ---
c_left, c_right = st.columns([2, 1])

with c_left:
    st.subheader("📈 Production Trend vs Conservation Goal")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Production'], name='Actual Production',
                               line=dict(color=NAVY_BLUE, width=4), fill='tozeroy', fillcolor='rgba(15, 35, 58, 0.1)'))
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg']*(1-savings_target/100), 
                               name='Target Goal', line=dict(color=SUCCESS_GREEN, width=3, dash='dot')))
    fig_t.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0), height=450, template="plotly_white")
    st.plotly_chart(fig_t, use_container_width=True)

with c_right:
    st.subheader("🎯 Metering Success")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff,
        number={'suffix': "%", 'font': {'size': 70, 'color': NAVY_BLUE}},
        gauge={'axis': {'range': [0, 100], 'tickwidth': 1}, 'bar': {'color': NAVY_BLUE},
               'steps': [{'range': [0, 70], 'color': "#fadbd8"},
                         {'range': [70, 90], 'color': "#fcf3cf"},
                         {'range': [90, 100], 'color': "#d4efdf"}]}))
    fig_g.update_layout(height=400, margin=dict(t=80, b=0))
    st.plotly_chart(fig_g, use_container_width=True)

# --- DISTRIBUTION BALANCE ---
st.subheader("📊 Daily Distribution Balance (Well vs. Booster)")
fig_b = go.Figure()
fig_b.add_trace(go.Bar(x=df_master['Full_Date'], y=df_master['Production'], name='Well Extraction (m³)', marker_color='#dfe6e9'))
fig_b.add_trace(go.Bar(x=df_master['Full_Date'], y=df_master['Distribution'], name='Booster Distribution (m³)', marker_color=NAVY_BLUE))
fig_b.update_layout(barmode='overlay', height=400, template="plotly_white", legend=dict(orientation="h", y=1.1, x=0))
st.plotly_chart(fig_b, use_container_width=True)

# ==========================================
# 5. DATA EXPORT (DOWNLOAD SECTION)
# ==========================================
st.markdown("---")
st.subheader("📥 Export Infrastructure Data")
col_d1, col_d2, _ = st.columns([1, 1, 2])

# CSV Download
csv = df_master.to_csv(index=False).encode('utf-8')
col_d1.download_button(label="📥 Download as CSV", data=csv, file_name=f'HMA_Water_Data_{selected_date}.csv', mime='text/csv')

# Excel Download
output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_master.to_excel(writer, index=False, sheet_name='Water_Report')
col_d2.download_button(label="📥 Download as Excel", data=output.getvalue(), file_name=f'HMA_Water_Data_{selected_date}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

st.caption(f"Last Refreshed: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | HMA BI Engine v2.0")
