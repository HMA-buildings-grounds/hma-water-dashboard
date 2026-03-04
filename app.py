import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- PAGE CONFIG ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide", page_icon="💧")

# --- TYPE-SAFE STATE INITIALIZATION ---
if 'pop' not in st.session_state:
    st.session_state.pop = 370
if 'target_lpd' not in st.session_state:
    st.session_state.target_lpd = 75

# --- ENTERPRISE CSS ---
st.markdown("""
    <style>
    .stApp {background-color: #F8FAFC;}
    .metric-card {background: white; padding: 20px; border-radius: 12px; border: 1px solid #E2E8F0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);}
    h1 {color: #1B263B; font-weight: 800;}
    </style>
""", unsafe_allow_html=True)

# --- MOCK DATA ENGINE (Replace with your actual SQL load_data) ---
@st.cache_data
def get_data():
    dates = pd.date_range(start="2026-01-01", periods=30)
    df = pd.DataFrame({
        'log_date': dates,
        'well_usage_m3': np.random.uniform(60, 110, 30),
        'Distribution': np.random.uniform(50, 95, 30)
    })
    df['Efficiency'] = (df['Distribution'] / df['well_usage_m3']) * 100
    return df

df = get_data()

# --- SIDEBAR: OPERATIONAL CONTROLS ---
with st.sidebar:
    st.markdown("## ⚙️ Control Center")
    
    # TYPE-SAFE INPUTS
    st.number_input("Campus Population", value=int(st.session_state.pop), step=1, format="%d", key="pop")
    st.number_input("WHO Target (L/c/d)", value=int(st.session_state.target_lpd), step=1, format="%d", key="target_lpd")
    
    st.divider()
    
    # EXPORT MODULE
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export Data (CSV)", csv, "water_usage_report.csv", "text/csv")
    
    st.markdown("### Compliance Links")
    st.markdown("• [WHO Guidelines](https://www.who.int/publications/i/item/9789241549950)")

# --- MAIN UI ---
st.title("💧 Water Infrastructure Executive Report")

# KPI CALCULATIONS
latest = df.iloc[-1]
prod = latest['well_usage_m3']
dist = latest['Distribution']
eff = latest['Efficiency']
per_capita = (dist * 1000) / st.session_state.pop

# KPI ROW
c1, c2, c3, c4 = st.columns(4)
c1.metric("Well Production", f"{prod:.1f} m³")
c2.metric("Efficiency", f"{eff:.1f}%", delta=f"{eff-85:.1f}%" if eff < 85 else None)
c3.metric("Per Capita", f"{per_capita:.0f} L/c/d")
c4.metric("Status", "CRITICAL" if eff < 70 else "NORMAL")

# DIAGNOSTICS
if eff < 70:
    st.error("🚨 CRITICAL: Efficiency below 70%. Inspect distribution network for leaks.")

# ADVANCED VISUALIZATION
fig = go.Figure()
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color="#A68A64", width=3)))

# WHO BENCHMARK LINE
fig.add_hline(y=(st.session_state.target_lpd * st.session_state.pop) / 1000, 
              line_dash="dash", line_color="red", annotation_text="WHO Standard")

fig.update_layout(template="plotly_white", hovermode="x unified", legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

# DATA TABLE
st.subheader("Historical Data")
st.dataframe(df, use_container_width=True)
