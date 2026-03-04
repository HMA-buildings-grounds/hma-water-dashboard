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
# 1. PAGE SETUP & PRO THEME
# ==========================================
st.set_page_config(page_title="HMA Infrastructure BI", layout="wide", page_icon="💧")

# HMA Branding Colors
NAVY = "#0f233a"
GOLD = "#d4af37"
SUCCESS = "#27ae60"
LIGHT_BG = "#f8f9fa"

# Custom CSS for "Card" Look
st.markdown(f"""
    <style>
    .main {{ background-color: {LIGHT_BG}; }}
    div[data-testid="stMetric"] {{
        background-color: white;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-left: 5px solid {GOLD};
    }}
    .metric-title {{ font-size: 14px; color: #666; font-weight: bold; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 24px; }}
    .stTabs [data-baseweb="tab"] {{ height: 50px; white-space: pre-wrap; background-color: white; border-radius: 5px 5px 0 0; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. ADVANCED DATA ENGINE
# ==========================================
@st.cache_data(ttl=300)
def load_and_process():
    sheet_id = "1txdEeHqCdlQigNRgOXc2x-w4BVFM0-cqdRSoVSqbEzQ"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    # Read raw to find header
    df_raw = pd.read_csv(url, header=None)
    header_idx = 0
    for i, row in df_raw.iterrows():
        if 'Date' in [str(v).strip() for v in row.values if pd.notnull(v)]:
            header_idx = i
            break
            
    df = pd.read_csv(url, skiprows=header_idx)
    df.columns = [str(c).strip() for c in df.columns]

    # Clean Numbers
    def clean_num(x):
        try:
            return float(re.split(r'\(|\s', str(x))[0].replace(',', ''))
        except: return 0.0

    # Clean Dates
    df['Full_Date'] = pd.to_datetime(df['Date'].astype(str) + " 2026", errors='coerce')
    df = df.dropna(subset=['Full_Date'])
    df['Year'] = df['Full_Date'].dt.year
    df['Month'] = df['Full_Date'].dt.strftime('%b')

    # Column Mapping
    prod_col = next((c for c in df.columns if "Usage Since" in c), None)
    meter_col = next((c for c in df.columns if "Meter Reading" in c), None)
    
    df['Consumed'] = df[prod_col].apply(clean_num)
    df['Meter'] = df[meter_col].apply(clean_num) if meter_col else df['Consumed']

    # Daily aggregation
    daily = df.groupby('Full_Date').agg({'Consumed':'sum', 'Meter':'max', 'Year':'first', 'Month':'first'}).reset_index()
    daily['Distributed'] = daily['Meter'].diff().fillna(daily['Consumed'])
    daily.loc[daily['Distributed'] <= 0, 'Distributed'] = daily['Consumed']
    
    return daily

try:
    data = load_and_process()
except Exception as e:
    st.error(f"Engine Failure: {e}")
    st.stop()

# ==========================================
# 3. SIDEBAR (FILTERS LIKE THE VIDEO)
# ==========================================
with st.sidebar:
    st.image("https://hma-edu.org/wp-content/uploads/2021/01/HMA-Logo-Color.png", use_container_width=True)
    st.title("🎛️ Dashboard Filters")
    
    # Multi-Year Selector
    years = sorted(data['Year'].unique())
    selected_year = st.selectbox("📅 Fiscal Year", years, index=len(years)-1)
    
    # Logic for Baseline
    pop = st.number_input("Campus Population", value=370)
    who_target = 100 # Liters per person
    baseline_daily = (pop * who_target) / 1000 # m3
    
    st.markdown("---")
    st.info(f"Target Baseline: **{baseline_daily:.1f} m³ / Day**")

# Filter data based on sidebar
df_year = data[data['Year'] == selected_year]

# ==========================================
# 4. TOP KPI ROW (THE "HEADER" METRICS)
# ==========================================
st.title(f"📊 {selected_year} Water Consumption & Conservation")
st.markdown("---")

total_consumed = df_year['Consumed'].sum()
# Calculate conservation: If WHO baseline is 37m3 and we used 30m3, we saved 7m3
total_baseline = baseline_daily * len(df_year)
total_saved = max(0, total_baseline - total_consumed)
avg_efficiency = (df_year['Distributed'].sum() / total_consumed * 100) if total_consumed > 0 else 0

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("TOTAL CONSUMPTION", f"{total_consumed:,.0f} m³", "Actual Usage")
with m2:
    st.metric("WATER CONSERVED", f"{total_saved:,.0f} m³", f"vs WHO Baseline", delta_color="normal")
with m3:
    st.metric("INFRA EFFICIENCY", f"{avg_efficiency:.1f}%", "System Health")
with m4:
    st.metric("DAILY AVG", f"{df_year['Consumed'].mean():.1f} m³", "Per Day")

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 5. CHARTS (TREND & CATEGORY)
# ==========================================
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("📈 Monthly Consumption vs. Baseline")
    # Group by month for the line chart
    monthly = df_year.groupby('Month', sort=False)['Consumed'].sum().reset_index()
    
    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=monthly['Month'], y=monthly['Consumed'], name='Actual Consumed', 
                                  line=dict(color=NAVY, width=4), mode='lines+markers'))
    fig_line.add_hline(y=baseline_daily * 30, line_dash="dot", line_color=SUCCESS, annotation_text="WHO Baseline")
    
    fig_line.update_layout(template="plotly_white", height=400, margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig_line, use_container_width=True)

with col_right:
    st.subheader("🏘️ Sector Distribution")
    # Simulation of sector data (Assuming Academic/Residential/Staff)
    # In a real sheet, you would group by a 'Category' column
    sectors = pd.DataFrame({
        'Sector': ['Academic', 'Dormitories', 'Staff Housing', 'Kitchen', 'Irrigation'],
        'Usage': [total_consumed*0.3, total_consumed*0.4, total_consumed*0.15, total_consumed*0.05, total_consumed*0.1]
    })
    fig_bar = px.bar(sectors, x='Usage', y='Sector', orientation='h', color_discrete_sequence=[GOLD])
    fig_bar.update_layout(template="plotly_white", height=400, margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig_bar, use_container_width=True)

# ==========================================
# 6. DATA TABLE & EXPORT (BOTTOM SECTION)
# ==========================================
st.markdown("---")
with st.expander("📂 View Detailed Infrastructure Logs"):
    st.dataframe(df_year[['Full_Date', 'Consumed', 'Distributed']].sort_values('Full_Date', ascending=False), use_container_width=True)
    
    # Export Button
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_year.to_excel(writer, index=False, sheet_name='Water_Data')
    st.download_button("📥 Export Current View to Excel", output.getvalue(), f"HMA_Report_{selected_year}.xlsx", use_container_width=True)

st.caption(f"HMA BI v5.0 | AI-Powered Data Engine | {datetime.now().strftime('%H:%M:%S')}")
