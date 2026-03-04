import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import datetime

# ==========================================
# 1. PAGE CONFIG & EXECUTIVE BRANDING
# ==========================================
st.set_page_config(page_title="HMA Water Dashboard", layout="wide")

# Institutional Palette (Executive Theme)
NAVY_BLUE = "#1B263B"       
HMA_GOLD = "#A68A64"        
SUCCESS_EMERALD = "#2D6A4F" 
ALERT_CRIMSON = "#941B0C"   
OFF_WHITE = "#F8F9FA"       
SLATE_GRAY = "#4A5568"      

WHO_BASELINE = 100

st.markdown(f"""
    <style>
    .stApp {{ background-color: {OFF_WHITE}; }}
    div[data-testid="stMetric"] {{
        background-color: white; border: 1px solid #E2E8F0;
        padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }}
    div[data-testid="stMetricLabel"] > div {{
        color: {SLATE_GRAY} !important; font-weight: 600 !important;
        text-transform: uppercase; letter-spacing: 0.8px; font-size: 0.8rem;
    }}
    h1, h2, h3 {{ color: {NAVY_BLUE}; font-weight: 800 !important; }}
    [data-testid="stSidebar"] {{ background-color: white; border-right: 1px solid #E2E8F0; }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. DATA ENGINE (MySQL Integration)
# ==========================================
@st.cache_data(ttl=600)
def load_mysql_data():
    try:
        # Connect to MySQL using Streamlit's built-in SQL connection
        # This looks for the [connections.mysql] block in your secrets.toml
        conn = st.connection("mysql", type="sql")
        
        # Query the clean database
        query = """
            SELECT log_date, well_usage_m3, booster_reading 
            FROM water_logs 
            WHERE well_usage_m3 >= 0
            ORDER BY log_date ASC;
        """
        df = conn.query(query)
        
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        st.info("Please ensure your database is running and Streamlit secrets are configured.")
        st.stop()

    # Convert to datetime format
    df['log_date'] = pd.to_datetime(df['log_date'])

    # Aggregate daily totals and max readings (same math as before)
    daily = df.groupby('log_date').agg({
        'well_usage_m3': 'sum', 
        'booster_reading': 'max'
    }).reset_index()

    # Calculate Consumption based on Booster Meter diff
    daily['Consumption_m3'] = daily['booster_reading'].diff()

    # Hard Filter for Meter Install Date (Feb 5, 2026)
    install_date = pd.Timestamp("2026-02-05")
    daily.loc[daily['log_date'] < install_date, 'Consumption_m3'] = np.nan
    
    # Calculate rolling averages and formatting
    daily['Rolling_Avg_30d'] = daily['well_usage_m3'].rolling(window=30).mean()
    daily['Date_Str'] = daily['log_date'].dt.strftime('%Y-%m-%d')
    
    return daily.dropna(subset=['Date_Str']).sort_values('log_date')

# Load the data
df_master = load_mysql_data()

# ==========================================
# 3. SIDEBAR & NAVIGATION
# ==========================================
with st.sidebar:
    st.markdown(f"<h1 style='color:{NAVY_BLUE}; text-align:center;'>HMA</h1>", unsafe_allow_index=True)
    st.markdown(f"<h2 style='color:{NAVY_BLUE}; font-size: 1.2rem;'>CONTROLS</h2>", unsafe_allow_index=True)
    
    pop = st.number_input("Campus Population", value=370, step=10)
    savings_target = st.slider("Goal Target (%)", 0, 30, 10)
    
    # Get the latest date or let user select
    dates_list = sorted(df_master['Date_Str'].unique(), reverse=True)
    selected_date = st.selectbox("Historical View Date", options=dates_list)
    
    st.markdown("---")
    st.markdown(f"<h2 style='color:{NAVY_BLUE}; font-size: 1.2rem;'>STANDARDS</h2>", unsafe_allow_index=True)
    st.link_button("WHO Guidelines", "https://www.who.int/publications/i/item/9789241549950")
    st.link_button("Sphere Handbook", "https://handbook.spherestandards.org/en/sphere/#ch006")

# ==========================================
# 4. DATA CALCULATIONS
# ==========================================
current_data = df_master[df_master['Date_Str'] == selected_date].iloc[0]
prod = current_data['well_usage_m3']
cons = current_data['Consumption_m3']
eff_cons = cons if not np.isnan(cons) and cons > 0 else 0

lpcd = (eff_cons * 1000) / pop if pop and eff_cons > 0 else 0
efficiency = (eff_cons / prod * 100) if prod > 0 else 0
loss_volume = prod - eff_cons if prod > 0 else 0
avg_usage = current_data['Rolling_Avg_30d'] if not np.isnan(current_data['Rolling_Avg_30d']) else prod
target_vol = avg_usage * (1 - (savings_target/100))
variance = prod - target_vol

# ==========================================
# 5. DASHBOARD UI
# ==========================================
st.title("WATER INFRASTRUCTURE DASHBOARD")
st.markdown(f"**HAILE-MANAS ACADEMY** | BUILDINGS & GROUNDS | UPDATED: `{selected_date}`")

# KPI ROW
m1, m2, m3 = st.columns(3)
m1.metric(label="WHO Optimal Standard", 
          value=f"{lpcd:.0f} L/c/d", 
          delta=f"{lpcd - WHO_BASELINE:.1f} vs Goal", 
          delta_color="inverse")

m2.metric(label="System Efficiency", 
          value=f"{efficiency:.1f}%", 
          delta=f"{loss_volume:.1f} m³ Loss", 
          delta_color="inverse")

m3.metric(label=f"Conservation Target (-{savings_target}%)", 
          value=f"{prod:.1f} m³", 
          delta=f"{variance:.1f} m³ vs Target", 
          delta_color="normal" if variance <= 0 else "inverse")

# CHART ROW 1
c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("Production Trend vs. Goal")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(x=df_master['log_date'], y=df_master['well_usage_m3'], name='Actual Production',
                               line=dict(color=NAVY_BLUE, width=3), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
    fig_t.add_trace(go.Scatter(x=df_master['log_date'], y=df_master['Rolling_Avg_30d']*(1-savings_target/100), 
                               name='Target Goal', line=dict(color=HMA_GOLD, width=2, dash='dot')))
    fig_t.update_layout(template='plotly_white', height=350, margin=dict(l=0,r=0,t=0,b=0), legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig_t, use_container_width=True)

with c2:
    st.subheader("System Reliability")
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number", value=efficiency,
        gauge={'axis': {'range': [0, 100], 'tickcolor': NAVY_BLUE},
               'bar': {'color': NAVY_BLUE},
               'bgcolor': "white",
               'steps': [{'range': [0, 70], 'color': '#FEE2E2'}, {'range': [70, 100], 'color': '#D1FAE5'}]}))
    fig_g.update_layout(height=350, margin=dict(l=20,r=20,t=40,b=20))
    st.plotly_chart(fig_g, use_container_width=True)

# CHART ROW 2
st.subheader("Daily Distribution Balance (Verified Consumption vs. Total Production)")
fig_b = go.Figure()
fig_b.add_trace(go.Bar(x=df_master['log_date'], y=df_master['well_usage_m3'], name='Total Pumped (Well)', marker_color='#E2E8F0'))
fig_b.add_trace(go.Bar(x=df_master['log_date'], y=df_master['Consumption_m3'], name='Verified Usage (Booster)', marker_color=NAVY_BLUE))

# Annotation for February 5th, 2026 meter installation
fig_b.add_vline(x=datetime.datetime(2026, 2, 5).timestamp() * 1000, line_width=2, line_dash="dot", line_color=HMA_GOLD)
fig_b.update_layout(barmode='overlay', template='plotly_white', height=300, 
                  margin=dict(l=0,r=0,t=0,b=0), legend=dict(orientation="h", y=1.1, x=0))
st.plotly_chart(fig_b, use_container_width=True)
