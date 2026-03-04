import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
import io
from datetime import datetime

# ==========================================
# 1. THE ARCHITECTURAL UI (SaaS-GRADE)
# ==========================================
st.set_page_config(
    page_title="HMA Infrastructure BI",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Executive Color Palette
PRUSSIAN_BLUE = "#001f3f"  # High-end Navy
HMA_GOLD = "#d4af37"       # Metallic Gold
VIBRANT_GREEN = "#00ff88"  # Neon Success
CRIMSON = "#ff4b4b"        # Sharp Alert
SLATE = "#1e293b"          # Modern Text Slate

# High-Performance CSS Injection
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] {{
        font-family: 'Manrope', sans-serif;
        background-color: #f1f5f9;
    }}

    /* Sharp Card Design */
    [data-testid="stMetric"] {{
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 4px; /* Sharp edges for a "sword" feel */
        padding: 25px !important;
        box-shadow: 10px 10px 0px -2px {PRUSSIAN_BLUE}; /* Brutalist Shadow */
        transition: transform 0.2s ease;
    }}
    [data-testid="stMetric"]:hover {{
        transform: translateY(-5px);
    }}
    
    [data-testid="stMetricValue"] {{ 
        font-size: 3rem !important; 
        font-weight: 800 !important; 
        color: {PRUSSIAN_BLUE} !important;
        letter-spacing: -2px;
    }}
    
    /* Custom Sidebar Branding */
    .sidebar-logo {{
        text-align: center;
        padding: 20px;
        background: #ffffff;
        border-bottom: 2px solid {PRUSSIAN_BLUE};
        margin-bottom: 20px;
    }}

    /* Global Title Polish */
    .dashboard-title {{
        font-size: 2.8rem;
        font-weight: 800;
        color: {PRUSSIAN_BLUE};
        text-transform: uppercase;
        letter-spacing: 2px;
        border-left: 15px solid {HMA_GOLD};
        padding-left: 20px;
        margin-bottom: 5px;
    }}
    
    /* Button Polish */
    .stButton>button {{
        border-radius: 0px;
        background-color: {PRUSSIAN_BLUE};
        color: white;
        font-weight: 600;
        border: none;
        width: 100%;
        height: 50px;
    }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. PRECISION DATA ENGINE
# ==========================================
@st.cache_data(ttl=600)
def load_precision_data():
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    df_raw = pd.read_csv(url, header=None)
    header_idx = next(i for i, row in df_raw.iterrows() if 'Date' in [str(v).strip() for v in row.values if pd.notnull(v)])
    df = pd.read_csv(url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]

    def to_f(val):
        try: return float(re.split(r'\(|\s', str(val))[0].replace(',', ''))
        except: return 0.0

    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    meter_col = next((c for c in df.columns if "Meter Reading" in c or "Booster" in c), None)

    df['Prod'] = df[usage_col].apply(to_f) if usage_col else 0
    df['Meter'] = df[meter_col].apply(to_f) if meter_col else 0

    # Logical Date Processor
    def parse_dt(d):
        try:
            d_str = str(d).strip()
            # Intelligent Year Detection (HMA Logic)
            yr = "2026" if any(m in d_str for m in ["Jan", "Feb", "Mar", "Apr"]) else "2025"
            return pd.to_datetime(f"{d_str} {yr}", errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(parse_dt)
    df = df.dropna(subset=['Full_Date'])

    daily = df.groupby('Full_Date').agg({'Prod':'sum', 'Meter':'max'}).reset_index().sort_values('Full_Date')
    
    # Surgical Delta Logic
    daily['Dist'] = daily['Meter'].diff()
    # Meter Installation Reference: Feb 5th 2026
    daily.loc[daily['Full_Date'] < pd.Timestamp("2026-02-05"), 'Dist'] = np.nan
    daily.loc[daily['Dist'] < 0, 'Dist'] = 0
    daily['Avg_30'] = daily['Prod'].rolling(window=30, min_periods=1).mean()
    
    return daily

try:
    master_df = load_precision_data()
except Exception as e:
    st.error(f"Surgical Error in Data Engine: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR (THE COMMAND CENTER)
# ==========================================
with st.sidebar:
    # High-Stability Logo Container
    st.markdown('<div class="sidebar-logo">', unsafe_allow_html=True)
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("### 🎛️ PARAMETERS")
    population = st.number_input("Campus Population", value=260, step=10)
    target_savings = st.slider("Conservation Goal (%)", 0, 50, 10)
    
    st.markdown("---")
    st.markdown("### 🔍 NAVIGATION")
    dates = sorted(master_df['Full_Date'].dt.date.unique(), reverse=True)
    sel_date = st.selectbox("Select Report Date", dates)
    
    st.markdown("---")
    st.markdown("### 📜 REFS")
    st.caption("Standard: WHO LPCD (100L)")
    st.caption("Infrastructure: 90% Efficiency Target")

# ==========================================
# 4. MAIN INTERFACE (DASHBOARD)
# ==========================================

# Dashboard Header
st.markdown('<p class="dashboard-title">WATER INFRASTRUCTURE BI</p>', unsafe_allow_html=True)
st.markdown(f"**DATA STATUS:** :green[ACTIVE] | **LOCATION:** ADDIS ABABA, ET | **DATE:** {sel_date}")

# Logical Calculations
day_data = master_df[master_df['Full_Date'].dt.date == sel_date].iloc[0]
p_val = day_data['Prod']
d_val = day_data['Dist'] if not pd.isna(day_data['Dist']) else 0
lpcd_val = (d_val * 1000) / population if d_val > 0 else 0
eff_val = (d_val / p_val * 100) if p_val > 0 else 0
target_val = day_data['Avg_30'] * (1 - target_savings/100)
var_val = p_val - target_val

# --- ROW 1: POWER METRICS ---
m1, m2, m3 = st.columns(3)
with m1:
    st.metric("WHO LPCD INDEX", f"{lpcd_val:.0f} L", f"{lpcd_val-100:+.0f} L vs WHO", delta_color="inverse")
with m2:
    loss = max(0, p_val - d_val)
    st.metric("SYSTEM EFFICIENCY", f"{eff_val:.1f}%", f"{loss:.1f} m³ Leak Loss", delta_color="inverse")
with m3:
    st.metric(f"WELL PRODUCTION", f"{p_val:.1f} m³", f"{var_val:+.1f} m³ vs Target", delta_color="inverse")

st.markdown("<br>", unsafe_allow_html=True)

# --- ROW 2: HIGH-END VISUALS ---
c_left, c_right = st.columns([2, 1])

with c_left:
    st.markdown("### 📈 Performance Tracking")
    fig_t = go.Figure()
    # High-contrast Area Chart
    fig_t.add_trace(go.Scatter(x=master_df['Full_Date'], y=master_df['Prod'], name='Well Production',
                               line=dict(color=PRUSSIAN_BLUE, width=4), fill='tozeroy', fillcolor='rgba(0, 31, 63, 0.05)'))
    fig_t.add_trace(go.Scatter(x=master_df['Full_Date'], y=master_df['Avg_30']*(1-target_savings/100), 
                               name='Target Boundary', line=dict(color=HMA_GOLD, width=3, dash='dot')))
    fig_t.update_layout(height=450, template="plotly_white", margin=dict(l=0,r=0,t=10,b=0), legend=dict(orientation="h", y=1.1, x=0))
    st.plotly_chart(fig_t, use_container_width=True)

with c_right:
    st.markdown("### 🎯 Verification")
    # Custom Gauge with Dark Mode feel
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff_val,
        number={'suffix': "%", 'font': {'color': PRUSSIAN_BLUE, 'size': 80}},
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': PRUSSIAN_BLUE},
               'steps': [{'range': [0, 80], 'color': "#fee2e2"},
                         {'range': [80, 100], 'color': "#d1fae5"}]}))
    fig_g.update_layout(height=450, margin=dict(t=100, b=0, l=30, r=30))
    st.plotly_chart(fig_g, use_container_width=True)

