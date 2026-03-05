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

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stMetricValue"] { color: #0D9488; font-size: 40px; font-weight: 800; }
    [data-testid="stSidebar"] { background-color: #1B263B; border-right: 1px solid #e2e8f0; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATA BRIDGE ---
@st.cache_data(ttl=300)
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        response = requests.get(api_url)
        if response.status_code == 200:
            return response.json()
        return {}
    except:
        return {}

# --- 3. SIDEBAR: LOGO & CONTROLS ---
with st.sidebar:
    # TRY TO LOAD LOGO FROM ASSETS
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except:
        st.markdown("<h2 style='color:#0D9488; text-align:center;'>HMA ACADEMY</h2>", unsafe_allow_html=True)

    st.markdown("<h3 style='color: white; font-size: 18px;'>Operational Controls</h3>", unsafe_allow_html=True)
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    conservation_goal = st.slider("Conservation Goal (%)", 0, 100, 15)
    st.date_input("Operational Date", value=datetime.now())

    st.divider()
    selected = option_menu(
        None, ["Performance Dashboard", "Data Logs", "Gallery"],
        icons=["speedometer2", "table", "images"], default_index=0,
        styles={"container": {"background-color": "#1B263B"}, "nav-link": {"color": "white"}, "nav-link-selected": {"background-color": "#0D9488"}}
    )
    st.divider()
    st.markdown("### Resources\n• [WHO Guidelines](https://www.who.int)\n• [Sphere Handbook](https://spherestandards.org)")
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 4. SMART DATA PROCESSING ---
raw_data = fetch_live_data()
all_sheets = {name: pd.DataFrame(rows) for name, rows in raw_data.items()}

# Pick the correct log sheet
sheet_name = "Water Usage Log (Sep 2025)" # Change this to your exact tab name if different
main_df = all_sheets.get(sheet_name, pd.DataFrame())

prod_col, dist_col = None, None

if not main_df.empty:
    # CLEAN COLUMN NAMES (Remove spaces)
    main_df.columns = [str(c).strip() for c in main_df.columns]
    
    # SMART SEARCH FOR COLUMNS
    for col in main_df.columns:
        if "prod" in col.lower(): prod_col = col
        if "dist" in col.lower() or "cons" in col.lower(): dist_col = col
    
    # CONVERT TO NUMERIC
    if prod_col: main_df[prod_col] = pd.to_numeric(main_df[prod_col], errors='coerce').fillna(0)
    if dist_col: main_df[dist_col] = pd.to_numeric(main_df[dist_col], errors='coerce').fillna(0)

# --- 5. CALCULATIONS ---
if not main_df.empty and prod_col and dist_col:
    latest = main_df.iloc[-1]
    prod_val = latest[prod_col]
    dist_val = latest[dist_col]
    
    efficiency = (dist_val / prod_val * 100) if prod_val > 0 else 0
    lpcd_index = (dist_val * 1000) / campus_pop
else:
    prod_val, dist_val, efficiency, lpcd_index = 0, 0, 0, 0

# --- 6. PERFORMANCE DASHBOARD ---
if selected == "Performance Dashboard":
    st.title("Operational Diagnostics & Performance")

    if not prod_col or not dist_col:
        st.error(f"Could not find 'Production' or 'Distribution' columns in sheet '{sheet_name}'. Please check your column headers.")
    else:
        # KPI Row
        k1, k2, k3 = st.columns(3)
        k1.metric("Water Distribution Index", f"{lpcd_index:.1f} LPCD")
        k2.metric("System Efficiency", f"{efficiency:.1f}%", f"{efficiency - (100-conservation_goal):.1f}% vs Target")
        k3.metric("Gross Well Extraction", f"{prod_val:.1f} m³")

        st.divider()

        # Ratio Chart
        st.subheader("Daily Distribution Index Trend (Ratio per Day)")
        main_df['Daily_Ratio'] = (main_df[dist_col] * 1000) / campus_pop
        fig_ratio = px.area(main_df, y='Daily_Ratio', template="plotly_white", color_discrete_sequence=['#0D9488'])
        st.plotly_chart(fig_ratio, use_container_width=True)

        # Comparative Chart
        st.subheader("Volume: Extraction vs. Distribution (m³)")
        fig_vol = px.line(main_df, y=[prod_col, dist_col], template="plotly_white", 
                          color_discrete_map={prod_col: "#1B263B", dist_col: "#0D9488"})
        st.plotly_chart(fig_vol, use_container_width=True)

elif selected == "Data Logs":
    st.title("Data Logs")
    if all_sheets:
        target = st.selectbox("Select Sheet", list(all_sheets.keys()))
        st.dataframe(all_sheets[target], use_container_width=True)
