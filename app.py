import streamlit as st
import pandas as pd
import os
import json
import boto3
from glob import glob

# --- CONFIGURATION ---
st.set_page_config(
    page_title="LeadMiner AI Dashboard Pro",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for a more advanced look
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
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #4facfe;
    }
    .metric-label {
        font-size: 1rem;
        color: #a0a0b0;
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


# --- BEDROCK INTEGRATION ---
def generate_pitch_with_opus(lead_data, offering_context, region):
    try:
        bedrock = boto3.client(service_name='bedrock-runtime', region_name=region)
        
        # Use standard model ID for Opus 4 (or cross-region if needed, but standard is often supported directly)
        model_id = 'anthropic.claude-opus-4-20250514-v1:0'
        
        prompt = f"""You are an elite, top-performing B2B sales development representative. 
Your task is to write a highly personalized, compelling, and concise cold outreach pitch for the following lead.

Target Lead Information:
{json.dumps(lead_data, indent=2)}

Our Product/Service Offering:
{offering_context}

Instructions:
1. Write a catchy and relevant subject line.
2. Personalize the opening based on their business name or location.
3. Clearly state the value proposition based on our offering.
4. Keep the email concise (under 150 words) and professional.
5. End with a soft, clear call-to-action (CTA).
6. Do NOT include placeholder tags like [Your Name], just provide the template text body."""

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1500,
            "temperature": 0.7,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        })
        
        response = bedrock.invoke_model(body=body, modelId=model_id)
        response_body = json.loads(response.get('body').read())
        return response_body['content'][0]['text']
    except Exception as e:
        return f"Error invoking AWS Bedrock (Opus 4): {e}"


# --- APP CORE ---
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

@st.cache_data
def load_data(file_path):
    try:
        xls = pd.ExcelFile(file_path)
        return {sheet: xls.parse(sheet) for sheet in xls.sheet_names}
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None

def main():
    # Sidebar Navigation & Settings
    st.sidebar.title("💎 LeadMiner Pro")
    st.sidebar.markdown("Advanced AI-Powered Lead Intelligence")
    
    st.sidebar.subheader("AWS Bedrock Settings")
    aws_region = st.sidebar.selectbox("AWS Region", ["us-east-1", "us-west-2", "eu-central-1", "ap-southeast-2"], index=1)
    
    # Check output directory
    if not os.path.exists(OUTPUT_DIR):
        st.warning(f"Output directory not found at {OUTPUT_DIR}. Please run the scraper first.")
        return

    excel_files = glob(os.path.join(OUTPUT_DIR, "*.xlsx"))
    excel_files.sort(key=os.path.getmtime, reverse=True)

    if not excel_files:
        st.info("No scraped results found. Run the scraper to generate some leads!")
        return

    st.sidebar.subheader("📁 Select Dataset")
    file_names = [os.path.basename(f) for f in excel_files]
    selected_file_name = st.sidebar.selectbox("Choose a batch file:", file_names)
    
    # Main content area
    st.title("LeadMiner Pro: Intelligence Dashboard")
    
    if selected_file_name:
        selected_file_path = os.path.join(OUTPUT_DIR, selected_file_name)
        dfs = load_data(selected_file_path)
        
        if not dfs:
            return
            
        sheet_name = st.sidebar.selectbox("Select Sheet:", list(dfs.keys()))
        df = dfs[sheet_name]
        
        # Dashboard Layout Tabs
        tab_overview, tab_data, tab_ai_pitch = st.tabs(["📈 Overview", "🗃️ Data Explorer", "🤖 AI Pitch Generator (Opus 4)"])
        
        with tab_overview:
            st.header("Campaign Overview")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f'<div class="metric-card"><div class="metric-value">{len(df)}</div><div class="metric-label">Total Leads Extracted</div></div>', unsafe_allow_html=True)
            with col2:
                # Estimate emails found if column exists
                emails_count = len(df[df['Email'].notna()]) if 'Email' in df.columns else "N/A"
                st.markdown(f'<div class="metric-card"><div class="metric-value">{emails_count}</div><div class="metric-label">Emails Found</div></div>', unsafe_allow_html=True)
            with col3:
                phones_count = len(df[df['Phone'].notna()]) if 'Phone' in df.columns else "N/A"
                st.markdown(f'<div class="metric-card"><div class="metric-value">{phones_count}</div><div class="metric-label">Phone Numbers Found</div></div>', unsafe_allow_html=True)
                
            st.markdown("<br>", unsafe_allow_html=True)
            with open(selected_file_path, "rb") as file:
                st.download_button(
                    label="📥 Download Full Dataset (Excel)",
                    data=file,
                    file_name=selected_file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

        with tab_data:
            st.header("Data Explorer")
            # Quick search filter
            search_query = st.text_input("🔍 Quick Search (Name, Category, etc.)")
            filtered_df = df
            if search_query:
                # Basic string contains filter across all string columns
                mask = filtered_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
                filtered_df = filtered_df[mask]
                
            st.dataframe(filtered_df, use_container_width=True, height=500)
            
        with tab_ai_pitch:
            st.header("AI Pitch Generator")
            st.markdown("Powered by **AWS Bedrock (Claude Opus 4)**")
            
            col_a, col_b = st.columns([1, 2])
            
            with col_a:
                st.subheader("1. Configure Context")
                offering_context = st.text_area(
                    "Our Offering (What are we selling?)", 
                    value="We are a digital marketing agency specializing in local SEO and high-conversion web design. We help small businesses dominate local search and capture more foot traffic.",
                    height=150
                )
                
                st.subheader("2. Select Lead")
                # Create a readable identifier for the dropdown
                if 'Name' in df.columns:
                    lead_options = df['Name'].dropna().tolist()
                else:
                    lead_options = [f"Lead #{i}" for i in range(len(df))]
                    
                selected_lead_name = st.selectbox("Choose a target lead", lead_options)
                
            with col_b:
                st.subheader("3. Generate Pitch")
                if st.button("🚀 Generate Pitch with Claude Opus 4", type="primary", use_container_width=True):
                    with st.spinner("Claude Opus 4 is crafting the perfect pitch..."):
                        # Get the specific lead data
                        if 'Name' in df.columns:
                            lead_row = df[df['Name'] == selected_lead_name].iloc[0].to_dict()
                        else:
                            idx = int(selected_lead_name.replace("Lead #", ""))
                            lead_row = df.iloc[idx].to_dict()
                            
                        # Clean up NaN values for JSON serialization
                        lead_row = {k: v for k, v in lead_row.items() if pd.notna(v)}
                        
                        pitch_result = generate_pitch_with_opus(lead_row, offering_context, aws_region)
                        
                        st.success("Pitch Generated Successfully!")
                        st.markdown("### Generated Outreach Email")
                        st.info(pitch_result)

if __name__ == "__main__":
    main()
