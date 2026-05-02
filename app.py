import streamlit as st
import pandas as pd
import os
from glob import glob

# --- CONFIGURATION ---
st.set_page_config(
    page_title="LeadMiner AI Dashboard",
    page_icon="💼",
    layout="wide",
)

# --- PASSWORD PROTECTION ---
# For a real EC2 deployment, use environment variables or a secure secret store.
# This is a basic hardcoded password for the prototype.
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "leadminer2026")

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == DASHBOARD_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Enter Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error.
        st.text_input(
            "Enter Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct.
        return True

if not check_password():
    st.stop()  # Do not continue if check_password is False.


# --- DASHBOARD APP ---
st.title("🚀 LeadMiner AI Dashboard")
st.markdown("View and download your AI-enriched lead lists.")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

@st.cache_data
def load_data(file_path):
    """Load the Excel file into a dictionary of pandas DataFrames (one per sheet)."""
    try:
        # Read all sheets
        xls = pd.ExcelFile(file_path)
        dfs = {sheet: xls.parse(sheet) for sheet in xls.sheet_names}
        return dfs
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None

def main():
    # 1. Find all Excel files in the output directory
    if not os.path.exists(OUTPUT_DIR):
        st.warning(f"Output directory not found at {OUTPUT_DIR}. Please run the scraper first.")
        return

    excel_files = glob(os.path.join(OUTPUT_DIR, "*.xlsx"))
    excel_files.sort(key=os.path.getmtime, reverse=True) # Newest first

    if not excel_files:
        st.info("No scraped results found. Run the scraper to generate some leads!")
        return

    # 2. Select file
    st.subheader("📁 Select Results File")
    file_names = [os.path.basename(f) for f in excel_files]
    selected_file_name = st.selectbox("Choose a batch file to view:", file_names)
    
    if selected_file_name:
        selected_file_path = os.path.join(OUTPUT_DIR, selected_file_name)
        
        # 3. Download Button
        with open(selected_file_path, "rb") as file:
            btn = st.download_button(
                label="📥 Download Full Excel File",
                data=file,
                file_name=selected_file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        st.markdown("---")

        # 4. Load Data
        dfs = load_data(selected_file_path)
        if dfs:
            st.subheader(f"📊 Data Viewer")
            
            # Select sheet
            sheet_name = st.selectbox("Select Sheet:", list(dfs.keys()))
            df = dfs[sheet_name]
            
            # Show summary stats
            st.write(f"**Total records in this sheet:** {len(df)}")
            
            # Interactive Table
            st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    main()
