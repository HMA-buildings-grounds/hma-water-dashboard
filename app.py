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
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=30) # Refresh quickly for testing
def fetch_live_data():
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
        return requests.get(api_url).json()
    except: return {}

# --- 2. SIDEBAR ---
with st.sidebar:
    try: st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except: st.title("HMA ACADEMY")
    
    st.markdown("<h3 style='color: white; font-size: 18px;'>Operational Controls</h3>", unsafe_allow_html=True)
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    cons_goal = st.slider("Conservation Goal (%)", 0, 100, 15)
    
    st.divider()
    selected = option_menu(None, ["Performance Dashboard", "Data Logs"], 
                           icons=["speedometer2", "table"], default_index=0,
                           styles={"container": {"background-color": "#1B263B"}, "nav-link": {"color": "white"}})
    
    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 3. SMART DATA PROCESSING ---
raw_data = fetch_live_data()
all_sheets = {name: pd.DataFrame(rows) for name, rows in raw_data.items()}

# Logic to find the right sheet and the right columns
main_df = pd.DataFrame()
prod_col, cons_col = None, None

# 1. Search through all sheets to find the one with water data
for name, df in all_sheets.items():
    if not df.empty:
        # Normalize column names (remove line breaks, spaces, and make lowercase)
        cols_normalized = {c: "".join(str(c).lower().split()) for c in df.columns}
        
        # Check if this sheet contains our keywords
        p_match = [orig for orig, norm in cols_normalized.items() if "wellproduction" in norm]
        c_match = [orig for orig, norm in cols_normalized.items() if "facilityconsumption" in norm]
        
        if p_match and c_match:
            main_df = df
            prod_col = p_match[0]
            cons_col = c_match[0]
            break

# --- 4. DASHBOARD VIEW ---
if selected == "Performance Dashboard":
    st.title("Operational Diagnostics & Performance")

    if main_df.empty:
        st.warning("⚠️ Could not find the 'Production' or 'Consumption' columns. Please ensure your headers in Google Sheets contain the words 'Well Production' and 'Facility Consumption'.")
        with st.expander("Debug: See detected columns"):
            for name, df in all_sheets.items():
                st.write(f"Sheet '{name}' columns:", list(df.columns))
    else:
        # Convert to numeric
        main_df[prod_col] = pd.to_numeric(main_df[prod_col], errors='coerce').fillna(0)
        main_df[cons_col] = pd.to_numeric(main_df[cons_col], errors='coerce').fillna(0)
        
        # Filter for summary rows (where production > 0)
        daily_df = main_df[main_df[prod_col] > 0].copy()
        
        if not daily_df.empty:
            latest = daily_df.iloc[-1]
            p_val, c_val = latest[prod_col], latest[cons_col]
            
            eff = (c_val / p_val * 100) if p_val > 0 else 0
            lpcd = (c_val * 1000) / campus_pop

            # --- ROW 1: KPIs ---
            k1, k2, k3 = st.columns(3)
            k1.metric("Water Distribution Index", f"{lpcd:.1f} LPCD", help="Liters per person per day")
            
            target_eff = 100 - cons_goal
            k2.metric("System Efficiency", f"{eff:.1f}%", f"{eff - target_eff:.1f}% vs Target", 
                      delta_color="normal" if eff >= target_eff else "inverse")
            
            k3.metric("Gross Well Extraction", f"{p_val:.1f} m³")

            if eff < 70:
                st.error("🚨 CRITICAL: System efficiency below 70%. Inspect for leaks.")

            st.divider()

            # --- ROW 2: CHARTS ---
            c_left, c_right = st.columns([2, 1])
            
            with c_left:
                st.subheader("Daily LPCD Ratio Trend")
                daily_df['LPCD'] = (daily_df[cons_col] * 1000) / campus_pop
                fig_lpcd = px.area(daily_df, x="Date", y="LPCD", template="plotly_white", color_discrete_sequence=['#0D9488'])
                st.plotly_chart(fig_lpcd, use_container_width=True)
                
            with c_right:
                st.subheader("Efficiency Status")
                fig_gauge = go.Figure(go.Indicator(
                    mode = "gauge+number", value = eff,
                    gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                             'steps': [{'range': [0, 70], 'color': "#FFEBEE"}, {'range': [90, 100], 'color': "#E8F5E9"}]}))
                fig_gauge.update_layout(height=300, margin=dict(l=20,r=20,t=40,b=20))
                st.plotly_chart(fig_gauge, use_container_width=True)

            st.subheader("Volume Comparison: Production vs Consumption (m³)")
            fig_vol = px.bar(daily_df, x="Date", y=[prod_col, cons_col], barmode="group",
                             template="plotly_white", color_discrete_map={prod_col: "#1B263B", cons_col: "#0D9488"})
            st.plotly_chart(fig_vol, use_container_width=True)
        else:
            st.info("📊 Columns found, but no daily totals (Production > 0) detected yet.")

elif selected == "Data Logs":
    st.title("Campus Water Resource Logs")
    if all_sheets:
        tab = st.selectbox("Select Sheet", list(all_sheets.keys()))
        st.dataframe(all_sheets[tab], use_container_width=True)
