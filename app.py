import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import re
import io
import xlsxwriter # Explicit import to ensure environment stability
from datetime import datetime

# ==========================================
# 1. PAGE CONFIG & PRO-BI STYLING
# ==========================================
st.set_page_config(
    page_title="HMA Water Infrastructure BI", 
    layout="wide", 
    page_icon="💧",
    initial_sidebar_state="expanded"
)

# Branding Colors
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#27ae60"
ALERT_RED = "#e74c3c"

# Advanced CSS for Scaling & Layout
st.markdown(f"""
    <style>
    .main {{ background-color: #f4f7f9; }}
    [data-testid="stMetricValue"] {{ font-size: calc(1.8rem + 1vw) !important; font-weight: 800 !important; color: {NAVY_BLUE}; }}
    [data-testid="stMetricLabel"] {{ font-size: 1rem !important; font-weight: 600 !important; color: #5f6368; }}
    .stMetric {{ 
        background-color: white; 
        padding: 20px; 
        border-radius: 15px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.05); 
        border-top: 5px solid {HMA_GOLD}; 
    }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-family: 'Segoe UI', sans-serif; }}
    .stButton>button {{ background-color: {NAVY_BLUE}; color: white; border-radius: 8px; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. AUTONOMOUS DATA ENGINE
# ==========================================
@st.cache_data(ttl=600)
def load_and_merge_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit"
    
    # Read raw data
    df_raw = conn.read(spreadsheet=url, header=None)
    
    # Dynamic Header Detection
    header_idx = 0
    for i, row in df_raw.iterrows():
        row_vals = [str(v).strip() for v in row.values]
        if 'Date' in row_vals:
            header_idx = i
            break
            
    df = df_raw.iloc[header_idx+1:].copy()
    raw_headers = [str(h).strip() for h in df_raw.iloc[header_idx].values]
    
    # Handle column names and duplicates
    clean_cols = []
    for i, h in enumerate(raw_headers):
        col_name = h if h and h != 'None' else f"Col_{i}"
        clean_cols.append(col_name)
    df.columns = clean_cols

    # Robust Date Parsing
    current_year = datetime.now().year
    def parse_dt(x):
        try:
            d = str(x).strip()
            if not d or d == 'None' or d == 'nan': return pd.NaT
            # Append year if missing, handle various formats
            return pd.to_datetime(f"{d} {current_year}", errors='coerce')
        except: return pd.NaT

    df['Full_Date'] = df['Date'].apply(parse_dt)
    df = df.dropna(subset=['Full_Date'])

    # Data Cleaning Logic
    def to_f(x):
        try:
            if isinstance(x, str):
                # Removes comments/text inside parentheses
                return float(re.split(r'\(|\s', x)[0].replace(',', ''))
            return float(x)
        except: return 0.0

    # Identify Key Columns by keyword matching
    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    booster_col = next((c for c in df.columns if "Booster" in c), None)

    df['Prod_m3'] = df[usage_col].apply(to_f) if usage_col else 0.0
    df['Booster_m3'] = pd.to_numeric(df[booster_col], errors='coerce').fillna(0.0)

    # Aggregation & Logic
    daily = df.groupby('Full_Date').agg({'Prod_m3':'sum', 'Booster_m3':'max'}).reset_index()
    daily = daily.sort_values('Full_Date')
    
    # Calculate Distribution (Delta between booster readings)
    daily['Dist_m3'] = daily['Booster_m3'].diff().fillna(0.0)
    
    # Filter negatives (Meter reset handling)
    daily.loc[daily['Dist_m3'] < 0, 'Dist_m3'] = 0
    daily['Rolling_Avg'] = daily['Prod_m3'].rolling(window=7, min_periods=1).mean()
    
    return daily

try:
    df_master = load_and_merge_data()
    if df_master.empty:
        st.error("No valid data found in the spreadsheet.")
        st.stop()
except Exception as e:
    st.error(f"⚠️ BI Engine Error: {str(e)}")
    st.info("Check your Google Sheet column names and Date format.")
    st.stop()

# ==========================================
# 3. SIDEBAR CONTROLS
# ==========================================
with st.sidebar:
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown("<h3 style='text-align: center;'>HMA INFRASTRUCTURE</h3>", unsafe_allow_html=True)
    st.markdown("---")
    
    pop = st.number_input("Campus Population", min_value=1, value=370)
    savings_target = st.slider("Conservation Goal (%)", 0, 50, 10)
    
    st.markdown("---")
    st.header("📅 DATA FILTER")
    available_dates = sorted(df_master['Full_Date'].dt.date.unique(), reverse=True)
    selected_date = st.selectbox("Select Reporting Date", available_dates)
    
    st.markdown("---")
    st.caption("Standard: WHO Technical Note 9.1")
    st.markdown(f"""
    <div style="border-left: 5px solid {ALERT_RED}; padding: 10px; background-color: #fffafa;">
        <small style="color: {ALERT_RED}; font-weight: bold;">WHO GUIDELINE</small><br>
        <b style="font-size: 14px;">Target: 100L / Person / Day</b>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 4. DASHBOARD MAIN UI
# ==========================================
st.title("🌊 WATER INFRASTRUCTURE ENTERPRISE BI")
st.markdown(f"**HAILE-MANAS ACADEMY** | STATUS: <span style='color:{SUCCESS_GREEN}'>● LIVE</span> | {datetime.now().strftime('%d %B %Y')}", unsafe_allow_html=True)

# Filter data for selected date
day_rows = df_master[df_master['Full_Date'].dt.date == selected_date]
if not day_rows.empty:
    day_data = day_rows.iloc[0]
    prod = day_data['Prod_m3']
    dist = day_data['Dist_m3']
    lpcd = (dist * 1000) / pop if dist > 0 else 0
    eff = (dist / prod * 100) if prod > 0 and dist > 0 else 0
    loss = prod - dist if prod > dist else 0

    # --- KPI ROW ---
    k1, k2, k3 = st.columns(3)
    with k1:
        delta_val = lpcd - 100
        st.metric("WHO Standard (LPCD)", f"{lpcd:.0f} L", f"{delta_val:.1f} vs Target", delta_color="inverse")
    with k2:
        st.metric("System Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Non-Revenue Water", delta_color="inverse")
    with k3:
        st.metric("Total Well Production", f"{prod:.1f} m³", f"Goal: -{savings_target}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- CHARTS ROW ---
    col_trend, col_gauge = st.columns([2, 1])

    with col_trend:
        st.subheader("📈 Extraction Trend & Targets")
        fig_t = go.Figure()
        fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Prod_m3'], name='Actual Extraction',
                                   line=dict(color=NAVY_BLUE, width=3), fill='tozeroy', fillcolor='rgba(15, 35, 58, 0.05)'))
        fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg']*(1-savings_target/100), 
                                   name='Conservation Goal', line=dict(color=SUCCESS_GREEN, width=2, dash='dot')))
        fig_t.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0), height=400, template="plotly_white", margin=dict(l=0,r=0,b=0))
        st.plotly_chart(fig_t, use_container_width=True)

    with col_gauge:
        st.subheader("🎯 Recovery Score")
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number", value=eff,
            number={'suffix': "%", 'font': {'color': NAVY_BLUE}},
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': NAVY_BLUE},
                   'steps': [{'range': [0, 70], 'color': "#fadbd8"},
                             {'range': [70, 90], 'color': "#fcf3cf"},
                             {'range': [90, 100], 'color': "#d4efdf"}]}))
        fig_g.update_layout(height=350, margin=dict(t=50, b=0, l=20, r=20))
        st.plotly_chart(fig_g, use_container_width=True)

    # --- HISTORICAL BAR CHART ---
    st.subheader("📊 Supply vs Distribution (Daily Balance)")
    fig_b = px.bar(df_master, x='Full_Date', y=['Prod_m3', 'Dist_m3'], 
                 barmode='group', labels={'value': 'Volume (m³)', 'variable': 'Metric'},
                 color_discrete_map={'Prod_m3': '#cfd8dc', 'Dist_m3': NAVY_BLUE})
    fig_b.update_layout(height=350, template="plotly_white", legend=dict(orientation="h", y=1.1, x=0), margin=dict(l=0,r=0,b=0))
    st.plotly_chart(fig_b, use_container_width=True)

# ==========================================
# 5. DATA EXPORT CENTER
# ==========================================
st.markdown("---")
st.subheader("📥 Management Reporting Hub")
d_col1, d_col2 = st.columns(2)

# CSV Export
csv_data = df_master.to_csv(index=False).encode('utf-8')
d_col1.download_button("📥 Download Master CSV", data=csv_data, file_name=f"HMA_Water_Report_{selected_date}.csv", mime='text/csv', use_container_width=True)

# Excel Export (Fixed Memory Handling)
try:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_master.to_excel(writer, index=False, sheet_name='Water_BI_Data')
    
    # CRITICAL: Move pointer to start of buffer
    excel_data = output.getvalue()
    
    d_col2.download_button(
        label="📥 Download Master Excel", 
        data=excel_data, 
        file_name="HMA_Master_Water_Log.xlsx", 
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
        use_container_width=True
    )
except Exception as e:
    d_col2.error(f"Excel Export Failed: {e}")

st.caption(f"Infrastructure BI v3.8 | Last System Refreshed: {datetime.now().strftime('%H:%M:%S')}")
