import sqlite3
import os
import sys
import math
import json
import ast
import argparse
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leadgen.db")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# ── Niche category mapping ────────────────────────────────────────────────────

NICHE_MAP = {
    "interior design": "Interior Design Firm",
    "interior designer": "Interior Design Firm",
    "furniture": "Furniture Brand",
    "architecture": "Architecture Studio",
    "architect": "Architecture Studio",
    "real estate": "Real Estate Agency",
    "estate agent": "Real Estate Agency",
    "construction": "Construction Company",
    "home builder": "Construction Company",
    "building contractor": "Construction Company",
    "dental": "Dental Clinic",
    "dentist": "Dental Clinic",
    "medical": "Medical Clinic",
    "doctor": "Medical Clinic",
    "gp surgery": "Medical Clinic",
    "urgent care": "Medical Clinic",
    "consulting": "Consulting Firm",
    "consultant": "Consulting Firm",
    "ecommerce": "Local Ecommerce Brand",
    "handmade": "Local Ecommerce Brand",
    "artisan": "Local Ecommerce Brand",
    "boutique": "Local Ecommerce Brand",
    "shop": "Local Ecommerce Brand",
    "store": "Local Ecommerce Brand",
}

def classify_niche(raw_niche: str, query: str = "") -> str:
    text = f"{raw_niche} {query}".lower()
    for keyword, category in NICHE_MAP.items():
        if keyword in text:
            return category
    return raw_niche.title() if raw_niche else "Other"

def extract_country(location: str, query: str = "") -> str:
    text = f"{location} {query}".lower()
    if "uk" in text.split() or "united kingdom" in text:
        return "UK"
    elif "australia" in text:
        return "Australia"
    elif "canada" in text:
        return "Canada"
    else:
        return "USA"

# ── CMS → readable tech name ─────────────────────────────────────────────────

CMS_DISPLAY = {
    "wordpress": "WordPress",
    "shopify": "Shopify",
    "wix": "Wix",
    "squarespace": "Squarespace",
    "webflow": "Webflow",
}

# ── Synthesize Observations ────────────────────────────────────────────────────

def audit_to_quality(audit_score: float) -> int:
    if audit_score is None or audit_score == 0:
        return 5
    quality = round(10 - (audit_score / 10))
    return max(1, min(10, quality))

def mobile_sub_score(raw: int) -> int:
    if raw is None:
        return 5
    return max(1, min(10, raw))

def estimate_age_style(cms: str, is_mobile: bool, issues: list) -> str:
    if not is_mobile:
        return "Likely Pre-2015 (Not Mobile Responsive)"
    if "Unknown/custom platform" in " ".join(issues):
        return "Custom Built / Older PHP or HTML"
    if cms == "wordpress":
        return "Older WordPress Layout"
    return "Standard Modern (Few Years Old)"

def synthesize_ui_ux(design_score: float, is_mobile: bool) -> str:
    if not is_mobile:
        return "Poor (Not Mobile Friendly)"
    if design_score <= 2:
        return "Weak (Poor layouts, clunky UI)"
    if design_score <= 4:
        return "Average (Standard template, needs refresh)"
    return "Good/Modern"

def synthesize_speed(speed_score: float) -> str:
    if speed_score <= 2:
        return "Very Slow (Needs Image/Asset Optimization)"
    if speed_score <= 5:
        return "Slow (Could be improved)"
    return "Acceptable/Fast"

def synthesize_cta(cta_score: float, issues: list) -> str:
    if cta_score <= 3 or "No contact form found" in issues:
        return "Weak (No clear forms or booking buttons)"
    return "Present (Forms/booking available)"

def synthesize_seo(seo_score: float, issues: list) -> str:
    weaknesses = [i for i in issues if "meta" in i.lower() or "h1" in i.lower() or "title" in i.lower()]
    if weaknesses:
        return f"Weak ({', '.join(weaknesses)})"
    return "Basic SEO Present"

