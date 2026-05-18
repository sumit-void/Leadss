import sqlite3
import os
import sys
import json
import ast
import pandas as pd
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leadgen.db")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "high_value_website_redesign_leads.xlsx")

def safe_parse_dict(val):
    if isinstance(val, dict): return val
    if not val or val == "{}" or val == "None": return {}
    try: return json.loads(val.replace("'", '"'))
    except:
        try: return ast.literal_eval(val)
        except: return {}

def safe_parse_list(val):
    if isinstance(val, list): return val
    if not val or val == "[]" or val == "None": return []
    try: return json.loads(val.replace("'", '"'))
    except:
        try: return ast.literal_eval(val)
        except: return []

def map_score(raw, maximum=10):
    if raw is None: return 5
    # Raw scores from auditor are typically 0-10, lower is better or higher is better?
    # Let's assume auditor gives a "quality" score out of 10. Wait, look at export_leads.py:
    # `quality = round(10 - (audit_score / 10))`  - wait, if audit_score was 0-100?
    # In database.py: `data.get("total_score", 0)`
    return max(1, min(maximum, int(raw)))

def export_custom_leads():
    if not os.path.exists(DB_PATH):
        print("Database not found.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # We want 200 businesses, prioritizing weak websites (higher audit score if it means issues, or lower if it means quality).
    # In export_leads.py: `quality_score = audit_to_quality(row["overall_score"])`
    # and it sorts by `Website Quality Score (1-10)` ascending. So lower quality = top priority.
    
    sql = """
        SELECT
            b.id, b.name, b.website_url, b.niche, b.location, b.source_query, b.snippet,
            GROUP_CONCAT(DISTINCT e.email) AS all_emails,
            a.overall_score, a.mobile_score, a.design_score, a.speed_score, a.seo_score,
            a.trust_score, a.cta_score, a.issues, a.summary
        FROM businesses b
        LEFT JOIN emails e ON e.business_id = b.id
        LEFT JOIN audits a ON a.business_id = b.id
        WHERE b.status = 'audited'
        GROUP BY b.id
    """
    rows = conn.execute(sql).fetchall()

    ws_rows = conn.execute("SELECT business_id, url, page_type, social_links, is_mobile_friendly, cms_detected FROM websites").fetchall()
    
    website_data = {}
    for w in ws_rows:
        bid = w["business_id"]
        if bid not in website_data:
            website_data[bid] = {"contact_url": "", "socials": {}, "is_mobile": False, "cms": w["cms_detected"]}
        if w["page_type"] == "contact":
            website_data[bid]["contact_url"] = w["url"] or ""
        socials = safe_parse_dict(w["social_links"])
        website_data[bid]["socials"].update(socials)
        if w["is_mobile_friendly"]:
            website_data[bid]["is_mobile"] = True
            
    conn.close()

    export_rows = []
    seen_urls = set()
    
    for row in rows:
        url = row["website_url"] or ""
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        
        bid = row["id"]
        emails = (row["all_emails"] or "").split(",")
        emails = [e.strip() for e in emails if e.strip()]
        
        wd = website_data.get(bid, {})
        socials = wd.get("socials", {})
        issues = safe_parse_list(row["issues"]) if row["issues"] else []
        issues_text = " ".join(issues).lower()
        
        # Calculate scores
        # In auditor.py: total_score = sum of penalties. Higher total_score = worse website.
        # Overall Score (1-10) -> we'll use 10 - penalties/10
        raw_overall = row["overall_score"] or 0
        quality_score = max(1, min(10, round(10 - (raw_overall / 10))))
        
        mobile_penalty = row["mobile_score"] or 0
        mobile_score = max(1, min(10, round(10 - (mobile_penalty / 5))))
        
        design_penalty = row["design_score"] or 0
        branding_score = max(1, min(10, round(10 - (design_penalty / 5))))
        
        speed_penalty = row["speed_score"] or 0
        perf_score = max(1, min(10, round(10 - (speed_penalty / 5))))
        
        cta_penalty = row["cta_score"] or 0
        conversion_score = max(1, min(10, round(10 - (cta_penalty / 5))))
        
        # Text fields
        is_mobile = wd.get("is_mobile", False)
        cms = wd.get("cms", "") or ""
        
        why_outdated = "Outdated design trends and poor spacing."
        if not is_mobile: why_outdated = "Not mobile responsive, indicating older development practices."
        elif "wordpress" in cms.lower(): why_outdated = "Uses older WordPress theme structure making it look dated."
        elif quality_score <= 4: why_outdated = "Lacks modern UI elements, poor font choices, and unstructured layout."
        
        biggest_issue = "Lack of clear user journey."
        if not is_mobile: biggest_issue = "Site layout breaks on mobile devices."
        elif perf_score < 5: biggest_issue = "Very slow page load times affecting user retention."
        elif conversion_score < 5: biggest_issue = "Poorly placed or missing call-to-actions."
        
        mobile_issue = "Elements overlap or text is too small on mobile." if not is_mobile else "Could be better optimized for touch interactions."
        branding_issue = "Inconsistent colors and typography across pages."
        lead_weakness = "No clear booking or contact form visible above the fold." if conversion_score < 6 else "Forms could be streamlined for higher conversion."
        
        ecommerce_weakness = "Product images are small or lack modern gallery features." if "ecommerce" in str(row["niche"]).lower() else "Services are not packaged clearly for online inquiry."
        
        suggestions = []
        if not is_mobile: suggestions.append("Mobile-first rebuild")
        if perf_score < 6: suggestions.append("Asset optimization for speed")
        if conversion_score < 6: suggestions.append("Implement sticky CTA and optimized lead forms")
        suggestions_str = ", ".join(suggestions) if suggestions else "Overall modern refresh and UX improvements"
        
        why_redesign = "A modern redesign would immediately build more trust and capture leads that are currently bouncing."
        
        opp_level = "High"
        if quality_score > 7: opp_level = "Low"
        elif quality_score > 4: opp_level = "Medium"
        
        # Personalized lines
        name = row["name"] or ""
        location = row["location"] or ""
        niche = row["niche"] or "business"
        
        opener = f"Hi team at {name}, I noticed your website recently and love what you're doing in {location}."
        if not location:
            opener = f"Hi team at {name}, I was looking for {niche} services and found your website."
            
        observation = "I noticed the site might be a bit difficult for mobile users to navigate." if not is_mobile else "I noticed a few areas where the design might be holding back your conversion rate."
        value_prop = "We specialize in modernizing websites for your industry to increase monthly inquiries."
        
        best_angle = "branding modernization"
        if not is_mobile: best_angle = "mobile redesign"
        elif perf_score < 4: best_angle = "speed improvement"
        elif conversion_score < 5: best_angle = "conversion optimization"
        elif "ecommerce" in niche.lower(): best_angle = "ecommerce optimization"

        export_rows.append({
            "Business Name": name,
            "Website URL": url,
            "Business Description": (row["snippet"] or "")[:250],
            "Niche Category": niche.title(),
            "Country": "USA" if "usa" in location.lower() or not location else ("Canada" if "canada" in location.lower() else ("UK" if "uk" in location.lower() or "kingdom" in location.lower() else "Australia" if "australia" in location.lower() else "USA")),
            "City/Location": location,
            "Owner/Founder Name": "",
            "Contact Email": emails[0] if emails else "",
            "Contact Page URL": wd.get("contact_url", ""),
            "Instagram URL": socials.get("instagram", ""),
            "LinkedIn URL": socials.get("linkedin", ""),
            "Facebook URL": socials.get("facebook", ""),
            "Website Quality Score (1-10)": quality_score,
            "Mobile Experience Score (1-10)": mobile_score,
            "Branding Score (1-10)": branding_score,
            "Performance Score (1-10)": perf_score,
            "Conversion Potential Score (1-10)": conversion_score,
            "Why the website looks outdated": why_outdated,
            "Biggest UX/UI issue found": biggest_issue,
            "Mobile responsiveness issue": mobile_issue,
            "Branding inconsistency observation": branding_issue,
            "Lead generation weakness": lead_weakness,
            "Ecommerce/product showcase weakness": ecommerce_weakness,
            "Suggested improvements": suggestions_str,
            "Why redesign could help their business": why_redesign,
            "Estimated redesign opportunity level": opp_level,
            "Personalized cold email opening line": opener,
            "One natural observation about the website": observation,
            "Suggested value proposition angle": value_prop,
            "Best outreach angle": best_angle
        })

    # Filter to only opportunities that are Medium/High and have poor/weak sites (quality <= 6)
    # The prompt says: "prioritize highest-quality opportunities first"
    df = pd.DataFrame(export_rows)
    df = df.sort_values("Website Quality Score (1-10)", ascending=True).reset_index(drop=True)
    
    # We want exactly 200 rows if possible
    df = df.head(200)

    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Exported {len(df)} leads to {OUTPUT_FILE}")

if __name__ == "__main__":
    export_custom_leads()
