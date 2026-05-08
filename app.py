"""
LeadGen — Dashboard
View leads, filter, export Excel/CSV. Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import io
import math
import os

from database import get_all_leads, get_batches, get_stats

st.set_page_config(page_title="LeadGen", page_icon="📧", layout="wide")

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
</style>
""", unsafe_allow_html=True)

QUERIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queriess.txt")


def make_excel(df, tab_size=20):
    out = io.BytesIO()
    cols = [c for c in ["Name", "Email", "Website", "Score", "Niche", "Location",
                         "Summary", "Opener", "Status"] if c in df.columns]
    export = df[cols].copy() if cols else df.copy()

    total = len(export)
    tabs = max(1, math.ceil(total / tab_size))

    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for i in range(tabs):
            s, e = i * tab_size, min((i + 1) * tab_size, total)
            chunk = export.iloc[s:e].reset_index(drop=True)
            chunk.index += 1
            sheet = f"Leads {s+1}-{e}" if total > 0 else "No Leads"
            chunk.to_excel(w, index=True, index_label="Sr", sheet_name=sheet)
    return out.getvalue()


def main():
    st.title("📧 LeadGen Dashboard")

    tab_leads, tab_queries = st.tabs(["📧 Leads", "⚙️ Queries"])

    # ═══════════════════════════════════════
    #  TAB 1: LEADS
    # ═══════════════════════════════════════
    with tab_leads:
        stats = get_stats()
        batches = get_batches()

        # Metrics
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="metric-box"><div class="metric-num">{stats["total"]}</div><div class="metric-lbl">Total Leads</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-box"><div class="metric-num">{stats["with_email"]}</div><div class="metric-lbl">With Email</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="metric-box"><div class="metric-num">{stats["audited"]}</div><div class="metric-lbl">Audited</div></div>', unsafe_allow_html=True)
        with c4:
            st.markdown(f'<div class="metric-box"><div class="metric-num">{stats["avg_score"]}</div><div class="metric-lbl">Avg Score</div></div>', unsafe_allow_html=True)

        if stats["total"] == 0:
            st.info("No leads yet. Run: `python run.py`")
            return

        # Filters
        with st.expander("🔍 Filters", expanded=False):
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                batch_options = ["All"] + [f"{b['batch_id']} ({b['count']})" for b in batches]
                batch_ids = ["All"] + [b["batch_id"] for b in batches]
                sel_label = st.selectbox("Batch", batch_options)
                sel_batch = batch_ids[batch_options.index(sel_label)]
            with fc2:
                search = st.text_input("Search", placeholder="Name, niche, location...")
                email_only = st.checkbox("Only with email", value=True)
            with fc3:
                min_score = st.slider("Min Score", 0, 100, 0, 5)

        # Load data
        leads = get_all_leads(
            batch_id=sel_batch if sel_batch != "All" else None,
            min_score=min_score if min_score > 0 else None,
            has_email=email_only if email_only else None,
        )

        if not leads:
            st.warning("No leads match your filters.")
            return

        df = pd.DataFrame(leads)

        # Search filter
        if search:
            mask = df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
            df = df[mask]

        # Rename columns for display
        display_cols = {
            "name": "Name",
            "all_emails": "Email",
            "website_url": "Website",
            "lead_score": "Score",
            "niche": "Niche",
            "location": "Location",
            "audit_summary": "Summary",
            "outreach_opener": "Opener",
            "status": "Status",
        }

        available = {k: v for k, v in display_cols.items() if k in df.columns}
        show_df = df[list(available.keys())].rename(columns=available)

        st.markdown(f"**Showing {len(show_df)} leads**")
        st.dataframe(show_df, use_container_width=True, hide_index=True, height=500)

        # Downloads
        st.markdown("---")
        col_xl, col_csv = st.columns(2)

        with col_xl:
            excel = make_excel(show_df)
            st.download_button(
                f"📥 Download Excel ({len(show_df)} leads)",
                data=excel,
                file_name="leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )

        with col_csv:
            csv = show_df.to_csv(index=False)
            st.download_button(
                f"📥 Download CSV ({len(show_df)} leads)",
                data=csv,
                file_name="leads.csv",
                mime="text/csv",
            )

    # ═══════════════════════════════════════
    #  TAB 2: QUERIES
    # ═══════════════════════════════════════
    with tab_queries:
        st.header("⚙️ Search Queries")
        st.caption("One per line. Used by `python run.py`")

        current = ""
        if os.path.exists(QUERIES_FILE):
            with open(QUERIES_FILE, "r", encoding="utf-8") as f:
                current = f.read()

        edited = st.text_area("Queries", value=current, height=500, label_visibility="collapsed")

        c1, c2 = st.columns([1, 3])
        with c1:
            if st.button("💾 Save", type="primary"):
                with open(QUERIES_FILE, "w", encoding="utf-8") as f:
                    f.write(edited)
                st.success("Saved!")
                st.rerun()
        with c2:
            lines = [l.strip() for l in edited.split("\n") if l.strip() and not l.startswith("#")]
            st.caption(f"{len(lines)} active queries")


if __name__ == "__main__":
    main()
