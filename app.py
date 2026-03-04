import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
import io
from datetime import datetime

# ==========================================
# 1. THEME & EXECUTIVE STYLING
# ==========================================
st.set_page_config(
    page_title="HMA Water Infrastructure BI", 
    layout="wide", 
    page_icon="💧",
    initial_sidebar_state="expanded"
)

# Institutional Branding
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#0f9d58"
ALERT_RED = "#d93025"
LIGHT_GRAY = "#f8f9fa"

# Custom CSS for "Power BI" Card Look
st.markdown(f"""
    <style>
    .main {{ background-color: {LIGHT_GRAY}; }}
    [data-testid="stMetric"] {{
        background-color: white;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-top: 5px solid {HMA_GOLD};
    }}
    [data-testid="stMetricValue"] {{ font-size: 2.2rem !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    [data-testid="stMetricLabel"] {{ font-size: 0.9rem !important; font-weight: 700 !important; color: #5f6368; text-transform: uppercase; }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-family: 'Segoe UI', sans-serif; font-weight: 800; }}
    .stSidebar {{ background-color: white; border-right: 1px solid #e0e0e0; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. PRO-GRADE DATA ENGINE
# ==========================================
@st.cache_data(ttl=300)
def load_hma_data():
    # Direct CSV Export for maximum stability
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    # 1. Read & Header Detection
    df_raw = pd.read_csv(url, header=None)
    header_idx = 0
    for i, row in df_raw.iterrows():
        if 'Date' in [str(v).strip() for v in row.values if pd.notnull(v)]:
            header_idx = i
            break
    df = pd.read_csv(url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]

    # 2. Ported Colab Filters (8:00 AM / 4:00 PM)
    if 'Time' in df.columns:
        df = df[df['Time'].isin(['8:00 AM', '4:00 PM'])].copy()

    # 3. Numeric Sanitization
    def clean_num(val):
        try: 
            # Removes comments like "(2.5)" or commas
            s = str(val).strip()
            if not s or s == 'nan': return np.nan
            return float(re.split(r'\(|\s', s)[0].replace(',', ''))
        except: return np.nan

    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    meter_col = next((c for c in df.columns if "Meter Reading" in c or "Booster" in c), None)

    df['Well_Usage_m3'] = df[usage_col].apply(clean_num) if usage_col else 0
    df['Meter_Raw'] = df[meter_col].apply(clean_num) if meter_col else 0

    # 4. Ported Year Logic (2025 vs 2026)
    def parse_hma_date(d_str):
        try:
            d = str(d_str).strip()
            # Months Jan-Apr are treated as 2026 based on HMA log cycle
            yr = "2026" if any(m in d for m in ["Jan", "Feb", "Mar", "Apr"]) else "2025"
            return pd.to_datetime(f"{d} {yr}", errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(parse_hma_date)
    df = df.dropna(subset=['Full_Date'])

    # 5. Aggregation & Rolling Averages
    daily = df.groupby('Full_Date').agg({
        'Well_Usage_m3':'sum', 
        'Meter_Raw':'max'
    }).reset_index().sort_values('Full_Date')

    # 6. Verified Distribution Logic (Feb 5th Cutoff)
    daily['Verified_Dist_m3'] = daily['Meter_Raw'].diff()
    install_date = pd.Timestamp("2026-02-05")
    daily.loc[daily['Full_Date'] < install_date, 'Verified_Dist_m3'] = np.nan
    
    # Clean anomalies (Meter resets/leaks)
    daily.loc[daily['Verified_Dist_m3'] < 0, 'Verified_Dist_m3'] = 0
    daily['Rolling_Avg_30d'] = daily['Well_Usage_m3'].rolling(window=30, min_periods=1).mean()
    
    return daily

# Try loading data with error reporting
try:
    df_master = load_hma_data()
except Exception as e:
    st.error("🚨 DATA FORMAT ERROR")
    st.info(f"Technical Details: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR NAVIGATION
# ==========================================
with st.sidebar:
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.header("🎛️ CONTROLS")
    pop = st.number_input("Population", value=260, step=10)
    goal_target = st.slider("Goal Target (%)", 0, 30, 10)
    
    st.markdown("---")
    st.header("📚 STANDARDS")
    st.markdown(f"""
    <div style="border-left: 4px solid {ALERT_RED}; padding: 10px; background: #fffafa;">
        <p style="color:{ALERT_RED}; font-weight:bold; margin-bottom:2px;">WHO GUIDELINES</p>
        <small>Ref: Table 5.1, Page 87<br><b>Baseline: 100L / Person</b></small>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    dates = sorted(df_master['Full_Date'].dt.date.unique(), reverse=True)
    sel_date = st.selectbox("📅 SELECT DATE", dates)

# ==========================================
# 4. DASHBOARD MAIN INTERFACE
# ==========================================
st.title("🌊 WATER INFRASTRUCTURE DASHBOARD")
st.markdown(f"**HAILE-MANAS ACADEMY** | STATUS: <span style='color:{SUCCESS_GREEN}'>● LIVE</span> | DATA AS OF: **{sel_date}**", unsafe_allow_html=True)

# Metric Calculations
day_data = df_master[df_master['Full_Date'].dt.date == sel_date].iloc[0]
prod = day_data['Well_Usage_m3']
dist = day_data['Verified_Dist_m3'] if not pd.isna(day_data['Verified_Dist_m3']) else 0
lpcd = (dist * 1000) / pop if dist > 0 else 0
eff = (dist / prod * 100) if prod > 0 else 0
target_vol = day_data['Rolling_Avg_30d'] * (1 - goal_target/100)
variance = prod - target_vol

# --- ROW 1: KPIs ---
k1, k2, k3 = st.columns(3)
with k1:
    st.metric("WHO Standard (LPCD)", f"{lpcd:.0f} L", f"{lpcd-100:+.1f} vs Target", delta_color="inverse")
with k2:
    loss = prod - dist if prod > dist else 0
    st.metric("Infrastructure Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Daily Loss", delta_color="inverse")
with k3:
    st.metric(f"Conservation Goal (-{goal_target}%)", f"{prod:.1f} m³", f"{variance:+.1f} vs Target", delta_color="inverse")

st.markdown("<br>", unsafe_allow_html=True)

# --- ROW 2: TREND & GAUGE ---
c_trend, c_gauge = st.columns([2, 1])

with c_trend:
    st.subheader("📈 Production Trend vs. Goal")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Well_Usage_m3'], name='Actual',
                               line=dict(color=NAVY_BLUE, width=3), fill='tozeroy', fillcolor='rgba(15, 35, 58, 0.05)'))
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg_30d']*(1-goal_target/100), 
                               name='Target Goal', line=dict(color=SUCCESS_GREEN, width=2, dash='dash')))
    fig_t.update_layout(height=400, template="plotly_white", margin=dict(l=0,r=0,t=0,b=0), legend=dict(orientation="h", y=1.1, x=0))
    st.plotly_chart(fig_t, use_container_width=True)

