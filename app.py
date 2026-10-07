import io
import re

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# --- 1. SETTINGS & CSS ---
st.set_page_config(page_title="HMA Water Intelligence", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    [data-testid="stSidebar"] { background-color: #1B263B !important; }
    [data-testid="stSidebar"] .stMarkdown,[data-testid="stSidebar"] label, [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h3 { color: white !important; }
    [data-testid="stSidebar"] input { color: #1B263B !important; background-color: white !important; border-radius: 5px; }
    [data-testid="stMetricValue"] { color: #1B263B; font-size: 38px; font-weight: 800; }
    .stMetric { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)


# --- 2. DATA LAYER ---
@st.cache_data(ttl=60)  # refresh at most once a minute (was 2s, which hammers the Google script)
def fetch_live_data():
    """Returns (data, error_message). Errors are shown to the user instead of hidden."""
    try:
        api_url = st.secrets["google_sheets"]["api_url"]
    except Exception:
        return {}, "Missing secret: google_sheets.api_url (add it in Streamlit secrets)."
    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return {}, f"Could not load data from Google Sheets: {exc}"


@st.cache_data(ttl=60)
def build_master(raw_data):
    """Turn raw meter readings into one row per day: Overnight, Daytime, Total (m3)."""
    empty = pd.DataFrame(columns=['Date', 'Overnight', 'Daytime', 'Total'])
    readings = []

    for sheet_name, rows in raw_data.items():
        df = pd.DataFrame(rows)
        if df.empty:
            continue

        year_match = re.search(r'20\d{2}', sheet_name)
        year = year_match.group(0) if year_match else "2026"

        for _, row in df.iterrows():
            try:
                d_val = str(row.iloc[0]).strip()
                t_val = str(row.iloc[1]).strip()
                m_val = str(row.iloc[2]).strip()

                if not d_val or d_val.lower() in ['nan', 'date']:
                    continue
                if not any(c.isdigit() for c in m_val):
                    continue

                m_num = float(re.search(r"[-+]?\d*\.\d+|\d+", m_val.replace(",", "")).group())
                d_str = d_val + " " + t_val if re.search(r'20\d{2}', d_val) else f"{d_val} {year} {t_val}"
                ts = pd.to_datetime(d_str, errors='coerce')
                if pd.isnull(ts):
                    continue

                readings.append({
                    'Timestamp': ts,
                    'DateOnly': ts.date(),
                    'IsMorning': ts.hour < 12,  # real hour check, not text matching
                    'Reading': m_num,
                })
            except Exception:
                continue

    if not readings:
        return empty

    df_r = (pd.DataFrame(readings)
            .sort_values('Timestamp')
            .drop_duplicates('Timestamp')
            .reset_index(drop=True))
    df_r['Usage'] = df_r['Reading'].diff().fillna(0)
    df_r.loc[df_r['Usage'] < 0, 'Usage'] = 0  # meter reset / typo guard

    daily = []
    for d, g in df_r.groupby('DateOnly'):
        day = g[~g['IsMorning']]['Usage'].sum()
        night = g[g['IsMorning']]['Usage'].sum()
        daily.append({'Date': pd.to_datetime(d), 'Overnight': night, 'Daytime': day, 'Total': day + night})

    master = pd.DataFrame(daily).sort_values('Date').reset_index(drop=True)

    # Anomaly flag: today's total is more than 2 standard deviations above the previous 14-day average
    prior = master['Total'].shift(1)
    roll_mean = prior.rolling(14, min_periods=7).mean()
    roll_std = prior.rolling(14, min_periods=7).std()
    master['Anomaly'] = master['Total'] > (roll_mean + 2 * roll_std)
    return master


raw_data, load_error = fetch_live_data()
master = build_master(raw_data) if raw_data else pd.DataFrame(
    columns=['Date', 'Overnight', 'Daytime', 'Total', 'Anomaly'])

# --- 3. SIDEBAR ---
with st.sidebar:
    try:
        st.image("assets/HMA_logo_color.jpg", use_container_width=True)
    except Exception:
        st.markdown("<h2 style='text-align:center; color:#1ABB9C;'>HMA WATER</h2>", unsafe_allow_html=True)

    st.markdown("### Operational Controls")
    campus_pop = st.number_input("Campus Population", value=370, min_value=1)
    target_lpcd = st.number_input("Baseline Target (LPCD)", value=50, min_value=35, max_value=100)

    if not master.empty:
        min_d, max_d = master['Date'].min().date(), master['Date'].max().date()
        selected_op_date = st.date_input("Operational Date", value=max_d, min_value=min_d, max_value=max_d)
    else:
        selected_op_date = st.date_input("Operational Date")

    st.divider()
    st.markdown("### 📖 Standards & References")
    st.markdown("""
        <div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">
            <a href="https://www.who.int/publications/i/item/9789241549950" target="_blank" style="color:#85C1E9; text-decoration:none;">📘 WHO Water Standards</a><br><br>
            <a href="https://handbook.spherestandards.org/en/sphere/#ch006" target="_blank" style="color:#85C1E9; text-decoration:none;">🌍 Sphere Handbook Ch.6</a>
        </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Sync Live Data"):
        st.cache_data.clear()
        st.rerun()

# --- 4. CALCULATIONS FOR SELECTED DAY ---
ov_v = dt_v = tot_v = lpcd = eff = 0.0
is_anomaly = False

if not master.empty:
    match = master[master['Date'].dt.date == selected_op_date]
    if not match.empty:
        row = match.iloc[0]
        ov_v, dt_v, tot_v = row['Overnight'], row['Daytime'], row['Total']
        is_anomaly = bool(row['Anomaly'])
        lpcd = (tot_v * 1000) / campus_pop
        eff = min((target_lpcd / lpcd * 100), 100) if lpcd > 0 else 0

# --- 5. DASHBOARD UI ---
st.title("Operational Diagnostics & Performance")

if load_error:
    st.error(load_error)
elif master.empty:
    st.info("No readings found yet. Add readings to the sheet, then click 'Sync Live Data'.")
elif tot_v == 0:
    st.warning(f"⚠️ No meter reading data calculated for {selected_op_date.strftime('%B %d, %Y')}.")
elif is_anomaly:
    st.error("🚨 Unusually high consumption vs the previous 14 days. Check for leaks, "
             "overflowing tanks or running pumps.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Overnight Usage", f"{ov_v:.1f} m³")
c2.metric("Daytime Usage", f"{dt_v:.1f} m³")
c3.metric("Total 24h Usage", f"{tot_v:.1f} m³")
c4.metric("Current LPCD", f"{lpcd:.1f}", f"{lpcd - target_lpcd:.1f} vs Target", delta_color="inverse")

st.divider()

l_col, r_col = st.columns([2.2, 0.8])

with l_col:
    view = st.selectbox("Select 24h Trend View",
                        ["Usage Analysis (Day vs Night)", "Total LPCD Index", "Efficiency Trend"])

    if not master.empty:
        plot = master.copy()
        plot['lpcd_p'] = (plot['Total'] * 1000) / campus_pop
        plot['eff_p'] = (target_lpcd / plot['lpcd_p']).replace([float('inf')], 0).fillna(0).mul(100).clip(upper=100)

        fig = go.Figure()
        if "Usage" in view:
            fig.add_trace(go.Scatter(x=plot['Date'], y=plot['Daytime'], mode='lines', line_shape='spline',
                                     name='Daytime Use', line=dict(width=3, color='#85C1E9'),
                                     fill='tozeroy', fillcolor='rgba(133, 193, 233, 0.2)'))
            fig.add_trace(go.Scatter(x=plot['Date'], y=plot['Overnight'], mode='lines', line_shape='spline',
                                     name='Overnight Use', line=dict(width=3, color='#82E0AA'),
                                     fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
            y_sel = dt_v
        elif "LPCD" in view:
            fig.add_trace(go.Scatter(x=plot['Date'], y=plot['lpcd_p'], mode='lines', line_shape='spline',
                                     name='24h LPCD', line=dict(width=3, color='#1B263B'),
                                     fill='tozeroy', fillcolor='rgba(27, 38, 59, 0.05)'))
            fig.add_trace(go.Scatter(x=plot['Date'], y=[target_lpcd] * len(plot), name="Baseline Target",
                                     line=dict(color="red", dash='dash', width=2)))
            y_sel = lpcd
        else:
            fig.add_trace(go.Scatter(x=plot['Date'], y=plot['eff_p'], mode='lines', line_shape='spline',
                                     name='Efficiency %', line=dict(width=3, color='#82E0AA'),
                                     fill='tozeroy', fillcolor='rgba(130, 224, 170, 0.2)'))
            y_sel = eff

        # Flag anomaly days on the usage view
        if "Usage" in view and plot['Anomaly'].any():
            a = plot[plot['Anomaly']]
            fig.add_trace(go.Scatter(x=a['Date'], y=a['Daytime'] + a['Overnight'], mode='markers',
                                     name='High-use alert', marker=dict(color='red', size=9, symbol='x')))

        if tot_v > 0:
            fig.add_trace(go.Scatter(x=[pd.to_datetime(selected_op_date)], y=[y_sel], mode='markers+text',
                                     name="Selected Day", text=[selected_op_date.strftime('%b %d')],
                                     textposition="top center",
                                     marker=dict(color='orange', size=12, line=dict(width=2, color='white'))))

        fig.update_layout(template="plotly_white", height=450, margin=dict(l=0, r=0, t=20, b=0),
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.markdown("### Efficiency Status")
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=eff,
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "rgba(0,0,0,0)"},
            'bgcolor': "white",
            'borderwidth': 1,
            'bordercolor': "#e2e8f0",
            'steps': [
                {'range': [0, 50], 'color': "#FFEBEE"},
                {'range': [50, 85], 'color': "#FFF9C4"},
                {'range': [85, 100], 'color': "#E8F5E9"},
            ],
            'threshold': {'line': {'color': "#1B263B", 'width': 8}, 'thickness': 0.85, 'value': eff},
        }))
    fig_gauge.update_layout(height=380, margin=dict(l=20, r=20, t=50, b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

# --- 6. DATA EXPORTS & VERIFICATION ---
st.divider()
st.subheader("📥 Data Download Center")
if raw_data:
    sel_sheet = st.selectbox("Select Log for Download", list(raw_data.keys()))
    df_dl = pd.DataFrame(raw_data[sel_sheet])
    d1, d2 = st.columns(2)
    d1.download_button("💾 Download CSV", df_dl.to_csv(index=False), f"{sel_sheet}.csv")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df_dl.to_excel(writer, index=False)
    d2.download_button("📂 Download Excel", buf.getvalue(), f"{sel_sheet}.xlsx")

with st.expander("🛠️ View Calculated Background Math (Engineering Verification)"):
    if not master.empty:
        show = master.copy()
        show['Date'] = show['Date'].dt.strftime('%Y-%m-%d')
        st.dataframe(show, use_container_width=True)
    else:
        st.info("No data calculated yet. Click 'Sync Live Data' after updating the sheet.")

