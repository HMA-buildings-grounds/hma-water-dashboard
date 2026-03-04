import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

# --- PAGE CONFIG ---
st.set_page_config(page_title="HMA Facility Command", layout="wide", page_icon="💧")

# --- ENTERPRISE CSS ---
st.markdown("""
    <style>
    /* Global Background */
    .stApp {background-color: #F1F5F9;}
    
    /* Card Component */
    .metric-card {
        background: #FFFFFF;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 5px solid #1B263B;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
    
    /* Typography */
    h1 {color: #1B263B !important; font-family: 'Inter', sans-serif;}
    .css-1r6slp0 {font-size: 1.2rem; font-weight: 600;}
    </style>
""", unsafe_allow_html=True)

# --- STATE MANAGEMENT ---
if 'pop' not in st.session_state: st.session_state.pop = 370
if 'target_lpd' not in st.session_state: st.session_state.target_lpd = 75

# --- DATA ENGINE (Mocked for logic flow) ---
@st.cache_data
def get_data():
    # Example logic: replace this with your actual SQL
    dates = pd.date_range(start="2026-01-01", periods=60)
    data = {
        'log_date': dates,
        'well_usage_m3': np.random.uniform(50, 100, 60),
        'Distribution': np.random.uniform(40, 90, 60)
    }
    return pd.DataFrame(data)

df = get_data()

# --- SIDEBAR: OPERATIONAL COMMAND ---
with st.sidebar:
    st.image("assets/HMA_logo_color.jpg", width=150)
    st.markdown("## ⚙️ Control Center")
    st.number_input("Campus Population (Free Input)", value=st.session_state.pop, key="pop")
    st.number_input("WHO Target (L/c/d)", value=st.session_state.target_lpd, key="target_lpd")
    
    st.divider()
    # CSV EXPORT ENGINE
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export CSV Report", csv, "HMA_Water_Report.csv", "text/csv")

# --- HEADER SECTION ---
st.title("Water Infrastructure Executive Report")
st.markdown("---")

# --- CALCULATED METRICS ---
latest = df.iloc[-1]
prod = latest['well_usage_m3']
dist = latest['Distribution']
per_capita = (dist * 1000) / st.session_state.pop
efficiency = (dist / prod) * 100

# --- KPI CARDS ---
c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("Daily Production", f"{prod:.1f} m³")
with c2: st.metric("Efficiency", f"{efficiency:.1f}%", delta=f"{efficiency-85:.1f}%")
with c3: st.metric("Per Capita Usage", f"{per_capita:.1f} L/c/d", 
                   delta=f"{per_capita-st.session_state.target_lpd:.1f} vs WHO", 
                   delta_color="inverse")
with c4: st.metric("System Status", "NORMAL" if efficiency > 70 else "CRITICAL", 
                   delta="Action Required" if efficiency < 70 else None)

# --- SMART VISUALIZATION ---
st.subheader("Distribution vs. WHO Benchmark")

fig = go.Figure()
# Add the Data
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Actual Distribution", line=dict(color="#A68A64", width=3)))

# Add the Smart Benchmark Line
fig.add_hline(y=st.session_state.target_lpd * st.session_state.pop / 1000, 
              line_dash="dot", line_color="#941B0C", annotation_text="WHO Daily Limit")

fig.update_layout(template="plotly_white", height=400, hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# --- DIAGNOSTICS TABLE ---
st.subheader("Daily Operational Log")
st.dataframe(df.style.background_gradient(subset=['Efficiency'], cmap='RdYlGn'), use_container_width=True)