def suggest_improvement(issues: list, cms: str, is_mobile: bool) -> str:
    suggestions = []
    if not is_mobile:
        suggestions.append("Mobile-responsive redesign")
    if cms == "wordpress":
        suggestions.append("Modern frontend rebuild (React/Next.js)")
    if any("slow" in i.lower() for i in issues):
        suggestions.append("Performance optimization")
    if any("ssl" in i.lower() for i in issues):
        suggestions.append("SSL certificate setup")
    if any("seo" in i.lower() or "meta" in i.lower() or "h1" in i.lower() for i in issues):
        suggestions.append("SEO technical improvements")
    if any("form" in i.lower() for i in issues):
        suggestions.append("Lead capture/booking forms")
    
    if not suggestions:
        suggestions.append("General UI/UX refresh")
    return " + ".join(suggestions[:3])

def calculate_lead_potential(quality_score: int, has_email: bool, has_social: bool) -> str:
    if quality_score <= 4 and has_email:
        return "High (Bad site + Contact info available)"
    if quality_score <= 6 and has_email:
        return "Medium (Average site + Contact info available)"
    if not has_email:
        return "Low (Missing contact info)"
    return "Low (Website is already decent)"

# ── Safe parse helpers ────────────────────────────────────────────────────────

def safe_parse_dict(val):
    if isinstance(val, dict): return val
    if not val or val == "{}": return {}
    try: return json.loads(val.replace("'", '"'))
    except:
        try: return ast.literal_eval(val)
        except: return {}

def safe_parse_list(val):
    if isinstance(val, list): return val
    if not val or val == "[]": return []
    try: return json.loads(val.replace("'", '"'))
    except:
        try: return ast.literal_eval(val)
        except: return []

# ── Main export ───────────────────────────────────────────────────────────────

