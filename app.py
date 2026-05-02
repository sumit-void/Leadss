import streamlit as st
import pandas as pd
import os
import io
import sqlite3

# --- CONFIGURATION ---
st.set_page_config(
    page_title="LeadMiner Pro - CRM Dashboard",
    page_icon="🗃️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for an advanced, modern look
st.markdown("""
<style>
    .reportview-container .main .block-container{
        padding-top: 2rem;
    }
    .metric-card {
        background-color: #1e1e2f;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        text-align: center;
        border-left: 4px solid #4facfe;
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: bold;
        color: #4facfe;
    }
    .metric-label {
        font-size: 1rem;
        color: #a0a0b0;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    /* Style the dataframe to look better */
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)


# --- PASSWORD PROTECTION ---
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "leadminer2026")

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == DASHBOARD_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Enter Dashboard Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Dashboard Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Password incorrect")
        return False
    else:
        return True

if not check_password():
    st.stop()


# --- DATABASE INTEGRATION ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leadminer.db")

def load_data_from_db():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM leads ORDER BY created_at DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def update_status_in_db(lead_id, new_status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE leads SET status = ? WHERE id = ?', (new_status, lead_id))
    conn.commit()
    conn.close()

def convert_df_to_excel(df):
    """Convert pandas dataframe to an in-memory Excel file for downloading."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Filtered_Leads')
    return output.getvalue()


def main():
    # Sidebar Navigation & Settings
    st.sidebar.title("🗃️ LeadMiner Data Hub")
    st.sidebar.markdown("Advanced Lead CRM System")
    st.sidebar.divider()
    
    # Load entire master database
    df = load_data_from_db()
    
    if df.empty:
        st.warning(f"Database is empty or missing. Please run the scraper first.")
        return

    # Filter by specific queries or Global Merged Output
    queries = ["Global Merged Master List"] + sorted(df['query'].dropna().unique().tolist())
    selected_query = st.sidebar.selectbox("📁 Select Batch View:", queries)
    
    if selected_query != "Global Merged Master List":
        df = df[df['query'] == selected_query]

    # Main content area
    st.title("Data Intelligence CRM")
    st.markdown("Filter, edit, map, and export your high-quality leads.")
    
    # Dashboard Layout Tabs
    tab_overview, tab_explorer, tab_map, tab_analytics = st.tabs([
        "📈 Campaign Overview", 
        "🔍 Advanced Data CRM", 
        "🌍 Geospatial Map", 
        "📊 Analytics"
    ])
    
    with tab_overview:
        st.header("Dataset Summary")
        
        # Calculate raw metrics
        total_leads = len(df)
        emails_count = len(df[df['email'].notna() & (df['email'] != "")])
        phones_count = len(df[df['phone'].notna() & (df['phone'] != "")])
        websites_count = len(df[df['website'].notna() & (df['website'] != "")])
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{total_leads}</div><div class="metric-label">Total Leads</div></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{emails_count}</div><div class="metric-label">Emails Found</div></div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{phones_count}</div><div class="metric-label">Phones Found</div></div>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<div class="metric-card"><div class="metric-value">{websites_count}</div><div class="metric-label">Websites Found</div></div>', unsafe_allow_html=True)
            
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # Direct Download of the entire original file
        st.subheader("📥 Direct Download")
        st.markdown("Download the raw, unfiltered Excel file for this view.")
        excel_data_all = convert_df_to_excel(df)
        st.download_button(
            label="📥 Download View as Excel",
            data=excel_data_all,
            file_name=f"leadminer_{selected_query.replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with tab_explorer:
        # --- FILTERING SECTION ---
        st.header("Advanced Lead Filter & CRM")
        
        with st.expander("⚙️ Filter Controls", expanded=True):
            search_query = st.text_input("🔍 Global Keyword Search (Name, Address, etc.)", placeholder="e.g. 'Clinic' or 'New York'")
            
            col_f1, col_f2, col_f3 = st.columns(3)
            
            # Checkbox Filters
            with col_f1:
                st.markdown("**Essential Data Filters**")
                must_have_email = st.checkbox("✉️ Must have Email Address")
                must_have_phone = st.checkbox("☎️ Must have Phone Number")
                must_have_website = st.checkbox("🌐 Must have Website")
            
            # Category & Status Filter
            with col_f2:
                st.markdown("**Category & Status Filters**")
                categories = sorted(df['category'].dropna().unique().tolist())
                selected_categories = st.multiselect("Filter by Category:", categories)
                
                statuses = sorted(df['status'].dropna().unique().tolist())
                selected_statuses = st.multiselect("Filter by CRM Status:", statuses, default=statuses)
            
            # Rating Filter
            with col_f3:
                st.markdown("**Rating Filter**")
                min_rating = st.slider("Minimum Rating", min_value=0.0, max_value=5.0, value=0.0, step=0.1)

        # --- APPLY FILTERS ---
        filtered_df = df.copy()
        
        # Global Search
        if search_query:
            mask = filtered_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            filtered_df = filtered_df[mask]
            
        # Boolean filters
        if must_have_email:
            filtered_df = filtered_df[filtered_df['email'].notna() & (filtered_df['email'].astype(str).str.strip() != "")]
            
        if must_have_phone:
            filtered_df = filtered_df[filtered_df['phone'].notna() & (filtered_df['phone'].astype(str).str.strip() != "")]
            
        if must_have_website:
            filtered_df = filtered_df[filtered_df['website'].notna() & (filtered_df['website'].astype(str).str.strip() != "")]
            
        # Category filter
        if selected_categories:
            filtered_df = filtered_df[filtered_df['category'].isin(selected_categories)]
            
        # Status filter
        if selected_statuses:
            filtered_df = filtered_df[filtered_df['status'].isin(selected_statuses)]
            
        # Rating filter
        if min_rating > 0.0:
            filtered_df['numeric_rating'] = pd.to_numeric(filtered_df['rating'], errors='coerce').fillna(0)
            filtered_df = filtered_df[filtered_df['numeric_rating'] >= min_rating]
            filtered_df = filtered_df.drop(columns=['numeric_rating'])

        # --- DISPLAY EDITABLE CRM TABLE ---
        st.markdown("### 📊 Interactive Lead Table")
        st.caption(f"Showing **{len(filtered_df)}** out of {len(df)} leads. (Editable 'status' column)")
        
        # Configure columns for data editor
        column_config = {
            "id": None, # Hide ID
            "status": st.column_config.SelectboxColumn(
                "Status",
                help="CRM Status of the lead",
                width="medium",
                options=[
                    "New",
                    "Contacted - Email",
                    "Contacted - Phone",
                    "Interested",
                    "Meeting Booked",
                    "Rejected"
                ],
            ),
            "website": st.column_config.LinkColumn("Website")
        }
        
        # Editable dataframe
        edited_df = st.data_editor(
            filtered_df,
            use_container_width=True,
            hide_index=True,
            column_config=column_config,
            disabled=[col for col in filtered_df.columns if col != 'status'],
            key="lead_crm_editor"
        )
        
        # Detect changes and save to SQLite
        if "lead_crm_editor" in st.session_state and "edited_rows" in st.session_state.lead_crm_editor:
            changes = st.session_state.lead_crm_editor["edited_rows"]
            if changes:
                for row_idx, edit_data in changes.items():
                    if 'status' in edit_data:
                        # Get the actual ID of the lead that was edited
                        actual_lead_id = filtered_df.iloc[int(row_idx)]['id']
                        new_status = edit_data['status']
                        update_status_in_db(int(actual_lead_id), new_status)
                st.success("Changes saved to database!", icon="✅")
        
        # Export Filtered Data
        st.markdown("---")
        if len(filtered_df) > 0:
            excel_data = convert_df_to_excel(filtered_df)
            st.download_button(
                label="📤 Export Filtered Leads to Excel",
                data=excel_data,
                file_name=f"filtered_leads_{selected_query.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

    with tab_map:
        st.header("Geospatial Map")
        st.markdown("Visual distribution of your scraped leads.")
        
        # Streamlit st.map requires columns named exactly "latitude" and "longitude" or "lat" and "lon"
        map_df = filtered_df.copy()
        
        if 'lat' in map_df.columns and 'lng' in map_df.columns:
            # Rename for st.map compatibility
            map_df = map_df.rename(columns={'lat': 'latitude', 'lng': 'longitude'})
            
            # Drop rows without coordinates
            map_df = map_df.dropna(subset=['latitude', 'longitude'])
            
            if len(map_df) > 0:
                st.map(map_df, use_container_width=True, height=600)
                st.caption(f"Showing {len(map_df)} plotted leads based on current filters.")
            else:
                st.info("None of the filtered leads have GPS coordinates available.")
        else:
            st.info("Latitude and Longitude columns are missing from the database.")

    with tab_analytics:
        st.header("Analytics")
        col_a1, col_a2 = st.columns(2)
        
        with col_a1:
            st.subheader("Leads by Category")
            if 'category' in filtered_df.columns:
                cat_counts = filtered_df['category'].value_counts().reset_index()
                cat_counts.columns = ['Category', 'Count']
                st.bar_chart(cat_counts.set_index('Category'))
                
        with col_a2:
            st.subheader("CRM Pipeline Status")
            if 'status' in filtered_df.columns:
                stat_counts = filtered_df['status'].value_counts().reset_index()
                stat_counts.columns = ['Status', 'Count']
                st.bar_chart(stat_counts.set_index('Status'))

if __name__ == "__main__":
    main()
