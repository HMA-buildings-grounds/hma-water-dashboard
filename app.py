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
# 1. PAGE CONFIG & PROFESSIONAL UI STYLING
# ==========================================
st.set_page_config(page_title="HMA Infrastructure Dashboard", layout="wide", page_icon="💧")

# HMA Brand Colors
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#27ae60"
ALERT_RED = "#e74c3c"

# Custom CSS for Professional UI (Responsive & Clean)
st.markdown(f"""
    <style>
    .main {{ background-color: #f8f9fa; font-family: 'Segoe UI', Tahoma, sans-serif; }}
    [data-testid="stMetricValue"] {{ font-size: calc(1.5rem + 1.2vw) !important; font-weight: 700 !important; color: {NAVY_BLUE}; }}
    .stMetric {{ background-color: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.04); border-bottom: 4px solid {HMA_GOLD}; }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-weight: 700; }}
    .sidebar .sidebar-content {{ background-color: white; }}
    /* Remove streamlit footer */
    footer {{visibility: hidden;}}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA ENGINE (CRAWLS ALL MONTH TABS)
# ==========================================
@st.cache_data(ttl=600)
def load_all_historical_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit"
    
    # ይህ ትዕዛዝ ሁሉንም የሺቱን ታቦች በሙሉ ለማግኘት ይረዳል
    all_month_data = []
    
    # የወራቶቹን ዝርዝር በሙሉ ለመፈተሽ (ከመስከረም ጀምሮ)
    potential_tabs = [
        "Water Usage Log (Sep 2025)", "Water Usage Log (Oct 2025)", 
        "Water Usage Log (Nov 2025)", "Water Usage Log (Dec 2025)", 
        "Water Usage Log (Jan 2026)", "Water Usage Log (Feb 2026)", 
        "Water Usage Log (Mar 2026)", "Water Usage Log (Apr 2026)"
    ]
    
    for tab_name in potential_tabs:
        try:
            df_raw = conn.read(spreadsheet=url, worksheet=tab_name, header=None)
            
            # ሄደር መፈለጊያ ሎጂክ
            header_idx = 0
            for i, row in df_raw.iterrows():
                if 'Date' in [str(v).strip() for v in row.values]:
                    header_idx = i
                    break
            
            df = df_raw.iloc[header_idx+1:].copy()
            headers = [str(h).strip() for h in df_raw.iloc[header_idx].values]
            
            # Duplicate አምዶችን ማስተካከያ
            clean_headers = []
            for i, h in enumerate(headers):
                clean_headers.append(h if h and h != 'None' else f"Col_{i}")
            df.columns = clean_headers

            # ዓመቱን መለየት
            year = "2026" if "2026" in tab_name else "2025"
            
            def parse_date(x):
                try:
                    d = str(x).strip()
                    if not d or d == 'None': return pd.NaT
                    return pd.to_datetime(f"{d} {year}", errors='coerce')
                except: return pd.NaT

            df['Full_Date'] = df['Date'].apply(parse_date)
            df = df.dropna(subset=['Full_Date', 'Time'])

            def clean_numeric(x):
                try:
                    if isinstance(x, str): return float(re.split(r'\(|\s', x)[0])
                    return float(x)
                except: return 0.0

            u_col = next((c for c in df.columns if "Usage Since" in c), None)
            b_col = next((c for c in df.columns if "Booster" in c and "Reading" in c), None)

            if u_col: df['Production'] = df[u_col].apply(clean_numeric)
            if b_col: df['Booster_Read'] = pd.to_numeric(df[b_col], errors='coerce').fillna(0.0)

            all_month_data.append(df[['Full_Date', 'Production', 'Booster_Read']])
        except:
            continue

    if not all_month_data:
        return pd.DataFrame()

    final_df = pd.concat(all_month_data, ignore_index=True)
    daily = final_df.groupby('Full_Date').agg({'Production':'sum', 'Booster_Read':'max'}).reset_index()
    daily['Distribution'] = daily['Booster_Read'].diff().fillna(0.0)
    
    # ኔጌቲቭ ዳታን ማስተካከል
    daily.loc[daily['Distribution'] < 0, 'Distribution'] = 0
    daily['Rolling_Avg'] = daily['Production'].rolling(window=7, min_periods=1).mean()
    
    return daily.sort_values('Full_Date')

try:
    df_master = load_all_historical_data()
except Exception as e:
    st.error(f"UI Data Error: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR (HMA LOGO & GUIDELINES)
# ==========================================
with st.sidebar:
    # 1. HMA Logo directly from website
    st.image("https://images.squarespace-cdn.com/content/v1/594009f6e3df285390772023/1597843477189-L3W6W5XQ4Q3W4Z6V6X4V/HMA_logo_color.jpg", use_container_width=True)
    st.markdown("<hr style='border: 1px solid #eee;'>", unsafe_allow_html=True)
    
    st.header("🎛️ CONTROLS")
    pop = st.number_input("Population", value=370, step=10)
    goal = st.slider("Conservation Goal (%)", 0, 40, 10)
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.header("📋 STANDARDS")
    st.markdown(f"""
    <div style="border-left: 5px solid {ALERT_RED}; padding: 15px; background-color: #fdf2f2; border-radius: 0 10px 10px 0;">
        <p style="color: {ALERT_RED}; font-weight: 800; margin-bottom: 5px; font-size: 15px;">WHO GUIDELINES</p>
        <p style="font-size: 13px; color: #333; line-height: 1.4;">Ref: Table 5.1, Page 87<br><b>Goal: 100L / Person / Day</b></p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    dates_list = sorted(df_master['Full_Date'].dt.date.unique(), reverse=True)
    selected_date = st.selectbox("📅 Select Analysis Date", dates_list)

# ==========================================
# 4. MAIN DASHBOARD UI
# ==========================================
st.title("💧 WATER INFRASTRUCTURE DASHBOARD")
st.markdown(f"**HAILE-MANAS ACADEMY** | BUILDINGS & GROUNDS | LIVE STATUS")

# Filter for the day
day_data = df_master[df_master['Full_Date'].dt.date == selected_date].iloc[0]
p_val = day_data['Production']
d_val = day_data['Distribution']
lpcd_val = (d_val * 1000) / pop if d_val > 0 else 0
eff_val = (d_val / p_val * 100) if p_val > 0 and d_val > 0 else 0
loss_val = p_val - d_val if p_val > d_val else 0

# --- KPI METRICS ---
col1, col2, col3 = st.columns(3)
col1.metric("WHO Standard (LPCD)", f"{lpcd_val:.0f} L", f"{lpcd_val-100:.1f} vs WHO", delta_color="inverse")
col2.metric("System Efficiency", f"{eff_val:.1f}%", f"{loss_val:.1f} m³ Daily Loss", delta_color="inverse")
col3.metric("Well Production", f"{p_val:.1f} m³", f"Current Goal: -{goal}%")

st.markdown("<br>", unsafe_allow_html=True)

# --- TRENDS & CHARTS ---
left_c, right_c = st.columns([2, 1])

with left_c:
    st.subheader("📈 Annual Water Extraction Trend")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Production'], name='Actual',
                               line=dict(color=NAVY_BLUE, width=4), fill='tozeroy', fillcolor='rgba(15, 35, 58, 0.05)'))
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg']*(1-goal/100), 
                               name='Conservation Target', line=dict(color=SUCCESS_GREEN, width=2, dash='dot')))
    fig_t.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0), height=400, template="plotly_white")
    st.plotly_chart(fig_t, use_container_width=True)

with right_c:
    st.subheader("🎯 System Recovery Rate")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff_val,
        number={'suffix': "%", 'font': {'size': 60, 'color': NAVY_BLUE}},
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE},
               'steps': [{'range': [0, 70], 'color': "#fadbd8"},
                         {'range': [70, 90], 'color': "#fcf3cf"},
                         {'range': [90, 100], 'color': "#d4efdf"}]}))
    fig_g.update_layout(height=350, margin=dict(t=50, b=0))
    st.plotly_chart(fig_g, use_container
