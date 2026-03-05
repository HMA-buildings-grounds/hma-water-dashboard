import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import create_engine
import io

# --- 1. SETTINGS & THEMING ---
st.set_page_config(page_title="HMA Water Intelligence", page_icon="💧", layout="wide")

# Professional UI Styling (Navy/Teal/Slate)
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    div[data-testid="stMetricValue"] { color: #0D9488; font-size: 32px; font-weight: 700; }
    .stButton>button { border-radius: 8px; background-color: #0D9488; color: white; }
    [data-testid="stSidebar"] { background-color: #1B263B; border-right: 1px solid #e2e8f0; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATA ENGINES (TiDB & Google Sheets) ---

@st.cache_resource
def get_tidb_engine():
    # Credentials from .streamlit/secrets.toml
    creds = st.secrets["tidb"]
    url = f"mysql+mysqlconnector://{creds['user']}:{creds['password']}@{creds['host']}:{creds['port']}/{creds['database']}?ssl_disabled=False"
    return create_engine(url)

@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

def fetch_all_google_sheets(spreadsheet_id):
    client = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    all_sheets_data = {}
    for worksheet in sh.worksheets():
        df = pd.DataFrame(worksheet.get_all_records())
        all_sheets_data[worksheet.title] = df
    return all_sheets_data

# --- 3. SIDEBAR NAVIGATION ---
with st.sidebar:
    st.image("https://via.placeholder.com/150x50?text=HMA+LOGO", use_column_width=True) # Place your logo here
    selected = option_menu(
        "Main Menu", 
        ["Home", "Consumption Logs", "Gallery"], 
        icons=["house", "cloud-download", "images"], 
        menu_icon="cast", 
        default_index=0,
        styles={
            "container": {"background-color": "#1B263B", "padding": "5px"},
            "icon": {"color": "#0D9488", "font-size": "18px"}, 
            "nav-link": {"color": "white", "font-size": "14px", "text-align": "left", "margin":"0px"},
            "nav-link-selected": {"background-color": "#415A77"},
        }
    )
    st.divider()
    if st.sidebar.button("🔄 Global Refresh"):
        st.cache_data.clear()
        st.rerun()

# --- 4. VIEW LOGIC ---

if selected == "Home":
    st.title("Campus Water Management Dashboard")
    
    # KPI SECTION
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Daily Production", "4,250 kL", "+2.5%")
    with col2: st.metric("Facility Consumption", "3,120 kL", "-1.2%")
    with col3: st.metric("Active Wells", "8 / 10", "Operational")
    with col4: st.metric("System Health", "94%", "High")

    # TREND SECTION (Mock Data - Replace with TiDB Query)
    st.subheader("Production vs Consumption Trends")
    df_trend = pd.DataFrame({
        'Date': pd.date_range(start='2024-01-01', periods=12, freq='M'),
        'Production': [400, 450, 420, 500, 550, 600, 580, 590, 610, 630, 650, 640],
        'Consumption': [380, 400, 390, 450, 480, 500, 490, 510, 530, 550, 570, 560]
    })
    fig = px.area(df_trend, x='Date', y=['Production', 'Consumption'], 
                  color_discrete_map={"Production": "#0D9488", "Consumption": "#415A77"},
                  template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)

elif selected == "Consumption Logs":
    st.title("Water Production & Facility Logs")
    
    # 1. Fetch data from EVERY sheet
    try:
        sheets_dict = fetch_all_google_sheets(st.secrets["google_sheets"]["spreadsheet_id"])
        
        # 2. Selector for which sheet to view
        target_sheet = st.selectbox("Select Facility Sheet", options=list(sheets_dict.keys()))
        df = sheets_dict[target_sheet]

        # 3. Filters
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            date_range = st.date_input("Filter by Date Range", [])
        
        # 4. Professional Table View
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 5. DOWNLOAD SECTION (Excel / CSV)
        st.subheader("📥 Export Center")
        d_col1, d_col2, d_col3 = st.columns(3)
        
        # CSV Download
        csv = df.to_csv(index=False).encode('utf-8')
        d_col1.download_button("Download CSV", data=csv, file_name=f"{target_sheet}_log.csv", mime="text/csv")

        # Multi-sheet Excel Download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for name, data in sheets_dict.items():
                data.to_excel(writer, sheet_name=name[:31], index=False)
        d_col2.download_button("Download All Sheets (Excel)", data=output.getvalue(), file_name="Campus_Water_Full_Log.xlsx")
        
        # PDF Links (WHO References)
        d_col3.link_button("WHO Water Quality Standards (PDF)", "https://www.who.int/publications/i/item/9789241549950")

    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")

elif selected == "Gallery":
    st.title("Facility Documentation Gallery")
    # Responsive Grid for Photos
    gal_cols = st.columns(3)
    # Placeholder images - replace with your actual facility URLs or local paths
    for i in range(6):
        with gal_cols[i % 3]:
            st.image("https://via.placeholder.com/400x300?text=Well+Site+"+str(i+1), 
                     caption=f"Facility Site {i+1} - Status: Operational", use_column_width=True)
