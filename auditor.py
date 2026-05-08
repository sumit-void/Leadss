"""
LeadGen — Website Auditor
Rule-based website quality scoring. 100% free, no API.
Higher score = more problems = better lead for your services.
"""


def audit_website(
    has_email=False, has_ssl=True, cms=None, is_mobile=True,
    load_time_ms=0, has_meta_desc=True, headings=None,
    has_forms=False, social_links=None, has_phone=False,
    title="", business_name="", niche="",
):
    """
    Score a business website. Returns dict with scores and outreach text.
    """
    headings = headings or {}
    social_links = social_links or {}
    issues = []
    score = 0  # 0-100, higher = needier prospect

    # Contact info
    if has_email:
        score += 15
    elif has_phone:
        score += 8
    else:
        score += 3
        issues.append("No contact email found")

    # SSL
    if not has_ssl:
        score += 10
        issues.append("No HTTPS/SSL — site is insecure")

    # CMS
    if cms == "wordpress":
        score += 8
        issues.append("WordPress site — may need updates/redesign")
    elif cms in ("wix", "squarespace"):
        score += 5
        issues.append(f"Built on {cms.title()} — limited customization")
    elif cms is None:
        score += 7
        issues.append("Unknown/custom platform — may need modernization")

    # Mobile
    if not is_mobile:
        score += 15
        issues.append("Not mobile-friendly — no viewport meta tag")

    # Speed
    if load_time_ms > 5000:
        score += 15
        issues.append(f"Very slow load ({load_time_ms}ms)")
    elif load_time_ms > 3000:
        score += 10
        issues.append(f"Slow load ({load_time_ms}ms)")

    # SEO
    if not has_meta_desc:
        score += 5
        issues.append("Missing meta description")
    if not headings.get("h1"):
        score += 5
        issues.append("Missing H1 heading")
    if not title or len(title) < 10:
        score += 5
        issues.append("Missing or poor page title")

    # Trust
    if not social_links:
        score += 5
        issues.append("No social media links")
    if not has_forms:
        score += 5
        issues.append("No contact form found")

    score = min(max(score, 0), 100)

    # Summary
    if score >= 70:
        quality = "high-priority"
    elif score >= 40:
        quality = "medium-priority"
    else:
        quality = "low-priority"

    issue_text = ", ".join(issues[:3]) if issues else "site looks decent"
    summary = f"{quality.title()} lead (score: {score}/100). Issues: {issue_text}."

    # Outreach opener
    name = business_name or "your business"
    if issues:
        opener = (
            f"Hi, I noticed {name}'s website could use some improvements — "
            f"specifically, {issues[0].lower()}. I help businesses like yours "
            f"modernize their online presence to attract more customers."
        )
    else:
        opener = (
            f"Hi, I came across {name}'s website. I help businesses grow "
            f"with modern web design and AI automation."
        )

    return {
        "total_score": score,
        "design_score": max(5 - len([i for i in issues if "design" in i.lower() or "modern" in i.lower()]), 0),
        "seo_score": max(5 - len([i for i in issues if "seo" in i.lower() or "meta" in i.lower() or "h1" in i.lower() or "title" in i.lower()]), 0),
        "mobile_score": 2 if not is_mobile else 8,
        "speed_score": 2 if load_time_ms > 5000 else (5 if load_time_ms > 3000 else 8),
        "trust_score": max(5 - len([i for i in issues if "social" in i.lower() or "ssl" in i.lower()]), 0),
        "cta_score": 3 if not has_forms else 8,
        "issues": issues,
        "summary": summary,
        "outreach_opener": opener,
    }
