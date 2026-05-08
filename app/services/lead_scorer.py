"""
LeadGen Pro — Lead Scorer
Rule-based lead scoring — 100% free, no API required.
Higher score = business needs more help = better prospect for your services.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ScoreBreakdown:
    """Detailed scoring breakdown."""
    total_score: float = 0.0
    max_score: float = 100.0
    design_score: float = 5.0    # 0-10
    seo_score: float = 5.0
    mobile_score: float = 5.0
    speed_score: float = 5.0
    trust_score: float = 5.0
    cta_score: float = 5.0
    issues: list = field(default_factory=list)
    summary: str = ""
    outreach_opener: str = ""


def score_lead(
    has_email: bool = False,
    has_ssl: bool = True,
    cms: str = None,
    is_mobile_friendly: bool = True,
    load_time_ms: int = 0,
    has_meta_description: bool = True,
    headings: dict = None,
    has_forms: bool = False,
    social_links: dict = None,
    has_phone: bool = False,
    title: str = "",
    business_name: str = "",
    niche: str = "",
) -> ScoreBreakdown:
    """
    Score a lead based on their website quality.
    Higher score = more issues = better prospect for web services.
    """
    headings = headings or {}
    social_links = social_links or {}
    breakdown = ScoreBreakdown()
    issues = []
    lead_points = 0  # 0–100, higher = better lead

    # ── 1. Contact Info (0-15 pts) ─────────────────────
    if has_email:
        lead_points += 15
    elif has_phone:
        lead_points += 8
    else:
        lead_points += 3
        issues.append({"category": "contact", "severity": "high",
                       "description": "No contact email found on website"})

    # ── 2. SSL / Security (0-10 pts) ───────────────────
    if not has_ssl:
        lead_points += 10
        breakdown.trust_score -= 3
        issues.append({"category": "security", "severity": "high",
                       "description": "Website not using HTTPS/SSL"})
    else:
        lead_points += 2

    # ── 3. CMS Detection (0-10 pts) ───────────────────
    if cms == "wordpress":
        lead_points += 8  # Common client, likely needs updates
        issues.append({"category": "platform", "severity": "low",
                       "description": "WordPress site — may benefit from modern redesign"})
    elif cms in ("wix", "squarespace", "webflow"):
        lead_points += 5
        issues.append({"category": "platform", "severity": "low",
                       "description": f"Built on {cms.title()} — limited customization"})
    elif cms == "shopify":
        lead_points += 4
    elif cms is None:
        lead_points += 7
        issues.append({"category": "platform", "severity": "medium",
                       "description": "Custom/unknown platform — may need modernization"})

    # ── 4. Mobile Friendliness (0-15 pts) ──────────────
    if not is_mobile_friendly:
        lead_points += 15
        breakdown.mobile_score -= 4
        issues.append({"category": "mobile", "severity": "high",
                       "description": "Website not mobile-friendly — missing viewport meta"})
    else:
        lead_points += 3

    # ── 5. Page Speed (0-15 pts) ───────────────────────
    if load_time_ms > 5000:
        lead_points += 15
        breakdown.speed_score -= 4
        issues.append({"category": "speed", "severity": "high",
                       "description": f"Very slow page load ({load_time_ms}ms)"})
    elif load_time_ms > 3000:
        lead_points += 10
        breakdown.speed_score -= 2
        issues.append({"category": "speed", "severity": "medium",
                       "description": f"Slow page load ({load_time_ms}ms)"})
    elif load_time_ms > 0:
        lead_points += 3

    # ── 6. SEO Structure (0-15 pts) ────────────────────
    seo_issues = 0
    if not has_meta_description:
        seo_issues += 1
        issues.append({"category": "seo", "severity": "medium",
                       "description": "Missing meta description"})
    if not headings.get("h1"):
        seo_issues += 1
        issues.append({"category": "seo", "severity": "medium",
                       "description": "Missing H1 heading"})
    if not title or len(title) < 10:
        seo_issues += 1
        issues.append({"category": "seo", "severity": "medium",
                       "description": "Missing or poor page title"})

    lead_points += min(seo_issues * 5, 15)
    breakdown.seo_score -= seo_issues * 1.5

    # ── 7. Trust Elements (0-10 pts) ───────────────────
    if not social_links:
        lead_points += 5
        breakdown.trust_score -= 2
        issues.append({"category": "trust", "severity": "low",
                       "description": "No social media links found"})

    if not has_forms:
        lead_points += 5
        breakdown.cta_score -= 2
        issues.append({"category": "cta", "severity": "medium",
                       "description": "No contact form found"})

    # ── 8. Design Indicators (0-10 pts) ────────────────
    h_count = sum(len(v) for v in headings.values())
    if h_count < 3:
        lead_points += 5
        breakdown.design_score -= 2
        issues.append({"category": "design", "severity": "low",
                       "description": "Minimal content structure — few headings"})

    # ── Clamp and normalize ────────────────────────────
    lead_points = min(max(lead_points, 0), 100)

    # Clamp individual scores
    for attr in ["design_score", "seo_score", "mobile_score", "speed_score", "trust_score", "cta_score"]:
        setattr(breakdown, attr, max(min(getattr(breakdown, attr), 10.0), 0.0))

    breakdown.total_score = lead_points
    breakdown.issues = issues

    # ── Generate summary ───────────────────────────────
    if lead_points >= 70:
        quality = "high-priority"
    elif lead_points >= 40:
        quality = "medium-priority"
    else:
        quality = "low-priority"

    issue_list = ", ".join(i["description"].lower() for i in issues[:3])
    breakdown.summary = (
        f"This is a {quality} lead (score: {lead_points}/100). "
        f"Key issues: {issue_list}." if issues else
        f"This is a {quality} lead (score: {lead_points}/100). Website appears well-maintained."
    )

    # ── Generate outreach opener ───────────────────────
    name = business_name or "your business"
    if issues:
        top_issue = issues[0]["description"].lower()
        breakdown.outreach_opener = (
            f"Hi, I noticed {name}'s website could benefit from some improvements — "
            f"specifically, {top_issue}. I help businesses like yours modernize their "
            f"online presence to attract more customers."
        )
    else:
        breakdown.outreach_opener = (
            f"Hi, I came across {name}'s website and was impressed. "
            f"I specialize in helping businesses like yours grow further with AI automation."
        )

    return breakdown
