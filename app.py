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
# 1. PAGE CONFIG & THEME
# ==========================================
st.set_page_config(page_title="HMA Water BI Dashboard", layout="wide", page_icon="💧")

# Branding Colors
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#27ae60"
ALERT_RED = "#e74c3c"

# Professional Styling
st.markdown(f"""
    <style>
    .main {{ background-color: #f8f9fa; }}
    [data-testid="stMetricValue"] {{ font-size: calc(1.8rem + 1vw) !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    .stMetric {{ background-color: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 5px solid {HMA_GOLD}; }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-family: 'Inter', sans-serif; }}
    .stDownloadButton > button {{ width: 100% !important; border-radius: 8px !important; background-color: {NAVY_BLUE} !important; color: white !important; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA ENGINE (MULTI-TAB CRAWLER)
# ==========================================
@st.cache_data(ttl=300)
def load_hma_infrastructure_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit"
    
    all_monthly_data = []
    # በሺትህ ላይ ያሉትን ሁሉንም ወራት ዝርዝር እዚህ እንዘረዝራለን
    tabs = ["Sep 2025", "Oct 2025", "Nov 2025", "Dec 2025", "Jan 2026", "Feb 2026", "Mar 2026"]
    
    for month in tabs:
        try:
            sheet_name = f"Water Usage Log ({month})"
            df_raw = conn.read(spreadsheet=url, worksheet=sheet_name, header=None)
            
            # ሄደሩን መፈለግ
            header_idx = 0
            for i, row in df_raw.iterrows():
                if 'Date' in [str(v).strip() for v in row.values]:
                    header_idx = i
                    break
            
            df = df_raw.iloc[header_idx+1:].copy()
            headers = [str(h).strip() for h in df_raw.iloc[header_idx].values]
            
            # ተመሳሳይ ስም ያላቸውን አምዶች ማስተካከል
            clean_headers = []
            for i, h in enumerate(headers):
                name = h if h != 'None' and h != '' else f"Col_{i}"
                clean_headers.append(name)
            df.columns = clean_headers

            # ዓመቱን መለየት
            yr = "2026" if "2026" in month else "2025"
            
            def fix_date(x):
                try:
                    d = str(x).strip()
                    if not d or d == 'None': return pd.NaT
                    return pd.to_datetime(f"{d} {yr}", errors='coerce')
                except: return pd.NaT

            df['Full_Date'] = df['Date'].apply(fix_date)
            df = df.dropna(subset=['Full_Date'])

            def to_f(x):
                try:
                    if isinstance(x, str): return float(re.split(r'\(|\s', x)[0])
                    return float(x)
                except: return 0.0

            usage_col = next((c for c in df.columns if "Usage Since" in c), None)
            booster_col = next((c for c in df.columns if "Booster" in c and "Reading" in c), None)

            df['Prod'] = df[usage_col].apply(to_f) if usage_col else 0.0
            df['Boost'] = pd.to_numeric(df[booster_col], errors='coerce').fillna(0.0)
            
            all_monthly_data.append(df[['Full_Date', 'Prod', 'Boost']])
        except:
            continue

    if not all_monthly_data:
        return pd.DataFrame()

    final_df = pd.concat(all_monthly_data, ignore_index=True)
    daily = final_df.groupby('Full_Date').agg({'Prod':'sum', 'Boost':'max'}).reset_index()
    daily['Dist'] = daily['Boost'].diff().fillna(0.0)
    
    # Negative value filter
    daily.loc[daily['Dist'] < 0, 'Dist'] = 0
    daily['Roll_Avg'] = daily['Prod'].rolling(window=7, min_periods=1).mean()
    
    return daily.sort_values('Full_Date')

try:
    df_master = load_hma_infrastructure_data()
    if df_master.empty:
        st.error("የዳታ ችግር፡ ወራቶቹን ማግኘት አልተቻለም። እባክዎ የታቦቹን ስም (Tab names) ያረጋግጡ።")
        st.stop()
except Exception as e:
    st.error(f"BI System Error: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR (DRIVE LOGO & CONTROLS)
# ==========================================
with st.sidebar:
    # Logo from direct HMA link (to ensure stability)
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown("<h4 style='text-align: center;'>Infrastructure Analytics</h4>", unsafe_allow_html=True)
    st.markdown("---")
    
    st.header("⚙️ Settings")
    pop = st.number_input("Population", value=370)
    savings = st.slider("Efficiency Target (%)", 0, 40, 10)
    
    st.markdown("---")
    st.header("📋 Standards")
    st.markdown(f"""
        <div style="background-color:#fff5f5; padding:15px; border-radius:10px; border-left: 5px solid {ALERT_RED};">
        <b style="color:{ALERT_RED};">WHO GUIDELINES</b><br>
        <small>Ref: Table 5.1, Page 87<br>Target: 100 Liters/Capita/Day</small>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    # Date Selector
    dates = sorted(df_master['Full_Date'].dt.date.unique(), reverse=True)
    sel_date = st.selectbox("📅 Select Date", dates)

# ==========================================
# 4. DASHBOARD UI
# ==========================================
st.title("💧 WATER INFRASTRUCTURE DASHBOARD")
st.markdown(f"**Haile-Manas Academy** | Buildings & Grounds | {sel_date.strftime('%B %d, %Y')}")

# Data for the selected day
day_row = df_master[df_master['Full_Date'].dt.date == sel_date].iloc[0]
p_val = day_row['Prod']
d_val = day_row['Dist']
lpcd_val = (d_val * 1000) / pop if d_val > 0 else 0
eff_val = (d_val / p_val * 100) if p_val > 0 else 0
loss_val = p_val - d_val if p_val > d_val else 0

# KPI ROW
m1, m2, m3 = st.columns(3)
m1.metric("WHO Standard (LPCD)", f"{lpcd_val:.0f} L", f"{lpcd_val-100:.1f} vs Goal", delta_color="inverse")
m2.metric("System Efficiency", f"{eff_val:.1f}%", f"{loss_val:.1f} m³ Loss", delta_color="inverse")
m3.metric("Well Extraction", f"{p_val:.1f} m³", f"Target: -{savings}%")

# GRAPHS
st.markdown("<br>", unsafe_allow_html=True)
g_left, g_right = st.columns([2, 1])

with g_left:
    st.subheader("📈 Extraction Trend")
    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Prod'], name='Actual', line=dict(color=NAVY_BLUE, width=3), fill='tozeroy'))
    fig_line.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Roll_Avg']*(1-savings/100), name='Goal', line=dict(color=SUCCESS_GREEN, dash='dot')))
    fig_line.update_layout(height=400, template="plotly_white", margin=dict(l=0,r=0,t=10,b=0), legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_line, use_container_width=True)

with g_right:
    st.subheader("🎯 Success Rate")
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=eff_val,
        gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE}}))
    fig_gauge.update_layout(height=350, margin=dict(t=50, b=0))
    st.plotly_chart(fig_gauge, use_container_width=True)

# FULL BAR CHART
st.subheader("📊 Distribution Balance (Sept - March)")
fig_bar = px.bar(df_master, x='Full_Date', y=['Prod', 'Dist'], barmode='group', color_discrete_map={'Prod': '#cfd8dc', 'Dist': NAVY_BLUE})
fig_bar.update_layout(height=400, template="plotly_white", legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig_bar, use_container_width=True)

# DOWNLOADS
st.markdown("---")
st.subheader("📥 Export Data")
d_col1, d_col2 = st.columns(2)

csv = df_master.to_csv(index=False).encode('utf-8')
d_col1.download_button("Download CSV", data=csv, file_name="HMA_Water_Report.csv", mime='text/csv')

output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_master.to_excel(writer, index=False, sheet_name='Report')
d_col2.download_button("Download Excel", data=output.getvalue(), file_name="HMA_Water_Report.xlsx")

st.caption(f"System Live | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