with c_gauge:
    st.subheader("🎯 Recovery Score")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff,
        number={'suffix': "%", 'font': {'color': NAVY_BLUE}},
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE},
               'steps': [{'range': [0, 70], 'color': "#fadbd8"},
                         {'range': [70, 90], 'color': "#fcf3cf"},
                         {'range': [90, 100], 'color': "#d4efdf"}]}))
    fig_g.update_layout(height=350, margin=dict(t=50, b=0, l=20, r=20))
    st.plotly_chart(fig_g, use_container_width=True)

# --- ROW 3: DISTRIBUTION BALANCE ---
st.subheader("📊 Daily Distribution Balance (Verified)")
fig_b = go.Figure()
fig_b.add_trace(go.Bar(x=df_master['Full_Date'], y=df_master['Well_Usage_m3'], name='Total Well Production', marker_color='#cfd8dc'))
fig_b.add_trace(go.Bar(x=df_master['Full_Date'], y=df_master['Verified_Dist_m3'], name='Verified Distribution', marker_color=NAVY_BLUE))

# Event Annotation: Meter Installation
install_ts = datetime(2026, 2, 5).timestamp() * 1000
fig_b.add_vline(x=install_ts, line_width=2, line_dash="dot", line_color=HMA_GOLD)
fig_b.add_annotation(x=install_ts, y=prod*1.2, text="Digital Meter Installed", showarrow=False, font=dict(color=HMA_GOLD, weight='bold'))

fig_b.update_layout(barmode='overlay', height=350, template="plotly_white", margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", y=1.1, x=0))
st.plotly_chart(fig_b, use_container_width=True)

# ==========================================
# 5. DATA EXPORT HUB
# ==========================================
st.markdown("---")
st.subheader("📥 Management Reporting Hub")
d1, d2 = st.columns(2)

# CSV
csv_data = df_master.to_csv(index=False).encode('utf-8')
d1.download_button("📥 DOWNLOAD DATA AS CSV", csv_data, f"HMA_Water_Log_{sel_date}.csv", use_container_width=True)

# Excel
output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_master.to_excel(writer, index=False, sheet_name='Water_BI_Data')
d2.download_button("📥 DOWNLOAD DATA AS EXCEL", output.getvalue(), f"HMA_Master_Log_{sel_date}.xlsx", use_container_width=True)

st.caption(f"BI System v5.2 | Last Sync: {datetime.now().strftime('%H:%M:%S')}")
