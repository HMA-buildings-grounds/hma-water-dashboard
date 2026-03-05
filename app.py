import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
import re
from datetime import datetime

# --- 1. SETTINGS & BRANDING ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label { color: white !important; }[data-testid="stMetricValue"] { color: #1B263B; font-size: 38px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=5)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        return requests.get(api_url).json()
    except:
        return {}

# --- 2. SIDEBAR: OPERATIONAL CONTROLS ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    selected_op_date = st.date_input("Operational Date", value=datetime(2026, 3, 1))
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("""<div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
        <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
        <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
    </div>""", unsafe_allow_html=True)

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. THE "HUMAN-PROOF" DATA ENGINE ---
def clean_usage_value(val):
    """Extracts '44' from '44 (13259-13215)'"""
    if pd.isna(val) or val == "": return 0.0
    s = str(val).strip()
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    return float(match.group()) if match else 0.0

# FIX 1: Allow dynamic years instead of hardcoding 2026
def parse_hma_date(date_str, year):
    """Turns 'Mar 1' into YYYY-MM-DD based on sheet name"""
    try:
        s = str(date_str).strip()
        if not s or s.lower() == 'nan': return None
        if len(s.split()) == 2:
            return pd.to_datetime(f"{s} {year}")
        return pd.to_datetime(s)
    except:
        return None

raw_data = fetch_live_data()
all_months_data =[] # List to hold ALL sheets

for sheet_name, rows in raw_data.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    # Extract the correct year from the tab name (e.g. "Sep 2025" -> "2025")
    year_match = re.search(r'20\d{2}', sheet_name)
    sheet_year = year_match.group(0) if year_match else "2026"
    
    df.columns =[str(c).strip() for c in df.columns]
    
    usage_col = next((c for c in df.columns if "Usage Since" in c), None)
    date_col = next((c for c in df.columns if "Date" in c), None)
    
    if usage_col and date_col:
        df['CleanDate'] = df[date_col].apply(lambda x: parse_hma_date(x, sheet_year))
        df = df.dropna(subset=['CleanDate'])
        df['UsageValue'] = df[usage_col].apply(clean_usage_value)
        
        daily = df.groupby('CleanDate')['UsageValue'].sum().reset_index()
        all_months_data.append(daily)

# FIX 2: Combine ALL sheets together, instead of just taking the last one [-1]
if all_months_data:
    current_df = pd.concat(all_months_data).groupby('CleanDate')['UsageValue'].sum().reset_index()
    current_df = current_df.sort_values('CleanDate')
else:
    current_df = pd.DataFrame()

# --- 4. CALCULATION & HIGHLIGHTING ---
p_val, lpcd, eff = 0.0, 0.0, 0.0
if not current_df.empty:
    target_dt = pd.to_datetime(selected_op_date)
    match = current_df[current_df['CleanDate'] == target_dt]
    
    if not match.empty:
        p_val = match.iloc[0]['UsageValue']
        lpcd = (p_val * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# Tooltips
prod_help = f"Calculation: Sum of 8:00 AM & 4:00 PM readings for {selected_op_date.strftime('%b %d')} = {p_val} m³."
lpcd_help = f"Calculation: ({p_val} m³ × 1000) ÷ {campus_pop} People = {lpcd:.1f} LPCD."
eff_help = f"Calculation: ({target_lpcd} Target ÷ {lpcd:.1f} Actual) × 100 = {eff:.1f}% Efficiency."

# --- 5. VISUALIZATION ---
st.title("Operational Diagnostics & Performance")

if p_val == 0 and not current_df.empty:
    st.warning(f"⚠️ Data for {selected_op_date.strftime('%B %d, %Y')} is either missing or not yet synced from the spreadsheet.")

k1, k2, k3 = st.columns(3)
k1.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse", help=lpcd_help)
k2.metric("System Efficiency", f"{eff:.1f}%", help=eff_help)
k3.metric("Daily Production", f"{p_val:.1f} m³", help=prod_help)

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    chart_view = st.selectbox("Select Performance View", ["Daily LPCD Index", "Production Trend (m³)", "Efficiency Status Trend"])
    
    if not current_df.empty:
        current_df['lpcd_plot'] = (current_df['UsageValue'] * 1000) / campus_pop
        current_df['eff_plot'] = (target_lpcd / current_df['lpcd_plot'] * 100).clip(upper=100)
        
        fig = go.Figure()
        
        y_data = 'lpcd_plot' if "LPCD" in chart_view else ('UsageValue' if "Production" in chart_view else 'eff_plot')
        y_label = "Liters per Capita" if "LPCD" in chart_view else ("Cubic Meters" if "Production" in chart_view else "Efficiency %")
        
        # Smooth SaaS Curved Area
        fig.add_trace(go.Scatter(
            x=current_df['CleanDate'], y=current_df[y_data],
            mode='lines', line_shape='spline', name=chart_view,
            line=dict(width=4, color='rgba(13, 148, 136, 0.6)'),
            fill='tozeroy', fillcolor='rgba(13, 148, 136, 0.1)'
        ))

        # Target Line for LPCD
        if "LPCD" in chart_view:
            fig.add_trace(go.Scatter(x=current_df['CleanDate'], y=[target_lpcd]*len(current_df), name="WHO Target", line=dict(color="#1B263B", dash='dash')))

        # Highlight Selected Date
        if p_val > 0:
            fig.add_trace(go.Scatter(
                x=[pd.to_datetime(selected_op_date)], y=[lpcd if "LPCD" in chart_view else (p_val if "Production" in chart_view else eff)],
                mode='markers+text', name="Selected Day",
                text=[f"Active Day"], textposition="top center",
                marker=dict(color='#1B263B', size=15, line=dict(width=3, color='white'))
            ))

        fig.update_layout(template="plotly_white", height=450, xaxis=dict(title="Timeline", showgrid=False), yaxis=dict(title=y_label), margin=dict(l=0,r=0,t=30,b=0))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range':[0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range':[0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range': [85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# Data Download Section
st.divider()
st.subheader("📥 Data Download Center")
if raw_data:
    # Use raw_data keys for the dropdown, so users select the actual original sheet names
    sel = st.selectbox("Select Log for Download", list(raw_data.keys()))
    df_dl = pd.DataFrame(raw_data[sel])
    c1, c2 = st.columns(2)
    c1.download_button("💾 Download CSV", df_dl.to_csv(index=False), f"{sel}.csv")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df_dl.to_excel(writer, index=False)
    c2.download_button("📂 Download Excel", buf.getvalue(), f"{sel}.xlsx")
