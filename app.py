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
# 1. PAGE CONFIG & ENTERPRISE STYLING
# ==========================================
st.set_page_config(page_title="HMA Water Infrastructure BI", layout="wide", page_icon="💧")

# HMA Brand Identity
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#27ae60"
ALERT_RED = "#e74c3c"
SOFT_BG = "#f8f9fa"

# Professional CSS for Scaling and BI Aesthetics
st.markdown(f"""
    <style>
    .main {{ background-color: {SOFT_BG}; }}
    [data-testid="stMetricValue"] {{ font-size: calc(1.8rem + 1vw) !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    [data-testid="stMetricLabel"] {{ font-size: 1rem !important; font-weight: 600 !important; color: #5f6368; }}
    .stMetric {{ background-color: white; padding: 25px; border-radius: 15px; box-shadow: 0 10px 20px rgba(0,0,0,0.05); border-top: 5px solid {HMA_GOLD}; }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-family: 'Inter', sans-serif; font-weight: 800; }}
    .sidebar .sidebar-content {{ background-color: white; }}
    /* Responsive Chart Container */
    .plot-container {{ border-radius: 15px; background-color: white; padding: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.03); }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. AUTONOMOUS DATA ENGINE (FUTURE-PROOF)
# ==========================================
@st.cache_data(ttl=600) # Auto-refresh every 10 mins
def load_autonomous_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit"
    
    # ሎጂክ፡ ሁሉንም ታቦች (Worksheets) በራስ-ሰር መፈለግ
    # በሺቱ ውስጥ ያሉትን ሁሉንም ታቦች ስም እናገኛለን
    # ማሳሰቢያ፡ ስትሪምሊት ሁሉንም ታቦች በአንድ ጊዜ እንዲያይ 'spreadsheet' ሊንኩን ብቻ እንሰጠዋለን
    df_raw = conn.read(spreadsheet=url, header=None)
    
    # ዳታውን የማጽዳትና የማደራጀት ስራ
    # የሺቱ አወቃቀር በመጀመሪያዎቹ መስመሮች ላይ ርዕስ ስላለው ትክክለኛውን ሄደር እንፈልጋለን
    header_idx = 0
    for i, row in df_raw.iterrows():
        if 'Date' in [str(v).strip() for v in row.values]:
            header_idx = i
            break
            
    df = df_raw.iloc[header_idx+1:].copy()
    raw_headers = [str(h).strip() for h in df_raw.iloc[header_idx].values]
    
    # Duplicate column ስሞችን ማስተካከያ
    clean_cols = []
    for i, h in enumerate(raw_headers):
        clean_cols.append(h if h and h != 'None' else f"Unassigned_{i}")
    df.columns = clean_cols

    # Date Parsing logic (ለማንኛውም ወር እንዲሰራ)
    def robust_date(x):
        try:
            d_str = str(x).strip()
            if not d_str or d_str == 'None': return pd.NaT
            # የዓመቱን መረጃ በራሱ እንዲጨምር (አሁን ያለንበትን ዓመት ይጠቀማል)
            return pd.to_datetime(f"{d_str} 2026", errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(robust_date)
    df = df.dropna(subset=['Full_Date'])

    # Numeric Extraction (m3 መረጃዎችን መለየት)
    def clean_val(x):
        try:
            if isinstance(x, str): return float(re.split(r'\(|\s', x)[0])
            return float(x)
        except: return 0.0

    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    booster_col = next((c for c in df.columns if "Booster" in c), None)

    df['Prod_m3'] = df[usage_col].apply(clean_val) if usage_col else 0.0
    df['Booster_m3'] = pd.to_numeric(df[booster_col], errors='coerce').fillna(0.0)

    # ዕለታዊ አጠቃላይ መረጃ ስሌት
    daily = df.groupby('Full_Date').agg({'Prod_m3':'sum', 'Booster_m3':'max'}).reset_index()
    daily['Dist_m3'] = daily['Booster_m3'].diff().fillna(0.0)
    
    # ኔጌቲቭ ዳታ እንዳይኖር (መለኪያው ሲቀየር የሚፈጠር ስህተት ለመከላከል)
    daily.loc[daily['Dist_m3'] < 0, 'Dist_m3'] = 0
    daily['Rolling_Avg'] = daily['Prod_m3'].rolling(window=7, min_periods=1).mean()
    
    return daily.sort_values('Full_Date')

try:
    df_master = load_autonomous_data()
except Exception as e:
    st.error(f"BI Data Engine Error: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR (OFFICIAL LOGO & GUIDELINES)
# ==========================================
with st.sidebar:
    # 1. Official Logo from hmacademy.org
    st.image("https://images.squarespace-cdn.com/content/v1/594009f6e3df285390772023/1597843477189-L3W6W5XQ4Q3W4Z6V6X4V/HMA_logo_color.jpg", use_container_width=True)
    
    st.markdown("<h2 style='text-align: center;'>Infrastructure BI</h2>", unsafe_allow_html=True)
    st.markdown("---")
    
    st.header("🎛️ SYSTEM CONTROLS")
    pop = st.number_input("Campus Population", value=370, step=10)
    savings_target = st.slider("Conservation Goal (%)", 0, 50, 10)
    
    st.markdown("---")
    st.header("📚 INSTITUTIONAL STANDARDS")
    st.markdown(f"""
    <div style="border-left: 5px solid {ALERT_RED}; padding: 15px; background-color: #fffafa; border-radius: 0 15px 15px 0;">
        <p style="color: {ALERT_RED}; font-weight: 900; margin-bottom: 5px; font-size: 16px;">WHO WATER AUDIT</p>
        <p style="font-size: 13px; color: #444; line-height: 1.5;">Ref: <b>Table 5.1, Page 87</b><br>Target: 100L / Person / Day</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    selected_date = st.selectbox("📅 Report Date", sorted(df_master['Full_Date'].dt.date.unique(), reverse=True))

# ==========================================
# 4. DASHBOARD - ANALYTICS LAYER
# ==========================================
st.title("💧 WATER INFRASTRUCTURE ENTERPRISE DASHBOARD")
st.markdown(f"**HAILE-MANAS ACADEMY** | DATA STATUS: **LIVE 24/7** | {datetime.now().strftime('%d %B %Y')}")

# Core Analytics for the Selected Day
day_data = df_master[df_master['Full_Date'].dt.date == selected_date].iloc[0]
prod = day_data['Prod_m3']
dist = day_data['Dist_m3']
lpcd = (dist * 1000) / pop if dist > 0 else 0
eff = (dist / prod * 100) if prod > 0 and dist > 0 else 0
loss = prod - dist if prod > dist else 0

# --- KPI ROW (PROPORTIONAL SCALING) ---
k1, k2, k3 = st.columns(3)
with k1:
    st.metric("WHO Standard (LPCD)", f"{lpcd:.0f} L", f"{lpcd-100:.1f} vs Baseline", delta_color="inverse")
with k2:
    st.metric("Infrastructure Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Daily Loss", delta_color="inverse")
with k3:
    st.metric("Total Well Production", f"{prod:.1f} m³", f"Current Goal: -{savings_target}%")

st.markdown("<br>", unsafe_allow_html=True)

# --- TREND ANALYSIS ROW ---
col_trend, col_gauge = st.columns([2, 1])

with col_trend:
    st.subheader("📈 Extraction Trend vs Institutional Goal")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Prod_m3'], name='Actual Extraction',
                               line=dict(color=NAVY_BLUE, width=4), fill='tozeroy', fillcolor='rgba(15, 35, 58, 0.05)'))
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg']*(1-savings_target/100), 
                               name='Conservation Target', line=dict(color=SUCCESS_GREEN, width=3, dash='dot')))
    fig_t.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0), height=450, template="plotly_white", margin=dict(l=0,r=10,t=0,b=0))
    st.plotly_chart(fig_t, use_container_width=True)

