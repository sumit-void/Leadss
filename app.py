"""
LeadMiner Dashboard — Simple & Clean
  - Tab 1: Leads viewer with batch selector, filters, tabbed Excel export
  - Tab 2: Queries editor
"""

import streamlit as st
import pandas as pd
import os, io, math

from database import get_all_batches, get_leads_by_batch, get_total_lead_count

# --- CONFIG ---
st.set_page_config(page_title="LeadMiner", page_icon="📋", layout="wide")

QUERIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queries.txt")
LEADS_PER_TAB = 20

# --- STYLING ---
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .metric-box {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        padding: 18px; border-radius: 12px; text-align: center;
        border: 1px solid #2a2a4a; margin-bottom: 8px;
    }
    .metric-num { font-size: 2rem; font-weight: 700; color: #4fc3f7; }
    .metric-lbl { font-size: 0.85rem; color: #8899aa; text-transform: uppercase; letter-spacing: 1px; }
    .batch-info { background: #1e1e2f; padding: 10px 16px; border-radius: 8px;
                  border-left: 3px solid #4fc3f7; margin-bottom: 16px; }
</style>
""", unsafe_allow_html=True)


def convert_df_to_tabbed_excel(df, leads_per_tab=20):
    """Convert dataframe to Excel with leads split across tabs of N each."""
    output = io.BytesIO()

    # Clean columns for export
    export_cols = ["name", "phone", "email", "category", "rating", "total_reviews", "address", "query"]
    available_cols = [c for c in export_cols if c in df.columns]
    export_df = df[available_cols].copy()

    # Rename for cleaner headers
    rename_map = {
        "name": "Name", "phone": "Phone", "email": "Email",
        "category": "Category", "rating": "Rating",
        "total_reviews": "Reviews", "address": "Address", "query": "Query"
    }
    export_df = export_df.rename(columns=rename_map)

    total = len(export_df)
    num_tabs = math.ceil(total / leads_per_tab) if total > 0 else 1

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for i in range(num_tabs):
            start = i * leads_per_tab
            end = min(start + leads_per_tab, total)
            chunk = export_df.iloc[start:end].reset_index(drop=True)
            chunk.index = chunk.index + 1  # 1-based index
            sheet_name = f"Leads {start+1}-{end}"
            chunk.to_excel(writer, index=True, index_label="Sr No", sheet_name=sheet_name)

            # Auto-fit columns
            ws = writer.sheets[sheet_name]
            for col_idx, col_name in enumerate(["Sr No"] + list(chunk.columns), 1):
                max_len = max(len(str(col_name)), chunk[col_name].astype(str).str.len().max() if col_name in chunk.columns and len(chunk) > 0 else 5)
                ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 3, 45)

    return output.getvalue()


def main():
    st.title("📋 LeadMiner")

    tab_leads, tab_queries = st.tabs(["📋 Leads", "⚙️ Queries"])

    # ════════════════════════════════════════
    #  TAB 1: LEADS
    # ════════════════════════════════════════
    with tab_leads:
        batches = get_all_batches()

        if not batches:
            st.info("No leads yet. Run the scraper first: `python batch_scraper.py`")
            return

        # --- Batch Selector ---
        batch_options = ["All Batches"] + [f"{b['batch_id']}  ({b['count']} leads)" for b in batches]
        batch_ids = ["All Batches"] + [b['batch_id'] for b in batches]

        col_batch, col_info = st.columns([3, 2])
        with col_batch:
            selected_label = st.selectbox("📁 Select Batch", batch_options, index=0)
            selected_batch = batch_ids[batch_options.index(selected_label)]

        # Load leads
        leads = get_leads_by_batch(selected_batch)
        df = pd.DataFrame(leads)

        if df.empty:
            st.warning("No leads in this batch.")
            return

        with col_info:
            st.markdown(f"""
            <div class="batch-info">
                <b>{selected_batch}</b> — {len(df)} leads loaded
            </div>
            """, unsafe_allow_html=True)

        # --- Metrics ---
        total = len(df)
        phones = len(df[df['phone'].notna() & (df['phone'].astype(str).str.strip() != "")])
        emails = len(df[df['email'].notna() & (df['email'].astype(str).str.strip() != "")])

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="metric-box"><div class="metric-num">{total}</div><div class="metric-lbl">Total Leads</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-box"><div class="metric-num">{phones}</div><div class="metric-lbl">With Phone</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="metric-box"><div class="metric-num">{emails}</div><div class="metric-lbl">With Email</div></div>', unsafe_allow_html=True)

        # --- Filters ---
        with st.expander("🔍 Filters", expanded=False):
            fc1, fc2 = st.columns(2)
            with fc1:
                search = st.text_input("Search (name, address, category...)", placeholder="Type to search...")
                has_email = st.checkbox("Only with email")
            with fc2:
                min_rating = st.slider("Min Rating", 0.0, 5.0, 0.0, 0.5)

                cats = sorted(df['category'].dropna().unique().tolist())
                sel_cats = st.multiselect("Category", cats)

        # Apply filters
        fdf = df.copy()
        if search:
            mask = fdf.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
            fdf = fdf[mask]
        if has_email:
            fdf = fdf[fdf['email'].notna() & (fdf['email'].astype(str).str.strip() != "")]
        if min_rating > 0:
            fdf['_r'] = pd.to_numeric(fdf['rating'], errors='coerce').fillna(0)
            fdf = fdf[fdf['_r'] >= min_rating].drop(columns=['_r'])
        if sel_cats:
            fdf = fdf[fdf['category'].isin(sel_cats)]

        # --- Data Table ---
        st.markdown(f"**Showing {len(fdf)} of {total} leads**")

        display_cols = ["name", "phone", "email", "category", "rating", "total_reviews", "address"]
        available = [c for c in display_cols if c in fdf.columns]

        st.dataframe(
            fdf[available],
            use_container_width=True,
            hide_index=True,
            column_config={
                "name": "Name", "phone": "Phone", "email": "Email",
                "category": "Category", "rating": "Rating",
                "total_reviews": "Reviews", "address": "Address"
            }
        )

        # --- Download ---
        st.markdown("---")
        if len(fdf) > 0:
            num_tabs = math.ceil(len(fdf) / LEADS_PER_TAB)
            excel_data = convert_df_to_tabbed_excel(fdf, LEADS_PER_TAB)

            batch_label = selected_batch.replace(" ", "_") if selected_batch != "All Batches" else "all_leads"
            st.download_button(
                label=f"📥 Download Excel ({len(fdf)} leads → {num_tabs} tabs of {LEADS_PER_TAB})",
                data=excel_data,
                file_name=f"leadminer_{batch_label}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

    # ════════════════════════════════════════
    #  TAB 2: QUERIES
    # ════════════════════════════════════════
    with tab_queries:
        st.header("⚙️ Search Queries")
        st.caption("One query per line. These are used by `python batch_scraper.py`")

        # Load current queries
        current_queries = ""
        if os.path.exists(QUERIES_FILE):
            with open(QUERIES_FILE, "r", encoding="utf-8") as f:
                current_queries = f.read()

        edited = st.text_area(
            "Edit queries.txt",
            value=current_queries,
            height=500,
            label_visibility="collapsed"
        )

        col_save, col_count = st.columns([1, 3])
        with col_save:
            if st.button("💾 Save Queries", type="primary"):
                with open(QUERIES_FILE, "w", encoding="utf-8") as f:
                    f.write(edited)
                st.success("Saved!")
                st.rerun()
        with col_count:
            lines = [l.strip() for l in edited.split("\n") if l.strip() and not l.startswith("#")]
            st.caption(f"{len(lines)} active queries")


if __name__ == "__main__":
    main()
