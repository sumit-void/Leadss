"""
LeadGen Pro — AI Audit Service
Uses free Ollama (local LLM) if available, falls back to rule-based scoring.
"""

import logging
import json
from typing import Optional

from app.services.lead_scorer import score_lead, ScoreBreakdown
from app.config import get_settings

logger = logging.getLogger(__name__)


def _build_audit_prompt(website_data: dict) -> str:
    """Build an audit prompt from crawled website data."""
    return f"""Analyze this website and provide a JSON audit report.

Website: {website_data.get('url', 'N/A')}
Title: {website_data.get('title', 'N/A')}
Meta Description: {website_data.get('meta_description', 'None')}
CMS: {website_data.get('cms', 'Unknown')}
SSL: {website_data.get('has_ssl', False)}
Mobile Friendly: {website_data.get('is_mobile_friendly', False)}
Load Time: {website_data.get('load_time_ms', 0)}ms
Has Forms: {website_data.get('has_forms', False)}
Social Links: {json.dumps(website_data.get('social_links', {}))}
Headings: {json.dumps(website_data.get('headings', {}))}
Business: {website_data.get('business_name', 'N/A')}
Niche: {website_data.get('niche', 'N/A')}

Return ONLY valid JSON with this structure:
{{
    "design_score": 0-10,
    "seo_score": 0-10,
    "mobile_score": 0-10,
    "speed_score": 0-10,
    "trust_score": 0-10,
    "cta_score": 0-10,
    "issues": [
        {{"category": "design|seo|mobile|speed|trust|cta", "severity": "high|medium|low", "description": "..."}}
    ],
    "summary": "2-3 sentence audit summary",
    "outreach_opener": "1-2 sentence personalized cold email opener"
}}"""


async def run_ollama_audit(website_data: dict) -> Optional[ScoreBreakdown]:
    """Run audit using free local Ollama LLM."""
    settings = get_settings()

    if not settings.ollama_base_url:
        return None

    try:
        import ollama as ollama_lib

        client = ollama_lib.Client(host=settings.ollama_base_url)
        prompt = _build_audit_prompt(website_data)

        response = client.chat(
            model=settings.ollama_model,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response["message"]["content"]

        # Try to parse JSON from response
        json_match = content
        if "```json" in content:
            json_match = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_match = content.split("```")[1].split("```")[0]

        data = json.loads(json_match.strip())

        breakdown = ScoreBreakdown(
            design_score=float(data.get("design_score", 5)),
            seo_score=float(data.get("seo_score", 5)),
            mobile_score=float(data.get("mobile_score", 5)),
            speed_score=float(data.get("speed_score", 5)),
            trust_score=float(data.get("trust_score", 5)),
            cta_score=float(data.get("cta_score", 5)),
            issues=data.get("issues", []),
            summary=data.get("summary", ""),
            outreach_opener=data.get("outreach_opener", ""),
        )

        # Calculate overall score
        scores = [breakdown.design_score, breakdown.seo_score, breakdown.mobile_score,
                  breakdown.speed_score, breakdown.trust_score, breakdown.cta_score]
        # Invert: lower website quality = higher lead score
        avg = sum(scores) / len(scores)
        breakdown.total_score = round((10 - avg) * 10, 1)

        return breakdown

    except ImportError:
        logger.info("Ollama package not installed, using rule-based scoring")
        return None
    except Exception as e:
        logger.warning(f"Ollama audit failed: {e}, falling back to rule-based")
        return None


def run_rule_based_audit(website_data: dict) -> ScoreBreakdown:
    """Run audit using free rule-based scoring."""
    return score_lead(
        has_email=website_data.get("has_email", False),
        has_ssl=website_data.get("has_ssl", True),
        cms=website_data.get("cms"),
        is_mobile_friendly=website_data.get("is_mobile_friendly", True),
        load_time_ms=website_data.get("load_time_ms", 0),
        has_meta_description=bool(website_data.get("meta_description")),
        headings=website_data.get("headings", {}),
        has_forms=website_data.get("has_forms", False),
        social_links=website_data.get("social_links", {}),
        has_phone=bool(website_data.get("phone_numbers")),
        title=website_data.get("title", ""),
        business_name=website_data.get("business_name", ""),
        niche=website_data.get("niche", ""),
    )


async def run_audit(website_data: dict) -> tuple[ScoreBreakdown, str]:
    """
    Run website audit. Tries Ollama first (free), falls back to rules.
    Returns (ScoreBreakdown, method_used).
    """
    # Try Ollama first
    result = await run_ollama_audit(website_data)
    if result:
        return result, "ollama"

    # Fall back to rule-based (always free)
    result = run_rule_based_audit(website_data)
    return result, "rule_based"
