import streamlit as st
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
    [data-testid="stSidebar"] * { color: white !important; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 36px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# No cache to ensure you always see the latest edits when testing
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
        st.markdown("<h2 style='text-align:center;'>💧 HMA WATER</h2>", unsafe_allow_html=True)
    
    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=400, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)
    
    # Calendar Input (Defaulting to March 3 for your testing)
    selected_op_date = st.date_input("Operational Date", value=datetime(2026, 3, 3))
    
    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("• [WHO Water Standards](https://www.who.int/publications/i/item/9789241549950)")
    st.markdown("• [Sphere Handbook Ch.6](https://handbook.spherestandards.org/en/sphere/#ch006)")

    st.divider()
    if st.button("🔄 Sync Live Data"):
        st.rerun()

# --- 3. THE "HEADER-BLIND" MATH ENGINE ---
raw_data = fetch_live_data()
valid_readings =[]

for sheet_name, rows in raw_data.items():
    df = pd.DataFrame(rows)
    if df.empty: continue
    
    # Grab the year from the sheet tab name
    year_match = re.search(r'20\d{2}', sheet_name)
    sheet_year = year_match.group(0) if year_match else "2026"
    
    # SCAN EVERY ROW (Ignoring headers, titles, and blank spaces)
    for _, row in df.iterrows():
        if len(row) >= 3:
            d_val = str(row.iloc[0]).strip() # Date
            t_val = str(row.iloc[1]).strip() # Time
            r_val = str(row.iloc[2]).strip() # Meter Reading
            
            # If the row has an AM/PM time and a date, it is a valid data log
            if d_val and ("AM" in t_val.upper() or "PM" in t_val.upper()):
                # Extract ONLY the numbers from the meter reading (ignores text)
                r_clean = re.sub(r'[^\d.]', '', r_val)
                if r_clean:
                    # Stitch the Date and Year together so the chart doesn't break
                    if len(d_val.split()) <= 2:
                        ts_str = f"{d_val} {sheet_year} {t_val}"
                    else:
                        ts_str = f"{d_val} {t_val}"
                        
                    ts = pd.to_datetime(ts_str, errors='coerce')
                    if pd.notnull(ts):
                        valid_readings.append({
                            'Timestamp': ts,
                            'Date': ts.date(),
                            'Time': t_val.upper(),
                            'Reading': float(r_clean)
                        })

# CALCULATE THE 24H DELTAS
if valid_readings:
    # Sort chronologically from Sept to March
    df_logs = pd.DataFrame(valid_readings).sort_values('Timestamp').drop_duplicates('Timestamp').reset_index(drop=True)
    
    # THE MATH: Current Meter Reading minus Previous Meter Reading
    df_logs['Usage'] = df_logs['Reading'].diff().fillna(0)
    # Clean up any negative numbers if the meter reset
    df_logs['Usage'] = df_logs['Usage'].apply(lambda x: x if x >= 0 else 0)
    
    daily_stats =[]
    # Group by the specific day
    for d, g in df_logs.groupby('Date'):
        # Overnight Usage = The math calculated at the AM reading
        ov = g[g['Time'].str.contains('AM')]['Usage'].sum()
        # Daytime Usage = The math calculated at the PM reading
        dt = g[g['Time'].str.contains('PM')]['Usage'].sum()
        
        daily_stats.append({
            'Date': d,
            'Overnight': ov,
            'Daytime': dt,
            'Total': ov + dt
        })
    master_df = pd.DataFrame(daily_stats)
else:
    master_df = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])

# --- 4. MATCH CALENDAR DATA ---
ov_v, dt_v, tot_v, lpcd, eff = 0.0, 0.0, 0.0, 0.0, 0.0
if not master_df.empty:
    match = master_df[master_df['Date'] == selected_op_date]
    if not match.empty:
        res = match.iloc[0]
        ov_v, dt_v, tot_v = res['Overnight'], res['Daytime'], res['Total']
        lpcd = (tot_v * 1000) / campus_pop
        eff = (target_lpcd / lpcd * 100) if lpcd > 0 else 0

# --- 5. DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")

if tot_v == 0 and not master_df.empty:
    st.warning(f"⚠️ No meter reading found for {selected_op_date.strftime('%B %d, %Y')}. Displaying 0.0.")

# ROW 1: THE THREE DIVISIONS + LPCD
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³", "8:00 AM Delta")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³", "4:00 PM Delta")
c3.metric("Total 24h Production", f"{tot_v:.1f} m³", "Day + Night")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse")

st.divider()

v_left, v_right = st.columns([2.2, 0.8])

with v_left:
    # THE RESTORED DROPDOWN
    chart_view = st.selectbox("Select Performance View",["Overlapping Usage (Day vs Night)", "Daily LPCD Index", "Efficiency Trend"])
    
    if not master_df.empty:
        fig = go.Figure()
        
        if "Overlapping" in chart_view:
            # The Green & Blue SaaS Chart
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Daytime'], mode='lines', line_shape='spline', name='Daytime', line=dict(width=4, color='#85C1E9'), fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['Overnight'], mode='lines', line_shape='spline', name='Overnight', line=dict(width=4, color='#82E0AA'), fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
        elif "LPCD" in chart_view:
            master_df['lpcd_plot'] = (master_df['Total'] * 1000) / campus_pop
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['lpcd_plot'], mode='lines', line_shape='spline', name='24h LPCD', line=dict(width=4, color='#1B263B'), fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=master_df['Date'], y=[target_lpcd]*len(master_df), name="WHO Target", line=dict(color="red", dash='dash')))
        else: # Efficiency
            master_df['eff_plot'] = (target_lpcd / ((master_df['Total'] * 1000) / campus_pop) * 100).fillna(0)
            fig.add_trace(go.Scatter(x=master_df['Date'], y=master_df['eff_plot'], mode='lines', line_shape='spline', name='Efficiency %', line=dict(width=4, color='#F8C471'), fill='tozeroy', fillcolor='rgba(248, 196, 113, 0.2)'))

        # HIGHLIGHT THE SELECTED CALENDAR DATE
        if tot_v > 0:
            y_val = dt_v if "Overlapping" in chart_view else (tot_v*1000/campus_pop if "LPCD" in chart_view else eff)
            fig.add_trace(go.Scatter(x=[selected_op_date], y=[y_val], mode='markers', name="Selected", marker=dict(color='#1B263B', size=15, line=dict(width=3, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with v_right:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = eff,
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#1B263B"},
                 'steps': [{'range': [0, 50], 'color': "#FFEBEE"}, {'range': [50, 85], 'color': "#FFF9C4"}, {'range':[85, 100], 'color': "#E8F5E9"}]}))
    fig_gauge.update_layout(height=400, margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# --- 6. EXPORTS ---
st.divider()
st.subheader("📥 Data Download Center")
if raw_data:
    sel = st.selectbox("Select Log for Download", list(raw_data.keys()))
    df_dl = pd.DataFrame(raw_data[sel])
    c1, c2 = st.columns(2)
    c1.download_button("💾 Download CSV", df_dl.to_csv(index=False), f"{sel}.csv")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df_dl.to_excel(writer, index=False)
    c2.download_button("📂 Download Excel", buf.getvalue(), f"{sel}.xlsx")
# Developer Transparency Log (so you can see the math worked)
with st.expander("🛠️ View Calculated Background Math (Engineering Verification)"):
    st.dataframe(master_df)
