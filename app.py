import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import re
import io
import xlsxwriter
from datetime import datetime

# ==========================================
# 1. PAGE CONFIG & STYLING
# ==========================================
st.set_page_config(page_title="HMA Water Infrastructure BI", layout="wide", page_icon="💧")

NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#27ae60"
ALERT_RED = "#e74c3c"

st.markdown(f"""
    <style>
    .main {{ background-color: #f4f7f9; }}
    [data-testid="stMetricValue"] {{ font-size: calc(1.8rem + 1vw) !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    .stMetric {{ background-color: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-top: 5px solid {HMA_GOLD}; }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-family: 'Segoe UI', sans-serif; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. ROBUST DATA ENGINE (Direct CSV Method)
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    # Direct Export Link (Bypasses Connection/Secrets issues)
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    # Read raw data starting from top to find header
    df_raw = pd.read_csv(csv_url, header=None)
    
    # 1. Find Header Row (Look for "Date")
    header_idx = 0
    for i, row in df_raw.iterrows():
        if 'Date' in [str(v).strip() for v in row.values if pd.notnull(v)]:
            header_idx = i
            break
            
    # 2. Re-read with correct header
    df = pd.read_csv(csv_url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns] # Clean column names
    
    # 3. Robust Date Parsing
    current_year = datetime.now().year
    def clean_date(x):
        try:
            val = str(x).strip()
            if not val or val.lower() == 'nan': return pd.NaT
            # Ensure year is present
            if len(val) < 8: val = f"{val} {current_year}"
            return pd.to_datetime(val, errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(clean_date)
    df = df.dropna(subset=['Full_Date'])

    # 4. Numeric Cleaning
    def clean_num(x):
        try:
            if pd.isna(x): return 0.0
            # Remove parentheses, text, and commas
            clean_str = re.split(r'\(|\s', str(x))[0].replace(',', '')
            return float(clean_str)
        except: return 0.0

    # Auto-detect columns by keyword
    prod_col = next((c for c in df.columns if "Usage Since" in c), None)
    dist_col = next((c for c in df.columns if "Booster" in c), None)

    if not prod_col or not dist_col:
        raise ValueError(f"Required columns not found. Found: {list(df.columns)}")

    df['Prod_m3'] = df[prod_col].apply(clean_num)
    df['Booster_raw'] = df[dist_col].apply(clean_num)

    # 5. Aggregation
    daily = df.groupby('Full_Date').agg({'Prod_m3':'sum', 'Booster_raw':'max'}).reset_index()
    daily = daily.sort_values('Full_Date')
    
    # Calculate Daily Distribution from Booster readings
    daily['Dist_m3'] = daily['Booster_raw'].diff().fillna(0.0)
    daily.loc[daily['Dist_m3'] < 0, 'Dist_m3'] = 0 # Handle meter resets
    
    daily['Rolling_Avg'] = daily['Prod_m3'].rolling(window=7, min_periods=1).mean()
    return daily

# --- Error Handling UI ---
try:
    df_master = load_data()
except Exception as e:
    st.error("🚨 DATA CONNECTION ERROR")
    st.warning(f"Technical Detail: {str(e)}")
    st.info("Make sure the Google Sheet is 'Public' (Anyone with link can view).")
    st.stop()

# ==========================================
# 3. SIDEBAR & FILTERS
# ==========================================
with st.sidebar:
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown("### 🎛️ SETTINGS")
    pop = st.number_input("Population", value=370)
    savings_target = st.slider("Conservation Goal (%)", 0, 50, 10)
    
    st.markdown("---")
    dates = sorted(df_master['Full_Date'].dt.date.unique(), reverse=True)
    selected_date = st.selectbox("📅 Report Date", dates)

# ==========================================
# 4. DASHBOARD UI
# ==========================================
st.title("🌊 WATER INFRASTRUCTURE BI")
st.markdown(f"**HAILE-MANAS ACADEMY** | STATUS: **LIVE** | {datetime.now().strftime('%d %B %Y')}")

# Filter data for metrics
day_data = df_master[df_master['Full_Date'].dt.date == selected_date].iloc[0]
prod = day_data['Prod_m3']
dist = day_data['Dist_m3']
lpcd = (dist * 1000) / pop if dist > 0 else 0
eff = (dist / prod * 100) if prod > 0 else 0
loss = prod - dist if prod > dist else 0

# Metrics
k1, k2, k3 = st.columns(3)
with k1: st.metric("Daily LPCD", f"{lpcd:.0f} L", f"{lpcd-100:.1f} vs WHO", delta_color="inverse")
with k2: st.metric("Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Loss", delta_color="inverse")
with k3: st.metric("Well Prod", f"{prod:.1f} m³", f"Goal: -{savings_target}%")

# Main Chart
st.subheader("📈 Extraction Trend")
fig_t = go.Figure()
fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Prod_m3'], name='Actual', line=dict(color=NAVY_BLUE, width=3)))
fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg']*(1-savings_target/100), name='Goal', line=dict(color=SUCCESS_GREEN, dash='dot')))
fig_t.update_layout(height=400, template="plotly_white", margin=dict(l=0,r=0,b=0,t=20))
st.plotly_chart(fig_t, use_container_width=True)

# ==========================================
# 5. EXPORT CENTER
# ==========================================
st.markdown("---")
st.subheader("📥 Export Reports")
c1, c2 = st.columns(2)

# CSV
csv_buffer = df_master.to_csv(index=False).encode('utf-8')
c1.download_button("📥 Download CSV", csv_buffer, "HMA_Water_Data.csv", "text/csv", use_container_width=True)

# Excel
output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_master.to_excel(writer, index=False, sheet_name='Data')
c2.download_button("📥 Download Excel", output.getvalue(), "HMA_Report.xlsx", use_container_width=True)

st.caption(f"BI v4.0 | Last Sync: {datetime.now().strftime('%H:%M:%S')}")
