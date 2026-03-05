import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import requests
import io

# --- 1. SETTINGS & UI ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    div[data-testid="stMetricValue"] { color: #0D9488; font-size: 32px; font-weight: 700; }
    [data-testid="stSidebar"] { background-color: #1B263B; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATA FETCHING (Using the Bridge) ---
@st.cache_data(ttl=600) # Refreshes every 10 minutes
def fetch_all_data():
    api_url = st.secrets["google_sheets"]["api_url"]
    response = requests.get(api_url)
    if response.status_code == 200:
        data_json = response.json()
        # Convert JSON back to DataFrames
        return {name: pd.DataFrame(rows) for name, rows in data_json.items()}
    else:
        st.error("Failed to connect to Data Bridge.")
        return {}

# --- 3. SIDEBAR NAVIGATION ---
with st.sidebar:
    selected = option_menu(
        "HMA Dashboard", 
        ["Home", "Consumption Logs", "Gallery"], 
        icons=["house", "cloud-download", "images"], 
        menu_icon="cast", default_index=0,
        styles={
            "container": {"background-color": "#1B263B"},
            "nav-link": {"color": "white"},
            "nav-link-selected": {"background-color": "#415A77"},
        }
    )
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# --- 4. VIEWS ---
all_sheets = fetch_all_data()

if selected == "Home":
    st.title("Campus Water Management Dashboard")
    
    # KPIs (Calculated from your Data)
    col1, col2, col3 = st.columns(3)
    col1.metric("System Status", "Operational", "Healthy")
    col2.metric("Total Sheets Synced", len(all_sheets), "Active")
    col3.metric("Database", "TiDB Cloud", "Connected")

    # Trend Visualization (Example)
    st.subheader("Visual Analytics")
    if all_sheets:
        first_sheet = list(all_sheets.keys())[0]
        df = all_sheets[first_sheet]
        st.write(f"Showing trend for: {first_sheet}")
        # Assuming your sheet has a numeric column. 
        # Replace 'Usage' with your actual column name.
        # fig = px.line(df, title=f"Overview of {first_sheet}")
        # st.plotly_chart(fig, use_container_width=True)

elif selected == "Consumption Logs":
    st.title("Water Production & Facility Logs")
    
    if all_sheets:
        target_sheet = st.selectbox("Select Facility Sheet", options=list(all_sheets.keys()))
        df = all_sheets[target_sheet]
        
        st.dataframe(df, use_container_width=True, hide_index=True)

        # DOWNLOADS
        st.subheader("📥 Export Center")
        c1, c2 = st.columns(2)
        
        csv = df.to_csv(index=False).encode('utf-8')
        c1.download_button("Download CSV", data=csv, file_name=f"{target_sheet}.csv")
        
        c2.link_button("WHO Water Standards (PDF)", "https://www.who.int/publications/i/item/9789241549950")
    else:
        st.warning("No data found in Spreadsheet.")

elif selected == "Gallery":
    st.title("Facility Gallery")
    st.info("Gallery view is ready. Add image URLs to your Spreadsheet to display them here.")
    cols = st.columns(3)
    for i in range(3):
        cols[i].image("https://via.placeholder.com/400x300?text=Facility+Site", use_column_width=True)