# --- ROW 3: WATER BALANCE (BRUTALIST BARS) ---
st.markdown("### 📊 Supply vs Verified Distribution")
fig_b = go.Figure()
fig_b.add_trace(go.Bar(x=master_df['Full_Date'], y=master_df['Prod'], name='Gross Supply (Well)', marker_color='#cbd5e1'))
fig_b.add_trace(go.Bar(x=master_df['Full_Date'], y=master_df['Dist'], name='Verified Distribution', marker_color=PRUSSIAN_BLUE))

# Digital Meter Milestone
milestone = datetime(2026, 2, 5).timestamp() * 1000
fig_b.add_vline(x=milestone, line_width=2, line_dash="dash", line_color=HMA_GOLD)
fig_b.add_annotation(x=milestone, y=master_df['Prod'].max()*1.1, text="DIGITAL METERING ONLINE", showarrow=False, font=dict(color=HMA_GOLD, weight='bold'))

fig_b.update_layout(barmode='overlay', height=400, template="plotly_white", margin=dict(l=0,r=0,t=50,b=0), legend=dict(orientation="h", y=1.2))
st.plotly_chart(fig_b, use_container_width=True)

# ==========================================
# 5. DATA SYNDICATION (EXPORT)
# ==========================================
st.markdown("---")
d1, d2, d3 = st.columns([2, 1, 1])
with d1:
    st.caption(f"HMA BI ENTERPRISE v7.0 | KERNEL: {datetime.now().strftime('%H:%M:%S')} | BUILDINGS & GROUNDS DIV")
with d2:
    st.download_button("📄 EXPORT CSV", master_df.to_csv(index=False).encode('utf-8'), f"HMA_DATA_{sel_date}.csv", use_container_width=True)
with d3:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as wr: master_df.to_excel(wr, index=False, sheet_name='BI_Export')
    st.download_button("📊 EXCEL REPORT", out.getvalue(), f"HMA_EXCEL_{sel_date}.xlsx", use_container_width=True)
