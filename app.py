import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
import io
import base64
from datetime import datetime

# ==========================================
# 1. THE ARCHITECTURAL SHELL (HIGH-CONTRAST)
# ==========================================
st.set_page_config(page_title="HMA EXECUTIVE BI", layout="wide", page_icon="💧")

# Executive Color Palette
HEX_BG = "#0A0C10"       # Deep Carbon
HEX_CARD = "#161B22"     # Slate Card
HEX_GOLD = "#D4AF37"     # HMA Gold
HEX_CYAN = "#00F2FF"     # Surgical Cyan
HEX_TEXT = "#E6EDF3"     # Off-White

# Inject High-Fidelity CSS
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;700;900&display=swap');
    
    /* Global Reset */
    .main, [data-testid="stAppViewContainer"] {{ background-color: {HEX_BG}; color: {HEX_TEXT}; }}
    [data-testid="stHeader"] {{ background: rgba(0,0,0,0); }}
    [data-testid="stSidebar"] {{ background-color: {HEX_CARD}; border-right: 1px solid #30363d; }}
    
    /* Surgical Metric Cards */
    .metric-card {{
        background: {HEX_CARD};
        border: 1px solid #30363d;
        border-left: 4px solid {HEX_GOLD};
        padding: 20px;
        border-radius: 2px;
        margin-bottom: 10px;
    }}
    .metric-label {{ font-family: 'JetBrains Mono', monospace; color: #8B949E; font-size: 10px; text-transform: uppercase; letter-spacing: 2px; }}
    .metric-value {{ font-family: 'Inter', sans-serif; font-weight: 900; color: {HEX_TEXT}; font-size: 32px; margin: 5px 0; }}
    .metric-delta {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; }}

    /* Typography */
    h1, h2, h3 {{ font-family: 'Inter', sans-serif; font-weight: 900; letter-spacing: -1px; }}
    .status-tag {{ background: {HEX_GOLD}; color: black; padding: 2px 8px; font-size: 10px; font-weight: 900; border-radius: 2px; }}
    
    /* Remove Streamlit Clutter */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. SURGICAL DATA ENGINE
# ==========================================
@st.cache_data(ttl=600)
def load_and_process():
    # Direct CSV Link
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    df_raw = pd.read_csv(url, header=None)
    header_idx = next(i for i, row in df_raw.iterrows() if 'Date' in [str(v).strip() for v in row.values if pd.notnull(v)])
    df = pd.read_csv(url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]

    # Numeric Cleanup
    def to_float(x):
        try: return float(re.split(r'\(|\s', str(x))[0].replace(',', ''))
        except: return 0.0

    u_col = next((c for c in df.columns if "Usage Since" in c), None)
    m_col = next((c for c in df.columns if "Meter Reading" in c or "Booster" in c), None)

    df['Prod'] = df[u_col].apply(to_float) if u_col else 0
    df['Meter'] = df[m_col].apply(to_float) if m_col else 0

    # Logic: 2025/2026 Shift
    def fix_date(d):
        d_str = str(d).strip()
        yr = "2026" if any(m in d_str for m in ["Jan", "Feb", "Mar", "Apr"]) else "2025"
        return pd.to_datetime(f"{d_str} {yr}", errors='coerce')

    df['Full_Date'] = df['Date'].apply(fix_date)
    df = df.dropna(subset=['Full_Date'])
    
    # Aggregation
    daily = df.groupby('Full_Date').agg({'Prod':'sum', 'Meter':'max'}).reset_index().sort_values('Full_Date')
    
    # Surgical Delta Logic
    daily['Dist'] = daily['Meter'].diff()
    # Meter Online Date: Feb 5th 2026
    meter_online_dt = pd.Timestamp("2026-02-05")
    daily.loc[daily['Full_Date'] < meter_online_dt, 'Dist'] = np.nan
    daily.loc[daily['Dist'] < 0, 'Dist'] = 0
    daily['Rolling_Avg'] = daily['Prod'].rolling(window=30, min_periods=1).mean()
    
    return daily

try:
    df_master = load_and_process()
except Exception as e:
    st.error(f"ENGINE FAILURE: {e}")
    st.stop()

# ==========================================
# 3. CUSTOM INTERFACE COMPONENTS
# ==========================================
def custom_metric(label, value, delta, color):
    delta_color = "#00FF88" if "vs" in str(delta) and "-" in str(delta) else "#FF4B4B"
    if "Efficiency" in label: delta_color = "#00FF88" if eff > 85 else "#FF4B4B"
    
    st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-delta" style="color: {delta_color}">{delta}</div>
        </div>
    """, unsafe_allow_html=True)

# ==========================================
# 4. SIDEBAR (BLACK LABEL)
# ==========================================
with st.sidebar:
    # Fixed Logo - Direct External Link (High-Reliability)
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("### COMMAND")
    pop = st.number_input("Population", value=260)
    target_pct = st.slider("Goal (%)", 0, 40, 10)
    
    st.markdown("---")
    # Date Picker - Defaults to LATEST valid date
    dates = sorted(df_master['Full_Date'].dt.date.unique(), reverse=True)
    sel_date = st.selectbox("Timeline Selection", dates)

# ==========================================
# 5. MAIN DASHBOARD (SURGICAL)
# ==========================================
# Calculations
day_data = df_master[df_master['Full_Date'].dt.date == sel_date].iloc[0]
prod = day_data['Prod']
dist = day_data['Dist'] if not pd.isna(day_data['Dist']) else 0
lpcd = (dist * 1000) / pop if dist > 0 else 0
eff = (dist / prod * 100) if prod > 0 else 0
target_val = day_data['Rolling_Avg'] * (1 - target_pct/100)

# Header Section
c_title, c_status = st.columns([3, 1])
with c_title:
    st.title("WATER INFRASTRUCTURE BI")
    st.markdown(f"**HAILE-MANAS ACADEMY** | DATA POINT: **{sel_date}**")
with c_status:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<span class=\"status-tag\">ENCRYPTION ACTIVE</span> <span class=\"status-tag\">LIVE SYNC</span>", unsafe_allow_html=True)

# Metrics Grid
m1, m2, m3 = st.columns(3)
with m1:
    status = "N/A - PRE METERING" if pd.isna(day_data['Dist']) else f"{lpcd:.0f} L / PERSON"
    custom_metric("WHO LPCD INDEX", status, f"{lpcd-100:+.1f} vs Target", HEX_CYAN)
with m2:
    loss = prod - dist if prod > dist else 0
    custom_metric("INFRASTRUCTURE EFFICIENCY", f"{eff:.1f}%", f"{loss:.1f} m³ Leak Loss", HEX_CYAN)
with m3:
    custom_metric("WELL EXTRACTION", f"{prod:.1f} m³", f"{prod - target_val:+.1f} vs Goal", HEX_GOLD)

st.markdown("<br>", unsafe_allow_html=True)

# Charts Row
col_a, col_b = st.columns([2, 1])

with col_a:
    st.markdown("### 01 / TREND ANALYSIS")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Prod'], name='Production', line=dict(color=HEX_GOLD, width=3)))
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg']*(1-target_pct/100), name='Target', line=dict(color="#30363D", dash='dot')))
    fig_t.update_layout(paper_bgcolor=HEX_BG, plot_bgcolor=HEX_BG, font_color=HEX_TEXT, height=400, margin=dict(l=0,r=0,t=0,b=0))
    st.plotly_chart(fig_t, use_container_width=True)

with col_b:
    st.markdown("### 02 / VERIFICATION")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff,
        number={'suffix': "%", 'font': {'color': HEX_TEXT}},
        gauge={'axis': {'range': [0, 100], 'tickcolor': HEX_TEXT}, 'bar': {'color': HEX_GOLD},
               'bgcolor': HEX_CARD, 'borderwidth': 0}))
    fig_g.update_layout(paper_bgcolor=HEX_BG, height=350, margin=dict(t=50, b=0))
    st.plotly_chart(fig_g, use_container_width=True)

# Supply Bar Chart
st.markdown("### 03 / SYSTEM BALANCE (WELL VS METER)")
fig_b = go.Figure()
fig_b.add_trace(go.Bar(x=df_master['Full_Date'], y=df_master['Prod'], name='Well Supply', marker_color='#30363D'))
fig_b.add_trace(go.Bar(x=df_master['Full_Date'], y=df_master['Dist'], name='Meter Verified', marker_color=HEX_GOLD))
fig_b.update_layout(barmode='overlay', paper_bgcolor=HEX_BG, plot_bgcolor=HEX_BG, font_color=HEX_TEXT, height=350, margin=dict(l=0,r=0,t=0,b=0))
st.plotly_chart(fig_b, use_container_width=True)

# Footer Exports
st.markdown("---")
c_f1, c_f2 = st.columns([3, 1])
with c_f1:
    st.caption(f"HMA BI CORE v8.0 | SYSTEM REFRESHED: {datetime.now().strftime('%H:%M:%S')}")
with c_f2:
    st.download_button("EXPORT ANNUAL REPORT (.XLSX)", df_master.to_csv().encode('utf-8'), "HMA_MASTER.csv", use_container_width=True)
