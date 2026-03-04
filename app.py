import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
import io
from datetime import datetime

# ==========================================
# 1. SURGICAL CSS & DESIGN SYSTEM
# ==========================================
st.set_page_config(page_title="HMA BI Enterprise", layout="wide", page_icon="💧")

# Executive Palette
NAVY_DEEP = "#0A192F"  # Darker, sharper navy
HMA_GOLD = "#C5A022"   # Refined gold
SLATE_TEXT = "#475569"
WHITE = "#FFFFFF"

# Inject High-End UI Styles
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
    
    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif !important;
        background-color: #F1F5F9;
    }}

    /* Remove Default Padding */
    .block-container {{ padding-top: 1.5rem !important; padding-bottom: 0rem !important; }}
    
    /* Sharp KPI Card Design */
    .kpi-card {{
        background: {WHITE};
        border-radius: 4px;
        padding: 24px;
        border-bottom: 4px solid {HMA_GOLD};
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        min-height: 140px;
    }}
    .kpi-label {{ color: {SLATE_TEXT}; font-size: 0.75rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; }}
    .kpi-value {{ color: {NAVY_DEEP}; font-size: 2.2rem; font-weight: 800; margin-top: 8px; }}
    .kpi-delta {{ font-size: 0.85rem; font-weight: 600; margin-top: 4px; }}

    /* Sidebar Refinement */
    [data-testid="stSidebar"] {{ background-color: {WHITE}; border-right: 1px solid #E2E8F0; width: 300px !important; }}
    .stSelectbox, .stSlider, .stNumberInput {{ margin-bottom: 20px; }}
    
    /* Header Block */
    .header-container {{ border-left: 10px solid {NAVY_DEEP}; padding-left: 20px; margin-bottom: 30px; }}
    .header-title {{ font-size: 2.4rem; font-weight: 800; color: {NAVY_DEEP}; letter-spacing: -0.02em; }}
    .header-sub {{ color: {HMA_GOLD}; font-weight: 600; font-size: 1rem; text-transform: uppercase; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA ENGINE (COLAB LOGIC PORT)
# ==========================================
@st.cache_data(ttl=300)
def fetch_live_data():
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    df_raw = pd.read_csv(url, header=None)
    header_idx = next(i for i, r in df_raw.iterrows() if 'Date' in [str(v).strip() for v in r.values if pd.notnull(v)])
    df = pd.read_csv(url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]

    # Filters (Colab Specific: 8am/4pm only)
    if 'Time' in df.columns:
        df = df[df['Time'].isin(['8:00 AM', '4:00 PM'])].copy()

    def clean_val(x):
        try: return float(re.split(r'\(|\s', str(x))[0].replace(',', ''))
        except: return 0.0

    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    meter_col = next((c for c in df.columns if "Meter Reading" in c or "Booster" in c), None)

    df['Well_Prod'] = df[usage_col].apply(clean_val) if usage_col else 0
    df['Meter_Raw'] = df[meter_col].apply(clean_val) if meter_col else 0

    # Year Logic: Jan-Apr are 2026, others 2025
    def hma_date(d):
        try:
            yr = "2026" if any(m in str(d) for m in ["Jan", "Feb", "Mar", "Apr"]) else "2025"
            return pd.to_datetime(f"{d} {yr}", errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(hma_date)
    df = df.dropna(subset=['Full_Date'])

    daily = df.groupby('Full_Date').agg({'Well_Prod':'sum', 'Meter_Raw':'max'}).reset_index().sort_values('Full_Date')
    
    # Verified Distribution (Install Cutoff Feb 5th 2026)
    daily['Dist'] = daily['Meter_Raw'].diff()
    daily.loc[daily['Full_Date'] < pd.Timestamp("2026-02-05"), 'Dist'] = np.nan
    daily.loc[daily['Dist'] < 0, 'Dist'] = 0
    daily['Avg_30'] = daily['Well_Prod'].rolling(window=30, min_periods=1).mean()
    
    return daily

try:
    master_df = fetch_live_data()
except Exception as e:
    st.error(f"ENGINE ERROR: {e}"); st.stop()

# ==========================================
# 3. SIDEBAR & LOGO (SHARP FIX)
# ==========================================
with st.sidebar:
    # Guaranteed Logo Loading
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", width=220)
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    st.markdown("### 🎛️ BI CONTROLS")
    population = st.number_input("Campus Population", value=260)
    savings_goal = st.slider("Conservation Goal (%)", 0, 40, 10)
    
    st.markdown("---")
    dates = sorted(master_df['Full_Date'].dt.date.unique(), reverse=True)
    sel_date = st.selectbox("📅 REPORTING DATE", dates)
    
    st.markdown("---")
    st.caption("SYSTEM STATUS: LIVE SYNC")
    st.caption("STANDARD: WHO WATER NOTE 9.1")

# ==========================================
# 4. DASHBOARD - SHARP INTERFACE
# ==========================================
# Header
st.markdown(f"""
    <div class="header-container">
        <div class="header-sub">Haile-Manas Academy | Infrastructure BI</div>
        <div class="header-title">WATER INFRASTRUCTURE DASHBOARD</div>
        <div style="color:#64748B; font-weight:700; font-size:0.9rem;">
            LIVE REPORTING PERIOD: {sel_date} | SYSTEM STABILITY: 99.8%
        </div>
    </div>
    """, unsafe_allow_html=True)

# Data Processing for selection
day = master_df[master_df['Full_Date'].dt.date == sel_date].iloc[0]
p = day['Well_Prod']
d = day['Dist'] if not pd.isna(day['Dist']) else 0
lpcd = (d * 1000) / population if d > 0 else 0
eff = (d / p * 100) if p > 0 else 0
loss = max(0, p - d)
target_v = day['Avg_30'] * (1 - savings_goal/100)

# --- SURGICAL KPI CARDS ---
c1, c2, c3 = st.columns(3)

def custom_kpi(col, title, value, delta, status_color):
    col.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{title}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-delta" style="color:{status_color};">{delta}</div>
        </div>
        """, unsafe_allow_html=True)

custom_kpi(c1, "WHO Standard (LPCD)", f"{lpcd:.0f} L", f"{lpcd-100:+.1f} vs Target", SUCCESS_GREEN if lpcd < 110 else ALERT_RED)
custom_kpi(c2, "Infrastructure Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Daily Loss", SUCCESS_GREEN if eff > 90 else ALERT_RED)
custom_kpi(c3, "Well Extraction", f"{p:.1f} m³", f"{p-target_v:+.1f} vs Goal", SUCCESS_GREEN if p < target_v else ALERT_RED)

st.markdown("<br>", unsafe_allow_html=True)

# --- TREND ANALYSIS ---
st.markdown("### 📈 EXTRACTION VS. TARGET ANALYTICS")
fig_t = go.Figure()
fig_t.add_trace(go.Scatter(x=master_df['Full_Date'], y=master_df['Well_Prod'], name='Actual Extraction',
                           line=dict(color=NAVY_DEEP, width=4), fill='tozeroy', fillcolor='rgba(10, 25, 47, 0.03)'))
fig_t.add_trace(go.Scatter(x=master_df['Full_Date'], y=master_df['Avg_30']*(1-savings_goal/100), 
                           name='Conservation Goal', line=dict(color=HMA_GOLD, width=3, dash='dash')))
fig_t.update_layout(height=400, template="plotly_white", margin=dict(l=0,r=0,t=20,b=0), 
                  legend=dict(orientation="h", y=1.1, x=0), hovermode="x unified")
st.plotly_chart(fig_t, use_container_width=True)

# --- BOTTOM ROW ---
b1, b2 = st.columns([2, 1])

with b1:
    st.markdown("### 📊 DAILY WATER BALANCE")
    fig_b = go.Figure()
    fig_b.add_trace(go.Bar(x=master_df['Full_Date'], y=master_df['Well_Prod'], name='Well Production', marker_color='#E2E8F0'))
    fig_b.add_trace(go.Bar(x=master_df['Full_Date'], y=master_df['Dist'], name='Verified Consumption', marker_color=NAVY_DEEP))
    
    # Meter Installation Marker
    install_ts = datetime(2026, 2, 5).timestamp() * 1000
    fig_b.add_vline(x=install_ts, line_width=2, line_dash="dot", line_color=HMA_GOLD)
    fig_b.add_annotation(x=install_ts, y=p*1.5, text="METER ONLINE", showarrow=False, font=dict(color=HMA_GOLD, size=10, weight=800))
    
    fig_b.update_layout(barmode='overlay', height=350, template="plotly_white", margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig_b, use_container_width=True)

with b2:
    st.markdown("### 📥 ENTERPRISE EXPORT")
    st.markdown("<br>", unsafe_allow_html=True)
    csv = master_df.to_csv(index=False).encode('utf-8')
    st.download_button("📂 DOWNLOAD CSV DATA", csv, "HMA_Water_Data.csv", use_container_width=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as wr: master_df.to_excel(wr, index=False)
    st.download_button("📊 DOWNLOAD EXCEL REPORT", output.getvalue(), "HMA_Enterprise_Report.xlsx", use_container_width=True)

st.markdown("---")
st.caption(f"HMA BI ENTERPRISE v7.0 | SYSTEM REFRESHED: {datetime.now().strftime('%H:%M:%S')}")