def export_all(min_score=0, email_only=False):
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = """
        SELECT
            b.id, b.name, b.website_url, b.niche, b.location, b.source_query, b.snippet,
            b.lead_score, b.status,
            GROUP_CONCAT(DISTINCT e.email) AS all_emails,
            a.overall_score, a.mobile_score, a.design_score, a.speed_score, a.seo_score,
            a.trust_score, a.cta_score, a.issues, a.summary
        FROM businesses b
        LEFT JOIN emails e ON e.business_id = b.id
        LEFT JOIN audits a ON a.business_id = b.id
        WHERE b.status = 'audited'
    """
    params = []
    if min_score > 0:
        sql += " AND b.lead_score >= ?"
        params.append(min_score)

    sql += " GROUP BY b.id ORDER BY b.lead_score DESC"
    rows = conn.execute(sql, params).fetchall()

    if not rows:
        print("❌ No audited leads found. Run the pipeline first.")
        conn.close()
        sys.exit(1)

    website_data = {}
    ws_rows = conn.execute("""
        SELECT business_id, url, page_type, cms_detected, social_links,
               is_mobile_friendly, title, phone_numbers
        FROM websites
    """).fetchall()

    for w in ws_rows:
        bid = w["business_id"]
        if bid not in website_data:
            website_data[bid] = {"pages": [], "cms": None, "socials": {}, "contact_url": "", "is_mobile": False, "phones": []}
        
        page_type = w["page_type"] or "homepage"
        if page_type == "homepage" and w["cms_detected"]:
            website_data[bid]["cms"] = w["cms_detected"]
        if page_type == "contact":
            website_data[bid]["contact_url"] = w["url"] or ""

        socials = safe_parse_dict(w["social_links"])
        website_data[bid]["socials"].update(socials)
        
        phones = safe_parse_list(w["phone_numbers"])
        website_data[bid]["phones"].extend(phones)

        if w["is_mobile_friendly"]:
            website_data[bid]["is_mobile"] = True

    conn.close()

    export_rows = []
    for row in rows:
        bid = row["id"]
        emails = (row["all_emails"] or "").split(",")
        emails = [e.strip() for e in emails if e.strip()]

        if email_only and not emails:
            continue

        wd = website_data.get(bid, {})
        socials = wd.get("socials", {})
        phones = list(set(wd.get("phones", [])))
        issues = safe_parse_list(row["issues"]) if row["issues"] else []
        cms = wd.get("cms") or None
        is_mobile = wd.get("is_mobile", False)

        quality_score = audit_to_quality(row["overall_score"])
        mobile_score = mobile_sub_score(row["mobile_score"])
        design_score = row["design_score"] or 5
        speed_score = row["speed_score"] or 5
        cta_score = row["cta_score"] or 5
        seo_score = row["seo_score"] or 5
        has_social = bool(socials)
        has_email = bool(emails)

        export_rows.append({
            "Business Name": row["name"] or "",
            "Website URL": row["website_url"] or "",
            "Business Niche": classify_niche(row["niche"] or "", row["source_query"] or ""),
            "Country": extract_country(row["location"] or "", row["source_query"] or ""),
            "City/Location": row["location"] or "",
            "Short Business Description": (row["snippet"] or "")[:250],
            
            "Contact Email": emails[0] if emails else "",
            "Contact Page URL": wd.get("contact_url", ""),
            "Phone Number": phones[0] if phones else "",
            "Owner/Founder Name": "",
            
            "Instagram URL": socials.get("instagram", ""),
            "LinkedIn URL": socials.get("linkedin", ""),
            "Facebook URL": socials.get("facebook", ""),
            
            "Website Quality Score (1-10)": quality_score,
            "Mobile Responsiveness Score": mobile_score,
            "Estimated Website Age/Style": estimate_age_style(cms, is_mobile, issues),
            "UI/UX Quality": synthesize_ui_ux(design_score, is_mobile),
            "Speed/Performance Observation": synthesize_speed(speed_score),
            "Whether site appears outdated": "Yes" if quality_score <= 4 else ("Somewhat" if quality_score <= 6 else "No"),
            "Broken sections/issues found": "; ".join(issues) if issues else "None observed",
            "Weak CTA observations": synthesize_cta(cta_score, issues),
            "SEO weakness observations": synthesize_seo(seo_score, issues),
            
            "Why this business may need redesign": "Poor mobile experience" if not is_mobile else "General UI/UX/Performance issues",
            "Suggested improvement opportunity": suggest_improvement(issues, cms, is_mobile),
            "Estimated lead potential": calculate_lead_potential(quality_score, has_email, has_social),
        })

    if not export_rows:
        print("❌ No leads matched your filters.")
        sys.exit(1)

    df = pd.DataFrame(export_rows)
    df = df.sort_values("Website Quality Score (1-10)", ascending=True).reset_index(drop=True)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = os.path.join(OUTPUT_DIR, f"leads_export_{timestamp}.csv")
    xlsx_path = os.path.join(OUTPUT_DIR, f"leads_export_{timestamp}.xlsx")

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    tab_size = 50
    total = len(df)
    tabs = max(1, math.ceil(total / tab_size))

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        for i in range(tabs):
            s, e = i * tab_size, min((i + 1) * tab_size, total)
            chunk = df.iloc[s:e].copy()
            chunk.index = range(1, len(chunk) + 1)
            sheet_name = f"Leads {s+1}-{e}"
            chunk.to_excel(writer, index=True, index_label="Sr", sheet_name=sheet_name)

            ws = writer.sheets[sheet_name]
            for col_idx, col_name in enumerate(["Sr"] + list(df.columns), 1):
                max_len = min(len(str(col_name)) + 2, 40)
                ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max_len

    print(f"\n{'=' * 60}")
    print(f"  ✅ EXPORT COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Total leads : {len(df)}")
    print(f"  With email  : {len(df[df['Contact Email'] != ''])}")
    print(f"  CSV         : {csv_path}")
    print(f"  Excel       : {xlsx_path}")
    print(f"{'=' * 60}")
    print()

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LeadGen — Full Export")
    ap.add_argument("--min-score", type=int, default=0, help="Minimum audit score to include")
    ap.add_argument("--email-only", action="store_true", help="Only export leads with email addresses")
    args = ap.parse_args()
    export_all(min_score=args.min_score, email_only=args.email_only)
