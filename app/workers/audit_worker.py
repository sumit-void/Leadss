"""
LeadGen Pro — Audit Worker
Celery task: runs website quality audit (rule-based + optional Ollama).
"""

import asyncio
import logging

from app.workers.celery_app import celery_app
from app.models.database import get_sync_db
from app.models.business import Business, BusinessStatus
from app.models.website import Website
from app.models.email_model import Email
from app.models.audit import Audit
from app.services.ai_audit import run_audit

from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.audit_worker.run_audit_task", bind=True, max_retries=2)
@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=20))
def run_audit_task(self, business_id: str):
    """
    Run a website quality audit for a business.
    Generates scores, issues, summary, and outreach opener.
    """
    db = get_sync_db()

    try:
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one_or_none()

        if not business:
            return {"error": "Business not found"}

        # Get homepage data
        homepage = db.execute(
            select(Website).where(
                Website.business_id == business_id,
                Website.page_type == "homepage",
            )
        ).scalar_one_or_none()

        if not homepage:
            logger.info(f"[Audit] No homepage data for: {business.name}")
            return {"business_id": business_id, "error": "No homepage data"}

        # Check if has emails
        email_count = db.execute(
            select(Email).where(Email.business_id == business_id)
        ).scalars().all()

        # Build website data dict for audit
        website_data = {
            "url": homepage.url,
            "title": homepage.title or "",
            "meta_description": homepage.meta_description or "",
            "cms": homepage.cms_detected,
            "has_ssl": homepage.has_ssl,
            "is_mobile_friendly": homepage.is_mobile_friendly,
            "load_time_ms": homepage.load_time_ms or 0,
            "has_forms": homepage.has_forms,
            "social_links": homepage.social_links or {},
            "headings": homepage.headings or {},
            "phone_numbers": homepage.phone_numbers or [],
            "has_email": len(email_count) > 0,
            "business_name": business.name,
            "niche": business.niche or "",
        }

        # Update status
        business.status = BusinessStatus.AUDITING
        db.commit()

        # Run audit (async)
        loop = asyncio.new_event_loop()
        try:
            breakdown, method = loop.run_until_complete(run_audit(website_data))
        finally:
            loop.close()

        # Store audit result
        audit = Audit(
            business_id=business.id,
            overall_score=breakdown.total_score,
            design_score=breakdown.design_score,
            seo_score=breakdown.seo_score,
            mobile_score=breakdown.mobile_score,
            speed_score=breakdown.speed_score,
            trust_score=breakdown.trust_score,
            cta_score=breakdown.cta_score,
            issues=breakdown.issues,
            summary=breakdown.summary,
            outreach_opener=breakdown.outreach_opener,
            audit_method=method,
        )
        db.add(audit)

        # Update business
        business.lead_score = breakdown.total_score
        business.status = BusinessStatus.AUDITED
        db.commit()

        logger.info(f"[Audit] Done: {business.name} — score: {breakdown.total_score} ({method})")
        return {
            "business_id": business_id,
            "score": breakdown.total_score,
            "method": method,
            "issues": len(breakdown.issues),
        }

    except Exception as e:
        db.rollback()
        logger.error(f"[Audit] Error for {business_id}: {e}")
        raise
    finally:
        db.close()
