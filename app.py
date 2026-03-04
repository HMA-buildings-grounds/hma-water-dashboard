import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
import io
from datetime import datetime

# ==========================================
# 1. ARCHITECTURAL UI & BRANDING
# ==========================================
st.set_page_config(
    page_title="HMA Infrastructure BI",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# World Bank Style Color Palette
NAVY_BLUE = "#0f233a"
GOLD_ACCENT = "#d4af37"
SUCCESS_GREEN = "#27ae60"
ALERT_RED = "#c0392b"
NEUTRAL_GRAY = "#f0f2f6"

# Inject Executive CSS
st.markdown(f"""
    <style>
    /* Global Typography & Background */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [class*="css"]  {{
        font-family: 'Inter', sans-serif;
        background-color: {NEUTRAL_GRAY};
    }}

    /* Professional Sidebar */
    [data-testid="stSidebar"] {{
        background-color: #ffffff;
        border-right: 1px solid #dee2e6;
    }}
    
    /* Branded Metric Cards */
    [data-testid="stMetric"] {{
        background-color: #ffffff;
        border: 1px solid #e1e4e8;
        padding: 24px !important;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
        border-left: 6px solid {GOLD_ACCENT};
    }}
    [data-testid="stMetricValue"] {{ font-size: 2.4rem !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    [data-testid="stMetricLabel"] {{ font-size: 0.85rem !important; font-weight: 600 !important; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em; }}

    /* Title & Headers */
    .main-title {{
        font-size: 2.2rem;
        font-weight: 800;
        color: {NAVY_BLUE};
        margin-bottom: 0px;
    }}
    .sub-status {{
        color: #6c757d;
        font-size: 0.95rem;
        margin-top: -10px;
        font-weight: 500;
    }}
    
    /* Clean Divider */
    hr {{ margin: 2rem 0; border: 0; border-top: 1px solid #dee2e6; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. INTELLIGENT DATA ENGINE
# ==========================================
@st.cache_data(ttl=600)
def load_and_clean_data():
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    df_raw = pd.read_csv(url, header=None)
    header_idx = next(i for i, row in df_raw.iterrows() if 'Date' in [str(v).strip() for v in row.values if pd.notnull(v)])
    df = pd.read_csv(url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]

    # Clean Logic
    def to_f(val):
        try: return float(re.split(r'\(|\s', str(val))[0].replace(',', ''))
        except: return np.nan

    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    meter_col = next((c for c in df.columns if "Meter Reading" in c or "Booster" in c), None)

    df['Prod'] = df[usage_col].apply(to_f) if usage_col else 0
    df['Meter'] = df[meter_col].apply(to_f) if meter_col else 0

    # Date Splitting Logic (Jan-Apr 2026, rest 2025)
    def parse_dt(d):
        try:
            yr = "2026" if any(m in str(d) for m in ["Jan", "Feb", "Mar", "Apr"]) else "2025"
            return pd.to_datetime(f"{d} {yr}", errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(parse_dt)
    df = df.dropna(subset=['Full_Date'])

    daily = df.groupby('Full_Date').agg({'Prod':'sum', 'Meter':'max'}).reset_index().sort_values('Full_Date')
    
    # Verified Distribution Logic
    daily['Dist'] = daily['Meter'].diff()
    daily.loc[daily['Full_Date'] < pd.Timestamp("2026-02-05"), 'Dist'] = np.nan
    daily.loc[daily['Dist'] < 0, 'Dist'] = 0
    daily['Avg_30'] = daily['Prod'].rolling(window=30, min_periods=1).mean()
    
    return daily

try:
    master_df = load_and_clean_data()
except Exception as e:
    st.error(f"BI Data Connection Failed: {e}")
    st.stop()

# ==========================================
# 3. BRANDED SIDEBAR (THE KEY TO "PROFESSIONAL")
# ==========================================
with st.sidebar:
    # Use st.logo for the absolute top-corner professional branding
    st.logo("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", size="large")
    
    st.markdown("### 📊 DASHBOARD CONTROLS")
    population = st.number_input("Campus Population", value=260, help="Used to calculate LPCD standards")
    target_pct = st.slider("Goal Savings (%)", 0, 40, 10)
    
    st.markdown("---")
    st.markdown("### 📅 DATE SELECTION")
    available_dates = sorted(master_df['Full_Date'].dt.date.unique(), reverse=True)
    selected_date = st.selectbox("Select Report Date", available_dates)
    
    st.markdown("---")
    st.markdown("### 📋 STANDARDS")
    st.caption("WHO Reference: Table 5.1 (100L)")
    st.caption("Infrastructure Target: 90% Efficiency")

# ==========================================
# 4. EXECUTIVE MAIN INTERFACE
# ==========================================
# Main Title Block
st.markdown('<p class="main-title">WATER INFRASTRUCTURE DASHBOARD</p>', unsafe_allow_html=True)
st.markdown(f'<p class="sub-status">HAILE-MANAS ACADEMY • BUILDINGS & GROUNDS • UPDATED: {selected_date}</p>', unsafe_allow_html=True)

# Data Selection
day_data = master_df[master_df['Full_Date'].dt.date == selected_date].iloc[0]
prod_val = day_data['Prod']
dist_val = day_data['Dist'] if not pd.isna(day_data['Dist']) else 0
lpcd_val = (dist_val * 1000) / population if dist_val > 0 else 0
eff_val = (dist_val / prod_val * 100) if prod_val > 0 else 0
target_val = day_data['Avg_30'] * (1 - target_pct/100)

# --- KPI ROW (Top Level Summary) ---
k1, k2, k3 = st.columns(3)
with k1:
    st.metric("WHO Standard (LPCD)", f"{lpcd_val:.0f} L", f"{lpcd_val-100:+.1f} vs Target", delta_color="inverse")
with k2:
    loss = max(0, prod_val - dist_val)
    st.metric("Infrastructure Efficiency", f"{eff_val:.1f}%", f"{loss:.1f} m³ Daily Loss", delta_color="inverse")
with k3:
    var = prod_val - target_val
    st.metric(f"Conservation Goal (-{target_pct}%)", f"{prod_val:.1f} m³", f"{var:+.1f} m³ vs Goal", delta_color="inverse")

st.markdown("<br>", unsafe_allow_html=True)

# --- TREND ANALYSIS ROW ---
col_trend, col_gauge = st.columns([2, 1])

with col_trend:
    st.markdown("#### 📈 Extraction Performance & Forecast")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=master_df['Full_Date'], y=master_df['Prod'], name='Actual Extraction', 
                               line=dict(color=NAVY_BLUE, width=3), fill='tozeroy', fillcolor='rgba(15, 35, 58, 0.05)'))
    fig_t.add_trace(go.Scatter(x=master_df['Full_Date'], y=master_df['Avg_30']*(1-target_pct/100), 
                               name='Conservation Target', line=dict(color=SUCCESS_GREEN, width=2, dash='dot')))
    fig_t.update_layout(height=380, template="plotly_white", margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", y=1.1, x=0))
    st.plotly_chart(fig_t, use_container_width=True)

with col_gauge:
    st.markdown("#### 🎯 System Recovery Score")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff_val,
        number={'suffix': "%", 'font': {'color': NAVY_BLUE, 'size': 60}},
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE},
               'steps': [{'range': [0, 70], 'color': "#f8d7da"},
                         {'range': [70, 90], 'color': "#fff3cd"},
                         {'range': [90, 100], 'color': "#d1e7dd"}]}))
    fig_g.update_layout(height=380, margin=dict(t=80, b=0, l=30, r=30))
    st.plotly_chart(fig_g, use_container_width=True)

# --- COMPREHENSIVE BALANCE CHART ---
st.markdown("#### 📊 Daily Water Balance (Total Production vs. Verified Distribution)")
fig_b = go.Figure()
fig_b.add_trace(go.Bar(x=master_df['Full_Date'], y=master_df['Prod'], name='Total Extraction (Well)', marker_color='#cfd8dc'))
fig_b.add_trace(go.Bar(x=master_df['Full_Date'], y=master_df['Dist'], name='Verified Consumption (Meter)', marker_color=NAVY_BLUE))

# Vertical Highlight for Meter Install
install_line = datetime(2026, 2, 5).timestamp() * 1000
fig_b.add_vline(x=install_line, line_width=2, line_dash="dash", line_color=GOLD_ACCENT)
fig_b.add_annotation(x=install_line, y=prod_val*1.5, text="DIGITAL METER ONLINE", showarrow=False, font=dict(color=GOLD_ACCENT, weight='bold'))

fig_b.update_layout(barmode='overlay', height=350, template="plotly_white", margin=dict(l=0,r=0,t=40,b=0), legend=dict(orientation="h", y=1.15))
st.plotly_chart(fig_b, use_container_width=True)

# --- EXPORT SECTION ---
st.markdown("---")
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    st.caption(f"BI ENTERPRISE SYSTEM V6.0 | SYSTEM TIME: {datetime.now().strftime('%H:%M:%S')} • HMA BUILDINGS & GROUNDS")
with c2:
    csv = master_df.to_csv(index=False).encode('utf-8')
    st.download_button("📄 CSV REPORT", csv, f"HMA_Water_Report_{selected_date}.csv", use_container_width=True)
with c3:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as wr: master_df.to_excel(wr, index=False, sheet_name='Water_Log')
    st.download_button("📊 EXCEL REPORT", out.getvalue(), f"HMA_Master_Log_{selected_date}.xlsx", use_container_width=True)
