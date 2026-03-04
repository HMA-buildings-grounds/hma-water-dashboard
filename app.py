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
# 1. PAGE CONFIGURATION & ENTERPRISE CSS
# ==========================================
st.set_page_config(page_title="HMA BI Dashboard", layout="wide", page_icon="📊")

# Color Palette (HMA Brand + BI Standards)
NAVY_BLUE = "#0f233a"
HMA_GOLD = "#d4af37"
SUCCESS_GREEN = "#10b981"
ALERT_RED = "#ef4444"
BG_COLOR = "#f3f4f6"

# Advanced CSS for Power BI Look & Feel
st.markdown(f"""
    <style>
    /* Global Font and Background */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: {BG_COLOR}; }}
    
    /* Hide Streamlit Default Elements */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    
    /* KPI Metric Cards Styling */
    div[data-testid="metric-container"] {{
        background-color: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        border-top: 5px solid {HMA_GOLD};
        display: flex;
        flex-direction: column;
        justify-content: center;
    }}
    div[data-testid="metric-container"] label {{ font-size: 14px !important; color: #6b7280 !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.05em; }}
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {{ font-size: 36px !important; font-weight: 800 !important; color: {NAVY_BLUE} !important; }}
    
    /* Custom Headings */
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-weight: 800; }}
    .block-container {{ padding-top: 2rem !important; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DYNAMIC & FUTURE-PROOF DATA ENGINE
# ==========================================
@st.cache_data(ttl=600)
def load_autonomous_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    url = "https://docs.google.com/spreadsheets/d/1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ/edit"
    
    all_data =[]
    # Generates month tags from August 2025 up to December 2030 automatically!
    months_list = pd.date_range(start='2025-08-01', end='2030-12-01', freq='MS').strftime('%b %Y').tolist()
    potential_tabs = [f"Water Usage Log ({m})" for m in months_list]
    
    for tab_name in potential_tabs:
        try:
            df_raw = conn.read(spreadsheet=url, worksheet=tab_name, header=None)
            
            # Find Header Row dynamically
            header_idx = -1
            for i, row in df_raw.iterrows():
                if 'Date' in[str(v).strip() for v in row.values]:
                    header_idx = i
                    break
            
            if header_idx == -1: continue # Skip if no Date column
            
            df = df_raw.iloc[header_idx+1:].copy()
            raw_headers =[str(h).strip() for h in df_raw.iloc[header_idx].values]
            
            # Fix duplicate columns cleanly
            clean_headers =[]
            counts = {}
            for h in raw_headers:
                name = h if h and h != 'None' else "Unassigned"
                if name in counts:
                    counts[name] += 1
                    clean_headers.append(f"{name}_{counts[name]}")
                else:
                    counts[name] = 1
                    clean_headers.append(name)
            df.columns = clean_headers

            # Extract year from tab name
            year = re.search(r'\d{4}', tab_name).group()
            
            def parse_date(x):
                try:
                    d = str(x).strip()
                    if not d or d == 'None': return pd.NaT
                    return pd.to_datetime(f"{d} {year}", errors='coerce')
                except: return pd.NaT

            df['Full_Date'] = df['Date'].apply(parse_date)
            df = df.dropna(subset=['Full_Date'])

            # Clean Numeric Data
            def clean_num(x):
                try:
                    if isinstance(x, str): return float(re.split(r'\(|\s', x)[0])
                    return float(x)
                except: return 0.0

            usage_col = next((c for c in df.columns if "Usage Since" in c), None)
            booster_col = next((c for c in df.columns if "Booster" in c and "Reading" in c), None)

            df['Prod_m3'] = df[usage_col].apply(clean_num) if usage_col else 0.0
            df['Booster_m3'] = pd.to_numeric(df[booster_col], errors='coerce').fillna(0.0)

            all_data.append(df[['Full_Date', 'Prod_m3', 'Booster_m3']])
        except:
            continue # Seamlessly skips missing tabs

    if not all_data:
        return pd.DataFrame()

    # Merge all historical data
    master = pd.concat(all_data, ignore_index=True)
    daily = master.groupby('Full_Date').agg({'Prod_m3':'sum', 'Booster_m3':'max'}).reset_index()
    daily = daily.sort_values('Full_Date')
    
    # Calculate Distribution & Efficiencies
    daily['Dist_m3'] = daily['Booster_m3'].diff().fillna(0.0)
    daily.loc[daily['Dist_m3'] < 0, 'Dist_m3'] = 0 # Zero out meter resets
    
    # Meter Installation filter
    daily.loc[daily['Full_Date'] < pd.Timestamp("2026-02-05"), 'Dist_m3'] = 0
    daily['Rolling_Avg'] = daily['Prod_m3'].rolling(window=7, min_periods=1).mean()
    
    return daily

try:
    df_master = load_autonomous_data()
    if df_master.empty:
        st.error("No data found. Ensure Google Sheet is shared and tabs match 'Water Usage Log (Mon YYYY)'")
        st.stop()
except Exception as e:
    st.error(f"BI System Error: {e}")
    st.stop()

# ==========================================
# 3. EXECUTIVE SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("<p style='font-size:12px; font-weight:bold; color:gray; letter-spacing:1px;'>EXECUTIVE CONTROLS</p>", unsafe_allow_html=True)
    pop = st.number_input("Campus Population", value=370, step=10)
    savings_target = st.slider("Conservation Goal (%)", 0, 50, 10)
    
    st.markdown("<p style='font-size:12px; font-weight:bold; color:gray; letter-spacing:1px; margin-top:20px;'>REPORT DATE</p>", unsafe_allow_html=True)
    dates = sorted(df_master['Full_Date'].dt.date.unique(), reverse=True)
    selected_date = st.selectbox("", dates, label_visibility="collapsed")
    
    st.markdown("<br><hr>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style="background-color: #fef2f2; border-left: 4px solid {ALERT_RED}; padding: 15px; border-radius: 4px;">
        <h4 style="color: {ALERT_RED}; margin: 0 0 5px 0; font-size: 14px;">WHO GUIDELINE BASELINE</h4>
        <p style="font-size: 12px; color: #4b5563; margin: 0;">Ref: Table 5.1, Page 87<br><b>Target: 100L / Person / Day</b></p>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 4. MAIN DASHBOARD CANVAS
# ==========================================
st.title("WATER INFRASTRUCTURE INTELLIGENCE")
st.markdown(f"<p style='color: #6b7280; font-size: 14px; margin-top: -15px;'>HAILE-MANAS ACADEMY | BUILDINGS & GROUNDS | LIVE DATA AS OF: <b>{datetime.now().strftime('%d %B %Y')}</b></p>", unsafe_allow_html=True)

# Analytics Engine
day_data = df_master[df_master['Full_Date'].dt.date == selected_date].iloc[0]
prod = day_data['Prod_m3']
dist = day_data['Dist_m3']
lpcd = (dist * 1000) / pop if dist > 0 and pop > 0 else 0
eff = (dist / prod * 100) if prod > 0 and dist > 0 else 0
loss = prod - dist if prod > dist else 0

# --- PERFORMANCE KPIs ---
st.markdown("<br>", unsafe_allow_html=True)
k1, k2, k3 = st.columns(3)
with k1:
    st.metric("Daily Consumption (LPCD)", f"{lpcd:.0f} L", f"{lpcd-100:.1f} L vs WHO Target", delta_color="inverse")
with k2:
    st.metric("System Efficiency", f"{eff:.1f}%", f"{loss:.1f} m³ Physical Loss", delta_color="inverse")
with k3:
    st.metric("Gross Well Extraction", f"{prod:.1f} m³", f"Goal: -{savings_target}%")

st.markdown("<br><br>", unsafe_allow_html=True)

# --- ADVANCED VISUALIZATIONS ---
c_chart1, c_chart2 = st.columns([2, 1])

# Chart 1: Trend
with c_chart1:
    st.markdown("<h4 style='color: #0f233a; font-size: 16px;'>PRODUCTION TREND VS INSTITUTIONAL GOAL</h4>", unsafe_allow_html=True)
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Prod_m3'], name='Actual Production',
                               line=dict(color=NAVY_BLUE, width=3), fill='tozeroy', fillcolor='rgba(15, 35, 58, 0.08)'))
    fig_t.add_trace(go.Scatter(x=df_master['Full_Date'], y=df_master['Rolling_Avg']*(1-savings_target/100), 
                               name='Target Baseline', line=dict(color=SUCCESS_GREEN, width=2, dash='dot')))
    fig_t.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0), height=380,
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#e5e7eb'))
    st.plotly_chart(fig_t, use_container_width=True)

# Chart 2: Gauge
with c_chart2:
    st.markdown("<h4 style='color: #0f233a; font-size: 16px;'>NETWORK RECOVERY RATE</h4>", unsafe_allow_html=True)
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=eff,
        number={'suffix': "%", 'font': {'size': 60, 'color': NAVY_BLUE, 'family': 'Inter'}},
        gauge={'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "white"}, 'bar': {'color': NAVY_BLUE},
               'steps': [{'range':[0, 70], 'color': "#fee2e2"},
                         {'range': [70, 90], 'color': "#fef3c7"},
                         {'range': [90, 100], 'color': "#d1fae5"}]}))
    fig_g.update_layout(height=350, margin=dict(t=50, b=0, l=20, r=20), paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_g, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# Chart 3: Full Distribution Balance
st.markdown("<h4 style='color: #0f233a; font-size: 16px;'>SUPPLY AND DISTRIBUTION BALANCE (FULL LIFECYCLE)</h4>", unsafe_allow_html=True)
fig_b = px.bar(df_master, x='Full_Date', y=['Prod_m3', 'Dist_m3'], barmode='group',
               color_discrete_map={'Prod_m3': '#d1d5db', 'Dist_m3': NAVY_BLUE})
fig_b.update_layout(height=400, legend=dict(orientation="h", y=1.1, x=0, title=""),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis_title="", yaxis_title="Volume (m³)",
                    xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#e5e7eb'))
st.plotly_chart(fig_b, use_container_width=True)

# ==========================================
# 5. ENTERPRISE REPORTING & EXPORT
# ==========================================
st.markdown("<br><hr style='border: 1px solid #e5e7eb;'>", unsafe_allow_html=True)
st.markdown("<h4 style='color: #0f233a; font-size: 16px;'>DATA EXPORT CENTER</h4>", unsafe_allow_html=True)

c_down1, c_down2, c_space = st.columns([1, 1, 2])

# CSV Download
csv_file = df_master.to_csv(index=False).encode('utf-8')
c_down1.download_button("⬇️ Export Full Dataset (CSV)", data=csv_file, file_name=f"HMA_Water_Data_{selected_date}.csv", mime='text/csv', use_container_width=True)

# Excel Download
excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
    df_master.to_excel(writer, index=False, sheet_name='BI_Data_Export')
c_down2.download_button("⬇️ Export Executive Report (Excel)", data=excel_buffer.getvalue(), file_name="HMA_Master_Report.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
