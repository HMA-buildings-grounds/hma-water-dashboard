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

# Branding Colors
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#27ae60"
ALERT_RED = "#e74c3c"

# CSS for Professional BI Look
st.markdown(f"""
    <style>
    .main {{ background-color: #f4f7f9; }}
    [data-testid="stMetricValue"] {{ font-size: calc(1.8rem + 1vw) !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    .stMetric {{ background-color: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-top: 5px solid {HMA_GOLD}; }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-family: 'Segoe UI', sans-serif; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. AUTONOMOUS DATA ENGINE (FUTURE-PROOF)
# ==========================================
@st.cache_data(ttl=600)
def load_and_merge_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit"
    
    # ሊነበቡ የሚገባቸው የታቦች ዝርዝር (ወደፊት አዳዲስ ወራት ሲጨመሩ እዚህ ይካተታሉ)
    tabs = ["Oct 2025", "Nov 2025", "Dec 2025", "Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026"]
    all_data = []

    for month in tabs:
        try:
            sheet_name = f"Water Usage Log ({month})"
            df_raw = conn.read(spreadsheet=url, worksheet=sheet_name, header=None)
            
            # Header Row መፈለግ
            header_idx = 0
            for i, row in df_raw.iterrows():
                if 'Date' in [str(v).strip() for v in row.values]:
                    header_idx = i
                    break
            
            df = df_raw.iloc[header_idx+1:].copy()
            headers = [str(h).strip() for h in df_raw.iloc[header_idx].values]
            
            # Duplicate Columns ማስተካከል
            clean_cols = []
            for i, h in enumerate(headers):
                clean_cols.append(h if h and h != 'None' else f"Col_{i}")
            df.columns = clean_cols

            # Date Parsing (ለማንኛውም ወር እንዲሰራ)
            year = "2026" if "2026" in month else "2025"
            df['Full_Date'] = pd.to_datetime(df['Date'].astype(str) + f" {year}", errors='coerce')
            df = df.dropna(subset=['Full_Date'])

            def to_f(x):
                try:
                    if isinstance(x, str): return float(re.split(r'\(|\s', x)[0])
                    return float(x)
                except: return 0.0

            usage_col = next((c for c in df.columns if "Usage Since" in c), None)
            booster_col = next((c for c in df.columns if "Booster" in c), None)

            if usage_col: df['Prod'] = df[usage_col].apply(to_f)
            if booster_col: df['Booster'] = pd.to_numeric(df[booster_col], errors='coerce').fillna(0.0)

            all_data.append(df[['Full_Date', 'Prod', 'Booster']])
        except: continue

    if not all_data: return pd.DataFrame()

    master = pd.concat(all_data, ignore_index=True)
    daily = master.groupby('Full_Date').agg({'Prod':'sum', 'Booster':'max'}).reset_index()
    daily['Dist'] = daily['Booster'].diff().fillna(0.0)
    daily.loc[daily['Dist'] < 0, 'Dist'] = 0
    daily['Rolling_Avg'] = daily['Prod'].rolling(window=7, min_periods=1).mean()
    return daily.sort_values('Full_Date')

try:
    df_master = load_and_merge_data()
except Exception as e:
    st.error(f"BI Data Engine Error: {e}"); st.stop()

# ==========================================
# 3. SIDEBAR (LOGO & CONTROLS)
# ==========================================
with st.sidebar:
    # የHMA ሎጎ በቀጥታ ከድረገጻቸው
    st.image("https://images.squarespace-cdn.com/content/v1/594009f6e3df285390772023/1597843477189-L3W6W5XQ4Q3W4Z6V6X4V/HMA_logo_color.jpg", use_container_width=True)
    st.markdown("---")
    st.header("🎛️ CONTROLS")
    pop = st.number_input("Population", value=370)
    goal = st.slider("Goal (%)", 0, 50, 10)
    
    st.markdown("---")
    st.header("📚 STANDARDS")
    st.error("**WHO GUIDELINE**  \nBaseline: 100L / Person / Day")
    
    selected_date = st.selectbox("📅 Select Date", sorted(df_master['Full_Date'].dt.date.unique(), reverse=True))

# ==========================================
# 4. MAIN DASHBOARD
# ==========================================
st.title("🌊 WATER INFRASTRUCTURE BI")
st.write(f"**HAILE-MANAS ACADEMY** | DATA STATUS: **LIVE 24/7**")

# Calculation for the selected day
day_data = df_master[df_master['Full_Date'].dt.date == selected_date].iloc[0]
prod, dist = day_data['Prod'], day_data['Dist']
lpcd = (dist * 1000) / pop if dist > 0 else 0
eff = (dist / prod * 100) if prod > 0 else 0

# KPI Row
k1, k2, k3 = st.columns(3)
k1.metric("WHO Standard (LPCD)", f"{lpcd:.0f} L", f"{lpcd-100:.1f} vs Goal", delta_color="inverse")
k2.metric("System Efficiency", f"{eff:.1f}%", f"{prod-dist:.1f} m³ Loss", delta_color="inverse")
k3.metric("Well Extraction", f"{prod:.1f} m³", f"Target: -{goal}%")

# Charts
c1, c2 = st.columns([2, 1])
with c1:
    st.subheader("📈 Extraction Trend")
    fig_t = px.line(df_master, x='Full_Date', y='Prod', title=None)
    fig_t.update_traces(line_color=NAVY_BLUE, line_width=3)
    st.plotly_chart(fig_t, use_container_width=True)

with c2:
    st.subheader("🎯 Recovery %")
    fig_g = go.Figure(go.Indicator(mode="gauge+number", value=eff,
                                   gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE}}))
    st.plotly_chart(fig_g, use_container_width=True)

# ==========================================
# 5. DATA DOWNLOADS
# ==========================================
st.markdown("---")
st.subheader("📥 Export Reports")
col_csv, col_xlsx = st.columns(2)

# CSV
csv = df_master.to_csv(index=False).encode('utf-8')
col_csv.download_button("Download CSV Dataset", data=csv, file_name="HMA_Water_Report.csv", mime='text/csv')

# Excel (Fixed)
output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_master.to_excel(writer, index=False, sheet_name='Water_Data')
col_xlsx.download_button("Download Excel Report", data=output.getvalue(), file_name="HMA_Water_Full_Report.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
