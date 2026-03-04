import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
import io
from datetime import datetime

# ==========================================
# 1. ARCHITECTURAL UI ENGINE (HIGH-CONTRAST)
# ==========================================
st.set_page_config(page_title="HMA BI EXECUTIVE", layout="wide", page_icon="💧")

# Executive Color Palette
NAVY = "#001f3f"    # Prussian Blue
GOLD = "#d4af37"    # HMA Gold
SLATE = "#1e293b"   # Slate Text
BG_GRAY = "#f1f5f9" # Off-white background

# Custom CSS Injection for "Sharp" Interface
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');
    
    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
        background-color: {BG_GRAY};
    }}

    /* Remove Streamlit Header Clutter */
    header {{visibility: hidden;}}
    .main .block-container {{padding-top: 1rem; padding-bottom: 1rem;}}

    /* Sharp Sidebar Branding */
    [data-testid="stSidebar"] {{
        background-color: {NAVY};
        color: white;
        border-right: 3px solid {GOLD};
    }}
    [data-testid="stSidebar"] * {{color: white !important;}}
    .sidebar-logo-container {{
        background-color: white;
        padding: 20px;
        border-radius: 0 0 20px 20px;
        margin-bottom: 30px;
        text-align: center;
    }}

    /* Surgical KPI Cards */
    .kpi-card {{
        background: white;
        border-left: 8px solid {GOLD};
        padding: 25px;
        box-shadow: 5px 5px 0px {NAVY};
        margin-bottom: 15px;
    }}
    .kpi-label {{
        color: {SLATE};
        font-weight: 900;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 2px;
    }}
    .kpi-value {{
        color: {NAVY};
        font-weight: 900;
        font-size: 2.8rem;
        letter-spacing: -2px;
        margin: 5px 0;
    }}
    .kpi-delta {{
        font-size: 0.85rem;
        font-weight: 700;
    }}

    /* Global Title */
    .dashboard-header {{
        border-bottom: 4px solid {NAVY};
        padding-bottom: 10px;
        margin-bottom: 30px;
    }}
    .title-text {{
        font-size: 2.5rem;
        font-weight: 900;
        color: {NAVY};
        letter-spacing: -1px;
    }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. SURGICAL DATA ENGINE
# ==========================================
@st.cache_data(ttl=600)
def load_precision_data():
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    df_raw = pd.read_csv(url, header=None)
    header_idx = next(i for i, row in df_raw.iterrows() if 'Date' in [str(v).strip() for v in row.values if pd.notnull(v)])
    df = pd.read_csv(url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]

    def clean(val):
        try: return float(re.split(r'\(|\s', str(val))[0].replace(',', ''))
        except: return 0.0

    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    meter_col = next((c for c in df.columns if "Meter Reading" in c or "Booster" in c), None)

    df['Prod'] = df[usage_col].apply(clean) if usage_col else 0
    df['Meter'] = df[meter_col].apply(clean) if meter_col else 0

    def parse_hma_date(d):
        d_str = str(d).strip()
        # Intelligent Year Split: Sep-Dec = 2025, Jan-Mar = 2026
        yr = "2026" if any(m in d_str for m in ["Jan", "Feb", "Mar", "Apr"]) else "2025"
        return pd.to_datetime(f"{d_str} {yr}", errors='coerce')

    df['Full_Date'] = df['Date'].apply(parse_hma_date)
    df = df.dropna(subset=['Full_Date'])
    
    daily = df.groupby('Full_Date').agg({'Prod':'sum', 'Meter':'max'}).reset_index().sort_values('Full_Date')
    
    # Verification Logic (Feb 5, 2026 is the cutoff)
    METER_INSTALL_DATE = pd.Timestamp("2026-02-05")
    daily['Dist'] = daily['Meter'].diff()
    
    # Critical Fix: Masking data before meter installation
    daily['Data_Verified'] = daily['Full_Date'] >= METER_INSTALL_DATE
    daily.loc[~daily['Data_Verified'], 'Dist'] = np.nan
    
    daily['Rolling_30'] = daily['Prod'].rolling(window=30, min_periods=1).mean()
    return daily

try:
    master_df = load_precision_data()
except Exception as e:
    st.error(f"Kernel Error: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR COMMAND CENTER
# ==========================================
with st.sidebar:
    # Forced Logo pop-out
    st.markdown('''
        <div class="sidebar-logo-container">
            <img src="https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png" style="width:100%;">
        </div>
    ''', unsafe_allow_html=True)
    
    st.markdown("### 🎚️ PARAMETERS")
    population = st.number_input("Campus Population", value=260)
    goal_pct = st.slider("Conservation Goal (%)", 0, 40, 10)
    
    st.markdown("---")
    st.markdown("### 📅 TIMELINE")
    dates = sorted(master_df['Full_Date'].dt.date.unique(), reverse=True)
    sel_date = st.selectbox("Select Reporting Date", dates)
    
    st.markdown("---")
    st.caption("Standard: WHO LPCD (100L)")
    st.caption("Infrastructure Target: 90% Eff.")

# ==========================================
# 4. DASHBOARD (THE INTERFACE)
# ==========================================

# Header Block
st.markdown(f'''
    <div class="dashboard-header">
        <div class="title-text">WATER INFRASTRUCTURE BI</div>
        <div style="color:{SLATE}; font-weight:700;">HMA BUILDINGS & GROUNDS • STATUS: ACTIVE • AS OF {sel_date}</div>
    </div>
''', unsafe_allow_html=True)

# Extract Selection Data
row = master_df[master_df['Full_Date'].dt.date == sel_date].iloc[0]
p_val = row['Prod']
d_val = row['Dist']
is_verified = row['Data_Verified']

# Calculated Metrics
lpcd = (d_val * 1000) / population if not pd.isna(d_val) else None
eff = (d_val / p_val * 100) if not pd.isna(d_val) and p_val > 0 else None
target = row['Rolling_30'] * (1 - goal_pct/100)
variance = p_val - target

# --- ROW 1: SURGICAL KPI CARDS ---
c1, c2, c3 = st.columns(3)

with c1:
    # Check if data is verified to avoid "0L" looking unprofessional
    val_display = f"{lpcd:.0f} L" if lpcd is not None else "PENDING"
    delta_text = f"{lpcd-100:+.1f} vs Target" if lpcd is not None else "Meter Not Active"
    st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">WHO Standard (LPCD)</div>
            <div class="kpi-value">{val_display}</div>
            <div class="kpi-delta" style="color:{NAVY if lpcd is not None else SLATE};">{delta_text}</div>
        </div>
    ''', unsafe_allow_html=True)

with c2:
    val_display = f"{eff:.1f}%" if eff is not None else "PENDING"
    delta_text = f"{p_val - d_val:.1f} m³ Daily Loss" if d_val is not None else "Audit Pending"
    st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">Infrastructure Efficiency</div>
            <div class="kpi-value">{val_display}</div>
            <div class="kpi-delta" style="color:{NAVY if d_val is not None else SLATE};">{delta_text}</div>
        </div>
    ''', unsafe_allow_html=True)

with c3:
    st.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-label">Current Extraction</div>
            <div class="kpi-value">{p_val:.1f} m³</div>
            <div class="kpi-delta" style="color:{ALERT_RED if variance > 0 else SUCCESS_GREEN};">{variance:+.1f} m³ vs Goal</div>
        </div>
    ''', unsafe_allow_html=True)

# --- ROW 2: ANALYTICS ---
col_trend, col_gauge = st.columns([2, 1])

with col_trend:
    st.markdown("### 📊 Performance Trend")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=master_df['Full_Date'], y=master_df['Prod'], name='Well Production',
                               line=dict(color=NAVY, width=4), fill='tozeroy', fillcolor='rgba(0, 31, 63, 0.05)'))
    fig_t.add_trace(go.Scatter(x=master_df['Full_Date'], y=master_df['Rolling_30']*(1-goal_pct/100), 
                               name='Conservation Goal', line=dict(color=GOLD, width=3, dash='dot')))
    fig_t.update_layout(height=400, template="plotly_white", margin=dict(l=0,r=0,t=0,b=0), legend=dict(orientation="h", y=1.1, x=0))
    st.plotly_chart(fig_t, use_container_width=True)

with col_gauge:
    st.markdown("### 🎯 Efficiency Verification")
    if eff is not None:
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number", value=eff,
            number={'suffix': "%", 'font': {'color': NAVY, 'size': 80}},
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY}}))
    else:
        # Show an empty state if before meter install
        fig_g = go.Figure()
        fig_g.add_annotation(text="METER OFFLINE<br>Historical Data Only", showarrow=False, font=dict(size=20, color=SLATE))
    fig_g.update_layout(height=400, margin=dict(t=50, b=0))
    st.plotly_chart(fig_g, use_container_width=True)

# --- ROW 3: BALANCE ---
st.markdown("### 🏛️ Daily Supply & Demand Balance")
fig_b = go.Figure()
fig_b.add_trace(go.Bar(x=master_df['Full_Date'], y=master_df['Prod'], name='Total Supply (Well)', marker_color='#cbd5e1'))
fig_b.add_trace(go.Bar(x=master_df['Full_Date'], y=master_df['Dist'], name='Verified Distribution (Meter)', marker_color=NAVY))

# Meter Install Line
fig_b.add_vline(x=datetime(2026, 2, 5).timestamp() * 1000, line_width=2, line_dash="dash", line_color=GOLD)
fig_b.add_annotation(x=datetime(2026, 2, 5).timestamp() * 1000, y=master_df['Prod'].max(), text="METER ONLINE", showarrow=False, font=dict(color=GOLD, weight='bold'))

fig_b.update_layout(barmode='overlay', height=350, template="plotly_white", margin=dict(l=0,r=0,t=40,b=0), legend=dict(orientation="h", y=1.15))
st.plotly_chart(fig_b, use_container_width=True)

# --- EXPORTS ---
st.markdown("---")
c1, c2 = st.columns(2)
with c1: st.download_button("📄 EXPORT MASTER CSV", master_df.to_csv(index=False).encode('utf-8'), "HMA_Water_Report.csv", use_container_width=True)
with c2: 
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as wr: master_df.to_excel(wr, index=False)
    st.download_button("📊 EXPORT EXECUTIVE EXCEL", out.getvalue(), "HMA_Water_Report.xlsx", use_container_width=True)
