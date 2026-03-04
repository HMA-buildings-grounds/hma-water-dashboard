import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide", page_icon="💧")

# --- INITIALIZE SESSION STATE ---
if 'pop' not in st.session_state: st.session_state.pop = 370
if 'target_lpd' not in st.session_state: st.session_state.target_lpd = 75

# --- ENTERPRISE THEME & CSS ---
st.markdown("""
    <style>
    .stApp {background-color: #F8FAFC;}
    .metric-card {background: white; padding: 20px; border-radius: 12px; border: 1px solid #E2E8F0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);}
    h1 {color: #1B263B; font-weight: 800;}
    .stMetric {background: #FFFFFF; padding: 15px; border-radius: 10px; border-left: 5px solid #1B263B; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    </style>
""", unsafe_allow_html=True)

# --- DATA ENGINE ---
@st.cache_data(ttl=600)
def load_data():
    # Placeholder for your actual SQL loading logic
    # Ensure this returns a DataFrame with 'log_date', 'well_usage_m3', 'Distribution', and 'Efficiency'
    dates = pd.date_range(end=pd.Timestamp.today(), periods=30)
    df = pd.DataFrame({
        'log_date': dates,
        'well_usage_m3': np.random.uniform(60, 100, 30),
        'Distribution': np.random.uniform(40, 90, 30)
    })
    df['Efficiency'] = (df['Distribution'] / df['well_usage_m3']) * 100
    return df

df = load_data()

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("## ⚙️ Operational Controls")
    
    # FIXED: Strict integer casting to prevent StreamlitMixedNumericTypesError
    st.number_input("Campus Population", min_value=1, value=int(st.session_state.pop), step=1, format="%d", key="pop")
    st.number_input("WHO Target (L/c/d)", min_value=1, value=int(st.session_state.target_lpd), step=1, format="%d", key="target_lpd")
    
    st.divider()
    # EXPORT MODULE
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export Data (CSV)", csv, "HMA_Water_Data.csv", "text/csv")
    
    st.markdown("### Resources")
    st.markdown("• [WHO Guidelines](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("• [Sphere Handbook](https://handbook.spherestandards.org/en/sphere/#ch006)")

# --- CALCULATIONS ---
curr = df.iloc[-1]
prod = curr['well_usage_m3']
dist = curr['Distribution']
eff = curr['Efficiency']
per_capita = (dist * 1000) / st.session_state.pop

# --- MAIN UI ---
st.title("💧 WATER INFRASTRUCTURE COMMAND CENTER")

# KPI ROW
c1, c2, c3, c4 = st.columns(4)
c1.metric("Well Production", f"{prod:.1f} m³")
c2.metric("Efficiency Ratio", f"{eff:.1f}%")
c3.metric("Per Capita Usage", f"{per_capita:.0f} L/c/d")
c4.metric("Status", "OPTIMAL" if eff > 70 else "CRITICAL")

# DIAGNOSTICS
if eff < 70:
    st.error("🚨 CRITICAL: Efficiency below 70%. Inspect distribution network for leaks.")
elif eff < 85:
    st.warning("⚠️ CAUTION: Efficiency suboptimal.")
else:
    st.success("✅ System Status: Normal operational range.")

# ADVANCED VISUALIZATION
st.subheader("Performance Trends")
fig = go.Figure()
fig.add_trace(go.Bar(x=df['log_date'], y=df['well_usage_m3'], name="Production", marker_color="#1B263B"))
fig.add_trace(go.Scatter(x=df['log_date'], y=df['Distribution'], name="Distribution", line=dict(color="#A68A64", width=3)))

# Add dynamic WHO benchmark line based on population
who_limit_m3 = (st.session_state.target_lpd * st.session_state.pop) / 1000
fig.add_hline(y=who_limit_m3, line_dash="dash", line_color="red", annotation_text="WHO Target (m³)")

fig.update_layout(template="plotly_white", hovermode="x unified", legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

# GAUGE
fig_g = go.Figure(go.Indicator(
    mode="gauge+number", value=eff, title={'text': "Efficiency (%)"},
    gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
           'steps': [{'range': [0, 70], 'color': '#FEE2E2'}, {'range': [70, 85], 'color': '#FEF9C3'}]}))
st.plotly_chart(fig_g, use_container_width=True)
