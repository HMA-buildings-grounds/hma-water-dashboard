import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
from datetime import datetime

# --- 1. SETTINGS & BRANDING ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

# Navy/Teal/Slate Theme for Deep Professionalism
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stMetricValue"] { color: #0D9488; font-size: 40px; font-weight: 800; }
    [data-testid="stSidebar"] { background-color: #1B263B; border-right: 1px solid #e2e8f0; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    h1, h2, h3 { color: #1B263B; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATA BRIDGE ---
@st.cache_data(ttl=300)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            # Returns a dictionary of DataFrames for every sheet
            return {name: pd.DataFrame(rows) for name, rows in data.items()}
        return {}
    except Exception as e:
        return {}

# --- 3. SIDEBAR: HMA LOGO & OPERATIONAL CONTROLS ---
with st.sidebar:
    # Organization Logo
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.markdown("<h2 style='color: #0D9488;'>HMA ACADEMY</h2>", unsafe_allow_html=True)

    st.markdown("<h3 style='color: white; font-size: 18px; margin-top:10px;'>Operational Controls</h3>", unsafe_allow_html=True)
    
    # User Inputs for real-time calculations
    campus_pop = st.number_input("Campus Population", value=450, min_value=1)
    conservation_goal = st.slider("Conservation Goal (%)", 0, 100, 15)
    op_date = st.date_input("Operational Date", value=datetime.now())

    st.divider()
    
    # Professional Navigation
    selected = option_menu(
        menu_title=None,
        options=["Performance Dashboard", "Data Logs", "Gallery"],
        icons=["speedometer2", "table", "images"], 
        default_index=0,
        styles={
            "container": {"background-color": "#1B263B"},
            "nav-link": {"color": "white", "font-size": "14px"},
            "nav-link-selected": {"background-color": "#0D9488"}
        }
    )

    st.divider()
    
    # Resources Center
    st.markdown("<h3 style='color: white; font-size: 16px;'>Resources</h3>", unsafe_allow_html=True)
    st.markdown("• [WHO Guidelines (Table 5.1)](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("• [Sphere Handbook (Ch 6)](https://spherestandards.org)")
    
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 4. DATA PROCESSING ---
all_sheets = fetch_live_data()

# Identify the main log (Adjust this name to match your Google Sheet tab exactly)
main_df = all_sheets.get("Water Usage Log (Sep 2025)", pd.DataFrame())

if not main_df.empty:
    # Convert data to numeric and clean it
    main_df = main_df.apply(pd.to_numeric, errors='ignore')
    
    # Fetch latest row for current KPIs
    latest = main_df.iloc[-1]
    
    # KPI 1: Daily Gross Well Extraction (m3)
    gross_extraction = latest.get('Production', 0)
    
    # KPI 2: System Efficiency (%)
    distributed = latest.get('Distribution', 0)
    efficiency = (distributed / gross_extraction * 100) if gross_extraction > 0 else 0
    
    # KPI 3: WATER DISTRIBUTION INDEX (LPCD) - THE CORE RATIO
    # Ratio = (m3 distributed * 1000) / Population
    lpcd_index = (distributed * 1000) / campus_pop
else:
    gross_extraction, efficiency, lpcd_index = 0, 0, 0

# --- 5. PERFORMANCE DASHBOARD VIEW ---

if selected == "Performance Dashboard":
    st.title("Operational Diagnostics & Performance")

    # ROW 1: PERFORMANCE KPIs (Replaces technical status)
    k1, k2, k3 = st.columns(3)
    
    # THE HERO RATIO: Water Distribution Index
    k1.metric(
        label="Water Distribution Index", 
        value=f"{lpcd_index:.1f} LPCD", 
        help="Liters per capita per day: Total water distributed divided by campus population."
    )
    
    k2.metric(
        label="System Efficiency", 
        value=f"{efficiency:.1f}%", 
        delta=f"{efficiency - (100-conservation_goal):.1f}% vs Target"
    )
    
    k3.metric(
        label="Gross Well Extraction", 
        value=f"{gross_extraction:.1f} m³", 
        help="Total raw water pumped from wells today."
    )

    st.divider()

    # ROW 2: ADVANCED VISUALIZATIONS
    col_ratio, col_gauge = st.columns([2, 1])

    with col_ratio:
        st.subheader("Daily Distribution Index Trend (Ratio per Day)")
        if not main_df.empty:
            # Create the daily ratio trend
            main_df['Daily_Ratio'] = (main_df['Distribution'] * 1000) / campus_pop
            fig_ratio = px.area(
                main_df, 
                y='Daily_Ratio', 
                title="Historical LPCD Index Ratio",
                labels={'Daily_Ratio': 'Liters per Person (LPCD)'},
                template="plotly_white",
                color_discrete_sequence=['#0D9488']
            )
            fig_ratio.update_layout(height=350, margin=dict(l=0,r=0,t=30,b=0))
            st.plotly_chart(fig_ratio, use_container_width=True)

    with col_gauge:
        st.subheader("System Performance")
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = efficiency,
            gauge = {
                'axis': {'range': [0, 100]},
                'bar': {'color': "#1B263B"},
                'steps': [
                    {'range': [0, 70], 'color': "#FFEBEE"},
                    {'range': [70, 90], 'color': "#FFF9C4"},
                    {'range': [90, 100], 'color': "#E8F5E9"}]
            }
        ))
        fig_gauge.update_layout(height=350, margin=dict(l=20,r=20,t=50,b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

    # ROW 3: PRODUCTION VS DISTRIBUTION (Advanced Analytics)
    st.divider()
    st.subheader("Daily Volume Extraction vs. Distribution (m³)")
    if not main_df.empty:
        fig_vol = px.line(
            main_df, 
            y=['Production', 'Distribution'],
            labels={'value': 'Cubic Meters (m³)', 'variable': 'Category'},
            template="plotly_white",
            color_discrete_map={"Production": "#1B263B", "Distribution": "#0D9488"}
        )
        st.plotly_chart(fig_vol, use_container_width=True)

elif selected == "Data Logs":
    st.title("Campus Water Resource Logs")
    if all_sheets:
        target = st.selectbox("Select Sheet to View/Export", list(all_sheets.keys()))
        st.dataframe(all_sheets[target], use_container_width=True)
        
        # Professional Excel Export
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            for name, df in all_sheets.items():
                df.to_excel(writer, sheet_name=name[:31], index=False)
        st.download_button("📥 Download Full Campus Log (Excel)", data=buffer.getvalue(), file_name="HMA_Water_Full_Report.xlsx")

elif selected == "Gallery":
    st.title("Infrastructure Gallery")
    st.info("Visual documentation of campus water assets.")
    # Show logo as part of the branding in gallery
    st.image("assets/HMA_logo_color.jpg", width=250)