with col_gauge:
    st.subheader("🎯 System Recovery Rate")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff,
        number={'suffix': "%", 'font': {'size': 80, 'color': NAVY_BLUE}},
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE},
               'steps': [{'range': [0, 70], 'color': "#fadbd8"},
                         {'range': [70, 90], 'color': "#fcf3cf"},
                         {'range': [90, 100], 'color': "#d4efdf"}]}))
    fig_g.update_layout(height=400, margin=dict(t=80, b=0))
    st.plotly_chart(fig_g, use_container_width=True)

# --- BAR CHART (FULL HISTORY) ---
st.subheader("📊 Supply & Demand Balance (Full Dataset History)")
fig_b = px.bar(df_master, x='Full_Date', y=['Prod_m3', 'Dist_m3'], 
             barmode='group', labels={'value': 'Volume (m³)', 'variable': 'Metric'},
             color_discrete_map={'Prod_m3': '#cfd8dc', 'Dist_m3': NAVY_BLUE})
fig_b.update_layout(height=400, template="plotly_white", legend=dict(orientation="h", y=1.1, x=0))
st.plotly_chart(fig_b, use_container_width=True)

# ==========================================
# 5. ENTERPRISE EXPORT CENTER
# ==========================================
st.markdown("---")
st.subheader("📥 Data Export Center (Auditing & Reporting)")
d_col1, d_col2 = st.columns(2)

# CSV Export
csv_data = df_master.to_csv(index=False).encode('utf-8')
d_col1.download_button("📥 Export Full Dataset (CSV)", data=csv_data, file_name=f"HMA_Water_Log_{datetime.now().date()}.csv", mime='text/csv', use_container_width=True)

# Professional Excel Export
excel_output = io.BytesIO()
with pd.ExcelWriter(excel_output, engine='xlsxwriter') as writer:
    df_master.to_excel(writer, index=False, sheet_name='Water_BI_Report')
d_col2.download_button("📥 Export Management Report (Excel)", data=excel_output.getvalue(), file_name=f"HMA_Master_Water_Report.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)

st.caption(f"System Operational | Global Time: {datetime.now().strftime('%H:%M:%S')} | HMA BI Engine v3.0")
