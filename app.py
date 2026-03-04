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
    [data-testid="stMetricValue"] {{ font-size: calc(1.5rem + 1vw) !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    .stMetric {{ background-color: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-top: 5px solid {HMA_GOLD}; }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-family: 'Segoe UI', sans-serif; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA ENGINE (MAPS TO YOUR SPECIFIC COLUMNS)
# ==========================================
@st.cache_data(ttl=300)
def load_data():
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    # 1. Read Raw
    df_raw = pd.read_csv(csv_url, header=None)
    
    # 2. Find Header Row
    header_idx = 0
    for i, row in df_raw.iterrows():
        if 'Date' in [str(v).strip() for v in row.values if pd.notnull(v)]:
            header_idx = i
            break
            
    # 3. Read with correct header
    df = pd.read_csv(csv_url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]

    # 4. Robust Date Parsing
    def clean_date(x):
        try:
            val = str(x).strip()
            if not val or val.lower() == 'nan': return pd.NaT
            # Check if year is missing (e.g., "March 4")
            if len(val) < 10: val = f"{val} {datetime.now().year}"
            return pd.to_datetime(val, errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(clean_date)
    df = df.dropna(subset=['Full_Date'])

    # 5. Numeric Cleaning
    def clean_num(x):
        try:
            if pd.isna(x): return 0.0
            # Remove parentheses like "(2.5)" and commas
            clean_str = re.split(r'\(|\s', str(x))[0].replace(',', '')
            return float(clean_str)
        except: return 0.0

    # --- KEY MAPPING (Based on your specific error log) ---
    # Look for "Usage Since Last Reading" as Well Production
    # Look for "Meter Reading" as the Cumulative Distribution
    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    meter_col = next((c for c in df.columns if "Meter Reading" in c), None)

    if not usage_col:
        raise ValueError(f"Could not find 'Usage' column. Available: {list(df.columns)}")

    df['Prod_m3'] = df[usage_col].apply(clean_num)
    
    # If we have a cumulative meter reading, we calculate daily distribution from it
    if meter_col:
        df['Meter_Raw'] = df[meter_col].apply(clean_num)
    else:
        df['Meter_Raw'] = df['Prod_m3'] # Fallback if meter is missing

    # 6. Aggregation (Daily)
    daily = df.groupby('Full_Date').agg({
        'Prod_m3': 'sum',
        'Meter_Raw': 'max'
    }).reset_index().sort_values('Full_Date')
    
    # Calculate daily distribution (The difference between today and yesterday's meter)
    daily['Dist_m3'] = daily['Meter_Raw'].diff().fillna(0.0)
    
    # Handle meter resets (don't allow negative distribution)
    daily.loc[daily['Dist_m3'] <= 0, 'Dist_m3'] = daily['Prod_m3'] 
    
    daily['Rolling_Avg'] = daily['Prod_m3'].rolling(window=7, min_periods=1).mean()
    return daily

# --- UI Error Handler ---
try:
    df_master = load_data()
except Exception as e:
    st.error("🚨 DATA FORMAT ERROR")
    st.info(f"Details: {str(e)}")
    st.stop()

# ==========================================
# 3. SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown("### ⚙️ PARAMETERS")
    pop = st.number_input("Population", value=370)
    target_pct = st.slider("Conservation Goal (%)", 0, 50, 10)
    
    st.markdown("---")
    dates = sorted(df_master['Full_Date'].dt.date.unique(), reverse=True)
    sel_date = st.selectbox("📅 Report Date", dates)

# ==========================================
# 4. DASHBOARD
# ==========================================
st.title("🌊 WATER INFRASTRUCTURE BI")
st.markdown(f"**HAILE-MANAS ACADEMY** | DATA: **LIVE** | {datetime.now().strftime('%d %B %Y')}")

# Metrics logic
day_data = df_master[df_master['Full_Date'].dt.date == sel_date].iloc[0]
p = day_data['Prod_m3']
d = day_data['Dist_m3']
lpcd = (d * 1000) / pop if d > 0 else 0
eff = (d / p * 100) if p > 0 else 100 # If p is 0, we can't calculate efficiency
loss = p - d if p > d else 0

k1, k2, k3 = st.columns(3)
with k1: st.metric("WHO LPCD", f"{lpcd:.0f} L", f"{lpcd-100:.1f} vs Target", delta_color="inverse")
with k2: st.metric("System Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Daily Loss", delta_color="inverse")
with k3: st.metric("Well Extraction", f"{p:.1f} m³", f"Goal: -{target_pct}%")

# Trend Chart
st.subheader("📈 Annual Extraction Trend")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Prod_m3'], name='Actual', line=dict(color=NAVY_BLUE, width=3)))
fig.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg']*(1-target_pct/100), name='Goal', line=dict(color=SUCCESS_GREEN, dash='dot')))
fig.update_layout(height=400, template="plotly_white", margin=dict(l=0,r=0,b=0,t=20), legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 5. EXPORTS
# ==========================================
st.markdown("---")
c1, c2 = st.columns(2)

csv = df_master.to_csv(index=False).encode('utf-8')
c1.download_button("📥 Download CSV", csv, "HMA_Water_Log.csv", use_container_width=True)

output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_master.to_excel(writer, index=False, sheet_name='Data')
c2.download_button("📥 Download Excel", output.getvalue(), "HMA_Water_Log.xlsx", use_container_width=True)

st.caption(f"BI v4.2 | Refreshed: {datetime.now().strftime('%H:%M:%S')}")
