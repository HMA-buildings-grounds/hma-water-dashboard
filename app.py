import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime
import io

# --- 1. THEME & BRANDING ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stMetricValue"] { color: #0D9488; font-size: 38px; font-weight: 800; }
    [data-testid="stSidebar"] { background-color: #1B263B; border-right: 1px solid #e2e8f0; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    div.stAlert { border-radius: 12px; border: none; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=60)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        return requests.get(api_url).json()
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return {}

# --- 2. SIDEBAR: OPERATIONAL CONTROLS ---
with st.sidebar:
    # Organization Logo
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.title("HMA ACADEMY")
    
    st.markdown("<h3 style='color: white; font-size: 18px; margin-top:10px;'>Operational Controls</h3>", unsafe_allow_html=True)
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    cons_goal = st.slider("Conservation Goal (%)", 0, 100, 15)
    st.date_input("Operational Date", value=datetime.now())
    
    st.divider()
    selected = option_menu(
        None, ["Performance Dashboard", "Data Logs", "Gallery"], 
        icons=["speedometer2", "table", "images"], 
        default_index=0,
        styles={"container": {"background-color": "#1B263B"}, "nav-link": {"color": "white"}, "nav-link-selected": {"background-color": "#0D9488"}}
    )
    
    st.divider()
    st.markdown("### Resources")
    st.markdown("• [WHO Guidelines (Table 5.1)](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("• [Sphere Handbook (Ch 6)](https://spherestandards.org)")
    
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. DATA PROCESSING ---
raw_data = fetch_live_data()
# Convert the first sheet found into the main analysis dataframe
sheet_names = list(raw_data.keys())
main_df = pd.DataFrame(raw_data.get(sheet_names[0] if sheet_names else "", []))

# EXACT COLUMN NAMES FROM YOUR SPREADSHEET
PROD_COL = "Total 24h Well Production (m³)"
CONS_COL = "Total 24h Facility Consumption (m³)"

# --- 4. PERFORMANCE DASHBOARD ---
if selected == "Performance Dashboard":
    st.title("Operational Diagnostics & Performance")

    if main_df.empty or PROD_COL not in main_df.columns:
        st.warning("Awaiting data sync... Ensure the spreadsheet contains 'Date' and Total columns.")
    else:
        # Convert data to numeric
        main_df[PROD_COL] = pd.to_numeric(main_df[PROD_COL], errors='coerce').fillna(0)
        main_df[CONS_COL] = pd.to_numeric(main_df[CONS_COL], errors='coerce').fillna(0)
        
        # Filter for rows where data exists (The Daily Totals)
        daily_df = main_df[main_df[PROD_COL] > 0].copy()
        
        if not daily_df.empty:
            latest = daily_df.iloc[-1]
            p_val = latest[PROD_COL]
            c_val = latest[CONS_COL]
            
            # KPI Calculations
            eff = (c_val / p_val * 100) if p_val > 0 else 0
            lpcd = (c_val * 1000) / campus_pop
            
            # --- ROW 1: PERFORMANCE KPIs ---
            k1, k2, k3 = st.columns(3)
            k1.metric("Water Distribution Index", f"{lpcd:.1f} LPCD", help="Liters per person per day")
            
            # Efficiency Alerting
            eff_color = "normal" if eff >= (100-cons_goal) else "inverse"
            k2.metric("System Efficiency", f"{eff:.1f}%", f"{eff - (100-cons_goal):.1f}% vs Target", delta_color=eff_color)
            
            k3.metric("Gross Well Extraction", f"{p_val:.1f} m³", "Daily Total")

            if eff < 70:
                st.error(f"⚠️ CRITICAL: Efficiency below 70%. Immediate inspection of distribution network required.")

            st.divider()

            # --- ROW 2: ADVANCED VISUALIZATIONS ---
            col_chart, col_gauge = st.columns([2, 1])

            with col_chart:
                st.subheader("Daily Distribution Index Trend (Ratio per Day)")
                daily_df['LPCD_Trend'] = (daily_df[CONS_COL] * 1000) / campus_pop
                fig_area = px.area(daily_df, x="Date", y="LPCD_Trend", 
                                  labels={'LPCD_Trend': 'Liters per Person'},
                                  template="plotly_white", color_discrete_sequence=['#0D9488'])
                st.plotly_chart(fig_area, use_container_width=True)

            with col_gauge:
                st.subheader("Efficiency Status")
                fig_gauge = go.Figure(go.Indicator(
                    mode = "gauge+number", value = eff,
                    gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                             'steps': [{'range': [0, 70], 'color': "#FADBD8"}, {'range': [70, 90], 'color': "#FEF9E7"}, {'range': [90, 100], 'color': "#D1E7DD"}]}))
                fig_gauge.update_layout(height=300, margin=dict(l=20,r=20,t=40,b=20))
                st.plotly_chart(fig_gauge, use_container_width=True)

            # --- ROW 3: VOLUME COMPARISON ---
            st.subheader("Volume Analytics: Well Production vs. Facility Consumption (m³)")
            fig_bar = px.bar(daily_df, x="Date", y=[PROD_COL, CONS_COL], 
                             barmode="group", template="plotly_white",
                             color_discrete_map={PROD_COL: "#1B263B", CONS_COL: "#0D9488"})
            st.plotly_chart(fig_bar, use_container_width=True)

elif selected == "Data Logs":
    st.title("Campus Water Resource Logs")
    if raw_data:
        target = st.selectbox("Select Facility Sheet", list(raw_data.keys()))
        df_display = pd.DataFrame(raw_data[target])
        st.dataframe(df_display, use_container_width=True)
        
        # Professional Excel Export
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            for name, df in raw_data.items():
                pd.DataFrame(df).to_excel(writer, sheet_name=name[:31], index=False)
        st.download_button("📥 Download All Sheets (Excel)", data=buffer.getvalue(), file_name="HMA_Water_Full_Report.xlsx")

elif selected == "Gallery":
    st.title("Infrastructure Gallery")
    st.image("assets/HMA_logo_color.jpg", width=300)
    st.info("Gallery for facility documentation. Add URLs to your spreadsheet to display live facility photos here.")
