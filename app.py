import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import re
from datetime import datetime

# ==========================================
# 1. PAGE SETUP & GLOBAL STYLING
# ==========================================
st.set_page_config(page_title="HMA Sustainability BI", layout="wide", page_icon="🌍")

# HMA Branding Palette
COLOR_PRIMARY = "#0f233a"  # Navy
COLOR_ACCENT = "#d4af37"   # Gold
COLOR_SUCCESS = "#27ae60"  # Green
COLOR_BG = "#f8f9fb"

# Custom CSS for "Card" Look
st.markdown(f"""
    <style>
    .main {{ background-color: {COLOR_BG}; }}
    div[data-testid="metric-container"] {{
        background-color: white;
        border: 1px solid #e1e4e8;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        border-top: 5px solid {COLOR_ACCENT};
    }}
    .stMetric label {{ font-weight: 700 !important; color: #5f6368 !important; text-transform: uppercase; font-size: 0.8rem !important; }}
    .stMetric div[data-testid="stMetricValue"] {{ color: {COLOR_PRIMARY} !important; font-size: 2.2rem !important; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA ENGINE
# ==========================================
@st.cache_data(ttl=300)
def load_enterprise_data():
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    df_raw = pd.read_csv(url, header=None)
    header_idx = 0
    for i, row in df_raw.iterrows():
        if 'Date' in [str(v).strip() for v in row.values if pd.notnull(v)]:
            header_idx = i
            break
            
    df = pd.read_csv(url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]

    # Parsing Dates & Years
    def parse_dt(x):
        try:
            val = str(x).strip()
            if len(val) < 10: val = f"{val} 2026" # Defaulting for your current log
            return pd.to_datetime(val, errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(parse_dt)
    df = df.dropna(subset=['Full_Date'])
    df['Year'] = df['Full_Date'].dt.year
    df['Month'] = df['Full_Date'].dt.strftime('%b')

    # Numeric Cleaning
    def clean_val(x):
        try: return float(re.split(r'\(|\s', str(x))[0].replace(',', ''))
        except: return 0.0

    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    meter_col = next((c for c in df.columns if "Meter Reading" in c), None)

    df['Consumption'] = df[usage_col].apply(clean_val)
    df['Meter'] = df[meter_col].apply(clean_val) if meter_col else df['Consumption']

    # Aggregating daily
    daily = df.groupby(['Full_Date', 'Year', 'Month']).agg({
        'Consumption': 'sum',
        'Meter': 'max'
    }).reset_index().sort_values('Full_Date')
    
    # Calculate Savings/Conserved
    daily['Conserved'] = daily['Consumption'] * 0.15 # Baseline estimate for the BI demo
    daily['Efficiency'] = ((daily['Consumption'] - daily['Conserved']) / daily['Consumption'] * 100).fillna(100)
    
    return daily

try:
    master_df = load_enterprise_data()
except Exception as e:
    st.error(f"Engine Error: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR & NAVIGATION (LOGO FIX)
# ==========================================
with st.sidebar:
    # Fixing the Logo: Using a stable direct link
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", width=200)
    st.markdown("### 🏢 HMA BI SYSTEMS")
    st.markdown("---")
    
    # Year Tabs (Like in the video)
    selected_year = st.radio("SELECT FISCAL YEAR", sorted(master_df['Year'].unique(), reverse=True), horizontal=True)
    
    st.markdown("---")
    st.markdown("### ⚙️ GLOBAL FILTERS")
    pop = st.number_input("Campus Population", value=370)
    
    st.markdown("---")
    st.info("💡 Pro Tip: Use the Year radio buttons above to toggle historical views.")

# Filter Data by Year
df_year = master_df[master_df['Year'] == selected_year]

# ==========================================
# 4. MAIN DASHBOARD (POWER BI LAYOUT)
# ==========================================
st.title("🛡️ SUSTAINABILITY PERFORMANCE DASHBOARD")
st.markdown(f"**PROJECT: HAILE-MANAS ACADEMY** | REPORTING YEAR: **{selected_year}**")

# --- ROW 1: TOP LEVEL KPIs ---
total_cons = df_year['Consumption'].sum()
total_saved = df_year['Conserved'].sum()
avg_eff = df_year['Efficiency'].mean()

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total Consumption", f"{total_cons:,.0f} m³", "Annual Sum")
with c2:
    st.metric("Water Conserved", f"{total_saved:,.0f} m³", f"{(total_saved/total_cons*100):.1f}% Saving", delta_color="normal")
with c3:
    st.metric("Avg Infrastructure Eff.", f"{avg_eff:.1f}%", "Target: 90%+")
with c4:
    lpcd_avg = (df_year['Consumption'].mean() * 1000) / pop
    st.metric("Avg Daily LPCD", f"{lpcd_avg:.0f} L", f"{lpcd_avg-100:.0f} vs WHO")

st.markdown("<br>", unsafe_allow_html=True)

# --- ROW 2: TREND ANALYSIS (BIG LINE CHART) ---
st.subheader("📊 Consumption & Conservation Trends")
fig_trend = go.Figure()
fig_trend.add_trace(go.Scatter(x=df_year['Full_Date'], y=df_year['Consumption'], name='Gross Consumption', 
                               line=dict(color=COLOR_PRIMARY, width=3), fill='tozeroy'))
fig_trend.add_trace(go.Scatter(x=df_year['Full_Date'], y=df_year['Conserved'], name='Water Conserved', 
                               line=dict(color=COLOR_SUCCESS, width=2, dash='dot')))
fig_trend.update_layout(height=400, template="plotly_white", margin=dict(l=0,r=0,b=0,t=20), hovermode="x unified")
st.plotly_chart(fig_trend, use_container_width=True)

# --- ROW 3: DETAILED ANALYSIS ---
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("📅 Monthly Performance")
    monthly = df_year.groupby('Month')['Consumption'].sum().reindex(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']).dropna()
    fig_month = px.bar(monthly, color_discrete_sequence=[COLOR_PRIMARY], text_auto='.2s')
    fig_month.update_layout(height=350, showlegend=False, template="plotly_white")
    st.plotly_chart(fig_month, use_container_width=True)

with col_right:
    st.subheader("📑 Data Explorer (Live Log)")
    # Just like the video's data table
    st.dataframe(df_year[['Full_Date', 'Consumption', 'Conserved', 'Efficiency']].sort_values('Full_Date', ascending=False), 
                 use_container_width=True, height=350)

# ==========================================
# 5. EXPORT CENTER
# ==========================================
st.markdown("---")
exp_c1, exp_c2 = st.columns([3, 1])
with exp_c1:
    st.caption(f"Enterprise BI System v5.0 | Last Refreshed: {datetime.now().strftime('%H:%M:%S')}")
with exp_c2:
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        df_year.to_excel(writer, index=False, sheet_name='Sustainability_Report')
    st.download_button("📥 EXPORT ANNUAL REPORT", excel_buffer.getvalue(), f"HMA_Report_{selected_year}.xlsx", use_container_width=True)
